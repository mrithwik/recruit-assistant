# Recruit Assistant

A local-first AI recruiting assistant. Scans resumes from local folders **and** connected
email accounts, merges them into deduplicated candidate profiles, and uses LLM-based
matching (with an LLM-as-judge review pass) to score candidates against your job
descriptions — with a clear path to production (cloud storage, company servers, multi-user)
without a rewrite.

Structured after [Prodigon](../prodigon)'s conventions: a Pydantic-Settings-configured
backend, ADR-documented design decisions, a Makefile as the single command surface, and a
React/Vite frontend.

## Quick start (mock mode — no API keys needed)

```bash
make setup
make run                 # backend on :8000

# separate terminal
make install-frontend
make run-frontend        # frontend on :5173
```

Open http://localhost:5173. Everything works offline out of the box (`USE_MOCK=true` in
`.env` by default) — folder scanning, resume parsing, matching, and drafting all run against
mock LLM responses so you can try the full flow with zero setup.

### Or with Docker (no Python/Node install needed)

```bash
docker compose up --build
```

Open http://localhost:5173. Same mock-mode-by-default behavior as above, no local Python or
Node required — just Docker. Candidate/resume data persists in a named Docker volume across
restarts (`docker compose down` keeps it; add `-v` to wipe it). To use a real LLM instead of
mock mode, set `OPENROUTER_API_KEY` (and `USE_MOCK=false`) in your shell before running, or in
a `.env` file at the repo root — see [architecture/getting-started.md](architecture/getting-started.md).
Real email OAuth (Gmail/Outlook) needs a system keyring, which isn't set up in the container by
default — folder scanning and mock-mode email scanning both work fully containerized.

See **[HOW_TO_RUN.md](HOW_TO_RUN.md)** for a step-by-step run/test walkthrough, or
[architecture/getting-started.md](architecture/getting-started.md) for enabling real LLM
scoring (OpenRouter/OpenAI) and email scanning (Gmail/Outlook OAuth).

## What it does

- **Job Descriptions** — the operational hub: add, search, and paginate any number of roles; set typed criteria and trigger scan/rescan per job.
- **Scan Sources** — scan local resume folders (with subfolders) and/or connected mailboxes,
  over a chosen date range. Both work independently or together; email resumes are also
  mirrored to local disk so they're browsable offline.
- **Candidate Results** — LLM-scored matches, color-coded by tier (great/good/average/poor,
  plus red-flagged), with match reasons, missing-info flags, and green/red flagging.
- **Criteria** — built-in job-board-standard filters plus custom criteria, with a rescan
  option (use existing data, or fully re-ingest sources).
- **Draft Email** — generates outreach email drafts from a match, checking required fields
  (legal name, employment status, work visa status) are present first.
- **Search History**, **Email Access**, **Connection Setup** (local-only today, cloud/company
  server is the next phase), **Screening Sources**.

See [architecture/README.md](architecture/README.md) for the full documentation set,
including the ADRs behind every major decision.

## Repo layout

```
recruit-assistant/
├── architecture/    # docs — start here
├── backend/         # FastAPI app
├── frontend/        # React + Vite SPA
├── data/            # gitignored — SQLite db + candidate/resume mirror
└── scripts/         # setup.sh, run_all.sh, check_health.sh
```

## Commands

```bash
make setup            # install backend deps, create .env
make run               # start the backend
make test              # backend unit + golden-set regression tests
make health             # check backend health
make install-frontend  # npm install
make run-frontend       # start Vite dev server
make build-frontend     # production frontend build
make lint               # ruff
make clean              # remove caches/build artifacts
```

## License

All rights reserved — see [LICENSE](LICENSE). See also [SECURITY.md](SECURITY.md) for how
candidate data and credentials are handled.
