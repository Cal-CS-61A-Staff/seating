"""
Where staff end up after an action. Each redirect names its page by endpoint (views.<name>), so a
wrong name would only show up as a 500 once someone takes that action.
"""
import pytest

from server.models import db, Exam, Offering, Room, SeatAssignment, Student

OFFERING_URL = '/offerings/1234567/'
EXAM_URL = '/offerings/1234567/exams/midterm1'
STUDENTS_URL = f'{EXAM_URL}/students/'

pytestmark = pytest.mark.app_config(WTF_CSRF_ENABLED=False)


@pytest.fixture
def staff(seeded_db, login_as):
    return login_as(1)


def _lands_on(response, path):
    assert response.status_code == 302
    assert response.location.endswith(path)


def test_home_sends_signed_in_users_to_their_offerings(staff):
    _lands_on(staff.get('/'), '/offerings')


def test_importing_with_nothing_left_to_import(staff):
    # user 1's only Canvas course as staff is already set up
    _lands_on(staff.get('/offerings/new'), '/offerings')


def test_importing_without_choosing_a_course(seeded_db, login_as):
    # user 2 teaches 2345678: take it out so there is a course to import
    db.session.delete(Offering.query.filter_by(canvas_id='2345678').one())
    db.session.commit()
    _lands_on(login_as(2).post('/offerings/new', data={'submit': 'y'}), '/offerings')


def test_new_exam(staff):
    response = staff.post('/offerings/1234567/exams/new/',
                          data={'name': 'final', 'display_name': 'Final', 'active': 'y', 'submit': 'y'})
    _lands_on(response, OFFERING_URL)
    assert Exam.query.filter_by(name='final').one().is_active
    assert not db.session.get(Exam, 1).is_active


def test_new_exam_left_inactive(staff):
    response = staff.post('/offerings/1234567/exams/new/',
                          data={'name': 'final', 'display_name': 'Final', 'submit': 'y'})
    _lands_on(response, OFFERING_URL)
    assert not Exam.query.filter_by(name='final').one().is_active
    assert db.session.get(Exam, 1).is_active


def test_new_exam_left_inactive_with_no_active_exam(staff):
    db.session.get(Exam, 1).is_active = False
    db.session.commit()
    response = staff.post('/offerings/1234567/exams/new/',
                          data={'name': 'final', 'display_name': 'Final', 'submit': 'y'})
    _lands_on(response, OFFERING_URL)
    with staff.session_transaction() as session:
        assert ('info', 'No active exam left. The first exam is activated by default.') in session['_flashes']
    assert [e.name for e in Exam.query.filter_by(offering_canvas_id='1234567', is_active=True)] == ['midterm1']


def test_cancelling_an_exam_edit(staff):
    response = staff.post(f'{EXAM_URL}/edit/', data={'display_name': 'Renamed', 'cancel': 'y'})
    _lands_on(response, OFFERING_URL)
    assert db.session.get(Exam, 1).display_name == 'Midterm 1'


def test_toggling_an_exam(staff):
    _lands_on(staff.post(f'{EXAM_URL}/toggle/'), OFFERING_URL)


def test_deleting_a_room(staff):
    room = Room.query.filter_by(exam_id=1).first()
    _lands_on(staff.post(f'{EXAM_URL}/rooms/{room.id}/delete'), f'{EXAM_URL}/')


def test_deleting_an_exam(staff):
    _lands_on(staff.post(f'{EXAM_URL}/delete/'), OFFERING_URL)
    assert db.session.get(Exam, 1) is None


def test_cancelling_a_room_edit(staff):
    room = Room.query.filter_by(exam_id=1).first()
    response = staff.post(f'{EXAM_URL}/rooms/{room.id}/edit', data={'display_name': 'Renamed', 'cancel': 'y'})
    _lands_on(response, f'{EXAM_URL}/')


def test_cancelling_a_student_edit(staff):
    response = staff.post(f'{STUDENTS_URL}1/edit', data={'new_email': 'renamed@example.com', 'cancel': 'y'})
    _lands_on(response, STUDENTS_URL)


def test_cancelling_a_bulk_student_edit(staff):
    _lands_on(staff.post(f'{STUDENTS_URL}edit', data={'cancel': 'y'}), STUDENTS_URL)


def test_deleting_all_assignments(staff):
    _lands_on(staff.post(f'{STUDENTS_URL}assign/', data={'delete_all': 'y'}), STUDENTS_URL)
    assert SeatAssignment.query.count() == 0


@pytest.mark.parametrize('seated', [True, False])
def test_deleting_one_assignment(staff, seated):
    student = db.session.get(Student, 1)
    if not seated and student.assignment:
        db.session.delete(student.assignment)
        db.session.commit()
    _lands_on(staff.post(f'{STUDENTS_URL}1/assign/', data={'just_delete': 'y'}), STUDENTS_URL)
    assert db.session.get(Student, 1).assignment is None


def test_logging_out(staff):
    _lands_on(staff.post('/logout/'), '/')


@pytest.mark.app_config(MOCK_CANVAS=False)
def test_real_canvas_without_a_token_sends_you_to_log_in(staff):
    # signed in to the app, but the session has no Canvas token to call Canvas with
    _lands_on(staff.get('/offerings'), '/login/')
