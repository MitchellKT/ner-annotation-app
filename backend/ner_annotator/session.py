"""Lightweight named sessions backed by a signed, HttpOnly cookie.

This is *identification*, not authentication: an annotator types their name and
we hand back a signed cookie carrying the derived user *slug*. Anyone can pick
any name (that is the product requirement); signing only stops casual cookie
tampering and lets us trust the slug server-side without keeping a session
table — so sessions survive pod restarts.

The signing key comes from ``SESSION_SECRET``. A random key is generated when it
is unset (fine for dev / single-replica), which invalidates existing cookies on
restart; set a stable secret (a k8s Secret) in production.
"""

from __future__ import annotations

import os
import re
import secrets
import unicodedata
from typing import Optional

from fastapi import Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

COOKIE_NAME = "ner_session"
# 30 days; the cookie is refreshed on every whoami so active users don't expire.
MAX_AGE_SECONDS = 30 * 24 * 3600
_SALT = "ner-annotator.session.v1"

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    """Derive a filesystem-safe, stable user id from a display name.

    Unicode is transliterated to ASCII where possible, lowercased, and reduced
    to ``[a-z0-9-]``. Two annotators typing the same name share a workspace by
    design (the name *is* the identity); genuinely distinct names slug apart.
    """
    normalized = unicodedata.normalize("NFKD", name)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    slug = _SLUG_RE.sub("-", ascii_only.lower()).strip("-")
    return slug


def _serializer() -> URLSafeTimedSerializer:
    secret = os.environ.get("SESSION_SECRET")
    if not secret:
        # No stable secret: mint an ephemeral one. Cookies won't survive a
        # restart, but the app still works for a single dev/session.
        secret = _ephemeral_secret()
    return URLSafeTimedSerializer(secret, salt=_SALT)


_EPHEMERAL: Optional[str] = None


def _ephemeral_secret() -> str:
    global _EPHEMERAL
    if _EPHEMERAL is None:
        _EPHEMERAL = secrets.token_urlsafe(32)
    return _EPHEMERAL


def issue(response: Response, *, slug: str, name: str) -> None:
    """Attach a fresh signed session cookie for ``slug`` to the response."""
    token = _serializer().dumps({"slug": slug, "name": name})
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        # Secure is driven by env so local http dev still works; set
        # SESSION_COOKIE_SECURE=1 behind TLS in production.
        secure=os.environ.get("SESSION_COOKIE_SECURE") == "1",
        path="/",
    )


def clear(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


def read(request: Request) -> Optional[dict]:
    """Return ``{"slug", "name"}`` for a valid cookie, else ``None``."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        data = _serializer().loads(token, max_age=MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(data, dict) or "slug" not in data:
        return None
    return data
