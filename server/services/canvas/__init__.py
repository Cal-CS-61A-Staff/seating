from flask import session, request, url_for
from canvasapi import Canvas
from canvasapi.user import User
from canvasapi.course import Course
from canvasapi.enrollment import Enrollment

from server import app
from server.models import Offering
from server.services.canvas.fake_canvas import FakeCanvas, FakeCourse, FakeUser
from server.typings.exception import Redirect


def is_mock_canvas() -> bool:
    return app.config['MOCK_CANVAS'] and \
        app.config['FLASK_ENV'].lower() != 'production'


def _get_client(key=None) -> FakeCanvas | Canvas:
    if is_mock_canvas():
        return FakeCanvas()
    if not key:
        key = session.get('access_token', None)
    if not key:
        session['after_login'] = request.url
        raise Redirect(url_for('auth.login'))
    return Canvas(app.config['CANVAS_SERVER_URL'], key)


def get_user(canvas_id, key=None) -> FakeUser | User:
    return _get_client(key).get_user(canvas_id)


def get_course(canvas_id, key=None) -> FakeCourse | Course:
    return _get_client(key).get_course(canvas_id)


def is_course_valid(c) -> bool:
    return not (not c) and \
        hasattr(c, 'id') and \
        hasattr(c, 'name') and \
        hasattr(c, 'course_code')


def get_user_courses_categorized(user: FakeUser | User) \
        -> tuple[list[FakeCourse | Course], list[FakeCourse | Course], list[FakeCourse | Course]]:
    courses_raw = user.get_courses(enrollment_status='active')
    staff_courses, student_courses, other = set(), set(), set()
    for c in courses_raw:
        if not is_course_valid(c):
            continue
        for e in c.enrollments:
            if e["type"] == 'ta' or e["type"] == 'teacher':
                staff_courses.add(c)
            elif e["type"] == 'student':
                student_courses.add(c)
            else:
                other.add(c)
    # a course should not appear in more than one category
    student_courses -= set(staff_courses)
    other = other - set(staff_courses) - set(student_courses)
    # sorted by course name
    staff_courses: list[FakeCourse | Course] = sorted(staff_courses, key=lambda c: c.name)
    student_courses: list[FakeCourse | Course] = sorted(student_courses, key=lambda c: c.name)
    other: list[FakeCourse | Course] = sorted(other, key=lambda c: c.name)
    return list(staff_courses), list(student_courses), list(other)


def api_course_to_model(course: Course | FakeCourse) -> Offering:
    return Offering(
        canvas_id=course.id,
        name=course.name,
        code=course.course_code
    )
