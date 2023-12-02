from server import app
from server.models import db
from server.services.email.smtp import SMTPConfig, send_email
import server.services.email.templates as templates
from server.typings.enum import EmailTemplate
from flask import url_for
from urllib.parse import urljoin

_email_config = SMTPConfig(
    app.config.get('EMAIL_SERVER'),
    app.config.get('EMAIL_PORT'),
    app.config.get('EMAIL_USERNAME'),
    app.config.get('EMAIL_PASSWORD')
)


def email_about_assignment(exam, form, to_addrs):
    if isinstance(to_addrs, str):
        to_addrs = to_addrs.strip().split(',')
    if not to_addrs:
        return set(), set()
    success_addrs, failure_addrs = set(), set()
    all_students = {s.email: s for s in exam.students}
    for to_addr in to_addrs:
        student = all_students.get(to_addr, None)
        if not student or not student.assignment:
            failure_addrs.add(to_addr)
            continue
        assignment = student.assignment
        subject = templates.make_substitutions(form.subject.data, {"EXAM": exam.display_name})
        body = templates.make_substitutions(form.body.data,
                                            {"NAME": assignment.student.first_name,
                                             "COURSE": exam.offering.name,
                                             "EXAM": exam.display_name,
                                             "ROOM": assignment.seat.room.display_name,
                                             "SEAT": assignment.seat.display_name,
                                             "START_TIME": assignment.seat.room.start_at_time_display(),
                                             "DURATION": assignment.seat.room.duration_display,
                                             "URL": urljoin(
                                                 app.config.get('SERVER_BASE_URL'),
                                                 url_for('student_single_seat',
                                                         seat_id=assignment.seat.id)),
                                             })
        success, payload = send_email(
            smtp=_email_config,
            from_addr=form.from_addr.data,
            to_addr=to_addr,
            subject=subject,
            body=body,
            body_html=body if form.body_html else None,
            cc_addr=form.cc_addr.data,
            bcc_addr=form.bcc_addr.data)
        if success:
            success_addrs.add(to_addr)
            assignment.emailed = True
        else:
            failure_addrs.add(to_addr)
    db.session.commit()
    return success_addrs, failure_addrs
