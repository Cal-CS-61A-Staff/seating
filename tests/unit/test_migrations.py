"""
The migrations build the schema the models describe, both on a new database and on one made
by `create_all` before migrations existed.
"""
import argparse
import os

import alembic.command
import pytest
import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from flask_migrate import downgrade, upgrade

import config
from server.application import MIGRATIONS_DIR, create_app
from server.models import db


@pytest.fixture()
def migrations_app(tmp_path):
    """An app on its own empty SQLite database, so the tests can run the migrations on it."""
    class Config(config.DevelopmentConfig):
        SQLALCHEMY_DATABASE_URI = f'sqlite:///{tmp_path / "migrations.db"}'

    app = create_app(Config)
    with app.app_context():
        yield app
        db.session.remove()
        db.engine.dispose()


def sql(statement, **params):
    with db.engine.begin() as connection:
        result = connection.execute(sa.text(statement), params)
        return result.all() if result.returns_rows else None


def schema_differences():
    with db.engine.connect() as connection:
        return compare_metadata(MigrationContext.configure(connection), db.metadata)


def tables():
    return set(sa.inspect(db.engine).get_table_names())


def test_new_database_matches_the_models(migrations_app):
    """A database built by the migrations is exactly what the models describe, so a model
    change needs a migration."""
    upgrade()
    assert schema_differences() == []


def test_database_from_before_migrations_keeps_its_data(migrations_app):
    """An older database built with create_all, without the newer table and columns, gets
    them, and keeps its rows."""
    db.create_all()
    sql('DROP TABLE canvas_tokens')
    sql('ALTER TABLE offerings DROP COLUMN is_hidden')
    sql('ALTER TABLE students DROP COLUMN canvas_sid')
    sql("INSERT INTO offerings (id, canvas_id, name, code, start_at) VALUES (1, '101', 'CS 1', 'CS1', '2026')")

    upgrade()

    assert schema_differences() == []
    assert sql('SELECT canvas_id, is_hidden FROM offerings') == [('101', False)]
    assert sql('SELECT version_num FROM alembic_version') == [('0001_baseline',)]


def test_missing_required_column_is_refused(migrations_app):
    """A column that can't be added without a value stops the upgrade, rather than being left
    out or filled in with a guess. (`flask db upgrade` then exits with 1, so a deploy doesn't
    start.)"""
    db.create_all()
    sql('ALTER TABLE offerings DROP COLUMN code')

    # alembic itself, so the error isn't turned into an exit by Flask-Migrate
    alembic_config = migrations_app.extensions['migrate'].migrate.get_config()
    with pytest.raises(RuntimeError, match='offerings.code is missing'):
        alembic.command.upgrade(alembic_config, 'head')
    # not recorded as done, so the next upgrade tries again
    assert sql('SELECT version_num FROM alembic_version') == []


def test_database_already_up_to_date_is_only_stamped(migrations_app):
    db.create_all()
    sql("INSERT INTO offerings (id, canvas_id, name, code, start_at, is_hidden) "
        "VALUES (1, '101', 'CS 1', 'CS1', '2026', 1)")

    upgrade()

    assert schema_differences() == []
    assert sql('SELECT is_hidden FROM offerings') == [(True,)]


def test_downgrade_removes_every_table(migrations_app):
    upgrade()
    downgrade(revision='base')
    assert tables() == {'alembic_version'}


def test_resetdb_builds_the_database_again(migrations_app):
    upgrade()
    runner = migrations_app.test_cli_runner()

    result = runner.invoke(args=['dropdb'], input='y\n')
    assert result.exit_code == 0, result.output
    assert tables() == set()

    result = runner.invoke(args=['initdb'])
    assert result.exit_code == 0, result.output
    assert schema_differences() == []
    assert sql('SELECT version_num FROM alembic_version') == [('0001_baseline',)]


def autogenerate(app, version_path):
    """What `flask db migrate` writes, into version_path rather than the repository."""
    alembic_config = app.extensions['migrate'].migrate.get_config()
    alembic_config.set_main_option('path_separator', 'os')
    alembic_config.set_main_option(
        'version_locations', os.pathsep.join([os.path.join(MIGRATIONS_DIR, 'versions'), str(version_path)]))
    # as `flask db migrate` sets them, which env.py reads
    alembic_config.cmd_opts = argparse.Namespace(autogenerate=True)
    alembic.command.revision(alembic_config, message='change', autogenerate=True, version_path=str(version_path))
    return [path.read_text() for path in version_path.glob('*.py')]


def test_autogenerate_writes_nothing_without_a_change(migrations_app, tmp_path):
    upgrade()
    assert autogenerate(migrations_app, tmp_path) == []


def test_autogenerate_writes_string_sets_as_text(migrations_app, tmp_path):
    """So a generated migration doesn't import server.models."""
    upgrade()
    sql('ALTER TABLE students DROP COLUMN wants')
    sql('ALTER TABLE students DROP COLUMN sid')

    [migration] = autogenerate(migrations_app, tmp_path)

    assert "sa.Column('wants', sa.Text(), nullable=False)" in migration
    assert "sa.Column('sid', sa.String(length=255), nullable=True)" in migration
    assert 'server.models' not in migration


def test_offline_upgrade_writes_the_sql_for_every_table(migrations_app, capsys):
    """`flask db upgrade --sql` prints the SQL without touching the database."""
    upgrade(sql=True)
    printed = capsys.readouterr().out
    for table in ('offerings', 'users', 'canvas_tokens', 'exams', 'rooms', 'students', 'seats', 'seat_assignments'):
        assert f'CREATE TABLE {table} ' in printed
    assert tables() == set()
