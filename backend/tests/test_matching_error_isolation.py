"""One candidate's deep-score/judge/triage call failing must not abort the
whole matching run and lose every other candidate's already-computed
results — the same guarantee already enforced in ingestion (per-resume) and
email fan-in (per-source), extended here to match_job_against_pool's three
bounded_gather passes. Before this fix, bounded_gather's unmodified
asyncio.gather meant a single exception propagated and killed the entire
batch (and, via the route's outer except, failed the whole job)."""

import json

import pytest

from app.matching.llm_client import LLMClient
from app.matching.matcher import SHORTLIST_MULTIPLIER, TRIAGE_WIDENING_MULTIPLIER, match_job_against_pool


class _FakeProfile:
    skills = ["python"]
    experience_years = 5.0
    education = ["BS"]

    class employment_status:
        value = "employed"

    class work_visa_status:
        value = "us_citizen"


def _pool(n: int) -> list[dict]:
    return [
        {
            "id": f"c{i}",
            "embedding": [1.0, 0.0],
            "resume_text": f"resume text for candidate {i}",
            "profile": _FakeProfile(),
            "summary": f"summary for candidate {i}",
        }
        for i in range(n)
    ]


@pytest.mark.asyncio
async def test_one_failing_deep_score_call_does_not_lose_the_other_candidates_results():
    class _FailsOnCandidate2(LLMClient):
        async def complete(self, model: str, prompt: str, system: str = "") -> str:
            if "candidate 2" in prompt:
                raise RuntimeError("simulated transient provider error")
            return json.dumps({"score": 90, "matched": [], "gaps": [], "missing_info": []})

        async def embed(self, model: str, text: str) -> list[float]:
            return [0.0]

    pool = _pool(3)  # top_n=1 * SHORTLIST_MULTIPLIER=3 keeps all 3

    results, stage_timings, errors = await match_job_against_pool(
        llm=_FailsOnCandidate2(),
        triage_model="triage",
        scoring_model="scoring",
        judge_model="judge",
        job_text="job description text",
        job_embedding=[1.0, 0.0],
        candidate_pool=pool,
        top_n=1,
    )

    ids = {r["candidate_id"] for r in results}
    assert ids == {"c0", "c1"}
    assert "c2" not in ids
    assert any("c2" in e for e in errors)


@pytest.mark.asyncio
async def test_one_failing_judge_call_still_keeps_that_candidates_unreviewed_deep_score():
    class _FailsJudgeForCandidate1(LLMClient):
        async def complete(self, model: str, prompt: str, system: str = "") -> str:
            if "Critique this score" in prompt:
                if "candidate 1" in prompt:
                    raise RuntimeError("simulated transient provider error")
                return json.dumps({"agrees": True, "corrected_score": None, "judge_notes": "fine"})
            # Score both candidates in the judge-review band (40-70) so both
            # trigger a judge call.
            return json.dumps({"score": 55, "matched": [], "gaps": [], "missing_info": []})

        async def embed(self, model: str, text: str) -> list[float]:
            return [0.0]

    pool = _pool(2)

    results, stage_timings, errors = await match_job_against_pool(
        llm=_FailsJudgeForCandidate1(),
        triage_model="triage",
        scoring_model="scoring",
        judge_model="judge",
        job_text="job description text",
        job_embedding=[1.0, 0.0],
        candidate_pool=pool,
        top_n=1,
    )

    # Both candidates still get a result — c1's judge call failing degrades
    # to "no judge correction applied" (its raw deep-score of 55 survives),
    # exactly like a candidate whose score never entered the judge band.
    by_id = {r["candidate_id"]: r for r in results}
    assert set(by_id) == {"c0", "c1"}
    assert by_id["c1"]["score"] == 55.0
    assert any("c1" in e for e in errors)


@pytest.mark.asyncio
async def test_one_failing_triage_call_fails_open_instead_of_dropping_the_candidate():
    class _FailsTriageForCandidate3(LLMClient):
        async def complete(self, model: str, prompt: str, system: str = "") -> str:
            if "triaging a candidate" in prompt:
                if "candidate 3" in prompt:
                    raise RuntimeError("simulated transient provider error")
                return json.dumps({"relevance": 10})
            return json.dumps({"score": 90, "matched": [], "gaps": [], "missing_info": []})

        async def embed(self, model: str, text: str) -> list[float]:
            return [0.0]

    # top_n=1 -> keep_n = SHORTLIST_MULTIPLIER = 3; widened embedding net
    # (TRIAGE_WIDENING_MULTIPLIER * keep_n) covers the whole 4-candidate
    # pool, so all 4 reach the triage pass and only the failing one's
    # candidate-3 fate is in question.
    pool = _pool(min(4, SHORTLIST_MULTIPLIER * TRIAGE_WIDENING_MULTIPLIER))

    results, stage_timings, errors = await match_job_against_pool(
        llm=_FailsTriageForCandidate3(),
        triage_model="triage",
        scoring_model="scoring",
        judge_model="judge",
        job_text="job description text",
        job_embedding=[1.0, 0.0],
        candidate_pool=pool,
        top_n=1,
        triage_mode="llm",
    )

    # Failing open (neutral relevance) beats every other candidate's
    # deliberately-low 10, so c3 survives the keep_n=3 cut instead of being
    # silently excluded because of a transient error.
    ids = {r["candidate_id"] for r in results}
    assert "c3" in ids
    assert any("c3" in e for e in errors)
