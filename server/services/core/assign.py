import random

from server.models import SeatAssignment
from server.typings.exception import SeatAssigningAlgorithmError
from server.utils.misc import arr_to_dict


def assign_students(exam):
    """
    The strategy:
    Look for students whose requirements are the most restrictive
        (i.e. have the fewest possible seats).
    Randomly assign them a seat.
    Repeat.
    """
    students = set(exam.unassigned_students)
    seats = set(exam.unassigned_seats)

    def seats_available(preference):
        """
        Return seats available for a given preference.
        Remember: any([]) return False, all([]) return True
        """
        wants, avoids, room_wants, room_avoids = preference
        return [
            seat for seat in seats
            if (all(a in seat.attributes for a in wants) and  # noqa
                all(a not in seat.attributes for a in avoids) and  # noqa
                (not room_wants or any(int(a) == seat.room.id for a in room_wants)) and  # noqa
                all(int(a) != seat.room.id for a in room_avoids)
                )
        ]

    assignments = []
    while students:
        students_by_preference = arr_to_dict(students, key_getter=lambda student: (
            frozenset(student.wants), frozenset(student.avoids),
            frozenset(student.room_wants), frozenset(student.room_avoids)))
        seats_by_preference = {
            preference: seats_available(preference)
            for preference in students_by_preference.keys()
        }
        min_preference = min(seats_by_preference,
                             key=lambda k: len(seats_by_preference[k]))
        min_students = students_by_preference[min_preference]
        min_seats = seats_by_preference[min_preference]

        if not min_seats:
            raise SeatAssigningAlgorithmError(exam, min_students, min_preference)

        student = random.choice(min_students)
        seat = random.choice(min_seats)

        students.remove(student)
        seats.remove(seat)

        assignments.append(SeatAssignment(student=student, seat=seat))
    return assignments
