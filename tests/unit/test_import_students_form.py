"""
Students are imported from one form (issue #142): an uploaded file, pasted rows or a Google Sheets link.
Files may be CSV, TSV or Excel, and pasted rows comma or tab separated, so rows copied straight out of a
spreadsheet can be pasted. The same form's second button imports the Canvas roster, with the same
options. The seed exam has three students.
"""
import html
import io
import re

import pytest
from openpyxl import Workbook


import server.services.core.data as data
from server.models import db, Student

EXAM_URL = '/offerings/1234567/exams/midterm1'
IMPORT_URL = f'{EXAM_URL}/students/import/'
CSV = 'canvas id,email,name,lefty\n777777,new@berkeley.edu,New Student,true\n'
TSV = 'canvas id\temail\tname\tlefty\n777777\tnew@berkeley.edu\tNew Student\ttrue\n'
OPTIONS = {
    'revalidate_existing_assignments': 'y', 'assignment_import_strategy': 'revalidate',
    'updated_student_info_import_strategy': 'merge', 'updated_preference_import_strategy': 'merge',
    'new_student_import_strategy': 'append', 'missing_student_import_strategy': 'ignore',
}


@pytest.fixture
def staff(seeded_db, login_as):
    return login_as(1)


def _import(client, **fields):
    page = client.get(IMPORT_URL).get_data(as_text=True)
    token = re.search(r'name="csrf_token" type="hidden" value="([^"]+)"', page).group(1)
    response = client.post(IMPORT_URL, data={'csrf_token': token, **OPTIONS, **fields},
                           content_type='multipart/form-data', follow_redirects=True)
    messages = [html.unescape(' '.join(m.split())) for m in
                re.findall(r'<span class="alert-message">(.*?)</span>', response.get_data(as_text=True), re.S)]
    return response, messages


def _new_student():
    db.session.expire_all()
    return Student.query.filter_by(exam_id=1, canvas_id='777777').one_or_none()


@pytest.mark.parametrize('text', [CSV, TSV, CSV.replace('\n', '\r\n'), '﻿' + TSV])
def test_paste_comma_or_tab_separated_rows(staff, text):
    _, messages = _import(staff, text=text)
    assert 'Import done. 1 new students' in messages[0]
    assert _new_student().wants == {'lefty'}


@pytest.mark.parametrize('filename, content', [('roster.csv', CSV), ('roster.tsv', TSV), ('roster.txt', TSV)])
def test_upload_a_csv_or_tsv_file(staff, filename, content):
    _, messages = _import(staff, file=(io.BytesIO(content.encode('utf-8')), filename))
    assert 'Import done. 1 new students' in messages[0]
    assert _new_student().wants == {'lefty'}


def _xlsx(*lines):
    workbook = Workbook()
    for line in lines:
        workbook.active.append(line)
    workbook.create_sheet('Other').append(['canvas id', 'email', 'name'])
    content = io.BytesIO()
    workbook.save(content)
    return content.getvalue()


def test_upload_an_excel_file(staff):
    # Excel keeps numbers as numbers and TRUE as a boolean; the first sheet is read
    content = _xlsx(['Canvas ID', 'Email', 'Name', 'Lefty', 'Student ID'], [],
                    [777777, 'new@berkeley.edu', 'New Student', True, 3034567890.0])
    _, messages = _import(staff, file=(io.BytesIO(content), 'roster.xlsx'))
    assert 'Import done. 1 new students' in messages[0]
    student = _new_student()
    assert (student.wants, student.sid) == ({'lefty'}, '3034567890')


def test_upload_an_unreadable_excel_file(staff):
    response, messages = _import(staff, file=(io.BytesIO(b'PK\x03\x04 not really'), 'roster.xlsx'))
    assert response.status_code == 200
    assert messages == ["Couldn't read the Excel file: save it as .xlsx or as CSV"]
    assert _new_student() is None


def test_upload_rejects_other_files(staff):
    response, messages = _import(staff, file=(io.BytesIO(b'\xd0\xcf\x11\xe0'), 'roster.xls'))
    assert response.status_code == 200
    assert messages == ['file: Choose a CSV, TSV or Excel (.xlsx) file']
    assert _new_student() is None


@pytest.fixture
def sheet(monkeypatch):
    """A Google Sheet with two tabs; records which tab was read."""
    read = []

    def tab_content(sheet_url, tab):
        read.append(tab)
        headers, rows = data.parse_csv_str(CSV)
        return headers, rows

    monkeypatch.setattr(data, 'get_spreadsheet_tabs', lambda sheet_url: ['Roster', 'Other'])
    monkeypatch.setattr(data, 'get_spreadsheet_tab_content', tab_content)
    return read


@pytest.mark.parametrize('tab, read', [('', 'Roster'), ('Other', 'Other')])
def test_google_sheet_link(staff, sheet, tab, read):
    _, messages = _import(staff, sheet_url='https://docs.google.com/spreadsheets/d/abc123/edit', sheet_range=tab)
    assert 'Import done. 1 new students' in messages[0]
    assert sheet == [read]  # without a tab, the first one
    assert _new_student() is not None


def test_nothing_to_import(staff):
    response, messages = _import(staff)
    assert response.status_code == 200
    assert messages == ['Choose a file, paste a roster or enter a Google Sheets link to import']
    assert Student.query.filter_by(exam_id=1).count() == 3


def test_first_source_given_is_used(staff, sheet):
    # the page stops this in the browser; the server takes the file, then pasted rows, then a link
    _, messages = _import(staff, file=(io.BytesIO(CSV.encode()), 'roster.csv'),
                          text=CSV.replace('777777', '888888'),
                          sheet_url='https://docs.google.com/spreadsheets/d/abc123/edit')
    assert 'Import done. 1 new students' in messages[0]
    assert _new_student() is not None
    assert Student.query.filter_by(exam_id=1, canvas_id='888888').count() == 0
    assert sheet == []


def test_page_has_one_form_with_one_set_of_options(staff):
    page = staff.get(IMPORT_URL).get_data(as_text=True)
    assert 'nav-tabs' not in page
    # besides the navbar's Log Out
    assert re.findall(r'<form[^>]*action="([^"]+)"', page) == ['/logout/', IMPORT_URL]
    # its second button imports the Canvas roster, with the same options
    assert page.count('value="Import"') == 1
    assert f'formaction="{IMPORT_URL}from_canvas_roster/"' in page
    assert page.count('name="missing_student_import_strategy"') == 1
    assert 'canvas id</strong>, <strong>email</strong> and <strong>name</strong> are required' in page


def test_page_says_which_options_the_canvas_roster_ignores(staff):
    page = staff.get(IMPORT_URL).get_data(as_text=True)
    options = re.findall(r'<div class="mb-3">(.*?)</div>\s*(?=<div class="mb-3"|</div>)',
                         page.split('<div class="import-strategies">')[1], re.S)
    ignored = [re.search(r'name="(\w+)"', option).group(1) for option in options
               if 'Not used when importing the Canvas roster.' in option]
    assert ignored == ['assignment_import_strategy']


@pytest.mark.parametrize('email, shown', [
    ('seating@example.iam.gserviceaccount.com',
     'share it with <strong class="share-email">seating@example.iam.gserviceaccount.com</strong>'),
    (None, "share it with the seating tool's Google account"),
])
def test_page_names_the_google_account_to_share_with(app, staff, email, shown):
    app.config['GCP_SA_EMAIL'] = email
    assert shown in staff.get(IMPORT_URL).get_data(as_text=True)
