from collections import defaultdict

import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from config import TestingConfig
from server.application import create_app
from server.models import db as sqlalchemy_db
from tests.a11y.utils import REPORT_DIR, slugify
from tests.conftest import chrome_driver, flask_server
from tests.fixtures import seed_db

BASE_URL = 'http://localhost:5000'

# rule id -> pages that break it, printed at the end of the run
VIOLATIONS_BY_RULE = defaultdict(set)


class Site:
    """One browser on one server, shared by every page audit, signed in as whoever a page needs."""

    def __init__(self, driver):
        self.driver = driver
        self.user = None

    def visit(self, path, user=None):
        if user != self.user:
            # log out with the navbar's Log Out form, which posts; not every audited page has the navbar
            if self.user is not None:
                self.driver.get(f'{BASE_URL}/offerings')
                self.driver.execute_script("document.querySelector('form[action=\"/logout/\"]').submit()")
                WebDriverWait(self.driver, 10).until(EC.url_to_be(f'{BASE_URL}/'))
            if user is not None:
                self._login(user)
            self.user = user
        self.driver.get(BASE_URL + path)
        WebDriverWait(self.driver, 10).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        return self.driver

    def _login(self, user):
        self.driver.get(f'{BASE_URL}/login/')
        self.driver.find_element(By.CSS_SELECTOR, '#user_id').send_keys(user)
        self.driver.find_element(By.CSS_SELECTOR, '#submit').click()
        WebDriverWait(self.driver, 10).until(EC.url_to_be(f'{BASE_URL}/offerings'))


@pytest.fixture(scope='session')
def a11y_site():
    with create_app(TestingConfig).app_context():
        sqlalchemy_db.drop_all()
        sqlalchemy_db.create_all()
        seed_db()
        sqlalchemy_db.session.remove()

    with flask_server():
        # a tall window keeps most of each page on screen, since axe skips the contrast of text off screen
        driver = chrome_driver('--window-size=1280,4000')
        try:
            yield Site(driver)
        finally:
            driver.quit()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    site = item.funcargs.get('a11y_site') if hasattr(item, 'funcargs') else None
    if report.when == 'call' and report.failed and site is not None:
        screenshots = REPORT_DIR / 'screenshots'
        screenshots.mkdir(parents=True, exist_ok=True)
        site.driver.save_screenshot(str(screenshots / f'{slugify(item.name)}.png'))


def pytest_terminal_summary(terminalreporter):
    if not VIOLATIONS_BY_RULE:
        return
    terminalreporter.section('accessibility violations by rule')
    for rule, pages in sorted(VIOLATIONS_BY_RULE.items()):
        terminalreporter.write_line(f'{rule} ({len(pages)} pages)')
        for page in sorted(pages):
            terminalreporter.write_line(f'  {page}')
