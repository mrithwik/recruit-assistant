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

from fastapi import APIRouter, Depends, HTTPException

from app.config import Settings
from app.dependencies import get_llm_client, get_settings
from app.matching.llm_client import DispatcherLLMClient, LLMClient
from app.models.schemas import MockModeOut, MockModeUpdateRequest
from app.runtime_settings import (
    get_use_mock_email,
    get_use_mock_llm,
    set_use_mock_email,
    set_use_mock_llm,
)

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


def _real_llm_available(llm: LLMClient) -> bool:
    return isinstance(llm, DispatcherLLMClient) and llm.real_client is not None


def _out(settings: Settings, llm: LLMClient) -> MockModeOut:
    return MockModeOut(
        use_mock_llm=get_use_mock_llm(),
        use_mock_email=get_use_mock_email(),
        real_llm_available=_real_llm_available(llm),
        expose_toggle=settings.expose_mock_mode_toggle,
    )


@router.get("/mock-mode", response_model=MockModeOut)
async def get_mock_mode(settings: Settings = Depends(get_settings), llm: LLMClient = Depends(get_llm_client)):
    return _out(settings, llm)


@router.patch("/mock-mode", response_model=MockModeOut)
async def update_mock_mode(
    payload: MockModeUpdateRequest,
    settings: Settings = Depends(get_settings),
    llm: LLMClient = Depends(get_llm_client),
):
    if payload.use_mock_llm is False and not _real_llm_available(llm):
        raise HTTPException(
            400,
            "Can't switch LLM processing to real mode — no OPENROUTER_API_KEY or OPENAI_API_KEY was "
            "configured when the backend started. Add one to .env and restart the backend first.",
        )

    if payload.use_mock_llm is not None:
        set_use_mock_llm(payload.use_mock_llm)
    if payload.use_mock_email is not None:
        set_use_mock_email(payload.use_mock_email)

    return _out(settings, llm)
