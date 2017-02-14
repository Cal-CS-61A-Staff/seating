from flask import redirect, render_template, request, url_for
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from werkzeug.routing import BaseConverter
from wtforms import HiddenField, StringField, SubmitField
from wtforms.validators import InputRequired, URL

from server import app, cache
from server.auth import ok_oauth
from server.models import db, Exam, Room, seed_exam

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

class Form(FlaskForm):
    @property
    def public_data(self):
        return {
            field.name: field.data for field in self
            if not isinstance(field, (HiddenField, SubmitField))
        }

class RoomForm(Form):
    display_name = StringField('display_name', [InputRequired()])
    sheet_url = StringField('sheet_url', [URL()])
    sheet_range = StringField('sheet_range', [InputRequired()])
    preview_room = SubmitField('preview_room')
    create_room = SubmitField('create_room')

@app.route('/<exam:exam>/new/', methods=['GET', 'POST'])
@login_required
def new_room(exam):
    form = RoomForm(**request.args.to_dict())
    print(form.public_data)
    if form.validate_on_submit():
        if form.preview_room.data:
            return redirect(url_for('new_room', exam=exam, **form.public_data))
        elif form.create_room.data:
            return redirect(url_for('exam', exam=exam))
    return render_template('new_room.html.j2', form=form)

@app.route('/<exam:exam>/<string:room>/')
@login_required
def room(exam, room):
    room = Room.query.filter_by(name=room).first_or_404()
    return 'OK'
