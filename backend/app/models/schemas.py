"""Pydantic API schemas — request/response contracts for the routes."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import EmploymentStatus, MatchTier, ResumeOrigin, WorkVisaStatus


# --- Auth ---

class AuthStatusOut(BaseModel):
    setup_complete: bool


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str = ""
    remember: bool = True


class LoginRequest(BaseModel):
    email: str
    password: str
    remember: bool = True


class UserOut(BaseModel):
    id: str
    email: str
    name: str


class SessionOut(BaseModel):
    token: str
    user: UserOut


# --- Jobs ---

class JobCreate(BaseModel):
    title: str
    raw_text: str
    company: str = ""


class JobOut(BaseModel):
    id: str
    title: str
    company: str
    raw_text: str
    parsed_requirements: dict
    criteria_version: int
    active: bool
    created_at: datetime


class BulkDeleteJobsRequest(BaseModel):
    job_ids: list[str]


class BulkDeleteJobsOut(BaseModel):
    deleted: int


# --- Candidate profile (parser output) ---

class CandidateProfile(BaseModel):
    """Structured extraction target for the resume parser (deterministic-first, LLM-fallback)."""

    legal_first_name: str = ""
    legal_middle_name: str = ""
    legal_last_name: str = ""
    email: str = ""
    phone: str = ""
    employment_status: EmploymentStatus = EmploymentStatus.UNKNOWN
    work_visa_status: WorkVisaStatus = WorkVisaStatus.UNKNOWN
    skills: list[str] = Field(default_factory=list)
    experience_years: float = 0.0
    education: list[str] = Field(default_factory=list)
    raw_text: str = ""
    linkedin_url: str = ""
    github_url: str = ""
    portfolio_url: str = ""


class CandidateOut(BaseModel):
    id: str
    legal_first_name: str
    legal_middle_name: str
    legal_last_name: str
    email: str
    phone: str
    employment_status: str
    work_visa_status: str
    skills: list[str]
    experience_years: float
    education: list[str] = Field(default_factory=list)
    semantic_summary: str
    date_submitted: datetime
    primary_file_path: str
    linkedin_url: str = ""
    github_url: str = ""
    portfolio_url: str = ""
    sources: list[str] = Field(default_factory=list)  # origins this candidate was seen from
    history: list[dict] = Field(default_factory=list)  # dated timeline — see Candidate.history


class CandidateListOut(BaseModel):
    candidates: list[CandidateOut]
    total: int = 0
    elapsed_seconds: float = 0.0


class ResumeSourceOut(BaseModel):
    """One ingested submission for a candidate — backs the 'view source
    email/resume text' links on the candidate detail page."""

    id: str
    origin: str
    source_ref: str
    date_submitted: datetime
    additional_attachments: list[str] = Field(default_factory=list)


class CandidateDetailOut(CandidateOut):
    """Full profile for the candidate detail page — adds every match this
    candidate has across all jobs, so a recruiter can see their whole
    pipeline standing from one place."""

    matches: list["MatchSummaryItem"] = Field(default_factory=list)


# --- Ingestion ---

class IngestedResume(BaseModel):
    """Common output shape for both FolderIngestor and EmailIngestor — the point
    at which the two source types converge into one pipeline."""

    origin: ResumeOrigin
    source_ref: str
    file_bytes: bytes
    filename: str
    date_submitted: datetime
    sender_email: str = ""
    sender_name: str = ""
    # Filenames of other qualifying attachments on the same message (cover
    # letter, portfolio, transcript) — recorded as metadata on the resulting
    # ResumeSource rather than each being ingested as its own equally-weighted
    # "resume" (which previously ran full LLM extraction on a cover letter
    # and could overwrite better fields from the actual resume).
    additional_attachments: list[str] = Field(default_factory=list)


class ScanFolderRequest(BaseModel):
    folder_paths: list[str]
    include_subfolders: bool = True
    date_start: datetime | None = None
    date_end: datetime | None = None


class ScanEmailRequest(BaseModel):
    account_ids: list[str]
    date_start: datetime | None = None
    date_end: datetime | None = None


class ScanResult(BaseModel):
    resumes_found: int
    candidates_created: int
    candidates_updated: int
    duplicates_skipped: int = 0
    errors: list[str] = Field(default_factory=list)
    elapsed_seconds: float = 0.0


# --- Matching ---

class MatchReasons(BaseModel):
    matched: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class FlagIn(BaseModel):
    color: str  # "green" | "red"
    note: str = ""


class MatchOut(BaseModel):
    id: str
    job_id: str
    candidate: CandidateOut
    score: float
    tier: MatchTier
    reasons: MatchReasons
    missing_info: list[str]
    flags: list[dict]
    judge_notes: str
    criteria_version: int
    matched_at: datetime


class MatchListOut(BaseModel):
    matches: list[MatchOut]
    elapsed_seconds: float = 0.0


class MatchSummaryItem(BaseModel):
    """One row in a lightweight match summary — used both on the candidate
    detail page (matches across jobs) and the Jobs page (top candidates for
    a job), so neither has to fetch full MatchOut payloads just to show a
    name, score, and tier."""

    match_id: str
    job_id: str
    job_title: str
    candidate_id: str
    candidate_name: str
    score: float
    tier: MatchTier
    matched_at: datetime


class JobMatchSummary(BaseModel):
    job_id: str
    total_matches: int
    tier_counts: dict[str, int] = Field(default_factory=dict)
    top_candidates: list[MatchSummaryItem] = Field(default_factory=list)
    last_matched_at: datetime | None = None


# --- Criteria ---

class CriterionIn(BaseModel):
    name: str
    description: str = ""
    weight: float = 1.0
    job_id: str | None = None
    field_type: str = "text"  # text | number | boolean | select
    options: list[str] = Field(default_factory=list)


class CriterionOut(CriterionIn):
    model_config = {"from_attributes": True}

    id: str
    is_builtin: bool


class JobCriterionIn(BaseModel):
    enabled: bool = True
    value: str = ""


class JobCriterionOut(BaseModel):
    criterion: CriterionOut
    enabled: bool
    value: str


class RescanRequest(BaseModel):
    job_id: str
    mode: str = "existing_data"  # "existing_data" | "full_rescan"


# --- Search history ---

class SearchHistoryOut(BaseModel):
    id: str
    job_id: str
    run_at: datetime
    date_range_start: datetime | None
    date_range_end: datetime | None
    sources_scanned: dict
    candidate_count: int
    criteria_version: int


# --- Draft email ---

class DraftEmailRequest(BaseModel):
    match_id: str


class DraftEmailOut(BaseModel):
    subject: str
    body: str
    missing_required_fields: list[str]


# --- Email accounts ---

class EmailAccountOut(BaseModel):
    id: str
    provider: str
    email_address: str
    connected_at: datetime
    last_scanned_at: datetime | None
    status: str


class ScheduledSourceIn(BaseModel):
    kind: str  # "folder" | "email_account"
    ref: str  # folder path, or EmailAccount.id
    include_subfolders: bool = True


class ScheduledSourceOut(BaseModel):
    id: str
    kind: str
    ref: str
    include_subfolders: bool
    created_at: datetime
    last_run_at: datetime | None


# --- Dashboard ---

class DashboardKPIs(BaseModel):
    active_jobs: int
    total_candidates: int
    matches_scored: int
    needs_attention: int
    connected_sources: int


class InflowDay(BaseModel):
    date: str  # YYYY-MM-DD
    email: int
    folder: int


class TierCount(BaseModel):
    tier: str
    count: int


class NamedCount(BaseModel):
    label: str
    count: int


class JobSnapshot(BaseModel):
    id: str
    title: str
    candidate_count: int
    top_score: float | None
    last_matched_at: datetime | None


class AttentionItem(BaseModel):
    match_id: str
    job_id: str
    job_title: str
    candidate_id: str
    candidate_name: str
    reason: str
    tier: MatchTier


class ActivityItem(BaseModel):
    type: str  # "scan" | "candidate"
    timestamp: datetime
    description: str
    job_id: str = ""  # set when type == "scan" — links to that job's results/history
    candidate_id: str = ""  # set when type == "candidate" — links to the candidate detail page


class DashboardSummary(BaseModel):
    kpis: DashboardKPIs
    inflow_trend: list[InflowDay]
    tier_distribution: list[TierCount]
    red_flagged_count: int
    top_skills: list[NamedCount]
    visa_breakdown: list[NamedCount]
    jobs_snapshot: list[JobSnapshot]
    needs_attention: list[AttentionItem]
    recent_activity: list[ActivityItem]


# --- Dev tools: sample data generation ---

class ClearDataOut(BaseModel):
    jobs_deleted: int
    candidates_deleted: int
    matches_deleted: int
    criteria_deleted: int
    email_accounts_deleted: int


class GenerateSampleDataRequest(BaseModel):
    initial: int = 500
    followups: int = 150
    upskill: int = 100
    seed: int = 42
    out_dir: str = ""  # blank = default sample_data/ next to data/


class GenerateSampleDataOut(BaseModel):
    total_items: int
    initial_applications: int
    followups: int
    upskill_resubmissions: int
    upskill_journey_candidates: int
    resumes_dir: str
    manifest_path: str
