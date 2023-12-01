import email
from math import e
from server import app
from server.models import Student, db, Exam, SeatAssignment, Offering
from server.services.email.smtp import SMTPConfig, send_email
import server.services.email.templates as templates
from server.typings.enum import EmailTemplate
from flask import url_for
import os

_email_config = SMTPConfig(
    app.config.get('EMAIL_SERVER'),
    app.config.get('EMAIL_PORT'),
    app.config.get('EMAIL_USERNAME'),
    app.config.get('EMAIL_PASSWORD')
)


def email_students(exam: Exam, form):
    ASSIGNMENT_PER_PAGE = 500
    page_number = 1

    email_success: set[Student] = set()
    email_failure: set[Student] = set()

    while True:
        assignments = exam.get_assignments(
            emailed=False,
            limit=ASSIGNMENT_PER_PAGE,
            offset=(page_number - 1) * ASSIGNMENT_PER_PAGE
        )
        if not assignments:
            break

        for assignment in assignments:
            result = _email_single_assignment(exam.offering, exam, assignment, form)
            if result[0]:
                email_success.add(assignment.student)
                assignment.emailed = True
            else:
                email_failure.add(assignment.student)

        db.session.commit()

    return email_success, email_failure


def email_student(exam: Exam, student_db_id: int, form):
    assignment: SeatAssignment = Student.query.get(student_db_id).assignment
    if assignment is None:
        return (False, "Student has no assignment.")
    result = _email_single_assignment(exam.offering, exam, assignment, form)
    if result[0]:
        assignment.emailed = True
        db.session.commit()
    return result


def _email_single_assignment(offering: Offering, exam: Exam, assignment: SeatAssignment, form):
    seat_path = url_for('student_single_seat', seat_id=assignment.seat.id)
    seat_absolute_path = os.path.join(app.config.get('SERVER_BASE_URL'), seat_path)

    student_email = \
        templates.get_email(EmailTemplate.ASSIGNMENT_INFORM_EMAIL,
                            {"EXAM": exam.display_name},
                            {"NAME": assignment.student.first_name,
                                "COURSE": offering.name,
                                "EXAM": exam.display_name,
                                "ROOM": assignment.seat.room.display_name,
                                "SEAT": assignment.seat.name,
                                "URL": seat_absolute_path,
                                "ADDITIONAL_INFO": form.additional_info.data,
                                "SIGNATURE": form.signature.data})

    effective_to_addr = form.override_to_addr.data or assignment.student.email
    effective_subject = form.override_subject.data or student_email.subject

    return send_email(smtp=_email_config,
                      from_addr=form.from_addr.data,
                      to_addr=effective_to_addr,
                      subject=effective_subject,
                      body=student_email.body,
                      body_html=student_email.body if student_email.body_html else None)
