import time

from flask import redirect, session, url_for
from flask_login import login_user, logout_user, login_required
from markupsafe import escape
import server.services.canvas as canvas_client

from server.models import db, User

from server.controllers import auth_module
from server.services.auth import SIGNED_IN_AT_KEY, oauth_provider
from server.services.auth.canvas_tokens import discard_token, store_token
from authlib.integrations.base_client import OAuthError


@auth_module.route('/login/')
def login():
    if canvas_client.is_mock_canvas():
        return redirect(url_for('dev_login.dev_login_page'))
    return oauth_provider().authorize_redirect(
        url_for('auth.authorized', _external=True, _scheme="https"))


@auth_module.route('/authorized/')
def authorized():
    try:
        # Authlib raises OAuthError when the provider reports an error, when the
        # `state` does not match the one we generated, or when the code exchange fails.
        resp = oauth_provider().authorize_access_token()
    except OAuthError as e:
        # the provider's error is copied from the `error`/`error_description` query parameters,
        # which anyone can put in a link, and a returned str is served as HTML: escape it
        return 'Access denied: {}'.format(escape(e.description or e.error or 'unknown error')), 403
    # a token from an earlier sign-in in this browser is no longer needed
    discard_token()
    access_token = resp['access_token']
    user_info = resp['user']

    user = canvas_client.get_user(user_info['id'], key=access_token)
    staff_course_dics, student_course_dics, _, _ = canvas_client.get_user_courses_categorized(user)

    user_model = User.query.filter_by(canvas_id=str(user_info['id'])).one_or_none()
    if not user_model:
        user_model = User(name=user_info['name'], canvas_id=str(user_info['id']))
        db.session.add(user_model)
    user_model.set_course_roles(staff_course_dics, student_course_dics)
    db.session.commit()
    store_token(user_model, access_token, resp.get('expires_in'))

    # No remember cookie: it holds no time, so it would sign the user back in with the roles from
    # their last sign-in for as long as the browser keeps it.
    login_user(user_model)
    session.permanent = True
    session[SIGNED_IN_AT_KEY] = time.time()
    after_login = session.pop('after_login', None) or url_for('views.index')
    return redirect(after_login)


@auth_module.route('/logout/')
@login_required
def logout():
    discard_token()
    session.clear()
    logout_user()
    return redirect(url_for('views.index'))
