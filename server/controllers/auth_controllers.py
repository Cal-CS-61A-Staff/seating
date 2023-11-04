from os import abort
from flask import redirect, request, session, url_for, render_template
from flask_login import login_user, logout_user, login_required
import server.services.canvas as canvas_client

from server.models import db, User

from server.controllers import auth_module
from server.services.canvas.stub import get_dev_user_oauth_resp
from server.services.auth import canvas_oauth


@auth_module.route('/login/')
def login():
    if canvas_client.is_mock_canvas():
        return redirect(url_for('auth.dev_login'))
    return canvas_oauth.authorize(callback=url_for('auth.authorized', _external=True, _scheme='https'))


@auth_module.route('/dev_login/', methods=['GET', 'POST'])
def dev_login():
    if canvas_client.is_mock_canvas():
        from server.forms import DevLoginForm
        form = DevLoginForm()
        if form.validate_on_submit():
            if form.login_as_jimmy.data:
                session["dev_user_id"] = 234567
                return redirect(url_for('auth.authorized'))
            elif form.login_as_yu.data:
                session["dev_user_id"] = 123456
                return redirect(url_for('auth.authorized'))
            else:
                abort(500, 'Invalid dev user')
        return render_template('dev_login.html.j2', form=form)
    return redirect(url_for('index'))


@auth_module.route('/authorized/')
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


@auth_module.route('/logout/')
@login_required
def logout():
    session.clear()
    logout_user()
    return redirect(url_for('index'))
