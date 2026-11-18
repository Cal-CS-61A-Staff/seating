from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from server.models import db, Exam, Room, Seat, SeatAssignment, Student

EMAIL_URL = 'http://localhost:5000/offerings/1234567/exams/midterm1/students/email/'
EXTRA_STUDENTS = 120  # with Jimmy Xu, who is seated in the seed: 121 students, so batches of 50, 50 and 21


def _seat_a_class(seeded_db):
    exam = db.session.get(Exam, 1)
    room = Room(name='hall', display_name='Hall', start_at='2023-12-12T10:00:00Z!', duration_minutes=120)
    exam.rooms.append(room)
    for i in range(EXTRA_STUDENTS):
        seat = Seat(name=f'A{i + 1}', row='A', seat=str(i + 1), fixed=True, x=i, y=0, attributes=set())
        room.seats.append(seat)
        student = Student(exam_id=exam.id, canvas_id=str(800000 + i), name=f'Student {i:03d}',
                          email=f's{i:03d}@berkeley.edu', wants=set(), avoids=set(), room_wants=set(),
                          room_avoids=set())
        db.session.add(SeatAssignment(student=student, seat=seat))
    db.session.commit()


def test_email_page_sends_to_a_large_class_in_batches(get_authed_driver, seeded_db):
    _seat_a_class(seeded_db)
    driver = get_authed_driver("123456")
    driver.get(EMAIL_URL)
    # record what the page sends in each request, what it shows meanwhile, and whether leaving
    # the page would ask first (a cancelled beforeunload is what makes the browser ask)
    driver.execute_script("""
        window.batches = [];
        window.leaveBlocked = () => !window.dispatchEvent(new Event('beforeunload', {cancelable: true}));
        const realFetch = window.fetch;
        window.fetch = function (url, options) {
            window.batches.push({to: options.body.get('to_addr').split(',').length,
                                 cc: options.body.get('cc_addr'),
                                 shown: document.getElementById('send-progress').innerText.split('\\n')[0],
                                 bar: document.querySelector('#send-progress progress').value,
                                 leaveBlocked: window.leaveBlocked()});
            return realFetch(url, options);
        };
    """)
    driver.find_element(By.ID, 'reply_to').send_keys('staff@berkeley.edu')
    driver.find_element(By.ID, 'cc_addr').send_keys('head-ta@berkeley.edu')
    driver.find_element(By.ID, 'submit').click()

    progress = driver.find_element(By.ID, 'send-progress')
    WebDriverWait(driver, 30).until(lambda d: progress.text.startswith('Emailed'))
    assert driver.current_url == EMAIL_URL
    # every batch carries the CC, so every student's email does (staff see a student's reply-all)
    batches = driver.execute_script('return window.batches')
    assert [(b['to'], b['cc']) for b in batches] == [
        (50, 'head-ta@berkeley.edu'), (50, 'head-ta@berkeley.edu'), (21, 'head-ta@berkeley.edu')]
    # while sending: the count so far, a time estimate once a batch is back, and closing the page asks first
    assert batches[0]['shown'] == 'Emailing students: 0 of 121 done…'
    assert batches[1]['shown'] == 'Emailing students: 50 of 121 done, less than a minute left…'
    assert [b['bar'] for b in batches] == [0, 50, 100]
    assert all(b['leaveBlocked'] for b in batches)
    # once done, the page can be left freely and the in-progress bar and note are gone
    assert not driver.execute_script('return window.leaveBlocked()')
    assert not driver.find_elements(By.CSS_SELECTOR, '#send-progress progress')
    assert 'Keep this page open' not in progress.text
    # the test server has no SMTP server, so every email fails, and the page says so
    lines = progress.text.split('\n')
    assert lines[0] == 'Emailed 0 of 121 students.'
    assert lines[1].startswith('Failed to email: ') and lines[1].count('@') == 121
    assert lines[-1] == 'Back to the students page'
    assert not driver.find_element(By.ID, 'submit').get_attribute('disabled')

    db.session.commit()  # end the test's transaction to see the server's writes
    assert Student.query.filter_by(exam_id=1).count() == 3 + EXTRA_STUDENTS
    assert not any(student.assignment and student.assignment.emailed
                   for student in Student.query.filter_by(exam_id=1))
