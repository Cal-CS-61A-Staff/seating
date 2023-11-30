from datetime import datetime


def parse_ISO8601(s: str) -> datetime:
    """
    Parse an ISO8601 date string and return a datetime.datetime object.

    datetime.fromisoformat cannot properly parse ISO 8601 format until 3.11
    so we use datetime.strptime instead
    in 3.11 you can do: datetime.fromisoformat(s)
    """
    return datetime.strptime(s, '%Y-%m-%dT%H:%M:%SZ')
