"""
What staff see when an action fails: messages we write ourselves, never the exception's own text,
which for a database error holds the SQL statement, its parameters (student data) and the database's host.
"""
import io
import re
from datetime import datetime

import pytest
from markupsafe import escape
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError, OperationalError

import server.views
from server.utils.date import to_ISO8601
from server.views import _room_exists_message
from server.models import db, Exam, Offering, Room
from server.forms import ChooseCourseOfferingForm
from server.typings.exception import DataValidationError, GcpError

EXAM_URL = '/offerings/1234567/exams/midterm1'
SECRET = 'INSERT INTO students (email) VALUES (oski@berkeley.edu) -- db.internal:5432'

pytestmark = pytest.mark.app_config(WTF_CSRF_ENABLED=False)


@pytest.fixture
def staff(seeded_db, login_as):
    return login_as(1)


def _flashes(client):
    with client.session_transaction() as session:
        return session.get('_flashes', [])


def _db_error(*args, **kwargs):
    raise OperationalError(SECRET, {'email': 'oski@berkeley.edu'}, Exception('could not connect to db.internal'))


def _assert_unexpected_error_flashed(client, message_start):
    # some actions also say which exam is active now: only the error matters here
    flashes = [message for category, message in _flashes(client) if category == 'error']
    assert len(flashes) == 1
    message = flashes[0]
    assert re.fullmatch(re.escape(message_start) + r" due to an unexpected error \(ref [0-9a-f]{8}\)\.", message)
    assert 'oski' not in message and 'db.internal' not in message


def test_database_error_shows_a_reference_and_logs_the_error(staff, database_goes_down, caplog):
    staff.post(f'{EXAM_URL}/delete/')
    _assert_unexpected_error_flashed(staff, "Couldn't delete exam 'Midterm 1'")
    ref = re.search(r'ref ([0-9a-f]{8})', _flashes(staff)[0][1]).group(1)
    # the full error is in the log, under the same reference
    record = next(r for r in caplog.records if ref in r.getMessage())
    assert record.exc_info and record.exc_info[0] is OperationalError


def test_student_import_error_hides_the_exception(staff, monkeypatch):
    monkeypatch.setattr(server.views, 'get_students_from_import_form', _db_error)
    staff.post(f'{EXAM_URL}/students/import/', data={'text': 'x', 'submit': 'y'})
    _assert_unexpected_error_flashed(staff, "Couldn't import students")


def test_duplicate_room_is_reported_plainly(staff):
    rooms = Room.query.filter_by(exam_id=1).count()
    staff.post(f'{EXAM_URL}/rooms/import/from_csv_upload/', data={
        'display_name': 'Soda 999', 'submit': 'y',
        'file': (io.BytesIO(b'row,seat\nA,1\n'), 'room.csv'),
    }, content_type='multipart/form-data')
    assert _flashes(staff) == [
        ('error', "Couldn't import room 'Soda 999': A room with that name and start time already exists")]
    assert Room.query.filter_by(exam_id=1).count() == rooms


def test_room_save_error_hides_the_exception(staff, database_goes_down):
    staff.post(f'{EXAM_URL}/rooms/import/from_csv_upload/', data={
        'display_name': 'Cory 277', 'submit': 'y',
        'file': (io.BytesIO(b'row,seat\nA,1\n'), 'room.csv'),
    }, content_type='multipart/form-data')
    _assert_unexpected_error_flashed(staff, "Couldn't import room 'Cory 277'")


def test_layout_preview_of_a_file_that_is_not_utf8(staff):
    response = staff.post('/layouts/preview/', data={
        'file': (io.BytesIO('row,seat\nA,1\n'.encode('utf-16')), 'room.csv'), 'submit': 'y',
    }, content_type='multipart/form-data')
    assert response.status_code == 200
    assert escape("Couldn't preview the layout: Save the file as CSV with UTF-8 encoding") in response.text


def test_room_file_that_is_not_utf8(staff):
    staff.post(f'{EXAM_URL}/rooms/import/from_csv_upload/', data={
        'display_name': 'Cory 277', 'submit': 'y',
        'file': (io.BytesIO('row,seat\nA,1\n'.encode('utf-16')), 'room.csv'),
    }, content_type='multipart/form-data')
    assert _flashes(staff) == [('error', "Couldn't import room 'Cory 277': Save the file as CSV with UTF-8 encoding")]


def test_student_file_that_is_not_utf8(staff):
    response = staff.post(f'{EXAM_URL}/students/import/', data={
        'file': (io.BytesIO('name,email,canvas id\n'.encode('utf-16')), 'students.csv'), 'submit': 'y',
    }, content_type='multipart/form-data')
    assert response.status_code == 200
    assert 'Save the file as CSV with UTF-8 encoding' in response.text


def test_canvas_roster_import_keeps_messages_written_for_users(staff, monkeypatch):
    def missing_emails(*args):
        raise DataValidationError('Missing "email" column')
    monkeypatch.setattr(server.views, 'get_students_from_canvas', missing_emails)
    staff.post(f'{EXAM_URL}/students/import/from_canvas_roster/', data={'submit': 'y'})
    assert _flashes(staff) == [
        ('error', 'Couldn\'t import students from the Canvas roster: Missing "email" column')]


EDIT_ROOM = {'display_name': 'Soda 999', 'movable_seats-0-attributes': '', 'movable_seats-0-count': '0', 'submit': 'y'}

# each action, and the start of what it says when the database fails under it
DATABASE_FAILURES = {
    'hide offering': ('/offerings/1234567/hide/', {}, "Couldn't hide Introduction to Software Engineering (Fall 2023)"),
    'create exam': ('/offerings/1234567/exams/new/', {'name': 'final', 'display_name': 'Final', 'submit': 'y'},
                    "Couldn't create exam 'final'"),
    'edit exam': (f'{EXAM_URL}/edit/', {'display_name': 'Midterm One', 'submit': 'y'},
                  "Couldn't edit exam 'Midterm One'"),
    'toggle exam': (f'{EXAM_URL}/toggle/', {}, "Couldn't activate or deactivate exam 'Midterm 1'"),
    'delete room': (f'{EXAM_URL}/rooms/1/delete', {}, "Couldn't delete room 'Soda 999'"),
    'edit room': (f'{EXAM_URL}/rooms/1/edit', EDIT_ROOM, "Couldn't edit room 'Soda 999'"),
    'delete student': (f'{EXAM_URL}/students/1/delete', {}, "Couldn't delete student Jimmy Xu"),
}


@pytest.fixture
def database_goes_down(monkeypatch):
    """Commits fail, and so does every query after the rollback: the error path must not need the database."""
    real_rollback = db.session.rollback

    def rollback():
        real_rollback()
        monkeypatch.setattr(db.session(), 'execute', _db_error)
    monkeypatch.setattr(db.session, 'commit', _db_error)
    monkeypatch.setattr(db.session, 'rollback', rollback)


@pytest.mark.parametrize('url, data, message_start', DATABASE_FAILURES.values(), ids=DATABASE_FAILURES.keys())
def test_database_errors_hide_the_exception(staff, database_goes_down, url, data, message_start):
    response = staff.post(url, data=data)
    assert response.status_code == 302
    _assert_unexpected_error_flashed(staff, message_start)


def test_importing_an_offering_hides_the_exception(seeded_db, login_as, monkeypatch):
    # user 2 teaches 2345678: take it out so there is a course to import
    db.session.delete(Offering.query.filter_by(canvas_id='2345678').one())
    db.session.commit()
    monkeypatch.setattr(db.session, 'commit', _db_error)
    client = login_as(2)
    client.post('/offerings/new', data={'offerings': '2345678', 'submit': 'y'})
    _assert_unexpected_error_flashed(client, "Couldn't import the course offerings")


def _clash_with(make_duplicate):
    """A commit that fails because another request just saved make_duplicate()."""
    real_commit, real_rollback = db.session.commit, db.session.rollback

    def commit():
        real_rollback()
        db.session.add(make_duplicate())
        real_commit()
        raise IntegrityError(SECRET, {}, Exception('UNIQUE constraint failed'))
    return commit


def test_exam_created_meanwhile_is_reported_plainly(staff, monkeypatch):
    # another request created it after the check for an existing exam
    monkeypatch.setattr(db.session, 'commit', _clash_with(
        lambda: Exam(offering_canvas_id='1234567', name='final', display_name='Final', is_active=False)))
    staff.post('/offerings/1234567/exams/new/', data={'name': 'final', 'display_name': 'Final', 'submit': 'y'})
    assert _flashes(staff) == [('error', "An exam named 'final' already exists in this offering.")]


def test_offering_imported_meanwhile_is_reported_plainly(seeded_db, login_as, monkeypatch):
    offering = Offering.query.filter_by(canvas_id='2345678').one()
    columns = {column.name: getattr(offering, column.name) for column in Offering.__table__.columns}
    name = offering.name
    db.session.delete(offering)
    db.session.commit()
    monkeypatch.setattr(db.session, 'commit', _clash_with(lambda: Offering(**columns)))
    client = login_as(2)
    client.post('/offerings/new', data={'offerings': '2345678', 'submit': 'y'})
    assert _flashes(client) == [('error', f"Already imported: {name}.")]


def test_room_imported_meanwhile_is_reported_plainly(staff, monkeypatch):
    monkeypatch.setattr(db.session, 'commit', _clash_with(
        lambda: Room(exam_id=1, name='cory277', display_name='Cory 277',
                     start_at=to_ISO8601(datetime(2023, 12, 12, 9, 0)))))
    staff.post(f'{EXAM_URL}/rooms/import/from_manual/',
               data={**EDIT_ROOM, 'display_name': 'Cory 277', 'start_at': '2023-12-12T09:00'})
    assert _flashes(staff) == [('error', _room_exists_message('Cory 277'))]


def test_room_without_a_start_time_is_never_a_duplicate(staff, monkeypatch):
    # the database lets rooms without a start time share a name, so a broken constraint is something else
    db.session.add(Room(exam_id=1, name='soda999', display_name='Soda 999 (late)',
                        start_at=to_ISO8601(datetime(2023, 12, 12, 14, 0))))
    db.session.commit()

    def commit():
        raise IntegrityError(SECRET, {}, Exception('NOT NULL constraint failed'))
    monkeypatch.setattr(db.session, 'commit', commit)
    # EDIT_ROOM has no start time
    staff.post(f'{EXAM_URL}/rooms/1/edit', data=EDIT_ROOM)
    _assert_unexpected_error_flashed(staff, "Couldn't edit room 'Soda 999'")


def test_room_moved_onto_another_rooms_time_names_that_room(staff):
    # same name (slug) as the seed room, at another time
    db.session.add(Room(exam_id=1, name='soda999', display_name='Soda 999 (late)',
                        start_at=to_ISO8601(datetime(2023, 12, 12, 14, 0))))
    db.session.commit()
    # renaming doesn't change the slug: moving the seed room to that time clashes with the late room
    before = _seed_room_name_and_time()
    response = staff.post(f'{EXAM_URL}/rooms/1/edit', data={**EDIT_ROOM, 'display_name': 'Soda 999 Overflow',
                                                            'start_at': '2023-12-12T14:00'})
    # the form stays up, with what was entered, to pick another time
    assert response.status_code == 200
    assert 'value="Soda 999 Overflow"' in response.text
    assert str(escape(_room_exists_message('Soda 999 (late)'))) in response.text
    assert _seed_room_name_and_time() == before


@pytest.mark.parametrize('url, data, message_start', [
    ('/offerings/1234567/exams/new/', {'name': 'final', 'display_name': 'Final', 'submit': 'y'},
     "Couldn't create exam 'final'"),
    (f'{EXAM_URL}/rooms/import/from_manual/', {**EDIT_ROOM, 'display_name': 'Cory 277'},
     "Couldn't import room 'Cory 277'"),
    (f'{EXAM_URL}/rooms/1/edit', EDIT_ROOM, "Couldn't edit room 'Soda 999'"),
], ids=['create exam', 'import room', 'edit room'])
def test_other_broken_constraints_are_unexpected(staff, monkeypatch, url, data, message_start):
    # not a duplicate: a bug, so it is logged with a reference rather than called a duplicate
    def commit():
        raise IntegrityError(SECRET, {}, Exception('NOT NULL constraint failed'))
    monkeypatch.setattr(db.session, 'commit', commit)
    assert staff.post(url, data=data).status_code == 302
    _assert_unexpected_error_flashed(staff, message_start)


RENAMED_ROOM = {**EDIT_ROOM, 'display_name': 'Soda 999 Overflow', 'start_at': '2023-12-12T14:00'}


def _seed_room_name_and_time():
    db.session.expire_all()
    room = db.session.get(Room, 1)
    return room.display_name, room.start_at


def test_room_seats_that_fail_validation_save_nothing(staff, monkeypatch):
    def fail(*args):
        raise DataValidationError('Fixed seat name repeated: A1')
    monkeypatch.setattr(server.views, 'update_room_from_manual_input', fail)
    before = _seed_room_name_and_time()
    response = staff.post(f'{EXAM_URL}/rooms/1/edit', data=RENAMED_ROOM)
    # the form stays up, with what was entered, to fix the seats
    assert response.status_code == 200
    assert 'value="Soda 999 Overflow"' in response.text
    assert str(escape("Couldn't edit the seats of room 'Soda 999 Overflow', so nothing was saved:"
                      " Fixed seat name repeated: A1")) in response.text
    assert _seed_room_name_and_time() == before


def test_room_seats_that_fail_with_the_database_down_go_back_to_the_exam(staff, database_goes_down, monkeypatch):
    def fail(*args):
        raise DataValidationError('Fixed seat name repeated: A1')
    monkeypatch.setattr(server.views, 'update_room_from_manual_input', fail)
    # after the rollback, the room can't be loaded to show the form again
    assert staff.post(f'{EXAM_URL}/rooms/1/edit', data=RENAMED_ROOM).status_code == 302
    assert _flashes(staff) == [('error', "Couldn't edit the seats of room 'Soda 999 Overflow', so nothing was saved:"
                                         " Fixed seat name repeated: A1")]


def test_room_seats_that_fail_when_even_rollbacks_fail_go_back_to_the_exam(staff, monkeypatch):
    def fail(*args):
        # the database goes down: queries fail, and so do rollbacks
        monkeypatch.setattr(db.session(), 'execute', _db_error)
        raise DataValidationError('Fixed seat name repeated: A1')
    monkeypatch.setattr(server.views, 'update_room_from_manual_input', fail)
    monkeypatch.setattr(db.session, 'rollback', _db_error)
    assert staff.post(f'{EXAM_URL}/rooms/1/edit', data=RENAMED_ROOM).status_code == 302
    assert _flashes(staff) == [('error', "Couldn't edit the seats of room 'Soda 999 Overflow', so nothing was saved:"
                                         " Fixed seat name repeated: A1")]


def test_room_deleted_while_its_seats_fail_goes_back_to_the_exam(staff, monkeypatch):
    def fail(*args):
        raise DataValidationError('Fixed seat name repeated: A1')
    monkeypatch.setattr(server.views, 'update_room_from_manual_input', fail)
    real_rollback = db.session.rollback

    def rollback():
        real_rollback()
        # another staff member deletes the room before the form is shown again
        db.session.execute(delete(Room).where(Room.id == 1))
        db.session.commit()
    monkeypatch.setattr(db.session, 'rollback', rollback)
    assert staff.post(f'{EXAM_URL}/rooms/1/edit', data=RENAMED_ROOM).status_code == 302
    assert _flashes(staff) == [('error', "Couldn't edit the seats of room 'Soda 999 Overflow', so nothing was saved:"
                                         " Fixed seat name repeated: A1")]


def _clash_on_commit(monkeypatch, rollbacks_that_work):
    """The commit breaks a constraint, then the database goes down: queries fail, and so do rollbacks
    after the first rollbacks_that_work."""
    def commit():
        raise IntegrityError(SECRET, {}, Exception('UNIQUE constraint failed'))
    real_rollback = db.session.rollback
    calls = []

    def rollback():
        calls.append(1)
        if len(calls) > rollbacks_that_work:
            _db_error()
        real_rollback()
        monkeypatch.setattr(db.session(), 'execute', _db_error)
    monkeypatch.setattr(db.session, 'commit', commit)
    monkeypatch.setattr(db.session, 'rollback', rollback)


@pytest.mark.parametrize('rollbacks_that_work', [0, 1], ids=['first rollback fails', 'looking for the clash fails'])
def test_a_clash_with_the_database_going_down_says_so(staff, monkeypatch, rollbacks_that_work):
    _clash_on_commit(monkeypatch, rollbacks_that_work)
    # with a start time, the clashing room is looked for
    assert staff.post(f'{EXAM_URL}/rooms/1/edit', data=RENAMED_ROOM).status_code == 302
    _assert_unexpected_error_flashed(staff, "Couldn't edit room 'Soda 999 Overflow'")


def test_room_seats_that_fail_unexpectedly_save_nothing(staff, monkeypatch):
    def fail(*args):
        raise OperationalError(SECRET, {}, Exception())
    monkeypatch.setattr(server.views, 'update_room_from_manual_input', fail)
    before = _seed_room_name_and_time()
    staff.post(f'{EXAM_URL}/rooms/1/edit', data=RENAMED_ROOM)
    _assert_unexpected_error_flashed(staff, "Couldn't edit the seats of room 'Soda 999 Overflow'")
    assert _seed_room_name_and_time() == before


def test_edited_room_says_it_was_saved(staff):
    assert staff.post(f'{EXAM_URL}/rooms/1/edit', data=RENAMED_ROOM).status_code == 302
    assert _flashes(staff) == [('success', "Saved room 'Soda 999 Overflow'.")]
    db.session.expire_all()
    assert db.session.get(Room, 1).display_name == 'Soda 999 Overflow'


NO_ACTIVE_EXAM_LEFT = ('info', "No active exam left. The first exam is activated by default.")


def test_created_exam_says_it_was_created(staff):
    staff.post('/offerings/1234567/exams/new/', data={'name': 'final', 'display_name': 'Final', 'submit': 'y'})
    assert _flashes(staff) == [('success', "Created exam 'Final'.")]


def test_edited_exam_says_it_was_saved(staff):
    staff.post(f'{EXAM_URL}/edit/', data={'display_name': 'Midterm One', 'active': 'y', 'submit': 'y'})
    assert _flashes(staff) == [('success', "Saved exam 'Midterm One'.")]


def test_toggled_exam_says_what_changed(staff):
    db.session.add(Exam(offering_canvas_id='1234567', name='midterm2', display_name='Midterm 2', is_active=False))
    db.session.commit()
    midterm2_url = '/offerings/1234567/exams/midterm2'
    staff.post(f'{midterm2_url}/toggle/')
    assert _flashes(staff) == [('success', "Activated exam 'Midterm 2'.")]
    with staff.session_transaction() as session:
        session.pop('_flashes')
    # with no exam left active, the first by name (Midterm 1) is activated
    staff.post(f'{midterm2_url}/toggle/')
    assert _flashes(staff) == [NO_ACTIVE_EXAM_LEFT, ('success', "Deactivated exam 'Midterm 2'.")]


def test_deactivating_the_only_exam_does_not_say_it_was_deactivated(staff):
    # it stays active, as the info message says
    staff.post(f'{EXAM_URL}/toggle/')
    assert _flashes(staff) == [NO_ACTIVE_EXAM_LEFT]
    db.session.expire_all()
    assert db.session.get(Exam, 1).is_active


def test_imported_room_says_it_was_imported(staff):
    staff.post(f'{EXAM_URL}/rooms/import/from_manual/', data={**EDIT_ROOM, 'display_name': 'Cory 277'})
    assert _flashes(staff) == [('success', "Imported room 'Cory 277'.")]


def test_master_sheet_rooms_say_how_many_were_imported(staff, monkeypatch):
    monkeypatch.setattr(server.views, 'get_spreadsheet_tabs', lambda url: ['Cory 277', 'Wheeler 150'])
    monkeypatch.setattr(server.views, 'get_room_from_google_spreadsheet',
                        lambda exam, form: Room(exam_id=exam.id, name=form.display_name.data.lower().replace(' ', ''),
                                                display_name=form.display_name.data))
    staff.post(f'{EXAM_URL}/rooms/import/from_master_sheet/',
               data={'rooms': ['Cory 277', 'Wheeler 150'], 'submit': 'y'})
    assert _flashes(staff) == [('success', "Imported 2 rooms.")]


def test_custom_sheet_room_error_hides_the_exception(staff, monkeypatch):
    monkeypatch.setattr(server.views, 'get_room_from_google_spreadsheet', _db_error)
    response = staff.post(f'{EXAM_URL}/rooms/import/from_custom_sheet/', data={
        'display_name': 'Cory 277', 'sheet_url': 'https://docs.google.com/spreadsheets/d/abc/edit',
        'sheet_range': 'Cory 277', 'create_room': 'y'})
    # nothing was imported, so the form stays up to fix the sheet
    assert response.status_code == 200
    assert re.search(r"Couldn(&#39;|')t import room (&#39;|')Cory 277(&#39;|') due to an unexpected error"
                     r" \(ref [0-9a-f]{8}\)\.", response.text)
    assert SECRET not in response.text and 'oski' not in response.text


def test_custom_sheet_room_is_saved(staff, monkeypatch):
    monkeypatch.setattr(server.views, 'get_room_from_google_spreadsheet',
                        lambda exam, form: Room(exam_id=exam.id, name='cory277', display_name='Cory 277'))
    staff.post(f'{EXAM_URL}/rooms/import/from_custom_sheet/', data={
        'display_name': 'Cory 277', 'sheet_url': 'https://docs.google.com/spreadsheets/d/abc/edit',
        'sheet_range': 'Cory 277', 'create_room': 'y'})
    assert Room.query.filter_by(exam_id=1, display_name='Cory 277').count() == 1


def test_master_sheet_rooms_report_each_failure(staff, monkeypatch):
    monkeypatch.setattr(server.views, 'get_spreadsheet_tabs', lambda url: ['Cory 277', 'Wheeler 150'])

    def get_room(exam, form):
        if form.display_name.data == 'Cory 277':
            raise GcpError('Sheet is empty')
        return Room(exam_id=exam.id, name='wheeler150', display_name='Wheeler 150')
    monkeypatch.setattr(server.views, 'get_room_from_google_spreadsheet', get_room)
    staff.post(f'{EXAM_URL}/rooms/import/from_master_sheet/',
               data={'rooms': ['Cory 277', 'Wheeler 150'], 'submit': 'y'})
    assert _flashes(staff) == [('error', "Couldn't import room 'Cory 277': Sheet is empty"),
                               ('success', "Imported 1 room.")]
    assert [r.display_name for r in Room.query.filter_by(exam_id=1).order_by(Room.id)] == ['Soda 999', 'Wheeler 150']


def test_canvas_roster_import_error_hides_the_exception(staff, monkeypatch):
    monkeypatch.setattr(server.views, 'get_students_from_canvas', _db_error)
    staff.post(f'{EXAM_URL}/students/import/from_canvas_roster/', data={'submit': 'y'})
    _assert_unexpected_error_flashed(staff, "Couldn't import students from the Canvas roster")


def test_layout_preview_error_hides_the_exception(staff, monkeypatch):
    monkeypatch.setattr(server.views, 'get_layout_preview_from_text', _db_error)
    response = staff.post('/layouts/preview/', data={'text': 'row,seat\nA,1\n'})
    assert re.search(r"Couldn(&#39;|')t preview the layout due to an unexpected error \(ref [0-9a-f]{8}\)\.",
                     response.text)
    assert 'oski' not in response.text


def test_broken_constraint_with_the_database_gone_is_unexpected(staff, database_goes_down, monkeypatch):
    # looking for the duplicate fails too, so it can't be called one
    def commit():
        raise IntegrityError(SECRET, {}, Exception('UNIQUE constraint failed'))
    monkeypatch.setattr(db.session, 'commit', commit)
    response = staff.post('/offerings/1234567/exams/new/', data={'name': 'final', 'display_name': 'Final', 'submit': 'y'})
    assert response.status_code == 302
    _assert_unexpected_error_flashed(staff, "Couldn't create exam 'final'")


def test_offering_shown_again_is_not_called_a_duplicate(seeded_db, login_as, monkeypatch):
    # 2345678 is hidden, so importing it shows it again: its row always exists, so it is no duplicate
    Offering.query.filter_by(canvas_id='2345678').one().is_hidden = True
    db.session.commit()

    def commit():
        raise IntegrityError(SECRET, {}, Exception('NOT NULL constraint failed'))
    monkeypatch.setattr(db.session, 'commit', commit)
    client = login_as(2)
    client.post('/offerings/new', data={'offerings': '2345678', 'submit': 'y'})
    _assert_unexpected_error_flashed(client, "Couldn't import the course offerings")


def test_hiding_reports_success_without_the_database(staff, monkeypatch):
    # after the commit the offering is expired: the message must not need it reloaded
    real_commit = db.session.commit

    def commit():
        real_commit()
        monkeypatch.setattr(db.session(), 'execute', _db_error)
    monkeypatch.setattr(db.session, 'commit', commit)
    staff.post('/offerings/1234567/hide/')
    assert _flashes(staff) == [('success', 'Hid Introduction to Software Engineering (Fall 2023). Its exams are kept;'
                                           ' import it again from Canvas to show it again.')]


def test_failed_room_lookup_does_not_fail_the_next_rooms(staff, monkeypatch):
    # on Postgres a failed statement aborts the transaction until a rollback
    monkeypatch.setattr(server.views, 'get_spreadsheet_tabs', lambda url: ['Cory 277', 'Wheeler 150'])
    rolled_back = []
    real_rollback = db.session.rollback
    monkeypatch.setattr(db.session, 'rollback', lambda: (rolled_back.append(True), real_rollback()))

    def get_room(exam, form):
        if form.display_name.data == 'Cory 277':
            raise OperationalError(SECRET, {}, Exception('statement timeout'))
        assert rolled_back
        return Room(exam_id=exam.id, name='wheeler150', display_name='Wheeler 150')
    monkeypatch.setattr(server.views, 'get_room_from_google_spreadsheet', get_room)
    staff.post(f'{EXAM_URL}/rooms/import/from_master_sheet/',
               data={'rooms': ['Cory 277', 'Wheeler 150'], 'submit': 'y'})
    _assert_unexpected_error_flashed(staff, "Couldn't import room 'Cory 277'")
    assert Room.query.filter_by(exam_id=1, display_name='Wheeler 150').count() == 1


def test_failed_seat_update_is_reported_once(staff, database_goes_down, monkeypatch):
    monkeypatch.setattr(server.views, 'update_room_from_manual_input', _db_error)
    assert staff.post(f'{EXAM_URL}/rooms/1/edit', data=EDIT_ROOM).status_code == 302
    _assert_unexpected_error_flashed(staff, "Couldn't edit the seats of room 'Soda 999'")


@pytest.mark.parametrize('csv, message', [
    ('row,seat,x\nA,1,left\n', 'Seat A1: x and y must be numbers.'),
    ('row,seat,count\n,,two\n', 'Each movable seat row needs a whole number in its count column (got "two").'),
], ids=['coordinate', 'count'])
def test_room_file_with_bad_numbers(staff, csv, message):
    staff.post(f'{EXAM_URL}/rooms/import/from_csv_upload/', data={
        'display_name': 'Cory 277', 'submit': 'y', 'file': (io.BytesIO(csv.encode()), 'room.csv'),
    }, content_type='multipart/form-data')
    assert _flashes(staff) == [('error', f"Couldn't import room 'Cory 277': {message}")]


def test_failure_before_saving_an_exam_is_unexpected(staff, monkeypatch):
    monkeypatch.setattr(Offering, 'mark_all_exams_as_inactive', _db_error)
    assert staff.post('/offerings/1234567/exams/new/',
                      data={'name': 'final', 'display_name': 'Final', 'active': 'y', 'submit': 'y'}).status_code == 302
    _assert_unexpected_error_flashed(staff, "Couldn't create exam 'final'")


def test_failed_room_preference_cleanup_keeps_the_room(staff, monkeypatch):
    monkeypatch.setattr(Exam, 'remove_room_preferences', _db_error)
    staff.post(f'{EXAM_URL}/rooms/1/delete')
    _assert_unexpected_error_flashed(staff, "Couldn't delete room 'Soda 999'")
    monkeypatch.undo()
    assert db.session.get(Room, 1)


def test_failed_rollback_still_reports_the_error(staff, monkeypatch):
    # with the connection gone, even the rollback can fail
    monkeypatch.setattr(db.session, 'commit', _db_error)
    monkeypatch.setattr(db.session, 'rollback', _db_error)
    staff.post(f'{EXAM_URL}/toggle/')
    _assert_unexpected_error_flashed(staff, "Couldn't activate or deactivate exam 'Midterm 1'")


def test_offering_really_imported_meanwhile(seeded_db, login_as, monkeypatch):
    # no stand-in commit: another request saves the course after this one has listed it as new
    offering = Offering.query.filter_by(canvas_id='2345678').one()
    columns = {column.name: getattr(offering, column.name) for column in Offering.__table__.columns}
    db.session.delete(offering)
    db.session.commit()
    real_validate = ChooseCourseOfferingForm.validate_on_submit

    def validate_then_import_elsewhere(form):
        db.session.add(Offering(**columns))
        db.session.commit()
        return real_validate(form)
    monkeypatch.setattr(ChooseCourseOfferingForm, 'validate_on_submit', validate_then_import_elsewhere)
    client = login_as(2)
    assert client.post('/offerings/new', data={'offerings': '2345678', 'submit': 'y'}).status_code == 302
    assert _flashes(client) == [('error', f"Already imported: {columns['name']}.")]


@pytest.mark.parametrize('url, message_start', [
    (f'{EXAM_URL}/delete/', "Couldn't delete exam 'Midterm 1'"),
    (f'{EXAM_URL}/students/1/delete', "Couldn't delete student Jimmy Xu"),
], ids=['exam', 'student'])
def test_failure_loading_what_a_delete_takes_with_it(staff, monkeypatch, url, message_start):
    # deleting loads what goes with it (an exam's rooms and students, a student's assignment)
    monkeypatch.setattr(db.session, 'delete', _db_error)
    assert staff.post(url).status_code == 302
    _assert_unexpected_error_flashed(staff, message_start)
