from selenium.webdriver.common.by import By


def test_student_can_see_offerings(get_authed_driver, seeded_db):
    driver = get_authed_driver("234567")
    offering_btns = driver.find_elements(By.CSS_SELECTOR, ".mdl-list__item-primary-content")
    for btn in offering_btns:
        if "Introduction to Software Engineering" in btn.text:
            break
    else:
        assert False


def test_student_can_see_exam(get_authed_driver, seeded_db):
    driver = get_authed_driver("234567")
    offering_btns = driver.find_elements(By.CSS_SELECTOR, ".mdl-list__item-primary-content")
    for btn in offering_btns:
        if "Introduction to Software Engineering" in btn.text:
            btn.click()
            break
    else:
        assert False
    exam_btn = driver.find_element(By.CSS_SELECTOR, ".mdl-list__item-primary-content")
    assert "Midterm 1" in exam_btn.text
