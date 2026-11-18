"""
Students may reference rooms in their wants/avoids that no longer belong to the exam
(e.g. the room was deleted, or the preferences were imported from another exam's export).
Such dangling ids must never crash the students page.
"""
import re

from server.models import db, Exam, Room, Student
from server.services.core.data import prepare_students
from server.services.core.student import StudentImportConfig, room_id_to_attr
from server.typings.enum import UpdatedRowImportStrategy
import pytest


EXAM_URL = '/offerings/1234567/exams/midterm1'
STALE_ROOM_ID = '999999'


@pytest.fixture
def exam(seeded_db):
    exam = db.session.get(Exam, 1)
    assert exam is not None
    assert len(exam.rooms) == 1
    yield exam


@pytest.fixture
def student_with_stale_prefs(seeded_db, exam):
    student = exam.students[0]
    student.room_wants = {str(exam.rooms[0].id), STALE_ROOM_ID}
    student.room_avoids = {STALE_ROOM_ID}
    seeded_db.session.commit()
    yield student


def _pref_cards(response):
    return re.findall(r'<div class="pref-card">(.*?)</div>', response.get_data(as_text=True))


def test_wanted_and_avoided_rooms_skip_unknown_ids(exam, student_with_stale_prefs):
    assert student_with_stale_prefs.wanted_rooms == [exam.rooms[0]]
    assert student_with_stale_prefs.avoided_rooms == []


def test_unknown_room_ids(exam, student_with_stale_prefs):
    assert student_with_stale_prefs.unknown_room_wants == [STALE_ROOM_ID]
    assert student_with_stale_prefs.unknown_room_avoids == [STALE_ROOM_ID]
    assert exam.get_unknown_room_ids({exam.rooms[0].id, 7, '8'}) == ['7', '8']


def test_get_rooms_ignores_rooms_of_other_exams(seeded_db, exam):
    other_exam = Exam(offering_canvas_id=exam.offering_canvas_id, name='other', display_name='Other', is_active=False)
    other_room = Room(name='other', display_name='Other Room', start_at=exam.rooms[0].start_at, duration_minutes=60)
    other_exam.rooms.append(other_room)
    seeded_db.session.add(other_exam)
    seeded_db.session.commit()

    assert exam.get_rooms({other_room.id}) == []
    assert exam.get_rooms({exam.rooms[0].id, str(other_room.id)}) == [exam.rooms[0]]
    assert exam.get_unknown_room_ids({other_room.id}) == [str(other_room.id)]


def test_students_page_labels_stale_room_preferences(exam, student_with_stale_prefs, login_as):
    response = login_as(1).get(f'{EXAM_URL}/students/')
    assert response.status_code == 200
    cards = _pref_cards(response)
    assert exam.rooms[0].name_and_start_at_time_display(short=True) in cards
    # once under wants and once under avoids
    assert cards.count(f'deleted room {STALE_ROOM_ID}') == 2


def test_deleting_a_room_removes_it_from_student_preferences(seeded_db, exam, login_as):
    room_id = str(exam.rooms[0].id)
    for student in exam.students:
        student.room_wants = {room_id}
        student.room_avoids = {STALE_ROOM_ID}
    seeded_db.session.commit()

    response = login_as(1).post(f'{EXAM_URL}/rooms/{room_id}/delete', follow_redirects=True)
    assert response.status_code == 200
    assert 'Deleted room.' in response.get_data(as_text=True)

    seeded_db.session.expire_all()
    assert db.session.get(Room, int(room_id)) is None
    for student in Student.query.filter_by(exam_id=exam.id).all():
        assert student.room_wants == set()
        # untouched: only the deleted room is removed
        assert student.room_avoids == {STALE_ROOM_ID}


def test_import_drops_room_preferences_for_rooms_of_other_exams(exam):
    room = exam.rooms[0]
    known_attr, unknown_attr = room_id_to_attr(room.id), room_id_to_attr(STALE_ROOM_ID)
    headers = ['email', 'name', 'canvas id', known_attr, unknown_attr]
    rows = [{'email': 'john.doe@example.com', 'name': 'John Doe', 'canvas id': '123456',
             known_attr: 'true', unknown_attr: 'false'}]

    new_students, updated_students, invalid_students, _ = prepare_students(exam, headers, rows)

    assert not invalid_students and not updated_students
    assert new_students[0].room_wants == {str(room.id)}
    assert new_students[0].room_avoids == set()


def test_merge_import_drops_existing_stale_room_preferences(exam, student_with_stale_prefs):
    # merging keeps a student's existing preferences, which must not carry stale ids along
    room = exam.rooms[0]
    student = student_with_stale_prefs
    headers = ['email', 'name', 'canvas id', room_id_to_attr(room.id)]
    rows = [{'email': student.email, 'name': student.name, 'canvas id': student.canvas_id,
             room_id_to_attr(room.id): 'true'}]

    _, updated_students, invalid_students, _ = prepare_students(
        exam, headers, rows,
        config=StudentImportConfig(updated_preference_import_strategy=UpdatedRowImportStrategy.MERGE))

    assert not invalid_students
    assert updated_students[0].room_wants == {str(room.id)}
    assert updated_students[0].room_avoids == set()
