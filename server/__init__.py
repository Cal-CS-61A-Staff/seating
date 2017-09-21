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
app.config.update(
    SECRET_KEY=os.getenv('SECRET_KEY'),
    OK_CLIENT_ID=os.getenv('OK_CLIENT_ID'),
    OK_CLIENT_SECRET=os.getenv('OK_CLIENT_SECRET'),
    GOOGLE_OAUTH2_CLIENT_ID=os.getenv('GOOGLE_CLIENT_ID'),
    GOOGLE_OAUTH2_CLIENT_SECRET=os.getenv('GOOGLE_CLIENT_SECRET'),
    SQLALCHEMY_DATABASE_URI=os.getenv('DATABASE_URL').replace('mysql://', 'mysql+pymysql://'),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SENDGRID_API_KEY=os.getenv('SENDGRID_API_KEY'),
    PHOTO_DIRECTORY=os.getenv('PHOTO_DIRECTORY'),
    COURSE=os.getenv('COURSE'),
    EXAM=os.getenv('EXAM'),
    DOMAIN=os.getenv('DOMAIN')
)

app.jinja_env.filters.update(
    min=min,
    max=max,
)

import server.auth
import server.models
import server.views
