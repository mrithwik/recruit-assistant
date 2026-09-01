"""Runtime mock/real toggles — see app/runtime_settings.py for why these
are separate from the rest of Settings (need to flip live, no restart).
GET reports current state (plus whether a real LLM client is actually
available, and whether Settings.expose_mock_mode_toggle says the UI should
show this control at all); PATCH updates one or both, refusing to enable
real LLM mode with no provider available rather than letting it fail
confusingly partway through a scan.

Real-availability is checked against the DispatcherLLMClient actually built
at startup (its .real_client), not by re-reading .env — a key added to
.env after the backend started wouldn't retroactively give the already-
built dispatcher a real client, so trusting a fresh Settings() read here
would let the guardrail pass while real mode still silently falls back to
mock (see DispatcherLLMClient._active)."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.config import Settings
from app.dependencies import get_llm_client, get_settings, get_storage
from app.matching.llm_client import DispatcherLLMClient, LLMClient
from app.models.db import User
from app.models.schemas import MockModeOut, MockModeUpdateRequest
from app.runtime_settings import (
    get_use_mock_email,
    get_use_mock_llm,
    set_use_mock_email,
    set_use_mock_llm,
)
from app.storage.base import BaseStorageBackend

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


def _real_llm_available(llm: LLMClient) -> bool:
    return isinstance(llm, DispatcherLLMClient) and llm.real_client is not None


def _consent_given(storage: BaseStorageBackend) -> bool:
    with storage.session() as session:
        user = session.execute(select(User).limit(1)).scalar_one_or_none()
        return user is not None and user.real_llm_consent_given_at is not None


def _out(settings: Settings, llm: LLMClient, storage: BaseStorageBackend) -> MockModeOut:
    return MockModeOut(
        use_mock_llm=get_use_mock_llm(),
        use_mock_email=get_use_mock_email(),
        real_llm_available=_real_llm_available(llm),
        expose_toggle=settings.expose_mock_mode_toggle,
        real_llm_consent_given=_consent_given(storage),
    )


@router.get("/mock-mode", response_model=MockModeOut)
async def get_mock_mode(
    settings: Settings = Depends(get_settings),
    llm: LLMClient = Depends(get_llm_client),
    storage: BaseStorageBackend = Depends(get_storage),
):
    return _out(settings, llm, storage)


@router.patch("/mock-mode", response_model=MockModeOut)
async def update_mock_mode(
    payload: MockModeUpdateRequest,
    settings: Settings = Depends(get_settings),
    llm: LLMClient = Depends(get_llm_client),
    storage: BaseStorageBackend = Depends(get_storage),
):
    if payload.use_mock_llm is False and not _real_llm_available(llm):
        raise HTTPException(
            400,
            "Can't switch LLM processing to real mode — no OPENROUTER_API_KEY or OPENAI_API_KEY was "
            "configured when the backend started. Add one to .env and restart the backend first.",
        )

    if payload.use_mock_llm is False and not _consent_given(storage):
        if not payload.consent_ack:
            raise HTTPException(
                428,
                "Real LLM mode requires one-time consent before it can be enabled — resend with consent_ack: true "
                "after showing the user what data leaves the machine.",
            )
        with storage.session() as session:
            user = session.execute(select(User).limit(1)).scalar_one_or_none()
            if user is not None:
                user.real_llm_consent_given_at = datetime.utcnow()
                session.commit()

    if payload.use_mock_llm is not None:
        set_use_mock_llm(payload.use_mock_llm)
    if payload.use_mock_email is not None:
        set_use_mock_email(payload.use_mock_email)

    return _out(settings, llm, storage)
