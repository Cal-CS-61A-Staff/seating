import re
import itertools

from apiclient import discovery, errors

from server.services.auth import google_oauth
from server.typings.exception import DataValidationError
from server.models import Room, Seat, Student, slug


def _read_csv(sheet_url, sheet_range):
    m = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', sheet_url)
    if not m:
        raise DataValidationError('Enter a Google Sheets URL')
    spreadsheet_id = m.group(1)
    http = google_oauth.http()
    discoveryUrl = ('https://sheets.googleapis.com/$discovery/rest?'
                    'version=v4')
    service = discovery.build('sheets', 'v4', http=http,
                              discoveryServiceUrl=discoveryUrl)

    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, range=sheet_range).execute()
    except errors.HttpError as e:
        raise DataValidationError(e._get_reason())
    values = result.get('values', [])

    if not values:
        raise DataValidationError('Sheet is empty')
    headers = [h.lower() for h in values[0]]
    rows = [
        {k: v for k, v in itertools.zip_longest(headers, row, fillvalue='')}
        for row in values[1:]
    ]
    if len(set(headers)) != len(headers):
        raise DataValidationError('Headers must be unique')
    elif not all(re.match(r'[a-z0-9]+', h) for h in headers):
        raise DataValidationError('Headers must consist of digits and numbers')
    return headers, rows


def parse_form_and_validate_room(exam, room_form):
    room = Room(
        exam_id=exam.id,
        name=slug(room_form.display_name.data),
        display_name=room_form.display_name.data,
    )
    existing_room = Room.query.filter_by(
        exam_id=exam.id, name=room.name).first()
    if existing_room:
        raise DataValidationError('A room with that name already exists')
    headers, rows = _read_csv(room_form.sheet_url.data,
                              room_form.sheet_range.data)
    if 'row' not in headers:
        raise DataValidationError('Missing "row" column')
    elif 'seat' not in headers:
        raise DataValidationError('Missing "seat" column')

    x, y = 0, -1
    last_row = None
    for row in rows:
        seat = Seat()
        seat.row = row.pop('row')
        seat.seat = row.pop('seat')
        seat.name = seat.row + seat.seat
        if not seat.name:
            continue
        if seat.row != last_row:
            x = 0
            y += 1
        else:
            x += 1
        last_row = seat.row
        x_override = row.pop('x', None)
        y_override = row.pop('y', None)
        try:
            if x_override:
                x = float(x_override)
            if y_override:
                y = float(y_override)
        except TypeError:
            raise DataValidationError('xy coordinates must be floats')
        seat.x = x
        seat.y = y
        seat.attributes = {k for k, v in row.items() if v.lower() == 'true'}
        room.seats.append(seat)
    if len(set(seat.name for seat in room.seats)) != len(room.seats):
        raise DataValidationError('Seats are not unique')
    elif len(set((seat.x, seat.y) for seat in room.seats)) != len(room.seats):
        raise DataValidationError('Seat coordinates are not unique')
    return room


def parse_student_sheet(form):
    return _read_csv(form.sheet_url.data, form.sheet_range.data)


def parse_canvas_student_roster(roster):
    headers = ['canvas id', 'email', 'name', 'student id']
    rows = []
    for student in roster:
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


def validate_students(exam, headers, rows):
    if 'email' not in headers:
        raise DataValidationError('Missing "email" column')
    elif 'name' not in headers:
        raise DataValidationError('Missing "name" column')
    elif 'bcourses id' not in headers and 'canvas id' not in headers:
        raise DataValidationError('Missing "canvas id" column')
    students = []
    for row in rows:
        canvas_id = row.pop(
            'bcourses id', row.pop('canvas id', None))
        email = row.pop('email', None)
        name = row.pop('name', None)
        if not canvas_id or not email or not name:
            # dangerous. Might skip students without notifying staff
            continue
        student = Student.query.filter_by(exam_id=int(exam.id), canvas_id=str(canvas_id)).first()
        if not student:
            student = Student(exam_id=exam.id, canvas_id=canvas_id)
        student.name = name or student.sid
        student.sid = row.pop('student id', None) or student.sid
        student.email = email or student.email
        student.wants = {k for k, v in row.items() if v.lower() == 'true'}
        student.avoids = {k for k, v in row.items() if v.lower() == 'false'}
        students.append(student)
    return students
