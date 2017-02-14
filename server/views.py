from flask import redirect, render_template, url_for
from flask_login import current_user, login_required
from werkzeug.routing import BaseConverter

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

@app.route('/<exam:exam>/new/', methods=['GET', 'POST'])
@login_required
def new_room(exam):
    return 'OK'

@app.route('/<exam:exam>/<string:room>/')
@login_required
def room(exam, room):
    room = Room.query.filter_by(name=room).first_or_404()
    return 'OK'
