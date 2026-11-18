# Database Migrations

The schema is managed with Flask-Migrate (Alembic); migrations live in `server/migrations/versions`. To change the schema, edit `server/models.py`, then from the repository root:

```
flask db migrate -m "describe the change"   # generates a migration; review and edit it
flask db upgrade                            # applies it to your local database
```

Commit the migration with the model change. `tests/unit/test_migrations.py` fails if the models and the migrations don't match.

`flask initdb` applies every migration, the same as `flask db upgrade`, and `flask resetdb` drops every table (and the migration record), then builds and seeds the database again.

## Deploying

A deployment with `RUN_MIGRATIONS=true` runs `flask db upgrade` when it starts, and doesn't start if that fails (see the `Dockerfile`). Set it on staging and production. PR previews never set it: they share the staging database, and a PR's migration shouldn't change that database before the PR is merged.

## Databases from Before Migrations

The first migration, `0001_baseline`, is the schema as it was when migrations were added. A database built before then with `flask initdb` (such as staging's, whose later tables and columns were added by hand) can be upgraded as it is: the baseline creates only the tables it is missing, adds the columns its tables are missing, and keeps every row. If a missing column is required and has no default, the upgrade stops and names it, so it can be added by hand.

## Migrations and PR Previews

Seating checks that the database's migration matches the code's latest migration (`server/schema_check.py`). While they differ, every page and `/health/` returns 503 with the reason, rather than failing on the first query that uses a missing column. The check is repeated at most once a minute. Tests build their tables with `create_all`, so test apps skip it.

This means **a PR that adds a migration can't be tried on its preview.** The preview shares the staging database, which only gets the migration when the PR is merged and staging deploys, so the preview says "This is a preview of PR #N, which adds a database migration… Merge the PR to see its changes on staging." Test such a PR locally (`flask db upgrade` against your own database), then merge it and check staging.

The reverse also happens: after another PR with a migration is merged, staging's database is ahead of a preview whose branch doesn't have that migration. The preview then says to merge main into the PR's branch, which redeploys the preview with the migration.

Locally, the same check tells you to run `flask db upgrade` when your database is behind: for example after pulling a new migration, or the first time you run this version against a database made with `create_all`.
