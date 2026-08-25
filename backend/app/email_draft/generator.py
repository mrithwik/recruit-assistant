"""Outreach email draft generator (requirement 2.6) — pulls legal name, match
reasons, and JD context from a persisted Match, and flags any of the
required fields (legal name parts, employment status, visa status) that are
still missing so the recruiter fills them in before sending."""

from app.matching.llm_client import LLMClient
from app.models.db import Candidate, Job, Match

REQUIRED_FIELDS = ["legal_first_name", "legal_last_name", "employment_status", "work_visa_status"]

DRAFT_PROMPT = """Write a warm, concise recruiter outreach email to a job candidate.

Candidate legal name: {first} {middle} {last}
Job title: {job_title}
Why they're a strong match: {matched_reasons}
Candidate's current employment status: {employment_status}
Candidate's work authorization: {work_visa_status}

The email should:
- Reference specific matched strengths (not generic flattery)
- Briefly describe the role
- Ask about interest and availability
- Be under 150 words, professional but friendly tone

Return ONLY the email body text, no subject line, no preamble.
"""


def missing_required_fields(candidate: Candidate) -> list[str]:
    missing = []
    for field in REQUIRED_FIELDS:
        value = getattr(candidate, field, "")
        if not value or value == "unknown":
            missing.append(field)
    return missing


async def generate_draft(llm: LLMClient, model: str, job: Job, candidate: Candidate, match: Match) -> dict:
    prompt = DRAFT_PROMPT.format(
        first=candidate.legal_first_name,
        middle=candidate.legal_middle_name,
        last=candidate.legal_last_name,
        job_title=job.title,
        matched_reasons=", ".join(match.reasons.get("matched", [])),
        employment_status=candidate.employment_status,
        work_visa_status=candidate.work_visa_status,
    )
    body = await llm.complete(model, prompt)
    subject = f"Opportunity: {job.title} — thought of you"
    return {
        "subject": subject,
        "body": body,
        "missing_required_fields": missing_required_fields(candidate),
    }
