"""
Runs axe on every page of the app, signed in as the kind of user who sees it.

Each page must meet WCAG 2.1 AA. The WCAG 2.2 AA, best-practice and Section 508 checks are
reported too, but are expected failures until the app meets them.
"""
import re
from dataclasses import dataclass

import pytest

from tests.a11y.conftest import BASE_URL, VIOLATIONS_BY_RULE
from tests.a11y.utils import COMPLETE_A11Y_STANDARDS, REQUIRED_A11Y_STANDARDS, assert_no_violations, run_axe, \
    save_report

# seeded users (tests/fixtures/user.json): Yu Long is staff in the seeded offering,
# and Jimmy Xu is a student in it with a seat
STAFF = '123456'
STUDENT = '234567'

EXAM = '/offerings/1234567/exams/midterm1'


@dataclass
class Page:
    name: str
    endpoint: str
    path: str
    user: str = None
    # where the page lands, when visiting it redirects
    lands_on: str = None


PAGES = [
    Page('home', 'views.index', '/'),
    Page('dev login', 'dev_login.dev_login_page', '/dev_login/'),

    Page('student offerings', 'views.offerings', '/offerings', STUDENT),
    Page('student offering', 'views.offering', '/offerings/1234567/', STUDENT),
    Page('student seat', 'views.student_single_seat', '/seats/1/', STUDENT),
    Page('student exam', 'views.exam', f'{EXAM}/', STUDENT, lands_on='/seats/1/'),

    Page('offerings', 'views.offerings', '/offerings', STAFF),
    Page('offering', 'views.offering', '/offerings/1234567/', STAFF),
    Page('new exam', 'views.new_exam', '/offerings/1234567/exams/new/', STAFF),
    Page('edit exam', 'views.edit_exam', f'{EXAM}/edit/', STAFF),
    Page('exam', 'views.exam', f'{EXAM}/', STAFF),
    Page('import room from custom sheet', 'views.import_room_from_custom_sheet',
         f'{EXAM}/rooms/import/from_custom_sheet/', STAFF),
    Page('import room from csv', 'views.import_room_from_csv_upload', f'{EXAM}/rooms/import/from_csv_upload/', STAFF),
    Page('import room manually', 'views.import_room_manually', f'{EXAM}/rooms/import/from_manual/', STAFF),
    Page('room', 'views.room', f'{EXAM}/rooms/1/', STAFF),
    Page('edit room', 'views.edit_room', f'{EXAM}/rooms/1/edit', STAFF),
    Page('students', 'views.students', f'{EXAM}/students/', STAFF),
    Page('import students', 'views.import_students', f'{EXAM}/students/import/', STAFF),
    Page('import students from canvas', 'views.import_students_from_canvas_roster',
         f'{EXAM}/students/import/from_canvas_roster/', STAFF),
    Page('edit students', 'views.edit_students', f'{EXAM}/students/edit', STAFF),
    Page('delete students', 'views.delete_students', f'{EXAM}/students/delete/', STAFF),
    Page('assign', 'views.assign', f'{EXAM}/students/assign/', STAFF),
    Page('email', 'views.email_all_students', f'{EXAM}/students/email/', STAFF),
    Page('student', 'views.student', f'{EXAM}/students/1', STAFF),
    Page('edit student', 'views.edit_student', f'{EXAM}/students/1/edit', STAFF),
    Page('assign student', 'views.assign_student', f'{EXAM}/students/1/assign/', STAFF),
    Page('email student', 'views.email_single_student', f'{EXAM}/students/1/email/', STAFF),
    Page('preview layout', 'views.preview_layout', '/layouts/preview/', STAFF),
]

# GET endpoints that are not audited, and why
SKIPPED_ENDPOINTS = {
    'static': 'not a page',
    'views.favicon': 'not a page',
    'views.students_template': 'not a page',
    'views.student_photo': 'not a page',
    'views.export_students_as_csv': 'not a page',
    'health.check': 'not a page',
    'health.check_db': 'not a page',
    'health.check_logging': 'not a page',
    'auth.login': 'redirects to the login page',
    'auth.authorized': 'redirects after login',
    'dev_login.mock_authorize': 'redirects during login',
    'views.add_offerings': 'redirects when every Canvas course is already added, as in the seed data',
    'views.import_room': 'reads the master room sheet from Google Sheets',
    'views.import_room_from_master_sheet': 'reads the master room sheet from Google Sheets',
}


def test_every_page_is_audited(app):
    get_endpoints = {rule.endpoint for rule in app.url_map.iter_rules() if 'GET' in rule.methods}
    audited = {page.endpoint for page in PAGES}
    missing = get_endpoints - audited - set(SKIPPED_ENDPOINTS)
    assert not missing, f"Add these to PAGES or SKIPPED_ENDPOINTS in {__file__}: {sorted(missing)}"
    assert not audited & set(SKIPPED_ENDPOINTS)


def _audit(a11y_site, page, standards, label):
    driver = a11y_site.visit(page.path, page.user)
    assert driver.current_url == BASE_URL + (page.lands_on or page.path)
    # Flask's error pages are titled with their status, e.g. "500 Internal Server Error"
    assert not re.match(r'\d{3} ', driver.title), driver.title
    report = run_axe(driver, standards)
    save_report(f'{page.name} {label}', report)
    for violation in report['violations']:
        VIOLATIONS_BY_RULE[f"{violation['id']} ({label})"].add(page.name)
    assert_no_violations(report)


@pytest.mark.parametrize('page', PAGES, ids=[page.name for page in PAGES])
def test_meets_wcag_21_aa(a11y_site, page):
    _audit(a11y_site, page, REQUIRED_A11Y_STANDARDS, 'WCAG 2.1 AA')


@pytest.mark.xfail(reason='WCAG 2.2 AA and best practices are not required yet')
@pytest.mark.parametrize('page', PAGES, ids=[page.name for page in PAGES])
def test_meets_wcag_22_aa(a11y_site, page):
    _audit(a11y_site, page, COMPLETE_A11Y_STANDARDS, 'WCAG 2.2 AA')
