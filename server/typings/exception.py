from werkzeug.exceptions import HTTPException
from os import getenv
from flask import redirect


class DataValidationError(Exception):
    pass


class GcpError (Exception):
    pass

class SeatAssignmentError(Exception):
    pass

class NotEnoughSeatError(SeatAssignmentError):
    def __init__(self, exam, students, preference):
        wants, avoids, room_wants, room_avoids = preference
        pref_str = """\
        wants: {}
        avoids: {}
        room_wants: {}
        room_avoids: {}
        """.format(
            ', '.join(wants),
            ', '.join(avoids),
            ', '.join([exam.get_room(id).name_and_start_at_time_display(short=True) for id in room_wants]),
            ', '.join([exam.get_room(id).name_and_start_at_time_display(short=True) for id in room_avoids]),
        )
        students_str = ', '.join([s.name for s in students])
        super().__init__(self, "Assignment failed on:\n"
                         f"- Student:\n{students_str}\n"
                         f"- Preference:\n{pref_str}\n"
                         "Seat with such preference does not exist or runs out.")

    def __str__(self):
        return self.args[1]

class SeatOverrideError(SeatAssignmentError):
    def __init__(self, student, seat, reason):
        super().__init__(self, "Seat override failed on:\n"
                         f"- Student: {student.name}\n"
                         f"- Seat: {seat.name}\n"
                         f"- Reason: {reason}")

    def __str__(self):
        return self.args[1]


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
