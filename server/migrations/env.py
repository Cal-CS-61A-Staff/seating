import logging
from logging.config import fileConfig

from flask import current_app

from alembic import context
from sqlalchemy import text

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
# Keep the app's loggers working: fileConfig disables every logger that already
# exists unless told not to, and the tests and server.seed run migrations in the
# same process as the app.
fileConfig(config.config_file_name, disable_existing_loggers=False)
logger = logging.getLogger('alembic.env')


def get_engine():
    return current_app.extensions['migrate'].db.engine


def get_engine_url():
    return get_engine().url.render_as_string(hide_password=False).replace('%', '%%')


# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
config.set_main_option('sqlalchemy.url', get_engine_url())
target_db = current_app.extensions['migrate'].db

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def get_metadata():
    return target_db.metadata


def render_item(type_, obj, autogen_context):
    """Writes the models' StringSet columns as Text in generated migrations, so a
    migration doesn't import server.models (which can change after it's written)."""
    from server.models import StringSet
    if type_ == "type" and isinstance(obj, StringSet):
        return "sa.Text()"
    return False


def run_migrations_offline():
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url, target_metadata=get_metadata(), literal_binds=True
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    # this callback is used to prevent an auto-migration from being generated
    # when there are no changes to the schema
    # reference: http://alembic.zzzcomputing.com/en/latest/cookbook.html
    def process_revision_directives(context, revision, directives):
        if getattr(config.cmd_opts, 'autogenerate', False):
            script = directives[0]
            if script.upgrade_ops.is_empty():
                directives[:] = []
                logger.info('No changes in schema detected.')

    # a copy, so these callbacks (which read this run's config) aren't kept for the next
    # command run in the same process, such as in the tests
    conf_args = dict(current_app.extensions['migrate'].configure_args)
    conf_args.setdefault("process_revision_directives", process_revision_directives)
    conf_args.setdefault("render_item", render_item)

    connectable = get_engine()

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=get_metadata(),
            **conf_args
        )

        with context.begin_transaction():
            # Several Cloud Run instances can start at once; the first takes this
            # lock and migrates, and the rest wait, then find nothing to do. (The
            # tests use SQLite, so they never take it.)
            if connection.dialect.name == "postgresql":  # pragma: no cover
                connection.execute(text("SELECT pg_advisory_xact_lock(724501)"))
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
