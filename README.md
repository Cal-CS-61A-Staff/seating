## Exam Seating App

[![codecov](https://codecov.io/gh/berkeley-cdss/seating/graph/badge.svg?token=0FJ178HK0N)](https://codecov.io/gh/berkeley-cdss/seating)
![CodeQL](https://github.com/berkeley-cdss/seating/actions/workflows/codeql.yml/badge.svg)
![Tests](https://github.com/berkeley-cdss/seating/actions/workflows/test.yml/badge.svg)
[![A11y](https://github.com/berkeley-cdss/seating/actions/workflows/a11y.yml/badge.svg)](docs/a11y.md)

One stop solution to manage and access exam seating assignments of all your Berkeley courses, for course staff and students.

Check out our [presentation slidedeck](https://docs.google.com/presentation/d/1UHyHwxE06L7hX2fEE3_JUhLN5CMolUJt7WaZstIjMXA/edit?usp=sharing) for Berkeley Teaching & Learning Conference 2024.

## Introduction

The app allows you to manage all your course exams. As course staff, you will be able to create, edit and delete exams, rooms/seats and student rosters, manage seating assignment, and email students about their assignments. As a student, you will be able to see your seating assignments.

The app is behind Canvas (bCourses) authentication, so only Berkeley affiliates can access the app. Only individuals that are enrolled in a certain course can access the app for that course - the type of enrollment (student, staff, etc.) fetched from Canvas determines the level of access.

## Features and Benefits

- Supports multiple exams for the same course. 
- Supports multiple room and multiple sessions for the same exam.
- Automates seat assignment and room allocation, reducing the workload on staff and minimizing human errors.
- Ensures fair seating arrangements for all students taking the exam, while taking into account student seating and room preferences (e.g. lefty chair, small room, DSP accommodation etc).
- Securely stores sensitive student and exam data, abiding by FERPA and other privacy laws, allowing only authorized staff to access the data.
- Allows exam seating email notification and seating chart projection during the exam.
- Allows staff to easily identify cheaters during exams by seating location.

## Get Started!

- If you are an instructor or a course staff member who wants to use this app for your course, see [here](wiki/for-course-staff).
- If you are a developer or maintainer that works with this app, see [here](wiki/for-developers).
- To change the database schema, see [Database Migrations](docs/migrations.md).
- If you are a student, see [here](wiki/for-students).
- To preview a room spreadsheet or build a new seating layout, see [Seating Layout Preview](Seating-Layout-Preview).
- For an audit of the Wheeler 150 room tabs against the official floor plan, see [Wheeler 150 Room Layouts](Wheeler-150-Room-Layouts).