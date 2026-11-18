def test_server_health(client):
    """
    Test that server health page works
    """
    response = client.get('/health/')
    assert response.status_code == 200
    assert 'UP' in response.data.decode('utf-8')


def test_server_health_db(client):
    """
    Test that server health page works
    """
    response = client.get('/health/db')
    assert response.status_code == 200
    assert 'UP' in response.data.decode('utf-8')


def test_server_health_db_down_hides_error(client, monkeypatch):
    """
    A failing database check reports DOWN without the database's error text
    """
    from server.models import db

    def fail(*args, **kwargs):
        raise RuntimeError('connection to secret-host:5432 failed')

    monkeypatch.setattr(db.session, 'execute', fail)
    response = client.get('/health/db')
    assert response.status_code == 500
    assert response.get_json() == {'status': 'DOWN'}
