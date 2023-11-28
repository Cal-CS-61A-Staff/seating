import os
from typing import Optional

from server.typings.exception import EnvironmentalVariableMissingError
from server.typings.enum import AppEnvironment, EmailSendingConfig


class ConfigBase(object):

    @staticmethod
    def getenv(key, default: Optional[str] = None):
        val = os.getenv(key, default)
        if val is None:
            raise EnvironmentalVariableMissingError(key)
        return val

    FLASK_APP = "server"
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    FIXTURES_DIRS = [os.path.join('tests', 'fixtures')]
    SERVER_BASE_URL = getenv('SERVER_BASE_URL', "http://localhost:5000/")

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    LOCAL_TIMEZONE = getenv('TIMEZONE', 'US/Pacific')

    # Coogle API setup
    GOOGLE_OAUTH2_CLIENT_ID = getenv('GOOGLE_CLIENT_ID')
    GOOGLE_OAUTH2_CLIENT_SECRET = getenv('GOOGLE_CLIENT_SECRET')

    # Canvas API setup
    CANVAS_SERVER_URL = getenv('CANVAS_SERVER_URL')
    CANVAS_CLIENT_ID = getenv('CANVAS_CLIENT_ID')
    CANVAS_CLIENT_SECRET = getenv('CANVAS_CLIENT_SECRET')

    # Stub Setup, allow
    MOCK_CANVAS = getenv('MOCK_CANVAS', 'false').lower() == 'true'
    SEND_EMAIL = getenv('SEND_EMAIL', 'off').lower()

    # Email setup. Domain environment is for link in email.
    SENDGRID_API_KEY = getenv('SENDGRID_API_KEY', "placeholder")

    PHOTO_DIRECTORY = getenv('PHOTO_DIRECTORY', "placeholder")


class ProductionConfig(ConfigBase):
    FLASK_ENV = AppEnvironment.PRODUCTION.value
    MOCK_CANVAS = False
    SEND_EMAIL = EmailSendingConfig.ON.value

    @property
    def SECRET_KEY(self):
        return ConfigBase.getenv('SECRET_KEY')

    @property
    def SQLALCHEMY_DATABASE_URI(self):
        return ConfigBase.getenv('DATABASE_URL').replace('mysql://', 'mysql+pymysql://')


class StagingConfig(ConfigBase):
    FLASK_ENV = AppEnvironment.STAGING.value
    SECRET_KEY = 'staging'
    SEND_EMAIL = EmailSendingConfig.TEST.value

    @property
    def SQLALCHEMY_DATABASE_URI(self):
        return ConfigBase.getenv('DATABASE_URL').replace('postgresql://', 'postgresql+psycopg2://')


class DevelopmentConfig(ConfigBase):
    FLASK_ENV = AppEnvironment.DEVELOPMENT.value
    SECRET_KEY = 'development'

    @property
    def SQLALCHEMY_DATABASE_URI(self):
        return 'sqlite:///' + os.path.join(self.BASE_DIR, 'seating_app_{}.db'.format(self.FLASK_ENV))


class TestingConfig(ConfigBase):
    FLASK_ENV = AppEnvironment.TESTING.value
    SECRET_KEY = 'testing'
    MOCK_CANVAS = True
    SEND_EMAIL = EmailSendingConfig.OFF.value

    @property
    def SQLALCHEMY_DATABASE_URI(self):
        return 'sqlite:///' + os.path.join(self.BASE_DIR, 'seating_app_{}.db'.format(self.FLASK_ENV))
