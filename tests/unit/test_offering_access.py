"""
Offering pages are for the course's staff and students. The seed course 1234567 has Yu Long
(user 1) as staff, and Jimmy Xu (user 2) and Sharon Lovera (user 3) as students.
"""
import pytest

from server.models import User, db

OFFERING_URL = '/offerings/1234567/'


def test_offering_requires_login(seeded_db, client):
    response = client.get(OFFERING_URL)
    assert response.status_code == 302
    assert '/login' in response.location


@pytest.mark.parametrize('user_id', [1, 2, 3])
def test_course_members_see_the_offering(seeded_db, login_as, user_id):
    assert login_as(user_id).get(OFFERING_URL).status_code == 200


def test_offering_requires_course_membership(seeded_db, login_as):
    # Jimmy Xu is staff of 2345678 and a student of 1234567, but not in 3456789
    assert login_as(2).get('/offerings/3456789/').status_code == 403


def test_non_members_cannot_tell_which_courses_use_seating(seeded_db, login_as):
    # 9999999 is not set up for seating; a non-member gets the same answer as for 3456789
    assert login_as(2).get('/offerings/9999999/').status_code == 403


def test_members_learn_their_course_is_not_set_up(seeded_db, login_as):
    user = db.session.get(User, 2)
    user.student_offerings = user.student_offerings | {'9999999'}
    db.session.commit()
    assert login_as(2).get('/offerings/9999999/').status_code == 404
