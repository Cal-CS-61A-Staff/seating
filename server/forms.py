import re

from flask_wtf import FlaskForm
from wtforms import FieldList, FormField, SelectField, ValidationError, BooleanField, FileField, SelectMultipleField, \
    StringField, SubmitField, TextAreaField, DateTimeField, IntegerField, widgets
from wtforms import Form as NoCsrfForm
from flask_wtf.file import FileRequired, FileAllowed
from wtforms.validators import Email, InputRequired, URL, Optional, DataRequired
from server.controllers import exam_regex
from server.services.email.templates import VARIABLES, unknown_variables
from server.typings.enum import AssignmentImportStrategy, NewRowImportStrategy, UpdatedRowImportStrategy, \
    MissingRowImportStrategy


class MultiCheckboxField(SelectMultipleField):
    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()


class ChooseCourseOfferingForm(FlaskForm):
    submit = SubmitField('import')
    offerings = MultiCheckboxField('select_offerings')

    def __init__(self, offering_list=None, *args, **kwargs):
        super(ChooseCourseOfferingForm, self).__init__(*args, **kwargs)
        if offering_list is not None:
            self.offerings.choices = [(o.canvas_id, str(o)) for o in offering_list]  # (value, label)


class ExamFormBase(FlaskForm):
    display_name = StringField('display_name', [InputRequired()], render_kw={
                               "placeholder": "Midterm 1"})
    active = BooleanField('active', default=True)

    cancel = SubmitField('cancel')


class ExamForm(ExamFormBase):
    name = StringField('name', [InputRequired()], render_kw={"placeholder": "midterm1"})
    submit = SubmitField('create')

    def validate_name(form, field):
        pattern = '^{}$'.format(exam_regex)
        if not re.match(pattern, field.data):
            raise ValidationError('Exam name must be match pattern {}'.format(pattern))


class EditExamForm(ExamFormBase):
    submit = SubmitField('make edits')


class RoomFormBase(FlaskForm):
    start_at = DateTimeField('start_at', [Optional()], format='%Y-%m-%dT%H:%M')
    duration_minutes = IntegerField('duration_minutes', [Optional()])


class RoomForm(RoomFormBase):
    display_name = StringField('display_name', [InputRequired()])
    sheet_url = StringField('sheet_url', [URL(), InputRequired()])
    sheet_range = StringField('sheet_range', [InputRequired()])
    preview_room = SubmitField('preview')
    create_room = SubmitField('create')


class ChooseRoomForm(RoomFormBase):
    submit = SubmitField('import')
    rooms = MultiCheckboxField('select_rooms')

    def __init__(self, room_list=None, *args, **kwargs):
        super(ChooseRoomForm, self).__init__(*args, **kwargs)
        if room_list is not None:
            self.rooms.choices = [(item, item) for item in room_list]  # (value, label)


class UploadRoomForm(RoomFormBase):
    submit = SubmitField('upload')
    file = FileField('Choose File', validators=[
        FileRequired(),
        FileAllowed(['csv'], 'CSV files only!')
    ])
    display_name = StringField('display_name', [InputRequired()])


class PreviewLayoutForm(FlaskForm):
    """Upload or paste a room spreadsheet just to look at it - nothing is saved."""
    file = FileField('Choose File', validators=[
        FileAllowed(['csv', 'tsv', 'txt'], 'CSV or TSV files only!')
    ])
    text = TextAreaField('text', render_kw={
        "placeholder": "row,seat,lefty,righty,broken\nA,1,TRUE,,\nA,2,,TRUE,TRUE\n..."})
    submit = SubmitField('preview layout')

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators):
            return False
        if not self.file.data and not (self.text.data or '').strip():
            self.file.errors = list(self.file.errors) + \
                ['Upload a file, or paste the rows from a spreadsheet.']
            return False
        return True


class MovableSeatSubForm(NoCsrfForm):
    attributes = StringField('attributes', default='', render_kw={"placeholder": "Righty, Aisle"})
    count = IntegerField('count', [InputRequired()], default=1, render_kw={"placeholder": "1"})


class EditRoomForm(RoomFormBase):
    display_name = StringField('display_name', [InputRequired()])
    movable_seats = FieldList(FormField(MovableSeatSubForm), min_entries=0)
    submit = SubmitField('make edits')
    cancel = SubmitField('cancel')


class ImportStudentFormBase(FlaskForm):
    revalidate_existing_assignments = BooleanField('revalidate_existing_assignments', default=True)
    assignment_import_strategy = SelectField('assignment_import_strategy', choices=[
        (AssignmentImportStrategy.REVALIDATE.value, "Use seat if it fits the student's preferences"),
        (AssignmentImportStrategy.FORCE.value, "Always use imported seat, even if it doesn't fit"),
        (AssignmentImportStrategy.IGNORE.value, "Ignore it")],
        default=AssignmentImportStrategy.REVALIDATE.value,
        validators=[DataRequired()])
    updated_student_info_import_strategy = SelectField('updated_student_info_import_strategy', choices=[
        (UpdatedRowImportStrategy.MERGE.value, "Merge with the import, skipping blanks from the import"),
        (UpdatedRowImportStrategy.OVERWRITE.value, "Replace with the import, including blanks"),
        (UpdatedRowImportStrategy.IGNORE.value, "Keep as they are")],
        default=UpdatedRowImportStrategy.MERGE.value,
        validators=[DataRequired()])
    # merge by default: a Canvas roster has no preference columns, so replacing would clear them all
    updated_preference_import_strategy = SelectField('updated_preference_import_strategy', choices=[
        (UpdatedRowImportStrategy.MERGE.value, "Add the import's preferences to theirs (merge)"),
        (UpdatedRowImportStrategy.OVERWRITE.value, "Replace their preferences with the import's, blanks included (overwrite)"),
        (UpdatedRowImportStrategy.IGNORE.value, "Keep their preferences as they are (ignore)")],
        default=UpdatedRowImportStrategy.MERGE.value,
        validators=[DataRequired()])
    new_student_import_strategy = SelectField('new_student_import_strategy', choices=[
        (NewRowImportStrategy.APPEND.value, "Add them"),
        (NewRowImportStrategy.IGNORE.value, "Skip them")],
        default=NewRowImportStrategy.APPEND.value,
        validators=[DataRequired()])
    missing_student_import_strategy = SelectField('missing_student_import_strategy', choices=[
        (MissingRowImportStrategy.IGNORE.value, "Keep them"),
        (MissingRowImportStrategy.DELETE.value, "Remove them, and their seat assignment")],
        default=MissingRowImportStrategy.IGNORE.value,
        validators=[DataRequired()])
    submit = SubmitField('import')


class ImportStudentsForm(ImportStudentFormBase):
    """
    One import, from a file, pasted text or a Google Sheets link: the first of them given is used.
    Files may be CSV, TSV or Excel; pasted text comma or tab separated.
    """
    file = FileField('file', validators=[
        Optional(), FileAllowed(['csv', 'tsv', 'txt', 'xlsx'], 'Choose a CSV, TSV or Excel (.xlsx) file')])
    text = TextAreaField('text', [Optional()], render_kw={
        "placeholder": "canvas id,email,name\n123456,x@y.z,John\n..."})
    sheet_url = StringField('sheet_url', [Optional(), URL()])
    sheet_range = StringField('sheet_range', [Optional()])


class ImportStudentFromCanvasRosterForm(ImportStudentFormBase):
    pass


class EditStudentsFormBase(FlaskForm):
    wants = StringField('wants')
    avoids = StringField('avoids')
    room_wants = MultiCheckboxField('room_wants')
    room_avoids = MultiCheckboxField('room_avoids')
    submit = SubmitField('make edits')
    cancel = SubmitField('cancel')

    def __init__(self, room_list=None, *args, **kwargs):
        super(EditStudentsFormBase, self).__init__(*args, **kwargs)
        if room_list is not None:
            self.room_wants.choices = [(str(item.id), item.name_and_start_at_time_display()) for item in room_list]
            self.room_avoids.choices = [(str(item.id), item.name_and_start_at_time_display()) for item in room_list]


class EditStudentForm(EditStudentsFormBase):
    new_email = StringField('email', [Email()])

    def __init__(self, room_list=None, *args, **kwargs):
        super(EditStudentForm, self).__init__(room_list=room_list, *args, **kwargs)


class EditStudentsForm(EditStudentsFormBase):
    emails = TextAreaField('emails')
    use_all_emails = BooleanField('use_all_emails')

    def __init__(self, room_list=None, *args, **kwargs):
        super(EditStudentsForm, self).__init__(room_list=room_list, *args, **kwargs)


class DeleteStudentForm(FlaskForm):
    emails = TextAreaField('emails')
    use_all_emails = BooleanField('use_all_emails')
    submit = SubmitField('delete by emails')


class RemoveDeletedRoomPreferencesForm(FlaskForm):
    submit = SubmitField('remove deleted rooms')


class AssignForm(FlaskForm):
    submit = SubmitField('assign')
    delete_all = SubmitField('delete all assignments')
    reassign_all = SubmitField('reassign all assignments')


class AssignSingleForm(FlaskForm):
    ignore_restrictions = BooleanField('ignore restrictions')
    seat_id = StringField('seat_id')
    just_delete = SubmitField('just delete')
    submit = SubmitField('assign')


def known_variables(known):
    """Refuses a placeholder that is not a variable, like {{ROOOM}}: it would reach every student as typed."""
    def validate(form, field):
        unknown = unknown_variables(field.data, known)
        if unknown:
            raise ValidationError('{} {}; the variables are listed below the email.'.format(
                ', '.join('{{%s}}' % name for name in unknown),
                'is not a variable' if len(unknown) == 1 else 'are not variables'))
    return validate


class EmailPreviewForm(FlaskForm):
    """What the email page's preview fills in for one student."""
    subject = StringField('subject', [InputRequired(), known_variables(VARIABLES)])
    # plain text: the HTML part of the email is built from it (issue #140)
    body = TextAreaField('body', [InputRequired(), known_variables(VARIABLES)])
    # the student whose seat fills in a preview or a test email
    test_student = SelectField('test_student', coerce=int, validate_choice=False)


class EmailForm(EmailPreviewForm):
    # every email is sent from the configured sender (EMAIL_SENDER); replies go here instead, if given
    reply_to = StringField('reply_to', [Optional(), Email()],
                           filters=[lambda value: value.strip() if value else value])
    to_addr = StringField('to_addr', [Optional()])
    cc_addr = StringField('cc_addr', [])
    bcc_addr = StringField('bcc_addr', [])
    submit = SubmitField('send')
    # a test fills in the email with one student's seat and sends it to a staff member instead
    # only checked when sending a test, so a regular send works even when no student has a seat
    test_to_addr = StringField('test_to_addr', [Optional(), Email()])
    send_test = SubmitField('send test')


class DevLoginForm(FlaskForm):
    # A pasted Canvas ID usually arrives with whitespace around it.
    user_id = StringField('user_id', [InputRequired()],
                          filters=[lambda value: value.strip() if value else value],
                          render_kw={"placeholder": "123456"})
    submit = SubmitField('login')
