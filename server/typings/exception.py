from werkzeug.exceptions import HTTPException
from os import getenv
from flask import redirect


class DataValidationError(Exception):
    pass


class EnvironmentalVariableMissingError(Exception):

    def __init__(self, var_name):
        self.var_name = var_name
        super().__init__(self,
                         "Environmental variable {} is missing in current env: {}".format(
                             var_name, getenv('FLASK_ENV', 'unknown')))


class Redirect(HTTPException):
    code = 302

    def __init__(self, url):
        self.url = url

    def get_response(self, environ=None):
        return redirect(self.url)
