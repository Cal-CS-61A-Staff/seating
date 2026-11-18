"""
Canvas ids are whole numbers, and a student is found on logging in by their Canvas id, so a student
imported with any other canvas id could never find their seat. (Student urls used to hold the Canvas
id too, which left such students impossible to open, edit or delete, #43; they now use database ids.)
Imports skip such rows and say why. The values below are ones found in real imports: a TRUE/FALSE
column read as canvas ids, and long Canvas ids a spreadsheet turned into scientific notation.
"""
import re

import pytest

from server.models import db, Exam, Student
from server.services.core.student import canvas_id_problem, prepare_students
from server.services.csv import parse_csv_str

EXAM_URL = '/offerings/1234567/exams/midterm1'
HEADER = 'email,name,canvas id\n'


@pytest.mark.parametrize('canvas_id', ['234567', '10720000001234567', '0'])
def test_whole_numbers_are_canvas_ids(canvas_id):
    assert canvas_id_problem(canvas_id) is None


@pytest.mark.parametrize('canvas_id', ['FALSE', 'abc123', '234567.5', '12-34', 'UID:123', '١٢٣'])
def test_anything_else_is_not_a_number(canvas_id):
    assert canvas_id_problem(canvas_id) == f'canvas id {canvas_id} is not a number'


@pytest.mark.parametrize('canvas_id', ['1.072E+16', '1.0720000001234567e16', '1E16', '1.072E16'])
def test_scientific_notation_is_explained(canvas_id):
    assert canvas_id_problem(canvas_id) == (
        f'canvas id {canvas_id} is in scientific notation, which a spreadsheet uses for long numbers '
        f'and which loses their last digits: format the column as text and export again')


@pytest.fixture
def exam(seeded_db):
    return db.session.get(Exam, 1)


def _import(exam, csv_text):
    headers, rows = parse_csv_str(csv_text)
    new, updated, invalid, _ = prepare_students(exam, headers, rows)
    db.session.add_all(new + updated)
    db.session.commit()
    return new, updated, [str(row) for row in invalid]


def test_rows_with_bad_canvas_ids_are_skipped(exam):
    new, updated, skipped = _import(exam, HEADER + 'a@berkeley.edu,Ann,FALSE\n'
                                                   'b@berkeley.edu,Bo,1.072E+16\n'
                                                   'c@berkeley.edu,Cy,777777\n')
    assert [student.canvas_id for student in new] == ['777777'] and not updated
    assert skipped == [
        'Row 2 (Ann, a@berkeley.edu, canvas id FALSE): canvas id FALSE is not a number',
        'Row 3 (Bo, b@berkeley.edu, canvas id 1.072E+16): canvas id 1.072E+16 is in scientific notation, which a '
        'spreadsheet uses for long numbers and which loses their last digits: format the column as text and export again',
    ]
    assert Student.query.filter(Student.canvas_id.in_(['FALSE', '1.072E+16'])).count() == 0


def test_bad_canvas_id_does_not_update_a_student_matched_by_email(exam):
    # the row is skipped, not matched by its email to an existing student and stored on them
    jimmy = Student.query.filter_by(exam_id=1, canvas_id='234567').one()
    _, updated, skipped = _import(exam, HEADER + f'{jimmy.email},Someone Else,FALSE\n')
    assert not updated and len(skipped) == 1
    db.session.expire_all()
    assert Student.query.filter_by(exam_id=1, canvas_id='234567').one().name == 'Jimmy Xu'


def test_cleaned_up_canvas_ids_are_still_accepted(exam):
    new, _, skipped = _import(exam, HEADER + 'c@berkeley.edu,Cy, 777777.0 \n')
    assert [student.canvas_id for student in new] == ['777777'] and not skipped


def test_imported_students_can_be_deleted_from_the_students_page(exam, login_as):
    _import(exam, HEADER + 'c@berkeley.edu,Cy,777777\n')
    client = login_as(1)
    page = client.get(f'{EXAM_URL}/students/').get_data(as_text=True)
    links = re.findall(r'<form method="POST" action="([^"]+/delete)"', page)
    new_student = Student.query.filter_by(exam_id=1, canvas_id='777777').one()
    assert f'{EXAM_URL}/students/{new_student.id}/delete' in links
    for link in links:
        assert client.post(link).status_code == 302
    assert Student.query.filter_by(exam_id=1).count() == 0
