"""
Pages about one student are at /offerings/<course>/exams/<exam>/students/<database id>/... (issue #132),
not at their Canvas id or student id. The seed exam's students have database ids 1 (Jimmy Xu, Canvas id
234567, seated), 2 (Sharon Lovera) and 3 (Lavender Angela).
"""
import re

import pytest

from server.models import db, Exam, Student

EXAM_URL = '/offerings/1234567/exams/midterm1'
PAGES = ['', '/edit', '/assign/', '/email/', '/photo/']


def _add_student(exam_id, canvas_id, name):
    student = Student(exam_id=exam_id, canvas_id=canvas_id, name=name, email=f'{canvas_id}@berkeley.edu',
                      wants=set(), avoids=set(), room_wants=set(), room_avoids=set())
    db.session.add(student)
    db.session.commit()
    return student


def test_students_page_links_use_database_ids(seeded_db, login_as):
    client = login_as(1)
    page = client.get(f'{EXAM_URL}/students/').get_data(as_text=True)
    # the exam's own pages (/students/import/, /students/edit, ...) are not about one student
    exam_pages = {'import', 'export', 'edit', 'assign', 'email', 'delete', 'remove_deleted_rooms'}
    links = {(student_id, rest) for student_id, rest in
             re.findall(rf"{EXAM_URL}/students/([^/'\"?]+)(/[a-z]*/?)?['\"]", page) if student_id not in exam_pages}
    assert {student_id for student_id, _ in links} == {'1', '2', '3'}, links
    # every page about a student is linked: the student, edit, assign, email and delete
    assert {rest for _, rest in links} >= {'', '/edit', '/assign/', '/email/', '/delete'}, links
    # delete buttons last: pressing one deletes the student
    for student_id, rest in sorted(links, key=lambda link: link[1] == '/delete'):
        response = _open(client, f'{EXAM_URL}/students/{student_id}{rest}')
        assert response.status_code in (200, 302), (student_id, rest, response.status_code)


@pytest.mark.parametrize('rest', PAGES)
def test_student_pages_work_by_database_id(seeded_db, login_as, rest):
    assert login_as(1).get(f'{EXAM_URL}/students/1{rest}').status_code == 200


def _open(client, url):
    """Opens a student page, or presses its delete button."""
    return client.post(url) if url.endswith('/delete') else client.get(url)


@pytest.mark.parametrize('rest', PAGES + ['/delete'])
def test_canvas_id_in_the_url_is_not_a_student(seeded_db, login_as, rest):
    assert _open(login_as(1), f'{EXAM_URL}/students/234567{rest}').status_code == 404


@pytest.mark.parametrize('rest', PAGES + ['/delete'])
def test_student_of_another_exam_is_not_found(seeded_db, login_as, rest):
    other_exam = Exam(offering_canvas_id='1234567', name='final', display_name='Final', is_active=True)
    db.session.add(other_exam)
    db.session.commit()
    other = _add_student(other_exam.id, '999001', 'Other Exam Student')
    assert _open(login_as(1), f'{EXAM_URL}/students/{other.id}{rest}').status_code == 404
    assert db.session.get(Student, other.id) is not None


def test_unknown_exam_is_not_found(seeded_db, login_as):
    assert login_as(1).get('/offerings/1234567/exams/nosuchexam/students/1').status_code == 404


def test_student_with_a_bad_canvas_id_can_be_opened_and_deleted(seeded_db, login_as):
    # students stored before imports checked canvas ids (e.g. "FALSE") used to be unreachable (#43)
    stuck = _add_student(1, 'FALSE', 'Stuck Student')
    client = login_as(1)
    for rest in ['', '/edit', '/assign/', '/email/']:
        assert client.get(f'{EXAM_URL}/students/{stuck.id}{rest}').status_code == 200, rest
    assert client.post(f'{EXAM_URL}/students/{stuck.id}/delete').status_code == 302
    assert db.session.get(Student, stuck.id) is None


def test_email_page_moved_under_the_student(seeded_db, login_as):
    assert login_as(1).get(f'{EXAM_URL}/students/email/1/').status_code == 404
