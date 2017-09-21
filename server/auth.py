from flask import redirect, request, session, url_for
from flask_login import LoginManager, login_required, login_user, logout_user
from flask_oauthlib.client import OAuth, OAuthException
from oauth2client.contrib.flask_util import UserOAuth2
from werkzeug import security

from server import app
from server.models import db, User, Student, SeatAssignment

login_manager = LoginManager(app=app)

oauth = OAuth()
server_url = 'https://okpy.org'
ok_oauth = oauth.remote_app(
    'seating',
    consumer_key=app.config.get('OK_CLIENT_ID'),
    consumer_secret=app.config.get('OK_CLIENT_SECRET'),
    request_token_params={
        'scope': 'all',
        'state': lambda: security.gen_salt(10),
    },
    base_url=server_url + '/api/v3/',
    request_token_url=None,
    access_token_method='POST',
    access_token_url=server_url + '/oauth/token',
    authorize_url=server_url + '/oauth/authorize',
)

@ok_oauth.tokengetter
def get_access_token(token=None):
    return session.get('ok_token')

google_oauth = UserOAuth2(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(user_id)

@login_manager.unauthorized_handler
def unauthorized():
    session['after_login'] = request.url
    return redirect(url_for('login'))

@app.route('/login/')
def login():
    return ok_oauth.authorize(callback=url_for('authorized', _external=True))

@app.route('/authorized/')
def authorized():
    resp = ok_oauth.authorized_response()
    if resp is None:
        return 'Access denied: {}'.format(request.args.get('error', 'unknown error'))
    session['ok_token'] = (resp['access_token'], '')

    info = ok_oauth.get('user').data['data']
    email = info['email']
    is_staff = email == app.config['TEST_LOGIN']
    for p in info['participations']:
        if is_staff:
            break
        if p['course']['offering'] != app.config['COURSE']:
            continue
        if p['role'] == 'student':
            student = Student.query.filter_by(email=email).join(Student.exam) \
                .filter_by(offering=app.config['COURSE'],
                           name=app.config['EXAM']).one_or_none()
            if not student:
                return 'Your email is not registered. Please contact the course staff.'
            if student:
                seat = SeatAssignment.query.filter_by(student_id=student.id).one_or_none()
                if not seat:
                    return 'No seat found. Please contact the course staff.'
                return redirect('/seat/{}'.format(seat.seat_id))
        elif p['role'] != 'lab assistant':
            is_staff = True
            
    if not is_staff:
        return 'Access denied: {}'.format(request.args.get('error', 'unknown error'))
        
    user = User.query.filter_by(email=email).one_or_none()
    if not user:
        user = User(email=email)
    user.offerings = [p['course']['offering'] for p in info['participations']]

    db.session.add(user)
    db.session.commit()

    login_user(user, remember=True)
    after_login = session.pop('after_login', None) or url_for('index')
    return redirect(after_login)

@app.route('/logout/')
def logout():
    session.clear()
    logout_user()
    return redirect(url_for('index'))
