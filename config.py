import os
from datetime import timedelta
from typing import Optional

from server.typings.exception import EnvironmentalVariableMissingError
from server.typings.enum import AppEnvironment, GcpSaCredType


class ConfigBase(object):
    """
    Settings read from the environment when the config is created, not when this module is
    imported, so an app built later (or in a test) sees the environment as it is then.
    """

    @staticmethod
    def getenv(key, default: Optional[str] = None, *, optional=False):
        val = os.getenv(key, default)
        if not optional and val is None:
            raise EnvironmentalVariableMissingError(key)
        return val

    FLASK_APP = "server.main"
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    FIXTURES_DIRS = [os.path.join('tests', 'fixtures')]

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Both cookies are HttpOnly by default. Lax still sends them on the top-level redirect back
    # from Canvas to /authorized/, but not on cross-site POSTs, fetches or embeds. (Strict would
    # drop the session on that redirect and break login.)
    SESSION_COOKIE_SAMESITE = 'Lax'
    REMEMBER_COOKIE_SAMESITE = 'Lax'
    # Sessions end after this long without a request. Sign-ins also expire after
    # SIGN_IN_MAX_AGE (server/services/auth), so Canvas roles are read again.
    PERMANENT_SESSION_LIFETIME = timedelta(hours=2)
    # The remember cookie is no longer set. Any left in browsers are refused (see
    # sign_in_expired), and logging out deletes them; until then they keep the flags above.

    # Uploads (rooms, students, layout previews) are read into memory, so refuse a request
    # larger than this with 413. A roster of thousands of students is well under 1 MB.
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024

    def __init__(self):
        getenv = self.getenv
        self.SERVER_BASE_URL = getenv('SERVER_BASE_URL', "http://localhost:5000/")
        self.WIKI_BASE_URL = getenv('WIKI_BASE_URL', "https://github.com/berkeley-eecs/seating/wiki/")
        self.LOCAL_TIMEZONE = getenv('TIMEZONE', 'US/Pacific')

        # Coogle Service Account Cred setup
        self.GCP_SA_CRED_TYPE = getenv('GCP_SA_CRED_TYPE', GcpSaCredType.FILE.value)
        self.GCP_SA_CRED_FILE = getenv('GCP_SA_CRED_FILE', optional=True)
        self.GCP_SA_CRED_VALUE = getenv('GCP_SA_CRED_VALUE', optional=True)
        # the Google account's email, shown on the import page so staff know who to share a sheet with
        self.GCP_SA_EMAIL = getenv('GCP_SA_EMAIL', optional=True)

        # Canvas API setup
        self.CANVAS_SERVER_URL = getenv('CANVAS_SERVER_URL')
        self.CANVAS_CLIENT_ID = getenv('CANVAS_CLIENT_ID')
        self.CANVAS_CLIENT_SECRET = getenv('CANVAS_CLIENT_SECRET')

        # Stub Setup, allow
        self.MOCK_CANVAS = getenv('MOCK_CANVAS', 'false').lower() == 'true'
        self.SEND_EMAIL = getenv('SEND_EMAIL', 'off').lower()

        # Email setup.
        self.EMAIL_SERVER = getenv('EMAIL_SERVER', optional=True)
        self.EMAIL_PORT = getenv('EMAIL_PORT', optional=True)
        self.EMAIL_USERNAME = getenv('EMAIL_USERNAME', optional=True)
        self.EMAIL_PASSWORD = getenv('EMAIL_PASSWORD', optional=True)
        self.EMAIL_SENDER = getenv('EMAIL_SENDER', optional=True)

        # C1C API setup
        self.MOCK_C1C = getenv('MOCK_C1C', 'false').lower() == 'true'
        self.C1C_PROXY_URL = getenv('C1C_PROXY_URL', optional=True)
        self.C1C_API_DOMAIN = getenv('C1C_API_DOMAIN', optional=True)
        self.C1C_API_USERNAME = getenv('C1C_API_USERNAME', optional=True)
        self.C1C_API_PASSWORD = getenv('C1C_API_PASSWORD', optional=True)
        self.C1C_PHOTO_CACHE_LIFE = int(getenv('C1C_PHOTO_CACHE_LIFE', 3600 * 24 * 90))

        # Master room sheet
        self.MASTER_ROOM_SHEET_URL = getenv('MASTER_ROOM_SHEET_URL', optional=True)

        self.PHOTO_DIRECTORY = getenv('PHOTO_DIRECTORY', "unset")

        # How long a Canvas sign-in is trusted, in seconds, before the user must sign in again
        sign_in_max_age = getenv('SIGN_IN_MAX_AGE', optional=True)
        if sign_in_max_age:
            self.SIGN_IN_MAX_AGE = int(sign_in_max_age)


class ProductionConfig(ConfigBase):
    FLASK_ENV = AppEnvironment.PRODUCTION.value
    # served over HTTPS only, so never send the session or remember cookie over plain HTTP
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True

    def __init__(self):
        super().__init__()
        self.MOCK_CANVAS = False

    @property
    def SECRET_KEY(self):
        return ConfigBase.getenv('SECRET_KEY')

    @property
    def SQLALCHEMY_DATABASE_URI(self):
        return ConfigBase.getenv('DATABASE_URL').replace('mysql://', 'mysql+pymysql://')


class StagingConfig(ConfigBase):
    FLASK_ENV = AppEnvironment.STAGING.value
    # the PR previews are served over HTTPS only, like production
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True

    def __init__(self):
        super().__init__()
        # Staging talks to real Canvas, so the dev login is never available here.
        self.MOCK_CANVAS = False

    # from the environment, as in production: staging signs in real Canvas users
    @property
    def SECRET_KEY(self):
        return ConfigBase.getenv('SECRET_KEY')

    @property
    def SQLALCHEMY_DATABASE_URI(self):
        import re
        # replace postgresql:// or postgres:// with postgresql+psycopg2://
        return re.sub(r'postgres(ql)?://', 'postgresql+psycopg2://', ConfigBase.getenv('DATABASE_URL'))


class DevelopmentConfig(ConfigBase):
    FLASK_ENV = AppEnvironment.DEVELOPMENT.value
    SECRET_KEY = 'development'

    def __init__(self):
        super().__init__()
        # Outside staging and production the fake Canvas is the default, so a fresh
        # checkout can be signed into through /dev_login without any Canvas
        # credentials. Set MOCK_CANVAS=false to point a dev server at real Canvas.
        self.MOCK_CANVAS = self.getenv('MOCK_CANVAS', 'true').lower() == 'true'

    @property
    def SQLALCHEMY_DATABASE_URI(self):
        return 'sqlite:///' + os.path.join(self.BASE_DIR, 'seating_app_{}.db'.format(self.FLASK_ENV))


class TestingConfig(ConfigBase):
    FLASK_ENV = AppEnvironment.TESTING.value
    SECRET_KEY = 'testing'

    def __init__(self):
        super().__init__()
        self.MOCK_CANVAS = True
        self.EMAIL_SENDER = 'seating@example.edu'

    @property
    def SQLALCHEMY_DATABASE_URI(self):
        return 'sqlite:///' + os.path.join(self.BASE_DIR, 'seating_app_{}.db'.format(self.FLASK_ENV))
