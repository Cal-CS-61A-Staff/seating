# Exam Seating App

[![codecov](https://codecov.io/gh/berkeley-eecs/seating/graph/badge.svg?token=0FJ178HK0N)](https://codecov.io/gh/berkeley-eecs/seating)

One stop solution to manage and access exam seating assignments of all your Berkeley courses, for course staff and students.

## Introduction

The app allows you to manage all your course exams. As a course staff, you will be able to create, edit and delete exams, room, seats and student rosters, manage seating assignment, and email students about their assignments. As a student, you will be able to see your available assignments.

The entire app is protected behind Canvas (bCourses) authentication and authorization, so only Berkeley students can access the app. Only individuals that are enrolled in a certain course can access the app for that course - the type of enrollment (student, staff, etc.) fetched from Canvas determines the level of access.

## Features and Benefits

- Supports multiple exams for the same course. Supports multiple room and multiple sessions for the same exam.
- Ensures fair seating arrangements for all students taking the exam, while taking into account student seating and room preferences (e.g. lefty chair, small room, dsp accomodation etc).
- Securely stores sensitive student and exam data, abiding by FERPA and other privacy laws, allowing only authorized staff to access the data.
- Streamlines the administrative process by automating seat assignment and room allocation, reducing the workload on staff and minimizing human errors.
- Allowing exam seating email notification and seating chart projection during the exam, smoothing the logistical processes for both students and staff.
- Allows staff to easily identify cheaters during exams by seating location, minimizing the possibility of academic misconduct or cheating during exams.

## Get Started!

- If you are an instructor or a course staff member who wants to use this app for your course, see [here](wiki/for-course-staff).
- If you are a developer or maintainer that works with this app, see [here](wiki/for-developers).
- If you are a student, see [here](wiki/for-students).
- 
