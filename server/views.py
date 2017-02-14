import itertools
import re

from apiclient import discovery, errors
from flask import abort, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from werkzeug.routing import BaseConverter
from wtforms import HiddenField, StringField, SubmitField
from wtforms.validators import InputRequired, URL

from server import app, cache
from server.auth import google_oauth, ok_oauth
from server.models import db, Exam, Room, Seat, seed_exam, slug

@app.route('/')
def index():
    return redirect(url_for('exam', exam=seed_exam))

name_part = '[^/]+'

class ExamConverter(BaseConverter):
    regex = name_part + '/' + name_part + '/' + name_part + '/' + name_part

    @login_required
    def to_python(self, value):
        offering, name = value.rsplit('/', 1)
        if offering not in staff_offerings(current_user.email):
            abort(404)
        exam = Exam.query.filter_by(offering=offering, name=name).first_or_404()
        return exam

    def to_url(self, exam):
        return exam.offering + '/' + exam.name

app.url_map.converters['exam'] = ExamConverter

@cache.memoize(5*60)
def staff_offerings(email):
    data = ok_oauth.get('enrollment/' + email).data['data']
    return [c['course']['offering'] for c in data['courses']]

@app.route('/<exam:exam>/')
@login_required
def exam(exam):
    return 'OK'

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
    return headers, rows

def validate_seats(exam, room_form):
    room = Room(
        exam_id=exam.id,
        name=slug(room_form.display_name.data),
        display_name=room_form.display_name.data,
    )
    existing_room = Room.query.filter_by(exam_id=exam.id, name=room.name).first()
    if existing_room:
        raise ValidationError('A room with that name already exists')
    headers, rows = read_csv(room_form.sheet_url.data, room_form.sheet_range.data)
    if len(set(headers)) != len(headers):
        raise ValidationError('Headers must be unique')
    elif not all(re.match(r'[a-z0-9]+', h) for h in headers):
        raise ValidationError('Headers must consist of digits and numbers')
    elif 'row' not in headers:
        raise ValidationError('Missing "row" column')
    elif 'seat' not in headers:
        raise ValidationError('Missing "seat" column')

    x, y = 0, -1
    last_row = None
    seats = []
    for row in rows:
        if row['row'] != last_row:
            x = 0
            y += 1
        else:
            x += 1
        last_row = row['row']
        try:
            if row.get('x'):
                x = float(row.get('x'))
            if row.get('y'):
                y = float(row.get('y'))
        except TypeError:
            raise ValidationError('xy coordinates must be floats')
        attributes = {
            k for k, v in row.items()
            if k not in ('row', 'seat', 'x', 'y') and v.lower() == 'true'
        }
        seat = Seat(
            room=room,
            name=row['row'] + row['seat'],
            row=row['row'],
            seat=row['seat'],
            x=x,
            y=y,
            attributes=attributes,
        )
        seats.append(seat)
    if len(set(seat.name for seat in seats)) != len(seats):
        raise ValidationError('Seats are not unique')
    elif len(set((seat.x, seat.y) for seat in seats)) != len(seats):
        raise ValidationError('Seat coordinates are not unique')
    return seats

@app.route('/<exam:exam>/new/', methods=['GET', 'POST'])
@login_required
@google_oauth.required(scopes=['https://www.googleapis.com/auth/spreadsheets.readonly'])
def new_room(exam):
    seats = []
    form = RoomForm()
    if form.validate_on_submit():
        try:
            seats = validate_seats(exam, form)
        except ValidationError as e:
            form.sheet_url.errors.append(str(e))
    return render_template('new_room.html.j2', form=form, seats=seats)

@app.route('/<exam:exam>/<string:room>/')
@login_required
def room(exam, room):
    room = Room.query.filter_by(name=room).first_or_404()
    return 'OK'
