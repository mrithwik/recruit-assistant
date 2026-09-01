<!-- Version: v0 | Last updated: 2026-09-01 | Status: current -->

# Backend Architecture

Single FastAPI process (`backend/app/main.py`), modular internally. Binds to `127.0.0.1` by
default, not `0.0.0.0` — see [Design Decisions](design-decisions.md) ADR-001 and ADR-010.

## Dependency injection

`app/dependencies.py` follows the same module-globals-initialized-in-lifespan pattern as
Prodigon: `init_dependencies(settings)` runs once at startup, creating the `LocalStorageBackend`
and `LLMClient`; routes pull them via `Depends(get_storage)` / `Depends(get_llm_client)`.

## Auth (`app/auth/`)

Single-account by design — `POST /auth/register` 403s once any account exists, not just an
oversight to harden later (ADR-010's context). Session tokens are HMAC-signed and expiring;
password hashing is PBKDF2-SHA256, 210k iterations, salted, constant-time verified.
`rate_limit.py` throttles `POST /auth/login`: an in-memory, per-process, per-email counter (5
failed attempts → 15-minute lockout), identical response shape for a locked-out real email vs.
a nonexistent one, so there's no user-enumeration side channel.

## Runtime settings (`app/runtime_settings.py`)

Mock/real toggles for LLM and email that need to flip live from the UI without a backend
restart — deliberately in-memory-only (module globals), so a restart falls back to the
`.env`-configured defaults rather than an unpredictable runtime-toggled state surviving
invisibly. `User.real_llm_consent_given_at` (persisted, not here) is the one exception to that
philosophy — see ADR-013 for why consent specifically needs to survive a restart when the
toggle itself shouldn't.

## Scanning (`app/scanning/`)

- `ingestor_base.py` — `ResumeIngestor` ABC, one `scan()` method yielding `IngestedResume`.
- `folder_ingestor.py` — recursive multi-folder scan, content-hash dedupe, mtime as
  `date_submitted` fallback.
- `email_ingestor.py` — `GmailIngestor` / `OutlookIngestor` (real Gmail API / Microsoft
  Graph calls) + `MockEmailIngestor` (fixture inbox for `USE_MOCK_EMAIL=true`).
- `parser.py` — deterministic text extraction (pypdf/pdfplumber/python-docx) first, LLM
  structured-extraction fallback when extraction yields too little text. Always produces a
  `CandidateProfile`.
- `identity_resolution.py` — fingerprinting + merge-without-erasing logic (ADR-005).
- `mirror_writer.py` — writes resume + summary + metadata to the local candidates/ tree
  (ADR-004). `delete_candidate_mirror()` is the counterpart for real per-candidate erasure
  (ADR-012) — groups a candidate's `ResumeSource` rows by shared target directory first (two
  same-day submissions can land in one directory with different extensions, sharing one
  `meta.json`), reading and safety-checking `meta.json` once per directory before deleting
  anything in it.
- `ingest_service.py` — `run_scan()`, the orchestration function both folder and email scans
  call: ingest → parse → resolve identity → mirror → persist.

## Matching (`app/matching/`)

- `llm_client.py` — `LLMClient` ABC, `OpenRouterClient`, `OpenAIClient`, `MockLLMClient`
  (ADR-007).
- `embeddings.py` — cosine-similarity pre-filter, no external vector DB.
- `matcher.py` — two-stage scoring + judge (ADR-006), `score_to_tier()` mapping score → the
  five `MatchTier` values that drive the UI color bands. `Match.pipeline_stage` (ADR-011)
  tracks process status alongside `tier`'s quality signal — a separate column, not derived
  from score.
- `prompts.py` — all prompt templates in one place, the surface the golden test harness
  regression-checks against.

## Storage (`app/storage/`, `app/models/`)

- `models/db.py` — SQLAlchemy models: `User` (single account, `real_llm_consent_given_at`),
  `Job`, `Candidate`, `ResumeSource`, `Match` (incl. `tier` and `pipeline_stage` as separate
  quality/status columns), `Criterion`, `JobCriterion`, `SearchHistoryEntry`,
  `IngestScanHistoryEntry`, `EmailAccount`, `ScheduledSource`. New columns auto-migrate via
  `storage/local.py`'s schema-driven `_add_missing_columns` — no manual migration step for any
  addition to this project so far.
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

## Dashboard (`app/dashboard/`)

`service.py`'s `build_dashboard_summary` — one aggregated query set (KPIs, inflow trend, tier
distribution, pipeline-stage distribution, top skills, visa breakdown, jobs snapshot, recent
activity), all data-mode-aware. Deliberately one endpoint, not one per widget — the frontend
renders the whole dashboard from a single `GET /dashboard/summary` response.

## Scheduler (`app/scheduler/`)

An opt-in, off-hours nightly scan over whatever folders/mailboxes are registered in
`ScheduledSource` — APScheduler-backed, records one `IngestScanHistoryEntry` per run like
every other scan-producing code path, so it shows up in Recent Activity indistinguishably from
a manual scan.

## Maintenance (`app/maintenance/`)

A small registry (`tasks.py`: `{id, label, description, run_fn, pending_count_fn}`) for
backfilling existing rows when a feature ships after data already exists — the pattern this
project reaches for instead of a one-off migration script, since the pending-count function
lets both the Scan Sources page and the Dashboard's pending-updates banner show "N candidates
still need this" without duplicating the backfill logic itself.

## Data classification (`app/data_classification.py`)

Classifies a `ResumeSource` as real vs. mock/sample **without a join**: `MockEmailIngestor`
always writes the literal `mock-demo-mailbox:` `source_ref` prefix, so email-origin sources
need no `EmailAccount` lookup; folder-origin falls back to a `sample_data` path heuristic. A
candidate counts as "real" if it has at least one real source, "mock" only if every source is
mock. Threaded as a `data_mode` query param through candidate listing, match listing/running,
and every candidate/match-derived dashboard widget.

## Routes (`app/routes/`)

One file per resource: `auth`, `jobs`, `scan`, `candidates`, `candidate_rescan`, `matches`,
`match_rescan`, `criteria`, `history`, `draft_email`, `email_accounts`, `scheduled_sources`,
`dashboard`, `mock_mode`, `maintenance`, `dev_tools`, `health`. See
[API Reference](api-reference.md).
