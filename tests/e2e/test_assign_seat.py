from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from server.models import db, Student

ASSIGN_URL = 'http://localhost:5000/offerings/1234567/exams/midterm1/students/1/assign/'  # Jimmy Xu


def _open_assign_page(get_authed_driver, height=1000):
    driver = get_authed_driver("123456")
    driver.set_window_size(1400, height)
    driver.get(ASSIGN_URL)
    return driver


def test_clicking_seat_selects_it(get_authed_driver, seeded_db):
    driver = _open_assign_page(get_authed_driver)
    seat = driver.find_element(By.ID, '3')
    seat.click()

    field = driver.find_element(By.ID, 'seat_id')
    assert field.get_attribute('value') == '3'
    assert 'selected' in seat.get_attribute('class')
    assert driver.find_element(By.ID, 'selected-seat').text == 'Selected seat: B1'

    # picking another seat moves the selection
    driver.find_element(By.ID, '4').click()
    assert 'selected' not in seat.get_attribute('class')
    assert driver.find_element(By.ID, 'selected-seat').text == 'Selected seat: B2'


def test_typing_seat_id_selects_it(get_authed_driver, seeded_db):
    driver = _open_assign_page(get_authed_driver)
    field = driver.find_element(By.ID, 'seat_id')
    field.send_keys('2')
    assert 'selected' in driver.find_element(By.ID, '2').get_attribute('class')
    assert driver.find_element(By.ID, 'selected-seat').text == 'Selected seat: A2'

    field.send_keys('99')
    assert driver.find_elements(By.CSS_SELECTOR, '.s.selected') == []
    assert driver.find_element(By.ID, 'selected-seat').text == ''


def test_assign_bar_stays_in_view(get_authed_driver, seeded_db):
    # in a short window, scrolling down the room maps would hide the form without the sticky bar
    driver = _open_assign_page(get_authed_driver, height=500)
    positions = driver.execute_script("""
        // scroll partway; at the very end, content after the page body pushes sticky elements up
        window.scrollTo(0, 150);
        var submit = document.getElementById('submit').getBoundingClientRect();
        return {
            scrolled: window.scrollY,
            barTop: document.querySelector('.assign-bar').getBoundingClientRect().top,
            submitVisible: submit.top >= 0 && submit.bottom <= window.innerHeight,
        };
    """)
    assert positions['scrolled'] > 0
    assert positions['barTop'] == 0
    assert positions['submitVisible']


def test_assign_chosen_seat(get_authed_driver, seeded_db):
    driver = _open_assign_page(get_authed_driver)
    driver.find_element(By.ID, '3').click()
    driver.find_element(By.ID, 'submit').click()
    WebDriverWait(driver, 5).until(lambda d: d.current_url != ASSIGN_URL)

    assert driver.current_url.endswith('/students/')
    assert 'Successfully assigned' in driver.find_element(By.TAG_NAME, 'body').text
    db.session.commit()  # end the test's transaction to see the server's write
    student = Student.query.filter_by(canvas_id='234567').one()
    assert student.assignment.seat_id == 3


def test_seat_photos_load_only_when_shown(get_authed_driver, seeded_db):
    # seat 1 is taken in the seed data, so its tooltip carries the student's photo
    driver = _open_assign_page(get_authed_driver)
    WebDriverWait(driver, 5).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    photo_requests = """
        return performance.getEntriesByType('resource').filter(e => e.name.includes('/photo/')).length
    """
    assert driver.execute_script(photo_requests) == 0

    seat = driver.find_element(By.ID, '1')
    driver.execute_script('arguments[0].scrollIntoView({block: "center"})', seat)
    ActionChains(driver).move_to_element(seat).perform()
    photo = WebDriverWait(driver, 5).until(lambda d: d.find_element(By.CSS_SELECTOR, '.tooltip .photo img'))
    # the placeholder shows behind the photo, which is shown once it has loaded
    frame = photo.find_element(By.XPATH, '..')
    assert 'photo-placeholder.png' in driver.execute_script(
        'return getComputedStyle(arguments[0]).backgroundImage', frame)
    WebDriverWait(driver, 5).until(lambda d: 'loaded' in photo.get_attribute('class').split())
    assert driver.execute_script('return arguments[0].naturalWidth > 0', photo)
    assert driver.execute_script('return getComputedStyle(arguments[0]).opacity', photo) == '1'
    assert driver.execute_script(photo_requests) == 1
