def test_webdriver_health(driver):
    """
    Test that webdriver works
    """
    driver.get('https://www.google.com')
    assert 'Google' in driver.title
