import os

from flask import Flask
import flask.ctx
from flask_caching import Cache

class UrlRequestContext(flask.ctx.RequestContext):
    def match_request(self):
        """Matches the request in a request context."""
        try:
            with self:
                url_rule, self.request.view_args = \
                    self.url_adapter.match(return_rule=True)
                self.request.url_rule = url_rule
        except HTTPException as e:
            self.request.routing_exception = e

class App(Flask):
    def request_context(self, environ):
        return UrlRequestContext(self, environ)

app = App(__name__)
app.config.update(
    SECRET_KEY=os.getenv('SECRET_KEY'),
    OK_CLIENT_ID=os.getenv('OK_CLIENT_ID'),
    OK_CLIENT_SECRET=os.getenv('OK_CLIENT_SECRET'),
    GOOGLE_OAUTH2_CLIENT_ID=os.getenv('GOOGLE_CLIENT_ID'),
    GOOGLE_OAUTH2_CLIENT_SECRET=os.getenv('GOOGLE_CLIENT_SECRET'),
    SQLALCHEMY_DATABASE_URI=os.getenv('DATABASE_URI'),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
)

cache = Cache(app, config={'CACHE_TYPE': 'simple'})

import server.auth
import server.models
import server.views
