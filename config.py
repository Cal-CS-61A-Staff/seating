import os
from typing import Optional

from server.typings.exception import EnvironmentalVariableMissingError
from server.typings.enum import AppEnvironment, EmailSendingConfig, GcpSaCredType


class ConfigBase(object):

    @staticmethod
    def getenv(key, default: Optional[str] = None, *, optional=False):
        val = os.getenv(key, default)
        if not optional and val is None:
            raise EnvironmentalVariableMissingError(key)
        return val

    FLASK_APP = "server"
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    FIXTURES_DIRS = [os.path.join('tests', 'fixtures')]
    SERVER_BASE_URL = getenv('SERVER_BASE_URL', "http://localhost:5000/")

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    LOCAL_TIMEZONE = getenv('TIMEZONE', 'US/Pacific')

    # Coogle Service Account Cred setup
    GCP_SA_CRED_TYPE = getenv('GCP_SA_CRED_TYPE', GcpSaCredType.FILE.value)
    GCP_SA_CRED_FILE = getenv('GCP_SA_CRED_FILE', optional=True)
    GCP_SA_CRED_VALUE = getenv('GCP_SA_CRED_VALUE', optional=True)

    # Canvas API setup
    CANVAS_SERVER_URL = getenv('CANVAS_SERVER_URL')
    CANVAS_CLIENT_ID = getenv('CANVAS_CLIENT_ID')
    CANVAS_CLIENT_SECRET = getenv('CANVAS_CLIENT_SECRET')

    # Stub Setup, allow
    MOCK_CANVAS = getenv('MOCK_CANVAS', 'false').lower() == 'true'
    SEND_EMAIL = getenv('SEND_EMAIL', 'off').lower()

    # Email setup.
    EMAIL_SERVER = getenv('EMAIL_SERVER', optional=True)
    EMAIL_PORT = getenv('EMAIL_PORT', optional=True)
    EMAIL_USERNAME = getenv('EMAIL_USERNAME', optional=True)
    EMAIL_PASSWORD = getenv('EMAIL_PASSWORD', optional=True)

    # Master room sheet
    MASTER_ROOM_SHEET_URL = getenv('MASTER_ROOM_SHEET_URL', optional=True)

    PHOTO_DIRECTORY = getenv('PHOTO_DIRECTORY', "unset")


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
