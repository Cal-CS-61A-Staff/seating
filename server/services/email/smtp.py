from smtplib import SMTP
from email.message import EmailMessage


class SMTPConfig:
    def __init__(self, smtp_server, smtp_port, username, password, use_tls=True, use_auth=True):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.use_tls = use_tls
        self.use_auth = use_auth

    def __repr__(self) -> str:
        return f'SMTPConfig(smtp_server={self.smtp_server}, smtp_port={self.smtp_port}, username={self.username}, use_tls={self.use_tls}, use_auth={self.use_auth})'  # noqa


def send_email(*, smtp: SMTPConfig, from_addr, to_addr, subject, body, body_html=None):
    msg = EmailMessage()
    msg['From'] = from_addr
    msg['To'] = to_addr
    msg['Subject'] = subject
    msg.set_content(body)

    if body_html:
        msg.add_alternative(body_html, subtype='html')

    try:
        server = SMTP(smtp.smtp_server, smtp.smtp_port)
        # if server.has_extn('STARTTLS'):
        if smtp.use_tls:
            server.starttls()
        # if server.has_extn('AUTH'):
        if smtp.use_auth:
            server.login(smtp.username, smtp.password)
        server.send_message(msg)
        server.quit()
        return (True, None)
    except Exception as e:
        return (False, f"Error sending email: {e.message}\n Config: \n{smtp}")
