import json

FAKE_USERS = None
FAKE_COURSES = None
FAKE_ENROLLMENTS = None

if not FAKE_USERS:
    with open('server/services/canvas/fake_data/fake_users.json', 'r') as f:
        FAKE_USERS = json.load(f)
if not FAKE_COURSES:
    with open('server/services/canvas/fake_data/fake_courses.json', 'r') as f:
        FAKE_COURSES = json.load(f)
if not FAKE_ENROLLMENTS:
    with open('server/services/canvas/fake_data/fake_enrollments.json', 'r') as f:
        FAKE_ENROLLMENTS = json.load(f)
