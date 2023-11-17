from selenium.webdriver.common.by import By


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
