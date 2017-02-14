from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy

from server import app

db = SQLAlchemy(app=app)

class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False, index=True)

@app.cli.command('initdb')
def init_db():
    print('Initializing database...')
    db.create_all()
