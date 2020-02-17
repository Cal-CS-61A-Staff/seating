import click
import itertools
from natsort import natsorted
import re

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import PrimaryKeyConstraint, types
from sqlalchemy.orm import backref

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
    email = db.Column(db.String(255), nullable=False, index=True)
    offerings = db.Column(StringSet, nullable=False)

class Exam(db.Model):
    __tablename__ = 'exams'
    id = db.Column(db.Integer, primary_key=True)
    offering = db.Column(db.String(255), nullable=False, index=True)
    name = db.Column(db.String(255), nullable=False, index=True)
    display_name = db.Column(db.String(255), nullable=False)

class Room(db.Model):
    __tablename__ = 'rooms'
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.ForeignKey('exams.id'), index=True, nullable=False)
    name = db.Column(db.String(255), nullable=False, index=True)
    display_name = db.Column(db.String(255), nullable=False)

    exam = db.relationship('Exam', backref=backref('rooms', order_by='Room.display_name'))

    @property
    def rows(self):
        seats = natsorted(self.seats, key=lambda seat: seat.row)
        return [
            natsorted(g, key=lambda seat: seat.x)
            for _, g in itertools.groupby(seats, lambda seat: seat.row)
        ]

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

    room = db.relationship('Room', backref='seats')

class Student(db.Model):
    __tablename__ = 'students'
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.ForeignKey('exams.id'), index=True, nullable=False)
    email = db.Column(db.String(255), index=True, nullable=False)
    name = db.Column(db.String(255), nullable=False)
    sid = db.Column(db.String(255))
    bcourses_id = db.Column(db.String(255))
    wants = db.Column(StringSet, nullable=False)
    avoids = db.Column(StringSet, nullable=False)

    exam = db.relationship('Exam', backref='students')

    @property
    def first_name(self):
        return self.name.rsplit(',', 1)[-1].strip().title()

class SeatAssignment(db.Model):
    __tablename__ = 'seat_assignments'
    __table_args__ = (
        PrimaryKeyConstraint('student_id', 'seat_id'),
    )
    student_id = db.Column(db.ForeignKey('students.id'), index=True, nullable=False)
    seat_id = db.Column(db.ForeignKey('seats.id'), index=True, nullable=False)
    emailed = db.Column(db.Boolean, default=False, index=True, nullable=False)

    student = db.relationship('Student', backref=backref('assignment', uselist=False))
    seat = db.relationship('Seat', backref=backref('assignment', uselist=False))

def slug(display_name):
    return re.sub(r'[^A-Za-z0-9._-]', '', display_name.lower())

# Flask-CLI commands
# Run with `flask <cmd>`
@app.cli.command('initdb')
def init_db():
    "Initializes the database"
    click.echo('Creating database...')
    db.create_all()
    db.session.commit()

@app.cli.command('dropdb')
def drop_db():
    "Drops all tables"
    doit = click.confirm('Are you sure you want to delete all data?')
    if doit:
        click.echo('Dropping database...')
        db.drop_all()

# For development purposes only
@app.cli.command('seeddb')
def seed_db():
    "Seeds database with data"
    for seed_exam in seed_exams:
        existing = Exam.query.filter_by(offering=seed_exam.offering, name=seed_exam.name).first()
        if not existing:
            click.echo('Adding seed exam {}...'.format(seed_exam.name))
            db.session.add(seed_exam)
            db.session.commit()

@app.cli.command('resetdb')
@click.pass_context
def reset_db(ctx):
    "Drops, initializes, then seeds tables with data"
    ctx.invoke(drop_db)
    ctx.invoke(init_db)
    ctx.invoke(seed_db)

seed_exams = [
    Exam(
        offering=app.config['COURSE'],
        name='midterm1',
        display_name='Midterm 1',
    ),
    Exam(
        offering=app.config['COURSE'],
        name='midterm2',
        display_name='Midterm 2',
    ),
    Exam(
        offering=app.config['COURSE'],
        name='final',
        display_name='Final',
    ),
    Exam(
        offering="cal/eecs16a/sp20",
        name='test',
        display_name='Test',
    ),
]
