<!-- Version: v0 | Last updated: 2026-08-01 | Status: current -->

# Infrastructure

## Local run (current)

- Backend: one `uvicorn` process, `make run` (from `backend/`), port 8000.
- Frontend: Vite dev server, `make run-frontend`, port 5173, proxies `/api` and `/health` to
  the backend.
- Storage: SQLite file at `DATA_DIR/recruit_assistant.db`; resume/summary mirror under
  `DATA_DIR/candidates/`. `DATA_DIR` defaults to `./data`, created automatically.
- Secrets: OAuth tokens in the OS keychain via `keyring`; LLM API keys in `.env` (gitignored).

## Path to production

Every "local now" piece was built behind an interface specifically so this doesn't require a
rewrite:

| Local piece | Production swap | Interface |
|---|---|---|
| SQLite | Postgres | `BaseStorageBackend` — new implementation, same methods |
| Local file mirror | S3 / equivalent | Extend `BaseStorageBackend` or a parallel file-storage interface |
| Single FastAPI process | Split services (gateway/scanning/matching) | Each `app/*` module already has clean boundaries via DI |
| OS keychain | Managed secrets (Vault, cloud secret manager) | `email_auth/oauth.py`'s `store_token`/`load_token` — swap the two functions |
| In-process scan on demand | APScheduler off-hours jobs (Phase 2) or a real task queue | `scanning/ingest_service.run_scan()` is already a standalone async function, callable from a scheduler or worker |

`backend/Dockerfile` (to be added alongside the service split) and containerized deployment
are Phase 2+, tracked in the plan's roadmap — not needed for a recruiter running this
locally today.

## Backups

Since everything lives under `data/`, backing up the app is copying that directory (or
pointing `DATA_DIR` at a synced/backed-up location). The candidate mirror under
`data/candidates/` is plain files — human-readable and portable independent of the app.
