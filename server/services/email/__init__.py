
import sendgrid

from server import app
from server.models import db, Room, Seat, SeatAssignment


def email_students(exam, form):
    """Emails students in batches of 900"""
    sg = sendgrid.SendGridAPIClient(api_key=app.config['SENDGRID_API_KEY'])
    test = form.test_email.data
    while True:
        limit = 1 if test else 900
        assignments = SeatAssignment.query.join(SeatAssignment.seat).join(Seat.room).filter(
            Room.exam_id == exam.id,
            not SeatAssignment.emailed
        ).limit(limit).all()
        if not assignments:
            break

        data = {
            'personalizations': [
                {
                    'to': [
                        {
                            'email': test if test else assignment.student.email,
                        }
                    ],
                    'substitutions': {
                        '-name-': assignment.student.first_name,
                        '-room-': assignment.seat.room.display_name,
                        '-seat-': assignment.seat.name,
                        '-seatid-': str(assignment.seat.id),
                    },
                }
                for assignment in assignments
            ],
            'from': {
                'email': form.from_email.data,
                'name': form.from_name.data,
            },
            'subject': form.subject.data,
            'content': [
                {
                    'type': 'text/plain',
                    'value': '''
Hi -name-,

Here's your assigned seat for {}:

Room: -room-

Seat: -seat-

You can view this seat's position on the seating chart at:
{}/seat/-seatid-/

{}
'''.format(exam.display_name, app.config['DOMAIN'], form.additional_text.data)
                },
            ],
        }

        response = sg.client.mail.send.post(request_body=data)
        if response.status_code < 200 or response.status_code >= 400:
            raise Exception('Could not send mail. Status: {}. Body: {}'.format(
                response.status_code, response.body
            ))
        if test:
            return
        for assignment in assignments:
            assignment.emailed = True
        db.session.commit()
