import re

from flask import current_app

from server.services.c1c import fake_data

# seconds to wait for C1C, so a slow response can't hold a request thread until gunicorn gives
# up on it; the student's photo shows the placeholder instead
TIMEOUT = 10


def is_mock_c1c() -> bool:
    return current_app.config['MOCK_C1C'] and \
        current_app.config['FLASK_ENV'].lower() != 'production'


class C1C:
    def __init__(self, proxy_url, api_domain, username, password):
        self.proxy_dict = {
            'http': proxy_url,
            'https': proxy_url
        } if proxy_url else None
        self.api_domain = api_domain
        self.username = username
        self.password = password

    def _make_request(self, path, method='GET'):
        import requests
        url = f'{self.api_domain}{path}'
        return requests.request(method, url, proxies=self.proxy_dict,
                                auth=(self.username, self.password), timeout=TIMEOUT)

    def get_student_photo(self, sid):
        # it goes into the url path: anything but digits could point the request elsewhere
        if not re.fullmatch(r'[0-9]+', sid or ''):
            return None
        if is_mock_c1c():
            return fake_data.get_fake_photo(sid)
        try:
            r = self._make_request(f'/c1c-api/v1/photo/{sid}')
            if r.status_code == 200:
                return r.content
            else:
                return None
        except:
            return None


def get_c1c_client():
    """A C1C client for the current app's config."""
    config = current_app.config
    return C1C(config['C1C_PROXY_URL'], config['C1C_API_DOMAIN'],
               config['C1C_API_USERNAME'], config['C1C_API_PASSWORD'])
