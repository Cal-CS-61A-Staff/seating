from enum import Enum


class AppEnvironment(Enum):
    DEVELOPMENT = 'development'
    PRODUCTION = 'production'
    STAGING = 'staging'
    TESTING = 'testing'


class EmailSendingConfig(Enum):
    OFF = 'off'  # does not send emails
    TEST = 'test'  # sends all emails to test email address
    ON = 'on'  # sends emails to real email addresses
