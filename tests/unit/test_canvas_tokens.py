"""
The Canvas access token is kept in the canvas_tokens table, not the session cookie. The cookie holds only
a random handle, whose hash finds the row. Signing out, or in again, deletes the row and revokes the token.
"""
import hashlib
import time

import pytest
import requests

import server.services.canvas as canvas_client
from server.models import CanvasToken, User, db
from server.services.auth import canvas_tokens
from server.services.auth.canvas_tokens import LEGACY_SESSION_KEY, SESSION_KEY
from server.services.canvas.fake_data import FAKE_USERS

STAFF_ID = '123456'


@pytest.fixture()
def canvas_signs_in(app, monkeypatch):
    """Makes the OAuth callback succeed as the fake Canvas user STAFF_ID, with a new token each time."""
    provider = app.extensions['seating_oauth_provider']
    issued = iter(f'token-{i}' for i in range(100))
    monkeypatch.setattr(provider, 'authorize_access_token',
                        lambda: {'access_token': next(issued), 'expires_in': 3600, 'user': FAKE_USERS[STAFF_ID]})


@pytest.fixture()
def revoked(monkeypatch):
    """Records the tokens revoked with Canvas."""
    tokens = []
    monkeypatch.setattr(canvas_client, 'revoke_token', tokens.append)
    return tokens


def _session(client):
    with client.session_transaction() as sess:
        return dict(sess)


def test_sign_in_keeps_the_token_on_the_server(seeded_db, client, canvas_signs_in):
    assert client.get('/authorized/').status_code == 302
    sess = _session(client)
    assert 'token-0' not in sess.values()
    assert LEGACY_SESSION_KEY not in sess
    row = CanvasToken.query.one()
    assert row.access_token == 'token-0'
    assert row.handle_hash == hashlib.sha256(sess[SESSION_KEY].encode()).hexdigest()
    assert row.user_id == User.query.filter_by(canvas_id=STAFF_ID).one().id
    assert time.time() + 3500 < row.expires_at <= time.time() + 3600


def test_logout_deletes_and_revokes_the_token(seeded_db, client, canvas_signs_in, revoked):
    client.get('/authorized/')
    stolen_cookie = _session(client)
    assert client.get('/logout/').status_code == 302
    assert CanvasToken.query.count() == 0
    assert revoked == ['token-0']
    # a copy of the cookie from before logout no longer finds a token
    with client.application.test_request_context():
        from flask import session
        session.update(stolen_cookie)
        assert canvas_tokens._this_browsers_row() is None


def test_signing_in_again_replaces_the_token(seeded_db, client, canvas_signs_in, revoked):
    client.get('/authorized/')
    client.get('/authorized/')
    assert [r.access_token for r in CanvasToken.query.all()] == ['token-1']
    assert revoked == ['token-0']


def test_expired_tokens_are_not_revoked_and_are_purged(seeded_db, client, canvas_signs_in, revoked):
    client.get('/authorized/')
    CanvasToken.query.update({'expires_at': int(time.time()) - 1})
    db.session.commit()
    client.get('/logout/')
    assert revoked == []

    db.session.add(CanvasToken(user_id=1, handle_hash='0' * 64, access_token='old', expires_at=1))
    db.session.commit()
    client.get('/authorized/')
    assert [r.access_token for r in CanvasToken.query.all()] == ['token-1']


def _current_token(app, sess, user_id):
    from flask import session
    from flask_login import login_user
    with app.test_request_context():
        session.update(sess)
        login_user(db.session.get(User, user_id))
        return canvas_tokens.current_token()


def test_current_token(seeded_db, app, client, canvas_signs_in):
    client.get('/authorized/')
    sess = _session(client)
    user_id = CanvasToken.query.one().user_id
    assert _current_token(app, sess, user_id) == 'token-0'
    # another user signed in with this handle doesn't get the token
    other = User.query.filter(User.id != user_id).first()
    assert _current_token(app, sess, other.id) is None
    # nor does anyone once it is about to expire
    CanvasToken.query.update({'expires_at': int(time.time()) + 30})
    db.session.commit()
    assert _current_token(app, sess, user_id) is None


def test_legacy_token_is_dropped_from_the_cookie(seeded_db, login_as):
    client = login_as(1)
    with client.session_transaction() as sess:
        sess[LEGACY_SESSION_KEY] = 'old-token'
    client.get('/')
    assert LEGACY_SESSION_KEY not in _session(client)


@pytest.fixture()
def real_canvas(app):
    """Uses the real Canvas client in this test's app (a new app each test, so no need to undo it)."""
    app.config['MOCK_CANVAS'] = False
    app.config['CANVAS_SERVER_URL'] = 'https://canvas.example.edu/'


def test_revoke_token_asks_canvas(app, real_canvas, monkeypatch):
    calls = []

    class Response:
        def raise_for_status(self):
            pass

    def delete(url, **kwargs):
        calls.append((url, kwargs['headers']))
        return Response()

    monkeypatch.setattr(requests, 'delete', delete)
    with app.app_context():
        canvas_client.revoke_token('abc')
    assert calls == [('https://canvas.example.edu/login/oauth2/token', {'Authorization': 'Bearer abc'})]


def test_revoke_token_tolerates_canvas_being_down(app, real_canvas, monkeypatch):
    def delete(url, **kwargs):
        raise requests.ConnectionError('down')

    monkeypatch.setattr(requests, 'delete', delete)
    with app.app_context():
        canvas_client.revoke_token('abc')
