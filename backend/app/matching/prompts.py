"""Prompt templates for the two-stage matcher + judge. Kept in one file so
prompt tuning (the thing the golden test harness regression-checks) has a
single place to change."""

# Labels for SCORING_PROMPT's {resume_label} slot — deep_score is handed
# either the raw resume text or the AI-generated summary (see matcher.py's
# _score_one), and the model should be told honestly which one it's
# reading, the same way JUDGE_PROMPT already labels its own input as
# "Candidate summary" rather than implying it's the resume itself. A
# mislabeled input risks the model reading SUMMARY_PROMPT's deliberate
# omissions (skills/years/education, already given above as structured
# fields) as gaps in the actual resume.
RESUME_TEXT_LABEL = "Resume text (truncated)"
SUMMARY_LABEL = (
    "Candidate summary (AI-generated from their resume — it was deliberately told not to "
    "restate skills/years/education, already given above, so don't treat something absent "
    "here as missing from the resume itself unless the Candidate Profile above is also silent on it)"
)

SCORING_PROMPT = """You are scoring a candidate resume against a job description.

Job Description:
---
{job_text}
---

Candidate Profile:
- Skills: {skills}
- Experience: {experience_years} years
- Education: {education}
- Employment status: {employment_status}
- Work authorization: {work_visa_status}

{resume_label}:
---
{resume_text}
---

Score the match from 0-100 and explain. Return ONLY JSON:
{{"score": <0-100>, "matched": [<strings>], "gaps": [<strings>], "missing_info": [<strings, fields the job needs but the resume doesn't answer>]}}
"""

TRIAGE_PROMPT = """You are quickly triaging a candidate for a job — not scoring in
depth, just judging whether they're plausibly relevant enough to be worth a
full review. Err toward including a candidate if unsure; this only decides
who advances to deep review, not a final score.

Job Description:
---
{job_text}
---

Candidate summary:
---
{candidate_summary}
---

Return ONLY JSON: {{"relevance": <0-100, how plausible a fit>}}
"""

JUDGE_PROMPT = """You are an impartial judge reviewing an AI-generated resume-to-job match score.

Job Description:
---
{job_text}
---

Candidate summary: {candidate_summary}
Initial score: {score}
Stated reasons matched: {matched}
Stated gaps: {gaps}

Critique this score. Is it fair, too generous, or too harsh given the evidence?
If you disagree, provide a corrected score. Return ONLY JSON:
{{"agrees": <true|false>, "corrected_score": <0-100 or null>, "judge_notes": "<1-2 sentence rationale>"}}
"""

SUMMARY_PROMPT = """Summarize this resume for a recruiter skimming a list, and for an
AI scorer matching it against job descriptions later. Skills, years of
experience, education, employment status, and work authorization are already
captured separately elsewhere — don't just restate them here. Focus on what a
bare skills list misses: career narrative and seniority trajectory, the most
relevant specific projects or achievements (with concrete scope or impact
where the resume states one — team size, scale, metrics), domain or industry
specialization, and any notable gaps or red flags worth flagging.

Write 4-6 sentences, dense with specifics actually present in the resume —
no generic filler, nothing invented. Plain prose, skimmable in seconds.

Resume text:
---
{resume_text}
---
"""
