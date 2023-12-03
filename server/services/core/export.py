from server.services.csv import to_csv_str


def export_exam_student_info(exam) -> str:
    """
    Export exam student info to a CSV file.
    """
    headers = ['name', 'email', 'student id', 'canvas id', 'room', 'seat', 'emailed']
    rows = []
    for student in exam.students:
        rows.append({
            'name': student.name,
            'email': student.email,
            'student id': student.sid,
            'canvas id': student.canvas_id,
            'room': student.assignment.seat.room.name_and_start_at_time_display() if student.assignment else None,
            'seat': student.assignment.seat.display_name if student.assignment else None,
            'emailed': student.assignment.emailed if student.assignment else None,
        })
    csv_str = to_csv_str(headers, rows)
    return csv_str
