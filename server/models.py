
import itertools
from natsort import natsorted
import re

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import PrimaryKeyConstraint, types
from sqlalchemy.orm import backref
from sqlalchemy import UniqueConstraint, desc, text
from sqlalchemy.ext.associationproxy import association_proxy

from server import app
from server.utils.date import parse_ISO8601
from server.utils.misc import arr_to_dict

db = SQLAlchemy(app=app)


class StringSet(types.TypeDecorator):
    impl = types.Text

    def process_bind_param(self, value, engine):
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


class Offering(db.Model):
    __tablename__ = 'offerings'
    id = db.Column(db.Integer, primary_key=True)
    canvas_id = db.Column(db.String(255), nullable=False, index=True, unique=True)
    name = db.Column(db.String(255), nullable=False)
    code = db.Column(db.String(255), nullable=False)
    start_at = db.Column(db.String(255), nullable=False)

    exams = db.relationship('Exam', uselist=True, cascade='all, delete-orphan',
                            order_by='Exam.display_name',
                            backref=backref('offering', uselist=False, single_parent=True))

    @property
    def start_at_date(self):
        return parse_ISO8601(self.start_at)

    def __repr__(self):
        return '<Offering {}>'.format(self.name)

    def mark_all_exams_as_inactive(self):
        Exam.query.filter_by(offering_canvas_id=self.canvas_id).update({"is_active": False})


class Exam(db.Model):
    __tablename__ = 'exams'
    id = db.Column(db.Integer, primary_key=True)
    offering_canvas_id = db.Column(db.ForeignKey(
        'offerings.canvas_id'), index=True, nullable=False)
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

    @property
    def unassigned_seats(self):
        return [seat for seat in itertools.chain(*self.seats) if seat.assignment == None]  # noqa

    @property
    def unassigned_students(self):
        return [student for student in self.students if student.assignment == None]  # noqa

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

    def __repr__(self):
        return '<Exam {}>'.format(self.name)


class Room(db.Model):
    __tablename__ = 'rooms'
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.ForeignKey('exams.id'), index=True, nullable=False)
    name = db.Column(db.String(255), nullable=False, index=True)
    display_name = db.Column(db.String(255), nullable=False)
    start_at = db.Column(db.String(255))
    duration_minutes = db.Column(db.Integer)

    @property
    def start_at_time(self):
        return parse_ISO8601(self.start_at)

    @property
    def start_at_time_display(self):
        return self.start_at_time.strftime('%I:%M %p - %b %d, %Y') if self.start_at_time else "Start Time TBA"

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

    def __repr__(self):
        return '<Room {}>'.format(self.name)


class Seat(db.Model):
    __tablename__ = 'seats'
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.ForeignKey('rooms.id'), index=True, nullable=False)
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
        return self.name if self.name else "Movable Seat"

    def __repr__(self):
        return '<Seat {}>'.format(self.name_display)


class Student(db.Model):
    __tablename__ = 'students'
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.ForeignKey('exams.id'), index=True, nullable=False)
    canvas_id = db.Column(db.String(255), nullable=False, index=True)
    email = db.Column(db.String(255), index=True, nullable=False)
    name = db.Column(db.String(255), nullable=False)
    sid = db.Column(db.String(255))
    wants = db.Column(StringSet, nullable=False)
    avoids = db.Column(StringSet, nullable=False)

    assignment = db.relationship('SeatAssignment', uselist=False, cascade='all, delete-orphan',
                                 backref=backref('student', uselist=False, single_parent=True))

    @property
    def first_name(self):
        return self.name.rsplit(',', 1)[-1].strip().title()

    def __repr__(self):
        return '<Student {} ({})>'.format(self.name, self.canvas_id)


class SeatAssignment(db.Model):
    __tablename__ = 'seat_assignments'
    __table_args__ = (
        PrimaryKeyConstraint('student_id', 'seat_id'),
    )
    student_id = db.Column(db.ForeignKey('students.id'), index=True, nullable=False)
    seat_id = db.Column(db.ForeignKey('seats.id'), index=True, nullable=False)
    emailed = db.Column(db.Boolean, default=False, index=True, nullable=False)


def slug(display_name):
    return re.sub(r'[^A-Za-z0-9._-]', '', display_name.lower())
