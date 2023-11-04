
from server.typings.exception import Redirect
from server.models import SeatAssignment, Student, db, Offering, Exam
from werkzeug.routing import BaseConverter
from flask_login import current_user
from flask import abort, request, session, url_for
from flask import Blueprint

auth_module = Blueprint('auth', 'auth', url_prefix='/')
import server.controllers.auth_controllers  # noqa
health_module = Blueprint('health', 'health', url_prefix='/health')
import server.controllers.health_controllers  # noqa

GENERAL_STUDENT_HINT = "If you think this is a mistake, please contact your course staff."

ban_words = '(?!(((new)|(offerings)|(exams))\b))'
offering_regex = ban_words + r'\d+'
exam_regex = ban_words + r'\w+'


def format_exam_url(offering_canvas_id, exam_name):
    return 'offerings/{}/exams/{}'.format(offering_canvas_id, exam_name)


class ExamConverter(BaseConverter):
    regex = format_exam_url(offering_regex, exam_regex)

    def to_python(self, value):
        if not current_user.is_authenticated:
            session['after_login'] = request.url
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
            raise Redirect(url_for('student_single_seat', seat_id=exam_student_seat.seat.id))
        else:
            abort(403, "You are not authorized to view this page." + GENERAL_STUDENT_HINT)

        return exam

    def to_url(self, exam):
        return format_exam_url(exam.offering_canvas_id, exam.name)


def format_offering_url(canvas_id):
    return "offerings/{}".format(canvas_id)


class OfferingConverter(BaseConverter):
    regex = format_offering_url(offering_regex)

    def to_python(self, value):
        if not current_user.is_authenticated:
            session['after_login'] = request.url
            raise Redirect(url_for('auth.login'))
        canvas_id = value.rsplit('/', 1)[-1]

        offering = Offering.query.filter_by(
            canvas_id=canvas_id).one_or_none()
        if not offering:
            import server.services.canvas as canvas_client
            # visiting a offering route the first time as a staff member will create it in db
            if str(canvas_id) not in current_user.staff_offerings:
                abort(404,
                      "This course offering is not initialized for seating." +
                      GENERAL_STUDENT_HINT)
            course_raw = canvas_client.get_course(canvas_id)
            if not canvas_client.is_course_valid(course_raw):
                abort(404, "Offering not found from Canvas.")
            offering = canvas_client.api_course_to_model(course_raw)
            db.session.add(offering)
            db.session.commit()
        return offering

    def to_url(self, offering):
        return format_offering_url(offering.canvas_id)
