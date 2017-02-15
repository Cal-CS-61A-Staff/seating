import json
import re

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import PrimaryKeyConstraint, types
from sqlalchemy.orm import backref

from server import app

db = SQLAlchemy(app=app)

class Json(types.TypeDecorator):
    impl = types.Text

    def process_bind_param(self, value, dialect):
        # Python -> SQL
        return json.dumps(value)

    def process_result_value(self, value, dialect):
        # SQL -> Python
        return json.loads(value)

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

    exam = db.relationship('Exam', backref='rooms')

class Seat(db.Model):
    __tablename__ = 'seats'
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.ForeignKey('rooms.id'), index=True, nullable=False)
    name = db.Column(db.String(255), nullable=False)
    row = db.Column(db.String(255), nullable=False)
    seat = db.Column(db.String(255), nullable=False, index=True)
    x = db.Column(db.Float, nullable=False)
    y = db.Column(db.Float, nullable=False)
    attributes = db.Column(Json, nullable=False)

    room = db.relationship('Room', backref='seats')

class Student(db.Model):
    __tablename__ = 'students'
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.ForeignKey('exams.id'), index=True, nullable=False)
    email = db.Column(db.String(255), index=True)
    name = db.Column(db.String(255))
    student_id = db.Column(db.String(255))
    preferences = db.Column(Json, nullable=False)

    exam = db.relationship('Exam', backref='students')

    @property
    def wants(self):
        return {k for k, v in self.preferences.items() if v}

    @property
    def rejects(self):
        return {k for k, v in self.preferences.items() if not v}

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

midterm1 = 'Midterm 1'
seed_exam = Exam(
    offering='cal/cs61a/sp17',
    name=slug(midterm1),
    display_name=midterm1,
)

@app.cli.command('initdb')
def init_db():
    print('Initializing database...')
    db.drop_all()
    db.create_all()
    db.session.add(seed_exam)
    db.session.commit()
