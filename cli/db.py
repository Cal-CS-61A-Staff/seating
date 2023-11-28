import click

from server.models import db
from server import app
from tests.fixtures import seed_db as _seed_db


@app.cli.command('initdb')
def init_db():
    """
    Initializes the database
    """
    click.echo('Creating database...')
    db.create_all()
    db.session.commit()


@app.cli.command('dropdb')
def drop_db():
    """
    Drops all tables from the database
    """
    doit = click.confirm('Are you sure you want to delete all data?')
    if doit:
        click.echo('Dropping database...')
        db.drop_all()


@app.cli.command('seeddb')
def seed_db():
    """
    Seeds the database with data
    There is no need to seed even in development, since the database is
    dynamically populated when app launches, see stub.py
    """
    click.echo('Seeding database...')
    _seed_db()


@app.cli.command('resetdb')
@click.pass_context
def reset_db(ctx):
    "Drops, initializes, then seeds tables with data"
    ctx.invoke(drop_db)
    ctx.invoke(init_db)
    ctx.invoke(seed_db)
