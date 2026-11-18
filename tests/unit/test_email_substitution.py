"""
Staff write assignment emails as plain text with {{VARIABLE}} placeholders (issue #140), and the app
builds both parts of the email from it. The values come from imports and staff input: the HTML part
escapes them, and everything staff typed, while the plain-text part and the subject take them as they
are. Staff text is never run as a Jinja template.
"""
import re

import pytest

from server.forms import EmailForm
from server.models import db, Exam, Student
import server.services.email as email_service
from server.services.email import email_about_assignment, substitute_about_assignment
from server.services.email.templates import get_email, make_substitutions, render_html, render_text, \
    unknown_variables, VARIABLES
from server.typings.enum import EmailTemplate

NAME = 'Lovelace, Ada & <Bo>'  # first name: "Ada & <Bo>"
VALUES = {'NAME': 'Ada & <Bo>', 'COURSE': 'CS 169', 'EXAM': 'Midterm <1>', 'ROOM': 'Soda 306',
          'SEAT': 'A1', 'START_TIME': '9:00 AM', 'DURATION': '2 hours', 'URL': 'https://seating.example.edu/seats/1/'}


def _body(html):
    return re.search(r'<body>(.*)</body>', html, re.S).group(1)


def _squeeze(html):
    return re.sub(r'>\s+<', '><', ' '.join(html.split()))


@pytest.mark.parametrize('value', ['Jo\\hn', 'Ann \\1', '\\g<0>', 'C:\\new\\table'])
def test_values_with_backslashes_are_taken_literally(value):
    assert make_substitutions('Dear {{NAME}},', {'NAME': value}) == f'Dear {value},'


def test_values_are_not_filled_in_again():
    # a name that looks like a variable (or a template) is printed as it is
    assert make_substitutions('Dear {{NAME}}, {{ROOM}}', {'NAME': '{{ROOM}} {{ 7*7 }}', 'ROOM': 'Soda'}) == \
        'Dear {{ROOM}} {{ 7*7 }}, Soda'
    values = {**VALUES, 'NAME': '{{ROOM}}', 'ROOM': 'Soda'}
    assert '<p>Dear {{ROOM}}, Soda</p>' in render_html('Seat', 'Dear {{NAME}}, {{ROOM}}', values)


def test_placeholders_allow_spaces_inside_the_braces():
    assert make_substitutions('{{NAME}} / {{ NAME }}', {'NAME': 'Ada'}) == 'Ada / Ada'


def test_plain_text_part_takes_values_as_they_are():
    assert render_text('Dear {{NAME}},\n\nRoom: {{ROOM}}\nExam: {{EXAM}}', VALUES) == \
        'Dear Ada & <Bo>,\n\nRoom: Soda 306\nExam: Midterm <1>'


def test_html_part_has_paragraphs_and_line_breaks():
    html = _squeeze(_body(render_html('Seat', 'Dear {{NAME}},\n\nRoom: {{ROOM}}\nSeat: {{SEAT}}\n\n\n\nBye', VALUES)))
    assert html == '<p>Dear Ada &amp; &lt;Bo&gt;,</p><p>Room: Soda 306<br>Seat: A1</p><p>Bye</p>'


def test_html_typed_by_staff_is_shown_as_text():
    html = _body(render_html('Seat', '<b>Hi</b> <script>alert(1)</script> {{ "x" * 3 }}', VALUES))
    assert '&lt;b&gt;Hi&lt;/b&gt; &lt;script&gt;alert(1)&lt;/script&gt;' in html
    assert '<b>' not in html and '<script>' not in html


@pytest.mark.parametrize('text', ['{{ 7 * 7 }}', '{% if true %}yes{% endif %}', '{{ config }}'])
def test_staff_text_is_not_run_as_a_template(text):
    assert '49' not in render_html('Seat', text, VALUES)
    assert 'yes</p>' not in render_html('Seat', text, VALUES)
    assert 'SECRET_KEY' not in render_html('Seat', text, VALUES)


@pytest.mark.parametrize('text, links', [
    ('See https://example.edu/a?b=1&c=2 now', ['https://example.edu/a?b=1&amp;c=2']),
    ('Ends a sentence: https://example.edu/a.', ['https://example.edu/a']),
    ('(see https://example.edu/a)', ['https://example.edu/a']),
    ('https://en.wikipedia.org/wiki/Seat_(furniture)', ['https://en.wikipedia.org/wiki/Seat_(furniture)']),
    ('Your seat: {{URL}}', ['https://seating.example.edu/seats/1/']),
    ('javascript:alert(1) and www.example.edu', []),
])
def test_links_are_clickable(text, links):
    html = render_html('Seat', text, VALUES)
    assert re.findall(r'<a href="([^"]*)">', html) == links


def test_quotes_in_a_link_do_not_leave_the_attribute():
    html = render_html('Seat', "https://example.edu/a'onmouseover='x", VALUES)
    assert re.findall(r'<a href="([^"]*)">', html) == ['https://example.edu/a&#39;onmouseover=&#39;x']


def test_subject_is_the_html_title():
    assert '<title>Seat for Midterm &lt;1&gt;</title>' in render_html('Seat for Midterm <1>', 'Hi', VALUES)


def test_unknown_variables():
    assert unknown_variables('{{NAME}} {{ROOOM}} {{ ROOOM }} {{SEATS}}') == ['ROOOM', 'SEATS']
    assert unknown_variables('{{SEAT_DETAILS_LIST}}') == ['SEAT_DETAILS_LIST']


def test_default_email_uses_only_known_variables_and_no_html():
    email = get_email(EmailTemplate.ASSIGNMENT_INFORM_EMAIL)
    assert email.subject == 'Your Exam Seating Assignment for {{EXAM}}'
    assert not unknown_variables(email.subject + email.body)
    assert '{{ROOM}}' in email.body and '{{SEAT}}' in email.body and '{{URL}}' in email.body
    assert '<' not in email.body


def test_every_variable_has_a_value(app, seeded_db):
    jimmy = Student.query.filter_by(exam_id=1, canvas_id='234567').one()
    with app.test_request_context():
        values = email_service.assignment_values(jimmy.exam, jimmy)
    assert set(values) == set(VARIABLES)


@pytest.fixture
def jimmy(seeded_db):
    exam = db.session.get(Exam, 1)
    exam.display_name = 'Midterm <1> & 2'
    jimmy = Student.query.filter_by(exam_id=exam.id, canvas_id='234567').one()
    jimmy.name = NAME
    db.session.commit()
    assert jimmy.assignment is not None
    yield jimmy


def _form(body='Dear {{NAME}}, {{EXAM}}'):
    return EmailForm(formdata=None, data={
        'reply_to': 'staff@berkeley.edu', 'to_addr': 'x@berkeley.edu', 'subject': 'Seat for {{EXAM}}', 'body': body})


def test_substitution_fills_in_all_three(app, jimmy):
    with app.test_request_context():
        subject, text, html = substitute_about_assignment(jimmy.exam, _form(), jimmy)
    assert subject == 'Seat for Midterm <1> & 2'
    assert text == 'Dear Ada & <Bo>, Midterm <1> & 2'
    assert '<p>Dear Ada &amp; &lt;Bo&gt;, Midterm &lt;1&gt; &amp; 2</p>' in html


@pytest.fixture
def sent(monkeypatch):
    """Captures the messages email_about_assignment would send."""
    sent_messages = []

    def fake_send_emails(*, smtp, messages):
        sent_messages.extend(messages)
        return [(message, None) for message in messages], []

    monkeypatch.setattr(email_service, 'send_emails', fake_send_emails)
    yield sent_messages


def test_every_email_has_a_text_and_an_html_part(app, jimmy, sent):
    with app.test_request_context():
        successful, failed = email_about_assignment(jimmy.exam, _form('Dear {{NAME}}\n\nRoom: {{ROOM}}'),
                                                    [jimmy.email])
    assert successful == {jimmy.email} and not failed
    (message,) = sent
    assert [part.get_content_type() for part in message.iter_parts()] == ['text/plain', 'text/html']
    text = message.get_body(('plain',)).get_content()
    assert text.rstrip() == f'Dear Ada & <Bo>\n\nRoom: {jimmy.assignment.seat.room.display_name}'
    assert 'Dear Ada &amp; &lt;Bo&gt;' in message.get_body(('html',)).get_content()
    assert message['Subject'] == 'Seat for Midterm <1> & 2'


def test_backslash_in_a_name_does_not_stop_the_emails(app, jimmy, sent):
    jimmy.name = 'Xu, Jo\\hn'
    db.session.commit()
    with app.test_request_context():
        successful, _ = email_about_assignment(jimmy.exam, _form(), [jimmy.email])
    assert successful == {jimmy.email}
    assert 'Dear Jo\\Hn' in sent[0].get_body(('html',)).get_content()
