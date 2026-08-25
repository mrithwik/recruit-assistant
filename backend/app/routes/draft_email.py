"""Draft Email panel (2.6)."""

from fastapi import APIRouter, Depends, HTTPException

from app.config import Settings
from app.dependencies import get_llm_client, get_settings, get_storage
from app.email_draft.generator import generate_draft
from app.matching.llm_client import LLMClient
from app.models.db import Candidate, Job, Match
from app.models.schemas import DraftEmailOut, DraftEmailRequest
from app.storage.base import BaseStorageBackend

router = APIRouter(prefix="/api/v1/draft-email", tags=["draft-email"])


@router.post("", response_model=DraftEmailOut)
async def draft_email(
    payload: DraftEmailRequest,
    storage: BaseStorageBackend = Depends(get_storage),
    llm: LLMClient = Depends(get_llm_client),
    settings: Settings = Depends(get_settings),
):
    with storage.session() as session:
        match = session.get(Match, payload.match_id)
        if not match:
            raise HTTPException(404, "Match not found")
        job = session.get(Job, match.job_id)
        candidate = session.get(Candidate, match.candidate_id)
        result = await generate_draft(llm, settings.llm_scoring_model, job, candidate, match)
        return DraftEmailOut(**result)
