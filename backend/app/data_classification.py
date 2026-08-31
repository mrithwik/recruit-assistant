"""Classifies whether a ResumeSource represents real scanned data (a
connected email account, or a folder of a recruiter's actual resumes) or
generated sample/test data (the mock email fixtures manifest, or a folder
scan of the sample-data generator's own output) — backs the "All / Real /
Mock" data-mode filter so a recruiter who loaded a large sample dataset for
testing can view or work with just their real candidates, or just the
sample set, without deleting either.

MockEmailIngestor always writes source_ref="mock-demo-mailbox:<id>" (a fixed
literal, not the configured demo mailbox's real address — see
scanning/email_ingestor.py) — real GmailIngestor/OutlookIngestor always use
the actual connected account's address instead, so origin="email" needs no
join against EmailAccount to classify; it's a reliable signal on its own.
A folder-origin source has no such construction-time marker, so it falls
back to a path heuristic: the sample-data generator's default/documented
output directory is named "sample_data" (see reference docs) — a folder
scan of a path containing that segment is treated as sample data too.
"""

from sqlalchemy import and_, or_, select
from sqlalchemy.sql import ColumnElement

from app.models.db import ResumeSource

MOCK_EMAIL_ACCOUNT_PREFIX = "mock-demo-mailbox"

DataMode = str  # "all" | "real" | "mock" — kept a plain str to avoid a schemas.py import cycle


def is_mock_source_condition() -> ColumnElement[bool]:
    return or_(
        and_(ResumeSource.origin == "email", ResumeSource.source_ref.like(f"{MOCK_EMAIL_ACCOUNT_PREFIX}:%")),
        and_(ResumeSource.origin == "folder", ResumeSource.file_path.ilike("%sample_data%")),
    )


def is_mock_source(source: ResumeSource) -> bool:
    if source.origin == "email":
        return source.source_ref.startswith(f"{MOCK_EMAIL_ACCOUNT_PREFIX}:")
    if source.origin == "folder":
        return "sample_data" in source.file_path.lower()
    return False


def real_candidate_ids_subquery():
    """Candidates with at least one real (non-sample) source — a candidate
    with a mix of real and sample sources still counts as real, since it has
    genuine data worth keeping in the "real" view."""
    return select(ResumeSource.candidate_id).where(~is_mock_source_condition())


def candidate_id_condition(id_column, data_mode: DataMode):
    """Returns a filter condition for a column holding candidate ids (e.g.
    Candidate.id, or Match.candidate_id) for the given data_mode, or None if
    data_mode == "all" (no filtering)."""
    if data_mode == "real":
        return id_column.in_(real_candidate_ids_subquery())
    if data_mode == "mock":
        return id_column.notin_(real_candidate_ids_subquery())
    return None
