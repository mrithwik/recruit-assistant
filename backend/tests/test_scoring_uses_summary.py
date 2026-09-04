"""Speed-plan lever — score against the candidate summary, not raw resume
text: match_job_against_pool's deep-score pass now sends the LLM-generated
summary (already what the judge stage scores against) instead of the raw
parsed resume text, which was silently truncated at 6000 chars and carried
PDF/OCR formatting noise. A candidate with no summary yet (pre-dates this
feature, or summarization failed) must still fall back to raw text rather
than being scored against nothing."""

import json

import pytest

from app.matching.llm_client import LLMClient
from app.matching.matcher import match_job_against_pool


class _RecordingLLMClient(LLMClient):
    def __init__(self):
        self.scoring_prompts: list[str] = []

    async def complete(self, model: str, prompt: str, system: str = "") -> str:
        self.scoring_prompts.append(prompt)
        # Score outside the judge-review band so judge_score never fires —
        # isolates this test to what deep_score's prompt actually contains.
        return json.dumps({"score": 90, "matched": [], "gaps": [], "missing_info": []})

    async def embed(self, model: str, text: str) -> list[float]:
        return [0.0]


class _FakeProfile:
    skills = ["python"]
    experience_years = 5.0
    education = ["BS"]

    class employment_status:
        value = "employed"

    class work_visa_status:
        value = "us_citizen"


@pytest.mark.asyncio
async def test_deep_score_is_given_the_summary_not_the_raw_resume_text():
    llm = _RecordingLLMClient()
    pool = [
        {
            "id": "c1",
            "embedding": [1.0, 0.0],
            "resume_text": "RAW_RESUME_TEXT_MARKER a long unstructured wall of resume text",
            "profile": _FakeProfile(),
            "summary": "SUMMARY_MARKER a concise recruiter-facing summary",
        }
    ]

    await match_job_against_pool(
        llm=llm,
        triage_model="triage",
        scoring_model="scoring",
        judge_model="judge",
        job_text="job description text",
        job_embedding=[1.0, 0.0],
        candidate_pool=pool,
        top_n=5,
    )

    assert len(llm.scoring_prompts) == 1
    prompt = llm.scoring_prompts[0]
    assert "SUMMARY_MARKER" in prompt
    assert "RAW_RESUME_TEXT_MARKER" not in prompt
    # QA finding: the prompt must tell the model it's reading a summary,
    # not the raw resume — a mislabeled input risks the model reading the
    # summary's deliberate omissions (skills/years/education, already given
    # above) as gaps in the actual resume.
    assert "AI-generated from their resume" in prompt
    assert "Resume text (truncated):" not in prompt


@pytest.mark.asyncio
async def test_deep_score_falls_back_to_raw_text_when_no_summary_exists_yet():
    llm = _RecordingLLMClient()
    pool = [
        {
            "id": "c1",
            "embedding": [1.0, 0.0],
            "resume_text": "RAW_RESUME_TEXT_MARKER — only source of truth here",
            "profile": _FakeProfile(),
            "summary": "",
        }
    ]

    await match_job_against_pool(
        llm=llm,
        triage_model="triage",
        scoring_model="scoring",
        judge_model="judge",
        job_text="job description text",
        job_embedding=[1.0, 0.0],
        candidate_pool=pool,
        top_n=5,
    )

    assert len(llm.scoring_prompts) == 1
    prompt = llm.scoring_prompts[0]
    assert "RAW_RESUME_TEXT_MARKER" in prompt
    assert "Resume text (truncated):" in prompt
    assert "AI-generated from their resume" not in prompt
