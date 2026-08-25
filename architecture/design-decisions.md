<!-- Version: v0 | Last updated: 2026-08-01 | Status: current -->

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
`OpenAIClient` as a direct fallback if OpenRouter fails, `MockLLMClient` for `USE_MOCK=true`.

**Alternatives Considered:** OpenAI-only — loses OpenRouter's model flexibility (different
models for triage/scoring/judge) and cross-provider fallback; hardcoding both SDKs into
every call site — couples every consumer to provider details.

**Consequences:** Adding a third provider (e.g. direct Anthropic) is one new adapter class.

---

## ADR-008: Pydantic Settings for Configuration (mirrors Prodigon ADR-006)

**Context:** All config (LLM keys, OAuth client IDs, data paths, mock mode) needs
type-validated, 12-factor, fail-fast configuration.

**Decision:** `app/config.py` — a single `Settings(BaseSettings)` class, env-driven,
`USE_MOCK=true` by default so the app runs fully offline out of the box.

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

## Cross-References

- [Backend Architecture](backend-architecture.md)
- [Frontend Architecture](frontend-architecture.md)
- [System Overview](system-overview.md)
