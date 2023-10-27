import os

from flask import Flask, redirect
import flask.ctx
from werkzeug.exceptions import HTTPException
from canvasapi.exceptions import InvalidAccessToken

from server.typings.enum import AppEnvironment
from server.typings.exception import EnvironmentalVariableMissingError


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


app = App(__name__)

from config import ConfigBase, ProductionConfig, StagingConfig, DevelopmentConfig, TestingConfig  # noqa
env_value = ConfigBase.getenv('FLASK_ENV').lower()

config_mapping = {
    AppEnvironment.PRODUCTION.value: ProductionConfig,
    AppEnvironment.TESTING.value: TestingConfig,
    AppEnvironment.STAGING.value: StagingConfig,
    AppEnvironment.DEVELOPMENT.value: DevelopmentConfig,
}

selected_config_class = config_mapping.get(env_value, None)

if selected_config_class:
    app.config.from_object(selected_config_class())
else:
    raise EnvironmentalVariableMissingError('FLASK_ENV')


@app.errorhandler(InvalidAccessToken)
def handle_invalid_access_token(e):
    """
    Redirects to login page if the Canvas access token is invalid or expired.
    """
    return redirect('/login')


app.jinja_env.filters.update(
    min=min,
    max=max,
)


import server.utils.auth  # noqa
import server.models  # noqa
import server.views  # noqa
import tests.conftest  # noqa
