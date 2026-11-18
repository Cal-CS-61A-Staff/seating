"""
The email page (issue #140): staff write plain text, never HTML. The subject comes first, showing the
exam's name; the variables are listed at the bottom; a placeholder that is not a variable is refused
before anything is sent; and the preview shows the email a student would get, filled in by the
server. The seed exam has Jimmy Xu in seat A1; Sharon Lovera and Lavender Angela have no seat.
"""
import re

import pytest

import server.services.email as email_service
from server.models import Student
from server.services.email.templates import VARIABLES

EXAM_URL = '/offerings/1234567/exams/midterm1'
EMAIL_URL = f'{EXAM_URL}/students/email/'
PREVIEW_URL = f'{EMAIL_URL}preview/'


@pytest.fixture
def staff(seeded_db, login_as):
    return login_as(1)


@pytest.fixture
def sent(monkeypatch):
    sent_messages = []

    def fake_send_emails(*, smtp, messages):
        sent_messages.extend(messages)
        return [(message, None) for message in messages], []

    monkeypatch.setattr(email_service, 'send_emails', fake_send_emails)
    yield sent_messages


def _jimmy():
    return Student.query.filter_by(exam_id=1, canvas_id='234567').one()


def _csrf(client):
    page = client.get(EMAIL_URL).get_data(as_text=True)
    return re.search(r'name="csrf_token" type="hidden" value="([^"]+)"', page).group(1)


def test_page_starts_from_plain_text_with_the_exam_name_in_the_subject(staff):
    page = staff.get(EMAIL_URL).get_data(as_text=True)
    assert 'body_html' not in page and 'HTML Body?' not in page
    assert re.search(r'id="subject"[^>]*value="Your Exam Seating Assignment for Midterm 1"', page)
    body = re.search(r'<textarea[^>]*id="body"[^>]*>(.*?)</textarea>', page, re.S).group(1)
    assert body.lstrip().startswith('Dear {{NAME}},') and '&lt;' not in body
    # the subject comes before the message
    assert page.index('id="subject"') < page.index('id="body"')


def test_page_lists_every_variable_at_the_bottom(staff):
    page = staff.get(EMAIL_URL).get_data(as_text=True)
    listed = re.findall(r'<code>\{\{(\w+)\}\}</code>', page)
    assert listed == list(VARIABLES)
    assert page.index('id="email-variables"') > page.index('id="submit"')


def test_single_student_page_keeps_the_variables(staff):
    page = staff.get(f'{EXAM_URL}/students/{_jimmy().id}/email/').get_data(as_text=True)
    assert '{{ROOM}}' in page


@pytest.mark.parametrize('fields, error', [
    ({'body': 'Dear {{NAME}}, see {{ROOOM}}'},
     'body: {{ROOOM}} is not a variable; the variables are listed below the email.'),
    ({'body': '{{ROOOM}} {{SEATS}}'},
     'body: {{ROOOM}}, {{SEATS}} are not variables; the variables are listed below the email.'),
    ({'subject': 'Seat {{SEAT_DETAILS_LIST}}'},
     'subject: {{SEAT_DETAILS_LIST}} is not a variable; the variables are listed below the email.'),
    ({'subject': 'Seat for {{EXAM}}', 'body': 'Dear {{NAME}},\n\n{{SEAT_DETAILS_LIST}}'},
     'body: {{SEAT_DETAILS_LIST}} is not a variable; the variables are listed below the email.'),
])
def test_unknown_variable_is_refused_before_sending(staff, sent, fields, error):
    data = {'csrf_token': _csrf(staff), 'reply_to': 'staff@berkeley.edu', 'to_addr': 'jx@berkeley.edu',
            'subject': 'Seat', 'body': 'Dear {{NAME}}', 'submit': 'y', **fields}
    response = staff.post(EMAIL_URL, data=data)
    assert response.status_code == 200
    flashes = re.findall(r'<span class="alert-message">(.*?)</span>', response.get_data(as_text=True), re.S)
    assert [f.replace('&#39;', "'") for f in flashes] == [error]
    assert sent == []
    # the batch endpoint the page sends through refuses it too, before its first batch
    batch = staff.post(f'{EMAIL_URL}send/', data=data)
    assert batch.status_code == 400 and sent == []


def _preview(client, **fields):
    data = {'csrf_token': _csrf(client), 'subject': 'Seat for {{EXAM}}',
            'body': 'Dear {{NAME}}, <b>hi</b>\n\nRoom: {{ROOM}}', 'test_student': str(_jimmy().id), **fields}
    return client.post(PREVIEW_URL, data=data)


def test_preview_is_the_email_the_student_would_get(staff, sent):
    response = _preview(staff)
    assert response.status_code == 200
    preview = response.get_json()
    assert preview['subject'] == 'Seat for Midterm 1'
    name = _jimmy().first_name
    room = _jimmy().assignment.seat.room.display_name
    assert preview['text'] == f'Dear {name}, <b>hi</b>\n\nRoom: {room}'
    assert f'<p>Dear {name}, &lt;b&gt;hi&lt;/b&gt;</p>' in preview['html'] and f'<p>Room: {room}</p>' in preview['html']
    assert sent == []


def test_preview_refuses_unknown_variables_and_unseated_students(staff):
    assert _preview(staff, body='{{ROOOM}}').get_json()['errors'] == {
        'body': ['{{ROOOM}} is not a variable; the variables are listed below the email.']}
    sharon = Student.query.filter_by(exam_id=1, canvas_id='345678').one()
    response = _preview(staff, test_student=str(sharon.id))
    assert response.status_code == 400
    assert response.get_json()['errors'] == {'test_student': ['Pick a student with a seat to preview the email with.']}


def test_preview_needs_staff(seeded_db, login_as):
    # Jimmy Xu (user 2) is not staff of this course
    assert login_as(2).post(PREVIEW_URL, data={}).status_code in (302, 403, 404)
