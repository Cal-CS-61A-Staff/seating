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
