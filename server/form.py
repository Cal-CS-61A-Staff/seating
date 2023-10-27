import re

from flask_wtf import FlaskForm
from wtforms import BooleanField, SelectMultipleField, StringField, SubmitField, \
    TextAreaField, widgets
from wtforms.validators import Email, InputRequired, URL

from server.utils.url import offering_regex, exam_regex


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
    sheet_url = StringField('sheet_url', [URL()])
    sheet_range = StringField('sheet_range', [InputRequired()])
    preview_room = SubmitField('preview')
    create_room = SubmitField('create')


class ChooseRoomForm(FlaskForm):
    rooms = MultiCheckboxField(choices=[('277 Cory', '277 Cory'),
                                        ('145 Dwinelle', '145 Dwinelle'),
                                        ('155 Dwinelle', '155 Dwinelle'),
                                        ('10 Evans', '10 Evans'),
                                        ('100 GPB', '100 GPB'),
                                        ('A1 Hearst Field Annex', 'A1 Hearst Field Annex'),
                                        ('Hearst Gym', 'Hearst Gym'),
                                        ('120 Latimer', '120 Latimer'),
                                        ('1 LeConte', '1 LeConte'),
                                        ('2 LeConte', '2 LeConte'),
                                        ('4 LeConte', '4 LeConte'),
                                        ('100 Lewis', '100 Lewis'),
                                        ('245 Li Ka Shing', '245 Li Ka Shing'),
                                        ('159 Mulford', '159 Mulford'),
                                        ('105 North Gate', '105 North Gate'),
                                        ('1 Pimentel', '1 Pimentel'),
                                        ('RSF FH', 'RSF FH'),
                                        ('306 Soda', '306 Soda'),
                                        ('2040 VLSB', '2040 VLSB'),
                                        ('2050 VLSB', '2050 VLSB'),
                                        ('2060 VLSB', '2060 VLSB'),
                                        ('150 Wheeler', '150 Wheeler'),
                                        ('222 Wheeler', '222 Wheeler')
                                        ])
    submit = SubmitField('import')


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


class AssignForm(FlaskForm):
    submit = SubmitField('assign')


class EmailForm(FlaskForm):
    from_email = StringField('from_email', [Email()])
    from_name = StringField('from_name', [InputRequired()])
    subject = StringField('subject', [InputRequired()])
    test_email = StringField('test_email')
    additional_text = TextAreaField('additional_text')
    submit = SubmitField('send')


class DevLoginForm(FlaskForm):
    login_as_yu = SubmitField('login as Yu (169 TA, 168 Student)')
    login_as_jimmy = SubmitField('login as Jimmy (169 Student, 168 TA)')
