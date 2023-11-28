def test_webdriver_health(driver):
    """
    Test that webdriver works
    """
    driver.get('https://www.google.com')
    assert 'Google' in driver.title


def test_local_home_page(driver):
    """
    Test that home page works
    """
    driver.get('http://localhost:5000/')


def test_health_page(driver):
    """
    Test that health page works
    """
    driver.get('http://localhost:5000/health')
    assert 'UP' in driver.page_source


def test_db_health_page(driver):
    """
    Test that db health page works
    """
    driver.get('http://localhost:5000/health/db')
    assert 'UP' in driver.page_source
