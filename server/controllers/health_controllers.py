
from flask import jsonify

from server.controllers import health_module


@health_module.route('/')
def check():
    return jsonify(status="UP"), 200


@health_module.route('/db')
def check_db():
    from server.models import db
    try:
        db.session.execute("SELECT 1")
        return jsonify(status="UP"), 200
    except Exception as e:
        return jsonify(status="DOWN", error=e.message), 500
