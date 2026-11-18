
from server.typings.exception import Redirect
from server.models import SeatAssignment, Student, db, Offering, Exam
from werkzeug.routing import BaseConverter
from flask_login import current_user
from server.services.auth.after_login import remember_page_for_after_login
from flask import abort, url_for
from flask import Blueprint


GENERAL_STUDENT_HINT = "If you think this is a mistake, please contact your course staff."

ban_words = r'(?!((new)|(offerings)|(exams)|(student)))'
offering_regex = ban_words + r'\d+'
exam_regex = ban_words + r'\w+'
student_regex = r'\d+'


def format_student_url(offering_canvas_id, exam_name, student_id):
    return 'offerings/{}/exams/{}/students/{}'.format(offering_canvas_id, exam_name, student_id)


class StudentConverter(BaseConverter):
    regex = format_student_url(offering_regex, exam_regex, student_regex)

    def to_python(self, value):
        if not current_user.is_authenticated:
            remember_page_for_after_login()
            raise Redirect(url_for('auth.login'))
        # students are identified by their database id, not their Canvas id or student id
        _, offering_canvas_id, _, exam_name, _, student_id = value.split('/', 5)
        exam = Exam.query.filter_by(
            offering_canvas_id=offering_canvas_id, name=exam_name
        ).one_or_none()

        if str(offering_canvas_id) in current_user.staff_offerings:
            pass
        elif str(offering_canvas_id) in current_user.student_offerings:
            abort(403, "You are not authorized to view this page. " + GENERAL_STUDENT_HINT)
        else:
            abort(403, "You are not authorized to view this page. " + GENERAL_STUDENT_HINT)
        if not exam:
            abort(404, "This exam does not exist. ")
        # only a student of the exam in the url: staff were checked against that exam's course
        exam_student = Student.query.filter_by(id=int(student_id), exam_id=exam.id).one_or_none()
        if not exam_student:
            abort(404, "This student is not in this exam. ")
        return exam, exam_student

    def to_url(self, value):
        exam, exam_student = value
        return format_student_url(exam.offering_canvas_id, exam.name, exam_student.id)


def format_exam_url(offering_canvas_id, exam_name):
    return 'offerings/{}/exams/{}'.format(offering_canvas_id, exam_name)


class ExamConverter(BaseConverter):
    regex = format_exam_url(offering_regex, exam_regex + r'(?!/students/\d+)')

    def to_python(self, value):
        if not current_user.is_authenticated:
            remember_page_for_after_login()
            raise Redirect(url_for('auth.login'))
        _, canvas_id, _, exam_name = value.split('/', 3)
        exam = Exam.query.filter_by(
            offering_canvas_id=canvas_id, name=exam_name
        ).one_or_none()

        if str(canvas_id) in current_user.staff_offerings:
            pass
        elif str(canvas_id) in current_user.student_offerings:
            if not exam:
                abort(404, "This exam is not initialized for seating. " + GENERAL_STUDENT_HINT)
            exam_student = Student.query.filter_by(
                canvas_id=str(current_user.canvas_id), exam_id=exam.id).one_or_none()
            if not exam_student:
                abort(
                    403, "You are not added as a student in this exam. " + GENERAL_STUDENT_HINT)
            exam_student_seat = SeatAssignment.query.filter_by(
                student_id=exam_student.id).one_or_none()
            if not exam_student_seat:
                abort(403,
                      "You have not been assigned a seat for this exam. " + GENERAL_STUDENT_HINT)
            raise Redirect(url_for('views.student_single_seat', seat_id=exam_student_seat.seat.id))
        else:
            abort(403, "You are not authorized to view this page. " + GENERAL_STUDENT_HINT)

        return exam

    def to_url(self, exam):
        return format_exam_url(exam.offering_canvas_id, exam.name)


def format_offering_url(canvas_id):
    return "offerings/{}".format(canvas_id)


class OfferingConverter(BaseConverter):
    regex = format_offering_url(offering_regex)

    def to_python(self, value):
        if not current_user.is_authenticated:
            remember_page_for_after_login()
            raise Redirect(url_for('auth.login'))
        canvas_id = value.rsplit('/', 1)[-1]
        # check membership first, so non-members cannot tell which courses use seating
        if str(canvas_id) not in current_user.staff_offerings | current_user.student_offerings:
            abort(403, "You are not authorized to view this page. " + GENERAL_STUDENT_HINT)

        offering = Offering.query.filter_by(
            canvas_id=canvas_id).one_or_none()
        if not offering:
            abort(404, "This course offering is not initialized for seating. " + GENERAL_STUDENT_HINT)
        return offering

    def to_url(self, offering):
        return format_offering_url(offering.canvas_id)


auth_module = Blueprint('auth', 'auth', url_prefix='/')
dev_login_module = Blueprint('dev_login', 'dev_login', url_prefix='/dev_login')
health_module = Blueprint('health', 'health', url_prefix='/health')
c1c_module = Blueprint('c1c', 'c1c', url_prefix='/c1c')

import server.controllers.auth_controllers  # noqa
import server.controllers.dev_login_controllers  # noqa
import server.controllers.health_controllers  # noqa
