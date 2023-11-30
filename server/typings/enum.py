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


class EmailTemplate(Enum):
    ASSIGNMENT_INFORM_EMAIL = 'assignment_inform_email'


class GcpSaCredType(Enum):
    FILE = 'file'
    ENV = 'env'
