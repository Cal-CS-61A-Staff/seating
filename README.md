# Exam Seating App

[![codecov](https://codecov.io/gh/berkeley-eecs/seating/graph/badge.svg?token=0FJ178HK0N)](https://codecov.io/gh/berkeley-eecs/seating)

The seating app's primary goal is to assign seats to students for exams.

Table of Contents:

- [Exam Seating App](#exam-seating-app)
  - [Introduction](#introduction)
  - [Features and Benefits](#features-and-benefits)
  - [For Course Staff](#for-course-staff)
    - [Quick Start](#quick-start)
      - [Step 1: Work with Offerings](#step-1-work-with-offerings)
      - [Step 2: Work with Exams](#step-2-work-with-exams)
      - [Step 3: Work with Rooms and Students](#step-3-work-with-rooms-and-students)
      - [Step 4: Setting Preferences, Assign Seats and Email Students](#step-4-setting-preferences-assign-seats-and-email-students)
    - [Detailed Guide](#detailed-guide)
      - [Creating Exams](#creating-exams)
      - [Importing Rooms](#importing-rooms)
      - [Google Sheets Format for Rooms](#google-sheets-format-for-rooms)
      - [Importing Students](#importing-students)
      - [Reviewing Data, Assigning Seats](#reviewing-data-assigning-seats)
      - [Emailing students](#emailing-students)
      - [Get Roster Photos](#get-roster-photos)
      - [During the exam](#during-the-exam)
  - [For Developers](#for-developers)
    - [Local Setup](#local-setup)
    - [Environment Variables](#environment-variables)
    - [Available CLI Commands](#available-cli-commands)
    - [Devops](#devops)
      - [Testing](#testing)
      - [CI/CD](#cicd)
      - [Deployment](#deployment)

## Introduction

The entire app is protected behind Canvas (bCourses) authentication and authorization, so only Berkeley students can access the app. Only individuals that are enrolled in a certain course can access the app for that course - the type of enrollment (student, staff, etc.) fetched from Canvas determines the level of access.

Course staff can create, edit, and delete exams, rooms, students rosters and preferences, assign seats to students, and mass email students about their assignments. Students can view their available seat assignment.

## Features and Benefits

- Ensures fair seating arrangements for all students taking the exam, while taking into account student preferences (e.g. lefty chair, dsp accomodation etc.)
- Securely stores sensitive student and exam data abide by FERPA and other privacy laws, allowing only authorized staff to access the data.
- Streamlines the administrative process by automating seat assignment, reducing the workload on staff and minimizing errors in seating allocation.
- Allowing exam seating email notification and seating chart projection during the exam, smoothing the logistical processes for both students and staff.
- Allows staff to easily identify cheaters during exams by seating location, minimizing the possibility of academic misconduct or cheating during exams.

## For Course Staff

### Quick Start

#### Step 1: Work with Offerings

After logging in you will be able to see a list of enrolled courses (we call it "offerings"). Click into any offering listed under "Staff Offerings" you want to work with to start using the seating app for that offering.

#### Step 2: Work with Exams

You will see a list of existing exams created for this offering. Click into any of them to start working with the exam. If you want to create a new exam, click the "Create" button. You can star or delete exams on this page too. Starring an exam won't do anything other than a visual effect.

#### Step 3: Work with Rooms and Students

After clicking into an exam, you will see a list of existing rooms and students already imported (or nothing, if this is a newly created exam). Naturally you will want to import rooms and students so you can start assigning seats. Click the "Import Rooms" or "Import Students" button to start importing. There are different options for importing rooms and students, which will be explained in the later section.

#### Step 4: Setting Preferences, Assign Seats and Email Students

Student and email data could come from different sources (Google Sheets, csv upload, Canvas Roster etc.) but have to be consolidated within the app itself. You may need to tweak student preferences (e.g. lefty, righty, front, back, etc.) and review all data imported before you start assigning seats. If you are sure about your student and room data, click the "Assign" button to start assigning seats. You can also click the "Email" button to send out emails to students about their seat assignments.

### Detailed Guide

#### Creating Exams

- `name` are `display_name` are different. `name` is like a unique id while `display_name` is what students see.

#### Importing Rooms

- All Room data are entered from a Google Sheet. Thus, you will need login to Google to import rooms. You can only use Google Sheets that you have access to from your Google account.
- There is a [master room sheet](https://drive.google.com/open?id=1cHKVheWv2JnHBorbtfZMW_3Sxj9VtGMmAUU2qGJ33-s) containing some commonly used exam rooms and seat information. This sheet is already hardcoded into the seating app. To import a room from the master sheet, simply select the room name from the checkbox menu.
- You can also create your own sheet and type in the sheet url and tab to import a custom room. You may reference [rooms](https://drive.google.com/drive/u/1/folders/0B7ZiW-W5STesMG50eDgxNlJBZ1E) used in the past years.
- On the import page, you can preview the seating chart for a room by specifying a room name, Google Sheets URL, and sheet name. Create the room when you're sure it's ready.
- If you created your own room sheet because it previously did not exist, consider adding the sheet to the master sheet.

#### Google Sheets Format for Rooms

- One row of the spreadsheet corresponds to one row.
- The "Row" and "Seat" columns specify the name of a seat.
- The "X" and "Y" are the coordinates in the seating chart. If "X" is left blank, it defaults to one space stage right (house left) to the previous seat. If "Y" is left blank, it defaults to the Y coordinate of the previous seat.
- The remaining columns are arbitrary TRUE/FALSE "attributes", which can give labels to seats such as LEFTY, RIGHTY, AISLE, FRONT, or RESERVED. A blank value is interpreted as FALSE. Student preferences are given in terms of these labels, and are used to match students to seats.

#### Importing Students

- Student data can be imported from a Google Sheet. Thus, you will need login to Google to import students. You can only use Google Sheets that you have access to from your Google account.
- To import students for an exam, create a Google spreadsheet with the columns "Name", "Student ID", "Email", and "Canvas ID". The remaining columns are arbitrary attributes (ex: LEFTY, RIGHTY, BROKEN) that express student preferences - check your room sheet for the available attributes.
- For example, if a student has LEFTY=TRUE, they will be assigned a seat with the LEFTY attribute. If a student has LEFTY=FALSE, they will be assigned a seat without the LEFTY attribute. If a student's LEFTY attribute is blank, then they will could be assigned to either a LEFTY or non-LEFTY seat as if they don't care.
- Student data can also be imported from Canvas Roster. Importing students this way results in all students from the roster being added to the database without any preferences/attributes. You can then manually add preferences/attributes to students.
- Remember, data can come from different sources but must be consolidated within the app itself. Multiple imports of the same student will be merged according to their Canvas ID (other fields would be updated to the latest import, if they are different).

#### Reviewing Data, Assigning Seats

- After importing rooms and students, you might need to review data (especially student preferences) before assigning seats. If you see problems, just edit student datatable on the app. The workflow is pretty intuitive as it basically resembles a spreadsheet.
- Any change of student preference attributes will make the student unassigned. You will need to reassign seats after making changes.
- Assign students by clicking on the `assign` button. Only unassigned students will be assigned a seat.
- You can mannually unassign students from the student table too.

#### Emailing students

In the emailing page, you should specify minimally sender's address and sender's signature. The signature is appended to the end of the email body. You can also specify additional text to be appended to the end of the email body (this is a good place to tell students what to do if they have concerns about their seating assignments). The email body is generated from a template. The template is a html file that you can edit. The template is located at `server/services/email/templates/assignment_inform_email.html` and its variables are automatically filled in.

#### Get Roster Photos

(Under Construction; content might be outdated)

To allow for roster photos to appear in the app, set the `PHOTO_DIRECTORY` env
variable to a directory containing files at the path:

    {PHOTO_DIRECTORY}/{Course Offering}/{bCourses ID}.jpeg

The bCourses ID column is used to determine which photo to display for which
student.

In the past, we've used the DownThemAll Firefox extension to grab all of our
roster photos from bCourses. That extension no longer works in Firefox Quantum,
so you can either use an old version of Firefox with support for legacy add-ins,
or use the script `download_bcourses_photos.py` in this repo.

#### During the exam

(Under Construction; content might be outdated)

Staff can project the seating chart, and use the seating chart to identity
cheaters.

## For Developers

### Local Setup

1. Clone Repo

Clone the repository and change directories into the repository.

```bash
	git clone git@github.com:berkeley-eecs/seating.git
	cd seating
```

2. Setup Virtual Environment

Create and activate a virtual environment and activate it.
We are not using `virtualenv`.

```bash
	python3 -m venv venv
	source env/bin/activate
```

3. Install Dependencies

You should install from both `requirements.txt` and `requirements-dev.txt`.
Make sure you are in the virtual environment.

```
	pip install -r requirements.txt
   pip install -r requirements-dev.txt
```

4. Setup Environment Variables

Copy the `.env.example` file to `.env` and fill in the environment variables.
You will need a few API keys and secrets. See the section on environment variables for details.
Make sure you are in the virtual environment.

5. Setup Database

For development, we are using a local `sqlite3` database. Hence, no need to configure any server or connection string.
You only need to initialize the database once.

```bash
   flask resetdb
```

6. Spin up the Server

```bash
   flask run
```

Open [localhost:5000](https://localhost:5000). You should be able to see the app running locally.

7. Navigate the App

Try clicking into a course offering and create an exam.
Use this [demo Google Sheet](https://docs.google.com/spreadsheets/d/1nC2vinn0k-_TLO0aLmLZtI9juEoSOVEvA3o40HGvXAw/edit?usp=drive_web&ouid=100612133541464602205) to import rooms and students, and trying out assigning seatings.

### Environment Variables

```bash
# env flag. available values: development, production, testing
FLASK_ENV=development

# whether to mock canvas. false to use real canvas api, true to use mock canvas api
MOCK_CANVAS=false

# google oauth client id and secrets, follow the normal gcp oauth flow to get it
# remember to setup the redirect and origin urls
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

# canvas server url, client id and secret, get them from school LTI team
CANVAS_SERVER_URL=
CANVAS_CLIENT_ID=
CANVAS_CLIENT_SECRET=

# email setup, use any smtp server
EMAIL_SERVER=
EMAIL_PORT=
EMAIL_USE_TLS=
EMAIL_USERNAME=

# misc
SERVER_BASE_URL=localhost:5000
LOCAL_TIMEZONE=US/Pacific
```

### Available CLI Commands

```bash
# intialize database
flask initdb
# drop database
flask dropdb
# seed database
flask seeddb
# reset database (drop, init, seed)
flask resetdb
# run linting check
flask lint
# run unit tests
flask unit
# run e2e tests
flask e2e
# run a11y tests
flask a11y
# run all tests (unit, e2e, a11y)
flask test
# run security audit
flask audit
```

### Devops

#### Testing

This repo is equipped with some typical testing scaffoldings you might expect to find in a full-stack application:

- Test runner: `pytest`
- Coverage: `pytest-cov`, which uses `coverage.py` under the hood
- HTTP request stubbing: `responses`
- Seeding database from fixture files: `flask-fixtures`
- Webdriver for UI/e2e tests: `selenium`

There are a few other aspects worth noting:

- Canvas OAuth

We did not use `responses` library to stub out Auth API Call. Instead, when `MOCK_CANVAS` env var is set to `True`, our app would connect to a fake local OAuth2 server instead of the actual Canvas OAuth2 server. It still completes the entire OAuth2 flow but draws user information from `server/services/canvas/fake_data/fake_users.json`.

- Canvas API

We did not use `responses` library to stub out Canvas API as we are using the `canvasapi` library instead of calling HTTP endpoints directly. What we did is to use a fake `CanvasClient` when `MOCK_CANVAS` env var is set to `True`, which draws information from `server/services/canvas/fake_data`.

- Email

We provide three ways to test the email feature.

#### CI/CD

We are using

#### Deployment

(under construction)
