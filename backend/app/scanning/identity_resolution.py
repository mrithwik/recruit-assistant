"""
Identity resolution — the piece that makes email-sourced and folder-sourced
resumes for the same person converge on one Candidate row instead of two.

Fingerprint priority: email address (most reliable) > normalized
name+phone. Every ingested resume runs through this before it's persisted.
"""

import re
import uuid

from app.models.db import Candidate, ResumeSource
from app.models.enums import ResumeOrigin
from app.models.schemas import CandidateProfile


def compute_fingerprint(profile: CandidateProfile) -> str:
    if profile.email:
        return f"email:{profile.email.strip().lower()}"
    name = f"{profile.legal_first_name}{profile.legal_last_name}".lower()
    name = re.sub(r"[^a-z]", "", name)
    phone_digits = re.sub(r"\D", "", profile.phone)
    if not name and not phone_digits:
        # No extractable identity at all (a thin/garbled resume with no name,
        # email, or phone) — give it a unique fingerprint rather than the
        # same "name::phone:" key every other unidentifiable resume would
        # get, which would silently merge unrelated people into one
        # candidate. There's nothing to merge on, so don't pretend there is.
        return f"unidentified:{uuid.uuid4()}"
    return f"name:{name}:phone:{phone_digits}"


def merge_into_candidate(existing: Candidate | None, profile: CandidateProfile, fingerprint: str) -> Candidate:
    """Create a new Candidate, or update an existing one with any newly-available
    fields (never overwrite a known field with a blank one — 'new info updates
    the profile' per requirement 3, it doesn't erase prior info)."""
    if existing is None:
        return Candidate(
            id=str(uuid.uuid4()),
            identity_fingerprint=fingerprint,
            legal_first_name=profile.legal_first_name,
            legal_middle_name=profile.legal_middle_name,
            legal_last_name=profile.legal_last_name,
            email=profile.email,
            phone=profile.phone,
            employment_status=profile.employment_status.value,
            work_visa_status=profile.work_visa_status.value,
            skills=profile.skills,
            experience_years=profile.experience_years,
            education=profile.education,
            linkedin_url=profile.linkedin_url,
            github_url=profile.github_url,
            portfolio_url=profile.portfolio_url,
            raw_parsed_profile=profile.model_dump(mode="json"),
            history=[],
            embedding=[],
        )

    for field, value in [
        ("legal_first_name", profile.legal_first_name),
        ("legal_middle_name", profile.legal_middle_name),
        ("legal_last_name", profile.legal_last_name),
        ("email", profile.email),
        ("phone", profile.phone),
        ("linkedin_url", profile.linkedin_url),
        ("github_url", profile.github_url),
        ("portfolio_url", profile.portfolio_url),
    ]:
        if value and not getattr(existing, field):
            setattr(existing, field, value)

    if profile.employment_status.value != "unknown":
        existing.employment_status = profile.employment_status.value
    if profile.work_visa_status.value != "unknown":
        existing.work_visa_status = profile.work_visa_status.value
    if profile.skills:
        existing.skills = sorted(set(existing.skills) | set(profile.skills))
    if profile.experience_years:
        existing.experience_years = max(existing.experience_years, profile.experience_years)
    if profile.education:
        existing.education = sorted(set(existing.education) | set(profile.education))
    existing.raw_parsed_profile = profile.model_dump(mode="json")
    return existing


def build_resume_source(candidate_id: str, origin: ResumeOrigin, source_ref: str, content_hash: str,
                         file_path: str, date_submitted, additional_attachments: list[str] | None = None,
                         email_link: str = "", generation_session_id: str | None = None) -> ResumeSource:
    return ResumeSource(
        id=str(uuid.uuid4()),
        candidate_id=candidate_id,
        origin=origin.value,
        source_ref=source_ref,
        content_hash=content_hash,
        file_path=file_path,
        date_submitted=date_submitted,
        additional_attachments=additional_attachments or [],
        email_link=email_link,
        generation_session_id=generation_session_id,
    )
