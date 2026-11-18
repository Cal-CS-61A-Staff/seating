import time

import requests
from requests.adapters import HTTPAdapter
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


# seconds to wait for each Canvas request for a roster's student ids, so a slow Canvas can't hold a
# request thread; and for all of them, for a photo, which can't wait on a roster of many pages
ROSTER_TIMEOUT = 10
PHOTO_ROSTER_DEADLINE = 20
# after Canvas fails to give a roster for a photo, seconds before photos ask again: not on every hover
ROSTER_FAILURE_CACHE_LIFE = 60


class _TimeoutAdapter(HTTPAdapter):
    """Gives each request a timeout: canvasapi sets none and has no setting for one."""

    def __init__(self, timeout):
        super().__init__()
        self.timeout = timeout

    def send(self, request, **kwargs):
        kwargs['timeout'] = kwargs.get('timeout') or self.timeout
        return super().send(request, **kwargs)


def _current_token():
    # imported here because canvas_tokens imports this module
    from server.services.auth.canvas_tokens import current_token
    return current_token()


def _get_client(key=None, timeout=None) -> FakeCanvas | Canvas:
    if is_mock_canvas():
        return FakeCanvas()
    if not key:
        key = _current_token()
    if not key:
        # imported here because the auth package imports this module
        from server.services.auth.after_login import remember_page_for_after_login
        remember_page_for_after_login()
        raise Redirect(url_for('auth.login'))
    client = Canvas(current_app.config['CANVAS_SERVER_URL'], key)
    if timeout:
        session = client._Canvas__requester._session
        session.mount('https://', _TimeoutAdapter(timeout))
        session.mount('http://', _TimeoutAdapter(timeout))
    return client


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


def _roster_students(offering_canvas_id, key=None, timeout=None):
    """The students on the offering's Canvas roster."""
    course = _get_client(key, timeout).get_course(offering_canvas_id)
    # Canvas sends 10 a page unless asked: 150 requests for a course of 1,500
    return course.get_users(enrollment_type='student', per_page=100)


def get_student_roster_for_offering(offering_canvas_id, key=None):
    headers = ['canvas id', 'email', 'name', 'student id']
    rows = []
    for student in _roster_students(offering_canvas_id, key, ROSTER_TIMEOUT):
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


class _RosterDeadlinePassed(Exception):
    pass


def _no_student_ids(offering_canvas_id, sids):
    """
    None for a roster with no student ids: Canvas leaves them out for staff whose role can't see them,
    and their import or lookup mustn't clear everyone's, or hide the photos from everyone else.
    """
    if sids:
        return sids
    current_app.logger.warning("The Canvas roster of offering %s has no student ids: the signed-in user's "
                               "Canvas role may not show them", offering_canvas_id)
    return None


def _fetch_student_ids(offering_canvas_id, key, deadline=None) -> dict[str, str] | None:
    """
    The student id (sis_user_id) of each student on the offering's Canvas roster, by Canvas id, or None
    if there are none (see _no_student_ids), Canvas fails or the deadline (a time.monotonic()) passes.
    A student without one is left out.
    """
    sids = {}
    try:
        for student in _roster_students(offering_canvas_id, key, ROSTER_TIMEOUT):
            if deadline is not None and time.monotonic() > deadline:
                raise _RosterDeadlinePassed('took too long')
            if getattr(student, 'sis_user_id', None):
                sids[str(student.id)] = str(student.sis_user_id)
    # anything: this is best effort, for a photo or alongside an import, and neither may fail for it
    # (e.g. a canvasapi upgrade breaking the timeout, which reaches into its internals)
    except Exception as error:
        current_app.logger.warning("Couldn't get the Canvas roster of offering %s: %s", offering_canvas_id, error)
        return None
    return _no_student_ids(offering_canvas_id, sids)


def _roster_key():
    """The Canvas token to get a roster with: '' for the fake Canvas, which needs none, or None if there's none."""
    return '' if is_mock_canvas() else _current_token()


def _cache_student_ids(offering_canvas_id, sids):
    from server.cache import cache_store, cache_key_roster_sids, ROSTER_SIDS_CACHE_LIFE
    cache_store.set(cache_key_roster_sids(offering_canvas_id), sids, timeout=ROSTER_SIDS_CACHE_LIFE)


def fetch_roster_student_ids(offering_canvas_id) -> dict[str, str] | None:
    """
    For an import: the student ids on the offering's Canvas roster now (see _fetch_student_ids), or
    None if there's no Canvas token or Canvas fails, so the import goes ahead without them.
    """
    key = _roster_key()
    if key is None:
        return None
    sids = _fetch_student_ids(offering_canvas_id, key)
    if sids is not None:
        _cache_student_ids(offering_canvas_id, sids)
    return sids


def roster_student_ids_from_rows(offering_canvas_id, rows) -> dict[str, str] | None:
    """The same, from the rows of get_student_roster_for_offering, which the Canvas roster import has."""
    sids = _no_student_ids(offering_canvas_id, {
        str(row['canvas id']): str(row['student id']) for row in rows if row.get('canvas id') and row.get('student id')})
    if sids is not None:
        _cache_student_ids(offering_canvas_id, sids)
    return sids


def get_roster_student_ids(offering_canvas_id) -> dict[str, str]:
    """
    For a photo of a student whose student id wasn't on the roster at the last import: the student ids
    on the offering's Canvas roster (see _fetch_student_ids), kept for a few minutes.

    It never fails: with no Canvas token, or if Canvas fails, is slow or gives no student ids, there are
    no ids (and the photo is the placeholder) rather than a sign-in redirect or an error. After any of
    those but the first, photos don't ask Canvas again for a minute.
    """
    from server.cache import cache_store, cache_key_roster_sids, cache_key_roster_failed
    sids = cache_store.get(cache_key_roster_sids(offering_canvas_id))
    if sids is not None:
        return sids
    key = _roster_key()
    if key is None or cache_store.get(cache_key_roster_failed(offering_canvas_id)):
        return {}
    sids = _fetch_student_ids(offering_canvas_id, key, deadline=time.monotonic() + PHOTO_ROSTER_DEADLINE)
    if sids is None:
        cache_store.set(cache_key_roster_failed(offering_canvas_id), True, timeout=ROSTER_FAILURE_CACHE_LIFE)
        return {}
    _cache_student_ids(offering_canvas_id, sids)
    return sids


def api_course_to_model(course: Course | FakeCourse) -> Offering:
    return Offering(
        canvas_id=str(course.id),
        name=course.name,
        code=course.course_code,
        start_at=course.start_at,
    )
