from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from server.models import db, Student

STUDENTS_URL = 'http://localhost:5000/offerings/1234567/exams/midterm1/students/'


def _press_delete(driver, name):
    driver.find_element(By.CSS_SELECTOR, f'button[aria-label="Delete {name}"]').click()
    return WebDriverWait(driver, 5).until(EC.alert_is_present())


def test_deleting_a_student_is_confirmed_then_posted(get_authed_driver, seeded_db):
    driver = get_authed_driver("123456")
    driver.get(STUDENTS_URL)
    name = db.session.get(Student, 1).name

    alert = _press_delete(driver, name)
    assert 'Are you sure you want to delete this student?' in alert.text
    alert.dismiss()
    db.session.commit()  # end the test's transaction to see the server's writes
    assert db.session.get(Student, 1) is not None

    _press_delete(driver, name).accept()
    # the page is replaced as the post goes through: this wait, unlike reading the body directly,
    # tries again when it catches the old page's body going stale
    WebDriverWait(driver, 10).until(EC.text_to_be_present_in_element((By.TAG_NAME, 'body'), 'Deleted student.'))
    assert driver.current_url == STUDENTS_URL
    db.session.commit()
    assert db.session.get(Student, 1) is None
