"""FastAPI dependency that guards every non-public route. Applied at router
inclusion time in main.py rather than per-route, so a new route is protected
by default and has to opt out, not the other way around."""

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.security import verify_session_token
from app.config import Settings
from app.dependencies import get_settings, get_storage
from app.models.db import User
from app.storage.base import BaseStorageBackend

_bearer = HTTPBearer(auto_error=False)


def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
    storage: BaseStorageBackend = Depends(get_storage),
) -> User:
    if credentials is None:
        raise HTTPException(401, "Not authenticated")

    user_id = verify_session_token(credentials.credentials, settings.resolved_secret_key)
    if user_id is None:
        raise HTTPException(401, "Invalid or expired session")

    with storage.session() as session:
        user = session.get(User, user_id)
        if user is None:
            raise HTTPException(401, "Account no longer exists")
        session.expunge(user)
        return user
