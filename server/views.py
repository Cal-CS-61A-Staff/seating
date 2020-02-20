import itertools
import os
import random
import re
import zipfile

import requests
import sendgrid
from flask import abort, redirect, render_template, request, send_file, session, url_for, g
from flask_login import current_user
from flask_wtf import FlaskForm
from werkzeug.exceptions import HTTPException
from werkzeug.routing import BaseConverter
from werkzeug.utils import secure_filename
from wtforms import SelectMultipleField, StringField, SubmitField, TextAreaField, widgets, FileField
from wtforms.validators import Email, InputRequired, URL

from server import app
from server.models import Exam, Room, Seat, SeatAssignment, Student, db, slug

name_part = '[^/]+'

DOMAIN_COURSES = {}
COURSE_ENDPOINTS = {}


def get_course(domain=None):
    if not domain:
        domain = request.headers["HOST"]
    if domain not in DOMAIN_COURSES:
        DOMAIN_COURSES[domain] = requests.post("https://auth.apps.cs61a.org/domains/get_course", json={
            "domain": domain
        }).json()
    return DOMAIN_COURSES[domain]


def get_endpoint(course=None):
    if not course:
        course = get_course()
    if course not in COURSE_ENDPOINTS:
        COURSE_ENDPOINTS[course] = requests.post("https://auth.apps.cs61a.org/api/{}/get_endpoint".format(course)).json()
    return COURSE_ENDPOINTS[course]


def is_admin(course=None):
    if not course:
        course = get_course()
    if g.get("is_admin") is None:
        g.is_admin = requests.post("https://auth.apps.cs61a.org/admins/{}/is_admin".format(course), json={
            "email": current_user.email
        }).json()
    return g.is_admin


def format_coursecode(course):
    m = re.match(r"([a-z]+)([0-9]+[a-z]?)", course)
    return m and (m.group(1) + " " + m.group(2)).upper()


class Redirect(HTTPException):
    code = 302

    def __init__(self, url):
        self.url = url

    def get_response(self, environ=None):
        return redirect(self.url)


class ExamConverter(BaseConverter):
    regex = name_part + '/' + name_part + '/' + name_part + '/' + name_part

    def to_python(self, value):
        offering, name = value.rsplit('/', 1)
        if not current_user.is_authenticated or offering not in current_user.offerings:
            session['after_login'] = request.url
            raise Redirect(url_for('login'))
        exam = Exam.query.filter_by(offering=offering, name=name).first_or_404()
        return exam

    def to_url(self, exam):
        return exam.offering + '/' + exam.name


class OfferingConverter(BaseConverter):
    regex = name_part + '/' + name_part + '/' + name_part

    def to_python(self, offering):
        if offering != get_endpoint():
            abort(404)
        if not current_user.is_authenticated or offering not in current_user.offerings:
            session['after_login'] = request.url
            raise Redirect(url_for('login'))
        return offering

    def to_url(self, offering):
        return offering


app.url_map.converters['exam'] = ExamConverter
app.url_map.converters['offering'] = OfferingConverter


class ValidationError(Exception):
    pass


class MultiCheckboxField(SelectMultipleField):
    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()


class RoomForm(FlaskForm):
    display_name = StringField('display_name', [InputRequired()])
    sheet_url = StringField('sheet_url', [URL()])
    sheet_range = StringField('sheet_range', [InputRequired()])
    preview_room = SubmitField('preview')
    create_room = SubmitField('create')


class MultRoomForm(FlaskForm):
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
                                        ('RSF FH ', 'RSF FH '),
                                        ('306 Soda', '306 Soda'),
                                        ('2040 VLSB', '2040 VLSB'),
                                        ('2050 VLSB', '2050 VLSB'),
                                        ('2060 VLSB', '2060 VLSB'),
                                        ('150 Wheeler', '150 Wheeler'),
                                        ('222 Wheeler', '222 Wheeler')
                                        ])
    submit = SubmitField('import')


def read_csv(sheet_url, sheet_range):
    values = requests.post("https://auth.apps.cs61a.org/google/read_spreadsheet", json={
        "url": sheet_url,
        "sheet_name": sheet_range,
        "client_name": app.config["AUTH_KEY"],
        "secret": app.config["AUTH_CLIENT_SECRET"],
    }).json()

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
        seat.attributes = {k for k, v in row.items() if v.lower() == 'true'}
        room.seats.append(seat)
    if len(set(seat.name for seat in room.seats)) != len(room.seats):
        raise ValidationError('Seats are not unique')
    elif len(set((seat.x, seat.y) for seat in room.seats)) != len(room.seats):
        raise ValidationError('Seat coordinates are not unique')
    return room


@app.route('/<exam:exam>/rooms/import/')
def import_room(exam):
    new_form = RoomForm()
    choose_form = MultRoomForm()
    return render_template('new_room.html.j2', exam=exam, new_form=new_form, choose_form=choose_form)


@app.route('/<exam:exam>/rooms/import/new/', methods=['GET', 'POST'])
def new_room(exam):
    new_form = RoomForm()
    choose_form = MultRoomForm()
    room = None
    if new_form.validate_on_submit():
        try:
            room = validate_room(exam, new_form)
        except ValidationError as e:
            new_form.sheet_url.errors.append(str(e))
        if new_form.create_room.data:
            db.session.add(room)
            db.session.commit()
            return redirect(url_for('exam', exam=exam))
    return render_template('new_room.html.j2', exam=exam, new_form=new_form, choose_form=choose_form, room=room)


@app.route('/<exam:exam>/rooms/import/choose/', methods=['GET', 'POST'])
def mult_new_room(exam):
    new_form = RoomForm()
    choose_form = MultRoomForm()
    if choose_form.validate_on_submit():
        for r in choose_form.rooms.data:
            # add error handling
            f = RoomForm(display_name=r,
                         sheet_url='https://docs.google.com/spreadsheets/d/1cHKVheWv2JnHBorbtfZMW_3Sxj9VtGMmAUU2qGJ33-s/edit?usp=sharing',
                         sheet_range=r)
            room = validate_room(exam, f)
            db.session.add(room)
            db.session.commit()
        return redirect(url_for('exam', exam=exam))
    return render_template('new_room.html.j2', exam=exam, new_form=new_form, choose_form=choose_form)


@app.route('/<exam:exam>/rooms/update/<room_name>/', methods=['POST'])
def update_room(exam, room_name):
    # ask if want to delete
    # if assigned ask if they are sure they want to delete seat assignments
    room = Room.query.filter_by(exam_id=exam.id, name=room_name).first()
    if room:
        room.name = new_room_name
        db.session.commit()
    return render_template('exam.html.j2', exam=exam)


@app.route('/<exam:exam>/rooms/delete/<room_name>/', methods=['GET', 'POST'])
def delete_room(exam, room_name):
    # ask if want to delete
    # if assigned ask if they are sure they want to delete seat assignments
    room = Room.query.filter_by(exam_id=exam.id, name=room_name).first()
    if room:
        seats = Seat.query.filter_by(room_id=room.id).all()
        for seat in seats:
            if seat.assignment:
                db.session.delete(seat.assignment)
            db.session.delete(seat)
        db.session.delete(room)
        db.session.commit()
    return render_template('exam.html.j2', exam=exam)


class StudentForm(FlaskForm):
    sheet_url = StringField('sheet_url', [URL()])
    sheet_range = StringField('sheet_range', [InputRequired()])
    submit = SubmitField('import')


def validate_students(exam, form):
    headers, rows = read_csv(form.sheet_url.data, form.sheet_range.data)
    if 'email' not in headers:
        raise ValidationError('Missing "email" column')
    elif 'name' not in headers:
        raise ValidationError('Missing "name" column')
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
        student.wants = {k for k, v in row.items() if v.lower() == 'true'}
        student.avoids = {k for k, v in row.items() if v.lower() == 'false'}
        students.append(student)
    return students


@app.route('/<exam:exam>/students/import/', methods=['GET', 'POST'])
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
'''.format(exam.display_name, request.url_root, form.additional_text.data)
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


@app.route("/")
def index():
    return redirect(url_for("offering", offering=get_endpoint()))


@app.route('/<offering:offering>/')
def offering(offering):
    if offering not in current_user.offerings:
        abort(401)
    exams = Exam.query.filter(Exam.offering==offering)
    return render_template("offering.j2", title="{} Exam Seating".format(format_coursecode(get_course())), exams=exams, offering=offering)


@app.route('/favicon.ico')
def favicon():
    return send_file('static/img/favicon.ico')


@app.route('/students-template.png')
def students_template():
    return send_file('static/img/students-template.png')

class ExamForm(FlaskForm):
    display_name = StringField('display_name', [InputRequired()], render_kw={"placeholder": "Midterm 1"})
    name = StringField('name', [InputRequired()], render_kw={"placeholder": "midterm1"})
    submit = SubmitField('create')

    def validate_name(form, field):
        if " " in field.data or field.data != field.data.lower():
            from wtforms.validators import ValidationError
            raise ValidationError('Exam name must be all lowercase with no spaces')


@app.route("/<offering:offering>/new/", methods=["GET", "POST"])
def new_exam(offering):
    form = ExamForm()
    if form.validate_on_submit():
        Exam.query.filter_by(offering=offering).update({"is_active": False})
        exam = Exam(offering=offering, name=form.name.data, display_name=form.display_name.data, is_active=True)
        db.session.add(exam)
        db.session.commit()

        return redirect(url_for("offering", offering=offering))
    return render_template("new_exam.html.j2", title="{} Exam Seating".format(format_coursecode(get_course())), form=form)


@app.route("/<exam:exam>/delete/", methods=["GET", "POST"])
def delete_exam(exam):
    db.session.delete(exam)
    db.session.commit()

    return redirect(url_for("offering", offering=exam.offering))


@app.route("/<exam:exam>/toggle/", methods=["GET", "POST"])
def toggle_exam(exam):
    if exam.is_active:
        exam.is_active = False
    else:
        Exam.query.filter_by(offering=exam.offering).update({"is_active": False})
        exam.is_active = True
    db.session.commit()
    return redirect(url_for("offering", offering=exam.offering))

@app.route('/<exam:exam>/')
def exam(exam):
    return render_template('exam.html.j2', exam=exam)


@app.route('/<exam:exam>/help/')
def help(exam):
    return render_template('help.html.j2', exam=exam)


class PhotosForm(FlaskForm):
    file = FileField("file", [InputRequired()])
    submit = SubmitField('Submit')


@app.route('/<exam:exam>/students/photos/', methods=['GET', 'POST'])
def new_photos(exam):
    form = PhotosForm()
    if form.validate_on_submit():
        f = form.file.data
        zf = zipfile.ZipFile(f, mode="r")
        for name in zf.namelist():
            if name.endswith("/"):
                continue
            secure_name = secure_filename(name)
            path = os.path.join(app.config["PHOTO_DIRECTORY"], exam.offering, secure_name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb+") as g:
                g.write(zf.open(name, "r").read())
    return render_template('new_photos.html.j2', exam=exam, form=form)


@app.route('/<exam:exam>/rooms/<string:name>/')
def room(exam, name):
    room = Room.query.filter_by(exam_id=exam.id, name=name).first_or_404()
    seat = request.args.get('seat')
    return render_template('room.html.j2', exam=exam, room=room, seat=seat)


@app.route('/<exam:exam>/students/')
def students(exam):
    # TODO load assignment and seat at the same time?
    students = Student.query.filter_by(exam_id=exam.id).all()
    return render_template('students.html.j2', exam=exam, students=students, is_admin=is_admin())


@app.route('/<exam:exam>/students/<string:email>/')
def student(exam, email):
    student = Student.query.filter_by(exam_id=exam.id, email=email).first_or_404()
    return render_template('student.html.j2', exam=exam, student=student)


@app.route('/<exam:exam>/students/<string:email>/photo')
def photo(exam, email):
    student = Student.query.filter_by(exam_id=exam.id, email=email).first_or_404()
    photo_path = os.path.join(app.config['PHOTO_DIRECTORY'], exam.offering, student.bcourses_id) + ".jpeg"
    return send_file(photo_path, mimetype='image/jpeg')


@app.route('/seat/<int:seat_id>/')
def single_seat(seat_id):
    seat = Seat.query.filter_by(id=seat_id).first_or_404()
    return render_template('seat.html.j2', room=seat.room, seat=seat)
