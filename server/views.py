import re
from flask import abort, redirect, render_template, request, send_file, url_for, flash, Response
from flask_login import current_user, login_required

from server import app
from server.models import SeatAssignment, db, Exam, Room, Seat, Student
from server.forms import EditRoomForm, ExamForm, ImportStudentFromCsvUploadForm, RoomForm, ChooseRoomForm, \
    ImportStudentFromSheetForm, ImportStudentFromCanvasRosterForm, DeleteStudentForm, AssignForm, EmailForm, \
    EditStudentForm, UploadRoomForm
from server.services.core.export import export_exam_student_info
from server.services.email.templates import get_email
from server.services.google import get_spreadsheet_tabs
import server.services.canvas as canvas_client
from server.services.email import email_about_assignment
from server.services.core.data import get_room_from_csv, get_room_from_google_spreadsheet, \
    get_students_from_canvas, get_students_from_csv, get_students_from_google_spreadsheet
from server.services.core.assign import assign_students
from server.typings.exception import SeatAssigningAlgorithmError
from server.typings.enum import EmailTemplate
from server.utils.date import to_ISO8601

# region Offering CRUDI


@app.route('/')
@login_required
def index():
    """
    Path: /
    Home page, which needs to be logged in to access.
    After logging in, fetch and present a list of course offerings.
    """
    user = canvas_client.get_user(current_user.canvas_id)
    staff_course_dics, student_course_dics, others = canvas_client.get_user_courses_categorized(
        user)
    staff_offerings = [canvas_client.api_course_to_model(c) for c in staff_course_dics]
    student_offerings = [canvas_client.api_course_to_model(c) for c in student_course_dics]
    return render_template("select_offering.html.j2",
                           title="Select a Course Offering",
                           staff_offerings=staff_offerings,
                           student_offerings=student_offerings,
                           other_offerings=others)


@app.route('/<offering:offering>/')
def offering(offering):
    """
    Path: /offerings/<canvas_id>
    Shows all exams created for a course offering.
    """
    is_staff = str(offering.canvas_id) in current_user.staff_offerings
    return render_template("select_exam.html.j2",
                           title="Select an Exam for {}".format(offering.name),
                           exams=offering.exams, offering=offering, is_staff=is_staff)

# endregion

# region Exam CRUDI


@app.route("/<offering:offering>/exams/new/", methods=["GET", "POST"])
def new_exam(offering):
    """
    Path: /offerings/<canvas_id>/exams/new
    Creates a new exam for a course offering.
    """
    # offering urls only checks login but does not check staff status
    # this is exam creation route but still handled by offering converter
    # it does need to check staff status, so we do it here
    if str(offering.canvas_id) not in current_user.staff_offerings:
        abort(403, "You are not a staff member in this offering.")
    form = ExamForm()
    if form.validate_on_submit():
        offering.mark_all_exams_as_inactive()
        try:
            exam = Exam(offering_canvas_id=offering.canvas_id,
                        name=form.name.data,
                        display_name=form.display_name.data,
                        is_active=True)
            db.session.add(exam)
            db.session.commit()
            return redirect(url_for('offering', offering=offering))
        except Exception as e:
            db.session.rollback()
            abort(400, "An error occurred when inserting exam of name={}\n{}".format(
                form.name.data, str(e)))
            return redirect(url_for('offering', offering=offering))
    return render_template("new_exam.html.j2",
                           title="Create an Exam for {}".format(offering.name),
                           form=form)


@app.route("/<exam:exam>/delete/", methods=["GET", "DELETE"])
def delete_exam(exam):
    """
    Path: /offerings/<canvas_id>/exams/<exam_name>/delete
    Deletes an exam for a course offering.
    """
    db.session.delete(exam)
    db.session.commit()
    return redirect(url_for('offering', offering=exam.offering))


@app.route("/<exam:exam>/toggle/", methods=["GET", "PATCH"])
def toggle_exam(exam):
    """
    Path: /offerings/<canvas_id>/exams/<exam_name>/toggle
    Toggles an exam for a course offering.
    """
    if exam.is_active:
        exam.is_active = False
    else:
        # only one exam can be active at a time, so deactivate all others first
        exam.offering.mark_all_exams_as_inactive()
        exam.is_active = True
    db.session.commit()
    return redirect(url_for('offering', offering=exam.offering))


@app.route('/<exam:exam>/')
def exam(exam):
    """
    Path: /offerings/<canvas_id>/exams/<exam_name>
    Front page for an exam, which essentially shows all rooms created for an exam.
    """
    return render_template('exam.html.j2', exam=exam)
# endregion

# region Room CRUDI


@app.route('/<exam:exam>/rooms/import/')
def import_room(exam):
    """
    Path: /offerings/<canvas_id>/exams/<exam_name>/rooms/import
    """
    new_form = RoomForm()
    choose_form = ChooseRoomForm(room_list=get_spreadsheet_tabs(app.config.get('MASTER_ROOM_SHEET_URL')))
    upload_form = UploadRoomForm()
    return render_template('new_room.html.j2',
                           exam=exam, new_form=new_form, choose_form=choose_form, upload_form=upload_form,
                           master_sheet_url=app.config.get('MASTER_ROOM_SHEET_URL'))


@app.route('/<exam:exam>/rooms/import/from_custom_sheet/', methods=['GET', 'POST'])
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
            return redirect(url_for('exam', exam=exam))
    for field, errors in new_form.errors.items():
        for error in errors:
            flash("{}: {}".format(field, error), 'error')
    return render_template('new_room.html.j2',
                           exam=exam,
                           new_form=new_form, choose_form=choose_form, upload_form=upload_form,
                           room=room,
                           master_sheet_url=app.config.get('MASTER_ROOM_SHEET_URL'))


@app.route('/<exam:exam>/rooms/import/from_master_sheet/', methods=['GET', 'POST'])
def import_room_from_master_sheet(exam):
    """
    Path: /offerings/<canvas_id>/exams/<exam_name>/rooms/import/choose
    """
    new_form = RoomForm()
    choose_form = ChooseRoomForm(room_list=get_spreadsheet_tabs(app.config.get('MASTER_ROOM_SHEET_URL')))
    upload_form = UploadRoomForm()
    if choose_form.validate_on_submit():
        for r in choose_form.rooms.data:
            f = RoomForm(
                display_name=r,
                sheet_url=app.config.get("MASTER_ROOM_SHEET_URL"),
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
        return redirect(url_for('exam', exam=exam))
    for field, errors in choose_form.errors.items():
        for error in errors:
            flash("{}: {}".format(field, error), 'error')
    return render_template('new_room.html.j2',
                           exam=exam,
                           new_form=new_form, choose_form=choose_form, upload_form=upload_form,
                           master_sheet_url=app.config.get('MASTER_ROOM_SHEET_URL'))


@app.route('/<exam:exam>/rooms/import/from_csv_upload/', methods=['GET', 'POST'])
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
        return redirect(url_for('exam', exam=exam))
    for field, errors in upload_form.errors.items():
        for error in errors:
            flash("{}: {}".format(field, error), 'error')
    return render_template('new_room.html.j2',
                           exam=exam,
                           new_form=new_form, choose_form=choose_form, upload_form=upload_form,
                           master_sheet_url=app.config.get('MASTER_ROOM_SHEET_URL'))


@app.route('/<exam:exam>/rooms/<int:id>/delete', methods=['GET', 'DELETE'])
def delete_room(exam, id):
    """
    Path: /offerings/<canvas_id>/exams/<exam_name>/rooms/<room_name>/delete
    Deletes a room for an exam.
    """
    room = Room.query.filter_by(exam_id=exam.id, id=id).first_or_404()
    if room:
        db.session.delete(room)
        db.session.commit()
    return render_template('exam.html.j2', exam=exam)


@app.route('/<exam:exam>/rooms/<int:id>/edit', methods=['GET', 'POST'])
def edit_room(exam, id):
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
    if form.validate_on_submit():
        if 'cancel' in request.form:
            return redirect(url_for('exam', exam=exam))
        room.display_name = form.display_name.data
        start_at_iso = None
        if form.start_at.data:
            start_at_iso = to_ISO8601(form.start_at.data)
        room.start_at = start_at_iso
        room.duration_minutes = form.duration_minutes.data
        try:
            db.session.commit()
        except Exception as e:
            flash(f"Failed to edit room due to a db error: {e}", 'error')
        return redirect(url_for('exam', exam=exam))
    return render_template('edit_room.html.j2', exam=exam, form=form, room=room)


@app.route('/<exam:exam>/rooms/<int:id>/')
def room(exam, id):
    """
    Path: /offerings/<canvas_id>/exams/<exam_name>/rooms/<room_name>
    Displays the room diagram, with an optional seat highlighted.
    """
    room = Room.query.filter_by(exam_id=exam.id, id=id).first_or_404()
    seat_id = request.args.get('seat')
    return render_template('room.html.j2', exam=exam, room=room, seat_id=seat_id)
# endregion

# region Student CRUDI


@app.route('/<exam:exam>/students/import/')
def import_students(exam):
    from_sheet_form = ImportStudentFromSheetForm()
    from_canvas_form = ImportStudentFromCanvasRosterForm()
    from_csv_form = ImportStudentFromCsvUploadForm()
    return render_template('new_students.html.j2', exam=exam,
                           from_sheet_form=from_sheet_form,
                           from_canvas_form=from_canvas_form,
                           from_csv_form=from_csv_form)


@app.route('/<exam:exam>/students/import/from_custom_sheet/', methods=['GET', 'POST'])
def import_students_from_custom_sheet(exam):
    from_sheet_form = ImportStudentFromSheetForm()
    from_canvas_form = ImportStudentFromCanvasRosterForm()
    from_csv_form = ImportStudentFromCsvUploadForm()
    if from_sheet_form.validate_on_submit():
        try:
            new_students, updated_students, invalid_students = get_students_from_google_spreadsheet(exam, from_sheet_form)
            to_commit = new_students + updated_students
            if to_commit:
                db.session.add_all(to_commit)
                db.session.commit()
            flash(
                f"Import done. {len(new_students)} new students, {len(updated_students)} updated students"
                f" {len(invalid_students)} invalid students.", 'success')
            if updated_students:
                flash(
                    f"Updated students: {','.join([s.name for s in updated_students])}", 'warning')
            if invalid_students:
                flash(
                    f"Invalid students: {invalid_students}", 'error')
        except Exception as e:
            flash(f"Failed to import students due to an unexpected error: {str(e)}", 'error')
        return redirect(url_for('students', exam=exam))
    for field, errors in from_sheet_form.errors.items():
        for error in errors:
            flash("{}: {}".format(field, error), 'error')
    return render_template('new_students.html.j2', exam=exam,
                           from_sheet_form=from_sheet_form,
                           from_canvas_form=from_canvas_form,
                           from_csv_form=from_csv_form)


@app.route('/<exam:exam>/students/import/from_canvas_roster/', methods=['GET', 'POST'])
def import_students_from_canvas_roster(exam):
    from_sheet_form = ImportStudentFromSheetForm()
    from_canvas_form = ImportStudentFromCanvasRosterForm()
    from_csv_form = ImportStudentFromCsvUploadForm()
    if from_canvas_form.validate_on_submit():
        try:
            new_students, updated_students, invalid_students = get_students_from_canvas(exam)
            to_commit = new_students + updated_students
            if to_commit:
                db.session.add_all(to_commit)
                db.session.commit()
            flash(
                f"Import done. {len(new_students)} new students, {len(updated_students)} updated students"
                f" {len(invalid_students)} invalid students.", 'success')
            if updated_students:
                flash(
                    f"Updated students: {','.join([s.name for s in updated_students])}", 'warning')
            if invalid_students:
                flash(
                    f"Invalid students: {invalid_students}", 'error')
        except Exception as e:
            flash(f"Failed to import students due to an unexpected error: {str(e)}", 'error')
        return redirect(url_for('students', exam=exam))
    for field, errors in from_canvas_form.errors.items():
        for error in errors:
            flash("{}: {}".format(field, error), 'error')
    return render_template('new_students.html.j2', exam=exam,
                           from_sheet_form=from_sheet_form,
                           from_canvas_form=from_canvas_form,
                           from_csv_form=from_csv_form)


@app.route('/<exam:exam>/students/import/from_csv_upload/', methods=['GET', 'POST'])
def import_students_from_csv_upload(exam):
    from_sheet_form = ImportStudentFromSheetForm()
    from_canvas_form = ImportStudentFromCanvasRosterForm()
    from_csv_form = ImportStudentFromCsvUploadForm()
    if from_csv_form.validate_on_submit():
        if from_csv_form.file.data:
            try:
                new_students, updated_students, invalid_students = get_students_from_csv(exam, from_csv_form)
                to_commit = new_students + updated_students
                if to_commit:
                    db.session.add_all(to_commit)
                    db.session.commit()
                flash(
                    f"Import done. {len(new_students)} new students, {len(updated_students)} updated students"
                    f" {len(invalid_students)} invalid students.", 'success')
                if updated_students:
                    flash(
                        f"Updated students: {','.join([s.name for s in updated_students])}", 'warning')
                if invalid_students:
                    flash(
                        f"Invalid students: {invalid_students}", 'error')
            except Exception as e:
                flash(f"Failed to import students due to an unexpected error: {str(e)}", 'error')
        else:
            flash("No file uploaded!", 'error')
        return redirect(url_for('students', exam=exam))
    for field, errors in from_csv_form.errors.items():
        for error in errors:
            flash("{}: {}".format(field, error), 'error')
    return render_template('new_students.html.j2', exam=exam,
                           from_sheet_form=from_sheet_form,
                           from_canvas_form=from_canvas_form,
                           from_csv_form=from_csv_form)


@app.route('/<exam:exam>/students/delete/', methods=['GET', 'POST'])
def delete_students(exam):
    form = DeleteStudentForm()
    deleted, did_not_exist = set(), set()
    if form.validate_on_submit():
        if not form.use_all_emails.data:
            emails = [x for x in re.split(r'\s|,', form.emails.data) if x]
            students = Student.query.filter(
                Student.email.in_(emails) & Student.exam_id == exam.id)
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
    return render_template('delete_students.html.j2',
                           exam=exam, form=form, deleted=deleted, did_not_exist=did_not_exist)


@app.route('/<exam:exam>/students/')
def students(exam):
    # TODO load assignment and seat at the same time?
    return render_template('students.html.j2', exam=exam, students=exam.students)


@app.route('/<exam:exam>/students/export/csv')
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


@app.route('/<exam:exam>/students/<string:canvas_id>/')
def student(exam, canvas_id):
    student = Student.query.filter_by(
        exam_id=exam.id, canvas_id=canvas_id).first_or_404()
    return render_template('student.html.j2', exam=exam, student=student)


@app.route('/<exam:exam>/students/<string:canvas_id>/edit', methods=['GET', 'POST'])
def edit_student(exam, canvas_id):
    student = Student.query.filter_by(
        exam_id=exam.id, canvas_id=canvas_id).first_or_404()
    if not student:
        abort(404, "Student not found.")
    form = EditStudentForm(room_list=exam.rooms)
    orig_wants_set = set(student.wants)
    orig_avoids_set = set(student.avoids)
    orig_room_wants_set = set(student.room_wants)
    orig_room_avoids_set = set(student.room_avoids)
    if request.method == 'GET':
        form.wants.data = ",".join(orig_wants_set)
        form.avoids.data = ",".join(orig_avoids_set)
        form.room_wants.data = ",".join(orig_room_wants_set)
        form.room_avoids.data = ",".join(orig_room_avoids_set)
        form.email.data = student.email
    if form.validate_on_submit():
        if 'cancel' in request.form:
            return redirect(url_for('students', exam=exam))
        new_wants_set = set(re.split(r'\s|,', form.wants.data)) if form.wants.data else set()
        new_avoids_set = set(re.split(r'\s|,', form.avoids.data)) if form.avoids.data else set()
        new_room_wants_set = set(form.room_wants.data)
        new_room_avoids_set = set(form.room_avoids.data)
        # wants and avoids should not overlap
        if not new_wants_set.isdisjoint(new_avoids_set) \
                or not new_room_wants_set.isdisjoint(new_room_avoids_set):
            flash(
                "Wants and avoids should not overlap.\n"
                f"Want: {new_wants_set}\nAvoid: {new_avoids_set}\n"
                f"Room Want: {new_room_wants_set}\nRoom Avoid: {new_room_avoids_set}", 'error')
            return render_template('edit_student.html.j2', exam=exam, form=form, student=student)
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
        student.email = form.email.data
        db.session.commit()
        return redirect(url_for('students', exam=exam))
    for field, errors in form.errors.items():
        for error in errors:
            flash("{}: {}".format(field, error), 'error')
    return render_template('edit_student.html.j2', exam=exam, form=form, student=student)


@app.route('/<exam:exam>/students/<string:canvas_id>/delete', methods=['GET', 'DELETE'])
def delete_student(exam, canvas_id):
    student = Student.query.filter_by(
        exam_id=exam.id, canvas_id=canvas_id).first_or_404()
    if student:
        db.session.delete(student)
        db.session.commit()
    return redirect(url_for('students', exam=exam))


@app.route('/<exam:exam>/students/assign/', methods=['GET', 'POST'])
def assign(exam):
    form = AssignForm()
    if form.validate_on_submit():
        def delete_all_assignments_no_sync(e):
            seat_ids = {seat.id for room in e.rooms for seat in room.seats}
            SeatAssignment.query.filter(SeatAssignment.seat_id.in_(seat_ids)).delete(synchronize_session=False)
            db.session.commit()
        if 'delete_all' in request.form:
            delete_all_assignments_no_sync(exam)
            flash("Successfully deleted all assignments.", 'success')
            return redirect(url_for('students', exam=exam))
        elif 'reassign_all' in request.form:
            delete_all_assignments_no_sync(exam)
        try:
            assignments = assign_students(exam)
            db.session.add_all(assignments)
            db.session.commit()
            flash(f"Successfully assigned {len(assignments)} students.", 'success')
        except SeatAssigningAlgorithmError as e:
            flash(str(e), 'error')
        return redirect(url_for('students', exam=exam))
    return render_template('assign.html.j2', exam=exam, form=form)


@app.route('/<exam:exam>/students/email/', methods=['GET', 'POST'])
def email_all_students(exam):
    form = EmailForm()
    if form.validate_on_submit():
        successful_emails, failed_emails = email_about_assignment(exam, form, form.to_addr.data)
        if successful_emails:
            flash(f"Successfully emailed {len(successful_emails)} students.", 'success')
        if failed_emails:
            flash(f"Failed to email students: {', '.join(failed_emails)}", 'error')
        if not successful_emails and not failed_emails:
            flash("No email sent.", 'warning')
        return redirect(url_for('students', exam=exam))
    else:
        email_prefill = get_email(EmailTemplate.ASSIGNMENT_INFORM_EMAIL)
        form.subject.data = email_prefill.subject
        form.body.data = email_prefill.body
        form.to_addr.data = ','.join([s.email for s in exam.students])
    return render_template('email.html.j2', exam=exam, form=form)


@app.route('/<exam:exam>/students/email/<string:student_id>/', methods=['GET', 'POST'])
def email_single_student(exam, student_id):
    form = EmailForm()
    if form.validate_on_submit():
        successful_emails, failed_emails = email_about_assignment(exam, form, form.to_addr.data)
        if successful_emails:
            flash(f"Successfully emailed {len(successful_emails)} students.", 'success')
        if failed_emails:
            flash(f"Failed to email students: {', '.join(failed_emails)}", 'error')
        if not successful_emails and not failed_emails:
            flash("No email sent.", 'warning')
        return redirect(url_for('students', exam=exam))
    else:
        email_prefill = get_email(EmailTemplate.ASSIGNMENT_INFORM_EMAIL)
        form.subject.data = email_prefill.subject
        form.body.data = email_prefill.body
        form.to_addr.data = Student.query.get(student_id).email
    return render_template('email.html.j2', exam=exam, form=form)

# endregion

# region Misc


@app.route('/help/')
@login_required
def help():
    return render_template('help.html.j2', title="Help")


@app.route('/favicon.ico')
def favicon():
    return send_file('static/img/favicon.ico')


@app.route('/students-template.png')
def students_template():
    return send_file('static/img/students-template.png')
# endregion

# region Student-facing pages


@app.route('/seats/<int:seat_id>/')
def student_single_seat(seat_id):
    seat = Seat.query.filter_by(id=seat_id).first_or_404()
    return render_template('seat.html.j2', room=seat.room, seat=seat)
# endregion


@app.route('/<exam:exam>/students/photos/', methods=['GET', 'POST'])
def new_photos(exam):
    return render_template('new_photos.html.j2', exam=exam)


@app.route('/<exam:exam>/students/<string:email>/photo')
def photo(exam, email):
    student = Student.query.filter_by(
        exam_id=exam.id, email=email).first_or_404()
    photo_path = '{}/{}/{}.jpeg'.format(app.config['PHOTO_DIRECTORY'],
                                        exam.offering_canvas_id, student.canvas_id)
    return send_file(photo_path, mimetype='image/jpeg')
