"""
Golden-set regression harness (requirement 7): fixed (JD, resume, expected
tier) pairs used to catch regressions when prompts/models change.

With USE_MOCK=true (CI default) the mock LLM returns a fixed canned score, so
these tests only assert the pipeline runs end-to-end and produces a
well-formed, in-range result — they can't judge match quality against a
constant mock. The tier assertions (`expected_tier_min`/`expected_tier_max`)
are enforced only when a real provider is configured (RUN_LIVE_GOLDEN=true +
OPENROUTER_API_KEY or OPENAI_API_KEY set) — that's the actual regression gate
for prompt/model tuning; run it before merging changes to matching/prompts.py.
"""

import json
import os
from pathlib import Path

import pytest

from app.matching.llm_client import MockLLMClient, build_llm_client
from app.matching.matcher import deep_score, score_to_tier
from app.models.enums import EmploymentStatus, WorkVisaStatus
from app.models.schemas import CandidateProfile

FIXTURES_DIR = Path(__file__).parent / "fixtures"
TIER_ORDER = ["poor_match", "average_match", "good_match", "great_match"]


def _load_fixtures():
    return [json.loads(p.read_text()) for p in sorted(FIXTURES_DIR.glob("*.json"))]


def _tier_at_least(tier: str, minimum: str) -> bool:
    return TIER_ORDER.index(tier) >= TIER_ORDER.index(minimum)


def _tier_at_most(tier: str, maximum: str) -> bool:
    return TIER_ORDER.index(tier) <= TIER_ORDER.index(maximum)


@pytest.mark.parametrize("fixture", _load_fixtures(), ids=lambda f: f["name"])
async def test_golden_fixture_runs_and_scores_in_range(fixture):
    llm = MockLLMClient()
    profile = CandidateProfile(raw_text=fixture["resume_text"])
    result = await deep_score(llm, "", fixture["job_text"], fixture["resume_text"], profile)

    assert 0 <= result.get("score", -1) <= 100
    assert "matched" in result and "gaps" in result


@pytest.mark.skipif(
    not os.getenv("RUN_LIVE_GOLDEN") or not (os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")),
    reason="Live golden regression requires RUN_LIVE_GOLDEN=true and a real LLM API key.",
)
@pytest.mark.parametrize("fixture", _load_fixtures(), ids=lambda f: f["name"])
async def test_golden_fixture_live_tier(fixture):
    llm = build_llm_client(
        use_mock=False,
        openrouter_key=os.getenv("OPENROUTER_API_KEY", ""),
        openai_key=os.getenv("OPENAI_API_KEY", ""),
    )
    profile = CandidateProfile(
        raw_text=fixture["resume_text"],
        employment_status=EmploymentStatus.UNKNOWN,
        work_visa_status=WorkVisaStatus.UNKNOWN,
    )
    result = await deep_score(
        llm,
        os.getenv("LLM_SCORING_MODEL", "openrouter/openai/gpt-4.1-mini"),
        fixture["job_text"],
        fixture["resume_text"],
        profile,
    )
    tier = score_to_tier(float(result.get("score", 0)), has_red_flag=False).value

    if "expected_tier_min" in fixture:
        assert _tier_at_least(tier, fixture["expected_tier_min"]), (
            f"{fixture['name']}: got {tier}, expected >= {fixture['expected_tier_min']}"
        )
    if "expected_tier_max" in fixture:
        assert _tier_at_most(tier, fixture["expected_tier_max"]), (
            f"{fixture['name']}: got {tier}, expected <= {fixture['expected_tier_max']}"
        )
