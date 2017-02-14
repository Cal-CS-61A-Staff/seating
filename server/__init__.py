import os

from flask import Flask
from flask_caching import Cache

app = Flask(__name__)
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
