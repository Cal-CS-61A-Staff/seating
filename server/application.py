import logging
import os

import flask.ctx
from canvasapi.exceptions import InvalidAccessToken
from dotenv import load_dotenv
from flask import Flask, redirect
from flask_migrate import Migrate
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from server.typings.enum import AppEnvironment
from server.typings.exception import EnvironmentalVariableMissingError


# Schema changes are Alembic migrations here; `flask db upgrade` applies them (docs/migrations.md).
MIGRATIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'migrations')


class UrlRequestContext(flask.ctx.RequestContext):
    def match_request(self):
        pass

    def push(self):
        super().push()
        try:
            url_rule, self.request.view_args = \
                self.url_adapter.match(return_rule=True)
            self.request.url_rule = url_rule
        except HTTPException as e:
            self.request.routing_exception = e


class App(Flask):
    def request_context(self, environ):
        return UrlRequestContext(self, environ)


# Sentry is only enabled in staging and production. Development and testing
# environments never report to Sentry.
SENTRY_ENABLED_ENVIRONMENTS = {
    AppEnvironment.STAGING.value,
    AppEnvironment.PRODUCTION.value,
}

# Defense in depth should a script ever get injected again: pages load scripts, styles, fonts and
# images only from this app, and fetch() only from this app, so an injected script cannot fetch()
# or load an image to hand data to another site.
# Inline <script> blocks and onclick= handlers are still allowed, as the templates use them
# throughout; dropping 'unsafe-inline' from script-src needs those moved into static/js first.
# There is no form-action: browsers apply it to the redirects after a form is posted, and a post
# made once the Canvas token has expired is redirected to Canvas to log in again.
CONTENT_SECURITY_POLICY = '; '.join([
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline'",
    "style-src 'self' 'unsafe-inline'",
    "font-src 'self'",
    # Bootstrap draws its checkboxes, selects and close buttons with data: SVGs
    "img-src 'self' data:",
    "connect-src 'self'",
    "base-uri 'self'",
    "object-src 'none'",
])


def config_for_environment():
    """
    The config FLASK_ENV names. FLASK_ENV is required, as in sections, so a misconfigured
    deployment can't fall back to development settings (the fake Canvas, a fixed SECRET_KEY).
    A local .env file is read first, without overriding what the environment already sets.
    """
    from config import ProductionConfig, StagingConfig, DevelopmentConfig, TestingConfig, ConfigBase
    load_dotenv()
    env_value = (ConfigBase.getenv('FLASK_ENV', optional=True) or '').lower()
    config_mapping = {
        AppEnvironment.PRODUCTION.value: ProductionConfig,
        AppEnvironment.TESTING.value: TestingConfig,
        AppEnvironment.STAGING.value: StagingConfig,
        AppEnvironment.DEVELOPMENT.value: DevelopmentConfig,
    }
    if env_value not in config_mapping:
        raise EnvironmentalVariableMissingError('FLASK_ENV')
    return config_mapping[env_value]


def create_app(config=None):
    """
    Builds the seating app with `config`: a config class or instance from config.py, or by
    default the one FLASK_ENV picks.
    """
    # 'server' keeps the templates, static files and logger where they were
    app = App('server')
    configure_logging(app)
    # Cloud Run terminates TLS, so trust its X-Forwarded-Proto for the request's scheme. Not
    # X-Forwarded-Host: Cloud Run passes the requested Host through and leaves that header as sent.
    # ProxyFix also trusts the last X-Forwarded-For entry by default (x_for=1), which Cloud Run sets, so
    # the access log shows the client's address rather than Cloud Run's.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1)

    if config is None:
        config = config_for_environment()
    if isinstance(config, type):
        config = config()
    app.config.from_object(config)

    if app.config['FLASK_ENV'] in SENTRY_ENABLED_ENVIRONMENTS:
        init_sentry(app.config['FLASK_ENV'])

    from server.models import db
    db.init_app(app)
    Migrate(app, db, directory=MIGRATIONS_DIR)
    # Test apps build their tables with create_all rather than migrations, so their databases
    # have no migration to check. test_schema_check tests it.
    if app.config['FLASK_ENV'] != AppEnvironment.TESTING.value:
        from server.schema_check import check_schema_before_requests
        check_schema_before_requests(app, MIGRATIONS_DIR)

    from server.cache import cache_store
    cache_store.init_app(app, config={
        'CACHE_TYPE': 'FileSystemCache',
        'CACHE_DIR': '.cache',
        'CACHE_DEFAULT_TIMEOUT': 3600})

    # before the other before_request hooks, so a post from another site reaches no view. (The URL
    # converters still run first, in UrlRequestContext.push: they check the user and look up the
    # offering, exam or student, but change nothing on a post.)
    from server.cross_origin import refuse_cross_origin_requests
    refuse_cross_origin_requests(app)

    from server.services.auth import init_auth
    init_auth(app)

    from server.controllers import ExamConverter, OfferingConverter, StudentConverter
    app.url_map.converters['exam_student'] = StudentConverter
    app.url_map.converters['exam'] = ExamConverter
    app.url_map.converters['offering'] = OfferingConverter

    # the views use the converters above, so they are registered after them
    from server.views import bp as views
    from server.controllers import auth_module, dev_login_module, health_module
    app.register_blueprint(views)
    app.register_blueprint(dev_login_module)
    app.register_blueprint(auth_module)
    app.register_blueprint(health_module)

    from cli import commands
    for command in commands(app):
        app.cli.add_command(command)

    @app.errorhandler(InvalidAccessToken)
    def handle_invalid_access_token(e):
        """
        Redirects to login page if the Canvas access token is invalid or expired.
        """
        return redirect('/login')

    @app.after_request
    def set_security_headers(response):
        response.headers.setdefault('Content-Security-Policy', CONTENT_SECURITY_POLICY)
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        return response

    app.jinja_env.filters.update(
        min=min,
        max=max,
    )

    return app


def configure_logging(app):
    """Logs INFO and up to stderr, which Cloud Run collects."""
    # every app built in a process shares the 'server' logger: add the handler once
    if not any(getattr(handler, 'seating', False) for handler in app.logger.handlers):
        handler = logging.StreamHandler()
        handler.seating = True
        app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)


def init_sentry(environment):
    import sentry_sdk

    sentry_sdk.init(
        dsn="https://bb1482ed49f0807ee6a49accafe927f9@o4506322522734592.ingest.sentry.io/4506322540953600",
        # Tag every event with the app environment so staging and production
        # issues can be told apart in Sentry.
        environment=environment,
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for performance monitoring.
        traces_sample_rate=1.0,
        # Set profiles_sample_rate to 1.0 to profile 100%
        # of sampled transactions.
        # We recommend adjusting this value in production.
        profiles_sample_rate=1.0,
    )
