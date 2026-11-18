"""
Emailing a large class (issue #86): who was emailed is saved after each batch, so a send that stops
partway keeps track of who got the email; the email page leaves out students already emailed, so it
picks up with the rest; and the page sends to the students a batch per request, through
email_students_batch, so no request runs into a server timeout.
The seed exam has Jimmy Xu seated in A1; Sharon Lovera and Lavender Angela have no seat.
"""
import re

import pytest

import server.services.email as email_service
from server.forms import EmailForm
from server.models import db, Exam, Seat, SeatAssignment, Student
from server.services.email import email_about_assignment

EXAM_URL = '/offerings/1234567/exams/midterm1'
EMAIL_URL = f'{EXAM_URL}/students/email/'
BATCH_URL = f'{EXAM_URL}/students/email/send/'


def _student(canvas_id):
    return Student.query.filter_by(exam_id=1, canvas_id=canvas_id).one()


@pytest.fixture
def seated(seeded_db):
    """Seats Sharon and Lavender too, so all three students can be emailed."""
    for canvas_id, seat_id in [('345678', 2), ('456789', 3)]:
        db.session.add(SeatAssignment(student=_student(canvas_id), seat=db.session.get(Seat, seat_id)))
        db.session.flush()
    db.session.commit()
    return [_student(canvas_id) for canvas_id in ('234567', '345678', '456789')]


@pytest.fixture
def sent(monkeypatch):
    sent_messages = []

    def fake_send_emails(*, smtp, messages):
        sent_messages.extend(messages)
        return [(message, None) for message in messages], []

    monkeypatch.setattr(email_service, 'send_emails', fake_send_emails)
    yield sent_messages


def _form():
    return EmailForm(formdata=None, data={
        'reply_to': 'staff@berkeley.edu', 'subject': 'Seat', 'body': 'Dear {{NAME}}'})


def test_emailed_is_saved_after_each_batch(app, seated, monkeypatch):
    # the second batch fails the way a killed request or a dropped SMTP connection would
    monkeypatch.setattr(email_service, 'SEND_BATCH_SIZE', 1)
    calls = []

    def send_emails(*, smtp, messages):
        calls.append(messages)
        if len(calls) == 2:
            raise TimeoutError('worker timeout')
        return [(message, None) for message in messages], []

    monkeypatch.setattr(email_service, 'send_emails', send_emails)
    exam = db.session.get(Exam, 1)
    with app.test_request_context(), pytest.raises(TimeoutError):
        email_about_assignment(exam, _form(), [student.email for student in seated])
    db.session.rollback()  # what the end of the request does with anything not committed
    db.session.expire_all()
    assert [_student(c).assignment.emailed for c in ('234567', '345678', '456789')] == [True, False, False]


def test_all_batches_are_sent(app, seated, sent, monkeypatch):
    monkeypatch.setattr(email_service, 'SEND_BATCH_SIZE', 2)
    exam = db.session.get(Exam, 1)
    with app.test_request_context():
        successful, failed = email_about_assignment(exam, _form(), [student.email for student in seated])
    assert successful == {student.email for student in seated} and not failed
    assert len(sent) == 3
    db.session.expire_all()
    assert all(_student(c).assignment.emailed for c in ('234567', '345678', '456789'))


def _to_field(page):
    return re.search(r'id="to_addr"[^>]*value="([^"]*)"', page).group(1).split(',')


def _note(page):
    match = re.search(r'<div class="delist mb-3 recipients-note">(.*?)</div>', page, re.S)
    return ' '.join(re.sub(r'<[^>]+>', '', match.group(1)).split()) if match else None


def test_email_page_leaves_out_students_without_a_seat(seeded_db, login_as):
    page = login_as(1).get(EMAIL_URL).get_data(as_text=True)
    assert _to_field(page) == [_student('234567').email]
    assert _note(page) == 'Leaving out 2 students without a seat.'


def test_email_page_leaves_out_students_already_emailed(seated, login_as):
    jimmy = _student('234567')
    jimmy.assignment.emailed = True
    db.session.commit()
    page = login_as(1).get(EMAIL_URL).get_data(as_text=True)
    assert sorted(_to_field(page)) == sorted([_student('345678').email, _student('456789').email])
    assert _note(page) == 'Leaving out 1 student already emailed. Email them again too.'
    assert f'href="{EMAIL_URL}?include_emailed=1"' in page


def test_email_page_can_include_students_already_emailed(seated, login_as):
    _student('234567').assignment.emailed = True
    db.session.commit()
    page = login_as(1).get(f'{EMAIL_URL}?include_emailed=1').get_data(as_text=True)
    assert len(_to_field(page)) == 3
    assert _note(page) == 'Including 1 student already emailed. Leave them out.'


def test_email_page_has_no_note_when_everyone_is_included(seated, login_as):
    assert _note(login_as(1).get(EMAIL_URL).get_data(as_text=True)) is None


def _csrf(client):
    page = client.get(EMAIL_URL).get_data(as_text=True)
    return re.search(r'name="csrf_token" type="hidden" value="([^"]+)"', page).group(1)


def test_batch_endpoint_emails_and_reports_who_was_emailed(seated, sent, login_as):
    client = login_as(1)
    response = client.post(BATCH_URL, data={
        'csrf_token': _csrf(client), 'reply_to': 'staff@berkeley.edu', 'subject': 'Seat', 'body': 'Dear {{NAME}}',
        'to_addr': f'{seated[0].email},{seated[1].email},nobody@berkeley.edu'})
    assert response.status_code == 200
    assert response.get_json() == {'sent': sorted([seated[0].email, seated[1].email]),
                                   'failed': ['nobody@berkeley.edu']}
    db.session.expire_all()
    assert [_student(c).assignment.emailed for c in ('234567', '345678', '456789')] == [True, True, False]


def test_batch_endpoint_rejects_an_invalid_form(seated, sent, login_as):
    client = login_as(1)
    response = client.post(BATCH_URL, data={'csrf_token': _csrf(client), 'to_addr': seated[0].email})
    assert response.status_code == 400
    assert set(response.get_json()['errors']) == {'subject', 'body'}
    assert sent == []


def test_email_page_sends_in_batches(seeded_db, login_as):
    page = login_as(1).get(EMAIL_URL).get_data(as_text=True)
    assert f'fetch("{BATCH_URL}"' in page


def test_batches_survive_a_test_send(seated, sent, login_as):
    client = login_as(1)
    response = client.post(EMAIL_URL, data={
        'csrf_token': _csrf(client), 'reply_to': 'staff@berkeley.edu', 'to_addr': seated[0].email,
        'subject': 'Seat', 'body': 'Dear {{NAME}}', 'send_test': 'y', 'test_student': str(seated[0].id),
        'test_to_addr': 'me@berkeley.edu'})
    assert f'fetch("{BATCH_URL}"' in response.get_data(as_text=True)


def test_single_student_page_sends_in_one_request(seeded_db, login_as):
    page = login_as(1).get(f'{EXAM_URL}/students/{_student("234567").id}/email/').get_data(as_text=True)
    assert BATCH_URL not in page
