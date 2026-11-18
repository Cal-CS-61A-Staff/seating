import re

from server.models import db, Exam, Offering

OFFERING = '1234567'


def _csrf_token(page):
    return re.search(r'name="csrf_token" type="hidden" value="([^"]+)"', page).group(1)


def test_hiding_keeps_the_offering_and_its_exams(seeded_db, login_as):
    exams_before = Exam.query.filter_by(offering_canvas_id=OFFERING).count()
    response = login_as(1).post(f'/offerings/{OFFERING}/hide/', follow_redirects=True)
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert 'Its exams are kept' in page
    offering = Offering.query.filter_by(canvas_id=OFFERING).one()
    assert offering.is_hidden
    assert Exam.query.filter_by(offering_canvas_id=OFFERING).count() == exams_before
    # left off the offerings page
    assert f'/offerings/{OFFERING}/"' not in page


def test_hidden_offering_is_not_listed_for_students(seeded_db, login_as):
    Offering.query.filter_by(canvas_id=OFFERING).one().is_hidden = True
    db.session.commit()
    # user 2 is a student in this offering
    page = login_as(2).get('/offerings').get_data(as_text=True)
    assert f'/offerings/{OFFERING}/"' not in page


def test_only_staff_can_hide(seeded_db, login_as):
    # user 2 is a student in this offering
    response = login_as(2).post(f'/offerings/{OFFERING}/hide/')
    assert response.status_code == 403
    assert not Offering.query.filter_by(canvas_id=OFFERING).one().is_hidden


def test_importing_a_hidden_offering_shows_it_again(seeded_db, login_as):
    Offering.query.filter_by(canvas_id=OFFERING).one().is_hidden = True
    db.session.commit()
    client = login_as(1)
    page = client.get('/offerings/new').get_data(as_text=True)
    assert f'value="{OFFERING}"' in page
    response = client.post('/offerings/new', data={
        'csrf_token': _csrf_token(page), 'offerings': [OFFERING], 'submit': 'y',
    }, follow_redirects=True)
    assert response.status_code == 200
    assert f'/offerings/{OFFERING}/"' in response.get_data(as_text=True)
    offerings = Offering.query.filter_by(canvas_id=OFFERING).all()
    assert len(offerings) == 1 and not offerings[0].is_hidden
    assert offerings[0].exams
