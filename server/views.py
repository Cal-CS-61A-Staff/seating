import itertools
import re

from apiclient import discovery, errors
from flask import abort, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from werkzeug.routing import BaseConverter
from wtforms import HiddenField, StringField, SubmitField
from wtforms.validators import InputRequired, URL

from server import app
from server.auth import google_oauth, ok_oauth
from server.models import db, Exam, Room, Seat, Student, seed_exam, slug

@app.route('/')
def index():
    return redirect(url_for('exam', exam=seed_exam))

name_part = '[^/]+'

class ExamConverter(BaseConverter):
    regex = name_part + '/' + name_part + '/' + name_part + '/' + name_part

    @login_required
    def to_python(self, value):
        offering, name = value.rsplit('/', 1)
        if offering not in current_user.offerings:
            abort(404)
        exam = Exam.query.filter_by(offering=offering, name=name).first_or_404()
        return exam

    def to_url(self, exam):
        return exam.offering + '/' + exam.name

app.url_map.converters['exam'] = ExamConverter

@app.route('/<exam:exam>/')
@login_required
def exam(exam):
    return render_template('exam.html.j2', exam=exam)

class ValidationError(Exception):
    pass

class RoomForm(FlaskForm):
    display_name = StringField('display_name', [InputRequired()])
    sheet_url = StringField('sheet_url', [URL()])
    sheet_range = StringField('sheet_range', [InputRequired()])
    preview_room = SubmitField('preview_room')
    create_room = SubmitField('create_room')

def read_csv(sheet_url, sheet_range):
    m = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', sheet_url)
    if not m:
        raise ValidationError('Enter a Google Sheets URL')
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
        raise ValidationError(e._get_reason())
    values = result.get('values', [])

    if not values:
        raise ValidationError('Sheet is empty')
    headers = [h.lower() for h in values[0]]
    rows = [
        {k: v for k, v in itertools.zip_longest(headers, row, fillvalue='')}
        for row in values[1:]
    ]
    if len(set(headers)) != len(headers):
        raise ValidationError('Headers must be unique')
    elif not all(re.match(r'[a-z0-9]+', h) for h in headers):
        raise ValidationError('Headers must consist of digits and numbers')
    return headers, rows

def validate_room(exam, room_form):
    room = Room(
        exam_id=exam.id,
        name=slug(room_form.display_name.data),
        display_name=room_form.display_name.data,
    )
    existing_room = Room.query.filter_by(exam_id=exam.id, name=room.name).first()
    if existing_room:
        raise ValidationError('A room with that name already exists')
    headers, rows = read_csv(room_form.sheet_url.data, room_form.sheet_range.data)
    if 'row' not in headers:
        raise ValidationError('Missing "row" column')
    elif 'seat' not in headers:
        raise ValidationError('Missing "seat" column')

    x, y = 0, -1
    last_row = None
    for row in rows:
        seat = Seat()
        seat.row = row.pop('row')
        seat.seat = row.pop('seat')
        seat.name = seat.row + seat.seat
        if not seat.name:
            continue
        if seat_row != last_row:
            x = 0
            y += 1
        else:
            x += 1
        last_row = seat_row
        x_override = row.pop('x')
        y_override = row.pop('y')
        try:
            if x_override:
                x = float(x_override)
            if y_override:
                y = float(y_override)
        except TypeError:
            raise ValidationError('xy coordinates must be floats')
        seat.x = x
        seat.y = y
        seat.attributes = { k for k, v in row.items() if v.lower() == 'true' }
        room.seats.append(seat)
    if len(set(seat.name for seat in room.seats)) != len(room.seats):
        raise ValidationError('Seats are not unique')
    elif len(set((seat.x, seat.y) for seat in room.seats)) != len(room.seats):
        raise ValidationError('Seat coordinates are not unique')
    return room

@app.route('/<exam:exam>/rooms/import/', methods=['GET', 'POST'])
@login_required
@google_oauth.required(scopes=['https://www.googleapis.com/auth/spreadsheets.readonly'])
def new_room(exam):
    form = RoomForm()
    room = None
    if form.validate_on_submit():
        try:
            room = validate_room(exam, form)
        except ValidationError as e:
            form.sheet_url.errors.append(str(e))
        if form.create_room.data:
            db.session.add(room)
            db.session.commit()
            return redirect(url_for('room', exam=exam, room=room.name))
    return render_template('new_room.html.j2', form=form, room=room)

@app.route('/<exam:exam>/rooms/<string:room>/')
@login_required
def room(exam, room):
    room = Room.query.filter_by(exam_id=exam.id, name=room).first_or_404()
    seat = request.args.get('seat')
    return render_template('room.html.j2', room=room, seat=seat)

class StudentForm(FlaskForm):
    sheet_url = StringField('sheet_url', [URL()])
    sheet_range = StringField('sheet_range', [InputRequired()])
    submit = SubmitField('submit')

def validate_students(exam, form):
    headers, rows = read_csv(form.sheet_url.data, form.sheet_range.data)
    if 'email' not in headers:
        raise Validation('Missing "email" column')
    students = []
    for row in rows:
        email = row.pop('email')
        if not email:
            continue
        student = Student.query.filter_by(exam_id=exam.id, email=email).first()
        if not student:
            student = Student(exam_id=exam.id, email=email)
        student.name = row.pop('name')
        student.sid = row.pop('student id')
        student.photo = row.pop('photo')
        student.wants = { k for k, v in row.items() if v.lower() == 'true' }
        student.avoids = { k for k, v in row.items() if v.lower() == 'false' }
        students.append(student)
    return students

@app.route('/<exam:exam>/students/import/', methods=['GET', 'POST'])
@login_required
@google_oauth.required(scopes=['https://www.googleapis.com/auth/spreadsheets.readonly'])
def new_students(exam):
    form = StudentForm()
    if form.validate_on_submit():
        try:
            students = validate_students(exam, form)
            db.session.add_all(students)
            db.session.commit()
            return redirect(url_for('exam', exam=exam))
        except ValidationError as e:
            form.sheet_url.errors.append(str(e))
    return render_template('new_students.html.j2', form=form)

@app.route('/<exam:exam>/students/<string:email>/')
@login_required
def student(exam, email):
    student = Student.query.filter_by(exam_id=exam.id, email=email).first_or_404()
    return render_template('student.html.j2', exam=exam, student=student)
