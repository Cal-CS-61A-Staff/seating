# Define the application directory and environment
import os
BASE_DIR = os.path.abspath(os.path.dirname(__file__)) 
ENV = os.getenv('FLASK_ENV')

# Define the database - we are working with
# SQLite for development, mysql for production [development should be changed to mysql in the future]
if ENV == 'development':
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(BASE_DIR, 'app.db')
else:
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL').replace('mysql://', 'mysql+pymysql://')
SQLALCHEMY_TRACK_MODIFICATIONS = False

# Configure timezone
LOCAL_TIMEZONE = os.getenv('TIMEZONE', 'US/Pacific')

# Configure other environment variables

OK_CLIENT_ID = os.getenv('OK_CLIENT_ID')
OK_CLIENT_SECRET = os.getenv('OK_CLIENT_SECRET')

GOOGLE_OAUTH2_CLIENT_ID=os.getenv('GOOGLE_CLIENT_ID')
GOOGLE_OAUTH2_CLIENT_SECRET=os.getenv('GOOGLE_CLIENT_SECRET')

# Email setup. Domain environment is for link in email.
SENDGRID_API_KEY=os.getenv('SENDGRID_API_KEY')
DOMAIN = os.getenv('DOMAIN', 'https://seating.test.org')

PHOTO_DIRECTORY=os.getenv('PHOTO_DIRECTORY')

# Used for redirects and auth: <domain>/COURSE/EXAM
COURSE = os.getenv('COURSE', 'cal/test/fa18')
EXAM = os.getenv('EXAM', 'midterm1')

TEST_LOGIN=os.getenv('TEST_LOGIN')

# Secret key for signing cookies
if ENV == 'development':
    SECRET_KEY = 'development'
else:
    SECRET_KEY = os.getenv('SECRET_KEY')
