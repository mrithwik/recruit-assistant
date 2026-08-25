<!-- Version: v0 | Last updated: 2026-08-01 | Status: current -->

# Backend Architecture

Single FastAPI process (`backend/app/main.py`), modular internally. See
[Design Decisions](design-decisions.md) ADR-001 for why.

## Dependency injection

`app/dependencies.py` follows the same module-globals-initialized-in-lifespan pattern as
Prodigon: `init_dependencies(settings)` runs once at startup, creating the `LocalStorageBackend`
and `LLMClient`; routes pull them via `Depends(get_storage)` / `Depends(get_llm_client)`.

## Scanning (`app/scanning/`)

- `ingestor_base.py` — `ResumeIngestor` ABC, one `scan()` method yielding `IngestedResume`.
- `folder_ingestor.py` — recursive multi-folder scan, content-hash dedupe, mtime as
  `date_submitted` fallback.
- `email_ingestor.py` — `GmailIngestor` / `OutlookIngestor` (real Gmail API / Microsoft
  Graph calls) + `MockEmailIngestor` (fixture inbox for `USE_MOCK=true`).
- `parser.py` — deterministic text extraction (pypdf/pdfplumber/python-docx) first, LLM
  structured-extraction fallback when extraction yields too little text. Always produces a
  `CandidateProfile`.
- `identity_resolution.py` — fingerprinting + merge-without-erasing logic (ADR-005).
- `mirror_writer.py` — writes resume + summary + metadata to the local candidates/ tree
  (ADR-004).
- `ingest_service.py` — `run_scan()`, the orchestration function both folder and email scans
  call: ingest → parse → resolve identity → mirror → persist.

## Matching (`app/matching/`)

- `llm_client.py` — `LLMClient` ABC, `OpenRouterClient`, `OpenAIClient`, `MockLLMClient`
  (ADR-007).
- `embeddings.py` — cosine-similarity pre-filter, no external vector DB.
- `matcher.py` — two-stage scoring + judge (ADR-006), `score_to_tier()` mapping score → the
  five `MatchTier` values that drive the UI color bands.
- `prompts.py` — all prompt templates in one place, the surface the golden test harness
  regression-checks against.

## Storage (`app/storage/`, `app/models/`)

- `models/db.py` — SQLAlchemy models: `Job`, `Candidate`, `ResumeSource`, `Match`,
  `Criterion`, `SearchHistoryEntry`, `EmailAccount`.
- `models/schemas.py` — Pydantic request/response contracts, kept separate from ORM models
  so the API surface can evolve independently of the storage schema.
- `storage/base.py` / `storage/local.py` — `BaseStorageBackend` ABC / `LocalStorageBackend`
  (ADR-002).

## Criteria (`app/criteria/`)

`builtin.py` seeds the standard job-board filters (skills, experience, location, education,
certifications, visa eligibility, salary, availability) on first run. `service.py` handles
custom criteria CRUD and bumps `Job.criteria_version` on change — the version recruiters use
to decide "existing data" vs. "full rescan" (requirement 5).

## Email auth (`app/email_auth/`)

`oauth.py` — Google OAuth (`google-auth-oauthlib`) and Microsoft Graph (`msal`) authorization
code flows, `keyring`-backed token storage (ADR-009). Requires an OAuth app registration —
see [Getting Started](getting-started.md).

## Email draft (`app/email_draft/`)

`generator.py` — builds an outreach draft from a `Match` (job + candidate + match reasons),
flags any of the four required fields (legal first/last name, employment status, work visa
status) still missing on the candidate.

## Routes (`app/routes/`)

One file per resource: `jobs`, `scan`, `candidates`, `matches`, `criteria`, `history`,
`draft_email`, `email_accounts`, `health`. See [API Reference](api-reference.md).
