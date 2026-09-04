"""Speed-plan lever — dual-mode triage (embedding-only default, optional
cheap-LLM re-rank): wires the previously-dead llm_triage_model config into
an actual triage_mode="llm" path, while triage_mode="embedding" (the
default) must behave exactly as before — see project-log."""

import json

import pytest

from app.matching.llm_client import LLMClient, MockLLMClient
from app.matching.matcher import SHORTLIST_MULTIPLIER, TRIAGE_WIDENING_MULTIPLIER, match_job_against_pool


class _FakeProfile:
    skills = ["python"]
    experience_years = 5.0
    education = ["BS"]

    class employment_status:
        value = "employed"

    class work_visa_status:
        value = "us_citizen"


def _pool(n: int, embeddings: dict[str, list[float]] | None = None) -> list[dict]:
    return [
        {
            "id": f"c{i}",
            "embedding": (embeddings or {}).get(f"c{i}", [1.0, 0.0]),
            "resume_text": f"resume text for candidate {i}",
            "profile": _FakeProfile(),
            "summary": f"summary for candidate {i}",
        }
        for i in range(n)
    ]


class _RecordingLLMClient(LLMClient):
    """Scores everything outside the judge-review band and outside triage
    concern (mock relevance always high) — isolates each test to what it's
    actually checking (call counts / which candidates reach deep_score)."""

    def __init__(self):
        self.deep_score_calls = 0
        self.triage_calls = 0

    async def complete(self, model: str, prompt: str, system: str = "") -> str:
        if "triaging a candidate" in prompt:
            self.triage_calls += 1
            return json.dumps({"relevance": 90})
        self.deep_score_calls += 1
        return json.dumps({"score": 90, "matched": [], "gaps": [], "missing_info": []})

    async def embed(self, model: str, text: str) -> list[float]:
        return [0.0]


@pytest.mark.asyncio
async def test_embedding_mode_never_calls_the_llm_for_triage():
    llm = _RecordingLLMClient()
    pool = _pool(10)

    results, stage_timings = await match_job_against_pool(
        llm=llm,
        triage_model="triage-model",
        scoring_model="scoring",
        judge_model="judge",
        job_text="job description text",
        job_embedding=[1.0, 0.0],
        candidate_pool=pool,
        top_n=2,
        triage_mode="embedding",
    )

    assert llm.triage_calls == 0
    assert stage_timings["triage"] == 0.0
    assert llm.deep_score_calls == 2 * SHORTLIST_MULTIPLIER


@pytest.mark.asyncio
async def test_llm_mode_triages_a_wider_net_down_to_the_same_deep_score_size():
    llm = _RecordingLLMClient()
    pool = _pool(20)
    keep_n = 2 * SHORTLIST_MULTIPLIER

    results, stage_timings = await match_job_against_pool(
        llm=llm,
        triage_model="triage-model",
        scoring_model="scoring",
        judge_model="judge",
        job_text="job description text",
        job_embedding=[1.0, 0.0],
        candidate_pool=pool,
        top_n=2,
        triage_mode="llm",
    )

    assert llm.triage_calls == min(len(pool), keep_n * TRIAGE_WIDENING_MULTIPLIER)
    assert stage_timings["triage"] > 0.0
    # deep_score's own cost is unaffected by which triage mode narrowed the
    # field down to it — same final shortlist size either way.
    assert llm.deep_score_calls == keep_n


@pytest.mark.asyncio
async def test_llm_triage_can_rescue_a_candidate_the_embedding_prefilter_would_have_dropped():
    """The actual point of this lever: a candidate embedding-similarity
    ranks outside the narrow embedding-only shortlist can still reach
    deep_score under triage_mode="llm", because the wider net + LLM re-rank
    gives it a second chance the embedding-only path never would."""

    # Strictly decreasing similarity by index (no ties, so ranking is
    # deterministic): c0 ranks 1st, c5 ranks 6th, ..., c19 ranks 20th. With
    # top_n=1 (SHORTLIST_MULTIPLIER=3, TRIAGE_WIDENING_MULTIPLIER=3), the
    # narrow embedding-only shortlist is the top 3 (c0-c2); the widened net
    # llm mode actually triages is the top 9 (c0-c8) — c5 sits inside the
    # widened net but outside the narrow one, so it's rescuable only if the
    # LLM triage pass, not embedding similarity alone, is what promotes it.
    embeddings = {f"c{i}": [1.0 - i * 0.001, i * 0.001] for i in range(20)}
    pool = _pool(20, embeddings)

    class _FavorsC5LLMClient(_RecordingLLMClient):
        async def complete(self, model: str, prompt: str, system: str = "") -> str:
            if "triaging a candidate" in prompt:
                self.triage_calls += 1
                relevance = 99 if "candidate 5" in prompt else 10
                return json.dumps({"relevance": relevance})
            self.deep_score_calls += 1
            return json.dumps({"score": 90, "matched": [], "gaps": [], "missing_info": []})

    llm = _FavorsC5LLMClient()

    results, _ = await match_job_against_pool(
        llm=llm,
        triage_model="triage-model",
        scoring_model="scoring",
        judge_model="judge",
        job_text="job description text",
        job_embedding=[1.0, 0.0],
        candidate_pool=pool,
        top_n=1,
        triage_mode="llm",
    )

    assert "c5" in {r["candidate_id"] for r in results}


@pytest.mark.asyncio
async def test_mock_llm_triage_reads_the_prompt_instead_of_returning_one_fixed_value():
    """USE_MOCK_LLM=true's MockLLMClient must exercise triage_mode="llm"
    deterministically — see _mock_triage in llm_client.py."""
    llm = MockLLMClient()
    pool = [
        {
            "id": "strong",
            "embedding": [1.0, 0.0],
            "resume_text": "resume text",
            "profile": _FakeProfile(),
            "summary": "Senior Python FastAPI engineer with deep PostgreSQL and Docker experience.",
        },
        {
            "id": "weak",
            "embedding": [1.0, 0.0],
            "resume_text": "resume text",
            "profile": _FakeProfile(),
            "summary": "Marketing coordinator with graphic design and social media experience.",
        },
    ]

    results, stage_timings = await match_job_against_pool(
        llm=llm,
        triage_model="triage-model",
        scoring_model="scoring",
        judge_model="judge",
        job_text="Backend Engineer needing Python, FastAPI, PostgreSQL, Docker.",
        job_embedding=[1.0, 0.0],
        candidate_pool=pool,
        top_n=1,
        triage_mode="llm",
    )

    assert stage_timings["triage"] > 0.0
    ids = {r["candidate_id"] for r in results}
    assert "strong" in ids
