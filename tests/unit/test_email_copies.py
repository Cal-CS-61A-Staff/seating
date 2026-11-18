"""
CC and BCC on assignment emails: every student's email is CC'd and BCC'd (CC is how course staff see
a student's reply-all), BCC'd addresses get the email without anyone seeing them, and a field can
list several addresses. The SMTP checks go through a real (local) SMTP server, to see what is sent.
"""
import pytest

import server.services.email as email_service
from server.forms import EmailForm
from server.models import db, Exam, Seat, SeatAssignment, Student
from server.services.email import email_about_assignment
from server.services.email.smtp import construct_email, message_recipients, send_emails
from tests.unit.test_email import CustomMessageHandler, _fake_email_config, smtp_server  # noqa: F401


def _message(cc=None, bcc=None):
    return construct_email(from_addr='staff@berkeley.edu', to_addr='student@berkeley.edu', subject='Seat',
                           body='Your seat', cc_addr=cc, bcc_addr=bcc)


@pytest.mark.parametrize('cc, bcc, expected', [
    (None, None, ['student@berkeley.edu']),
    ('ta@berkeley.edu', 'hidden@berkeley.edu', ['student@berkeley.edu', 'ta@berkeley.edu', 'hidden@berkeley.edu']),
    ('ta1@berkeley.edu,ta2@berkeley.edu', 'h1@berkeley.edu, h2@berkeley.edu',
     ['student@berkeley.edu', 'ta1@berkeley.edu', 'ta2@berkeley.edu', 'h1@berkeley.edu', 'h2@berkeley.edu']),
])
def test_message_recipients_lists_each_address(cc, bcc, expected):
    assert message_recipients(_message(cc, bcc)) == expected


def test_bcc_is_delivered_but_not_shown(smtp_server):  # noqa: F811
    successful, failed = send_emails(smtp=_fake_email_config, messages=[
        _message(cc='ta1@berkeley.edu, ta2@berkeley.edu', bcc='h1@berkeley.edu,h2@berkeley.edu')])
    assert len(successful) == 1 and not failed
    (received,) = CustomMessageHandler.received_message
    # no header shows the BCC'd addresses (X-RcptTo is added by the test SMTP server)
    assert received['Bcc'] is None
    assert [name for name, value in received.items() if name != 'X-RcptTo' and 'h1@' in value] == []
    assert received['Cc'] == 'ta1@berkeley.edu, ta2@berkeley.edu'
    # every address got the message, each as its own recipient
    assert received['X-RcptTo'].split(', ') == [
        'student@berkeley.edu', 'ta1@berkeley.edu', 'ta2@berkeley.edu', 'h1@berkeley.edu', 'h2@berkeley.edu']


def test_sending_leaves_the_message_unchanged(smtp_server):  # noqa: F811
    message = _message(bcc='hidden@berkeley.edu')
    send_emails(smtp=_fake_email_config, messages=[message])
    assert message['Bcc'] == 'hidden@berkeley.edu'


@pytest.fixture
def seated(seeded_db):
    """All three seed students seated (only Jimmy Xu is, in the seed)."""
    for canvas_id, seat_id in [('345678', 2), ('456789', 3)]:
        student = Student.query.filter_by(exam_id=1, canvas_id=canvas_id).one()
        db.session.add(SeatAssignment(student=student, seat=db.session.get(Seat, seat_id)))
        db.session.flush()
    db.session.commit()
    return Student.query.filter_by(exam_id=1).order_by(Student.id).all()


@pytest.fixture
def sent(monkeypatch):
    """The messages email_about_assignment sends, captured instead of going to an SMTP server."""
    sent_messages = []

    def fake_send_emails(*, smtp, messages):
        sent_messages.extend(messages)
        return [(message, None) for message in messages], []

    monkeypatch.setattr(email_service, 'send_emails', fake_send_emails)
    yield sent_messages


def test_every_student_email_is_copied(app, seated, sent):
    with app.test_request_context():
        form = EmailForm(formdata=None, data={
            'reply_to': 'staff@berkeley.edu', 'subject': 'Seat', 'body': 'Dear {{NAME}}',
            'cc_addr': 'ta1@berkeley.edu, ta2@berkeley.edu', 'bcc_addr': 'hidden@berkeley.edu'})
        email_about_assignment(db.session.get(Exam, 1), form, [student.email for student in seated])
    assert [message['To'] for message in sent] == [student.email for student in seated]
    assert {(message['Cc'], message['Bcc']) for message in sent} == {
        ('ta1@berkeley.edu, ta2@berkeley.edu', 'hidden@berkeley.edu')}
