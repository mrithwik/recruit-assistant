"""
Password hashing (PBKDF2-SHA256, stdlib `hashlib` — no bcrypt/argon2 dependency
to install) and signed, expiring session tokens (HMAC-SHA256, stdlib `hmac` —
no PyJWT dependency). Deliberately dependency-free: this is a local desktop
app, and every extra native/compiled dependency is friction for a recruiter
running `make setup` on their own machine.

Token shape mirrors JWT's spirit without the library: base64url(payload) +
"." + hex HMAC signature. `create_session_token` / `verify_session_token` are
the only functions callers need.
"""

import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone

PBKDF2_ITERATIONS = 210_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt_hex, digest_hex = stored_hash.split("$", 1)
    except ValueError:
        return False
    salt = bytes.fromhex(salt_hex)
    expected = bytes.fromhex(digest_hex)
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return hmac.compare_digest(expected, actual)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_session_token(user_id: str, secret_key: str, ttl_hours: int) -> str:
    payload = {
        "sub": user_id,
        "exp": (datetime.now(timezone.utc) + timedelta(hours=ttl_hours)).timestamp(),
    }
    payload_b64 = _b64url_encode(json.dumps(payload).encode())
    signature = hmac.new(secret_key.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{signature}"


def verify_session_token(token: str, secret_key: str) -> str | None:
    """Returns the user_id if the token is valid and unexpired, else None."""
    try:
        payload_b64, signature = token.split(".", 1)
    except ValueError:
        return None

    expected_signature = hmac.new(secret_key.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_signature, signature):
        return None

    try:
        payload = json.loads(_b64url_decode(payload_b64))
        if datetime.now(timezone.utc).timestamp() > payload["exp"]:
            return None
        return payload["sub"]
    except (ValueError, KeyError, json.JSONDecodeError):
        return None
