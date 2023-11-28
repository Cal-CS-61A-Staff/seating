from tests.a11y.utils import run_axe, assert_no_violations, save_report, print_violations
from selenium.webdriver.common.by import By


def test_a11y_sanity(driver):
    """
    Checks a11y check are working
    """
    driver.get('http://localhost:5000/')
    report = run_axe(driver)
    assert report is not None


# Only three pages are visible to students: select offering, select exam, and seating chart
def test_a11y_select_offering_page(seeded_db, get_authed_driver):
    """
    Checks a11y for select offering page
    """
    report = run_axe(get_authed_driver("123456"))
    assert_no_violations(report)


def test_a11y_select_exam_page(seeded_db, get_authed_driver):
    """
    Checks a11y for select exam page
    """
    driver = get_authed_driver("123456")
    first_offering_btn = driver.find_element(By.CSS_SELECTOR, ".mdl-list__item-primary-content")
    assert first_offering_btn is not None
    first_offering_btn.click()
    report = run_axe(driver)
    assert_no_violations(report)

# TODO: add test for seating chart; need to setup seeding data first
