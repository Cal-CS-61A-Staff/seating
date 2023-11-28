import pytest
from unittest.mock import patch
import server.services.email.templates as templates
from server.services.email import send_email, _email_config, SMTPConfig
from server.typings.enum import EmailTemplate
from email.message import Message

TEST_FROM_EMAIL = 'sender@example.com'
TEST_TO_EMAIL = 'recipient@example.com'
TEST_SUBJECT = 'Test Subject'
TEST_BODY = 'Test Body'
TEST_BODY_HTML = '<html><body><h1>Test Body</h1></body></html>'


def _get_content(msg: Message, type='text/html'):
    """
    returns the content of the email body with the given type
    """
    if msg.is_multipart():
        for part in msg.get_payload():
            if part.get_content_type() == type:
                return part.get_payload(decode=True).decode(part.get_content_charset())
    else:
        if msg.get_content_type() == type:
            return msg.get_payload(decode=True).decode(msg.get_content_charset())
    return None


@patch('server.services.email.smtp.SMTP')
def test_send_plain_text_email(mock_smtp):
    """
    Stubs out the SMTP server and checks that plain text email is sent correctly
    """

    success = send_email(smtp=_email_config,
                         from_addr=TEST_FROM_EMAIL,
                         to_addr=TEST_TO_EMAIL,
                         subject=TEST_SUBJECT,
                         body=TEST_BODY)

    assert success[0]

    # check the use of smtp server
    mock_smtp.assert_called_with(_email_config.smtp_server, _email_config.smtp_port)
    mock_smtp.return_value.starttls.assert_called_once()
    mock_smtp.return_value.login.assert_called_once_with(_email_config.username, _email_config.password)
    mock_smtp.return_value.send_message.assert_called_once()
    mock_smtp.return_value.quit.assert_called_once()

    # check email meta
    msg = mock_smtp.return_value.send_message.call_args[0][0]
    assert msg['From'] == TEST_FROM_EMAIL
    assert msg['To'] == TEST_TO_EMAIL
    assert msg['Subject'] == TEST_SUBJECT

    # check plain text content
    assert TEST_BODY in msg.get_payload()


@patch('server.services.email.smtp.SMTP')
def test_send_html_email(mock_smtp):
    """
    Stubs out the SMTP server and checks that html email is sent correctly
    """

    success = send_email(smtp=_email_config,
                         from_addr=TEST_FROM_EMAIL,
                         to_addr=TEST_TO_EMAIL,
                         subject=TEST_SUBJECT,
                         body=TEST_BODY,
                         body_html=TEST_BODY_HTML)

    assert success[0]

    msg = mock_smtp.return_value.send_message.call_args[0][0]
    html = _get_content(msg, 'text/html')
    assert html is not None
    assert TEST_BODY_HTML in html


import threading  # noqa
from aiosmtpd.controller import Controller  # noqa
from aiosmtpd.handlers import Message as MessageHandler  # noqa
from email import message_from_string  # noqa

_fake_email_config = SMTPConfig('127.0.0.1', 1025, 'user', 'pass', use_tls=False, use_auth=False)


class CustomMessageHandler(MessageHandler):
    received_message = []

    def handle_message(self, message):
        CustomMessageHandler.received_message.append(message_from_string(message.as_string()))


@pytest.fixture()
def smtp_server():
    controller = Controller(CustomMessageHandler(),
                            hostname=_fake_email_config.smtp_server,
                            port=_fake_email_config.smtp_port)
    # has to use 127.0.0.1 instead of localhost so that the test can run on Github Actions
    # otherwise, the test does not seem to be able to find the smtp server
    thread = threading.Thread(target=controller.start)
    thread.start()

    yield controller

    CustomMessageHandler.received_message = []
    controller.stop()
    thread.join()


def test_send_plain_text_email_with_mock_smtp_server(smtp_server):
    """
    Use a local fake smtp server to test that plain text email is sent correctly
    """

    success = send_email(
        smtp=_fake_email_config,
        from_addr=TEST_FROM_EMAIL,
        to_addr=TEST_TO_EMAIL,
        subject=TEST_SUBJECT,
        body=TEST_BODY)

    assert success[0]

    msg = CustomMessageHandler.received_message[0]

    assert msg is not None
    assert msg['From'] == TEST_FROM_EMAIL
    assert msg['To'] == TEST_TO_EMAIL
    assert msg['Subject'] == TEST_SUBJECT
    assert TEST_BODY in msg.get_payload()


def test_send_html_email_with_mock_smtp_server(smtp_server):
    """
    Use a local fake smtp server to test that html email is sent correctly
    """

    success = send_email(
        smtp=_fake_email_config,
        from_addr=TEST_FROM_EMAIL,
        to_addr=TEST_TO_EMAIL,
        subject=TEST_SUBJECT,
        body=TEST_BODY,
        body_html=TEST_BODY_HTML)

    assert success[0]

    msg = CustomMessageHandler.received_message[0]

    # check html content
    html = _get_content(msg, 'text/html')
    assert html is not None
    assert TEST_BODY_HTML in html


def test_send_seating_html_email_with_mock_smtp_server(smtp_server):

    test_seating_email = \
        templates.get_email(EmailTemplate.ASSIGNMENT_INFORM_EMAIL,
                            {"EXAM": "test exam"},
                            {"NAME": "test name",
                                "COURSE": "test course",
                                "EXAM": "test exam",
                                "ROOM": "test room",
                                "SEAT": "test seat",
                                "URL": "test/url",
                                "ADDITIONAL_INFO": "test additional text",
                                "SIGNATURE": "test signature"})

    success = send_email(smtp=_fake_email_config,
                         from_addr=TEST_FROM_EMAIL,
                         to_addr=TEST_TO_EMAIL,
                         subject=test_seating_email.subject,
                         body=test_seating_email.body,
                         body_html=test_seating_email.body if test_seating_email.body_html else None)

    assert success[0]

    msg = CustomMessageHandler.received_message[0]

    assert msg['From'] == TEST_FROM_EMAIL
    assert msg['To'] == TEST_TO_EMAIL
    assert msg['Subject'] == test_seating_email.subject

    html = _get_content(msg, 'text/html')
    assert html is not None
    assert test_seating_email.body in html


def test_send_email_for_exam_with_mock_smtp_server(smtp_server):
    pass
