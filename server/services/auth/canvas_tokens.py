"""
Canvas access tokens, kept on the server rather than in the session cookie.

Flask's session cookie is signed but not encrypted, so a token kept there could be read by anyone
holding a copy of the cookie, and that copy would keep working after logout until the token expired.
Instead the cookie holds a random handle for a CanvasToken row. Signing out, or in again, deletes the
row and revokes the token with Canvas, so no copy of the cookie can use it.
"""
import hashlib
import secrets
import time

from flask import session
from flask_login import current_user

import server.services.canvas as canvas_client
from server.models import CanvasToken, User, db

SESSION_KEY = 'canvas_token_id'
# Where the token was kept in the cookie before this; dropped wherever it's found.
LEGACY_SESSION_KEY = 'access_token'
# Canvas tokens last an hour; used when the token response doesn't say.
DEFAULT_EXPIRES_IN = 60 * 60
# Treat a token this close to expiring as expired, so a page doesn't fail halfway through its Canvas calls.
EXPIRY_MARGIN = 60


def _hash(handle: str) -> str:
    return hashlib.sha256(handle.encode()).hexdigest()


def _this_browsers_row() -> CanvasToken | None:
    handle = session.get(SESSION_KEY)
    if not isinstance(handle, str):
        return None
    return CanvasToken.query.filter_by(handle_hash=_hash(handle)).one_or_none()


def store_token(user: User, access_token: str, expires_in: float | None):
    """Keeps `access_token` for this browser's sign-in as `user`."""
    now = time.time()
    handle = secrets.token_urlsafe(32)
    db.session.add(CanvasToken(user_id=user.id, handle_hash=_hash(handle), access_token=access_token,
                               expires_at=int(now + (expires_in or DEFAULT_EXPIRES_IN))))
    # tokens from sign-ins that never signed out; Canvas no longer accepts them
    CanvasToken.query.filter(CanvasToken.expires_at < now).delete()
    db.session.commit()
    session[SESSION_KEY] = handle


def current_token() -> str | None:
    """
    This browser's Canvas token for the signed-in user, or None if there's none or it has (nearly)
    expired, in which case they need to sign in again.
    """
    if not current_user.is_authenticated:
        return None
    row = _this_browsers_row()
    if row is None or row.user_id != current_user.id or time.time() + EXPIRY_MARGIN >= row.expires_at:
        return None
    return row.access_token


def discard_token():
    """Forgets this browser's token, and revokes it with Canvas."""
    row = _this_browsers_row()
    session.pop(SESSION_KEY, None)
    session.pop(LEGACY_SESSION_KEY, None)
    if row is None:
        return
    access_token, expired = row.access_token, row.expires_at <= time.time()
    db.session.delete(row)
    db.session.commit()
    if not expired:
        canvas_client.revoke_token(access_token)
