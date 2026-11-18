from flask import current_app
from flask_caching import Cache

# set up for each app by create_app
cache_store = Cache()


def cache_key_photo(sid: str):
    return f'student_photo_{sid}'


def cache_life_photo():
    return current_app.config['C1C_PHOTO_CACHE_LIFE']


def cache_key_roster_sids(offering_canvas_id: str):
    return f'roster_sids_{offering_canvas_id}'


def cache_key_roster_failed(offering_canvas_id: str):
    return f'roster_failed_{offering_canvas_id}'


# a seat map loads a photo per seated student: ask Canvas for the roster once for all of them, but
# soon notice a student who has dropped the course
ROSTER_SIDS_CACHE_LIFE = 300
