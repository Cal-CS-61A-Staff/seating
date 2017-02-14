from flask import redirect, render_template, url_for
from flask_login import current_user, login_required
from werkzeug.routing import BaseConverter

from server import app, cache
from server.auth import ok_oauth
from server.models import db, Exam, Room

@app.route('/')
def index():
    return redirect(url_for('exam', offering='cal/cs61a/sp17', exam_name='midterm1'))

name_part = '[^/]+'

class OfferingConverter(BaseConverter):
    regex = name_part + '/' + name_part + '/' + name_part

app.url_map.converters['offering'] = OfferingConverter

@cache.memoize(5*60)
def staff_offerings(email):
    data = ok_oauth.get('enrollment/' + email).data['data']
    return [c['course']['offering'] for c in data['courses']]

def get_exam(offering, exam_name):
    if offering not in staff_offerings(current_user.email):
        abort(404)
    exam = Exam.query.filter_by(offering=offering, name=exam_name).first_or_404()
    return exam

@app.route('/<offering:offering>/<string:exam_name>/')
@login_required
def exam(offering, exam_name):
    exam = get_exam(offering, exam_name)
    return 'OK'

@app.route('/<offering:offering>/<string:exam_name>/new/', methods=['GET', 'POST'])
@login_required
def new_room(offering, exam_name):
    exam = get_exam(offering, exam_name)
    return 'OK'

@app.route('/<offering:offering>/<string:exam_name>/<string:room>/')
@login_required
def room(offering, exam_name, room):
    exam = get_exam(offering, exam_name)
    room = Room.query.filter_by(name=room).first_or_404()
    return 'OK'
