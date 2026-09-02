"""Confirms run_scan's per-resume processing actually runs concurrently
within a batch (parse + summarize, both routed through the LLM client) —
not the old one-at-a-time sequential loop. See the speed-plan report's
lever #1 and app/scanning/ingest_service.py's docstring for the two-phase
(concurrent parse+summarize, then sequential identity-resolution/mirror-
write) design this proves."""

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import datetime

import pytest

from app.matching.llm_client import LLMClient
from app.models.enums import ResumeOrigin
from app.models.schemas import IngestedResume
from app.scanning.ingest_service import run_scan
from app.scanning.ingestor_base import ResumeIngestor

# Long enough (200+ chars) to take parse_resume's real LLM-extraction path
# rather than the thin/garbled regex-only fallback — otherwise `complete()`
# is never called and this test would prove nothing.
LONG_RESUME_TEMPLATE = (
    "Candidate Number {i}\ncandidate{i}@example.com\n"
    "{years} years of backend engineering experience with Python, FastAPI, "
    "PostgreSQL, and Kubernetes. Led cross-functional teams through several "
    "major platform migrations, owned schema design end to end, and mentored "
    "junior engineers on system design fundamentals and code review practice."
)


def _distinct_long_resume(i: int) -> bytes:
    text = LONG_RESUME_TEMPLATE.format(i=i, years=i + 1)
    assert len(text) >= 200
    return text.encode()


class _MultiDistinctIngestor(ResumeIngestor):
    def __init__(self, count: int):
        self.count = count

    async def scan(self, date_start=None, date_end=None) -> AsyncIterator[IngestedResume]:
        for i in range(self.count):
            yield IngestedResume(
                origin=ResumeOrigin.FOLDER,
                source_ref="/tmp/resumes",
                file_bytes=_distinct_long_resume(i),
                filename=f"candidate{i}.txt",
                date_submitted=datetime(2026, 1, 1),
            )


class ConcurrencyTrackingLLMClient(LLMClient):
    """Every complete() call sleeps briefly and records how many calls were
    in flight at once — same pattern as test_matcher_concurrency.py's
    tracker, applied to the ingest pipeline instead of the matcher."""

    def __init__(self):
        self.in_flight = 0
        self.max_in_flight = 0
        self.lock = asyncio.Lock()

    async def complete(self, model: str, prompt: str, system: str = "") -> str:
        async with self.lock:
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
        await asyncio.sleep(0.05)
        async with self.lock:
            self.in_flight -= 1
        if "JSON" in system:
            return json.dumps(
                {
                    "legal_first_name": "Candidate",
                    "legal_middle_name": "",
                    "legal_last_name": "Number",
                    "email": "",
                    "phone": "",
                    "employment_status": "employed",
                    "work_visa_status": "us_citizen",
                    "skills": ["Python"],
                    "experience_years": 3,
                    "education": [],
                }
            )
        return "Summary of a backend engineer."

    async def embed(self, model: str, text: str) -> list[float]:
        return [0.0, 1.0]


@pytest.mark.asyncio
async def test_parse_and_summarize_run_concurrently_within_a_batch(storage, tmp_path):
    llm = ConcurrencyTrackingLLMClient()
    max_concurrent = 5

    with storage.session() as session:
        result = await run_scan(
            ingestor=_MultiDistinctIngestor(count=20),
            storage=storage,
            session=session,
            candidates_dir=tmp_path,
            llm=llm,
            summary_model="",
            max_concurrent_processing=max_concurrent,
        )

    assert result.candidates_created == 20
    assert result.errors == []
    assert llm.max_in_flight > 1, "expected parse/summarize calls to overlap, not run one at a time"
    assert llm.max_in_flight <= max_concurrent
