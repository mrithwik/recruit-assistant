<!-- Version: v0 | Last updated: 2026-08-01 | Status: current -->

# API Reference

Base URL: `http://localhost:8000/api/v1` (proxied from the frontend dev server at `/api/v1`).

## Jobs

| Method | Path | Notes |
|---|---|---|
| GET | `/jobs` | List all jobs, newest first |
| POST | `/jobs` | `{title, raw_text}` — 400 if 10 active jobs already exist |
| DELETE | `/jobs/{id}` | Deactivates (soft), doesn't delete history/matches |

## Scan

| Method | Path | Notes |
|---|---|---|
| POST | `/scan/folders` | `{folder_paths, include_subfolders, date_start?, date_end?}` |
| POST | `/scan/email-accounts` | `{account_ids, date_start?, date_end?}` — mirrors resumes to disk |

Both return `ScanResult {resumes_found, candidates_created, candidates_updated, errors[]}`.

## Candidates

| Method | Path | Notes |
|---|---|---|
| GET | `/candidates?date_start=&date_end=&source=` | `source` is `email`\|`folder`, omit for both |

## Matches

| Method | Path | Notes |
|---|---|---|
| POST | `/matches/run/{job_id}?top_n=20` | Runs two-stage matching + judge, persists results |
| GET | `/matches/{job_id}?top_n=20` | Latest persisted matches for a job |
| POST | `/matches/{match_id}/flag` | `{color: "green"\|"red", note}` — red flag forces tier to `red_flagged` |

## Criteria

| Method | Path | Notes |
|---|---|---|
| GET | `/criteria?job_id=` | Built-in criteria (job_id null) + this job's custom ones |
| POST | `/criteria` | `{name, description, weight, job_id?}` — bumps job's criteria_version |
| POST | `/criteria/rescan` | `{job_id, mode: "existing_data"\|"full_rescan"}` |

## History

| Method | Path | Notes |
|---|---|---|
| GET | `/history?job_id=` | Search runs, newest first |

## Draft email

| Method | Path | Notes |
|---|---|---|
| POST | `/draft-email` | `{match_id}` → `{subject, body, missing_required_fields[]}` |

## Email accounts

| Method | Path | Notes |
|---|---|---|
| GET | `/email-accounts` | Connected accounts |
| GET | `/email-accounts/connect/google` | Redirects into Google OAuth consent |
| GET | `/email-accounts/callback/google` | OAuth redirect target, stores token in keychain |
| GET | `/email-accounts/connect/microsoft` | Redirects into Microsoft OAuth consent |
| GET | `/email-accounts/callback/microsoft` | OAuth redirect target |
| DELETE | `/email-accounts/{id}` | Disconnects + purges keychain token |

## Health

`GET /health` → `{"status": "ok"}`
