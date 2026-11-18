"""
Requests are refused, with a reason, while the database's migrations don't match the code's:
most often a PR preview whose PR adds a migration.
"""
from unittest.mock import patch

import pytest
import sqlalchemy as sa
from alembic.script import ScriptDirectory
from flask_migrate import upgrade

import config
from server.application import MIGRATIONS_DIR, create_app
from server.models import db

HEAD = ScriptDirectory(MIGRATIONS_DIR).get_current_head()


@pytest.fixture()
def checked_app(tmp_path):
    """A development app, which checks the schema, on its own empty SQLite database."""
    class Config(config.DevelopmentConfig):
        SQLALCHEMY_DATABASE_URI = f'sqlite:///{tmp_path / "schema.db"}'

    app = create_app(Config)
    with app.app_context():
        yield app
        db.session.remove()
        db.engine.dispose()


@pytest.fixture()
def checked_client(checked_app):
    return checked_app.test_client()


def set_revision(revision):
    with db.engine.begin() as connection:
        connection.execute(sa.text('UPDATE alembic_version SET version_num = :rev'), {'rev': revision})


def test_matching_schema_serves_requests(checked_client):
    upgrade()
    response = checked_client.get('/health/')
    assert response.status_code == 200
    assert checked_client.get('/').status_code != 503


def test_preview_of_a_pr_with_a_migration_says_to_merge(checked_client, monkeypatch):
    monkeypatch.setenv('PREVIEW_PR', '42')
    response = checked_client.get('/')
    assert response.status_code == 503
    message = response.get_data(as_text=True)
    assert f'This is a preview of PR #42, which adds a database migration ({HEAD}).' in message
    assert 'Merge the PR to see its changes on staging.' in message


def test_health_is_refused_too(checked_client, monkeypatch):
    """So a deploy whose database is behind doesn't look healthy."""
    monkeypatch.setenv('PREVIEW_PR', '42')
    assert checked_client.get('/health/').status_code == 503


def test_static_files_are_served(checked_client):
    with checked_client.get('/static/css/style.css') as response:
        assert response.status_code != 503


def test_preview_older_than_the_database_says_to_merge_main(checked_client, monkeypatch):
    upgrade()
    set_revision('0099_from_main')
    monkeypatch.setenv('PREVIEW_PR', '42')
    message = checked_client.get('/').get_data(as_text=True)
    assert 'whose branch is older than the staging database (at migration 0099_from_main)' in message
    assert "Merge main into the PR's branch" in message


def test_database_ahead_outside_previews(checked_client, monkeypatch):
    upgrade()
    set_revision('0099_from_main')
    monkeypatch.delenv('PREVIEW_PR', raising=False)
    message = checked_client.get('/').get_data(as_text=True)
    assert "The database is at migration 0099_from_main, which this version of Seating doesn't have." in message


def test_outside_previews_says_to_upgrade(checked_client, monkeypatch):
    monkeypatch.delenv('PREVIEW_PR', raising=False)
    message = checked_client.get('/').get_data(as_text=True)
    assert (f'The database is at migration none, but this version of Seating expects {HEAD}. '
            f'Run `flask db upgrade`') in message


def test_result_is_cached_briefly(checked_client):
    assert checked_client.get('/health/').status_code == 503
    upgrade()
    # still the cached result...
    assert checked_client.get('/health/').status_code == 503
    # ...until it expires
    with patch('server.schema_check.time.monotonic', return_value=10 ** 9):
        assert checked_client.get('/health/').status_code == 200


def test_unreachable_database_lets_the_request_through(checked_client):
    with patch('server.schema_check.schema_problem', side_effect=RuntimeError('no database')):
        assert checked_client.get('/health/').status_code == 200


def test_testing_apps_are_not_checked(tmp_path):
    """Test apps build their tables with create_all, so they have no migration to check."""
    class Config(config.TestingConfig):
        SQLALCHEMY_DATABASE_URI = f'sqlite:///{tmp_path / "unchecked.db"}'

    app = create_app(Config)
    assert app.test_client().get('/health/').status_code == 200
