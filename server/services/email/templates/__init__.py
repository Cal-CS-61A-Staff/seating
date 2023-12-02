from server.typings.enum import EmailTemplate
import os
import json
import re


class EmailContent:
    def __init__(self, subject: str, body: str, body_html: bool):
        self.subject = subject
        self.body = body
        self.body_html = body_html

    def apply_substitutions(self, subject_substitutions: dict[str, str], body_substitutions: dict[str, str]):
        if subject_substitutions:
            self.subject = make_substitutions(self.subject, subject_substitutions)
        if body_substitutions:
            self.body = make_substitutions(self.body, body_substitutions)

    def __repr__(self) -> str:
        return f'EmailContent(subject={self.subject}, body={self.body}, body_type={self.body_html})'


def get_email(
        template: EmailTemplate,
        subject_substitutions: dict[str, str] = None,
        body_substitutions: dict[str, str] = None
) -> EmailContent:
    # template.value is the file name for email metadata (json)
    # let us read it that first. The file sits in the same path as this file.
    email_metadata = None
    with open(os.path.join(os.path.dirname(__file__), template.value + ".json")) as f:
        email_metadata = json.load(f)
    subject = email_metadata['subject']
    body_html = email_metadata['body_html']
    body_path = os.path.join(os.path.dirname(__file__), email_metadata['body_path'])
    body = None
    with open(body_path) as f:
        body = f.read()
    content = EmailContent(subject, body, re.match('[Tt]rue', body_html) is not None)
    content.apply_substitutions(subject_substitutions, body_substitutions)
    return content


def make_substitutions(text: str, substitutions: dict[str, str]) -> str:
    for key, value in substitutions.items():
        text = re.sub(r'\{\{\s*' + key + r'\s*\}\}', value, text)
    return text
