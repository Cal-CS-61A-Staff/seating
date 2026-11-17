import os
import subprocess
import time
from contextlib import contextmanager

import pytest
import responses

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from config import TestingConfig
from server.application import create_app
from server.models import db as sqlalchemy_db
from server.services.auth import SIGNED_IN_AT_KEY
from tests.fixtures import seed_db


def pytest_configure(config):
    config.addinivalue_line('markers', 'app_config(**settings): build the test\'s app with these settings')


@pytest.fixture()
def app_config(request):
    """
    The config each test's app is built with: TestingConfig, plus the settings of any
    @pytest.mark.app_config(...) on the test, its class or its module.
    """
    app_config = TestingConfig()
    # closest first, so apply them in reverse for a test's own settings to win
    for marker in reversed(list(request.node.iter_markers('app_config'))):
        for key, value in marker.kwargs.items():
            setattr(app_config, key, value)
    return app_config


@pytest.fixture()
def app(app_config):
    """A new app for each test, so settings never carry over from one test to the next."""
    app = create_app(app_config)
    yield app
    # each app has its own database engine: close its connections
    with app.app_context():
        sqlalchemy_db.session.remove()
        for engine in sqlalchemy_db.engines.values():
            engine.dispose()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def runner(app):
    return app.test_cli_runner()


@pytest.fixture()
def db(app):
    with app.app_context():
        sqlalchemy_db.drop_all()
        sqlalchemy_db.create_all()

        yield sqlalchemy_db

        sqlalchemy_db.session.remove()


@pytest.fixture()
def mocker():
    with responses.RequestsMock() as rsps:
        yield rsps


@contextmanager
def flask_server():
    import requests
    TIMEOUT = 5
    # the tests seed TestingConfig's database, so the server must serve that config too
    server = subprocess.Popen(['coverage', 'run', '--source', 'server', '-m', 'flask', 'run'],
                              env={**os.environ, 'FLASK_ENV': 'testing'})
    start_time = time.time()
    while True:
        try:
            response = requests.get(TestingConfig().SERVER_BASE_URL)
            if response.status_code < 400:
                break
        except requests.ConnectionError:
            if time.time() - start_time > TIMEOUT:
                raise TimeoutError("Flask server did not start within 5 seconds")
            time.sleep(0.5)

    try:
        yield
    finally:
        server.terminate()


def chrome_driver(*arguments):
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    for argument in arguments:
        options.add_argument(argument)
    return webdriver.Chrome(options=options)


@pytest.fixture()
def start_flask_app():
    with flask_server():
        yield


@pytest.fixture()
def driver(start_flask_app):
    driver = chrome_driver()
    yield driver
    driver.close()


@pytest.fixture()
def get_authed_driver(driver):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    def _get_authed_driver(some_user_id):
        driver.get('http://localhost:5000/login')
        assert 'Login' in driver.title
        user_id_input = driver.find_element(By.CSS_SELECTOR, '#user_id')
        assert user_id_input is not None
        user_id_input.send_keys(some_user_id)
        form_submit_btn = driver.find_element(By.CSS_SELECTOR, '#submit')
        assert form_submit_btn is not None
        form_submit_btn.click()
        # The click kicks off a redirect chain (dev_login -> oauth -> /authorized/ -> / -> /offerings);
        # wait for it to land on the offerings page before handing the driver to the test.
        wait = WebDriverWait(driver, 10)
        wait.until(EC.url_to_be('http://localhost:5000/offerings'))
        wait.until(lambda d: d.execute_script('return document.readyState') == 'complete')
        return driver

    yield _get_authed_driver


@pytest.fixture()
def seeded_db(app):
    with app.app_context():
        sqlalchemy_db.drop_all()
        sqlalchemy_db.create_all()

        seed_db()

        yield sqlalchemy_db

        sqlalchemy_db.session.expunge_all()


@pytest.fixture()
def login_as(client):
    """Signs the test client in as the user with the given id, skipping Canvas OAuth."""
    def _login_as(user_id):
        with client.session_transaction() as sess:
            sess['_user_id'] = str(user_id)
            sess['_fresh'] = True
            sess[SIGNED_IN_AT_KEY] = time.time()
        return client

    return _login_as
