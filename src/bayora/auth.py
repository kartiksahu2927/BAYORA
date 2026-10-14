"""Password hashing and opaque session primitives for Bayora authentication."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass, field

from .models import Actor


_ALGORITHM = "pbkdf2_sha256"
_ITERATIONS = 600_000
_SALT_BYTES = 16
_DIGEST_BYTES = 32
_DUMMY_SALT = b"bayora-password-check"
_DUMMY_DIGEST = hashlib.pbkdf2_hmac("sha256", b"bayora-dummy-password", _DUMMY_SALT, _ITERATIONS, _DIGEST_BYTES)
_DUMMY_HASH = "$".join(
    (
        _ALGORITHM,
        str(_ITERATIONS),
        base64.urlsafe_b64encode(_DUMMY_SALT).decode("ascii"),
        base64.urlsafe_b64encode(_DUMMY_DIGEST).decode("ascii"),
    )
)


def hash_password(password: str) -> str:
    """Return a versioned, salted password hash using only the stdlib."""
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS, _DIGEST_BYTES)
    return "$".join(
        (
            _ALGORITHM,
            str(_ITERATIONS),
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        )
    )


def _decoded_hash(encoded: str | None) -> tuple[int, bytes, bytes] | None:
    if not encoded:
        return None
    try:
        algorithm, iterations_text, salt_text, digest_text = encoded.split("$", 3)
        iterations = int(iterations_text)
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
    except (TypeError, ValueError, UnicodeError):
        return None
    if algorithm != _ALGORITHM or iterations < 1 or not salt or not expected:
        return None
    return iterations, salt, expected


def verify_password(password: str, encoded: str | None) -> bool:
    """Verify a password with a constant-time digest comparison.

    Missing or malformed hashes still perform a full dummy derivation so an
    unknown user does not take a substantially different password-check path.
    """
    parsed = _decoded_hash(encoded)
    if parsed is None:
        iterations, salt, expected = _decoded_hash(_DUMMY_HASH)  # type: ignore[misc]
        valid_hash = False
    else:
        iterations, salt, expected = parsed
        valid_hash = True
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, len(expected))
    matches = hmac.compare_digest(candidate, expected)
    return valid_hash and matches


@dataclass(frozen=True)
class AuthSession:
    """The one-time raw token and actor returned to the HTTP adapter."""

    token: str = field(repr=False)
    actor: Actor
    expires_at: float
