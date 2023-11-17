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
        driver.get('http://localhost:5000/')
        assert 'Login' in driver.title
        user_id_input = driver.find_element(By.CSS_SELECTOR, '#user_id')
        assert user_id_input is not None
        user_id_input.send_keys(some_user_id)
        form_submit_btn = driver.find_element(By.CSS_SELECTOR, '#submit')
        assert form_submit_btn is not None
        form_submit_btn.click()
        return driver

    yield _get_authed_driver
