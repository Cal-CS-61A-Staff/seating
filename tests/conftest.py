import os

import pytest
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
def driver():
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    driver = webdriver.Chrome(options=options)
    yield driver
    driver.close()


@flask_app.cli.command('e2e')
def run_e2e():
    print('Running end-to-end tests...')
    pytest.main(['-s', 'tests/e2e'])


@flask_app.cli.command('unit')
def run_unit():
    print('Running unit tests...')
    pytest.main(['-s', 'tests/unit'])


@flask_app.cli.command('test')
def run_all():
    print('Running all tests...')
    pytest.main(['-s', 'tests'])


@flask_app.cli.command('cov')
def run_cov():
    print('Running all tests with coverage...')
    pytest.main(['-s', '--cov=server', 'tests'])


@flask_app.cli.command('audit')
def run_audit():
    print('Checking for broken dependencies...')
    os.system('pip check')
    print('Checking for outdated dependencies...')
    os.system('pip list --outdated')
    print('Auditing with pip-audit...')
    os.system('pip-audit')
    print('Auditing with safety...')
    os.system('safety check')


@flask_app.cli.command('lint')
def run_lint():
    print('Running flake8 linter...')
    os.system('flake8 server tests')
