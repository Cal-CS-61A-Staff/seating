import os

from flask import Flask
import flask.ctx
from werkzeug.exceptions import HTTPException

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

app.config.from_object('config')

app.jinja_env.filters.update(
    min=min,
    max=max,
)

import server.auth
import server.models
import server.views
