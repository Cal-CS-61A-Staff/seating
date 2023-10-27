
from os import getenv


class DataValidationError(Exception):
    pass


class EnvironmentalVariableMissingError(Exception):

    def __init__(self, var_name):
        self.var_name = var_name
        super().__init__(self,
                         "Environmental variable {} is missing in current env: {}".format(
                             var_name, getenv('FLASK_ENV', 'unknown')))
