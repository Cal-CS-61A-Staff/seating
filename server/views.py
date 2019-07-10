import itertools
import os
import random
import re

from apiclient import discovery, errors
from flask import abort, redirect, render_template, request, send_file, session, url_for
from flask_login import current_user
from flask_wtf import FlaskForm
import sendgrid
from werkzeug.exceptions import HTTPException
from werkzeug.routing import BaseConverter
from wtforms import HiddenField, StringField, SubmitField, TextAreaField
from wtforms.validators import Email, InputRequired, URL

from server import app
from server.auth import google_oauth, ok_oauth
from server.models import db, Exam, Room, Seat, SeatAssignment, Student, slug

name_part = '[^/]+'

class Redirect(HTTPException):
    code = 302
    def __init__(self, url):
        self.url = url

    def get_response(self, environ=None):
        return redirect(self.url)

class ExamConverter(BaseConverter):
    regex = name_part + '/' + name_part + '/' + name_part + '/' + name_part

    def to_python(self, value):
        if not current_user.is_authenticated:
            session['after_login'] = request.url
            raise Redirect(url_for('login'))
        offering, name = value.rsplit('/', 1)
        if offering not in current_user.offerings:
            abort(404)
        exam = Exam.query.filter_by(offering=offering, name=name).first_or_404()
        return exam

    def to_url(self, exam):
        return exam.offering + '/' + exam.name

app.url_map.converters['exam'] = ExamConverter

class ValidationError(Exception):
    pass

class RoomForm(FlaskForm):
    display_name = StringField('display_name', [InputRequired()])
    sheet_url = StringField('sheet_url', [URL()])
    sheet_range = StringField('sheet_range', [InputRequired()])
    preview_room = SubmitField('preview')
    create_room = SubmitField('create')

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
            return redirect(url_for('room', exam=exam, name=room.name))
    return render_template('new_room.html.j2', exam=exam, form=form, room=room)

class StudentForm(FlaskForm):
    sheet_url = StringField('sheet_url', [URL()])
    sheet_range = StringField('sheet_range', [InputRequired()])
    submit = SubmitField('import')

def validate_students(exam, form):
    headers, rows = read_csv(form.sheet_url.data, form.sheet_range.data)
    if 'email' not in headers:
        raise Validation('Missing "email" column')
    elif 'name' not in headers:
        raise Validation('Missing "name" column')
    students = []
    for row in rows:
        email = row.pop('email')
        if not email:
            continue
        student = Student.query.filter_by(exam_id=exam.id, email=email).first()
        if not student:
            student = Student(exam_id=exam.id, email=email)
        student.name = row.pop('name')
        student.sid = row.pop('student id', None) or student.sid
        student.bcourses_id = row.pop('bcourses id', None) or student.bcourses_id
        student.wants = { k for k, v in row.items() if v.lower() == 'true' }
        student.avoids = { k for k, v in row.items() if v.lower() == 'false' }
        students.append(student)
    return students

@app.route('/<exam:exam>/students/import/', methods=['GET', 'POST'])
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
    return render_template('new_students.html.j2', exam=exam, form=form)

class DeleteStudentForm(FlaskForm):
    emails = TextAreaField('emails')
    submit = SubmitField('delete')

@app.route('/<exam:exam>/students/delete/', methods=['GET', 'POST'])
def delete_students(exam):
    form = DeleteStudentForm()
    deleted, did_not_exist = set(), set()
    if form.validate_on_submit():
        for email in re.split(r'\s|,', form.emails.data):
            if not email:
                continue
            student = Student.query.filter_by(exam_id=exam.id, email=email).first()
            if student:
                deleted.add(email)
                if student.assignment:
                    db.session.delete(student.assignment)
                db.session.delete(student)
            else:
                did_not_exist.add(email)
        db.session.commit()
    return render_template('delete_students.html.j2',
        exam=exam, form=form, deleted=deleted, did_not_exist=did_not_exist)

class AssignForm(FlaskForm):
    submit = SubmitField('assign')

def collect(s, key=lambda x: x):
    d = {}
    for x in s:
        k = key(x)
        if k in d:
            d[k].append(x)
        else:
            d[k] = [x]
    return d

def assign_students(exam):
    """The strategy: look for students whose requirements are the most
    restrictive (i.e. have the fewest possible seats). Randomly assign them
    a seat. Repeat.
    """
    students = set(Student.query.filter_by(
        exam_id=exam.id, assignment=None
    ).all())
    seats = set(Seat.query.join(Seat.room).filter(
        Room.exam_id == exam.id,
        Seat.assignment == None,
    ).all())

    def seats_available(preference):
        wants, avoids = preference
        return [
            seat for seat in seats
            if all(a in seat.attributes for a in wants)
            and all(a not in seat.attributes for a in avoids)
        ]

    assignments = []
    while students:
        students_by_preference = collect(students, key=
            lambda student: (frozenset(student.wants), frozenset(student.avoids)))
        seats_by_preference = {
            preference: seats_available(preference)
            for preference in students_by_preference
        }
        min_preference = min(seats_by_preference, key=lambda k: len(seats_by_preference[k]))
        min_students = students_by_preference[min_preference]
        min_seats = seats_by_preference[min_preference]
        if not min_seats:
            return 'Assignment failed! No more seats for preference {}'.format(min_preference)

        student = random.choice(min_students)
        seat = random.choice(min_seats)

        students.remove(student)
        seats.remove(seat)

        assignments.append(SeatAssignment(student=student, seat=seat))
    return assignments

@app.route('/<exam:exam>/students/assign/', methods=['GET', 'POST'])
def assign(exam):
    form = AssignForm()
    if form.validate_on_submit():
        assignments = assign_students(exam)
        if type(assignments) == str:
            return assignments
        db.session.add_all(assignments)
        db.session.commit()
        return redirect(url_for('students', exam=exam))
    return render_template('assign.html.j2', exam=exam, form=form)

class EmailForm(FlaskForm):
    from_email = StringField('from_email', [Email()])
    from_name = StringField('from_name', [InputRequired()])
    subject = StringField('subject', [InputRequired()])
    test_email = StringField('test_email')
    additional_text = TextAreaField('additional_text')
    submit = SubmitField('send')

def email_students(exam, form):
    """Emails students in batches of 900"""
    sg = sendgrid.SendGridAPIClient(api_key=app.config['SENDGRID_API_KEY'])
    test = form.test_email.data
    while True:
        limit = 1 if test else 900
        assignments = SeatAssignment.query.join(SeatAssignment.seat).join(Seat.room).filter(
            Room.exam_id == exam.id,
            SeatAssignment.emailed == False,
        ).limit(limit).all()
        if not assignments:
            break

        data = {
            'personalizations': [
                {
                    'to': [
                        {
                            'email': test if test else assignment.student.email,
                        }
                    ],
                    'substitutions': {
                        '-name-': assignment.student.first_name,
                        '-room-': assignment.seat.room.display_name,
                        '-seat-': assignment.seat.name,
                        '-seatid-': str(assignment.seat.id),
                    },
                }
                for assignment in assignments
            ],
            'from': {
                'email': form.from_email.data,
                'name': form.from_name.data,
            },
            'subject': form.subject.data,
            'content': [
                {
                    'type': 'text/plain',
                    'value': '''
Hi -name-,

Here's your assigned seat for {}:

Room: -room-

Seat: -seat-

You can view this seat's position on the seating chart at:
{}/seat/-seatid-/

{}
'''.format(exam.display_name, app.config['DOMAIN'], form.additional_text.data)
                },
            ],
        }

        response = sg.client.mail.send.post(request_body=data)
        if response.status_code < 200 or response.status_code >= 400:
            raise Exception('Could not send mail. Status: {}. Body: {}'.format(
                response.status_code, response.body
            ))
        if test:
            return
        for assignment in assignments:
            assignment.emailed = True
        db.session.commit()

@app.route('/<exam:exam>/students/email/', methods=['GET', 'POST'])
def email(exam):
    form = EmailForm()
    if form.validate_on_submit():
        email_students(exam, form)
        return redirect(url_for('students', exam=exam))
    return render_template('email.html.j2', exam=exam, form=form)

@app.route('/')
def index():
    return redirect('/' + app.config['COURSE'] + '/' + app.config['EXAM'])

@app.route('/favicon.ico')
def favicon():
    return send_file('static/img/favicon.ico')

@app.route('/<exam:exam>/')
def exam(exam):
    return render_template('exam.html.j2', exam=exam)

@app.route('/<exam:exam>/help/')
def help(exam):
    return render_template('help.html.j2', exam=exam)

@app.route('/<exam:exam>/students/photos/', methods=['GET', 'POST'])
def new_photos(exam):
    return render_template('new_photos.html.j2', exam=exam)

@app.route('/<exam:exam>/rooms/<string:name>/')
def room(exam, name):
    room = Room.query.filter_by(exam_id=exam.id, name=name).first_or_404()
    seat = request.args.get('seat')
    return render_template('room.html.j2', exam=exam, room=room, seat=seat)

@app.route('/<exam:exam>/students/')
def students(exam):
    # TODO load assignment and seat at the same time?
    students = Student.query.filter_by(exam_id=exam.id).all()
    return render_template('students.html.j2', exam=exam, students=students)

@app.route('/<exam:exam>/students/<string:email>/')
def student(exam, email):
    student = Student.query.filter_by(exam_id=exam.id, email=email).first_or_404()
    return render_template('student.html.j2', exam=exam, student=student)

@app.route('/<exam:exam>/students/<string:email>/photo')
def photo(exam, email):
    student = Student.query.filter_by(exam_id=exam.id, email=email).first_or_404()
    photo_path = '{}/{}/{}.jpeg'.format(app.config['PHOTO_DIRECTORY'], 
        exam.offering, student.bcourses_id)
    return send_file(photo_path, mimetype='image/jpeg')

@app.route('/seat/<int:seat_id>/')
def single_seat(seat_id):
    seat = Seat.query.filter_by(id=seat_id).first_or_404()
    return render_template('seat.html.j2', room=seat.room, seat=seat)
