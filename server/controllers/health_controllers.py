from flask import jsonify, current_app
from sqlalchemy import text

from server.controllers import health_module


@health_module.route('/')
def check():
    return jsonify(status="UP"), 200


@health_module.route('/db')
def check_db():
    from server.models import db
    try:
        db.session.execute(text("SELECT 1"))
        return jsonify(status="UP"), 200
    except Exception:
        # The error text can reveal database details, so it only goes to the logs.
        current_app.logger.exception("Database health check failed")
        return jsonify(status="DOWN"), 500


@health_module.route('/log')
def check_logging():
    current_app.logger.debug("Debug logging is working")
    current_app.logger.info("Info logging is working")
    current_app.logger.warning("Warning logging is working")
    current_app.logger.error("Error logging is working")
    return jsonify(status="SEE LOGS"), 200
