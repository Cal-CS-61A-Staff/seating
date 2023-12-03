from server.typings.exception import DataValidationError
from server.models import Room, Seat, Student, slug
from server.utils.date import to_ISO8601


def prepare_room(exam, room_form):
    """
    Prepare a room object from the form data that is associated with the given exam.
    We only need start_at, duration_minutes, and display_name from the room_form.
    """
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


def prepare_seat(headers, rows):  # noqa: C901
    """
    Prepare a list of seats from the spreadsheet data.
    This spreadsheet data may come from a Google Sheet or a CSV file.
    """
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
            seat.attributes = {k.lower() for k, v in row.items() if v.lower() == 'true'}
            valid_seats.append(seat)
        else:
            # allows count column so we can define multiple movable seats in one row
            count = row.pop('count', 1)
            attributes = {k.lower() for k, v in row.items() if v.lower() == 'true'}
            for _ in range(int(count)):
                seat = Seat()
                seat.fixed = False
                seat.attributes = attributes
                valid_seats.append(seat)
    return valid_seats
