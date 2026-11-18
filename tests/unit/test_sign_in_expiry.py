"""
Canvas roles are saved at sign-in (and when /offerings loads), so a sign-in must not last long: no remember cookie, and a
session whose sign-in is older than SIGN_IN_MAX_AGE (or has no sign-in time) is signed out.
"""
import time

import pytest

from server.services.auth import DEFAULT_SIGN_IN_MAX_AGE, SIGNED_IN_AT_KEY
from server.services.canvas.fake_data import FAKE_USERS

STAFF_ID = '123456'


@pytest.fixture()
def canvas_signs_in(app, monkeypatch):
    """Makes the OAuth callback succeed as the fake Canvas user STAFF_ID."""
    provider = app.extensions['seating_oauth_provider']
    monkeypatch.setattr(provider, 'authorize_access_token',
                        lambda: {'access_token': 'dev_access_token', 'user': FAKE_USERS[STAFF_ID]})


def _signed_in_at(client, when):
    with client.session_transaction() as sess:
        if when is None:
            sess.pop(SIGNED_IN_AT_KEY, None)
        else:
            sess[SIGNED_IN_AT_KEY] = when


def _is_signed_in(client):
    return client.get('/offerings').status_code == 200


def test_sign_in_sets_no_remember_cookie(seeded_db, client, canvas_signs_in):
    before = time.time()
    response = client.get('/authorized/')
    assert response.status_code == 302
    assert not any(h.startswith('remember_token=') for h in response.headers.getlist('Set-Cookie'))
    with client.session_transaction() as sess:
        assert sess.permanent
        assert before <= sess[SIGNED_IN_AT_KEY] <= time.time()
    assert _is_signed_in(client)


def test_recent_sign_in_is_kept(seeded_db, login_as):
    client = login_as(1)
    _signed_in_at(client, time.time() - DEFAULT_SIGN_IN_MAX_AGE + 60)
    assert _is_signed_in(client)


@pytest.mark.parametrize('when', [
    time.time() - DEFAULT_SIGN_IN_MAX_AGE - 60,
    None,  # sessions and remember cookies from before the sign-in time was kept
    'yesterday',
])
def test_old_or_unknown_sign_in_must_sign_in_again(seeded_db, login_as, when):
    client = login_as(1)
    _signed_in_at(client, when)
    response = client.get('/offerings')
    assert response.status_code == 302
    assert response.location == '/login/'


@pytest.mark.app_config(SIGN_IN_MAX_AGE=60)
def test_max_age_comes_from_config(seeded_db, login_as):
    client = login_as(1)
    _signed_in_at(client, time.time() - 120)
    assert not _is_signed_in(client)


def test_sign_in_max_age_env_var(monkeypatch):
    import config
    monkeypatch.setenv('SIGN_IN_MAX_AGE', '3600')
    assert config.TestingConfig().SIGN_IN_MAX_AGE == 3600
