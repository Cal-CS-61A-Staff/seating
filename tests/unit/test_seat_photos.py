"""
Seat maps show each assigned student's photo in their seat's tooltip. The photos must load
lazily: otherwise the browser fetches one photo per assigned student as soon as a seat map
opens (1,500 requests on the assign page of a large exam), even though they stay hidden.
Each photo is in a .photo, which shows the placeholder until the photo has loaded.
"""
import re

import pytest

from server.models import db, Exam, SeatAssignment, Student

EXAM_URL = '/offerings/1234567/exams/midterm1'


@pytest.fixture
def exam(seeded_db):
    exam = db.session.get(Exam, 1)
    # the seed already seats a student in a fixed seat; seat another in a movable one,
    # since the seat map draws the two kinds with separate markup
    movable_seat = next(seat for seat in exam.rooms[0].seats if seat.fixed is False)
    student = Student.query.filter_by(exam_id=exam.id, canvas_id='345678').one()
    db.session.add(SeatAssignment(student=student, seat=movable_seat))
    db.session.commit()
    yield exam


def _photo_imgs(response):
    assert response.status_code == 200
    return re.findall(r'<span class="photo"><img [^>]*>', response.get_data(as_text=True))


@pytest.mark.parametrize('path', [
    '/rooms/1/',
    '/students/3/assign/',
])
def test_seat_map_photos_load_lazily(exam, login_as, path):
    photos = _photo_imgs(login_as(1).get(EXAM_URL + path))
    assert len(photos) == 2  # one fixed seat, one movable seat
    for photo in photos:
        assert 'loading="lazy"' in photo


def test_student_page_photo_shows_the_placeholder_until_loaded(seeded_db, login_as):
    photo, = _photo_imgs(login_as(1).get(EXAM_URL + '/students/1'))
    assert f'src="{EXAM_URL}/students/1/photo/"' in photo


@pytest.mark.app_config(MOCK_C1C=True)
def test_photo_is_fetched_once_then_cached(seeded_db, login_as):
    from server.cache import cache_key_photo, cache_store
    sid = db.session.get(Student, 1).sid
    cache_store.delete(cache_key_photo(sid))
    response = login_as(1).get('/offerings/1234567/exams/midterm1/students/1/photo/')
    assert response.status_code == 200
    assert response.mimetype == 'image/jpeg'
    assert cache_store.get(cache_key_photo(sid)) == response.data
    cache_store.delete(cache_key_photo(sid))


PHOTO_URL = EXAM_URL + '/students/{}/photo/'


@pytest.fixture
def photo_caches(seeded_db):
    """Empty photo and roster caches, and the C1C requests made, by student id."""
    from server.cache import cache_key_photo, cache_key_roster_failed, cache_key_roster_sids, cache_store
    sids = ['3033033334', '3033033335', '3033033336', '3033033399']

    def clear():
        cache_store.delete(cache_key_roster_sids('1234567'))
        cache_store.delete(cache_key_roster_failed('1234567'))
        for sid in sids:
            cache_store.delete(cache_key_photo(sid))

    clear()
    yield
    clear()


@pytest.fixture
def c1c_requests(monkeypatch):
    from server.services.c1c import C1C
    requested = []
    get_photo = C1C.get_student_photo

    def recording_get_photo(self, sid):
        requested.append(sid)
        return get_photo(self, sid)

    monkeypatch.setattr(C1C, 'get_student_photo', recording_get_photo)
    return requested


@pytest.mark.app_config(MOCK_C1C=True)
def test_photo_uses_the_student_id_from_canvas(photo_caches, c1c_requests, login_as):
    # the import gave another student id: the photo is still fetched by the one Canvas has
    student = db.session.get(Student, 1)
    student.sid = '3033033399'
    db.session.commit()
    response = login_as(1).get(PHOTO_URL.format(1))
    assert response.mimetype == 'image/jpeg'
    assert c1c_requests == ['3033033334']


@pytest.mark.app_config(MOCK_C1C=True)
def test_no_photo_for_a_student_not_on_the_canvas_roster(photo_caches, c1c_requests, login_as):
    student = db.session.get(Student, 1)
    student.canvas_id = '999999'
    db.session.commit()
    response = login_as(1).get(PHOTO_URL.format(1))
    assert response.mimetype == 'image/png'  # the placeholder
    assert c1c_requests == []


@pytest.mark.parametrize('sid', ['3033033334/../../other', '../photo', '', None, '３０３'])
def test_c1c_requests_only_all_digit_student_ids(app, monkeypatch, sid):
    from server.services.c1c import C1C
    client = C1C(None, 'https://c1c.example', 'user', 'password')
    monkeypatch.setattr(client, '_make_request', lambda path: pytest.fail(f'requested {path}'))
    with app.app_context():
        assert client.get_student_photo(sid) is None


@pytest.mark.app_config(MOCK_C1C=True)
def test_placeholder_when_canvas_fails(photo_caches, c1c_requests, login_as, monkeypatch):
    from canvasapi.exceptions import CanvasException
    from server.services import canvas

    def failing_roster(*args, **kwargs):
        raise CanvasException('Canvas is down')

    monkeypatch.setattr(canvas, '_roster_students', failing_roster)
    response = login_as(1).get(PHOTO_URL.format(1))
    assert response.status_code == 200
    assert response.mimetype == 'image/png'
    assert c1c_requests == []


def test_a_roster_without_student_ids_is_not_cached(photo_caches, login_as, monkeypatch):
    """A viewer whose Canvas role can't see student ids mustn't hide the photos from other staff."""
    from server.cache import cache_key_roster_sids, cache_store
    from server.services import canvas
    roster = canvas._roster_students

    def roster_without_sids(*args, **kwargs):
        students = list(roster(*args, **kwargs))
        for student in students:
            del student.sis_user_id
        return students

    monkeypatch.setattr(canvas, '_roster_students', roster_without_sids)
    assert login_as(1).get(PHOTO_URL.format(1)).mimetype == 'image/png'
    assert cache_store.get(cache_key_roster_sids('1234567')) is None


@pytest.mark.app_config(MOCK_CANVAS=False)
def test_placeholder_without_a_canvas_token(photo_caches, login_as, client):
    # signed in, but this browser has no Canvas token: no sign-in redirect for an <img>
    response = login_as(1).get(PHOTO_URL.format(1))
    assert response.status_code == 200
    assert response.mimetype == 'image/png'
    with client.session_transaction() as session:
        assert 'after_login' not in session


@pytest.mark.app_config(MOCK_CANVAS=False)
def test_photo_roster_requests_time_out(app, monkeypatch):
    from requests import Response
    from requests.adapters import HTTPAdapter
    from server.services import canvas
    sent = {}

    def send(self, request, **kwargs):
        sent.update(kwargs)
        response = Response()
        response.status_code = 200
        return response

    monkeypatch.setattr(HTTPAdapter, 'send', send)
    with app.app_context():
        client = canvas._get_client('token', timeout=canvas.ROSTER_TIMEOUT)
        session = client._Canvas__requester._session
        session.get('https://canvas.example.edu/api/v1/courses/1')
    assert sent['timeout'] == canvas.ROSTER_TIMEOUT


def test_roster_import_asks_for_100_students_a_page(app, monkeypatch):
    from server.services import canvas
    from server.services.canvas.fake_canvas import FakeCourse
    asked = {}
    get_users = FakeCourse.get_users

    def recording_get_users(self, **kwargs):
        asked.update(kwargs)
        return get_users(self, **kwargs)

    monkeypatch.setattr(FakeCourse, 'get_users', recording_get_users)
    with app.test_request_context():
        canvas.get_student_roster_for_offering('1234567')
    assert asked['per_page'] == 100
