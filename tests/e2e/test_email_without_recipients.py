"""
Once every student has been emailed, the email page starts with To empty (issue #147). A test email
still sends, since it only goes to the test address; "Send to students" says To needs someone.
"""
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from server.models import db, Student

EMAIL_URL = 'http://localhost:5000/offerings/1234567/exams/midterm1/students/email/'


def _open_with_everyone_emailed(get_authed_driver):
    jimmy = Student.query.filter_by(exam_id=1, canvas_id='234567').one()
    jimmy.assignment.emailed = True
    db.session.commit()
    driver = get_authed_driver("123456")
    driver.get(EMAIL_URL)
    assert driver.find_element(By.ID, 'to_addr').get_attribute('value') == ''
    driver.find_element(By.ID, 'reply_to').send_keys('staff@berkeley.edu')
    return driver


def test_send_test_is_not_blocked_by_an_empty_to(get_authed_driver, seeded_db):
    driver = _open_with_everyone_emailed(get_authed_driver)
    driver.find_element(By.ID, 'test_to_addr').send_keys('me@berkeley.edu')
    driver.find_element(By.ID, 'send_test').click()

    # the test server has no SMTP server, so the test fails to send, but it got past the browser and the form
    WebDriverWait(driver, 10).until(lambda d: d.find_elements(By.CLASS_NAME, 'alert-message'))
    flashes = [element.text for element in driver.find_elements(By.CLASS_NAME, 'alert-message')]
    assert flashes == ['Failed to send the test email.']


def test_send_to_students_with_an_empty_to_says_why(get_authed_driver, seeded_db):
    driver = _open_with_everyone_emailed(get_authed_driver)
    driver.execute_script("""
        window.fetched = 0;
        const realFetch = window.fetch;
        window.fetch = function (url, options) { window.fetched += 1; return realFetch(url, options); };
    """)
    driver.find_element(By.ID, 'submit').click()

    progress = driver.find_element(By.ID, 'send-progress')
    WebDriverWait(driver, 10).until(lambda d: progress.text)
    assert progress.text == 'Enter at least one student email address.'
    assert driver.execute_script('return window.fetched') == 0
    assert driver.current_url == EMAIL_URL
