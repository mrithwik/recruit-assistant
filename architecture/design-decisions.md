<!-- Version: v0 | Last updated: 2026-09-01 | Status: current -->

# Design Decisions — Architecture Decision Records (ADRs)

Format: Context, Decision, Alternatives Considered, Consequences.

---

## ADR-001: Single FastAPI Process, Modular Internally (not Prodigon's multi-service split)

**Context:** Prodigon (the reference project) splits into gateway/model/worker services.
Recruit Assistant runs on a recruiter's laptop, not a deployed platform.

**Decision:** One FastAPI app. Internal modules (`scanning/`, `matching/`, `storage/`,
`criteria/`, `email_auth/`, `email_draft/`) keep clean boundaries via `dependencies.py`
DI getters, the same pattern Prodigon uses for its service layer.

**Alternatives Considered:** Multi-service like Prodigon — more moving parts to run locally
(multiple uvicorn processes) with no benefit at single-user, single-machine scale.

**Consequences:** `make run` starts one process. Any module can become its own service later
(the DI + interface boundaries are already in place) without a rewrite — see ADR-002 and
ADR-003 for the two interfaces designed with that split in mind.

---

## ADR-002: BaseStorageBackend — Local Now, Cloud/Company-Server Later

**Context:** Requirement: local storage now, with an explicit path to company server / cloud
later, without a rewrite.

**Decision:** `BaseStorageBackend` ABC (`storage/base.py`); `LocalStorageBackend`
(`storage/local.py`) is the only implementation today — SQLite via SQLAlchemy for structured
data, plus a local file mirror (`scanning/mirror_writer.py`) for resumes and summaries.

**Alternatives Considered:** Direct SQLite calls scattered through routes — would couple
every route to "local" and make a future cloud swap a rewrite, not a swap.

**Consequences:** Adding a `CloudStorageBackend` later is one new class implementing the
same interface; callers (routes, ingest_service) don't change. Mirrors Prodigon ADR-003's
`BaseQueue` pattern exactly.

---

## ADR-003: One ResumeIngestor Interface for Both Email and Folders

**Context:** The user explicitly corrected an earlier draft of this plan: email and folder
scanning must both work from day one — a recruiter may have no local resumes at all yet, so
email can be the *only* source. They must also converge into one deduplicated candidate pool
searchable by submission date regardless of origin.

**Decision:** `ResumeIngestor` ABC (`scanning/ingestor_base.py`) with `FolderIngestor` and
`GmailIngestor`/`OutlookIngestor` (+ `MockEmailIngestor`) implementations, all yielding the
same `IngestedResume` shape. `scanning/ingest_service.py` runs one orchestration function
(parse → identity resolution → mirror-to-disk → persist) for either source.

**Alternatives Considered:** Separate code paths for email vs. folder ingestion — would
duplicate parsing/identity/mirroring logic and risk the two sources drifting into different
candidate representations, defeating the "one merged profile" requirement.

**Consequences:** Adding a new source (LinkedIn export, ATS integration — see
[Screening Sources](../architecture/system-overview.md)) is one new `ResumeIngestor`
implementation, not a pipeline rewrite.

---

## ADR-004: Email Ingestion Mirrors to Local Disk at Ingest Time

**Context:** Requirement: recruiter must be able to browse scanned emails as plain files,
and the system should work with no internet connectivity once a scan has run.

**Decision:** `scanning/mirror_writer.py` writes every ingested resume (regardless of
origin) to `data/candidates/<job-slug>/<date-submitted>/<candidate-slug>/` — the resume
file, an LLM-generated `profile_summary.md`, and a `meta.json` sidecar — at ingest time, not
lazily.

**Alternatives Considered:** Store only a reference to the email (message ID) and re-fetch
on demand — fails offline, and re-fetching on every view is slower and burns API quota.

**Consequences:** Folder-scanned and email-scanned resumes land in the identical on-disk
shape, which is also what makes ADR-003's single ingestor interface clean — both sources
produce something with the same downstream footprint.

---

## ADR-005: Identity Resolution — Source-Agnostic Candidate Profiles

**Context:** The same person may be seen via email today and a folder-dropped resume next
week (or vice versa). They must merge into one profile, not two, and `date_submitted` must
be filterable uniformly regardless of source.

**Decision:** `scanning/identity_resolution.py` computes a fingerprint (email address,
falling back to normalized name+phone) before every candidate create/update. New info
merges into the existing profile (skills union, non-blank field wins) rather than
overwriting or duplicating.

**Alternatives Considered:** Dedupe by file hash only — misses the actual requirement (same
person, different resume version/file); dedupe by source — defeats the point entirely, since
folder and email are supposed to converge.

**Consequences:** `ResumeSource` rows (not `Candidate` rows) record per-ingest history, so a
candidate can have multiple sources while the app still shows one profile.

---

## ADR-006: Two-Stage Matching + LLM-as-Judge

**Context:** Requirement 7: use LLMs for search quality, with LLM-as-judge and a way to
"reiterate the scan as needed," while staying fast/cheap enough to run over an entire
candidate pool.

**Decision:** `matching/matcher.py` — (1) embedding cosine-similarity pre-filter over the
full pool (cheap, no LLM call), (2) deep LLM scoring on the shortlist only, (3) a judge pass
(`matching/prompts.py` `JUDGE_PROMPT`) reviewing borderline scores (40-70) that can correct
the score.

**Alternatives Considered:** Score every candidate with a full LLM call — correct but slow
and expensive at scale; single-stage scoring with no judge — cheaper but requirement 7
explicitly asks for LLM-as-judge iteration.

**Consequences:** Cost/latency bounded by the shortlist size (`top_n * 3` by default), while
still using LLM judgment on the results that matter (borderline calls). Golden-set
regression tests (`backend/tests/golden/`) are the gate for prompt/model changes here.

---

## ADR-007: OpenRouter Primary / OpenAI Fallback via One LLMClient Abstraction

**Context:** User has both OpenRouter and OpenAI keys and wants "whichever method works
best."

**Decision:** `matching/llm_client.py` — `LLMClient` ABC, `OpenRouterClient` as primary
(model routing/fallback/cost visibility across providers from one integration),
`OpenAIClient` as a direct fallback if OpenRouter fails, `MockLLMClient` for `USE_MOCK_LLM=true`
(wrapped by `DispatcherLLMClient`, which routes to mock or real per-call based on the live
runtime flag — see app/runtime_settings.py — so the UI's mock/real toggle takes effect without
a backend restart).

**Alternatives Considered:** OpenAI-only — loses OpenRouter's model flexibility (different
models for triage/scoring/judge) and cross-provider fallback; hardcoding both SDKs into
every call site — couples every consumer to provider details.

**Consequences:** Adding a third provider (e.g. direct Anthropic) is one new adapter class.

---

## ADR-008: Pydantic Settings for Configuration (mirrors Prodigon ADR-006)

**Context:** All config (LLM keys, OAuth client IDs, data paths, mock mode) needs
type-validated, 12-factor, fail-fast configuration.

**Decision:** `app/config.py` — a single `Settings(BaseSettings)` class, env-driven,
`USE_MOCK_LLM=true` / `USE_MOCK_EMAIL=true` by default so the app runs fully offline out of
the box. These two are also live-toggleable at runtime (see `app/runtime_settings.py`) since
unlike the rest of Settings they need to be flippable from the UI without a restart.

**Consequences:** Same pattern as Prodigon, same benefit: bad config fails at startup with a
clear error, not a runtime surprise mid-scan.

---

## ADR-009: Credentials via OS Keychain, Never in DB or Config File

**Context:** Requirement 2.3 explicitly calls out "associated safeguards" for email access.

**Decision:** `email_auth/oauth.py` stores OAuth tokens via the `keyring` library (macOS
Keychain / Windows Credential Manager / Linux Secret Service). The `EmailAccount` SQLite row
holds only a `keychain_ref`, never the token.

**Alternatives Considered:** Store tokens in `.env` or the SQLite DB — both are plaintext-ish
and get backed up/synced/shared far more casually than an OS credential store.

**Consequences:** Disconnecting an account (`DELETE /email-accounts/{id}`) also purges the
keychain entry — no orphaned credentials.

---

## ADR-010: Bind to Localhost by Default, Rate-Limit Login In-Process

**Context:** A four-perspective stakeholder review (`reports/stakeholder-review.md`) found the
backend listening on `0.0.0.0` by default despite being documented as local-first, and no
throttling on `POST /auth/login` — both real findings, scoped explicitly to the confirmed
deployment model of one instance per recruiter's own laptop, not a shared server.

**Decision:** `.env.example` sets `API_HOST=127.0.0.1`. Login attempts are throttled by
`app/auth/rate_limit.py` — an in-memory, per-process, per-email counter (5 failures → 15-minute
lockout), identical response shape for a locked-out real email and a nonexistent one.

**Alternatives Considered:** A Redis-backed rate limiter — real overkill for a single-process
app with one possible account; per-IP throttling instead of per-email — less meaningful when
the whole point is one trusted operator on one machine, and per-email is what actually stops
credential-stuffing against the one account that exists.

**Consequences:** Rate-limit state doesn't survive a restart (acceptable — an attacker who can
restart the process already has more access than the lockout was protecting against). Mirrors
the existing `job_registry.py` module-global pattern (ADR mirrors the in-memory scan-job
registry already established elsewhere in this codebase) rather than introducing a new
persistence mechanism for state that's fine to lose.

---

## ADR-011: Pipeline Stage Lives on `Match`, Not a New Table or `Candidate`

**Context:** The stakeholder review's top recruiter-facing gap: the app tracks match
*quality* (`tier`) but not process *status* (sourced → screened → submitted → interviewing →
offer → placed/declined) — the single most-used view in any ATS, per the review.

**Decision:** `PipelineStage` enum, mirroring the existing `MatchTier` pattern exactly, added
as a plain column on `Match` — the same row `tier`/`flags`/`judge_notes` already live on.
Defaults to `sourced`, free-form transitions (no enforced state machine), auto-migrated via
the existing schema-driven `_add_missing_columns`.

**Alternatives Considered:** A new `PipelineEvent`/history table — richer (a timeline of every
transition) but unrequested and unbuilt-toward; a column on `Candidate` instead of `Match` —
wrong shape entirely, since stage is inherently per-job (a candidate can be "interviewing" for
one role and merely "sourced," never acted on, for another) and `Candidate` has no per-job
scope to hang it on.

**Consequences:** Zero new tables, zero new migration machinery — the feature is exactly as
expensive to add as any other column this project has added before it (`recruiter_notes`,
`last_scanned_at`, etc.), and existing rows backfill to `sourced` with no manual step.

---

## ADR-012: Per-Candidate Delete Is a Real Delete, Not a Soft-Delete

**Context:** The only existing deletion path (`dev_tools.clear_data`, the "danger zone") wipes
every job/candidate/match in the database — no way to honor one person's actual
right-to-erasure request without destroying everyone else's data too.

**Decision:** `DELETE /candidates/{id}` performs a genuine, irreversible delete — the DB row
via `session.delete()` (cascading to `Match`/`ResumeSource` through the ORM's existing
`delete-orphan` relationships), plus the on-disk mirror files (resume, summary, meta),
verified against `meta.json`'s own `candidate_id` before anything is touched, and removed by
exact filename — never an `rmtree`. No Undo affordance on the frontend, unlike the existing
job-deletion and note-deletion Undo patterns.

**Alternatives Considered:** Soft-delete (mirroring `Job.active=False`) — the pattern this
project already uses elsewhere, but wrong here: the entire premise is real erasure, and a
soft-deleted row with real PII still sitting in the database and on disk doesn't satisfy that;
an Undo-toast (mirroring note deletion) — same problem, an "undo" only makes sense when
nothing was actually destroyed yet.

**Consequences:** No recovery path if triggered by mistake — the typed `"DELETE"`
confirmation (mirroring the existing danger-zone pattern) is the only safeguard, deliberately,
since a real safety net here would contradict the feature's purpose. QA caught a real gap in
the on-disk cleanup on first pass (two same-day submissions sharing one mirror directory) —
see project log section 37 — now covered by a regression test.

---

## ADR-013: Real-LLM Consent Persists on `User`, Not `runtime_settings`

**Context:** Switching mock LLM mode off sends full resume text and job descriptions to a
third-party API (OpenRouter/OpenAI) with no acknowledgment step — flagged by the stakeholder
review as a real gap independent of the multi-tenancy question.

**Decision:** New `User.real_llm_consent_given_at` (nullable `datetime`), set once via `PATCH
/settings/mock-mode`'s `consent_ack: true` and never re-checked afterward. A new
`LlmConsentModal` intercepts the frontend toggle before the API call fires, the first time.

**Alternatives Considered:** Storing consent in `app/runtime_settings.py` alongside the
mock/real flags themselves — wrong on purpose: that module is deliberately in-memory-only (see
ADR-008), so the mock/real toggle resets to mock on every backend restart by design, but
re-asking for a one-time consent acknowledgment on every restart would be actively
user-hostile, not merely inconsistent with the toggle's own reset behavior.

**Consequences:** The two states now deliberately diverge across a restart — `use_mock_llm`
resets, `real_llm_consent_given` doesn't — which is the correct behavior, not a bug, and is
covered by a test that restarts the backend process and asserts exactly that split.

---

## Cross-References

- [Backend Architecture](backend-architecture.md)
- [Frontend Architecture](frontend-architecture.md)
- [System Overview](system-overview.md)
