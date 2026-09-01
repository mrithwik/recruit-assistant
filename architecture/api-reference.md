<!-- Version: v0 | Last updated: 2026-09-01 | Status: current -->

# API Reference

Base URL: `http://localhost:8000/api/v1` (proxied from the frontend dev server at `/api/v1`).
All routes except `GET /health` and the `auth` routes below require `Authorization: Bearer
<token>` — see [Auth](#auth).

## Auth

| Method | Path | Notes |
|---|---|---|
| GET | `/auth/status` | `{setup_complete}` — whether the one account has been created yet |
| POST | `/auth/register` | `{email, password}` → session token. 403s once any account exists — single-account by design, not a bug |
| POST | `/auth/login` | `{email, password}` → session token. Rate-limited: 5 failed attempts locks that email for 15 minutes, identical response for a locked-out real email vs. a nonexistent one |
| GET | `/auth/me` | Current user from the bearer token |

## Jobs

| Method | Path | Notes |
|---|---|---|
| GET | `/jobs` | List active jobs, newest first |
| GET | `/jobs/inactive` | List soft-deleted jobs |
| POST | `/jobs` | `{title, company, raw_text}` — 400 if 10 active jobs already exist |
| DELETE | `/jobs/{id}` | Soft-delete (`active = false`) — doesn't touch matches/history |
| POST | `/jobs/{id}/reactivate` | Undoes a soft-delete |
| POST | `/jobs/bulk-delete` | `{job_ids}` — same soft-delete, bulk |

## Scan

| Method | Path | Notes |
|---|---|---|
| POST | `/scan/folders` | `{folder_paths, include_subfolders, date_start?, date_end?}` — backgrounded job |
| POST | `/scan/email-accounts` | `{account_ids, date_start?, date_end?}` — mirrors resumes to disk |
| POST | `/scan/all` | Scans every connected source (folders + all email accounts) in one job |
| GET | `/scan/logs` | Per-scan ingest log entries |
| GET | `/scan/jobs/{job_id}` | Poll a backgrounded scan job's status/progress |
| POST | `/scan/jobs/{job_id}/cancel` | Cooperative cancel — finishes the in-flight resume, stops before the next |

All scan endpoints return/poll to a `ScanResult {resumes_found, candidates_created,
candidates_updated, duplicates_skipped, errors[]}`.

## Candidates

| Method | Path | Notes |
|---|---|---|
| GET | `/candidates` | Filterable: skills, employment status, work visa status, experience range, date range, `data_mode` (`all`\|`real`\|`mock`) |
| GET | `/candidates/facets` | Distinct filter values for the current pool |
| GET | `/candidates/data-mode-counts` | `{real, mock, total}` for the header's All/Real/Mock toggle |
| GET | `/candidates/export` / `/export-selected` | CSV export, all-filtered or a specific id list |
| GET | `/candidates/{id}` | Full detail incl. per-job match list (`CandidateMatchDetail`, includes `pipeline_stage`) |
| DELETE | `/candidates/{id}` | **Real, irreversible** delete — DB rows (cascading) + on-disk mirror files. Not a soft-delete; see ADR-012 |
| POST | `/candidates/{id}/notes` | `{text}` — free-text recruiter note, independent of any one job |
| DELETE | `/candidates/{id}/notes/{note_id}` | |
| GET | `/candidates/{id}/sources` | This candidate's `ResumeSource` rows |
| GET | `/candidates/{id}/sources/{source_id}/file` | Download the original resume file |
| GET | `/candidates/{id}/sources/{source_id}/text` | Extracted plain text |
| POST | `/candidates/{id}/rescan` | "Check for updates" — sender-scoped, re-ingests just this person's messages |

## Matches

| Method | Path | Notes |
|---|---|---|
| POST | `/matches/run/{job_id}?top_n=20` | Backgrounded: embed → similarity pre-filter → deep LLM score (shortlist) → judge (borderline) |
| GET | `/matches/{job_id}?top_n=20` | Latest persisted matches for a job |
| GET | `/matches/summary/{job_id}` | Lightweight tier counts + top 3, for the Jobs page |
| POST | `/matches/{match_id}/flag` | `{color: "green"\|"red", note}` — red forces tier to `red_flagged` |
| POST | `/matches/{match_id}/stage` | `{stage}` — one of `PipelineStage`'s 7 values, free-form transition |
| POST | `/matches/{job_id}/rescan-matched` | "Check for updates," bounded to this job's already-matched candidates |

## Criteria

| Method | Path | Notes |
|---|---|---|
| GET | `/criteria?job_id=` | Built-in criteria (job_id null) + this job's custom ones |
| POST | `/criteria` | `{name, description, weight, job_id?, field_type, options?}` |
| GET | `/criteria/for-job/{job_id}` | This job's selected criteria + values |
| PUT | `/criteria/for-job/{job_id}/{criterion_id}` | Enable/disable/set value — bumps `Job.criteria_version` |
| POST | `/criteria/rescan` | `{job_id, mode: "existing_data"\|"full_rescan"}` |

## Dashboard

| Method | Path | Notes |
|---|---|---|
| GET | `/dashboard/summary` | KPIs, inflow trend, tier + pipeline-stage distributions, top skills, visa breakdown, jobs snapshot, recent activity — accepts `data_mode` |
| GET | `/dashboard/activity` | Paginated activity log ("see more" beyond the summary's top 10) |

## Settings

| Method | Path | Notes |
|---|---|---|
| GET | `/settings/mock-mode` | `{use_mock_llm, use_mock_email, real_llm_available, expose_toggle, real_llm_consent_given}` |
| PATCH | `/settings/mock-mode` | `{use_mock_llm?, use_mock_email?, consent_ack?}` — flipping to real LLM mode without prior consent 428s unless `consent_ack: true` is sent; see ADR-013 |

## Email accounts

| Method | Path | Notes |
|---|---|---|
| GET | `/email-accounts` | Connected accounts |
| GET | `/email-accounts/oauth-status` | Whether Google/Microsoft OAuth apps are registered in `.env` |
| GET | `/email-accounts/connect/google` \| `/connect/microsoft` | Redirects into OAuth consent |
| GET | `/email-accounts/callback/google` \| `/callback/microsoft` | OAuth redirect target, stores token via OS keychain |
| DELETE | `/email-accounts/{id}` | Disconnects + purges the keychain token |

## Scheduled sources

| Method | Path | Notes |
|---|---|---|
| GET | `/scheduled-sources` | Folders/mailboxes opted into the nightly off-hours scan |
| POST | `/scheduled-sources` | `{kind: "folder"\|"email_account", ref, include_subfolders?}` |
| DELETE | `/scheduled-sources/{id}` | |

## Maintenance

| Method | Path | Notes |
|---|---|---|
| GET | `/maintenance/tasks` | Registered backfill tasks + pending-item counts |
| POST | `/maintenance/tasks/{task_id}/run` | Backgrounded — reuses the scan-job registry |

## Draft email

| Method | Path | Notes |
|---|---|---|
| POST | `/draft-email` | `{match_id}` → `{subject, body, missing_required_fields[]}` |

## History

| Method | Path | Notes |
|---|---|---|
| GET | `/history?job_id=` | Search runs, newest first |

## Dev tools

| Method | Path | Notes |
|---|---|---|
| POST | `/dev-tools/generate-sample-data` | In-app sample-data generation, same generator as `scripts/generate_sample_data.py` |
| POST | `/dev-tools/clear-data` | Wipes every job/candidate/match/criterion/email-account — typed-confirmation gated on the frontend. Does **not** delete on-disk mirror files (a known gap, distinct from `DELETE /candidates/{id}`'s real cleanup — see ADR-012) |

## Health

`GET /health` → `{"status": "ok"}` — unauthenticated, used for liveness checks and by
`scripts/run_all.sh`'s startup verification.
