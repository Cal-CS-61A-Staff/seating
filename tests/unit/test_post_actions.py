"""
Deleting an exam, a room or a student, toggling an exam, hiding an offering and logging out take only
POST, and a post that another site made a signed-in browser send is refused (as in sections).
"""
import re
import time

import pytest

import server.services.canvas as canvas_client
from server.models import db, CanvasToken, Exam, Offering, Room, Student
from server.services.auth import SIGNED_IN_AT_KEY
from server.services.auth.after_login import NOT_DONE
from server.services.canvas.fake_data import FAKE_USERS
from server.typings.enum import AssignmentImportStrategy, MissingRowImportStrategy, NewRowImportStrategy, \
    UpdatedRowImportStrategy

OFFERING_URL = '/offerings/1234567/'
EXAM_URL = '/offerings/1234567/exams/midterm1'
# the test client's requests go to http://localhost
SAME_ORIGIN = 'http://localhost'
# same site, were the app served from a berkeley.edu subdomain, so SameSite=Lax cookies are sent
OTHER_SUBDOMAIN = 'https://evil.berkeley.edu'


def _room_id():
    return Room.query.filter_by(exam_id=1).order_by(Room.id).first().id


def _unchanged(action, url):
    """Whether what posting `action` to `url` would change is still as the seed left it."""
    return {
        'hide': lambda: not Offering.query.filter_by(canvas_id='1234567').one().is_hidden,
        'delete exam': lambda: db.session.get(Exam, 1) is not None,
        'toggle exam': lambda: not db.session.get(Exam, 1).is_active,
        'delete room': lambda: db.session.get(Room, int(url.rsplit('/', 2)[1])) is not None,
        'delete student': lambda: db.session.get(Student, 1) is not None,
    }[action]()


ACTIONS = {
    'hide': lambda: f'{OFFERING_URL}hide/',
    'delete exam': lambda: f'{EXAM_URL}/delete/',
    'toggle exam': lambda: f'{EXAM_URL}/toggle/',
    'delete room': lambda: f'{EXAM_URL}/rooms/{_room_id()}/delete',
    'delete student': lambda: f'{EXAM_URL}/students/1/delete',
}


@pytest.fixture
def seeded(seeded_db):
    # the seed exam starts inactive, so toggling it has a change to make
    db.session.get(Exam, 1).is_active = False
    db.session.add(Exam(offering_canvas_id='1234567', name='final', display_name='Final', is_active=True))
    db.session.commit()


@pytest.fixture
def staff(seeded, login_as):
    return login_as(1)


@pytest.mark.parametrize('action', ACTIONS)
def test_following_a_link_changes_nothing(staff, action):
    url = ACTIONS[action]()
    assert staff.get(url).status_code == 405
    db.session.expire_all()
    assert _unchanged(action, url)


@pytest.mark.parametrize('headers', [
    {'Sec-Fetch-Site': 'same-site', 'Origin': OTHER_SUBDOMAIN},
    {'Sec-Fetch-Site': 'cross-site', 'Origin': 'https://evil.example'},
    # browsers that send Origin but not Sec-Fetch-Site
    {'Origin': OTHER_SUBDOMAIN},
    {'Origin': 'https://localhost'},  # another scheme is another origin
    {'Origin': 'null'},  # e.g. from a sandboxed iframe
])
@pytest.mark.parametrize('action', ACTIONS)
def test_posts_from_another_site_are_refused(staff, action, headers):
    url = ACTIONS[action]()
    response = staff.post(url, headers=headers)
    assert response.status_code == 403
    assert 'came from another website' in response.get_data(as_text=True)
    db.session.expire_all()
    assert _unchanged(action, url)


@pytest.mark.parametrize('headers', [
    {'Sec-Fetch-Site': 'same-origin', 'Origin': SAME_ORIGIN},
    {'Origin': SAME_ORIGIN},  # browsers that don't send Sec-Fetch-Site
    # Sec-Fetch-Site decides when it's sent; "none" is a request the user made directly
    {'Sec-Fetch-Site': 'same-origin', 'Origin': 'https://evil.example'},
    {'Sec-Fetch-Site': 'none'},
    {},  # not from a browser, so there's no borrowed cookie
])
@pytest.mark.parametrize('action', ACTIONS)
def test_posts_from_this_app_make_the_change(staff, action, headers):
    url = ACTIONS[action]()
    assert staff.post(url, headers=headers).status_code == 302
    db.session.expire_all()
    assert not _unchanged(action, url)


def test_origin_matches_behind_cloud_run(staff):
    # Cloud Run terminates TLS and says so in X-Forwarded-Proto, which ProxyFix trusts, so a browser
    # without Sec-Fetch-Site sends an https Origin to what Flask sees as an http request
    response = staff.post(f'{EXAM_URL}/delete/', headers={'X-Forwarded-Proto': 'https', 'Origin': 'https://localhost'})
    assert response.status_code == 302
    assert db.session.get(Exam, 1) is None


def test_gets_from_another_site_are_not_refused(staff):
    # links from other sites, e.g. Canvas's redirect back after login, are GETs
    response = staff.get('/offerings', headers={'Sec-Fetch-Site': 'cross-site', 'Origin': 'https://evil.example'})
    assert response.status_code == 200


@pytest.mark.parametrize('page_url, action', [
    ('/offerings', 'hide'),
    (OFFERING_URL, 'delete exam'),
    (OFFERING_URL, 'toggle exam'),
    (f'{EXAM_URL}/', 'delete room'),
    (f'{EXAM_URL}/students/', 'delete student'),
])
def test_buttons_post(staff, page_url, action):
    page = staff.get(page_url).get_data(as_text=True)
    url = ACTIONS[action]()
    assert re.search(rf'<form method="POST" action="{re.escape(url)}"', page), \
        f'no form posting to {url} on {page_url}'


FORGED = {'Sec-Fetch-Site': 'same-site', 'Origin': OTHER_SUBDOMAIN}
SAME = {'Sec-Fetch-Site': 'same-origin'}


def _session(client):
    # read the session itself: the tests share one app context, so Flask-Login keeps the user it
    # loaded in g from one request to the next
    with client.session_transaction() as session:
        return dict(session)


@pytest.mark.parametrize('url', [
    '/offerings/new',
    f'{EXAM_URL}/students/remove_deleted_rooms/',
])
def test_other_posts_from_another_site_are_refused(staff, url):
    assert staff.post(url, headers=FORGED).status_code == 403


def test_a_csrf_token_does_not_get_a_post_from_another_site_through(staff):
    page = staff.get(f'{EXAM_URL}/edit/').get_data(as_text=True)
    csrf_token = re.search(r'name="csrf_token" type="hidden" value="([^"]+)"', page).group(1)
    data = {'csrf_token': csrf_token, 'display_name': 'Renamed', 'submit': 'y'}
    assert staff.post(f'{EXAM_URL}/edit/', data=data, headers=FORGED).status_code == 403
    db.session.expire_all()
    assert db.session.get(Exam, 1).display_name == 'Midterm 1'
    # the same post from this app goes through
    assert staff.post(f'{EXAM_URL}/edit/', data=data, headers=SAME).status_code == 302
    db.session.expire_all()
    assert db.session.get(Exam, 1).display_name == 'Renamed'


@pytest.mark.app_config(WTF_CSRF_ENABLED=False)  # the dev login form's own token is not what's tested
def test_other_sites_cannot_sign_users_in_as_someone_else(staff):
    # a dev login post starts a sign-in as the posted user (it is finished at /authorized/)
    other_user = next(user_id for user_id in FAKE_USERS if user_id != '123456')
    assert staff.post('/dev_login/', data={'user_id': other_user}, headers=FORGED).status_code == 403
    assert staff.post('/dev_login/', data={'user_id': other_user}, headers=SAME).status_code == 302


def test_other_sites_cannot_log_users_out(staff):
    assert staff.get('/logout/').status_code == 405
    assert staff.post('/logout/', headers=FORGED).status_code == 403
    assert _session(staff)['_user_id'] == '1'
    assert staff.post('/logout/', headers=SAME).status_code == 302
    assert '_user_id' not in _session(staff)


def test_logging_out_once_the_sign_in_has_expired(staff):
    # e.g. a tab left open past the sign-in limit: Log Out signs out, rather than sending the user
    # to sign in again, which Canvas may do without asking, leaving them signed in
    with staff.session_transaction() as session:
        session[SIGNED_IN_AT_KEY] = time.time() - 365 * 24 * 60 * 60
    response = staff.post('/logout/', headers=SAME)
    assert response.status_code == 302
    assert response.location == '/'
    assert _session(staff) == {}


def test_logging_out_once_the_sign_in_has_expired_revokes_the_token(seeded_db, client, canvas_signs_in, monkeypatch):
    revoked = []
    monkeypatch.setattr(canvas_client, 'revoke_token', revoked.append)
    _sign_in(client)
    assert CanvasToken.query.count() == 1
    with client.session_transaction() as session:
        session[SIGNED_IN_AT_KEY] = time.time() - 365 * 24 * 60 * 60
    assert client.post('/logout/', headers=SAME).location == '/'
    assert CanvasToken.query.count() == 0
    assert revoked == ['dev_access_token']


def test_logging_out_when_already_signed_out(seeded_db, client):
    response = client.post('/logout/', headers=SAME)
    assert response.status_code == 302
    assert response.location == '/'


@pytest.fixture
def canvas_signs_in(app, monkeypatch):
    """Makes the OAuth callback succeed as the fake Canvas user 123456 (user 1)."""
    provider = app.extensions['seating_oauth_provider']
    monkeypatch.setattr(provider, 'authorize_access_token',
                        lambda: {'access_token': 'dev_access_token', 'user': FAKE_USERS['123456']})


def _sign_in(client):
    """Signs in from /login/ through the OAuth callback, and returns where it sends the user."""
    # the fake Canvas's login page would show (and so use up) any flash, as Canvas's own wouldn't
    assert client.get('/login/').status_code == 302
    response = client.get('/authorized/')
    assert response.status_code == 302
    return response.location


@pytest.mark.parametrize('action', ACTIONS)
def test_pressing_a_button_once_signed_out_does_not_come_back_to_it(seeded, client, canvas_signs_in, action):
    # e.g. the page was left open past the idle limit: signing in again comes back with a GET, which
    # can't redo the post (and would be a 405), so it lands on the home page and says it wasn't done
    url = ACTIONS[action]()
    response = client.post(url, headers=SAME)
    assert response.location == '/login/'
    assert _sign_in(client) == '/'
    page = client.get('/', follow_redirects=True).get_data(as_text=True)
    assert NOT_DONE.replace("'", '&#39;') in page
    db.session.expire_all()
    assert _unchanged(action, url)


def test_posting_a_form_once_signed_out_does_not_come_back_to_it(seeded_db, client, canvas_signs_in):
    # login_required sends it to sign in, rather than a url converter
    assert client.post('/offerings/new', headers=SAME).location == '/login/'
    assert _sign_in(client) == '/'
    page = client.get('/', follow_redirects=True).get_data(as_text=True)
    assert NOT_DONE.replace("'", '&#39;') in page


@pytest.mark.app_config(MOCK_CANVAS=False)
def test_posting_without_a_canvas_token_does_not_come_back_to_it(staff):
    # signed in to the app, but the session has no Canvas token to call Canvas with
    with staff.session_transaction() as session:
        session['after_login'] = f'http://localhost{EXAM_URL}/students/'
    assert staff.post('/offerings/new', headers=SAME).location == '/login/'
    session = _session(staff)
    assert 'after_login' not in session
    assert session['_flashes'] == [('warning', NOT_DONE)]


@pytest.mark.app_config(MOCK_CANVAS=False, WTF_CSRF_ENABLED=False)
def test_importing_the_roster_without_a_canvas_token_asks_to_sign_in(staff):
    # the view's catch-all for import errors must not swallow the redirect to sign in
    data = {
        'assignment_import_strategy': AssignmentImportStrategy.REVALIDATE.value,
        'updated_student_info_import_strategy': UpdatedRowImportStrategy.MERGE.value,
        'updated_preference_import_strategy': UpdatedRowImportStrategy.MERGE.value,
        'new_student_import_strategy': NewRowImportStrategy.APPEND.value,
        'missing_student_import_strategy': MissingRowImportStrategy.IGNORE.value,
        'submit': 'y',
    }
    response = staff.post(f'{EXAM_URL}/students/import/from_canvas_roster/', data=data, headers=SAME)
    assert response.location == '/login/'
    assert _session(staff)['_flashes'] == [('warning', NOT_DONE)]


def test_a_page_opened_earlier_is_not_returned_to_after_a_post(seeded_db, client, canvas_signs_in):
    client.get(f'{EXAM_URL}/students/')
    client.post(f'{EXAM_URL}/students/1/delete', headers=SAME)
    assert _sign_in(client) == '/'


def test_opening_a_page_once_signed_out_comes_back_to_it(seeded_db, client, canvas_signs_in):
    assert client.get(f'{EXAM_URL}/students/').location == '/login/'
    assert _sign_in(client) == f'http://localhost{EXAM_URL}/students/'
    page = client.get(f'{EXAM_URL}/students/').get_data(as_text=True)
    assert NOT_DONE.replace("'", '&#39;') not in page


def test_a_post_from_another_site_while_signed_out_leaves_the_session_alone(seeded_db, client):
    # the URL converters ask for a sign-in before the cross-origin check refuses the post
    page = f'http://localhost{EXAM_URL}/students/'
    with client.session_transaction() as session:
        session['after_login'] = page
    assert client.post(f'{EXAM_URL}/delete/', headers=FORGED).status_code == 403
    session = _session(client)
    assert session['after_login'] == page
    assert '_flashes' not in session


@pytest.mark.parametrize('method', ['HEAD', 'OPTIONS'])
def test_head_and_options_while_signed_out_leave_the_session_alone(seeded_db, client, method):
    # a page, which a GET would remember to come back to
    client.open(f'{EXAM_URL}/students/', method=method)
    session = _session(client)
    assert 'after_login' not in session and '_flashes' not in session


def test_a_fetch_while_signed_out_flashes_nothing(seeded_db, client):
    # the email page previews and sends with fetch(), which would never show the flash
    for _ in range(3):
        client.post(f'{EXAM_URL}/students/email/preview/', headers={**SAME, 'Sec-Fetch-Mode': 'cors'})
    assert '_flashes' not in _session(client)


def test_pressing_buttons_while_signed_out_says_so_once(seeded_db, client):
    for _ in range(3):
        client.post(f'{EXAM_URL}/students/1/delete', headers={**SAME, 'Sec-Fetch-Mode': 'navigate'})
    assert _session(client)['_flashes'] == [('warning', NOT_DONE)]


def test_a_link_from_another_site_while_signed_out_comes_back_to_its_page(seeded_db, client, canvas_signs_in):
    # e.g. a link from Canvas
    response = client.get(f'{EXAM_URL}/students/', headers={'Sec-Fetch-Site': 'cross-site'})
    assert response.location == '/login/'
    assert _sign_in(client) == f'http://localhost{EXAM_URL}/students/'
