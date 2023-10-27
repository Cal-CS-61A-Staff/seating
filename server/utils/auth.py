from os import abort
from flask import redirect, request, session, url_for, render_template
from flask_login import LoginManager, login_user, logout_user, login_required
from flask_oauthlib.client import OAuth
from oauth2client.contrib.flask_util import UserOAuth2


from server import app
from server.models import db, User
import server.utils.canvas as canvas_client
from server.utils.stub import get_dev_user_oauth_resp
from server.form import DevLoginForm

login_manager = LoginManager(app=app)

oauth = OAuth()

server_url = app.config.get('CANVAS_SERVER_URL')
consumer_key = app.config.get('CANVAS_CLIENT_ID')
consumer_secret = app.config.get('CANVAS_CLIENT_SECRET')

canvas_oauth = oauth.remote_app(
    'seating',
    consumer_key=consumer_key,
    consumer_secret=consumer_secret,
    base_url=server_url,
    request_token_url=None,
    access_token_method='POST',
    access_token_url=server_url + 'login/oauth2/token',
    authorize_url=server_url + 'login/oauth2/auth',
)


@canvas_oauth.tokengetter
def get_access_token(token=None):
    return session.get('access_token')


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
    if canvas_client.is_mock_canvas():
        return redirect(url_for('dev_login'))
    return canvas_oauth.authorize(callback=url_for('authorized', _external=True, _scheme='https'))


@app.route('/dev_login/', methods=['GET', 'POST'])
def dev_login():
    if canvas_client.is_mock_canvas():
        form = DevLoginForm()
        if form.validate_on_submit():
            if form.login_as_jimmy.data:
                session["dev_user_id"] = 234567
                return redirect(url_for('authorized'))
            elif form.login_as_yu.data:
                session["dev_user_id"] = 123456
                return redirect(url_for('authorized'))
            else:
                abort(500, 'Invalid dev user')
        return render_template('dev_login.html.j2', form=form)
    return redirect(url_for('index'))


@app.route('/authorized/')
def authorized():
    if canvas_client.is_mock_canvas():
        resp = get_dev_user_oauth_resp(session["dev_user_id"])
    else:
        resp = canvas_oauth.authorized_response()

    if resp is None:
        return 'Access denied: {}'.format(request.args.get('error', 'unknown error'))
    session['access_token'] = resp['access_token']
    user_info = resp['user']

    user = canvas_client.get_user(user_info['id'])
    staff_course_dics, student_course_dics, _ = canvas_client.get_user_courses_categorized(user)
    staff_offerings = [str(c.id) for c in staff_course_dics]
    student_offerings = [str(c.id) for c in student_course_dics]

    user_model = User.query.filter_by(canvas_id=user_info['id']).one_or_none()
    if not user_model:
        user_model = User(
            name=user_info['name'],
            canvas_id=user_info['id'],
            staff_offerings=staff_offerings,
            student_offerings=student_offerings)
        db.session.add(user_model)
    else:
        user_model.staff_offerings = staff_offerings
        user_model.student_offerings = student_offerings
    db.session.commit()

    login_user(user_model, remember=True)
    after_login = session.pop('after_login', None) or url_for('index')
    return redirect(after_login)


@app.route('/logout/')
@login_required
def logout():
    session.clear()
    logout_user()
    return redirect(url_for('index'))
