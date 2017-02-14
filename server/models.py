import re

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import PrimaryKeyConstraint, types

from server import app

db = SQLAlchemy(app=app)

class StringSet(types.TypeDecorator):
    impl = types.Text

    def process_bind_param(self, value, engine):
        if not value:
            return None
        else:
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

    room = db.relationship('Room')

class Student(db.Model):
    __tablename__ = 'students'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255))
    email = db.Column(db.String(255))
    sid = db.Column(db.String(255))
    attributes = db.Column(StringSet, nullable=False)

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

midterm1 = 'Midterm 1'
seed_exam = Exam(
    offering='cal/cs61a/sp17',
    name=slug(midterm1),
    display_name=midterm1,
)

@app.cli.command('initdb')
def init_db():
    print('Initializing database...')
    db.create_all()
    db.session.add(seed_exam)
    db.session.commit()