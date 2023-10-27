import click
import itertools
from natsort import natsorted
import re

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import PrimaryKeyConstraint, types
from sqlalchemy.orm import backref
from sqlalchemy import UniqueConstraint
from sqlalchemy.ext.associationproxy import association_proxy

from server import app

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
    canvas_id = db.Column(db.String(255), nullable=False, index=True)
    staff_offerings = db.Column(StringSet, nullable=False)
    student_offerings = db.Column(StringSet, nullable=False)


class Offering(db.Model):
    __tablename__ = 'offerings'
    id = db.Column(db.Integer, primary_key=True)
    canvas_id = db.Column(db.String(255), nullable=False, index=True)
    name = db.Column(db.String(255), nullable=False)
    code = db.Column(db.String(255), nullable=False)

    exams = db.relationship('Exam', uselist=True, cascade='all, delete-orphan',
                            order_by='Exam.display_name',
                            backref=backref('offering', uselist=False, single_parent=True))

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
                            order_by='Room.display_name',
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

    def __repr__(self):
        return '<Exam {}>'.format(self.name)


class Room(db.Model):
    __tablename__ = 'rooms'
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.ForeignKey('exams.id'), index=True, nullable=False)
    name = db.Column(db.String(255), nullable=False, index=True)
    display_name = db.Column(db.String(255), nullable=False)

    seats = db.relationship('Seat', uselist=True, cascade='all, delete-orphan',
                            order_by='Seat.name',
                            backref=backref('room', uselist=False, single_parent=True))

    __table_args__ = (
        UniqueConstraint('exam_id', 'name', name='uq_exam_id_name'),
    )

    @property
    def rows(self):
        seats = natsorted(self.seats, key=lambda seat: seat.row)
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
    name = db.Column(db.String(255), nullable=False)
    row = db.Column(db.String(255), nullable=False)
    seat = db.Column(db.String(255), nullable=False, index=True)
    x = db.Column(db.Float, nullable=False)
    y = db.Column(db.Float, nullable=False)
    attributes = db.Column(StringSet, nullable=False)

    assignment = db.relationship('SeatAssignment', uselist=False, cascade='all, delete-orphan',
                                 backref=backref('seat', uselist=False, single_parent=True))

    def __repr__(self):
        return '<Seat {}>'.format(self.name)


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

# Flask-CLI commands
# Run with `flask <cmd>`


@app.cli.command('initdb')
def init_db():
    """
    Initializes the database
    """
    click.echo('Creating database...')
    db.create_all()
    db.session.commit()


@app.cli.command('dropdb')
def drop_db():
    """
    Drops all tables from the database
    """
    doit = click.confirm('Are you sure you want to delete all data?')
    if doit:
        click.echo('Dropping database...')
        db.drop_all()

# For development purposes only


@app.cli.command('seeddb')
def seed_db():
    """
    Seeds the database with data
    There is no need to seed even in development, since the database is
    dynamically populated when app launches, see stub.py
    """
    pass


@app.cli.command('resetdb')
@click.pass_context
def reset_db(ctx):
    "Drops, initializes, then seeds tables with data"
    ctx.invoke(drop_db)
    ctx.invoke(init_db)
    ctx.invoke(seed_db)
