# Exam Seating App

The seating app assigns seats to students, taking some basic preferences into account. 
Students can log in with their Ok account to view their seat in their room. 
General course staff can project the seating chart during the beginning of the exam
and help individual students find their seat. An admin TA (configured through config vars)
will be able to choose rooms, assign seats, and mass email students their seat assignment.

This app uses Ok to manage access. Even if you aren't using Ok for assignments, 
you should create a course on Ok and enroll all of your staff, academic interns, 
and students with the appropriate roles.

## Usage (Admin TAs for Courses)

It's janky. Many steps involve directly poking the database. The only way to
correct errors is to manually edit the database, so be careful.

In summary, setting up the seating chart involves these steps:
1. *Create an exam* (ex. Midterm 1 or Final). Or at least in the future you will be able to.
For now, contact the slack to have your exam created for you if you did not set up the app.
This step is already done for you if you can successfully view the seating app.
2. *Add rooms.* Choose your rooms from our selection or import your own custom room.
3. *Import students.* Customize your student preferences (left seat, front/back, buildings, etc.)
4. *Assign! Then email!* 

Read further for more details regarding each step.

### Choosing rooms
#### Import a room
Room data is entered from a Google Sheet. If you picked your rooms from our selection,
those rooms are imported from the master room sheet.

Master: https://drive.google.com/open?id=1cHKVheWv2JnHBorbtfZMW_3Sxj9VtGMmAUU2qGJ33-s

If the room you want does not exist, you can try looking through the [rooms](https://drive.google.com/drive/u/1/folders/0B7ZiW-W5STesMG50eDgxNlJBZ1E) used in the past years.

#### Create a room
You can also create and customize the room you want with a Google spreadsheet.

One row of the spreadsheet corresponds to one row. The "Row" and "Seat" columns
specify the name of a seat. The "X" and "Y" are the coordinates in the seating
chart. If "X" is left blank, it defaults to one space stage right (house left)
to the previous seat. If "Y" is left blank, it defaults to the Y coordinate of
the previous seat. The remaining columns are arbitrary TRUE/FALSE "attributes",
which can give labels to seats such as LEFTY, RIGHTY, AISLE, FRONT, or RESERVED.
A blank value is interpreted as FALSE. Student preferences are given in terms
of these labels, and are used to match students to seats. It's helpful while
creating your room to preview it on the `Import rooms` page.

On the `Import Rooms` page, you can preview the seating chart for a room by specifying a room name,
Google Sheets URL, and sheet name. Create the room when you're sure it's ready.

If you created your own room sheet because it previously did not exist, we would appreciate
you adding the sheet to the [master doc](https://drive.google.com/open?id=1cHKVheWv2JnHBorbtfZMW_3Sxj9VtGMmAUU2qGJ33-s).

### Importing and Assigning students

To import students, create a Google spreadsheet with the columns "Name",
"Student ID", "Email", and "bCourses ID". The remaining columns are arbitrary attributes
(ex: LEFTY, RIGHTY, BROKEN) that express student preferences. 

For example, if a student has LEFTY=TRUE, they will be assigned a seat with the
LEFTY attribute. If a student has LEFTY=FALSE, they will be assigned a seat
without the LEFTY attribute. If a student's LEFTY attribute is blank, i.e. TRUE
nor FALSE, then they will could be assigned to either a LEFTY or non-LEFTY seat
as if they don't care.

You can add students to the spreadsheet and import them again later. Duplicates
will be merged.

Assign students by clicking on the `assign` button. Only unassigned students will
be assigned a seat. To reassign a student, delete their corresponding row from the
`seat_assignments` table.

### Emailing students

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

### Roster Photos

To allow for roster photos to appear in the app, set the `PHOTO_DIRECTORY` env
variable to a directory containing files at the path:

	{PHOTO_DIRECTORY}/{Course Offering}/{bCourses ID}.jpeg

The bCourses ID column is used to determine which photo to display for which
student.

In the past, we've used the DownThemAll Firefox extension to grab all of our
roster photos from bCourses. That extension no longer works in Firefox Quantum,
so you can either use an old version of Firefox with support for legacy add-ins,
or use the script `download_bcourses_photos.py` in this repo.

### During the exam

Staff can project the seating chart, and use the seating chart to identity
cheaters.

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

## Setup (development)
1. Clone the repository and change directories into the repository.
```
	git clone https://github.com/Cal-CS-61A-Staff/seating.git
	cd seating
```

2. Create and activate a virtual environment.
``` 
	python3 -m venv env 
	source env/bin/activate
```

3. Use pip to install all the dependencies.
```
	pip install -r requirements.txt
```

4. Add yourself to `cal/test/fa18` course (both as student and instructor but with different emails). Development server uses `cal/test/fa18` as its test OKPY course. 

5. Make sure your virtual environment is activated. Then set up the environment variables.
```
export FLASK_APP = server  (or server/__init__.py)
export FLASK_ENV = development
```

6. Modify `config.py` as necessary. Set `OK_CLIENT_ID`, `OK_CLIENT_SECRET`, `GOOGLE_OAUTH2_CLIENT_ID`, `GOOGLE_OAUTH2_CLIENT_SECRET`, `SENDGRID_API_KEY`, `PHOTO_DIRECTORY`, `EXAM`, `ADMIN` as needed.

7. Import [demo data](https://docs.google.com/spreadsheets/d/1nC2vinn0k-_TLO0aLmLZtI9juEoSOVEvA3o40HGvXAw/edit?usp=drive_web&ouid=100612133541464602205) for students and rooms (photos TBA). 

4. Initialize tables and seed the data: `flask resetdb`
This command drops previous tables, initializes tables and adds seeds the exams table. Students, rooms, etc. must be imported (see how in the previous section, Using the app). 

5. Run the app: `flask run`
This commands only needs to be run once.

6. Open [localhost:5000](https://localhost:5000)


## Production (First Time Deployment on dokku)
	dokku apps:create seating
	dokku mysql:create seating
	dokku mysql:link seating seating
	# Set DNS record
	dokku domains:add seating seating.cs61a.org
	# Change OK OAuth to support the domain

	dokku config:set seating <ENVIRONMENT VARIABLES>

	git remote add dokku dokku@apps.cs61a.org:seating
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
ADMIN
```

You can create an Ok OAuth client [here](https://okpy.org/admin/clients/), though it will need to be approved by an Ok admin before it can be used.
