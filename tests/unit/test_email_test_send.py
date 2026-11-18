"""
Staff can send themselves a test of the assignment email (issue #77): it is filled in with one seated
student's data but sent to the staff member, with "[TEST]" before the subject. The seed exam has
Jimmy Xu in seat A1; Sharon Lovera and Lavender Angela have no seat.
"""
import html
import re

import pytest

import server.services.email as email_service
from server.models import db, Student

EXAM_URL = '/offerings/1234567/exams/midterm1'
EMAIL_URL = f'{EXAM_URL}/students/email/'
BODY = 'Dear {{NAME}}, you sit in {{ROOM}} seat {{SEAT}}.'


@pytest.fixture
def sent(monkeypatch):
    """The messages the app sends, captured instead of going to an SMTP server."""
    sent_messages = []

    def fake_send_emails(*, smtp, messages):
        sent_messages.extend(messages)
        return [(message, None) for message in messages], []

    monkeypatch.setattr(email_service, 'send_emails', fake_send_emails)
    yield sent_messages


@pytest.fixture
def staff(seeded_db, login_as):
    return login_as(1)


def _student(canvas_id):
    return Student.query.filter_by(exam_id=1, canvas_id=canvas_id).one()


def _post(client, url, page_url=None, **fields):
    page = client.get(page_url or url).get_data(as_text=True)
    data = {
        'csrf_token': re.search(r'name="csrf_token" type="hidden" value="([^"]+)"', page).group(1),
        'reply_to': 'staff@berkeley.edu', 'to_addr': 'jx@berkeley.edu',
        'cc_addr': 'cc@berkeley.edu', 'bcc_addr': 'bcc@berkeley.edu',
        'subject': 'Seat for {{EXAM}}', 'body': BODY,
    }
    data.update({key: value for key, value in fields.items() if value is not None})
    for key in [key for key, value in fields.items() if value is None]:
        data.pop(key, None)
    return client.post(url, data=data)


def _flashes(response):
    return [html.unescape(message) for message in
            re.findall(r'<span class="alert-message">(.*?)</span>', response.get_data(as_text=True), re.S)]


def test_only_seated_students_are_offered(staff):
    page = staff.get(EMAIL_URL).get_data(as_text=True)
    options = re.findall(r'<option[^>]*>([^<]*)</option>', page)
    jimmy = _student('234567')
    seat = jimmy.assignment.seat
    assert options == [f'Jimmy Xu ({seat.room.display_name} {seat.display_name})']


def test_send_test_goes_to_staff_filled_in_with_the_student(staff, sent):
    jimmy = _student('234567')
    response = _post(staff, EMAIL_URL, send_test='y', test_student=str(jimmy.id), test_to_addr='me@berkeley.edu')
    assert response.status_code == 200
    (message,) = sent
    assert message['To'] == 'me@berkeley.edu'
    assert message['Cc'] is None and message['Bcc'] is None
    assert message['Subject'] == f'[TEST] Seat for {jimmy.exam.display_name}'
    html = message.get_body(('html',)).get_content()
    assert f'Dear {jimmy.first_name}, you sit in {jimmy.assignment.seat.room.display_name} seat ' \
        f'{jimmy.assignment.seat.display_name}.' in html
    assert _flashes(response) == [
        "Sent a test email to me@berkeley.edu, filled in with Jimmy Xu's seat."]
    # the student was not emailed, and the page still has the template to keep editing
    db.session.expire_all()
    assert _student('234567').assignment.emailed is False
    assert '{{NAME}}' in response.get_data(as_text=True)


def test_send_test_works_when_every_student_was_already_emailed(staff, sent):
    jimmy = _student('234567')
    jimmy.assignment.emailed = True
    db.session.commit()

    response = _post(staff, EMAIL_URL, to_addr=None, send_test='y', test_student=str(jimmy.id),
                     test_to_addr='me@berkeley.edu')

    assert response.status_code == 200
    (message,) = sent
    assert message['To'] == 'me@berkeley.edu'
    assert _flashes(response) == [
        "Sent a test email to me@berkeley.edu, filled in with Jimmy Xu's seat."]


def test_send_test_has_a_text_and_an_html_part(staff, sent):
    jimmy = _student('234567')
    _post(staff, EMAIL_URL, send_test='y', test_student=str(jimmy.id), test_to_addr='me@berkeley.edu')
    (message,) = sent
    assert [part.get_content_type() for part in message.iter_parts()] == ['text/plain', 'text/html']
    assert message.get_body(('plain',)).get_content().startswith(f'Dear {jimmy.first_name}, you sit in ')


def test_send_test_needs_an_address(staff, sent):
    jimmy = _student('234567')
    response = _post(staff, EMAIL_URL, send_test='y', test_student=str(jimmy.id), test_to_addr='')
    assert _flashes(response) == ['Enter the address to send the test email to.']
    assert sent == []


def test_send_test_rejects_a_bad_address(staff, sent):
    jimmy = _student('234567')
    response = _post(staff, EMAIL_URL, send_test='y', test_student=str(jimmy.id), test_to_addr='not an email')
    assert _flashes(response) == ['test_to_addr: Invalid email address.']
    assert sent == []
    # what was typed is kept
    assert 'value="not an email"' in response.get_data(as_text=True)


def test_send_test_rejects_a_student_without_a_seat(staff, sent):
    sharon = _student('345678')
    response = _post(staff, EMAIL_URL, send_test='y', test_student=str(sharon.id), test_to_addr='me@berkeley.edu')
    assert _flashes(response) == ['Pick a student with a seat to fill in the test email.']
    assert sent == []


def test_send_test_rejects_an_unknown_student(staff, sent):
    response = _post(staff, EMAIL_URL, send_test='y', test_student='999999', test_to_addr='me@berkeley.edu')
    assert _flashes(response) == ['Pick a student with a seat to fill in the test email.']
    assert sent == []


def test_send_still_emails_the_students(staff, sent):
    response = _post(staff, EMAIL_URL, submit='y', test_student=str(_student('234567').id))
    assert response.status_code == 302
    (message,) = sent
    assert message['To'] == 'jx@berkeley.edu'
    assert not message['Subject'].startswith('[TEST]')
    db.session.expire_all()
    assert _student('234567').assignment.emailed is True


def test_send_works_without_any_seated_student(staff, sent):
    # with nobody seated the student list is empty, so the browser posts no test student
    db.session.delete(_student('234567').assignment)
    db.session.commit()
    response = _post(staff, EMAIL_URL, submit='y')
    assert response.status_code == 302
    assert _flashes(staff.get(f'{EXAM_URL}/students/')) == ['Failed to email students: jx@berkeley.edu']


def test_real_send_requires_a_recipient(staff, sent):
    response = _post(staff, EMAIL_URL, submit='y', to_addr=None)

    assert response.status_code == 200
    assert _flashes(response) == ['to_addr: This field is required.']
    assert sent == []


def test_single_student_send_requires_a_recipient(staff, sent):
    jimmy = _student('234567')
    response = _post(staff, f'{EXAM_URL}/students/{jimmy.id}/email/', submit='y', to_addr=None)

    assert response.status_code == 200
    assert _flashes(response) == ['to_addr: This field is required.']
    assert sent == []


def test_batch_send_requires_a_recipient(staff, sent):
    response = _post(staff, f'{EMAIL_URL}send/', page_url=EMAIL_URL, to_addr=None)

    assert response.status_code == 400
    assert response.json == {'errors': {'to_addr': ['This field is required.']}}
    assert sent == []


def test_invalid_send_keeps_the_typed_email(staff, sent):
    response = _post(staff, EMAIL_URL, submit='y', subject='')
    assert response.status_code == 200
    assert 'subject: This field is required.' in _flashes(response)
    assert sent == []
    assert 'you sit in {{ROOM}}' in response.get_data(as_text=True)


def test_single_student_page_preselects_that_student(staff):
    jimmy = _student('234567')
    page = staff.get(f'{EXAM_URL}/students/{jimmy.id}/email/').get_data(as_text=True)
    assert re.search(rf'<option selected value="{jimmy.id}">', page)


def test_no_seated_students_means_no_test(staff):
    db.session.delete(_student('234567').assignment)
    db.session.commit()
    page = staff.get(EMAIL_URL).get_data(as_text=True)
    assert 'No student has a seat yet' in page
    assert 'name="send_test"' not in page
