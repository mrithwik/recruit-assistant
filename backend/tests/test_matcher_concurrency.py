"""Confirms match_job_against_pool's deep-scoring pass actually runs
concurrently (not the old one-at-a-time sequential loop) while still
respecting the max_concurrent cap — see project-log."""

import asyncio
import json

import pytest

from app.matching.llm_client import LLMClient
from app.matching.matcher import match_job_against_pool


class ConcurrencyTrackingLLMClient(LLMClient):
    """Every complete() call sleeps briefly and records how many calls were
    in flight at once, so the test can assert both "ran concurrently" (max
    seen > 1) and "respected the cap" (max seen <= max_concurrent)."""

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
        # Score outside the judge-review band so judge_score never fires —
        # isolates this test to the deep-scoring concurrency pass.
        return json.dumps({"score": 90, "matched": [], "gaps": [], "missing_info": []})

    async def embed(self, model: str, text: str) -> list[float]:
        return [0.0]


@pytest.mark.asyncio
async def test_deep_scoring_runs_concurrently_within_cap():
    llm = ConcurrencyTrackingLLMClient()
    pool = [
        {
            "id": f"c{i}",
            "embedding": [1.0, 0.0],
            "resume_text": "some resume text",
            "profile": _FakeProfile(),
            "summary": "summary",
        }
        for i in range(20)
    ]
    max_concurrent = 5

    await match_job_against_pool(
        llm=llm,
        triage_model="triage",
        scoring_model="scoring",
        judge_model="judge",
        job_text="job description text",
        job_embedding=[1.0, 0.0],
        candidate_pool=pool,
        top_n=20,
        max_concurrent=max_concurrent,
    )

    assert llm.max_in_flight > 1, "expected calls to overlap, not run one at a time"
    assert llm.max_in_flight <= max_concurrent


class _FakeProfile:
    skills = ["python"]
    experience_years = 5.0
    education = ["BS"]

    class employment_status:
        value = "employed"

    class work_visa_status:
        value = "us_citizen"
