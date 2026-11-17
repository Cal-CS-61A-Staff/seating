"""
Importing students must not create duplicates (issue #42). A row is matched to a student by
canvas id, falling back to student id, then email, and a student listed on several rows is
created once. The seed exam has Jimmy Xu (234567), Sharon Lovera (345678) and Lavender Angela (456789).
"""
import io
import re

import pytest
from markupsafe import Markup
from werkzeug.datastructures import FileStorage

from server.models import db, Exam, Student, User
from server.services.core.student import InvalidRow, StudentImportConfig, describe_invalid_rows, normalize_id, \
    prepare_students, room_id_to_attr
from server.typings.enum import NewRowImportStrategy, UpdatedRowImportStrategy
from server.services.csv import parse_csv, parse_csv_str

EXAM_URL = '/offerings/1234567/exams/midterm1'
HEADER = 'email,name,canvas id,student id\n'


@pytest.fixture
def exam(seeded_db):
    exam = db.session.get(Exam, 1)
    assert len(exam.students) == 3
    jimmy = Student.query.filter_by(exam_id=exam.id, canvas_id='234567').one()
    jimmy.sid = '3031000001'
    jimmy.email = 'jimmy@berkeley.edu'
    db.session.commit()
    yield exam


def _import(exam, csv_text):
    """Runs CSV text through the import like the upload view does, and returns its result."""
    headers, rows = parse_csv_str(csv_text)
    new, updated, invalid, _ = prepare_students(exam, headers, rows)
    db.session.add_all(new + updated)
    db.session.commit()
    return new, updated, invalid


def _students_named(name):
    return Student.query.filter_by(exam_id=1, name=name).all()


@pytest.mark.parametrize('value, expected', [
    ('234567', '234567'),
    (' 234567 ', '234567'),
    ('234567.0', '234567'),
    ('234567.00', '234567'),
    (234567, '234567'),
    ('', None),
    ('  ', None),
    (None, None),
    ('234567.5', '234567.5'),
    ('ab.0', 'ab.0'),
    # student ids are not always numbers: a student can be listed by their UID
    ('UID:1234567', 'UID:1234567'),
    (' UID:1234567 ', 'UID:1234567'),
    ('UID:1234567.0', 'UID:1234567.0'),
])
def test_normalize_id(value, expected):
    assert normalize_id(value) == expected


@pytest.mark.parametrize('canvas_id', [' 234567', '234567 ', '234567.0'])
def test_canvas_id_from_a_spreadsheet_matches(exam, canvas_id):
    new, updated, invalid = _import(exam, HEADER + f'jimmy@berkeley.edu,Jimmy Xu,{canvas_id},3031000001\n')
    assert (len(new), len(updated), len(invalid)) == (0, 1, 0)
    assert len(_students_named('Jimmy Xu')) == 1


def test_new_canvas_id_is_stored_clean(exam):
    new, _, _ = _import(exam, HEADER + 'new@berkeley.edu,New Student, 777777.0 ,3031000002.0\n')
    assert new[0].canvas_id == '777777'
    assert new[0].sid == '3031000002'


def test_roster_canvas_ids_are_ints(exam):
    # the canvas roster import passes canvas ids as numbers and student ids as None
    rows = [{'canvas id': 234567, 'email': 'jimmy@berkeley.edu', 'name': 'Jimmy Xu', 'student id': None}]
    new, updated, invalid, _ = prepare_students(exam, ['canvas id', 'email', 'name', 'student id'], rows)
    assert (len(new), len(updated), len(invalid)) == (0, 1, 0)
    assert updated[0].sid == '3031000001'


def test_row_without_canvas_id_matches_by_student_id(exam):
    new, updated, invalid = _import(exam, HEADER + 'other@berkeley.edu,Jimmy X,,3031000001\n')
    assert (len(new), len(updated), len(invalid)) == (0, 1, 0)
    assert updated[0].canvas_id == '234567'
    assert updated[0].name == 'Jimmy X'


def test_row_without_canvas_id_matches_by_email_ignoring_case(exam):
    new, updated, invalid = _import(exam, HEADER + ' JIMMY@Berkeley.edu ,Jimmy X,,\n')
    assert (len(new), len(updated), len(invalid)) == (0, 1, 0)
    assert updated[0].canvas_id == '234567'


def test_student_id_is_tried_before_email(exam):
    # the student id is Jimmy's, the email Sharon's: the student id wins
    sharon = Student.query.filter_by(exam_id=1, canvas_id='345678').one()
    _, updated, _ = _import(exam, HEADER + f'{sharon.email},Someone,,3031000001\n')
    assert updated[0].canvas_id == '234567'


def test_uid_student_id_is_kept(exam):
    new, _, invalid = _import(exam, HEADER + 'new@berkeley.edu,New Student,777777, UID:1234567 \n')
    assert not invalid
    assert new[0].sid == 'UID:1234567'
    assert Student.query.filter_by(exam_id=1, canvas_id='777777').one().sid == 'UID:1234567'


def test_row_without_canvas_id_matches_by_uid_student_id(exam):
    jimmy = Student.query.filter_by(exam_id=1, canvas_id='234567').one()
    jimmy.sid = 'UID:1234567'
    db.session.commit()
    new, updated, invalid = _import(exam, HEADER + 'other@berkeley.edu,Jimmy X,,UID:1234567\n')
    assert (len(new), len(updated), len(invalid)) == (0, 1, 0)
    assert updated[0].canvas_id == '234567'


def test_row_without_canvas_id_or_match_is_invalid(exam):
    new, updated, invalid = _import(exam, HEADER + 'nobody@berkeley.edu,Nobody,,3039999999\n')
    assert (len(new), len(updated), len(invalid)) == (0, 0, 1)


@pytest.mark.parametrize('row', [
    'jimmy@berkeley.edu,Jimmy Xu,999999,\n',  # Jimmy's email
    'someone@berkeley.edu,Jimmy Xu,999999,3031000001\n',  # Jimmy's student id
])
def test_existing_student_with_another_canvas_id_is_invalid(exam, row):
    new, updated, invalid = _import(exam, HEADER + row)
    assert (len(new), len(updated), len(invalid)) == (0, 0, 1)
    assert len(_students_named('Jimmy Xu')) == 1
    assert Student.query.filter_by(exam_id=1, canvas_id='999999').count() == 0


def test_student_listed_twice_is_created_once(exam):
    new, updated, invalid = _import(exam, HEADER + 'new@berkeley.edu,New Student,777777,3031000002\n'
                                                   'NEW@berkeley.edu,New Student,777777.0,3031000002\n')
    assert (len(new), len(updated), len(invalid)) == (1, 0, 0)
    assert len(_students_named('New Student')) == 1


CONTRADICTING_ROWS = ('email,name,canvas id,lefty\n'
                      'new@berkeley.edu,New Student,777777,false\n'
                      'new@berkeley.edu,New Student,777777,true\n')


def test_later_row_of_a_new_student_merges_into_it(exam):
    # merging (the default) adds the later row's wants to the earlier row's avoids: a contradiction,
    # so the later row is skipped and the student keeps the first row's preferences
    new, _, invalid = _import(exam, CONTRADICTING_ROWS)
    assert len(new) == 1
    assert new[0].wants == set()
    assert new[0].avoids == {'lefty'}
    assert len(invalid) == 1


def test_later_row_of_a_new_student_overwrites_it(exam):
    headers, rows = parse_csv_str(CONTRADICTING_ROWS)
    new, _, invalid, _ = prepare_students(exam, headers, rows, config=StudentImportConfig(
        updated_preference_import_strategy=UpdatedRowImportStrategy.OVERWRITE))
    assert len(new) == 1 and not invalid
    assert new[0].wants == {'lefty'}
    assert new[0].avoids == set()


def test_new_student_listed_again_without_canvas_id_is_not_duplicated(exam):
    new, updated, invalid = _import(exam, HEADER + 'new@berkeley.edu,New Student,777777,3031000002\n'
                                                   'new@berkeley.edu,New Student,,\n')
    assert (len(new), len(updated), len(invalid)) == (1, 0, 0)
    assert len(_students_named('New Student')) == 1


def test_new_student_listed_again_with_another_canvas_id_is_invalid(exam):
    new, updated, invalid = _import(exam, HEADER + 'new@berkeley.edu,New Student,777777,3031000002\n'
                                                   'new@berkeley.edu,New Student,888888,3031000002\n')
    assert (len(new), len(updated), len(invalid)) == (1, 0, 1)
    assert len(_students_named('New Student')) == 1


def test_student_listed_twice_can_still_open_the_exam(exam, login_as):
    # two students with one canvas id used to crash the exam page for that student
    db.session.delete(Student.query.filter_by(exam_id=1, canvas_id='345678').one())
    db.session.commit()
    _import(exam, HEADER + 'sharon@berkeley.edu,Sharon Lovera,345678,\n'
                           'sharon@berkeley.edu,Sharon Lovera,345678,\n')
    assert Student.query.filter_by(exam_id=1, canvas_id='345678').count() == 1

    sharon = User.query.filter_by(canvas_id='345678').one()
    response = login_as(sharon.id).get(f'{EXAM_URL}/')
    # not seated yet, which the page explains instead of crashing
    assert response.status_code == 403
    assert 'You have not been assigned a seat' in response.get_data(as_text=True)


def test_parse_csv_reads_excel_utf8_files():
    file = FileStorage(io.BytesIO('﻿Email,Name,Canvas ID\nx@berkeley.edu,X,1\n'.encode('utf-8')))
    headers, rows = parse_csv(file)
    assert headers == ['email', 'name', 'canvas id']
    assert rows == [{'email': 'x@berkeley.edu', 'name': 'X', 'canvas id': '1'}]


def test_upload_excel_utf8_csv(exam, login_as):
    client = login_as(1)
    page = client.get(f'{EXAM_URL}/students/import/').get_data(as_text=True)
    csrf_token = re.search(r'name="csrf_token" type="hidden" value="([^"]+)"', page).group(1)
    csv_bytes = ('﻿' + HEADER + 'jimmy@berkeley.edu,Jimmy Xu,234567.0,3031000001\n'
                 'new@berkeley.edu,New Student,777777,3031000002\n').encode('utf-8')
    response = client.post(f'{EXAM_URL}/students/import/', data={
        'csrf_token': csrf_token,
        'file': (io.BytesIO(csv_bytes), 'roster.csv'),
        'revalidate_existing_assignments': 'y',
        'assignment_import_strategy': 'revalidate',
        'updated_student_info_import_strategy': 'merge',
        'updated_preference_import_strategy': 'overwrite',
        'new_student_import_strategy': 'append',
        'missing_student_import_strategy': 'ignore',
    }, content_type='multipart/form-data', follow_redirects=True)
    assert 'Import done. 1 new students, 1 updated students 0 invalid students' in response.get_data(as_text=True)
    assert len(_students_named('Jimmy Xu')) == 1
    assert Student.query.filter_by(exam_id=1).count() == 4


def _problems(exam, csv_text, **config):
    headers, rows = parse_csv_str(csv_text)
    _, _, invalid, _ = prepare_students(exam, headers, rows, config=StudentImportConfig(**config))
    return [str(row) for row in invalid]


def test_invalid_rows_say_who_and_why(exam):
    assert _problems(exam, HEADER + 'new@berkeley.edu,New Student,777777,\n'
                                    'jimmy@berkeley.edu,Jimmy Xu,999999,\n'
                                    'someone@berkeley.edu,Someone,888888,3031000001\n'
                                    'nobody@berkeley.edu,Nobody,,3039999999\n'
                                    ',,,\n') == [
        'Row 3 (Jimmy Xu, jimmy@berkeley.edu, canvas id 999999): '
        'its email belongs to Jimmy Xu (canvas id 234567), who has a different canvas id',
        'Row 4 (Someone, someone@berkeley.edu, canvas id 888888, student id 3031000001): '
        'its student id belongs to Jimmy Xu (canvas id 234567), who has a different canvas id',
        'Row 5 (Nobody, nobody@berkeley.edu, student id 3039999999): '
        'no canvas id, and no student has its student id or email',
        'Row 6 (no name, email or ids): no canvas id, student id or email',
    ]


def test_invalid_row_without_name_or_email(exam):
    assert _problems(exam, HEADER + ',,777777,\nnew@berkeley.edu,,888888,\n') == [
        'Row 2 (canvas id 777777): no name or email',
        'Row 3 (new@berkeley.edu, canvas id 888888): no name',
    ]


def test_invalid_row_for_ignored_new_student(exam):
    assert _problems(exam, HEADER + 'new@berkeley.edu,New Student,777777,\n',
                     new_student_import_strategy=NewRowImportStrategy.IGNORE) == [
        'Row 2 (New Student, new@berkeley.edu, canvas id 777777): '
        'new student, and the import is set to ignore new students',
    ]


def test_invalid_row_that_wants_and_avoids_the_same(exam):
    # merging keeps Jimmy's existing wants, which the row now avoids
    jimmy = Student.query.filter_by(exam_id=1, canvas_id='234567').one()
    room = exam.rooms[0]
    jimmy.wants, jimmy.room_wants = {'lefty'}, {str(room.id)}
    db.session.commit()
    problems = _problems(exam, f'email,name,canvas id,lefty,{room_id_to_attr(room.id)}\n'
                               'jimmy@berkeley.edu,Jimmy Xu,234567,false,false\n',
                         updated_preference_import_strategy=UpdatedRowImportStrategy.MERGE)
    assert problems == [
        f'Row 2 (Jimmy Xu, jimmy@berkeley.edu, canvas id 234567): '
        f'both wants and avoids lefty, {room.name_and_start_at_time_display()}',
    ]


def test_describe_invalid_rows_escapes_and_shortens():
    rows = [InvalidRow(n, 'no email', name='<b>x</b>') for n in range(2, 14)]
    message = describe_invalid_rows(rows)
    # Markup, so a template that autoescapes leaves the already escaped rows alone
    assert isinstance(message, Markup)
    lines = message.split('\n')
    assert lines[0] == 'Skipped 12 rows:'
    assert lines[1] == '- Row 2 (&lt;b&gt;x&lt;/b&gt;): no email'
    assert len(lines) == 12  # header, 10 rows, and the rest summed up
    assert lines[-1] == '- and 2 more'
    assert describe_invalid_rows(rows[:1]).startswith('Skipped 1 row:')


def test_upload_shows_why_rows_were_skipped(exam, login_as):
    client = login_as(1)
    page = client.get(f'{EXAM_URL}/students/import/').get_data(as_text=True)
    csrf_token = re.search(r'name="csrf_token" type="hidden" value="([^"]+)"', page).group(1)
    csv_bytes = (HEADER + 'jimmy@berkeley.edu,<script>alert(1)</script>,999999,\n').encode('utf-8')
    response = client.post(f'{EXAM_URL}/students/import/', data={
        'csrf_token': csrf_token,
        'file': (io.BytesIO(csv_bytes), 'roster.csv'),
        'revalidate_existing_assignments': 'y',
        'assignment_import_strategy': 'revalidate',
        'updated_student_info_import_strategy': 'merge',
        'updated_preference_import_strategy': 'overwrite',
        'new_student_import_strategy': 'append',
        'missing_student_import_strategy': 'ignore',
    }, content_type='multipart/form-data', follow_redirects=True)
    page = response.get_data(as_text=True)
    assert 'Skipped 1 row:<br>- Row 2 (&lt;script&gt;alert(1)&lt;/script&gt;, jimmy@berkeley.edu, canvas id 999999): ' \
        'its email belongs to Jimmy Xu (canvas id 234567), who has a different canvas id' in page
    assert '<script>alert(1)</script>' not in page
