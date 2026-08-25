"""
Auth — a single local recruiter account (first-run setup), guarding the rest
of the API. Kept intentionally simple for a local app:

- /auth/status tells the frontend whether to show "create your account" or
  "sign in" on the login page.
- /auth/register only succeeds once — after the first account exists, it's
  locked (403) rather than left open, so if this app is ever exposed beyond
  localhost it doesn't silently accept new accounts from anyone who finds it.
- Sessions are signed, expiring bearer tokens (app/auth/security.py) — no
  server-side session store to manage for a single-process local app.
"""

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import require_auth
from app.auth.security import create_session_token, hash_password, verify_password
from app.config import Settings
from app.dependencies import get_settings, get_storage
from app.models.db import User
from app.models.schemas import AuthStatusOut, LoginRequest, RegisterRequest, SessionOut, UserOut
from app.storage.base import BaseStorageBackend

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LENGTH = 8


def _to_user_out(user: User) -> UserOut:
    return UserOut(id=user.id, email=user.email, name=user.name)


def _issue_session(user: User, settings: Settings, remember: bool) -> SessionOut:
    ttl = settings.session_ttl_hours_remembered if remember else settings.session_ttl_hours_short
    token = create_session_token(user.id, settings.resolved_secret_key, ttl)
    return SessionOut(token=token, user=_to_user_out(user))


@router.get("/status", response_model=AuthStatusOut)
def auth_status(storage: BaseStorageBackend = Depends(get_storage)):
    with storage.session() as session:
        return AuthStatusOut(setup_complete=storage.any_user_exists(session))


@router.post("/register", response_model=SessionOut)
def register(
    payload: RegisterRequest,
    storage: BaseStorageBackend = Depends(get_storage),
    settings: Settings = Depends(get_settings),
):
    if not EMAIL_RE.match(payload.email):
        raise HTTPException(400, "Enter a valid email address")
    if len(payload.password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(400, f"Password must be at least {MIN_PASSWORD_LENGTH} characters")

    with storage.session() as session:
        if storage.any_user_exists(session):
            raise HTTPException(403, "An account already exists — sign in instead")

        user = User(
            id=str(uuid.uuid4()),
            email=payload.email.lower(),
            name=payload.name,
            password_hash=hash_password(payload.password),
        )
        storage.create_user(session, user)
        session.commit()
        return _issue_session(user, settings, payload.remember)


@router.post("/login", response_model=SessionOut)
def login(
    payload: LoginRequest,
    storage: BaseStorageBackend = Depends(get_storage),
    settings: Settings = Depends(get_settings),
):
    with storage.session() as session:
        user = storage.find_user_by_email(session, payload.email)
        if user is None or not verify_password(payload.password, user.password_hash):
            raise HTTPException(401, "Incorrect email or password")
        return _issue_session(user, settings, payload.remember)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(require_auth)):
    return _to_user_out(user)
