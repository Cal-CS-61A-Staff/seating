from server.models import Seat, User, Offering, Exam, Room, Student


def test_health():
    """
    Test that testing framework works
    """
    assert True


def test_client_health(client):
    """
    Test that client and making requests works
    """
    response = client.get('/')
    assert response.status_code == 302  # redirect to login


def test_db_health(db):
    """
    Test that database access works
    """
    new_user = User(name='test',
                    canvas_id='test',
                    staff_offerings=['test'],
                    student_offerings=['test'])
    db.session.add(new_user)
    db.session.commit()
    assert User.query.filter_by(name='test').first() is not None


def test_db_rollback(db):
    """
    Test that database commits of different cases do not interfere with each other
    """
    assert User.query.filter_by(name='test').first() is None


def test_seeded_db(seeded_db):
    """
    Test that seeded database works
    """
    assert User.query.count() > 0
    assert Offering.query.count() > 0
    assert Exam.query.count() > 0
    room = Room.query.first()
    assert room is not None
    assert room.seats is not None
    assert Student.query.count() > 0

    # now remove all user
    User.query.delete()
    seeded_db.session.commit()
    assert User.query.count() == 0


def test_seeded_db_rollback(seeded_db):
    """
    Test that the previous test did not affect the seeded database
    """
    assert User.query.count() > 0


def test_mocking(mocker):
    """
    Test that api mocking works
    """
    import requests
    mocker.get(
        "http://xyz.com/api/1/foobar",
        body="{}",
        status=200,
        content_type="application/json",
    )
    resp = requests.get("http://xyz.com/api/1/foobar")
    assert resp.status_code == 200
    assert resp.json() == {}


def test_multiple_fixtures(app, client, db):
    """
    Test that multiple fixtures work
    """
    assert app is not None
    assert client is not None
    assert db is not None
