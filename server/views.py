from flask_login import login_required

from server import app

@app.route('/')
@login_required
def index():
    return 'Hello world!'
