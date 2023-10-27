from flask import session, request, url_for
from canvasapi import Canvas

from server import app
from server.models import Offering
from server.utils.stub import get_dev_user, get_dev_course, get_dev_user_courses
from server.utils.url import Redirect


def _get_client(key=None):
    if not key:
        key = session.get('access_token', None)
    if not key:
        session['after_login'] = request.url
        raise Redirect(url_for('login'))
    return Canvas(app.config['CANVAS_SERVER_URL'], key)


def is_mock_canvas():
    return app.config['MOCK_CANVAS'] and \
        app.config['FLASK_ENV'].lower() != 'production'


def get_user(canvas_id, key=None):
    if is_mock_canvas():
        return get_dev_user(canvas_id)
    return _get_client(key).get_user(canvas_id)


def get_course(canvas_id, key=None):
    if is_mock_canvas():
        return get_dev_course(canvas_id)
    return _get_client(key).get_course(canvas_id)


def get_user_courses(user):
    if is_mock_canvas():
        return get_dev_user_courses(user.id)
    return user.get_courses(enrollment_status='active')


def is_course_valid(c):
    return not (not c) and \
        hasattr(c, 'id') and \
        hasattr(c, 'name') and \
        hasattr(c, 'course_code')


def get_user_courses_categorized(user):
    courses_raw = get_user_courses(user)
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
    staff_courses = sorted(staff_courses, key=lambda c: c.name)
    student_courses = sorted(student_courses, key=lambda c: c.name)
    other = sorted(other, key=lambda c: c.name)
    return list(staff_courses), list(student_courses), list(other)


def api_course_to_model(course):
    return Offering(
        canvas_id=course.id,
        name=course.name,
        code=course.course_code
    )


def get_students(course_canvas_id, key=None):
    # if is_mock_canvas():
    #     return []
    return get_course(course_canvas_id, key).get_users(enrollment_type='student')
