import random

from server.models import SeatAssignment
from server.typings.exception import NotEnoughSeatError, SeatOverrideError
from server.utils.misc import arr_to_dict

def _freeze_student_preference(student):
    return frozenset(student.wants), frozenset(student.avoids), frozenset(student.room_wants), frozenset(student.room_avoids)

def _seats_available(seats, preference):
    """
    Return seats available for a given preference.
    Comparison of attributes is case-insensitive.
    Remember: any([]) return False, all([]) return True
    """
    wants, avoids, room_wants, room_avoids = preference
    return [
        seat for seat in seats
        if (all(want.lower() in {attr.lower() for attr in seat.attributes} for want in wants) and  # noqa
            all(avoid.lower() not in {attr.lower() for attr in seat.attributes} for avoid in avoids) and  # noqa
            (not room_wants or any(int(a) == seat.room.id for a in room_wants)) and  # noqa
            all(int(a) != seat.room.id for a in room_avoids)
            )
    ]

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

    assignments = []
    while students:
        students_by_preference = \
            arr_to_dict(students, key_getter=_freeze_student_preference)
        seats_by_preference = {
            preference: _seats_available(seats, preference)
            for preference in students_by_preference.keys()
        }
        min_preference = min(seats_by_preference,
                             key=lambda k: len(seats_by_preference[k]))
        min_students = students_by_preference[min_preference]
        min_seats = seats_by_preference[min_preference]

        if not min_seats:
            raise NotEnoughSeatError(exam, min_students, min_preference)

        student = random.choice(min_students)
        seat = random.choice(min_seats)

        students.remove(student)
        seats.remove(seat)

        assignments.append(SeatAssignment(student=student, seat=seat))
    return assignments

def assign_single_student(exam, student, seat=None, ignore_restrictions=False):
    """
    Assign a single student to a seat.
    If a seat is not provided, try to find a seat that meets the student's requirements (if ignore_restrictions is False),
    or just any seat that is available (if ignore_restrictions is True).
    If a seat is provided, check if the seat is available and meets the student's requirements (if ignore_restrictions is False),
    or only check if the seat is available (if ignore_restrictions is True).
    Then, the chosen seat is assigned to the student.

    The original assignment will NOT be removed! It is the caller's responsibility to remove the original assignment if needed.
    """
    preference = _freeze_student_preference(student)
    seats = _seats_available(exam.unassigned_seats, preference) \
            if not ignore_restrictions else exam.unassigned_seats
    
    # if a seat is provided, check it
    if seat and seat not in seats:
        raise SeatOverrideError(student, seat, 
                                "Seat is already taken or does exist in the exam, or does not meet the student's requirements.")
    
    # if seat is not provided, try getting a seat that meets the student's requirements
    if not seat:
        if not seats:
            raise NotEnoughSeatError(exam, [student], preference)
        seat = random.choice(seats)
    
    # create and return a new assignment
    return SeatAssignment(student=student, seat=seat)
    