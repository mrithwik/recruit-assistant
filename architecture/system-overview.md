<!-- Version: v0 | Last updated: 2026-08-01 | Status: current -->

# System Overview

## What it does

A recruiter adds any number of job descriptions, points the app at local resume folders and/or
connected email accounts, and runs a scan. Every resume found — regardless of source — is
parsed, deduplicated against existing candidates by identity (email or name+phone), and
merged into one source-agnostic candidate profile. The recruiter then runs LLM-based
matching against a job, reviews color-coded results with match reasons and flags, and can
generate a draft outreach email.

## Architecture

```mermaid
graph TB
    Browser([Browser]) --> Frontend[React Frontend :5173 dev]
    Frontend -->|"/api/* /health"| Backend[FastAPI Backend :8000]

    Backend --> Storage[(SQLite + local file mirror)]
    Backend --> LLM[LLM Client]
    Backend --> Gmail[Gmail API]
    Backend --> Graph[Microsoft Graph API]

    LLM -->|primary| OpenRouter[OpenRouter]
    LLM -->|fallback| OpenAI[OpenAI]

    subgraph backend_modules["Backend modules (single process)"]
        Scanning[scanning/: folder + email ingestors, parser, identity resolution, mirror writer]
        Matching[matching/: embeddings, two-stage matcher, judge]
        Criteria[criteria/]
        EmailDraft[email_draft/]
        EmailAuth[email_auth/: OAuth + OS keychain]
        StorageMod[storage/: BaseStorageBackend]
    end

    Backend --> backend_modules

    style Frontend fill:#3b82f6,color:#fff
    style OpenRouter fill:#10b981,color:#fff
```

Unlike a typical microservices platform, this is intentionally **one FastAPI process**,
modular internally by domain. A recruiter runs this on a laptop — `make run` starts
everything backend-side, `make run-frontend` starts the Vite dev server. See
[Design Decisions](design-decisions.md) for why, and how a future split into services
would work without a rewrite.

## Repo structure

```
recruit-assistant/
├── architecture/          # this documentation
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI app + lifespan
│   │   ├── config.py          # Settings (env-driven, Pydantic)
│   │   ├── dependencies.py    # DI getters (storage, LLM client)
│   │   ├── routes/            # jobs, scan, candidates, matches, criteria, history,
│   │   │                      # draft-email, email-accounts, health
│   │   ├── scanning/          # ResumeIngestor (folder + email), parser, identity
│   │   │                      # resolution, mirror writer, ingest orchestrator
│   │   ├── email_auth/        # Gmail / Microsoft Graph OAuth, keychain token storage
│   │   ├── matching/          # LLM client, embeddings, two-stage matcher + judge
│   │   ├── criteria/          # built-in + custom criteria, rescan orchestration
│   │   ├── email_draft/       # outreach email generator
│   │   └── models/            # SQLAlchemy models + Pydantic schemas
│   └── tests/
│       ├── golden/            # golden JD/resume fixtures + regression harness
│       └── ...                # unit tests
├── frontend/               # React + Vite + TS + Zustand + Tailwind
│   └── src/
│       ├── components/{jobs,scan,candidates,criteria,layout,ui}/
│       ├── stores/         # zustand: jobs, matches, scan, criteria, history, candidates
│       ├── pages/          # one per nav tab
│       └── lib/            # api client, shared types, nav config
├── data/                    # gitignored — SQLite db + candidate/resume mirror
├── scripts/                 # setup.sh, run_all.sh, check_health.sh
├── Makefile
└── pyproject.toml
```

## Tech stack

**Backend:** Python 3.11+, FastAPI, SQLAlchemy + SQLite, Pydantic v2, httpx, structlog,
pypdf/pdfplumber/python-docx, keyring (OS keychain), google-auth-oauthlib, msal, APScheduler.

**Frontend:** React 18 + TypeScript + Vite, Zustand, Tailwind CSS v4, react-router-dom.

**LLM:** OpenRouter (primary gateway) with OpenAI as a direct fallback provider, behind one
`LLMClient` abstraction. `MockLLMClient` runs the entire pipeline offline with zero API keys.

## Where each requirement lives

| Requirement | Where |
|---|---|
| 2.1 Job descriptions (uncapped, searchable, paginated) | `routes/jobs.py`, `pages/jobs-page.tsx` — the operational hub |
| 2.2 Multi-folder scan w/ subfolders | `scanning/folder_ingestor.py`, `pages/scan-page.tsx` |
| 2.3 Email access + safeguards | `email_auth/oauth.py` (OS keychain), `pages/email-access-page.tsx` |
| 2.4 Connection setup (company/cloud) | `storage/base.py` interface (Phase 2 impl), `pages/connections-page.tsx` (stub) |
| 2.5 Candidate results, color-coded | `matching/matcher.py` (`score_to_tier`), `components/ui/match-badge.tsx` |
| 2.6 Draft outreach email | `email_draft/generator.py`, `components/candidates/draft-email-modal.tsx` |
| 2.7 Search history | `routes/history.py`, `pages/history-page.tsx` |
| 2.8 Date range picker | `components/ui/date-range-picker.tsx` |
| 2.9 Local save, browsable structure | `scanning/mirror_writer.py` |
| 2.10 Screening sources | `pages/screening-sources-page.tsx` |
| Criteria library (typed: text/number/boolean/select) | `criteria/builtin.py`, `criteria/service.py` |
| Per-job criteria selection | `JobCriterion` model, `routes/criteria.py` (`/for-job/*`), `components/jobs/job-criteria-panel.tsx` |
| Per-job scan/rescan (existing data vs. re-ingest) | `components/jobs/job-scan-match-panel.tsx` (reuses `scan-store`) |
| Candidate history timeline (dated, multi-submission) | `Candidate.history`, `scanning/ingest_service.py` (`_append_history_entry`) |
| LLM matching + judge + golden tests | `matching/`, `backend/tests/golden/` |
| Personal dashboard | `dashboard/service.py`, `pages/dashboard-page.tsx` |
| Sample-data generation (CLI + in-app, folder + mailbox source) | `dev_tools/sample_data_generator.py`, `routes/dev_tools.py`, `components/scan/sample-data-generator.tsx` |
| Candidate detail page (links, pipeline, history, source text) | `pages/candidate-detail-page.tsx`, `routes/candidates.py` (`/{id}`, `/{id}/sources*`) |
| Job match summary ("latest results" on the Jobs page) | `routes/matches.py` (`/summary/{job_id}`), `components/jobs/job-results-summary.tsx` |
| Company field + advanced job search | `Job.company`, `pages/jobs-page.tsx` |
| Default criteria auto-applied on job creation | `criteria/service.py` (`seed_default_job_criteria`) |
| Scan/generate progress + ETA | `components/ui/progress-bar.tsx` (`useSimulatedProgress`) |
