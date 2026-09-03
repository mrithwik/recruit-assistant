"""Pydantic API schemas — request/response contracts for the routes."""

from datetime import UTC, datetime

from pydantic import BaseModel, Field, field_validator

from app.models.enums import EmploymentStatus, MatchTier, PipelineStage, ResumeOrigin, WorkVisaStatus


def _to_naive_utc(value: datetime | None) -> datetime | None:
    """The frontend's date picker sends toISOString() (a "Z"-suffixed,
    timezone-aware string) — Pydantic parses that as an aware datetime, but
    every date_submitted elsewhere in the codebase is naive UTC
    (datetime.utcnow()). Comparing an aware and a naive datetime raises
    TypeError ("can't compare offset-naive and offset-aware datetimes") —
    this is what actually failed a real scan (see project-log). Normalizing
    once at the request boundary means no ingestor/comparison site downstream
    needs to know timezones exist at all."""
    if value is not None and value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value

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


class CandidateIdsIn(BaseModel):
    ids: list[str]


class CandidateNoteOut(BaseModel):
    id: str
    text: str
    created_at: datetime


class CandidateNoteCreate(BaseModel):
    text: str


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
    recruiter_notes: list[CandidateNoteOut] = Field(default_factory=list)  # see Candidate.recruiter_notes
    # Deep link to the most recent source email with one on record — blank
    # if every source is folder-origin, a mock fixture, or predates the
    # email_link feature. See ResumeSource.email_link / email_ingestor.py.
    email_link: str = ""


class CandidateListOut(BaseModel):
    candidates: list[CandidateOut]
    total: int = 0
    elapsed_seconds: float = 0.0


class CandidateFacetsOut(BaseModel):
    """Options for the All Candidates filter bar — skills are the distinct
    values actually present in the pool (so the picker never offers a skill
    with zero matches); status/visa options are the fixed enums since every
    value is always a legitimate filter choice even if unused today."""

    skills: list[str] = Field(default_factory=list)
    employment_statuses: list[str] = Field(default_factory=list)
    work_visa_statuses: list[str] = Field(default_factory=list)
    experience_years_max: float = 0.0


class DataModeCountsOut(BaseModel):
    """Backs the "All / Real / Mock" data-mode toggle — lets it show
    "Real (624) / Mock (14,115)" instead of unlabeled options."""

    real: int = 0
    mock: int = 0
    total: int = 0


class ResumeSourceOut(BaseModel):
    """One ingested submission for a candidate — backs the 'view source
    email/resume text' links on the candidate detail page."""

    id: str
    origin: str
    source_ref: str
    date_submitted: datetime
    additional_attachments: list[str] = Field(default_factory=list)
    email_link: str = ""


class CandidateDetailOut(CandidateOut):
    """Full profile for the candidate detail page — adds every match this
    candidate has across all jobs, so a recruiter can see their whole
    pipeline standing from one place."""

    matches: list["CandidateMatchDetail"] = Field(default_factory=list)


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
    # Deep link to the source email (Gmail/Outlook web UI) — blank for
    # folder-origin resumes and mock fixtures. See email_ingestor.py.
    email_link: str = ""


class ScanFolderRequest(BaseModel):
    folder_paths: list[str]
    include_subfolders: bool = True
    date_start: datetime | None = None
    date_end: datetime | None = None

    _normalize_dates = field_validator("date_start", "date_end")(_to_naive_utc)


class ScanEmailRequest(BaseModel):
    account_ids: list[str]
    date_start: datetime | None = None
    date_end: datetime | None = None
    # When false (default) and date_start isn't explicitly given, each
    # account is scanned only from its own EmailAccount.last_scanned_at
    # forward — see speed-plan lever "incremental email scan" in
    # project-log.md. Set true to force a full mailbox rescan (e.g. after a
    # parsing/matching change that should reprocess history).
    full_rescan: bool = False

    _normalize_dates = field_validator("date_start", "date_end")(_to_naive_utc)


class ScanResult(BaseModel):
    resumes_found: int
    candidates_created: int
    candidates_updated: int
    duplicates_skipped: int = 0
    errors: list[str] = Field(default_factory=list)
    elapsed_seconds: float = 0.0
    # Total wall-clock seconds spent in each named pipeline stage across the
    # whole run (e.g. "parse", "summarize", "mirror_write" for a scan;
    # "embed", "deep_score", "judge" for a match run) — see the speed-plan
    # report's "instrument first" recommendation. Empty for job types that
    # don't report per-stage timing yet. Stages can run concurrently with
    # each other (bounded_gather), so these don't sum to elapsed_seconds.
    stage_timings: dict[str, float] = Field(default_factory=dict)


class ScanJobOut(BaseModel):
    """A scan now runs as a background job (see app/scanning/job_registry.py)
    instead of blocking the triggering request — a real email scan can run
    long enough that holding one HTTP request open for it is bad UX and
    risks a browser/proxy timeout. POST /scan/folders and /scan/email-accounts
    return this immediately with status="running"; poll GET /scan/jobs/{id}
    for progress."""

    id: str
    status: str
    started_at: datetime
    completed_at: datetime | None = None
    result: ScanResult | None = None
    progress: ScanResult | None = None
    error: str | None = None
    # True once the job actually stopped early from a cancel request (see
    # job_registry.request_cancel) — status is still "completed", since
    # whatever it found up to that point is real, saved progress, not a
    # failure.
    cancelled: bool = False


class MaintenanceTaskOut(BaseModel):
    """One registered backfill/repair task — see app/maintenance/tasks.py."""

    id: str
    label: str
    description: str
    pending_count: int = 0


# --- Matching ---

class MatchReasons(BaseModel):
    matched: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class FlagIn(BaseModel):
    color: str  # "green" | "red"
    note: str = ""


class PipelineStageIn(BaseModel):
    stage: PipelineStage


class MatchOut(BaseModel):
    id: str
    job_id: str
    candidate: CandidateOut
    score: float
    tier: MatchTier
    pipeline_stage: PipelineStage
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
    """One row in a lightweight match summary — used on the Jobs page's
    "top candidates for this job" widget, where only a name/score/tier is
    shown and fetching full MatchOut payloads (reasons, flags, etc.) would
    be wasted work. See CandidateMatchDetail for the richer version the
    candidate detail page uses."""

    match_id: str
    job_id: str
    job_title: str
    candidate_id: str
    candidate_name: str
    score: float
    tier: MatchTier
    pipeline_stage: PipelineStage
    matched_at: datetime


class CandidateMatchDetail(MatchSummaryItem):
    """CandidateDetailOut's per-match rows — adds the same red-flag/missing-
    info/judge-notes detail the Match Results page shows, so the "Review"
    link from the dashboard's Needs Attention list actually lands somewhere
    that explains *why* this match needs a look, not just a bare tier badge
    with no way to follow up."""

    reasons: MatchReasons = Field(default_factory=MatchReasons)
    missing_info: list[str] = Field(default_factory=list)
    flags: list[dict] = Field(default_factory=list)
    judge_notes: str = ""


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


class IngestScanLogOut(BaseModel):
    id: str
    origin: str
    source_label: str
    resumes_found: int
    candidates_created: int
    candidates_updated: int
    duplicates_skipped: int
    error_count: int
    ran_at: datetime
    batch_id: str | None
    job_id: str | None


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


class OAuthStatusOut(BaseModel):
    """Whether Google/Microsoft OAuth client credentials are set in .env —
    backs the setup-instructions banner on the Email Access page for a
    fresh deploy where nobody's connected an account yet."""

    google_configured: bool
    microsoft_configured: bool


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


class PipelineStageCount(BaseModel):
    stage: str
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


class ActivityItem(BaseModel):
    type: str  # "scan" (a matching run) | "candidate" | "ingest" (a folder/email scan — see IngestScanHistoryEntry)
    timestamp: datetime
    description: str
    job_id: str = ""  # set when type == "scan" — links to that job's Match Results
    candidate_id: str = ""  # set when type == "candidate" — links to the candidate detail page
    # Populated only for a collapsed bulk-run entry (see SearchHistoryEntry/
    # IngestScanHistoryEntry.batch_id and dashboard/service.py's
    # _recent_activity) — one sub-item per job in that batch, so a "Match
    # all" or "Update matched (N)" run shows as one row with the individual
    # per-job outcomes available on expand rather than flooding the feed.
    sub_items: list["ActivityItem"] = Field(default_factory=list)


class ActivityLogPage(BaseModel):
    items: list[ActivityItem]
    total: int


class DashboardSummary(BaseModel):
    kpis: DashboardKPIs
    inflow_trend: list[InflowDay]
    tier_distribution: list[TierCount]
    pipeline_stage_distribution: list[PipelineStageCount]
    red_flagged_count: int
    top_skills: list[NamedCount]
    visa_breakdown: list[NamedCount]
    jobs_snapshot: list[JobSnapshot]
    missing_info_breakdown: list[NamedCount]
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
    label: str | None = None  # blank = auto-labeled from counts + timestamp


class GenerateSampleDataOut(BaseModel):
    total_items: int
    initial_applications: int
    followups: int
    upskill_resubmissions: int
    upskill_journey_candidates: int
    resumes_dir: str
    manifest_path: str
    session_id: str
    label: str


class SampleSessionOut(BaseModel):
    id: str
    label: str
    generated_at: str
    seed: int | None = None
    total_items: int
    candidates_scanned: int
    scanned: bool


class SampleSessionDeleteOut(BaseModel):
    candidates_deleted: int
    candidates_trimmed: int
    sources_deleted: int
    files_deleted: bool


# --- Mock mode (runtime-toggleable, see app/runtime_settings.py) ---

class MockModeOut(BaseModel):
    use_mock_llm: bool
    use_mock_email: bool
    real_llm_available: bool  # whether an OpenRouter/OpenAI key is configured at all
    expose_toggle: bool  # Settings.expose_mock_mode_toggle — UI hides the control if false
    real_llm_consent_given: bool  # one-time ack that resume text leaves the machine in real mode


class MockModeUpdateRequest(BaseModel):
    use_mock_llm: bool | None = None
    use_mock_email: bool | None = None
    consent_ack: bool = False  # required the first time use_mock_llm is set to False
