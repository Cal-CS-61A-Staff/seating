from server.models import User


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


def test_multiple_fixtures(app, client, db):
    """
    Test that multiple fixtures work
    """
    assert app is not None
    assert client is not None
    assert db is not None
