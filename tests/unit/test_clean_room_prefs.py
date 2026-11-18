import re

import pytest

from server.models import db, Exam, Student

EXAM_URL = '/offerings/1234567/exams/midterm1'
STUDENTS_URL = f'{EXAM_URL}/students/'
NOTICE = 'room preferences for deleted rooms'


@pytest.fixture
def exam(seeded_db):
    exam = db.session.get(Exam, 1)
    assert [room.id for room in exam.rooms] == [1]
    yield exam


@pytest.fixture
def stale_students(seeded_db, exam):
    """Two students reference deleted rooms 998/999; the third only has the real room 1."""
    first, second, third = exam.students
    first.room_wants, first.room_avoids = {'1', '999'}, set()
    second.room_wants, second.room_avoids = set(), {'998'}
    third.room_wants, third.room_avoids = {'1'}, set()
    seeded_db.session.commit()
    yield first, second, third


def _prefs(student_id):
    student = db.session.get(Student, student_id)
    return student.room_wants, student.room_avoids


def test_remove_unknown_room_preferences(exam, stale_students):
    first, second, third = stale_students
    assert exam.remove_unknown_room_preferences() == 2
    db.session.commit()
    assert _prefs(first.id) == ({'1'}, set())
    assert _prefs(second.id) == (set(), set())
    assert _prefs(third.id) == ({'1'}, set())


def test_students_page_notice_counts_students(exam, stale_students, login_as):
    page = login_as(1).get(STUDENTS_URL).get_data(as_text=True)
    assert NOTICE in page
    assert re.search(r'2\s+students have\s+room preferences', page)


def test_students_page_notice_singular(exam, stale_students, login_as):
    first, second, _ = stale_students
    second.room_avoids = set()
    db.session.commit()
    page = login_as(1).get(STUDENTS_URL).get_data(as_text=True)
    assert re.search(r'1\s+student has\s+room preferences', page)


def test_students_page_has_no_notice_without_deleted_rooms(exam, login_as):
    page = login_as(1).get(STUDENTS_URL).get_data(as_text=True)
    assert NOTICE not in page


def test_remove_button_cleans_preferences(exam, stale_students, login_as):
    client = login_as(1)
    page = client.get(STUDENTS_URL).get_data(as_text=True)
    csrf_token = re.search(r'name="csrf_token" type="hidden" value="([^"]+)"', page).group(1)
    # submit the form where the page actually points it, not a hard-coded url
    # (besides the navbar's Log Out and the delete buttons)
    actions = [action for action in re.findall(r'<form method="POST" action="([^"]+)">', page)
               if action != '/logout/' and not action.endswith('/delete')]
    assert actions == [f'{STUDENTS_URL}remove_deleted_rooms/']
    action = actions[0]

    response = client.post(action, data={'csrf_token': csrf_token}, follow_redirects=True)

    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert 'Removed deleted rooms from the preferences of 2 students.' in page
    assert NOTICE not in page
    assert not any(card.startswith('deleted room') for card in re.findall(r'<div class="pref-card">(.*?)</div>', page))
    first, second, _ = stale_students
    db.session.expire_all()
    assert _prefs(first.id) == ({'1'}, set())
    assert _prefs(second.id) == (set(), set())


def test_remove_button_rejects_missing_csrf_token(exam, stale_students, login_as):
    response = login_as(1).post(f'{STUDENTS_URL}remove_deleted_rooms/', follow_redirects=True)
    assert 'Failed to remove deleted rooms' in response.get_data(as_text=True)
    first, _, _ = stale_students
    db.session.expire_all()
    assert _prefs(first.id) == ({'1', '999'}, set())


def test_remove_button_forbidden_for_students(exam, stale_students, login_as):
    # user 3 is a student in this offering without a seat assignment
    response = login_as(3).post(f'{STUDENTS_URL}remove_deleted_rooms/')
    assert response.status_code == 403


def test_cli_dry_run_changes_nothing(exam, stale_students, runner):
    result = runner.invoke(args=['cleanroomprefs', '--dry-run'])
    assert result.exit_code == 0, result.output
    assert '1234567/midterm1: 2 students' in result.output
    assert 'Dry run: would update 2 students.' in result.output
    first, second, _ = stale_students
    db.session.expire_all()
    assert _prefs(first.id) == ({'1', '999'}, set())
    assert _prefs(second.id) == (set(), {'998'})


def test_cli_cleans_preferences(exam, stale_students, runner):
    result = runner.invoke(args=['cleanroomprefs'])
    assert result.exit_code == 0, result.output
    assert 'Updated 2 students.' in result.output
    first, second, third = stale_students
    db.session.expire_all()
    assert _prefs(first.id) == ({'1'}, set())
    assert _prefs(second.id) == (set(), set())
    assert _prefs(third.id) == ({'1'}, set())
