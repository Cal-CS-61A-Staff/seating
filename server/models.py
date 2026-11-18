
import itertools
from natsort import natsorted
import re

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import PrimaryKeyConstraint, types
from sqlalchemy.orm import backref, contains_eager, joinedload
from sqlalchemy import UniqueConstraint, desc, false, text
from sqlalchemy.ext.associationproxy import association_proxy

from server.utils.date import parse_ISO8601
from server.utils.misc import arr_to_dict, set_to_str

db = SQLAlchemy()


class StringSet(types.TypeDecorator):
    impl = types.Text
    cache_ok = True

    def process_bind_param(self, value, engine):
        # set('123') would store each character as its own item
        if isinstance(value, str):
            raise TypeError('StringSet expects a collection of strings, not a str')
        return ','.join(set(value))

    def process_result_value(self, value, engine):
        if not value:
            return set()
        else:
            return set(value.split(','))


class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), index=True, nullable=False)
    canvas_id = db.Column(db.String(255), nullable=False, index=True, unique=True)
    staff_offerings = db.Column(StringSet, nullable=False)
    student_offerings = db.Column(StringSet, nullable=False)

    def set_course_roles(self, staff_courses, student_courses):
        """Saves which courses the user teaches and takes, from their Canvas courses."""
        self.staff_offerings = {str(c.id) for c in staff_courses}
        self.student_offerings = {str(c.id) for c in student_courses}


class Offering(db.Model):
    __tablename__ = 'offerings'
    id = db.Column(db.Integer, primary_key=True)
    canvas_id = db.Column(db.String(255), nullable=False, index=True, unique=True)
    name = db.Column(db.String(255), nullable=False)
    code = db.Column(db.String(255), nullable=False)
    start_at = db.Column(db.String(255), nullable=False)
    # Hidden offerings are left off the offerings page but keep their exams;
    # importing the course again shows them again.
    is_hidden = db.Column(db.Boolean, nullable=False, default=False, server_default=false())

    exams = db.relationship('Exam', uselist=True, cascade='all, delete-orphan',
                            order_by='Exam.display_name',
                            backref=backref('offering', uselist=False, single_parent=True))

    @property
    def start_at_date(self):
        return parse_ISO8601(self.start_at)

    @property
    def active_exam(self):
        return next((exam for exam in self.exams if exam.is_active), None)

    def __str__(self):
        return f"{self.start_at_date.strftime('%Y-%m')} | {self.code} | {self.name}"

    def __repr__(self):
        return '<Offering {}>'.format(self.name)

    def mark_all_exams_as_inactive(self):
        Exam.query.filter_by(offering_canvas_id=self.canvas_id).update({"is_active": False})

    def ensure_one_exam_is_active(self):
        if not self.exams:
            return
        if not any(exam.is_active for exam in self.exams):
            self.exams[0].is_active = True
            return True
        return False


class Exam(db.Model):
    __tablename__ = 'exams'
    id = db.Column(db.Integer, primary_key=True)
    offering_canvas_id = db.Column(db.ForeignKey(
        'offerings.canvas_id', ondelete='CASCADE'), index=True, nullable=False)
    name = db.Column(db.String(255), nullable=False, index=True)
    display_name = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.BOOLEAN, nullable=False)

    rooms = db.relationship('Room', uselist=True, cascade='all, delete-orphan',
                            order_by=[desc(text('rooms.start_at')), desc(text('rooms.display_name'))],
                            backref=backref('exam', uselist=False, single_parent=True))
    students = db.relationship('Student', uselist=True, cascade='all, delete-orphan',
                               order_by='Student.name',
                               backref=backref('exam', uselist=False, single_parent=True))
    seats = association_proxy('rooms', 'seats')

    __table_args__ = (
        UniqueConstraint('offering_canvas_id', 'name', name='uq_offering_canvas_id_name'),
    )

    def get_seats(self):
        """
        All seats of all rooms of this exam, in a single query.
        Each seat comes with its room and its assignment (or None) already loaded,
        so callers can check `seat.assignment` / `seat.room` without one query per seat.
        """
        return (
            Seat.query
            .join(Seat.room)
            .filter(Room.exam_id == self.id)
            .options(contains_eager(Seat.room), joinedload(Seat.assignment))
            .order_by(Room.id, Seat.name)
            .all()
        )

    def get_students(self, with_seat=False):
        """
        All students of this exam, in a single query, with their assignment (or None) already loaded.
        With `with_seat=True`, the assigned seat and its room are loaded in the same query too,
        which is what list/export/email views need.
        """
        query = Student.query.filter_by(exam_id=self.id).order_by(Student.name)
        if with_seat:
            query = query.options(
                joinedload(Student.assignment).joinedload(SeatAssignment.seat).joinedload(Seat.room))
        else:
            query = query.options(joinedload(Student.assignment))
        return query.all()

    @property
    def unassigned_seats(self):
        return [seat for seat in self.get_seats() if seat.assignment is None]

    @property
    def unassigned_students(self):
        return [student for student in self.get_students() if student.assignment is None]

    def get_assignments(self, emailed=None, limit=None, offset=None):
        query = SeatAssignment.query.join(SeatAssignment.seat).join(Seat.room).filter(
            Room.exam_id == self.id,
        )
        if emailed is not None:
            query = query.filter(SeatAssignment.emailed == emailed)
        if limit is not None:
            query = query.limit(limit)
        if offset is not None:
            query = query.offset(offset)
        return query.all()

    def get_rooms(self, room_ids):
        """
        Return the rooms of this exam whose ids are in `room_ids` (ids may be ints or strings),
        in the exam's room order. Ids that do not belong to this exam are silently skipped.
        """
        # Use the already-loaded relationship instead of issuing a query per call: the
        # students page calls this for every student, which for a large exam adds up fast.
        wanted_ids = {str(room_id) for room_id in room_ids}
        return [room for room in self.rooms if str(room.id) in wanted_ids]

    def get_unknown_room_ids(self, room_ids):
        """
        Return the ids in `room_ids` that are not rooms of this exam (e.g. deleted rooms),
        as sorted strings.
        """
        exam_room_ids = {str(room.id) for room in self.rooms}
        return sorted({str(room_id) for room_id in room_ids} - exam_room_ids)

    def remove_room_preferences(self, room_id):
        """
        Drop `room_id` from every student's room wants/avoids, so that deleting a room
        does not leave dangling references behind. Does not commit.
        """
        room_id = str(room_id)
        for student in self.students:
            if room_id in student.room_wants:
                student.room_wants = student.room_wants - {room_id}
            if room_id in student.room_avoids:
                student.room_avoids = student.room_avoids - {room_id}

    def remove_unknown_room_preferences(self):
        """
        Drop ids of rooms that are not in this exam (e.g. deleted rooms) from every student's
        room wants/avoids. Returns the number of students changed. Does not commit.
        """
        exam_room_ids = {str(room.id) for room in self.rooms}
        changed = 0
        for student in self.students:
            room_wants = student.room_wants & exam_room_ids
            room_avoids = student.room_avoids & exam_room_ids
            if room_wants != student.room_wants or room_avoids != student.room_avoids:
                student.room_wants, student.room_avoids = room_wants, room_avoids
                changed += 1
        return changed

    def __repr__(self):
        return '<Exam {}>'.format(self.name)


class Room(db.Model):
    __tablename__ = 'rooms'
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.ForeignKey('exams.id', ondelete='CASCADE'), index=True, nullable=False)
    name = db.Column(db.String(255), nullable=False, index=True)
    display_name = db.Column(db.String(255), nullable=False)
    start_at = db.Column(db.String(255))
    duration_minutes = db.Column(db.Integer)

    @property
    def start_at_time(self):
        return parse_ISO8601(self.start_at) if self.start_at else None

    def start_at_time_display(self, short=False):
        t_format = '%H:%M-%b %d' if short else '%I:%M %p - %b %d, %Y'
        placeholder = "TBA" if short else "Start Time TBA"
        return self.start_at_time.strftime(t_format) if self.start_at else placeholder

    def name_and_start_at_time_display(self, short=False):
        return f"{self.display_name} ({self.start_at_time_display(short)})"

    @property
    def duration_display(self):
        return f"{self.duration_minutes} mins" if self.duration_minutes else "Duration TBA"

    seats = db.relationship('Seat', uselist=True, cascade='all, delete-orphan',
                            order_by='Seat.name',
                            backref=backref('room', uselist=False, single_parent=True))

    __table_args__ = (
        UniqueConstraint('exam_id', 'name', 'start_at', name='uq_exam_id_name_start_at'),
    )

    @property
    def fixed_seats(self):
        return [seat for seat in self.seats if seat.fixed]

    @property
    def movable_seats(self):
        return [seat for seat in self.seats if not seat.fixed]

    @property
    def movable_seats_by_attribute(self):
        return arr_to_dict(self.movable_seats, key_getter=lambda seat: frozenset(seat.attributes))

    @property
    def rows(self):
        seats = natsorted(self.fixed_seats, key=lambda seat: seat.row)
        return [
            natsorted(g, key=lambda seat: seat.x)
            for _, g in itertools.groupby(seats, lambda seat: seat.row)
        ]

    def update_movable_seats(self, new_movable_seats):
        self.seats = self.fixed_seats + new_movable_seats

    def __repr__(self):
        return '<Room {}>'.format(self.name)


class Seat(db.Model):
    __tablename__ = 'seats'
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.ForeignKey('rooms.id', ondelete='CASCADE'), index=True, nullable=False)
    fixed = db.Column(db.Boolean, default=True, nullable=False)
    name = db.Column(db.String(255))
    row = db.Column(db.String(255))
    seat = db.Column(db.String(255), index=True)
    x = db.Column(db.Float)
    y = db.Column(db.Float)
    attributes = db.Column(StringSet, nullable=False)

    assignment = db.relationship('SeatAssignment', uselist=False, cascade='all, delete-orphan',
                                 backref=backref('seat', uselist=False, single_parent=True))

    @property
    def display_name(self):
        return self.name if self.name else f"Movable Seat ({set_to_str(self.attributes)})"

    def __repr__(self):
        return '<Seat {}>'.format(self.display_name)


class Student(db.Model):
    __tablename__ = 'students'
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.ForeignKey('exams.id', ondelete='CASCADE'), index=True, nullable=False)
    canvas_id = db.Column(db.String(255), nullable=False, index=True)
    email = db.Column(db.String(255), index=True, nullable=False)
    name = db.Column(db.String(255), nullable=False)
    sid = db.Column(db.String(255))
    wants = db.Column(StringSet, nullable=False)
    avoids = db.Column(StringSet, nullable=False)
    room_wants = db.Column(StringSet, nullable=False)
    room_avoids = db.Column(StringSet, nullable=False)

    assignment = db.relationship('SeatAssignment', uselist=False, cascade='all, delete-orphan',
                                 backref=backref('student', uselist=False, single_parent=True))

    @property
    def first_name(self):
        return self.name.rsplit(',', 1)[-1].strip().title()

    @property
    def wanted_rooms(self):
        """Rooms of this exam the student wants; ids of rooms that no longer exist are skipped."""
        return self.exam.get_rooms(self.room_wants)

    @property
    def avoided_rooms(self):
        """Rooms of this exam the student avoids; ids of rooms that no longer exist are skipped."""
        return self.exam.get_rooms(self.room_avoids)

    @property
    def unknown_room_wants(self):
        """Wanted room ids that are not rooms of this exam, e.g. rooms that were deleted."""
        return self.exam.get_unknown_room_ids(self.room_wants)

    @property
    def unknown_room_avoids(self):
        """Avoided room ids that are not rooms of this exam, e.g. rooms that were deleted."""
        return self.exam.get_unknown_room_ids(self.room_avoids)

    def __repr__(self):
        return '<Student {} ({})>'.format(self.name, self.canvas_id)


class SeatAssignment(db.Model):
    __tablename__ = 'seat_assignments'
    __table_args__ = (
        PrimaryKeyConstraint('student_id', 'seat_id'),
    )
    student_id = db.Column(db.ForeignKey('students.id', ondelete='CASCADE'), index=True, nullable=False)
    seat_id = db.Column(db.ForeignKey('seats.id', ondelete='CASCADE'), index=True, nullable=False)
    emailed = db.Column(db.Boolean, default=False, index=True, nullable=False)


def slug(display_name):
    return re.sub(r'[^A-Za-z0-9._-]', '', display_name.lower())
