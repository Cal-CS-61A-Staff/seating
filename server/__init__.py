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

# These must be done after `app`` is created as they depend on `app`

# prepares all auth clients
import server.services.auth  # noqa

# prepares mock canvas db
import server.services.canvas.fake_data  # noqa

# registers controller converters
from server.controllers import ExamConverter, OfferingConverter  # noqa
app.url_map.converters['exam'] = ExamConverter
app.url_map.converters['offering'] = OfferingConverter

# registers base controllers (depends on converters, so must be done after)
import server.views  # noqa

# registers blueprint controllers
from server.controllers import auth_module, dev_login_module, health_module  # noqa
app.register_blueprint(dev_login_module)
app.register_blueprint(auth_module)
app.register_blueprint(health_module)

# registers flask cli commands
import cli  # noqa
