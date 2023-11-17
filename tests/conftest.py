import os

import pytest
import responses
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from server import app as flask_app
from server.models import db as sqlalchemy_db


@pytest.fixture()
def app():
    yield flask_app


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
        sqlalchemy_db.drop_all()


@pytest.fixture()
def mocker():
    with responses.RequestsMock() as rsps:
        yield rsps


@pytest.fixture()
def driver():
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    driver = webdriver.Chrome(options=options)
    yield driver
    driver.close()


@pytest.fixture()
def get_authed_driver(driver):
    from selenium.webdriver.common.by import By

    def _get_authed_driver(some_user_id):
        # TODO: some_user_id is not used yet;
        # we need to first set up seeding data for mock users
        # and have a way to identify then by certain id
        # for now, we just use the first user in the list
        driver.get('http://localhost:5000/')
        first_dev_login_btn = driver.find_element(By.CSS_SELECTOR, '.form-buttons .mdl-button')
        assert first_dev_login_btn is not None
        first_dev_login_btn.click()
        return driver

    yield _get_authed_driver
