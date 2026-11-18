import click
import flask_migrate
from sqlalchemy import text

from server.models import db, Exam
from flask.cli import with_appcontext
from tests.fixtures import seed_db as _seed_db


@click.command('initdb')
@with_appcontext
def init_db():
    """
    Initializes the database by applying every migration (the same as `flask db upgrade`)
    """
    click.echo('Creating database...')
    flask_migrate.upgrade()


@click.command('dropdb')
@with_appcontext
def drop_db():
    """
    Drops all tables from the database
    """
    doit = click.confirm('Are you sure you want to delete all data?')
    if doit:
        click.echo('Dropping database...')
        db.drop_all()
        # and the migration record, so initdb builds the tables again
        with db.engine.begin() as connection:
            connection.execute(text('DROP TABLE IF EXISTS alembic_version'))


@click.command('seeddb')
@with_appcontext
def seed_db():
    """
    Seeds the database with data
    There is no need to seed even in development, since the database is
    dynamically populated when app launches, see stub.py
    """
    click.echo('Seeding database...')
    _seed_db()


@click.command('resetdb')
@with_appcontext
@click.pass_context
def reset_db(ctx):
    "Drops, initializes, then seeds tables with data"
    ctx.invoke(drop_db)
    ctx.invoke(init_db)
    ctx.invoke(seed_db)


@click.command('cleanroomprefs')
@with_appcontext
@click.option('--dry-run', is_flag=True, help='Report what would change without saving it.')
def clean_room_prefs(dry_run):
    """
    Removes ids of deleted rooms from every student's room wants/avoids
    """
    total = 0
    for exam in Exam.query.all():
        changed = exam.remove_unknown_room_preferences()
        if changed:
            click.echo(f'{exam.offering_canvas_id}/{exam.name}: {changed} students')
            total += changed
    if dry_run:
        db.session.rollback()
        click.echo(f'Dry run: would update {total} students.')
    else:
        db.session.commit()
        click.echo(f'Updated {total} students.')
