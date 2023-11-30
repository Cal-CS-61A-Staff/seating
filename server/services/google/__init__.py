import re
import itertools
import json
import base64

from apiclient import errors
from server import app
from server.typings.enum import GcpSaCredType
from server.typings.exception import GcpError

from google.oauth2 import service_account
from googleapiclient.discovery import build


def _get_spreadsheet_service():
    """
    Returns an authorized API client service for Google Sheets API.
    """
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
    cred_type = app.config.get('GCP_SA_CRED_TYPE')
    credentials = None
    if cred_type == GcpSaCredType.FILE.value:
        credentials = service_account.Credentials.from_service_account_file(
            app.config.get('GCP_SA_CRED_FILE'), scopes=SCOPES)
    elif cred_type == GcpSaCredType.ENV.value:
        decoded_credentials = base64.b64decode(app.config.get('GCP_SA_CRED_VALUE'))
        service_account_info = json.loads(decoded_credentials)
        credentials = service_account.Credentials.from_service_account_info(
            service_account_info, scopes=SCOPES)
    else:
        raise GcpError('Invalid GCP_SA_CRED_TYPE')
    if not credentials:
        raise GcpError('Invalid GCP credentials')
    return build('sheets', 'v4', credentials=credentials)


service = _get_spreadsheet_service()


def _get_spreadsheet_id(sheet_url):
    m = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', sheet_url)
    if not m or not m.group(1):
        raise GcpError('Enter a Google Sheets URL')
    return m.group(1)


def get_spreadsheet_tabs(sheet_url):
    spreadsheet_id = _get_spreadsheet_id(sheet_url)
    try:
        sheet_metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheets = sheet_metadata.get('sheets', '')
        return [sheet['properties']['title'] for sheet in sheets]
    except errors.HttpError as e:
        raise GcpError(e._get_reason())


def get_spreadsheet_tab_content(sheet_url, tab_name):
    spreadsheet_id = _get_spreadsheet_id(sheet_url)
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, range=tab_name).execute()
    except errors.HttpError as e:
        raise GcpError(e._get_reason())
    values = result.get('values', [])

    if not values:
        raise GcpError('Sheet is empty')
    headers = [h.lower() for h in values[0]]
    rows = [
        {k: v for k, v in itertools.zip_longest(headers, row, fillvalue='')}
        for row in values[1:]
    ]
    if len(set(headers)) != len(headers):
        raise GcpError('Headers must be unique')
    elif not all(re.match(r'[a-z0-9]+', h) for h in headers):
        raise GcpError('Headers must consist of digits and numbers')
    return headers, rows
