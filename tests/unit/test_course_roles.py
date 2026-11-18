"""
Course roles are saved from Canvas at sign-in, and again whenever /offerings loads, so that every course
it lists opens. The mock Canvas has Jimmy Xu (user 2) as a student of 1234567 and a TA of 2345678, and
Yu Long (user 1, Canvas id 123456) as a TA of 1234567 and a student of 4567890.
"""
import pytest

from server.models import User, db
from server.services.canvas.fake_data import FAKE_USERS


def _make_roles_stale(user_id):
    """Saves roles that no longer match Canvas, as if from an old sign-in."""
    user = db.session.get(User, user_id)
    user.staff_offerings = set()
    user.student_offerings = {'3456789'}
    db.session.commit()


def test_offerings_page_saves_roles_from_canvas(seeded_db, login_as):
    _make_roles_stale(2)
    assert login_as(2).get('/offerings').status_code == 200
    user = db.session.get(User, 2)
    assert user.staff_offerings == {'2345678'}
    assert user.student_offerings == {'1234567'}


def test_course_added_since_sign_in_opens_after_offerings_page(seeded_db, login_as):
    _make_roles_stale(2)
    client = login_as(2)
    assert client.get('/offerings/1234567/').status_code == 403
    client.get('/offerings')
    assert client.get('/offerings/1234567/').status_code == 200


def test_course_removed_since_sign_in_closes_after_offerings_page(seeded_db, login_as):
    _make_roles_stale(2)
    client = login_as(2)
    client.get('/offerings')
    assert client.get('/offerings/3456789/').status_code == 403


@pytest.fixture()
def canvas_signs_in_as_yu_long(app, monkeypatch):
    """Makes the OAuth callback succeed as Yu Long."""
    provider = app.extensions['seating_oauth_provider']
    monkeypatch.setattr(provider, 'authorize_access_token',
                        lambda: {'access_token': 'dev_access_token', 'user': FAKE_USERS['123456']})


def _saved_roles(canvas_id):
    user = User.query.filter_by(canvas_id=canvas_id).one()
    return user.staff_offerings, user.student_offerings


def test_first_sign_in_saves_roles(seeded_db, client, canvas_signs_in_as_yu_long):
    db.session.delete(db.session.get(User, 1))
    db.session.commit()
    assert client.get('/authorized/').status_code == 302
    assert _saved_roles('123456') == ({'1234567'}, {'4567890'})


def test_sign_in_updates_saved_roles(seeded_db, client, canvas_signs_in_as_yu_long):
    _make_roles_stale(1)
    assert client.get('/authorized/').status_code == 302
    assert _saved_roles('123456') == ({'1234567'}, {'4567890'})
