import time

from flask import current_app, redirect, request, session, url_for

from flask_login import LoginManager
from authlib.integrations.flask_client import OAuth
from .scope import scopes
from server.services.canvas import is_mock_canvas

# set up for each app by init_auth
login_manager = LoginManager()

# When the user last signed in through Canvas, in the (signed) session cookie.
SIGNED_IN_AT_KEY = 'signed_in_at'
# Roles come from Canvas only at sign-in, so a sign-in older than this is refused and the user
# signs in again, picking up any role they've gained or lost. Overridable with the
# SIGN_IN_MAX_AGE config value, in seconds.
DEFAULT_SIGN_IN_MAX_AGE = 12 * 60 * 60


def sign_in_expired():
    """
    Whether this session's sign-in is too old to trust its Canvas roles, or has no sign-in time
    (sessions and remember cookies from before it was kept).
    """
    signed_in_at = session.get(SIGNED_IN_AT_KEY)
    max_age = current_app.config.get('SIGN_IN_MAX_AGE', DEFAULT_SIGN_IN_MAX_AGE)
    return not isinstance(signed_in_at, (int, float)) or time.time() - signed_in_at > max_age


def get_access_token():
    """
    Supplies the stored Canvas token to Authlib when the client is used to call
    the remote API. Authlib expects a token dict rather than a bare string.
    """
    from server.services.auth.canvas_tokens import current_token
    access_token = current_token()
    return {'access_token': access_token, 'token_type': 'Bearer'} if access_token else None


def init_auth(app):
    """Sets up logins for `app`, with the real Canvas or the fake one its config asks for."""
    login_manager.init_app(app)
    oauth = OAuth(app)
    if not is_mock_canvas(app.config):
        canvas_server_url = app.config.get('CANVAS_SERVER_URL')
        provider = oauth.register(
            'seating',
            client_id=app.config.get('CANVAS_CLIENT_ID'),
            client_secret=app.config.get('CANVAS_CLIENT_SECRET'),
            api_base_url=canvas_server_url,
            access_token_url=canvas_server_url + 'login/oauth2/token',
            authorize_url=canvas_server_url + 'login/oauth2/auth',
            # Canvas expects the client credentials in the POST body, not a Basic auth header
            client_kwargs={
                'scope': ' '.join(scopes),
                'token_endpoint_auth_method': 'client_secret_post',
            },
            fetch_token=get_access_token,
        )
    else:
        # dev login uses HTTP so we need to allow that for OAuth2
        import os
        os.environ['AUTHLIB_INSECURE_TRANSPORT'] = '1'
        dev_oauth_server_url = app.config.get('SERVER_BASE_URL')
        provider = oauth.register(
            'seating_dev',
            client_id='development_key',
            client_secret='development_secret',
            api_base_url=dev_oauth_server_url,
            access_token_url=dev_oauth_server_url + 'dev_login/oauth2/token/',
            authorize_url=dev_oauth_server_url + 'dev_login/oauth2/auth/',
            client_kwargs={'token_endpoint_auth_method': 'client_secret_post'},
            fetch_token=get_access_token,
        )
    app.extensions['seating_oauth_provider'] = provider

    @app.before_request
    def drop_legacy_access_token():
        """Removes the Canvas token that sign-ins used to keep in the session cookie."""
        from server.services.auth.canvas_tokens import LEGACY_SESSION_KEY
        if LEGACY_SESSION_KEY in session:
            session.pop(LEGACY_SESSION_KEY)


def oauth_provider():
    """The current app's Canvas OAuth client."""
    return current_app.extensions['seating_oauth_provider']


@login_manager.user_loader
def load_user(user_id):
    from server.models import db, User
    if sign_in_expired():
        return None
    return db.session.get(User, user_id)


@login_manager.unauthorized_handler
def unauthorized():
    session['after_login'] = request.url
    return redirect(url_for('auth.login'))
