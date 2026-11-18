from server.forms import ImportStudentFormBase
from server.services.canvas import get_student_roster_for_offering, roster_student_ids_from_rows
from server.services.csv import original_csv_headers, parse_csv, parse_csv_str, parse_xlsx, sniff_delimiter
from server.services.google import get_spreadsheet_tab_content, get_spreadsheet_tabs

from server.services.core.layout_preview import build_layout_preview
from server.services.core.room import prepare_room, prepare_seat
from server.services.core.student import StudentImportConfig, prepare_students
from server.typings.enum import AssignmentImportStrategy
from server.typings.exception import DataValidationError


def get_room_from_google_spreadsheet(exam, room_form):
    room = prepare_room(exam, room_form)
    headers, rows = get_spreadsheet_tab_content(room_form.sheet_url.data,
                                                room_form.sheet_range.data)
    seats = prepare_seat(headers, rows)
    room.seats = seats
    return room


def get_room_from_csv(exam, room_form):
    room = prepare_room(exam, room_form)
    headers, rows = parse_csv(room_form.file.data)
    seats = prepare_seat(headers, rows)
    room.seats = seats
    return room


def get_room_from_manual_input(exam, room_form, manual_input_dict):
    room = prepare_room(exam, room_form)
    headers, rows = _get_seats_from_manual_input(manual_input_dict)
    seats = prepare_seat(headers, rows)
    room.seats = seats
    return room


def update_room_from_manual_input(room, manual_input_dict):
    headers, rows = _get_seats_from_manual_input(manual_input_dict)
    seats = prepare_seat(headers, rows)
    room.update_movable_seats(seats)  # manual input only handles movable seats


def _get_seats_from_manual_input(manual_input_dict):
    headers = set(['row', 'seat', 'x', 'y'])
    for attr_set in manual_input_dict:
        headers.union(attr_set)
    headers = list(headers)
    rows = []
    for attr_set, count in manual_input_dict.items():
        row_dic = {
            k.lower(): 'true' for k in attr_set
        }
        row_dic['count'] = count
        rows.append(row_dic)
    return headers, rows


def get_layout_preview_from_file(file):
    """Parse an uploaded room file into a preview, without creating a room."""
    # utf-8-sig so a spreadsheet export's byte order mark does not end up
    # glued to the first column name.
    return get_layout_preview_from_text(file.read().decode('utf-8-sig'))


def get_layout_preview_from_text(text):
    """
    Parse room spreadsheet text into a preview, without creating a room.

    Takes comma or tab separated text, so a range pasted straight out of Google
    Sheets works as well as a downloaded CSV.
    """
    delimiter = sniff_delimiter(text)
    headers, rows = parse_csv_str(text, delimiter=delimiter)
    return build_layout_preview(prepare_seat(headers, rows),
                                columns=original_csv_headers(text, delimiter=delimiter))


def _get_config_from_form(student_form: ImportStudentFormBase):
    return StudentImportConfig(
        revalidate_existing_assignments=student_form.revalidate_existing_assignments.data,
        assignment_import_strategy=student_form.assignment_import_strategy.data,
        updated_student_info_import_strategy=student_form.updated_student_info_import_strategy.data,
        updated_preference_import_strategy=student_form.updated_preference_import_strategy.data,
        new_student_import_strategy=student_form.new_student_import_strategy.data,
        missing_student_import_strategy=student_form.missing_student_import_strategy.data
    )


def get_students_from_import_form(exam, form):
    """
    Prepares the students of the import form: from its file, pasted text or Google Sheets link,
    whichever comes first. Files may be CSV, TSV or Excel, and pasted text comma or tab separated, so
    rows copied straight out of a spreadsheet work as well as a downloaded CSV. Without a tab name, a
    sheet's first tab is read, as is an Excel file's first sheet.
    """
    if form.file.data and form.file.data.filename.lower().endswith('.xlsx'):
        headers, rows = parse_xlsx(form.file.data.read())
        return prepare_students(exam, headers, rows, config=_get_config_from_form(form))
    elif form.file.data:
        text = form.file.data.read().decode('utf-8-sig')
    elif form.text.data and form.text.data.strip():
        text = form.text.data
    elif form.sheet_url.data:
        tab = form.sheet_range.data or get_spreadsheet_tabs(form.sheet_url.data)[0]
        headers, rows = get_spreadsheet_tab_content(form.sheet_url.data, tab)
        return prepare_students(exam, headers, rows, config=_get_config_from_form(form))
    else:
        raise DataValidationError('Choose a file, paste a roster or enter a Google Sheets link to import')
    # a byte order mark (from a file, or pasted along with text copied out of one) is not part of the header
    text = text.lstrip('\ufeff')
    headers, rows = parse_csv_str(text, delimiter=sniff_delimiter(text))
    return prepare_students(exam, headers, rows, config=_get_config_from_form(form))


def get_students_from_canvas(exam, student_form):
    """Prepares the students of the offering's Canvas roster, and gives the roster's student ids too."""
    headers, rows = get_student_roster_for_offering(exam.offering_canvas_id)
    return prepare_students(exam, headers, rows, config=_get_config_from_form(student_form)), \
        roster_student_ids_from_rows(exam.offering_canvas_id, rows)
