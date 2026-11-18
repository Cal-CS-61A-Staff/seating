"""
A student's photo is fetched by the student id Canvas has for them (canvas_sid), not the one an import
gave. Each import stores it for every student of the exam from the course's Canvas roster; a photo of a
student without one looks them up on the roster again, in case they've joined since.
The seed exam has Jimmy Xu (234567), Sharon Lovera (345678) and Lavender Angela (456789), whose student
ids in the mock Canvas are 3033033334, 3033033335 and 3033033336.
"""
import pytest
from canvasapi.exceptions import CanvasException

from server.models import db, Student
from server.services import canvas
from tests.unit.test_import_options import _manual, _post, _student

EXAM_URL = '/offerings/1234567/exams/midterm1'
PHOTO_URL = EXAM_URL + '/students/{}/photo/'


@pytest.fixture(autouse=True)
def empty_roster_caches(seeded_db):
    from server.cache import cache_key_roster_failed, cache_key_roster_sids, cache_store

    def clear():
        cache_store.delete(cache_key_roster_sids('1234567'))
        cache_store.delete(cache_key_roster_failed('1234567'))

    clear()
    yield
    clear()


@pytest.fixture
def staff(seeded_db, login_as):
    return login_as(1)


@pytest.fixture
def roster_requests(monkeypatch):
    """The roster lookups made, which can be made to fail with roster_requests.fail = True."""
    roster = canvas._roster_students

    class Requests(list):
        fail = False

    requests = Requests()

    def recording_roster(*args, **kwargs):
        requests.append(args[0])
        if requests.fail:
            raise CanvasException('Canvas is down')
        return roster(*args, **kwargs)

    monkeypatch.setattr(canvas, '_roster_students', recording_roster)
    return requests


def _canvas_sids():
    db.session.expire_all()
    return {s.canvas_id: s.canvas_sid for s in Student.query.filter_by(exam_id=1)}


def test_a_file_import_stores_every_students_canvas_student_id(staff):
    # only Sharon is in the import, but the whole exam is checked against the roster; the student id
    # in the file is not the one stored
    _manual(staff, 'canvas id,email,name,student id\n345678,sharon@berkeley.edu,"Lovera, Sharon",3099999999')
    assert _canvas_sids() == {'234567': '3033033334', '345678': '3033033335', '456789': '3033033336'}
    assert _student('345678').sid == '3099999999'


def test_a_student_not_on_the_roster_gets_no_canvas_student_id(staff):
    _manual(staff, 'canvas id,email,name,student id\n999001,new@berkeley.edu,"Student, New",3099999998')
    assert _canvas_sids()['999001'] is None


def test_an_import_clears_the_canvas_student_id_of_a_student_who_dropped(staff, monkeypatch):
    _manual(staff, 'canvas id,email,name\n345678,sharon@berkeley.edu,"Lovera, Sharon"')
    assert _canvas_sids()['234567'] == '3033033334'
    roster = canvas._roster_students
    monkeypatch.setattr(canvas, '_roster_students',
                        lambda *args: [s for s in roster(*args) if str(s.id) != '234567'])
    _manual(staff, 'canvas id,email,name\n345678,sharon@berkeley.edu,"Lovera, Sharon"')
    assert _canvas_sids()['234567'] is None


def test_the_canvas_roster_import_stores_canvas_student_ids(staff):
    _post(staff, 'canvas_roster')
    assert _canvas_sids() == {'234567': '3033033334', '345678': '3033033335', '456789': '3033033336'}


def test_a_file_import_still_works_when_canvas_fails(staff, roster_requests):
    _manual(staff, 'canvas id,email,name\n345678,sharon@berkeley.edu,"Lovera, Sharon"')
    roster_requests.fail = True
    messages = _manual(staff, 'canvas id,email,name\n999001,new@berkeley.edu,"Student, New"')
    assert any(m.startswith('Import done.') for m in messages), messages
    # the stored ids are kept rather than cleared
    assert _canvas_sids() == {'234567': '3033033334', '345678': '3033033335', '456789': '3033033336',
                              '999001': None}


@pytest.mark.app_config(MOCK_C1C=True)
def test_a_photo_by_a_stored_canvas_student_id_asks_canvas_nothing(staff, roster_requests):
    student = db.session.get(Student, 1)
    student.canvas_sid = '3033033334'
    db.session.commit()
    assert staff.get(PHOTO_URL.format(1)).mimetype == 'image/jpeg'
    assert roster_requests == []


@pytest.mark.app_config(MOCK_C1C=True)
def test_a_photo_without_a_stored_canvas_student_id_looks_it_up_and_stores_it(staff, roster_requests):
    assert db.session.get(Student, 1).canvas_sid is None
    assert staff.get(PHOTO_URL.format(1)).mimetype == 'image/jpeg'
    assert roster_requests == ['1234567']
    assert _canvas_sids()['234567'] == '3033033334'


def test_after_canvas_fails_photos_dont_ask_again_for_a_while(staff, roster_requests):
    roster_requests.fail = True
    assert staff.get(PHOTO_URL.format(1)).mimetype == 'image/png'
    assert staff.get(PHOTO_URL.format(2)).mimetype == 'image/png'
    assert roster_requests == ['1234567']


def test_a_photos_roster_lookup_gives_up_after_its_deadline(staff, monkeypatch):
    # every page of the roster is slow: the lookup stops instead of holding the request
    monkeypatch.setattr(canvas, 'PHOTO_ROSTER_DEADLINE', -1)
    assert staff.get(PHOTO_URL.format(1)).mimetype == 'image/png'
    assert _canvas_sids()['234567'] is None


def test_the_import_page_says_an_import_is_under_way(staff):
    page = staff.get(EXAM_URL + '/students/import/').get_data(as_text=True)
    assert 'id="import-status"' in page and 'role="status"' in page


@pytest.fixture
def roster_without_student_ids(monkeypatch):
    """The signed-in user's Canvas role can't see student ids: Canvas leaves them out."""
    roster = canvas._roster_students

    def without_sids(*args, **kwargs):
        students = list(roster(*args, **kwargs))
        for student in students:
            del student.sis_user_id
        return students

    monkeypatch.setattr(canvas, '_roster_students', without_sids)


def test_an_import_by_someone_who_cant_see_student_ids_keeps_the_stored_ones(staff, request):
    _manual(staff, 'canvas id,email,name\n345678,sharon@berkeley.edu,"Lovera, Sharon"')
    stored = _canvas_sids()
    request.getfixturevalue('roster_without_student_ids')
    _manual(staff, 'canvas id,email,name\n345678,sharon@berkeley.edu,"Lovera, Sharon"')
    _post(staff, 'canvas_roster')
    assert _canvas_sids() == stored == {'234567': '3033033334', '345678': '3033033335', '456789': '3033033336'}


def test_photos_dont_keep_asking_for_a_roster_without_student_ids(staff, roster_without_student_ids,
                                                                  roster_requests):
    assert staff.get(PHOTO_URL.format(1)).mimetype == 'image/png'
    assert staff.get(PHOTO_URL.format(2)).mimetype == 'image/png'
    assert roster_requests == ['1234567']


def test_any_error_in_a_photos_roster_lookup_gives_the_placeholder(staff, monkeypatch):
    # e.g. a canvasapi upgrade that breaks the timeout, which reaches into its internals
    def broken_client(*args, **kwargs):
        raise AttributeError("'Canvas' object has no attribute '_Canvas__requester'")

    monkeypatch.setattr(canvas, '_get_client', broken_client)
    assert staff.get(PHOTO_URL.format(1)).mimetype == 'image/png'


def test_the_canvas_roster_import_has_a_timeout_and_caches_the_student_ids(staff, monkeypatch):
    from server.cache import cache_key_roster_sids, cache_store
    timeouts = []
    roster = canvas._roster_students

    def recording_roster(offering_canvas_id, key=None, timeout=None):
        timeouts.append(timeout)
        return roster(offering_canvas_id, key, timeout)

    monkeypatch.setattr(canvas, '_roster_students', recording_roster)
    _post(staff, 'canvas_roster')
    assert timeouts == [canvas.ROSTER_TIMEOUT]
    # so a photo right after the import doesn't fetch the roster again
    assert cache_store.get(cache_key_roster_sids('1234567')) == {
        '234567': '3033033334', '345678': '3033033335', '456789': '3033033336'}
