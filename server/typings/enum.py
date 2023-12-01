from enum import Enum


class AppEnvironment(Enum):
    DEVELOPMENT = 'development'
    PRODUCTION = 'production'
    STAGING = 'staging'
    TESTING = 'testing'


class EmailTemplate(Enum):
    ASSIGNMENT_INFORM_EMAIL = 'assignment_inform_email'


class GcpSaCredType(Enum):
    FILE = 'file'
    ENV = 'env'
