import requests
from flask import current_app, url_for
from canvasapi import Canvas
from canvasapi.user import User
from canvasapi.course import Course

from server.models import Offering
from server.services.canvas.fake_canvas import FakeCanvas, FakeCourse, FakeUser
from server.typings.exception import Redirect


def is_mock_canvas(config=None) -> bool:
    """Whether to use the fake Canvas: only when asked for, and never in production."""
    config = current_app.config if config is None else config
    return config['MOCK_CANVAS'] and config['FLASK_ENV'].lower() != 'production'


def _get_client(key=None) -> FakeCanvas | Canvas:
    if is_mock_canvas():
        return FakeCanvas()
    if not key:
        # imported here because canvas_tokens imports this module
        from server.services.auth.canvas_tokens import current_token
        key = current_token()
    if not key:
        # imported here because the auth package imports this module
        from server.services.auth.after_login import remember_page_for_after_login
        remember_page_for_after_login()
        raise Redirect(url_for('auth.login'))
    return Canvas(current_app.config['CANVAS_SERVER_URL'], key)


def revoke_token(access_token: str):
    """
    Asks Canvas to revoke an access token, so it stops working before it expires. Best effort: signing
    out mustn't fail because Canvas is down, and the token expires within an hour regardless.
    """
    if is_mock_canvas():
        return
    try:
        response = requests.delete(current_app.config['CANVAS_SERVER_URL'] + 'login/oauth2/token',
                                   headers={'Authorization': f'Bearer {access_token}'}, timeout=5)
        response.raise_for_status()
    except requests.RequestException as error:
        current_app.logger.warning("Couldn't revoke a Canvas access token: %s", error)


def get_user(canvas_id, key=None) -> FakeUser | User:
    return _get_client(key).get_user(canvas_id)


def get_course(canvas_id, key=None) -> FakeCourse | Course:
    return _get_client(key).get_course(canvas_id)


def is_staff_enrollment(enrollment_type: str):
    return enrollment_type.lower() in ('ta', 'teacher')


def is_course_valid(c) -> bool:
    # A valid course has a name, id and course code
    # TODO: TBD if we should filter on published
    return not (not c) and \
        hasattr(c, 'id') and \
        hasattr(c, 'name') and \
        hasattr(c, 'course_code')


def normalize_course_start_date(course: FakeCourse | Course) -> None:
    # Ensure a valid start_at date for a course.
    # return the term start_at_date if present
    # created_at is assumed to be at least always present
    # TODO: does Course ever has `term` attribute? (This is added by Michael's PR)
    # I know there is a `enrollment_term_id` attribute
    if hasattr(course, 'term') and course.term and course.term['start_at']:
        start_at = course.term['start_at']
        start_at_date = course.term['start_at_date']
    else:
        start_at = course.start_at if (hasattr(course, 'start_at') and course.start_at) else course.created_at
        start_at_date = course.start_at_date if (hasattr(course, 'start_at_date')
                                                 and course.start_at_date) else course.created_at_date
    course.start_at = start_at
    course.start_at_date = start_at_date
    return course.start_at is not None


def get_user_courses_categorized(user: FakeUser | User) \
        -> tuple[list[FakeCourse | Course], list[FakeCourse | Course], list[FakeCourse | Course]]:
    courses_raw = user.get_courses(enrollment_status='active', include=['term'], per_page=100)
    # TODO: Refactor to a dict { staff:, student:, other: }
    staff_courses, student_courses, other, skipped = set(), set(), set(), set()
    for c in courses_raw:
        if not is_course_valid(c) or not normalize_course_start_date(c):
            skipped.add(c)
            continue
        # TODO: refactor to function `find_course_enrollment_type`
        for e in c.enrollments:
            if is_staff_enrollment(e["type"]):
                staff_courses.add(c)
            elif e["type"] == 'student':
                student_courses.add(c)
            else:
                other.add(c)

    # a course should not appear in more than one category
    student_courses -= set(staff_courses)
    other = other - set(staff_courses) - set(student_courses)

    # convert to list because order matters
    staff_courses: list[FakeCourse | Course] = list(staff_courses)
    student_courses: list[FakeCourse | Course] = list(student_courses)
    other: list[FakeCourse | Course] = list(other)

    # sorted by start_at_date DESC and then by name ASC
    def _sort_courses(courses: list[FakeCourse | Course]):
        # Cannot do courses.sort(key=lambda c: (c.start_at_date, c.name))
        # String or Datetime object cannot be negated to reverse the order
        courses.sort(key=lambda c: c.name)
        courses.sort(key=lambda c: c.start_at_date, reverse=True)

    _sort_courses(staff_courses)
    _sort_courses(student_courses)
    _sort_courses(other)

    return list(staff_courses), list(student_courses), list(other), list(skipped)


def get_student_roster_for_offering(offering_canvas_id, key=None):
    course = _get_client(key).get_course(offering_canvas_id)
    students = course.get_users(enrollment_type='student')
    headers = ['canvas id', 'email', 'name', 'student id']
    rows = []
    for student in students:
        stu_dict = {}
        if hasattr(student, 'id'):
            stu_dict['canvas id'] = student.id
        if hasattr(student, 'email'):
            stu_dict['email'] = student.email
        if hasattr(student, 'short_name'):
            stu_dict['name'] = student.short_name
        if hasattr(student, 'sis_user_id'):
            stu_dict['student id'] = student.sis_user_id
        rows.append(stu_dict)
    return headers, rows


def api_course_to_model(course: Course | FakeCourse) -> Offering:
    return Offering(
        canvas_id=str(course.id),
        name=course.name,
        code=course.course_code,
        start_at=course.start_at,
    )
