import re
from flask import Blueprint, abort, current_app, redirect, render_template, request, send_file, url_for, flash, \
    Response
from flask.json import jsonify
from flask_login import current_user, login_required
from werkzeug.exceptions import HTTPException

from server.models import SeatAssignment, db, Exam, Room, Seat, Student
from server.forms import AssignSingleForm, EditExamForm, EditRoomForm, ExamForm, ImportStudentsForm, \
    RoomForm, ChooseRoomForm, ImportStudentFromCanvasRosterForm, DeleteStudentForm, \
    AssignForm, EmailForm, EmailPreviewForm, EditStudentForm, UploadRoomForm, ChooseCourseOfferingForm, EditStudentsForm, \
    PreviewLayoutForm, RemoveDeletedRoomPreferencesForm
from server.services.core.export import export_exam_student_info
from server.services.core.student import describe_invalid_rows
from server.services.email.templates import VARIABLES, get_email, make_substitutions
from server.services.google import get_spreadsheet_tabs
import server.services.canvas as canvas_client
from server.services.email import email_about_assignment, send_test_email, substitute_about_assignment
from server.services.core.data import get_room_from_csv, get_room_from_google_spreadsheet, get_room_from_manual_input, \
    get_students_from_canvas, get_students_from_import_form, update_room_from_manual_input, \
    get_layout_preview_from_file, get_layout_preview_from_text
from server.services.core.assign import assign_single_student, assign_students
from server.typings.exception import DataValidationError, NotEnoughSeatError, SeatAssignmentError
from server.typings.enum import EmailTemplate
from server.utils.date import to_ISO8601
from server.utils.misc import set_to_str, str_set_to_set

from sqlalchemy import select
from sqlalchemy.orm import joinedload

# the app's own pages; create_app registers it
bp = Blueprint('views', __name__)


@bp.route('/')
def index():
    """
    Path: /
    Home page, which is the login page.
    """
    # if already logged in, redirect to offerings page
    if current_user and current_user.is_authenticated:
        return redirect(url_for('views.offerings'))
    return render_template("index.html")


# region Offering CRUDI


@bp.route('/offerings')
@login_required
def offerings():
    from server.models import Offering
    """
    Path: /offerings
    Home page, which needs to be logged in to access.
    After logging in, fetch and present a list of course offerings.
    """
    # Fetch all user course offerings from canvas
    user = canvas_client.get_user(current_user.canvas_id)
    staff_course_dics, student_course_dics, others, skipped = canvas_client.get_user_courses_categorized(
        user)
    # course and exam pages check the user's saved roles: update them too, so every course listed here opens
    current_user.set_course_roles(staff_course_dics, student_course_dics)
    db.session.commit()
    # All fetched courses are converted to models
    staff_offerings = [canvas_client.api_course_to_model(c) for c in staff_course_dics]
    student_offerings = [canvas_client.api_course_to_model(c) for c in student_course_dics]
    other_offerings = [canvas_client.api_course_to_model(c) for c in others]
    # Check which offerings are already in the database
    staff_offering_canvas_ids = set([o.canvas_id for o in staff_offerings])
    student_offering_canvas_ids = set([o.canvas_id for o in student_offerings])
    other_offering_canvas_ids = set([o.canvas_id for o in other_offerings])
    wanted_offering_canvas_ids = staff_offering_canvas_ids | student_offering_canvas_ids | other_offering_canvas_ids
    existing_offerings = Offering.query.filter(
        Offering.canvas_id.in_(wanted_offering_canvas_ids), Offering.is_hidden.is_(False)).all()
    # Now split existing_offerings back to 3 lists
    staff_offerings_existing = []
    student_offerings_existing = []
    other_offerings_existing = []
    for o in existing_offerings:
        if o.canvas_id in staff_offering_canvas_ids:
            staff_offerings_existing.append(o)
        elif o.canvas_id in student_offering_canvas_ids:
            student_offerings_existing.append(o)
        elif o.canvas_id in other_offering_canvas_ids:
            other_offerings_existing.append(o)

    if skipped:
        flash("Skipped invalid courses from Canvas: " + str([s.__dict__ for s in skipped]), 'warning')

    return render_template("select_offering.html",
                           title="Select a Course Offering",
                           staff_offerings_existing=staff_offerings_existing,
                           student_offerings_existing=student_offerings_existing,
                           other_offerings_existing=other_offerings_existing)


@bp.route('/offerings/new', methods=['GET', 'POST'])
@login_required
def add_offerings():
    from server.models import Offering
    """
    Path: /offerings/new
    Add new course offerings to the database.
    """
    user = canvas_client.get_user(current_user.canvas_id)
    staff_course_dics, _, _, skipped = canvas_client.get_user_courses_categorized(user)
    staff_offerings = [canvas_client.api_course_to_model(o) for o in staff_course_dics]
    staff_offerings_id_to_model = {o.canvas_id: o for o in staff_offerings}
    staff_offering_ids_wanted = list(staff_offerings_id_to_model.keys())
    # Hidden offerings can be imported again, which shows them again with their exams
    hidden_offerings = {o.canvas_id: o for o in Offering.query.filter(
        Offering.canvas_id.in_(staff_offering_ids_wanted), Offering.is_hidden.is_(True))}
    staff_offering_ids_existing = set([x[0] for x in Offering.query.filter(
        Offering.canvas_id.in_(staff_offering_ids_wanted)).with_entities(Offering.canvas_id)])
    staff_offering_ids_not_existing = set(staff_offering_ids_wanted) - staff_offering_ids_existing \
        | set(hidden_offerings)
    if skipped:
        flash("Skipped invalid courses from Canvas: " + str([s.__dict__ for s in skipped]), 'warning')
    if not staff_offering_ids_not_existing:
        flash("No more new courses to import.", 'info')
        return redirect(url_for('views.offerings'))
    staff_offerings_not_existing = [staff_offerings_id_to_model[canvas_id] for canvas_id in staff_offering_ids_not_existing]
    form = ChooseCourseOfferingForm(offering_list=staff_offerings_not_existing)
    if form.validate_on_submit():
        chosen = form.offerings.data
        if not chosen:
            flash("No course offering imported.", 'info')
            return redirect(url_for('views.offerings'))
        try:
            for canvas_id in chosen:
                if canvas_id in hidden_offerings:
                    hidden_offerings[canvas_id].is_hidden = False
            db.session.bulk_save_objects([staff_offerings_id_to_model[canvas_id]
                                          for canvas_id in chosen if canvas_id not in hidden_offerings])
            db.session.commit()
            flash(f"Imported {len(chosen)} course offerings.", 'success')
            return redirect(url_for('views.offerings'))
        except Exception as e:
            db.session.rollback()
            print("error", str(e))
            flash("An error occurred when inserting offering: " + str(e), 'error')
    return render_template("new_offerings.html",
                           title="Add New Course Offerings",
                           form=form)


@bp.route('/<offering:offering>/')
def offering(offering):
    """
    Path: /offerings/<canvas_id>
    Shows all exams created for a course offering.
    """
    is_staff = str(offering.canvas_id) in current_user.staff_offerings
    all_exams = offering.exams
    active_exams = [e for e in all_exams if e.is_active]
    inactive_exams = [e for e in all_exams if not e.is_active]
    return render_template("select_exam.html",
                           title="Select an Exam for {}".format(offering.name),
                           active_exams=active_exams,
                           inactive_exams=inactive_exams,
                           all_exams=all_exams,
                           offering=offering,
                           is_staff=is_staff)


@bp.route('/<offering:offering>/hide/', methods=['POST'])
def hide_offering(offering):
    """
    Path: /offerings/<canvas_id>/hide
    Hides a course offering from the offerings page. Its exams are kept,
    and importing the course again shows it again.
    """
    # offering urls convertor lets the course's students in too: check staff status here
    if str(offering.canvas_id) not in current_user.staff_offerings:
        abort(403, "You are not a staff member in this offering.")
    try:
        offering.is_hidden = True
        db.session.commit()
        flash(f"Hid {offering.name}. Its exams are kept; import it again from Canvas to show it again.", 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"Failed to hide offering {offering.name} (Canvas ID: {offering.canvas_id}) due to an error:\n{e}", 'error')
    return redirect(url_for('views.offerings'))


# endregion

# region Exam CRUDI


@bp.route("/<offering:offering>/exams/new/", methods=["GET", "POST"])
def new_exam(offering):
    """
    Path: /offerings/<canvas_id>/exams/new
    Creates a new exam for a course offering.
    """
    # offering urls convertor lets the course's students in too: check staff status here
    if str(offering.canvas_id) not in current_user.staff_offerings:
        abort(403, "You are not a staff member in this offering.")
    form = ExamForm()
    if form.validate_on_submit():
        try:
            if form.active.data:
                # only one exam can be active at a time, so deactivate all others first
                offering.mark_all_exams_as_inactive()
            exam = Exam(offering_canvas_id=offering.canvas_id,
                        name=form.name.data,
                        display_name=form.display_name.data,
                        is_active=form.active.data)
            offering.exams.append(exam)
            if offering.ensure_one_exam_is_active():
                flash("No active exam left. The first exam is activated by default.", 'info')
            db.session.commit()
            return redirect(url_for('views.offering', offering=offering))
        except Exception as e:
            db.session.rollback()
            flash(f"An error occurred when inserting exam of name={form.name.data}\n{str(e)}", 'error')
            return redirect(url_for('views.offering', offering=offering))
    return render_template("upsert_exam.html",
                           title="Create an Exam for {}".format(offering.name),
                           form=form, exam=None)


@bp.route("/<exam:exam>/delete/", methods=["POST"])
def delete_exam(exam):
    """
    Path: /offerings/<canvas_id>/exams/<exam_name>/delete
    Deletes an exam for a course offering.
    """
    try:
        db.session.delete(exam)
        db.session.commit()
        flash("Deleted exam.", 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"Failed to delete exam {exam.display_name} (ID: {exam.id}) due to an error:\n{e}", 'error')
    return redirect(url_for('views.offering', offering=exam.offering))


@bp.route("/<exam:exam>/edit/", methods=["GET", "POST"])
def edit_exam(exam):
    """
    Path: /offerings/<canvas_id>/exams/<exam_name>/edit
    Edits an exam for a course offering.
    """
    form = EditExamForm()
    if request.method == 'GET':
        form.display_name.data = exam.display_name
        form.active.data = exam.is_active
    if form.validate_on_submit():
        if 'cancel' in request.form:
            return redirect(url_for('views.offering', offering=exam.offering))
        exam.display_name = form.display_name.data
        if form.active.data:
            exam.offering.mark_all_exams_as_inactive()
            exam.is_active = True
        else:
            exam.is_active = False
            if exam.offering.ensure_one_exam_is_active():
                flash("No active exam left. The first exam is activated by default.", 'info')
        try:
            db.session.commit()
            return redirect(url_for('views.offering', offering=exam.offering))
        except Exception as e:
            db.session.rollback()
            flash(f"Failed to edit exam name={exam.display_name} due to a db error: \n{e}", 'error')
            return redirect(url_for('views.offering', offering=exam.offering))
    return render_template("upsert_exam.html",
                           title="Edit Exam: {}".format(exam.display_name),
                           form=form, exam=exam)


@bp.route("/<exam:exam>/toggle/", methods=["POST"])
def toggle_exam(exam):
    """
    Path: /offerings/<canvas_id>/exams/<exam_name>/toggle
    Toggles an exam for a course offering.
    """
    if exam.is_active:
        exam.is_active = False
        if exam.offering.ensure_one_exam_is_active():
            flash("No active exam left. The first exam is activated by default.", 'info')
    else:
        # only one exam can be active at a time, so deactivate all others first
        exam.offering.mark_all_exams_as_inactive()
        exam.is_active = True
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f"Failed to toggle exam name={exam.display_name} due to a db error: \n{e}", 'error')
    return redirect(url_for('views.offering', offering=exam.offering))


@bp.route('/<exam:exam>/')
def exam(exam):
    """
    Path: /offerings/<canvas_id>/exams/<exam_name>
    Front page for an exam, which essentially shows all rooms created for an exam.
    """
    return render_template('exam.html', exam=exam)
# endregion

# region Room CRUDI


@bp.route('/<exam:exam>/rooms/import/')
def import_room(exam):
    """
    Path: /offerings/<canvas_id>/exams/<exam_name>/rooms/import
    """
    new_form = RoomForm()
    choose_form = ChooseRoomForm(room_list=get_spreadsheet_tabs(current_app.config.get('MASTER_ROOM_SHEET_URL')))
    upload_form = UploadRoomForm()
    return render_template('new_room.html',
                           exam=exam, new_form=new_form, choose_form=choose_form,
                           upload_form=upload_form,
                           master_sheet_url=current_app.config.get('MASTER_ROOM_SHEET_URL'))


@bp.route('/<exam:exam>/rooms/import/from_custom_sheet/', methods=['GET', 'POST'])
def import_room_from_custom_sheet(exam):
    """
    Path: /offerings/<canvas_id>/exams/<exam_name>/rooms/import/new
    """
    new_form = RoomForm()
    choose_form = ChooseRoomForm()
    upload_form = UploadRoomForm()
    room = None
    if new_form.validate_on_submit():
        try:
            room = get_room_from_google_spreadsheet(exam, new_form)
        except Exception as e:
            flash(f"Failed to import room due to an unexpected error: {e}", 'error')
        if new_form.create_room.data:
            try:
                db.session.add(room)
                db.session.commit()
            except Exception as e:
                flash(f"Failed to import room due to an db error: {e}", 'error')
            return redirect(url_for('views.exam', exam=exam))
    for field, errors in new_form.errors.items():
        for error in errors:
            flash("{}: {}".format(field, error), 'error')
    return render_template('new_room.html',
                           exam=exam,
                           new_form=new_form, choose_form=choose_form,
                           upload_form=upload_form,
                           room=room,
                           master_sheet_url=current_app.config.get('MASTER_ROOM_SHEET_URL'))


@bp.route('/<exam:exam>/rooms/import/from_master_sheet/', methods=['GET', 'POST'])
def import_room_from_master_sheet(exam):
    """
    Path: /offerings/<canvas_id>/exams/<exam_name>/rooms/import/choose
    """
    new_form = RoomForm()
    choose_form = ChooseRoomForm(room_list=get_spreadsheet_tabs(current_app.config.get('MASTER_ROOM_SHEET_URL')))
    upload_form = UploadRoomForm()
    if choose_form.validate_on_submit():
        for r in choose_form.rooms.data:
            f = RoomForm(
                display_name=r,
                sheet_url=current_app.config.get("MASTER_ROOM_SHEET_URL"),
                sheet_range=r)
            room = None
            try:
                room = get_room_from_google_spreadsheet(exam, f)
            except Exception as e:
                flash(f"Failed to import room due to an unexpected error: {e}", 'error')
            if room:
                try:
                    db.session.add(room)
                    db.session.commit()
                except Exception as e:
                    flash(f"Failed to import room due to an db error: {e}", 'error')
        return redirect(url_for('views.exam', exam=exam))
    for field, errors in choose_form.errors.items():
        for error in errors:
            flash("{}: {}".format(field, error), 'error')
    return render_template('new_room.html',
                           exam=exam,
                           new_form=new_form, choose_form=choose_form,
                           upload_form=upload_form,
                           master_sheet_url=current_app.config.get('MASTER_ROOM_SHEET_URL'))


@bp.route('/<exam:exam>/rooms/import/from_csv_upload/', methods=['GET', 'POST'])
def import_room_from_csv_upload(exam):
    new_form = RoomForm()
    choose_form = ChooseRoomForm()
    upload_form = UploadRoomForm()
    if upload_form.validate_on_submit():
        room = None
        if upload_form.file.data:
            try:
                room = get_room_from_csv(exam, upload_form)
            except Exception as e:
                flash(f"Failed to import room due to an unexpected error: {e}", 'error')
        else:
            flash("No file uploaded!", 'error')
        if room:
            try:
                db.session.add(room)
                db.session.commit()
            except Exception as e:
                flash(f"Failed to import room due to a db error: {e}", 'error')
        return redirect(url_for('views.exam', exam=exam))
    for field, errors in upload_form.errors.items():
        for error in errors:
            flash("{}: {}".format(field, error), 'error')
    return render_template('new_room.html',
                           exam=exam,
                           new_form=new_form, choose_form=choose_form,
                           upload_form=upload_form,
                           master_sheet_url=current_app.config.get('MASTER_ROOM_SHEET_URL'))


@bp.route('/<exam:exam>/rooms/import/from_manual/', methods=['GET', 'POST'])
def import_room_manually(exam):  # noqa: C901
    form = EditRoomForm()
    if request.method == 'GET':
        if not form.movable_seats.entries:
            form.movable_seats.append_entry({
                'attributes': '',
                'count': 1
            })
    if form.validate_on_submit():
        from collections import defaultdict
        seats_to_add = defaultdict(int)
        for seat_form in form.movable_seats.data:
            seats_to_add[frozenset(str_set_to_set(seat_form['attributes']))] += max(0, seat_form['count'])
        room = None
        try:
            room = get_room_from_manual_input(exam, form, seats_to_add)
        except Exception as e:
            flash(f"Failed to import room due to an unexpected error: {e}", 'error')
        if room:
            try:
                db.session.add(room)
                db.session.commit()
            except Exception as e:
                flash(f"Failed to import room due to a db error: {e}", 'error')
        return redirect(url_for('views.exam', exam=exam))
    for field, errors in form.errors.items():
        for error in errors:
            flash("{}: {}".format(field, error), 'error')
    return render_template('upsert_room.html', exam=exam, form=form, room=None)


@bp.route('/<exam:exam>/rooms/<int:id>/delete', methods=['POST'])
def delete_room(exam, id):
    """
    Path: /offerings/<canvas_id>/exams/<exam_name>/rooms/<room_name>/delete
    Deletes a room for an exam.
    """
    room = Room.query.filter_by(exam_id=exam.id, id=id).first_or_404()
    try:
        # students may still reference this room in their wants/avoids
        exam.remove_room_preferences(room.id)
        db.session.delete(room)
        db.session.commit()
        flash("Deleted room.", 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"Failed to delete room {room.display_name} (ID: {room.id}) due to an error:\n{e}", 'error')
    return redirect(url_for('views.exam', exam=exam))


@bp.route('/<exam:exam>/rooms/<int:id>/edit', methods=['GET', 'POST'])
def edit_room(exam, id):  # noqa: C901
    """
    Path: /offerings/<canvas_id>/exams/<exam_name>/rooms/<room_name>/edit
    Edits a room for an exam.
    """
    room = Room.query.filter_by(exam_id=exam.id, id=id).first_or_404()
    form = EditRoomForm()
    if request.method == 'GET':
        form.display_name.data = room.display_name
        if room.start_at:
            form.start_at.data = room.start_at_time
        if room.duration_minutes:
            form.duration_minutes.data = room.duration_minutes
        for attr in room.movable_seats_by_attribute:
            form.movable_seats.append_entry({
                'attributes': set_to_str(attr),
                'count': len(room.movable_seats_by_attribute[attr])
            })
        if not form.movable_seats.entries:
            form.movable_seats.append_entry({
                'attributes': '',
                'count': 0
            })
    if form.validate_on_submit():
        if 'cancel' in request.form:
            return redirect(url_for('views.exam', exam=exam))
        # update other stuff
        room.display_name = form.display_name.data
        start_at_iso = None
        if form.start_at.data:
            start_at_iso = to_ISO8601(form.start_at.data)
        room.start_at = start_at_iso
        room.duration_minutes = form.duration_minutes.data
        # update movable seats
        from collections import defaultdict
        seats_to_add = defaultdict(int)
        for seat_form in form.movable_seats.data:
            seats_to_add[frozenset(str_set_to_set(seat_form['attributes']))] += max(0, seat_form['count'])
        try:
            update_room_from_manual_input(room, seats_to_add)
        except Exception as e:
            flash(f"Failed to edit room seats due to an unexpected error: {e}", 'error')
        try:
            db.session.commit()
        except Exception as e:
            flash(f"Failed to edit room due to a db error: {e}", 'error')
        return redirect(url_for('views.exam', exam=exam))
    return render_template('upsert_room.html', exam=exam, form=form, room=room)


@bp.route('/<exam:exam>/rooms/<int:id>/')
def room(exam, id):
    """
    Path: /offerings/<canvas_id>/exams/<exam_name>/rooms/<room_name>
    Displays the room diagram, with an optional seat highlighted.
    """
    # fetch all seat assignment at this point too to avoid N+1 problem
    # we will need to display the seat assignment in the room diagram
    room = Room.query.options(
        joinedload(Room.seats).joinedload(Seat.assignment).joinedload(SeatAssignment.student)
    ).filter_by(exam_id=exam.id, id=id).first_or_404()
    # seat ids are ints: as a string, the seat to highlight never matched any seat
    seat_id = request.args.get('seat', type=int)
    # this page is staff only (the exam converter sends students to their own seat), so the
    # proctor view, which shows the room from the front, is never offered to students
    proctor = request.args.get('view') == 'proctor'
    return render_template('room.html', exam=exam, room=room, seat_id=seat_id, proctor=proctor)
# endregion

# region Student CRUDI


def _save_student_import(exam, prepared, roster_sids):
    """
    Saves what a student import prepared, and says what it did: who was added, updated and
    removed, and which rows were skipped and why.

    roster_sids are the student ids on the course's Canvas roster now, by Canvas id, or None if
    Canvas couldn't give them: every student of the exam gets theirs as their canvas_sid, which their
    photo is fetched by, and a student no longer on the roster loses it.
    """
    new_students, updated_students, invalid_students, students_ids_to_remove = prepared
    removed_students = Student.query.filter(Student.id.in_(students_ids_to_remove), Student.exam_id == exam.id) \
        .order_by(Student.name).all() if students_ids_to_remove else []
    # one by one rather than in a single DELETE, so that their seat assignments go with them
    for student in removed_students:
        db.session.delete(student)
    if roster_sids is not None:
        # the imported students first, so the query (which flushes them) doesn't update them twice
        for student in new_students + updated_students:
            student.canvas_sid = roster_sids.get(str(student.canvas_id))
        for student in Student.query.filter_by(exam_id=exam.id):
            student.canvas_sid = roster_sids.get(str(student.canvas_id))
    db.session.add_all(new_students + updated_students)
    db.session.commit()
    flash(
        f"Import done. {len(new_students)} new students, {len(updated_students)} updated students"
        f" {len(invalid_students)} invalid students. {len(removed_students)} students removed.", 'success')
    if removed_students:
        flash(f"Removed students not in the import: {', '.join(student.name for student in removed_students)}",
              'warning')
    if updated_students:
        flash(f"Updated students: {set_to_str([s.name for s in updated_students])}", 'warning')
    if invalid_students:
        flash(describe_invalid_rows(invalid_students), 'error')


def _render_import_students(exam, form, from_canvas_form):
    for field, errors in list(form.errors.items()) + list(from_canvas_form.errors.items()):
        for error in errors:
            flash("{}: {}".format(field, error), 'error')
    return render_template('new_students.html', exam=exam, form=form)


@bp.route('/<exam:exam>/students/import/', methods=['GET', 'POST'])
def import_students(exam):
    """
    Imports students from a file, pasted text or a Google Sheets link. The same form's other button
    imports the Canvas roster instead (import_students_from_canvas_roster), with the same options.
    """
    form = ImportStudentsForm()
    from_canvas_form = ImportStudentFromCanvasRosterForm()
    if form.validate_on_submit():
        try:
            prepared = get_students_from_import_form(exam, form)
            _save_student_import(exam, prepared, canvas_client.fetch_roster_student_ids(exam.offering_canvas_id))
        except DataValidationError as e:
            flash(str(e), 'error')
            return _render_import_students(exam, form, from_canvas_form)
        except Exception as e:
            flash(f"Failed to import students due to an unexpected error: {str(e)}", 'error')
        return redirect(url_for('views.students', exam=exam))
    return _render_import_students(exam, form, from_canvas_form)


@bp.route('/<exam:exam>/students/import/from_canvas_roster/', methods=['GET', 'POST'])
def import_students_from_canvas_roster(exam):
    form = ImportStudentsForm()
    from_canvas_form = ImportStudentFromCanvasRosterForm()
    if from_canvas_form.validate_on_submit():
        try:
            _save_student_import(exam, *get_students_from_canvas(exam, from_canvas_form))
        except HTTPException:
            # e.g. the redirect to sign in again once the Canvas token has expired
            raise
        except Exception as e:
            flash(f"Failed to import students due to an unexpected error: {str(e)}", 'error')
        return redirect(url_for('views.students', exam=exam))
    return _render_import_students(exam, form, from_canvas_form)


@bp.route('/<exam:exam>/students/delete/', methods=['GET', 'POST'])
def delete_students(exam):
    form = DeleteStudentForm()
    deleted, did_not_exist = set(), set()
    if form.validate_on_submit():
        if not form.use_all_emails.data:
            emails = [x for x in str_set_to_set(form.emails.data) if x]
            students = Student.query.filter(
                Student.email.in_(emails) & (Student.exam_id == exam.id))
        else:
            students = Student.query.filter_by(exam_id=exam.id)
        deleted = {student.email for student in students}
        did_not_exist = set()
        if not form.use_all_emails.data:
            did_not_exist = set(emails) - deleted
        students.delete(synchronize_session=False)
        db.session.commit()
        if not deleted and not did_not_exist:
            abort(404, "No change has been made.")
    return render_template('delete_students.html',
                           exam=exam, form=form, deleted=deleted, did_not_exist=did_not_exist)


@bp.route('/<exam:exam>/students/')
def students(exam):
    students_list = exam.get_students(with_seat=True)
    students_with_deleted_rooms = sum(
        1 for student in students_list if student.unknown_room_wants or student.unknown_room_avoids)
    return render_template('students.html', exam=exam, students=students_list,
                           students_with_deleted_rooms=students_with_deleted_rooms,
                           remove_deleted_rooms_form=RemoveDeletedRoomPreferencesForm())


@bp.route('/<exam:exam>/students/remove_deleted_rooms/', methods=['POST'])
def remove_deleted_room_preferences(exam):
    """
    Removes ids of deleted rooms from every student's room wants/avoids in this exam.
    """
    form = RemoveDeletedRoomPreferencesForm()
    if form.validate_on_submit():
        changed = exam.remove_unknown_room_preferences()
        db.session.commit()
        flash(f"Removed deleted rooms from the preferences of {changed} students.", 'success')
    else:
        flash("Failed to remove deleted rooms: the form expired, please try again.", 'error')
    return redirect(url_for('views.students', exam=exam))


@bp.route('/<exam:exam>/students/export/csv')
def export_students_as_csv(exam):
    from datetime import datetime
    file_content = export_exam_student_info(exam)
    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    file_name = f"{exam.name}_students_{timestamp}.csv"
    return Response(
        file_content,
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename={file_name}"}
    )


@bp.route('/<exam_student:exam_student>/edit', methods=['GET', 'POST'])
def edit_student(exam_student):
    exam, student = exam_student
    form = EditStudentForm(room_list=exam.rooms)
    edited, did_not_exist = set(), set()
    orig_wants_set = set(student.wants)
    orig_avoids_set = set(student.avoids)
    orig_room_wants_set = set(student.room_wants)
    orig_room_avoids_set = set(student.room_avoids)
    if request.method == 'GET':
        form.wants.data = set_to_str(orig_wants_set)
        form.avoids.data = set_to_str(orig_avoids_set)
        form.room_wants.data = set_to_str(orig_room_wants_set)
        form.room_avoids.data = set_to_str(orig_room_avoids_set)
        form.new_email.data = student.email
    if form.validate_on_submit():
        if 'cancel' in request.form:
            return redirect(url_for('views.students', exam=exam))
        new_wants_set = str_set_to_set(form.wants.data)
        new_avoids_set = str_set_to_set(form.avoids.data)
        new_room_wants_set = set(form.room_wants.data)
        new_room_avoids_set = set(form.room_avoids.data)
        # wants and avoids should not overlap
        if not new_wants_set.isdisjoint(new_avoids_set) \
                or not new_room_wants_set.isdisjoint(new_room_avoids_set):
            flash(
                "Wants and avoids should not overlap.\n"
                f"Want: {new_wants_set}\nAvoid: {new_avoids_set}\n"
                f"Room Want: {new_room_wants_set}\nRoom Avoid: {new_room_avoids_set}", 'error')
            # the single- and multi-student edit pages share one template (edit_student.html is long gone)
            return render_template('edit_students.html', exam=exam, form=form, edited=edited,
                                   did_not_exist=did_not_exist, student=student)
        student.wants = new_wants_set
        student.avoids = new_avoids_set
        student.room_wants = new_room_wants_set
        student.room_avoids = new_room_avoids_set
        # if wants or avoids changed, delete original assignment
        # we need to compare sets because order does not matter
        if orig_wants_set != new_wants_set \
                or orig_avoids_set != new_avoids_set \
                or orig_room_wants_set != new_room_wants_set \
                or orig_room_avoids_set != new_room_avoids_set:
            if student.assignment:
                db.session.delete(student.assignment)
        student.email = form.new_email.data
        db.session.commit()
        return redirect(url_for('views.students', exam=exam))
    for field, errors in form.errors.items():
        for error in errors:
            flash("{}: {}".format(field, error), 'error')
    return render_template('edit_students.html', exam=exam, form=form, edited=edited,
                           did_not_exist=did_not_exist, student=student)


@bp.route('/<exam:exam>/students/edit', methods=['GET', 'POST'])
def edit_students(exam):  # noqa: C901
    form = EditStudentsForm(room_list=exam.rooms)
    edited, did_not_exist = set(), set()
    if form.validate_on_submit():
        if 'cancel' in request.form:
            return redirect(url_for('views.students', exam=exam))
        if not form.use_all_emails.data:
            emails = list(str_set_to_set(form.emails.data))
            students_query = Student.query.filter(
                Student.email.in_(emails) & (Student.exam_id == exam.id))
        else:
            students_query = Student.query.filter_by(exam_id=exam.id)
        students = students_query.options(joinedload(Student.assignment)).all()
        edited = {student.email for student in students}
        did_not_exist = set()
        if not form.use_all_emails.data:
            did_not_exist = set(emails) - edited
        if not edited and not did_not_exist:
            abort(404, "No change has been made.")
        for student in students:
            new_wants_set = str_set_to_set(form.wants.data)
            new_avoids_set = str_set_to_set(form.avoids.data)
            new_room_wants_set = set(form.room_wants.data)
            new_room_avoids_set = set(form.room_avoids.data)
            # wants and avoids should not overlap
            if not new_wants_set.isdisjoint(new_avoids_set) \
                    or not new_room_wants_set.isdisjoint(new_room_avoids_set):
                flash(
                    "Wants and avoids should not overlap.\n"
                    f"Want: {new_wants_set}\nAvoid: {new_avoids_set}\n"
                    f"Room Want: {new_room_wants_set}\nRoom Avoid: {new_room_avoids_set}", 'error')
                return render_template('edit_students.html', exam=exam, form=form)
            orig_wants_set = set(student.wants)
            orig_avoids_set = set(student.avoids)
            orig_room_wants_set = set(student.room_wants)
            orig_room_avoids_set = set(student.room_avoids)
            student.wants = new_wants_set
            student.avoids = new_avoids_set
            student.room_wants = new_room_wants_set
            student.room_avoids = new_room_avoids_set
            # if wants or avoids changed, delete original assignment
            # we need to compare sets because order does not matter
            if orig_wants_set != new_wants_set \
                    or orig_avoids_set != new_avoids_set \
                    or orig_room_wants_set != new_room_wants_set \
                    or orig_room_avoids_set != new_room_avoids_set:
                if student.assignment:
                    db.session.delete(student.assignment)
        db.session.commit()
        # return redirect(url_for('views.students', exam=exam))
    for field, errors in form.errors.items():
        for error in errors:
            flash("{}: {}".format(field, error), 'error')
    return render_template('edit_students.html', exam=exam, form=form, edited=edited,
                           did_not_exist=did_not_exist, student=None)


@bp.route('/<exam_student:exam_student>/delete', methods=['POST'])
def delete_student(exam_student):
    exam, student = exam_student
    if student:
        try:
            db.session.delete(student)
            db.session.commit()
            flash("Deleted student.", 'success')
        except Exception as e:
            db.session.rollback()
            flash(f"Failed to delete student {student.name}"
                  f"(Canvas id: {student.canvas_id}) due to an error:\n{str(e)}", 'error')
    return redirect(url_for('views.students', exam=exam))


@bp.route('/<exam:exam>/students/assign/', methods=['GET', 'POST'])
def assign(exam):
    form = AssignForm()
    if form.validate_on_submit():
        def delete_all_assignments_no_sync(e):
            # single DELETE ... WHERE seat_id IN (SELECT ...); no need to load every seat first
            exam_seat_ids = select(Seat.id).join(Room, Seat.room_id == Room.id).where(Room.exam_id == e.id)
            SeatAssignment.query.filter(SeatAssignment.seat_id.in_(exam_seat_ids)).delete(synchronize_session=False)
            db.session.commit()
        if 'delete_all' in request.form:
            delete_all_assignments_no_sync(exam)
            flash("Successfully deleted all assignments.", 'success')
            return redirect(url_for('views.students', exam=exam))
        elif 'reassign_all' in request.form:
            delete_all_assignments_no_sync(exam)
        try:
            assignments = assign_students(exam)
            db.session.add_all(assignments)
            db.session.commit()
            flash(f"Successfully assigned {len(assignments)} students.", 'success')
        except SeatAssignmentError as e:
            flash(str(e), 'error')
        return redirect(url_for('views.students', exam=exam))
    return render_template('assign.html', exam=exam, form=form)


@bp.route('/<exam_student:exam_student>/assign/', methods=['GET', 'POST'])
def assign_student(exam_student):
    form = AssignSingleForm()
    exam, student = exam_student
    if form.validate_on_submit():
        try:
            if 'just_delete' in request.form:
                if student.assignment:
                    db.session.delete(student.assignment)
                    db.session.commit()
                    flash(f"Successfully deleted assignment for {student.name}.", 'success')
                else:
                    flash(f"No assignment to delete for {student.name}.", 'warning')
                return redirect(url_for('views.students', exam=exam))
            chosen_seat = Seat.query.filter_by(id=form.seat_id.data).first_or_404() if form.seat_id.data != "" else None
            old_assignment = None
            if student.assignment:
                old_assignment = student.assignment
            assignment = assign_single_student(exam, student, chosen_seat, ignore_restrictions=form.ignore_restrictions.data)
            if old_assignment:
                db.session.delete(old_assignment)
            db.session.add(assignment)
            db.session.commit()
            flash(f"Successfully assigned {student.name}.", 'success')
        except SeatAssignmentError as e:
            flash(str(e), 'error')
        return redirect(url_for('views.students', exam=exam))
    # The page draws every room with every seat's occupant, so load all of it up front
    # instead of one query per seat (assignment) plus one per occupied seat (student).
    rooms = Room.query.filter_by(exam_id=exam.id).options(
        joinedload(Room.seats).joinedload(Seat.assignment).joinedload(SeatAssignment.student)
    ).order_by(Room.start_at.desc(), Room.display_name.desc()).all()
    return render_template('assign_single.html', exam=exam, rooms=rooms, form=form)


def _email_form(exam, form_class=None):
    """The email form, with the seated students offered for a preview or a test email."""
    form = (form_class or EmailForm)()
    form.test_student.choices = [
        (student.id, f'{student.name} ({student.assignment.seat.room.display_name} {student.assignment.seat.display_name})')
        for student in exam.get_students(with_seat=True) if student.assignment]
    return form


def _send_test_email(exam, form, **page):
    """
    Handles the "send test" button of the email pages, then shows the page again with the
    subject and body as they were, so staff can keep editing and send for real.
    """
    if not form.test_to_addr.data:
        flash("Enter the address to send the test email to.", 'error')
    else:
        student = Student.query.filter_by(id=form.test_student.data, exam_id=exam.id).one_or_none()
        if not student or not student.assignment:
            flash("Pick a student with a seat to fill in the test email.", 'error')
        elif send_test_email(exam, form, student, form.test_to_addr.data):
            flash(f"Sent a test email to {form.test_to_addr.data}, filled in with {student.name}'s seat.", 'success')
        else:
            flash("Failed to send the test email.", 'error')
    return _render_email_page(exam, form, **page)


def _render_email_page(exam, form, **page):
    return render_template('email.html', exam=exam, form=form, variables=VARIABLES,
                           preview_url=url_for('views.email_preview', exam=exam), **page)


def _prefill_email(exam, form):
    """
    The assignment email to start from: the subject shows the exam's name, and the body keeps its
    variables, which are filled in for each student when sending.
    """
    email_prefill = get_email(EmailTemplate.ASSIGNMENT_INFORM_EMAIL)
    form.subject.data = make_substitutions(email_prefill.subject, {'EXAM': exam.display_name})
    form.body.data = email_prefill.body


@bp.route('/<exam:exam>/students/email/preview/', methods=['POST'])
def email_preview(exam):
    """
    The email one student would get, filled in from the email page's subject and body, as JSON:
    the page shows it, so staff see the real email rather than the text they typed.
    """
    form = _email_form(exam, EmailPreviewForm)
    if not form.validate_on_submit():
        return jsonify(errors=form.errors), 400
    student = Student.query.filter_by(id=form.test_student.data, exam_id=exam.id).one_or_none()
    subject, body, body_html = substitute_about_assignment(exam, form, student)
    if not subject:
        return jsonify(errors={'test_student': ['Pick a student with a seat to preview the email with.']}), 400
    return jsonify(subject=subject, text=body, html=body_html)


def _flash_form_errors(form):
    for field, errors in form.errors.items():
        for error in errors:
            flash("{}: {}".format(field, error), 'error')


def _has_email_recipients(form):
    """Require recipients for a real send, but not for a test email."""
    if form.to_addr.data and form.to_addr.data.strip():
        return True
    form.to_addr.errors.append('This field is required.')
    return False


@bp.route('/<exam:exam>/students/email/', methods=['GET', 'POST'])
def email_all_students(exam):
    form = _email_form(exam)
    # the page sends to the students in batches, through this url (see email_students_batch)
    page = {'batch_url': url_for('views.email_students_batch', exam=exam)}
    if form.validate_on_submit():
        if form.send_test.data:
            return _send_test_email(exam, form, **page)
        if not _has_email_recipients(form):
            _flash_form_errors(form)
            return _render_email_page(exam, form, **page)
        successful_emails, failed_emails = email_about_assignment(exam, form, form.to_addr.data)
        if successful_emails:
            flash(f"Successfully emailed {len(successful_emails)} students.", 'success')
        if failed_emails:
            flash(f"Failed to email students: {set_to_str(failed_emails)}", 'error')
        if not successful_emails and not failed_emails:
            flash("No email sent.", 'warning')
        return redirect(url_for('views.students', exam=exam))
    elif form.is_submitted():
        # keep what was typed, rather than starting over from the template
        _flash_form_errors(form)
    else:
        _prefill_email(exam, form)
        # only students with a seat have anything to be told; leave out those already emailed, so that
        # after a send that stopped partway the page picks up with the rest
        include_emailed = request.args.get('include_emailed') == '1'
        students = exam.get_students(with_seat=True)
        seated = [student for student in students if student.assignment]
        form.to_addr.data = set_to_str(
            [student.email for student in seated if include_emailed or not student.assignment.emailed])
        page['recipients'] = {
            'include_emailed': include_emailed,
            'already_emailed': sum(1 for student in seated if student.assignment.emailed),
            'unseated': len(students) - len(seated),
        }
    return _render_email_page(exam, form, **page)


@bp.route('/<exam:exam>/students/email/send/', methods=['POST'])
def email_students_batch(exam):
    """
    Emails the students in `to_addr` and returns who was emailed, as JSON. The email page sends a
    class in several of these, a batch of students each, so that no request runs into a server
    timeout however large the class is.
    """
    form = _email_form(exam)
    if not form.validate_on_submit():
        return jsonify(errors=form.errors), 400
    if not _has_email_recipients(form):
        return jsonify(errors={'to_addr': form.to_addr.errors}), 400
    successful_emails, failed_emails = email_about_assignment(exam, form, form.to_addr.data)
    return jsonify(sent=sorted(successful_emails), failed=sorted(failed_emails))


@bp.route('/<exam_student:exam_student>/email/', methods=['GET', 'POST'])
def email_single_student(exam_student):
    exam, student = exam_student
    form = _email_form(exam)
    if form.validate_on_submit():
        if form.send_test.data:
            return _send_test_email(exam, form)
        if not _has_email_recipients(form):
            _flash_form_errors(form)
            return _render_email_page(exam, form)
        successful_emails, failed_emails = email_about_assignment(exam, form, form.to_addr.data)
        if successful_emails:
            flash(f"Successfully emailed {len(successful_emails)} students.", 'success')
        if failed_emails:
            flash(f"Failed to email students: {set_to_str(failed_emails)}", 'error')
        if not successful_emails and not failed_emails:
            flash("No email sent.", 'warning')
        return redirect(url_for('views.students', exam=exam))
    elif form.is_submitted():
        _flash_form_errors(form)
    else:
        _prefill_email(exam, form)
        form.to_addr.data = student.email
        form.test_student.data = student.id
    return _render_email_page(exam, form)


@bp.route('/<exam_student:exam_student>', methods=['GET'])
def student(exam_student):
    exam, student = exam_student
    return render_template('student.html', exam=exam, student=student)


@bp.route('/<exam_student:exam_student>/photo/', methods=['GET'])
def student_photo(exam_student):
    """
    The student's Cal1Card photo, by the student id Canvas has for them (canvas_sid): their sid came
    from an import, which could name anyone. Without one, they weren't on the course's Canvas roster
    at the last import: look again, so a student who has joined since gets their photo.
    """
    exam, student = exam_student
    sid = student.canvas_sid
    if not sid:
        sid = canvas_client.get_roster_student_ids(exam.offering_canvas_id).get(str(student.canvas_id))
        if sid:
            student.canvas_sid = sid
            db.session.commit()
    if sid:
        from server.cache import cache_store, cache_key_photo, cache_life_photo
        import io
        photo = cache_store.get(cache_key_photo(sid))
        if photo is not None:
            return send_file(io.BytesIO(photo), mimetype='image/jpeg')
        from server.services.c1c import get_c1c_client
        photo = get_c1c_client().get_student_photo(sid)
        if photo is not None:
            cache_store.set(cache_key_photo(sid), photo, timeout=cache_life_photo())
            return send_file(io.BytesIO(photo), mimetype='image/jpeg')
    return send_file('static/img/photo-placeholder.png', mimetype='image/png')

# endregion

# region Misc


@bp.app_context_processor
def inject_env_vars():
    return dict(wiki_base_url=current_app.config.get('WIKI_BASE_URL'))


@bp.route('/favicon.ico')
def favicon():
    return send_file('static/img/favicon.ico')


@bp.route('/students-template.png')
def students_template():
    return send_file('static/img/students-template.png')
# endregion

# region Layout preview


@bp.route('/layouts/preview/', methods=['GET', 'POST'])
@login_required
def preview_layout():
    """
    Path: /layouts/preview
    A scratchpad for seating layouts: upload (or paste) the same room CSV the
    import flow accepts, look at the resulting layout, highlight the seats
    belonging to a layout or attribute, and toggle seats to build a new layout.
    Nothing here touches the database.
    """
    form = PreviewLayoutForm()
    preview = None
    if form.validate_on_submit():
        try:
            if form.file.data:
                preview = get_layout_preview_from_file(form.file.data)
            else:
                preview = get_layout_preview_from_text(form.text.data)
        except Exception as e:
            flash(f"Failed to preview layout: {e}", 'error')
        if preview is not None and not preview['counts']['total']:
            flash("That file did not contain any seats.", 'warning')
            preview = None
    for field, errors in form.errors.items():
        for error in errors:
            flash("{}: {}".format(field, error), 'error')
    return render_template('preview_layout.html',
                           title="Seating Layout Preview",
                           form=form, preview=preview)
# endregion

# region Student-facing pages


@bp.route('/seats/<int:seat_id>/')
def student_single_seat(seat_id):
    seat = Seat.query.filter_by(id=seat_id).first_or_404()
    return render_template('seat.html', room=seat.room, seat=seat)
# endregion
