from server.typings.exception import DataValidationError
from server.models import Student


def prepare_students(exam, headers, rows):
    """
    Prepare a list of students from the spreadsheet data, for the given exam.
    """
    if 'email' not in headers:
        raise DataValidationError('Missing "email" column')
    elif 'name' not in headers:
        raise DataValidationError('Missing "name" column')
    elif 'bcourses id' not in headers and 'canvas id' not in headers:
        raise DataValidationError('Missing "canvas id" column')

    new_students = []
    updated_students = []
    invalid_students = []

    for row in rows:
        canvas_id = row.pop(
            'bcourses id', row.pop('canvas id', None))
        email = row.pop('email', None)
        name = row.pop('name', None)
        if not canvas_id:
            invalid_students.append(row)
        student = Student.query.filter_by(exam_id=int(exam.id), canvas_id=str(canvas_id)).first()
        is_new = False
        if not student:
            is_new = True
            student = Student(exam_id=exam.id, canvas_id=canvas_id)
        student.name = name or student.name
        student.email = email or student.email
        if not student.name or not student.email:
            invalid_students.append(row)
            continue
        student.sid = row.pop('student id', None) or student.sid
        student.wants = {k.lower() for k, v in row.items() if v.lower() == 'true'}
        student.avoids = {k.lower() for k, v in row.items() if v.lower() == 'false'}
        student.room_wants = set()
        student.room_avoids = set()
        # wants and avoids should be mutually exclusive
        if not student.wants.isdisjoint(student.avoids) \
                or not student.room_wants.isdisjoint(student.room_avoids):
            invalid_students.append(row)
            continue
        if is_new:
            new_students.append(student)
        else:
            # clear original assignment (if any) if student is updated
            student.assignment = None
            updated_students.append(student)

    return new_students, updated_students, invalid_students
