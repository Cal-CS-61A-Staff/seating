from server.services.google import get_spreadsheet_tab_content

from server.typings.exception import DataValidationError
from server.models import Room, Seat, Student, slug
from server.utils.date import to_ISO8601


def _prepare_room(exam, room_form):
    room = Room(
        exam_id=exam.id,
        name=slug(room_form.display_name.data),
        display_name=room_form.display_name.data
    )

    start_at_iso = None
    if room_form.start_at.data:
        start_at_iso = to_ISO8601(room_form.start_at.data)
        room.start_at = start_at_iso
    if room_form.duration_minutes.data:
        room.duration_minutes = room_form.duration_minutes.data

    existing_room_query = Room.query.filter_by(
        exam_id=exam.id, name=room.name)
    if start_at_iso:
        existing_room_query = existing_room_query.filter_by(start_at=start_at_iso)
    existing_room = existing_room_query.first()

    if existing_room:
        raise DataValidationError('A room with that name and start time already exists')

    return room


def _prepare_seat(room_form):
    headers, rows = get_spreadsheet_tab_content(room_form.sheet_url.data,
                                                room_form.sheet_range.data)
    if 'row' not in headers or 'seat' not in headers:
        raise DataValidationError('Missing compulsory columns "row" and/or "seat"')

    x, y = 0, -1
    last_row = None
    valid_seats, seat_names, seat_coords = [], set(), set()
    for row in rows:
        seat = Seat()
        seat.row, seat.seat = row.pop('row', None), row.pop('seat', None)
        seat.fixed = bool(seat.row and seat.seat)

        # if we leave either row or seat blank, we regard it as a movable seat
        # movable seats does not have a fixed coordinate or name, but it still attributes
        if seat.fixed:
            seat.name = seat.row + seat.seat
            if seat.name in seat_names:
                raise DataValidationError(f'Fixed seat name repeated: {seat.name}')
            seat_names.add(seat.name)
            if seat.row != last_row:
                x, y = 0, y + 1
            else:
                x += 1
            last_row = seat.row
            x_override, y_override = row.pop('x', None), row.pop('y', None)
            try:
                if x_override:
                    x = float(x_override)
                if y_override:
                    y = float(y_override)
            except TypeError:
                raise DataValidationError('Fixed seat coordinate override must be floats.')
            coords = x, y
            if coords in seat_coords:
                raise DataValidationError(f'Fixed seat coordinates repeated: {coords}')
            seat_coords.add(coords)
            seat.x, seat.y = coords
            _ = row.pop('count', 1)  # discard count column if it exists
            seat.attributes = {k for k, v in row.items() if v.lower() == 'true'}
            valid_seats.append(seat)
        else:
            # allows count column so we can define multiple movable seats in one row
            count = row.pop('count', 1)
            attributes = {k for k, v in row.items() if v.lower() == 'true'}
            for _ in range(int(count)):
                seat = Seat()
                seat.fixed = False
                seat.attributes = attributes
                valid_seats.append(seat)
    return valid_seats


def parse_form_and_validate_room(exam, room_form):
    room = _prepare_room(exam, room_form)
    seats = _prepare_seat(room_form)
    room.seats = seats
    return room


def parse_student_sheet(form):
    return get_spreadsheet_tab_content(form.sheet_url.data, form.sheet_range.data)


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
        student.wants = {k for k, v in row.items() if v.lower() == 'true'}
        student.avoids = {k for k, v in row.items() if v.lower() == 'false'}
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
