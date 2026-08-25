from app.matching.llm_client import _SKILL_VOCAB, _mock_extract_profile

RESUME_PROMPT = """Extract structured candidate info from this resume text.
Return JSON with keys: legal_first_name, ...

Resume text:
---
Priya Johnson
priya.johnson@example.com | (415) 555-0192 | Austin, TX

I am writing to formally submit my application for the Data Engineer position.

Summary: 6 years of experience as a data engineer, most recently at Acme Corp.

Skills: Python, SQL, Airflow, Spark

Education: M.S. , Tech University

Work authorization: H1B
Status: actively looking
---
"""


def test_mock_extraction_reads_the_actual_resume_not_a_fixed_canned_profile():
    profile = _mock_extract_profile(RESUME_PROMPT)

    assert profile["legal_first_name"] == "Priya"
    assert profile["legal_last_name"] == "Johnson"
    assert profile["email"] == "priya.johnson@example.com"
    assert "python" in profile["skills"]
    assert "sql" in profile["skills"]
    assert profile["work_visa_status"] == "h1b"
    assert profile["employment_status"] == "actively_looking"
    assert profile["experience_years"] == 6


def test_mock_extraction_skill_match_uses_word_boundaries():
    # "go" (the language) must not substring-match inside "Google Analytics"
    # or "negotiation" — this produced wildly inflated false-positive counts
    # at dataset scale before the fix.
    prompt = "Resume text:\n---\nSkills: Google Analytics, negotiation, ongoing campaigns\n---\n"
    profile = _mock_extract_profile(prompt)
    assert "go" not in profile["skills"]
    assert "google analytics" in profile["skills"]
    assert "negotiation" not in _SKILL_VOCAB or "negotiation" in profile["skills"]


def test_mock_extraction_degrades_gracefully_on_thin_text():
    profile = _mock_extract_profile("Resume text:\n---\nJohnson - Sales Manager - resume attached\n---\n")

    assert profile["work_visa_status"] == "unknown"
    assert profile["employment_status"] == "unknown"
    assert profile["skills"] == []
