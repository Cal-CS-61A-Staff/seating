import copy
from flask import current_app
from smtplib import SMTP, SMTPException
from email.message import EmailMessage
from email.utils import getaddresses
from time import sleep


class SMTPConfig:
    def __init__(self, smtp_server, smtp_port, username, password, email, use_tls=True, use_auth=True):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.sender_email = email
        self.use_tls = use_tls
        self.use_auth = use_auth

    def __repr__(self) -> str:
        return (f'SMTPConfig(smtp_server={self.smtp_server}, '
                f'smtp_port={self.smtp_port}, '
                f'username={self.username}, '
                f'use_tls={self.use_tls}, '
                f'use_auth={self.use_auth})')


def construct_email(*, from_addr, to_addr, subject, body, body_html=None, bcc_addr=None, cc_addr=None,
                    reply_to=None):
    msg = EmailMessage()
    msg['From'], msg['To'], msg['Subject'] = from_addr, to_addr, subject
    if reply_to:
        msg['Reply-To'] = reply_to
    if bcc_addr:
        if isinstance(bcc_addr, str):
            bcc_addr = [address.strip() for address in bcc_addr.split(',') if address.strip()]
        msg['Bcc'] = bcc_addr
    if cc_addr:
        if isinstance(cc_addr, str):
            cc_addr = [address.strip() for address in cc_addr.split(',') if address.strip()]
        msg['Cc'] = cc_addr
    msg.set_content(body)
    if body_html:
        msg.add_alternative(body_html, subtype='html')
    return msg


def message_recipients(msg: EmailMessage) -> list[str]:
    """
    Every address `msg` goes to, from its To, Cc and Bcc headers. A header can list several
    addresses ("a@x.edu, b@x.edu"), which each have to be given to the SMTP server separately.
    """
    headers = msg.get_all('To', []) + msg.get_all('Cc', []) + msg.get_all('Bcc', [])
    return [address for _, address in getaddresses([str(header) for header in headers]) if address]


def construct_smtp_server(smtp: SMTPConfig):
    try:
        smtp_server = SMTP(smtp.smtp_server, smtp.smtp_port)
        if smtp.use_tls:
            smtp_server.starttls()
        if smtp.use_auth:
            smtp_server.login(smtp.username, smtp.password)
    except Exception as e:
        current_app.logger.error(f"Error occurred when connecting to SMTP server: {str(e)}\nConfig:\n{smtp}")
        return None
    return smtp_server


def send_email_batch(*, smtp_server: SMTP, batch=list[EmailMessage], envelope_sender_addr: str,
                     max_retries=3, retry_delay=1.0, exponential_backoff=True):
    successful_emails = []
    failed_emails = []
    for msg in batch:
        recipients = message_recipients(msg)
        # Bcc recipients get the message, but the Bcc header itself must not be sent along, or every
        # recipient could see who was BCC'd
        transmitted = copy.copy(msg)
        del transmitted['Bcc']
        for attempt in range(max_retries):
            try:
                smtp_server.sendmail(
                    from_addr=envelope_sender_addr,   # The authorized sender email
                    to_addrs=recipients,
                    msg=transmitted.as_string())
                successful_emails.append((msg, None))
                break
            except Exception as e:
                current_app.logger.error(
                    f"Error on attempt {attempt + 1} for email to {msg['To']}: {str(e)}", exc_info=True)
                if attempt < max_retries - 1:
                    cur_delay = retry_delay * (2 ** attempt) if exponential_backoff else retry_delay
                    sleep(cur_delay)
                else:
                    err_msg = f"SMTP error after {max_retries} retries for email to {msg['To']}: {str(e)}"
                    failed_emails.append((msg, err_msg))
    return successful_emails, failed_emails


def send_emails(*, smtp: SMTPConfig, messages=list[EmailMessage],
                batch_size=100, batch_delay=0.1,
                max_retries=3, retry_delay=1.0, exponential_backoff=True):
    successful_emails = []
    failed_emails = []

    smtp_server = construct_smtp_server(smtp)
    if not smtp_server:
        failed_emails = [(msg, "Error occurred when connecting to SMTP server") for msg in messages]
        return successful_emails, failed_emails

    try:
        for i in range(0, len(messages), batch_size):
            batch = messages[i:i + batch_size]
            successful_batch, failed_batch = send_email_batch(
                smtp_server=smtp_server, batch=batch,
                envelope_sender_addr=smtp.sender_email,
                max_retries=max_retries, retry_delay=retry_delay, exponential_backoff=exponential_backoff)
            successful_emails.extend(successful_batch)
            failed_emails.extend(failed_batch)
            sleep(batch_delay)
    except Exception as e:
        err_msg = f"Error occurred when sending emails: {str(e)} (Batch number: {i})\n Config: \n{smtp}"
        current_app.logger.error(err_msg)
        # everything that is not reached is considered failed
        already_categorized = set([msg for msg, _ in successful_emails + failed_emails])
        for msg in messages:
            if msg not in already_categorized:
                failed_emails.append((msg, err_msg))
    finally:
        try:
            smtp_server.quit()
        except Exception as e:
            err_msg = f"Error occurred when closing SMTP server: {str(e)}\n Config: \n{smtp}"
            current_app.logger.error(err_msg)
    return successful_emails, failed_emails


def send_single_email(*, smtp: SMTPConfig, from_addr, to_addr, subject, body,
                      body_html=None, bcc_addr=None, cc_addr=None, reply_to=None):
    msg = construct_email(from_addr=from_addr, to_addr=to_addr, subject=subject, body=body,
                          body_html=body_html, bcc_addr=bcc_addr, cc_addr=cc_addr, reply_to=reply_to)
    successful_emails, failed_emails = send_emails(smtp=smtp, messages=[msg])
    if successful_emails:
        return successful_emails[0]
    if failed_emails:
        return failed_emails[0]
