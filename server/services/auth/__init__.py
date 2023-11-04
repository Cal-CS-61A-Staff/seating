from flask import redirect, request, session, url_for

from flask_login import LoginManager
from flask_oauthlib.client import OAuth
from oauth2client.contrib.flask_util import UserOAuth2

from server import app

login_manager = LoginManager(app=app)

oauth = OAuth()

canvas_server_url = app.config.get('CANVAS_SERVER_URL')
consumer_key = app.config.get('CANVAS_CLIENT_ID')
consumer_secret = app.config.get('CANVAS_CLIENT_SECRET')

canvas_oauth = oauth.remote_app(
    'seating',
    consumer_key=consumer_key,
    consumer_secret=consumer_secret,
    base_url=canvas_server_url,
    request_token_url=None,
    access_token_method='POST',
    access_token_url=canvas_server_url + 'login/oauth2/token',
    authorize_url=canvas_server_url + 'login/oauth2/auth',
)


@canvas_oauth.tokengetter
def get_access_token(token=None):
    return session.get('access_token')


@login_manager.user_loader
def load_user(user_id):
    from server.models import User
    return User.query.get(user_id)


@login_manager.unauthorized_handler
def unauthorized():
    session['after_login'] = request.url
    return redirect(url_for('auth.login'))


google_oauth = UserOAuth2(app)
