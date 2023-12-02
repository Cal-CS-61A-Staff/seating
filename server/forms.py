import re

from flask_wtf import FlaskForm
from wtforms import BooleanField, SelectMultipleField, StringField, SubmitField, \
    TextAreaField, DateTimeField, IntegerField, ValidationError, widgets
from wtforms.validators import Email, InputRequired, URL, Optional
from server.controllers import exam_regex


class ExamForm(FlaskForm):
    display_name = StringField('display_name', [InputRequired()], render_kw={
                               "placeholder": "Midterm 1"})
    name = StringField('name', [InputRequired()], render_kw={"placeholder": "midterm1"})
    submit = SubmitField('create')

    def validate_name(form, field):
        pattern = '^{}$'.format(exam_regex)
        if not re.match(pattern, field.data):
            from wtforms.validators import ValidationError
            raise ValidationError('Exam name must be match pattern {}'.format(pattern))


class MultiCheckboxField(SelectMultipleField):
    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()


class RoomForm(FlaskForm):
    display_name = StringField('display_name', [InputRequired()])
    sheet_url = StringField('sheet_url', [URL(), InputRequired()])
    sheet_range = StringField('sheet_range', [InputRequired()])
    start_at = DateTimeField('start_at', [Optional()], format='%Y-%m-%dT%H:%M')
    duration_minutes = IntegerField('duration_minutes', [Optional()])
    preview_room = SubmitField('preview')
    create_room = SubmitField('create')


class ChooseRoomForm(FlaskForm):
    submit = SubmitField('import')
    rooms = MultiCheckboxField('select_rooms')

    def __init__(self, room_list=None, *args, **kwargs):
        super(ChooseRoomForm, self).__init__(*args, **kwargs)
        if room_list is not None:
            self.rooms.choices = [(item, item) for item in room_list]


class EditRoomForm(FlaskForm):
    display_name = StringField('display_name')
    start_at = DateTimeField('start_at', [Optional()], format='%Y-%m-%dT%H:%M')
    duration_minutes = IntegerField('duration_minutes', [Optional()])
    submit = SubmitField('make edits')
    cancel = SubmitField('cancel')


class ImportStudentFromSheetForm(FlaskForm):
    sheet_url = StringField('sheet_url', [URL()])
    sheet_range = StringField('sheet_range', [InputRequired()])
    submit = SubmitField('import')


class ImportStudentFromCanvasRosterForm(FlaskForm):
    submit = SubmitField('import')


class DeleteStudentForm(FlaskForm):
    emails = TextAreaField('emails')
    use_all_emails = BooleanField('use_all_emails')
    submit = SubmitField('delete by emails')


class EditStudentForm(FlaskForm):
    email = StringField('email', [Email()])
    wants = StringField('wants')
    avoids = StringField('avoids')
    submit = SubmitField('make edits')
    cancel = SubmitField('cancel')


class AssignForm(FlaskForm):
    submit = SubmitField('assign')


def validate_email_list(form, field):
    email_list = field.data.split(',')
    for email in email_list:
        email = email.strip()
        if not Email()(form, field):
            print(f'Invalid email address: {email}')
            raise ValidationError(f'Invalid email address: {email}')


class EmailForm(FlaskForm):
    from_addr = StringField('from_addr', [Email(), InputRequired()])
    to_addr = StringField('to_addr', [InputRequired()])
    cc_addr = StringField('cc_addr', [])
    bcc_addr = StringField('bcc_addr', [])
    subject = StringField('subject', [InputRequired()])
    body = TextAreaField('body', [InputRequired()])
    body_html = BooleanField('body_html', default=True)
    submit = SubmitField('send')


class DevLoginForm(FlaskForm):
    user_id = StringField('user_id', [InputRequired()], render_kw={"placeholder": "123456"})
    submit = SubmitField('login')
