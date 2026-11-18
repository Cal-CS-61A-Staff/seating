"""
Refuses requests while the database's schema doesn't match the code's migrations, with a
message saying why, instead of failing on the first query that uses a missing column.

The usual cause is a PR preview whose PR adds a migration: previews share the staging
database and never run migrations (see the Dockerfile), so the migration only reaches that
database once the PR is merged and staging deploys.
"""
import os
import time

from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from flask import current_app, request

from server.models import db

# How long to trust a result, so most requests don't query the database for it.
CACHE_SECONDS = 60


def schema_problem(migrations_dir):
    """Why the database doesn't match the code's migrations, or None if it does."""
    script = ScriptDirectory(migrations_dir)
    code_heads = set(script.get_heads())
    with db.engine.connect() as connection:
        db_heads = set(MigrationContext.configure(connection).get_current_heads())
    if db_heads == code_heads:
        return None

    known = {revision.revision for revision in script.walk_revisions()}
    pr = os.getenv('PREVIEW_PR')
    db_names = ', '.join(sorted(db_heads)) or 'none'
    code_names = ', '.join(sorted(code_heads))
    if db_heads - known:
        # The database has a migration this code doesn't know about.
        if pr:
            return (f'This is a preview of PR #{pr}, whose branch is older than the staging database '
                    f'(at migration {db_names}). Merge main into the PR\'s branch to update the preview.')
        return (f'The database is at migration {db_names}, which this version of Seating doesn\'t have. '
                f'Deploy a newer version, or point it at a matching database.')
    if pr:
        return (f'This is a preview of PR #{pr}, which adds a database migration ({code_names}). '
                f'PR previews share the staging database and never run migrations, so this preview '
                f'can\'t run. Merge the PR to see its changes on staging.')
    return (f'The database is at migration {db_names}, but this version of Seating expects {code_names}. '
            f'Run `flask db upgrade` from the repository root.')


def check_schema_before_requests(app, migrations_dir):
    cached = {'checked_at': None, 'problem': None}

    def current_problem():
        now = time.monotonic()
        if cached['checked_at'] is None or now - cached['checked_at'] > CACHE_SECONDS:
            try:
                cached['problem'] = schema_problem(migrations_dir)
            except Exception:
                # Can't tell (say the database is unreachable): let the request run and
                # report its own error, and check again next time.
                current_app.logger.exception('Couldn\'t compare the database schema with the migrations')
                return None
            cached['checked_at'] = now
        return cached['problem']

    @app.before_request
    def refuse_mismatched_schema():
        if request.endpoint == 'static':
            return None
        problem = current_problem()
        if problem is None:
            return None
        return problem, 503, {'Content-Type': 'text/plain; charset=utf-8'}
