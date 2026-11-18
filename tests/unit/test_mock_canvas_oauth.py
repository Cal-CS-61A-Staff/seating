"""
The fake Canvas OAuth endpoints behind the dev login must only work with the fake Canvas,
and must only send the browser back to this app.
"""
import pytest

AUTH_URL = '/dev_login/oauth2/auth/'
TOKEN_URL = '/dev_login/oauth2/token/'
CALLBACK = 'http://localhost/authorized/'


real_canvas = pytest.mark.app_config(MOCK_CANVAS=False)


def test_authorize_redirects_to_own_callback(client):
    response = client.get(AUTH_URL, query_string={'redirect_uri': CALLBACK, 'state': 'abc', 'user_id': '123456'})
    assert response.status_code == 302
    assert response.headers['Location'] == '/authorized/?code=123456&state=abc'


def test_authorize_encodes_query_values(client):
    response = client.get(AUTH_URL, query_string={'redirect_uri': CALLBACK, 'state': 'a&b', 'user_id': '1#x'})
    assert response.status_code == 302
    assert response.headers['Location'] == '/authorized/?code=1%23x&state=a%26b'


@pytest.mark.parametrize('redirect_uri', [
    'https://evil.example/authorized/',
    'https://evil.example/',
    '//evil.example/authorized/',
    'http://localhost.evil.example/authorized/',
    'http://localhost/offerings',
    'javascript:alert(1)',
    '/authorized/',
])
def test_authorize_rejects_other_redirects(client, redirect_uri):
    response = client.get(AUTH_URL, query_string={'redirect_uri': redirect_uri, 'state': 'abc', 'user_id': '123456'})
    assert response.status_code == 400
    assert 'Location' not in response.headers


def test_authorize_requires_redirect_uri(client):
    assert client.get(AUTH_URL, query_string={'state': 'abc', 'user_id': '123456'}).status_code == 400


def test_token_returns_fake_user(client):
    response = client.post(TOKEN_URL, data={'code': '123456'})
    assert response.status_code == 200
    assert response.get_json()['user']['name'] == 'Yu Long'


@real_canvas
def test_authorize_is_hidden_with_real_canvas(client):
    response = client.get(AUTH_URL, query_string={'redirect_uri': CALLBACK, 'state': 'abc', 'user_id': '123456'})
    assert response.status_code == 404


@real_canvas
def test_token_is_hidden_with_real_canvas(client):
    assert client.post(TOKEN_URL, data={'code': '123456'}).status_code == 404


@real_canvas
def test_dev_login_page_still_redirects_home_with_real_canvas(client):
    response = client.get('/dev_login/')
    assert response.status_code == 302
    assert '/dev_login' not in response.headers['Location']
