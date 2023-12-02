from datetime import datetime


def parse_ISO8601(s: str) -> datetime:
    """
    Parse an ISO8601 date string and return a datetime.datetime object.

    datetime.fromisoformat cannot properly parse ISO 8601 format until 3.11
    so we use datetime.strptime instead
    in 3.11 you can do: datetime.fromisoformat(s)
    """
    # remove trailing ! if present
    # this should only come from seeding data fixtures
    # flask-fixture will parse out date string if there is no trailing !
    # but we never really want to store datetime object to db; we only store str
    # so, we force the trailing ! to be there to avoid parsing by flask-fixture
    if s.endswith('!'):
        s = s[:-1]
    return datetime.strptime(s, '%Y-%m-%dT%H:%M:%SZ')


def to_ISO8601(d: datetime) -> str:
    """
    Convert a datetime.datetime object to an ISO8601 date string.

    datetime.isoformat cannot properly format ISO 8601 format until 3.11
    so we use datetime.strftime instead
    in 3.11 you can do: d.isoformat()
    """
    return d.strftime('%Y-%m-%dT%H:%M:%SZ')
