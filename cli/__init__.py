import cli.db

from config import ConfigBase  # noqa
from server.typings.enum import AppEnvironment

env_value = ConfigBase.getenv('FLASK_ENV').lower()

if env_value == AppEnvironment.DEVELOPMENT.value or \
        env_value == AppEnvironment.TESTING.value:
    import cli.qa
