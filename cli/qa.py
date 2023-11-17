import click
import os
import pytest

from server import app


@app.cli.command('e2e')
def run_e2e():
    click.echo('Running end-to-end tests...')
    pytest.main(['-s', 'tests/e2e'])


@app.cli.command('unit')
def run_unit():
    click.echo('Running unit tests...')
    pytest.main(['-s', 'tests/unit'])


@app.cli.command('a11y')
def run_a11y():
    click.echo('Running accessibility tests...')
    pytest.main(['-s', 'tests/a11y'])


@app.cli.command('test')
def run_all():
    click.echo('Running all tests...')
    pytest.main(['-s', 'tests'])


@app.cli.command('cov')
def run_cov():
    click.echo('Running all tests with coverage...')
    pytest.main(['-s', '--cov=server', 'tests'])


@app.cli.command('audit')
def run_audit():
    click.echo('Checking for broken dependencies...')
    os.system('pip check')
    click.echo('Checking for outdated dependencies...')
    os.system('pip list --outdated')
    click.echo('Auditing with pip-audit...')
    os.system('pip-audit')
    click.echo('Auditing with safety...')
    os.system('safety check')


@app.cli.command('lint')
def run_lint():
    click.echo('Running flake8 linter...')
    os.system('flake8 server tests')
