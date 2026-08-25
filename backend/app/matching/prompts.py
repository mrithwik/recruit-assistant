"""Prompt templates for the two-stage matcher + judge. Kept in one file so
prompt tuning (the thing the golden test harness regression-checks) has a
single place to change."""

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

Resume text (truncated):
---
{resume_text}
---

Score the match from 0-100 and explain. Return ONLY JSON:
{{"score": <0-100>, "matched": [<strings>], "gaps": [<strings>], "missing_info": [<strings, fields the job needs but the resume doesn't answer>]}}
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

SUMMARY_PROMPT = """Write a 2-3 sentence semantic summary of this candidate for a
recruiter skimming a list — role fit, seniority, standout skills, notable gaps.

Resume text:
---
{resume_text}
---
"""
