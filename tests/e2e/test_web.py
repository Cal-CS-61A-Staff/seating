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


def test_dev_login(driver):
    """
    Test that dev login works
    """
    driver.get('http://localhost:5000/')
    first_dev_login_btn = driver.find_element(By.CSS_SELECTOR, '.form-buttons .mdl-button')
    assert first_dev_login_btn is not None
    first_dev_login_btn.click()
    assert 'Select a Course Offering' in driver.title
