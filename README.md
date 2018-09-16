# Exam Seating App

This app assigns seats to students, taking some basic preferences into account,
It allows students to log in with their Ok account and/or for emails to be sent,
and creates seating charts that can be used by staff, or projected to be used
by students. 

## Roster Photos

To allow for roster photos to appear in the app, set the `PHOTO_DIRECTORY` env
variable to a directory containing files at the path:

	{PHOTO_DIRECTORY}/{Course Offering}/{bCourses ID}.jpeg

The bCourses ID column is used to determine which photo to display for which
student.

I've found that the easiest way to get all of these photos is using the
DownThemAll extension in Firefox to grab all photos from the roster webpage on
bCourses.

## Using the app

It's janky. Many steps involve directly poking the database. The only way to
correct errors is to manually edit the database, so be careful.

### Authentication

Viewing full seating charts requires logging in as a TA or tutor through Ok.

Importing spreadsheets requires a separate Google OAuth login.

All paths at an exam route (e.g. `/cal/cs61a/fa17/midterm1`) require a proper
staff login.

The `/seat/<id>` routes are publicly accessible, and highlight a single seat on
a room's full seating chart without displaying any student info or info about
seat assignments.

When a student attempts to log in, they will be redirected to their assigned
seat page if it exists. This only works for the current COURSE and EXAM as
set in the environment variables.

### Creating exams

Create an exam by adding a row to the `exams` table. The exam that the home page
redirects to is hardcoded, so you may want to change that too. In the future,
there should be an interface to CRUD exams.

### Creating a room

Room data is entered from a Google Sheet. We'll store some existing rooms here:

https://drive.google.com/drive/u/1/folders/0B7ZiW-W5STesMG50eDgxNlJBZ1E

One row of the spreadsheet corresponds to one row. The "Row" and "Seat" columns
specify the name of a seat. The "X" and "Y" are the coordinates in the seating
chart. If "X" is left blank, it defaults to one space stage right (house left)
to the previous seat. If "Y" is left blank, it defaults to the Y coordinate of
the previous seat. The remaining columns are arbitrary TRUE/FALSE "attributes",
which can give labels to seats such as LEFTY, RIGHTY, AISLE, FRONT, or RESERVED.
A blank value is interpreted as FALSE. Student preferences are given in terms
of these labels, and are used to match students to seats.

Import a room by going to (e.g.)

https://seating.cs61a.org/cal/cs61a/sp17/final/rooms/import/

Here you can preview the seating chart for a room by specifying a room name,
Google Sheets URL, and sheet name. Create the room when you're sure it's ready.

Once your room is finalized, we would appreciate you adding the sheet to the
Drive folder linked above so that other exams can use them.

### Assigning students

Create a spreadsheet with one row for each student that will be assigned a seat.
It should have columns "Name", "Student ID", "Email", and "bCourses ID". The
remaining columns are arbitrary attributes that express student preferences. For
example, if a student has LEFTY=TRUE, they will be assigned a seat with the
LEFTY attribute. If a student has LEFTY=FALSE, they will be assigned a seat
without the LEFTY attribute. If a student's LEFTY attribute is blank, i.e. TRUE
nor FALSE, then they will could be assigned to either a LEFTY or non-LEFTY seat
as if they don't care.

Import students by going to (e.g.)

https://seating.cs61a.org/cal/cs61a/sp17/final/students/import/

You can add students to the spreadsheet and import them again later. Duplicates
will be merged.

Assign students to seats by going to

https://seating.cs61a.org/cal/cs61a/sp17/final/students/assign/

only unassigned students will be assigned a seat. To reassign a student,
delete their corresponding row from the `seat_assignments` table.

### Emailing students

Go to (e.g.)

https://seating.cs61a.org/cal/cs61a/sp17/final/students/email/

Students will receive an email that looks like
```
Hi -name-,

Here's your assigned seat for -exam-:

Room: -room-

Seat: -seat-

You can view this seat's position on the seating chart at:
<domain>/seat/-seatid-/

-additional text-
```

The "additional text" is a good place to tell them what to do if they have an
issue with their seat, and to sign the email (e.g. "- Cal CS 61A Staff").

### During the exam

Staff can project the seating chart, and use the seating chart to identity
cheaters.

## First Time Deployment

	dokku apps:create seating
	dokku mysql:create seating
	dokku mysql:link seating seating
	# Set DNS record
	dokku domains:add seating seating.cs61a.org
	# Change OK OAuth to support the domain

	dokku config:set seating <ENVIRONMENT VARIABLES>

	git remote add dokku dokku@app.cs61a.org:seating
	git push dokku master

	dokku run seating flask initdb
	dokku letsencrypt seating

In addition, add the following to `/home/dokku/seating/nginx.conf`:
```
proxy_buffer_size   128k;
proxy_buffers   4 256k;
proxy_busy_buffers_size   256k;
```

## Environment variables

```
FLASK_APP=server/__init__.py
SECRET_KEY
DATABASE_URL
OK_CLIENT_ID
OK_CLIENT_SECRET
GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET
COURSE
EXAM
DOMAIN
PHOTO_DIRECTORY=/app/storage
```

You can create an Ok OAuth client [here](https://okpy.org/admin/clients/), though it will need to be approved by an Ok admin before it can be used.
