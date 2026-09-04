<!-- Version: v0 | Last updated: 2026-09-01 | Status: current -->

# Project Log

A chronological record of every planning decision and build phase on this project, so a
future session (human or AI) can pick up context without re-deriving it. For *why* each
architecture choice was made, see [Design Decisions](design-decisions.md) (ADRs); this file
is the narrative timeline connecting them.

## 1. Origin — researching Prodigon, then planning Phase 1

Before writing any code, [Prodigon](../../prodigon) (a teaching-grade multi-service FastAPI +
React platform at `~/projects/prodigon`) was read in depth as a structural reference: its
`architecture/` doc set, ADR-driven decisions, `shared/` config module, Pydantic Settings
pattern, and Makefile-as-command-surface. Recruit Assistant deliberately reuses those
conventions but **not** Prodigon's multi-service topology — see ADR-001.

The initial plan (built via `EnterPlanMode`, since the user explicitly asked for one) scoped
folder-scanning first and email second. **The user corrected this**: a recruiter may have no
local resume data at all yet, so email can be the *only* source from day one — folder and
email scanning had to ship together in Phase 1, both first-class, converging on one
identity-resolved, source-agnostic candidate pool. This correction shaped the whole ingestion
architecture (`ResumeIngestor` interface, `identity_resolution.py`, `mirror_writer.py` — see
ADR-003/004/005).

## 2. Phase 1 MVP build

Built in one pass: single FastAPI backend (`backend/app/`) with `scanning/` (folder + email
ingestion, parser, identity resolution, disk mirror), `matching/` (two-stage LLM scoring +
judge, OpenRouter primary / OpenAI fallback), `criteria/`, `email_draft/`, `email_auth/`
(OAuth + OS keychain), `storage/` (SQLite behind a swappable `BaseStorageBackend`); and a
React/Vite/Zustand/Tailwind frontend with all 8 nav tabs. Verified end-to-end in mock mode
(zero API keys) with a real browser session, not just unit tests. Golden-set regression tests
added for the matching pipeline (`backend/tests/golden/`).

## 3. UI redesign

First pass was functionally complete but visually flat ("doesn't look very pleasing"). Rebuilt
around a proper design system: `components/ui/` primitives (Button, Card, Input, EmptyState,
PageHeader), Inter/Lexend fonts, a `zinc` neutral scale, tinted match-tier badges, `lucide-react`
icons throughout. Verified visually via Playwright screenshots (installed since `chromium-cli`
wasn't available in this environment), in both light and dark mode.

Follow-up: removed the top dropdown nav per user request ("the side panel is plenty") — sidebar
is now the sole navigation surface; header keeps a breadcrumb-style page label.

## 4. Auth + landing page

Added: a public marketing landing page (`/`), and real local auth — first-run account creation
(locked after the first account exists, so `/auth/register` isn't an open door if ever exposed
beyond localhost), PBKDF2 password hashing and HMAC-signed session tokens (both stdlib-only, no
bcrypt/PyJWT dependency), every API route protected except `/health` and `/auth/*`. Mid-task,
user asked for "keep me signed in" — added a `remember` flag with two session TTLs
(30-day / 12-hour) rather than a separate persistence mechanism, since the token already lives
in `localStorage` either way.

## 5. Personal dashboard

Requested with explicit emphasis: "plan in depth", "in depth research", "very visual". Response
mapped standard ATS-dashboard pillars (Greenhouse/Lever/LinkedIn Recruiter patterns) onto what
the data model actually supports, then built `GET /api/v1/dashboard/summary` (one aggregated
call) + a `dashboard-page.tsx` with Recharts: candidate inflow (stacked area), match-quality
distribution (ordinal bars), top skills / work-authorization (ranked bars), jobs snapshot,
needs-attention queue, recent activity. Became the new post-login landing route.

The `dataviz` skill was loaded and its palette **validator script was actually run** (not
eyeballed) for every color choice — categorical pair, 4-step ordinal ramp — both passed CVD
safety checks in light and dark mode. Caught and fixed a real Recharts bug this way: its
auto-tick algorithm produced non-monotonic Y-axis labels on small integer ranges; fixed with
explicit clean tick generation, confirmed via the DOM (not the screenshot — anti-aliased tick
text at that size is genuinely hard to eyeball, and was misread twice before checking the DOM).

## 6. Sample dataset generator

Needed to test the app at realistic volume. Built `scripts/generate_sample_data.py`: 2,050
synthetic items (1,600 applications + 450 follow-ups) across a 2-year date spread, 12 writing
personas, ~30% deliberately incomplete/garbled, output both as a folder-scan tree (file mtimes
set to match synthetic dates) and an `emails_manifest.json` consumed by a new
`MOCK_EMAIL_FIXTURES_PATH` setting (auto-seeds a `demo@mock.local` mailbox in mock mode, so
"Scan email" is testable with zero OAuth).

Running it at scale exposed that `MockLLMClient` returned one fixed canned profile for every
resume — all the generated variety was invisible. Fixed by giving the mock client real
regex-based extraction from the actual resume text (name, skills-by-keyword, visa/status
lines) — verified live: skills and visa distributions became genuinely varied across 1,660
candidates. That fix itself had a bug (substring match: "go" matched inside "Google
Analytics") — fixed with word-boundary regex. Also fixed a `.strip()` bug producing bare
"Added" text in the dashboard's recent-activity feed for nameless candidates. All caught by
actually running a full scan against the generated dataset, not by code review.

## 7. Job Descriptions as the operational hub, typed per-job criteria, candidate history

A batch request landed with 8 items at once, several of which turned out to reshape the same
area of the app, so they were done together: uncapped/searchable/paginated (10/page) Job
Descriptions with individual and bulk delete; a criteria *library* (`Criterion`, extended with
`field_type`/`options` — text/number/boolean/select) separately selectable per job
(`JobCriterion`), rendered as the right control per type; a "Scan & match" panel embedded
directly on each job card (existing-data vs. re-scan-sources, reusing whatever's configured
on Scan Sources rather than requiring a trip to that tab); and a sidebar regrouping into
**Workflow** (Dashboard, Jobs, Results, History) vs **Settings & Sources** (everything
configured once and left alone) — this is what resolved "where do I even start," since Job
Descriptions is now genuinely the hub the user asked for, not just a list.

Also added in the same pass: a dated candidate-history timeline (`Candidate.history`) —
built at ingest time, one entry per submission, always re-sorted by date since ingestion
order isn't guaranteed chronological. Two real bugs surfaced only by actually running it
against the generated dataset: (1) resumes with *no* extractable name/email/phone all
collapsed onto the same empty-string identity fingerprint, silently merging unrelated
people — fixed by falling back to a random per-resume fingerprint when there's truly nothing
to identify against; (2) the "Initial application" vs "Updated" label was derived from
ingestion order (`is_new`), which doesn't match calendar order when a later-dated resume
happens to be processed first (e.g. an upskill resubmission scanned before the original) —
fixed by deriving the label from sort position after sorting, not from ingestion order.

The sample-data generator was extended to match: date spread widened from 2 to 10 years,
and a new "upskill journey" mode makes ~1,400 candidates resubmit 1-3 more times over
subsequent years with more experience and added skills — a real test of the history
timeline, not just synthetic volume. Default CLI/API counts now produce 10,000+ items
total. The generator itself moved from `scripts/` into `backend/app/dev_tools/` so a new
in-app "Generate sample data" panel (Scan Sources tab) can call the identical code — no
terminal required, with presets (Small/Medium/Large) and a default output path that
automatically matches whatever `MOCK_EMAIL_FIXTURES_PATH` is already configured to, so a
generate click "just works" with the mock email scan with no `.env` edit.

## 8. Usability pass — after using the app at real volume

Running the app end-to-end (not just testing individual features) surfaced a batch of
friction points and two real bugs, addressed together:

**Bugs fixed:**
- The mock LLM's *scoring* prompt (as opposed to the extraction prompt, fixed earlier) was
  still returning one hardcoded `{"score": 72, ...}` for every candidate — every match looked
  identical regardless of fit. `_mock_score_match()` now does real regex-based skill-overlap
  scoring against the job text (same `_SKILL_VOCAB` used for extraction), so scores and
  matched/gap reasons vary by candidate even in mock mode. The mock judge prompt was also
  silently mismatched (wrong JSON shape), fixed to return a proper `{agrees, corrected_score,
  judge_notes}` structure.
- Generated sample data wasn't reliably scannable: the in-app generator's `result` was
  component-local `useState`, lost on navigating away from Scan Sources and back; separately,
  the mock mailbox EmailAccount row was only seeded at backend *startup*, so generating data
  after startup (the normal flow) left no way to scan it as email without a restart, and if
  `MOCK_EMAIL_FIXTURES_PATH` was never set the email scan endpoint read from an empty path
  entirely. Fixed by moving generator state into `scan-store` (now `zustand/persist`-backed,
  survives navigation and reloads), seeding the demo mailbox right after a successful generate
  call, and falling back to the same `sample_data/emails_manifest.json` path the generator
  itself defaults to when the env var is unset.
- Dashboard "View" links (Jobs snapshot, Needs attention) went to `/app/results` with no job
  id, so they always landed on whatever job happened to be selected — not the one the card was
  about. Results page now reads a `?job=` query param and both dashboard links pass it.
- `create_job` returned a `DetachedInstanceError` 500 once job creation started seeding
  default criteria in the same request (a second `session.commit()` re-expired the just-loaded
  `Job` object) — fixed with a second `session.refresh()` after the criteria seed.

**New capabilities:**
- Jobs carry a `company` field; the Jobs page search gained an "Advanced" company-filter
  panel (client-side, no backend query needed since the full job list is already loaded).
- New job descriptions auto-seed a sensible default criteria selection (skills, experience,
  location, visa sponsorship enabled with reasonable defaults; education/certs/salary/
  availability present but off) instead of an empty checklist — visible immediately after
  saving via auto-expand.
- Candidates gained `linkedin_url`/`github_url`/`portfolio_url`, extracted deterministically
  (regex, never LLM-guessed) by both the real parser and the mock extractor; the sample-data
  generator now writes these into a majority of "full" synthetic resumes so the feature is
  exercised at volume, not just on one hand-written test file.
- A new candidate detail page (`/app/candidates/:id`) — full profile, clickable
  LinkedIn/GitHub/portfolio links, a `mailto:` link, pipeline standing across every job,
  the full dated history timeline, and every source submission with its mirrored text
  viewable inline (`GET /candidates/{id}/sources`, `.../sources/{id}/text`).
- Job Descriptions cards now show a live "latest results" summary (tier counts, top 3
  candidates, link into the full Results view scoped to that job) via a new
  `GET /matches/summary/{job_id}` endpoint — addresses "results get lost across multiple
  jobs" without moving matching off the Results page.
- The sample-data generator can now be used as a mailbox source with one click (selects the
  seeded `demo@mock.local` account) in addition to a folder source, and has a "Regenerate"
  action that reruns with a fresh random seed.
- Scan Sources was restructured into three numbered steps (source → date range → scan) with
  hover tooltips explaining what each source actually does — it had read as one
  undifferentiated block.
- A shared simulated-progress-bar component (`useSimulatedProgress`) gives scans, matching,
  and generation an ETA readout. It's an honest client-side estimate (elapsed-time easing
  toward 95%, jumping to 100% on completion), not real backend progress — true incremental
  progress would need a streaming endpoint, which is the separate, already-roadmapped
  streaming-results item below.
- Header and sidebar now use a visibly distinct solid background (`zinc-100`/`zinc-900`) from
  the main content canvas (`zinc-50`/`zinc-950`) in both themes — they previously used
  translucent variants of the *same* base color, which was nearly indistinguishable in dark
  mode.
- Login/register inputs carry proper `name`/`autoComplete` attributes so the browser's native
  password manager can offer to save and later autofill credentials — independent of, and in
  addition to, the "keep me signed in" session-length toggle.

## 9. Second usability pass — sharing, comparing, and finding data across jobs

A second round of using the app surfaced navigation and clarity gaps, addressed together:

- Dashboard's "Needs attention" review links, and the Jobs/Attention "View" links, pointed at
  `/app/results` with no way to land on the right job or candidate — `AttentionItem` now
  carries `candidate_id` and links go straight to the candidate detail page; job-scoped links
  carry `?job=`.
- Search History was implicitly filtered by whichever job happened to be selected on the
  Results page (shared global state) — it now always loads every run and has its own job
  filter + text search, independent of that selection.
- Added an "All Candidates" page (`/app/candidates`, paginated 50/page, name/email/skill
  search) reachable from a new nav item and from the dashboard's "Total candidates" tile —
  previously there was no way to browse the whole pool independent of a job. All five
  dashboard stat tiles are now clickable, linking to the page that explains the number.
- Results page: cards can now expand independently (was a single `expanded` id, closing one
  card when opening another); added a multi-select "Compare" flow
  (`components/candidates/candidate-compare-modal.tsx`) — side-by-side skills/experience/
  education/status/matched-gaps table for 2+ selected candidates.
- Added the job's company + posted date near the Results job selector, and a "Scored
  {date}" stamp on every match card and on the candidate detail page's per-job pipeline list
  — previously a card gave no way to tell which company/job it belonged to without switching
  tabs, or when the score was produced.
- `sources` (email/folder badges) were sometimes duplicated (`["email","email","folder"]`)
  since every `ResumeSource` row contributed one raw entry — deduped in `_to_out()`, and
  rendered as small distinct badges (`components/ui/source-badges.tsx`) instead of a
  comma-joined string, so a candidate seen via both channels reads unambiguously as both.
- The simulated scan/generate progress bar used a flat, volume-blind time estimate (a fixed
  guess per source, ignoring how many items were actually being scanned), so a 10,000-item
  scan would sit at 95% "almost done" for a long time — looked hung. It now bases the estimate
  on the last-generated dataset's real item count, and past ~1.5x the estimate the label
  switches to an explicit "still working, large batches take a few minutes" message instead of
  repeating "almost done."
- Scan Sources' date-range picker now shows an explicit "All time (default)" chip when nothing
  is selected, instead of silently scanning everything with no visible indication.
- Added a scroll-to-top button (`components/layout/app-shell.tsx`) that appears after
  scrolling any page, since several pages (All Candidates, Jobs, Results) can get long.
- The per-job "Run" action now distinguishes "no candidate data exists yet" from "ran and
  found nothing," pointing the recruiter at Scan Sources instead of a silent 0-match toast.

**Investigated but not a bug:** a report that email-sourced candidates only showed "folder"
as their origin. Live-tested both scan orders (email-then-folder, folder-then-email, email-
only) — origin tracking is correct; a candidate scanned via both channels does get both
`ResumeSource` rows (deduped by `content_hash` **and** `source_ref`, so the same content from
two different channels is never treated as one duplicate). The actual defect found was the
`sources` duplication/rendering issue above, which is what "add a method to make both visible"
maps onto — fixed via the dedup + badge change.

## Current state (as of this entry)

Phase 1 MVP functional end-to-end: auth, all 8+1 tabs (Dashboard added), Job Descriptions as
the operational hub with per-job criteria and scan/rescan, dashboard, folder + mock-email
ingestion at 10,000+-item scale, matching, dedup, candidate history, in-app + CLI sample-data
tooling, a candidate detail page, and company/link-aware search. 36 backend tests passing.

**Not yet built (roadmap):**
- Real OAuth email at scale — the connect/callback code path exists but has never been
  exercised against a live Gmail/Outlook consent screen (see `getting-started.md`).
- Company/cloud storage backend, off-hours scheduling.
- **Streaming match results** — candidates appearing one-by-one as they're scored, instead of
  waiting for the whole batch. Scoped as a real feature (SSE, mirroring the pattern already
  in Prodigon's ADR-004), not something to squeeze into the batch above.
- **A chat assistant** — natural-language Q&A over existing data first ("how many candidates
  are H1B for the Backend role?"), read-only against the existing API/DB; action-taking
  (trigger scans, add jobs) explicitly deferred past that.
- **Screening for job-opening emails**, not just candidate applications — detecting when an
  inbound email is actually a hiring-manager notification about a new requisition (not a
  resume), and offering to draft a Job Description from it. Requested as an explicit Phase 2
  item; not yet designed.
- **Attitude/culture-fit signal from scanned emails** — evaluating whether an applicant's tone
  in their email/cover note matches the job or team's energy. Explicitly requested as a later
  phase, not now — flagged here so it isn't lost, not designed.

## 10. Third usability pass — collapsibility, activity links, sorting, data safety

- Jobs page and Candidate Results both had per-item expand/collapse (criteria panels, match
  reason panels) with no bulk control — added "Expand all"/"Collapse all" toggles to both.
- Dashboard's Recent Activity items were plain text — `ActivityItem` now carries `job_id`
  (scan/match-run entries) or `candidate_id` (new-candidate entries), and the feed links to
  Search History (now itself `?job=`-linkable, same pattern as Results) or the candidate
  detail page.
- Added sort controls (`components/ui/sort-select.tsx`, reused across pages) — All Candidates
  (recent/oldest/name), Job Descriptions (newest/oldest/title), Candidate Results (best match/
  most recent/oldest/name) — "best match" preserves the backend's native score ordering rather
  than re-sorting client-side.
- Added an explicit, opt-in "Clear all data" action (`DELETE`-equivalent
  `POST /dev-tools/clear-data`, gated behind a typed "CLEAR" confirmation in the UI) as the
  deliberate counterpart to sample-data generation — wipes jobs/candidates/matches/email
  accounts, re-seeds the criteria library, and leaves the user's login and on-disk generated
  files untouched. This is now the *only* way data gets cleared — no code-change or
  restart path should ever silently wipe it (a prior habit of wiping test data between
  verification passes was corrected; see [[feedback-recruit-assistant-workflow]] for the
  process fix — verification now runs against an isolated second backend/frontend instance on
  different ports with its own throwaway SQLite file, never touching the user's running
  instance or database).
- Re-evaluated the Criteria Library page's "Rescan for the selected job" section — it
  duplicated the Jobs page's per-job `JobScanMatchPanel` but keyed off the ambient global
  `selectedJobId`, so it wasn't obvious *which* job it would act on from this page. Replaced
  with a pointer explaining the library/per-job split and linking to Job Descriptions; the
  library's "add custom criterion" now always adds to the global library (`job_id=None`)
  rather than silently scoping to whatever job happened to be selected elsewhere.

## 11. Performance pass — N+1 queries and re-embedding the whole pool every run

Two real, measured bottlenecks, found by reading the query patterns rather than guessing:

**All Candidates was slow: N+1 queries.** `GET /candidates` ran one extra SQL query *per
candidate* to fetch its `ResumeSource` origins (email/folder badges) — 5,159 candidates meant
5,159 extra round trips. Same pattern in `GET /matches/{job}` and `POST /matches/run/{job}`.
Fixed with `_batch_origins()` (`routes/candidates.py`) — one `WHERE candidate_id IN (...)`
query for the whole page, grouped in Python. Measured on a 5,159-candidate pool: **298ms**
end-to-end for the full All Candidates load (was doing the origin lookup as 5,159 separate
queries before).

**Matching re-embedded the entire candidate pool on every single "Run matching" click** —
`POST /matches/run/{job}` called `llm.embed()` for every candidate in the pool, every time,
regardless of whether anything had changed since the last run. Embeddings are now computed
once at ingest time (`scanning/ingest_service.py`, cached on a new `Candidate.embedding`
column) and reused at match time; only candidates ingested before this change (missing a
cached embedding) get embedded on demand, concurrently (`asyncio.gather`), and the result is
persisted so it's never recomputed again. Measured on the same 5,159-candidate pool: matching
completed in **0.43–0.45s** with embeddings cached vs **0.84s** with them forced empty (the
old behavior) — roughly 2x in mock mode, where the embed call itself is a cheap local hash.
The real payoff is with a live embeddings API (OpenRouter/OpenAI): that's a genuine network
round trip per candidate, so the old behavior would have meant thousands of sequential HTTP
calls on every match run — this eliminates that entirely rather than just speeding it up.

**Ingest itself** also ran two SQL queries per resume (`find_candidate_by_fingerprint`,
`find_resume_source_by_hash`) plus a `session.flush()` after every insert. `run_scan` now
preloads both into in-memory dicts/sets once before the loop and updates them in memory as
new rows are created, deferring everything to the single `session.commit()` at the end.
5,694 resumes (parse + summarize + embed + 3 file writes each, mock mode) scanned in 28.4s
server-side.

Timing is now surfaced in the UI itself, not just claimed — `ScanResult`, and the new
`MatchListOut`/`CandidateListOut` wrapper schemas, all carry a server-measured
`elapsed_seconds`, rendered via `components/ui/timing-badge.tsx` next to the Scan Sources
result, Candidate Results toolbar, and All Candidates header ("Loaded in 298ms" /
"Matched in 0.43s").

## 12. Dashboard "Needs attention" fix + dates on Job Descriptions

The "Needs attention" KPI tile could show a number bigger than the list underneath it could
ever contain: `_kpis()` summed a red-flagged count and a missing-info count separately, so a
match that was both counted twice. Fixed to count each match once (`tier == RED_FLAG or
missing_info`), matching the list's own logic — a new test
(`test_needs_attention_kpi_counts_each_match_once`) pins this. The tile's link also went to
a generic `/app/results` with no job context, which did nothing useful; it now scrolls to the
dashboard's own "Needs attention" section (`#needs-attention`, `SectionCard` now accepts an
`id`), which already has the real per-candidate links.

Job Descriptions cards now show "Posted {date}" (`Job.created_at`), and the per-job "latest
results" panel shows when that job was last matched (`JobMatchSummary.last_matched_at`, wired
into the UI but previously unused).

## 13. Fixed: schema changes silently broke every existing database

Adding `Candidate.embedding` (section 11) broke the dashboard — and every other route
touching `Candidate` — on any database created before that column existed, with `sqlite3.
OperationalError: no such column: candidates.embedding`. Root cause: `Base.metadata.
create_all()` only creates tables that don't exist yet; it never alters an existing table to
add a column a newer model version introduced. This wasn't caught earlier because verification
ran against fresh isolated databases every time — a real, already-populated database (10,259
candidates) is what surfaced it.

Fixed generally, not just for this one column: `storage/local.py` now runs
`_add_missing_columns()` on every startup — diffs each mapped table's columns against
`PRAGMA table_info`, and `ALTER TABLE ... ADD COLUMN` for anything missing, backfilling
existing rows with the column's real default (including resolving SQLAlchemy's wrapped
`default=list`/`default=dict` callables to `'[]'`/`'{}'`, not just literal scalar defaults).
A schema change in code should never again require a manual migration step or an empty
database. `test_storage_migration.py` pins this against a simulated pre-migration database.
Verified against the user's actual database: the column was added and all 10,259 existing
candidate rows got the correct backfilled `[]` default.

## 14. Fixed: Scan Sources page crashed to a blank page on old cached scan results

Reported as two symptoms — "Scan sources not working" and "dashboard top-right Scan Sources
link goes to a blank page, and I can't even go back." Both had the same cause. `useScanStore`
persists `lastResult` (the last scan's summary) to `localStorage` via zustand's `persist`
middleware, so it survives across sessions. `ScanResult.elapsed_seconds` was added in section
11 (the performance pass) — any `lastResult` written to `localStorage` by a scan that ran
*before* that change simply doesn't have the field. `TimingBadge` (`timing-badge.tsx`) only
guarded against `seconds === null`, not `undefined`; rendering the Scan Sources page called
`seconds.toFixed(2)` on `undefined` and threw. There's no error boundary anywhere in the app,
so an uncaught render error unmounts the entire React tree — hence the blank page, and the
back button not working either (the browser changes the URL, but React itself has crashed and
is no longer listening for that change). Confirmed via the real dev server's own log
(`/private/tmp/frontend.log`), which had the exact `TypeError: Cannot read properties of
undefined (reading 'toFixed')` at `TimingBadge`.

Fixed two ways: `TimingBadge` now also treats `undefined` as "don't render" — the immediate
fix. And added `RouteErrorBoundary` (`components/layout/route-error-boundary.tsx`), wrapping
the routed page content in `AppShell`, keyed on `location.pathname` so navigating to a
different route resets it — a crash in one page now shows a recoverable "something went
wrong" card with a link back to the dashboard instead of taking down the whole app. Verified
on an isolated instance (fresh backend on :8001/:5176, throwaway `/tmp` paths) at a realistic
volume (~11k candidates, matching the real account's scale) by injecting the exact
pre-migration `lastResult` shape into `localStorage` and driving the same dashboard → Scan
Sources → back click path that was reported broken — renders correctly and back navigation
works with the fix in place.

## 15. Hardening plan, Stage 1 — performance (concurrency + vectorized similarity + real pagination)

First stage of the hardening plan, following a research pass across the codebase: four
confirmed performance gaps, all fixed.

**Sequential LLM calls in matching and ingest.** `matcher.py`'s deep-scoring and judge passes,
and `ingest_service.py`'s per-candidate embedding, each awaited one LLM call at a time in a
loop — network-bound work that left most of the wall-clock time idle. Added
`app/matching/concurrency.py`'s `bounded_gather()` (asyncio.gather behind a semaphore,
capped by the new `MAX_CONCURRENT_LLM_CALLS` setting, default 8) and applied it at all three
call sites, plus the pre-existing unbounded `asyncio.gather` in `routes/matches.py`'s
missing-embedding backfill (same risk, found while doing this). Ingest's embedding step is
deferred out of the per-resume loop into one concurrent pass after it (identity
resolution/merge stays sequential — it depends on a progressively-updated in-memory
fingerprint map — but nothing about embedding does), preserving exact prior ordering/last-
write-wins semantics if two resumes in one scan merge into the same candidate.

**Non-vectorized cosine similarity.** `embeddings.py`'s `top_n_by_similarity()` called
`cosine_similarity()` per candidate, each call allocating fresh numpy arrays — at 10k+
candidates, 10k+ tiny allocations on every single "Run matching" click. Rewritten to build one
matrix once and do a single normalized dot product. Same ranking, no behavior change — pinned
against the old loop's output in `tests/test_embeddings.py`.

**No server-side pagination on `/candidates`.** Returned every row every call; the frontend
paginated/searched/sorted a fully-loaded in-memory array. Added `storage.candidates_page()`
(filter, search, sort, and `LIMIT`/`OFFSET` all in SQL, with a matching count query) and
rewired `all-candidates-page.tsx` + `candidates-store.ts` to request server-side pages
(debounced search, same 300ms pattern already used on the Results page for the top-N filter)
instead of holding the whole pool client-side.

Verified: full backend suite (48 passed, 2 pre-existing golden-model skips) plus new tests —
`test_matcher_concurrency.py` (asserts deep-scoring actually overlaps and respects the cap),
`test_embeddings.py`, `test_candidates_pagination.py`. End-to-end on an isolated instance
(`/tmp/verify_stage1`, throwaway ports): generated + scanned 359 mock resumes, ran matching,
confirmed paginated/sorted/searched `/candidates` responses all correct (total counts, search
hits, sort order) — no functional regressions from the rewrite.

## 16. Hardening plan, Stage 2 — git init + CI

Discovered mid-plan: the project had no git repository at all (`git status` failed outright),
which blocks GitHub Actions entirely — CI needs a repo pushed to GitHub to run against. Asked
the user how to handle it; chose to initialize git now and add CI, with the user pushing to
GitHub themselves when ready (nothing was pushed anywhere by this work).

Ran `git init`, reviewed the diff against `.gitignore` (already correctly excluded `.env`,
`data/`, `sample_data/`, `node_modules/`) before committing, and made the initial commit (174
files). Added `.github/workflows/ci.yml`: a `backend` job (`pip install -e ".[dev]"`, `pytest
backend/tests/` with `USE_MOCK=true` so it needs no API keys) and a `frontend` job (`npm ci`,
`npm run lint`, `npm run build` — build already includes `tsc -b` so this covers typecheck).
Both jobs reuse the exact commands already in the `Makefile` (`make test`, `make lint`, `make
build-frontend`) rather than inventing new ones.

`ruff check backend/` surfaced ~120 pre-existing findings (mostly `datetime.utcnow()`
deprecation warnings scattered across the codebase, unrelated to this pass) — gating on that
today would make CI red on the very first run for debt nobody was asked to fix. Kept it in the
workflow as `continue-on-error: true` (visible, not blocking) rather than either silently
dropping it or scope-creeping into fixing 120 findings; a real lint-debt cleanup is its own
future task. Frontend's `npm run lint` (oxlint) already passes clean (warnings only, exit 0).

Verified the gate actually gates, not just decoratively: temporarily broke
`test_score_to_tier_bands`'s assertion, ran the exact CI test command locally, confirmed it
failed (`1 failed, 47 passed`), reverted, confirmed green again (48 passed). No live GitHub
Actions run yet — that requires the user to push this repo to a GitHub remote, which wasn't
done as part of this pass.

## 17. Hardening plan, Stage 3 — real-Gmail testing readiness

The OAuth connect flow (`email_auth/oauth.py`, `routes/email_accounts.py`) was structurally
complete but had never actually been exercised against a real account — two gaps found during
the earlier research pass, both fixed here:

**Connected account showed a placeholder forever.** Both OAuth callbacks hardcoded
`email_address="(pending profile fetch)"` and never followed up. Fixed: after token exchange,
one profile call per provider (Google: `GET oauth2/v2/userinfo`; Microsoft: `GET
graph.microsoft.com/v1.0/me`) using the just-issued access token, written into the
`EmailAccount` row before commit. Needed adding the `userinfo.email` scope alongside
`gmail.readonly` for the Google side.

**No token refresh — a real scan would start failing with 401s after ~1 hour.** The stored
token shape was a bare `{access_token, refresh_token}` dict with no way to actually refresh
(refreshing needs the token endpoint + client id/secret too, and — the one that actually broke
the first version of this fix, caught by its own test — the token's `expiry`, without which a
reloaded `Credentials` object never looks expired and refresh() never fires). Replaced with
`store_google_credentials`/`load_google_credentials` (full `Credentials` material, including
expiry) and `store_ms_cache`/`load_ms_cache` (MSAL's own `SerializableTokenCache`, since MSAL
handles refresh internally against it via `acquire_token_silent`). Added
`get_valid_access_token()` as the one place `routes/scan.py` now asks for a token — refreshes
first if needed, transparently to the caller.

Documented the two setup gotchas that would otherwise block real-account testing entirely in
`architecture/getting-started.md`: the `userinfo.email` scope, and — the one that actually
looks like a bug the first time you hit it — Google rejects sign-in from *any* account,
including your own, on an unverified OAuth app unless it's explicitly added as a "test user"
on the consent screen.

Verified: full backend suite (52 passed — 4 new tests for token refresh, 2 pre-existing golden
skips). `test_oauth_token_refresh.py` fakes the OS keychain (never touches the real one) and
stubs the SDK refresh calls (never hits the network): confirms an expired Google credential
gets refreshed and re-persisted, a non-expired one is left alone, a missing account returns
`None` cleanly, and the Outlook path correctly delegates to MSAL's `acquire_token_silent`. The
first draft of the Google refresh fix had a real bug — `expiry` wasn't being persisted, so a
reloaded credential never looked expired and refresh() silently never fired — caught by this
test suite before it ever reached the real OAuth flow. No real Google Cloud / Azure AD test
account was available in this environment, so the actual browser-based connect → callback →
scan round trip against a live inbox is still unverified; that's on the user to try against
their own account per the updated getting-started.md steps.

## 18. Hardening plan, Stage 4 — attachment scanning depth

Two gaps closed, both from the earlier research pass:

**OCR fallback for scanned/image PDFs.** `scanning/parser.py`'s `_extract_pdf_text` gave up
after pdfplumber and pypdf both came back thin — a scanned-image resume produced an
almost-empty profile. Added `_ocr_pdf_text()` as a third fallback (`pytesseract` +
`pdf2image`), tried only when the first two are still thin. Neither Python package is a hard
dependency (new `pip install ".[ocr]"` optional group) since they also need the `tesseract`
and `poppler` system binaries, which most installs won't have — missing either degrades to
returning `""` and logging, exactly the pre-OCR behavior, never a crash. Documented the
install steps (both the pip extra and the system binaries) in getting-started.md.

**Multi-attachment emails were silently mis-ingested.** `GmailIngestor`/`OutlookIngestor`'s
`_extract_attachments` yielded a separate `IngestedResume` for *every* qualifying attachment
on a message — a resume + cover letter sent together got the cover letter run through full
LLM structured-extraction as if it were an equally-valid resume, and ingested as a second
`ResumeSource` that could overwrite already-correct fields parsed from the real resume with
worse ones from the cover letter. Fixed: only the first qualifying attachment is ingested as
the resume; the rest are recorded as filenames on `IngestedResume.additional_attachments` →
`ResumeSource.additional_attachments` (new JSON column — auto-migrates on existing databases
via the mechanism from section 13, confirmed against a simulated pre-migration
`resume_sources` table) and surfaced as a small inline hint next to each source entry on the
candidate detail page (not full "additional documents" UI — deferred per the original plan as
a reasonable fast-follow, not required for this pass).

Verified: full backend suite (58 passed, 2 pre-existing golden skips) plus new tests —
`test_ocr_fallback.py` (unavailable-degrades-gracefully, using this environment's actual
missing-dependency state rather than simulating it; available-and-used; available-but-fails
still degrades gracefully), `test_email_ingestor_attachments.py` (multi-attachment picks the
right primary + records the rest for both Gmail and Outlook; single-attachment — the
common/existing case — is unaffected). Frontend typechecks clean.

## 19. Hardening plan, Stage 5 — opt-in off-hours scheduler

The last stage of the hardening plan. `apscheduler` was already a dependency but
`scheduler/__init__.py` was an empty stub. Per explicit user decision: ship it, but off by
default, with per-source opt-in the user controls — not automatic behavior sprung on anyone.

Added `ScheduledSource` (new table: `kind` "folder"|"email_account", `ref`, `last_run_at`) —
a row here is the only thing that makes a source eligible for the nightly job; nothing is
auto-scanned just because it was scanned on-demand once. CRUD lives at
`routes/scheduled_sources.py`. `SCHEDULER_ENABLED` (default `false`) is the master switch —
`main.py`'s lifespan only imports and starts `scheduler.start_scheduler()` when it's true, so
with the shipped default literally zero scheduler code path is reached. The nightly job
(`scheduler._run_nightly_scan`, cron-triggered via `SCHEDULER_HOUR`, default 2am) reuses the
exact same `run_scan()` pipeline and email-ingestor selection the on-demand `/scan/*` routes
use — `build_email_ingestor()` was extracted out of `routes/scan.py` specifically so the
scheduler isn't a second parallel implementation of "which ingestor for this account." Scan
Sources page gets a small clock-icon toggle next to each folder chip and email account row
(off by default, per the plan), with an inline note that it also needs the server-side setting.

Two real bugs caught by this stage's own tests before either reached the real app:

1. **The nightly job unconditionally loaded the full mock-email fixture manifest** (thousands
   of files off disk) even when zero email sources were scheduled — a folder-only nightly run
   would have taken ~17s of pure file I/O for no reason every single night. Caught because the
   first version of `test_nightly_scan_runs_for_scheduled_folder_source` was suspiciously slow
   (25s) compared to everything else in the suite; profiled with `cProfile` rather than
   shrugging it off, found 14k `pathlib.read_bytes` calls, fixed by loading the manifest
   lazily (only the first time an email-kind source is actually encountered) instead of
   unconditionally up front. Confirmed via profiling again: 19ms.
2. **`POST /scheduled-sources` threw `DetachedInstanceError`** the first time it was actually
   exercised through the real FastAPI app (not just unit-tested against the storage layer) —
   `session.commit()` expires ORM attributes by default, and returning the object for
   `response_model` serialization after the session's `with` block closes means pydantic can't
   read it. Fixed the same way `routes/jobs.py`'s `create_job` already does (an established
   pattern in this codebase, not a new one): `session.refresh(source)` before returning.

Verified: full backend suite (66 passed, 2 pre-existing golden skips) — new tests
`test_scheduler.py` (nightly job actually scans a scheduled folder source and updates
`last_run_at`; no-op with zero scheduled sources; confirms `start_scheduler` is never called
when `SCHEDULER_ENABLED=false`) and `test_scheduled_sources.py` (full CRUD against the real
FastAPI app via `TestClient`, incl. auth-required and duplicate-add dedup). Frontend
typechecks and builds clean. End-to-end on an isolated instance (`:8004`/`:5177`, throwaway
`/tmp` paths): added a folder, toggled its auto-scan clock icon on, reloaded the page and
confirmed the toggle state persisted server-side (not just client state), toggled back off —
zero console errors throughout.

## 20. Repo setup — git, license, Docker packaging

Follow-up work once the hardening plan itself was done. The project had no git repository at
all until this point (see section 16); it's now pushed to
`https://github.com/mrithwik/recruit-assistant`. Added `LICENSE` (all rights reserved — a
deliberate choice, not a default: this handles real candidate PII and isn't intended as an
open-source project) and `SECURITY.md` documenting the existing safeguards (PBKDF2 password
hashing, OS-keychain token storage, read-only OAuth scopes).

Added Docker packaging so someone can run the whole app with zero local Python/Node install —
`docker compose up --build`: `backend/Dockerfile` (installs the existing `pyproject.toml`
package into a `python:3.12-slim` image), `frontend/Dockerfile` (multi-stage — `node:20-slim`
build, served by `nginx:alpine`), and `frontend/nginx.conf` reverse-proxying `/api` and
`/health` to the backend container — mirroring what `vite.config.ts`'s dev-mode proxy already
does for `npm run dev`, since the production build has no dev server to do that at request
time. `docker-compose.yml` wires the two together with a named volume for
`backend/data` (SQLite + resume mirror) so data survives a container restart, and defaults to
`USE_MOCK=true` — same zero-setup default as the rest of the project.

Verified by actually building and running the stack (`docker compose build` then `up`) rather
than trusting the Dockerfiles on paper: confirmed the backend container starts and answers
`/health`, the frontend container serves the built SPA, and nginx's reverse proxy correctly
forwards both `/api/*` and `/health` to the backend over the internal Docker network. One
verification snag worth recording: the first build/run used the default `8000`/`5173` ports,
which — on this machine — briefly overlapped with the real, already-running dev instance
(Docker Desktop's port-forwarding proxy can coexist with a loopback-bound native process on
macOS rather than erroring, so both were reachable at once for about 10-15 seconds). Caught
by checking `lsof` after the fact rather than assuming success; remapped to `8010`/`5183` for
the rest of verification, tore down and removed the test containers/volumes afterward, and
confirmed directly via `sqlite3` that the real database was completely unaffected (same
10,259 candidates, same account) — but the real dev session's browser tab may have
transiently 401'd and shown a login screen during that window, since its bearer token
wouldn't have validated against the fresh container's independently-generated secret key.

## 21. Real-Gmail scan performance — async, concurrent, backgrounded

Real-Gmail testing (a synthetic ~10,000-persona dataset generated for load testing — resumes,
follow-ups, resume updates, casual check-ins, and back-and-forth threads spanning 10 years,
delivered via real SMTP + Gmail API insert) surfaced a real architectural gap before a full
scan was ever attempted against it: `GmailIngestor.scan()` did two sequential blocking network
calls per matched message (full message fetch, then attachment fetch) with no concurrency at
all, using a sync `httpx.Client` directly inside an `async def` route with no threadpool
offload. At real-mailbox scale (~11,000+ attachment-bearing messages) that's 20,000+
sequential round-trips — estimated at 1-3+ hours — and because the sync client blocked the
event loop directly, the *entire* single-process backend would have frozen (no other request
served) for the whole duration, with the triggering HTTP request held open the entire time.

Fixed in three parts:

1. **Async + bounded-concurrent ingestion.** `ResumeIngestor.scan()` is now an async generator
   (`AsyncIterator[IngestedResume]`); `GmailIngestor`/`OutlookIngestor` use `httpx.AsyncClient`
   and fetch each page's messages concurrently via the existing `bounded_gather` helper (new
   `max_concurrent_email_fetches` setting, default 15 — Gmail starts returning 429s somewhere
   around 25 concurrent, found via the load-test delivery run). Added 429/5xx retry with
   exponential backoff (`_get_with_retry`) and trimmed the Gmail `fields` param to only what
   `_walk_parts`/header-parsing actually reads. `FolderIngestor`/`MockEmailIngestor` updated to
   the same async-generator interface for parity (trivial — disk/in-memory, no real concurrency
   need there). `ingest_service.run_scan`'s consuming loop changed from `for` to `async for`.

2. **Background job execution.** Even with concurrency, a real scan can still run for
   several minutes to tens of minutes — long enough that holding one HTTP request open for it
   is bad UX and risks a browser/proxy timeout. `POST /scan/folders` and
   `/scan/email-accounts` now kick the scan off as an `asyncio.create_task` and return a job id
   immediately (202), tracked in a new in-memory `app/scanning/job_registry.py` (same
   module-global pattern as `dependencies.py`); a new `GET /scan/jobs/{id}` endpoint reports
   status/result. Frontend (`scan-store.ts`) updated to poll every 1.5s instead of awaiting the
   POST directly; `scan-page.tsx` needed no changes since the store still resolves/rejects the
   same way once the job finishes.

3. **Verification** (deliberately *not* run against the real connected account per explicit
   instruction — full 66→71-test suite plus three new targeted tests instead): a concurrency
   test proving `GmailIngestor.scan()` actually overlaps fetches while respecting the
   concurrency cap (mirrors the existing `test_matcher_concurrency.py` pattern), job-registry
   lifecycle tests, and the existing attachment-handling tests rewritten for the new
   async/`_extract_one` shape. Full suite green; frontend typechecks and builds clean.

## 22. Scan-job resilience — checkpointing, duplicate-scan guard, live progress

Before attempting a real scan against the load-test account, walked through what a
30-40 minute background job (see section 21) would actually mean in practice, and found
three more real gaps, all fixed without running anything against the live account:

1. **No partial persistence.** `run_scan()` did one `session.commit()` at the very end —
   a failure near the end of a long run (e.g. retries finally exhausted on a persistent
   network blip) would have discarded the entire run's work. Added `checkpoint_every`
   (default 500) — commits (and flushes any pending embeddings) periodically during the
   loop via a `_flush_checkpoint()` helper, reached through a `finally` block so it still
   fires on the "already-seen, skip" `continue` path too. Verified with a test that makes
   the ingestor raise partway through and confirms the already-processed candidates
   survived in the DB despite the run never completing.

2. **Duplicate-scan race.** The "scanning" button-disable state lives in browser JS and
   isn't persisted — a page refresh mid-scan resets it, and a re-click would start a
   second job against the same account with no visibility into the first one's in-flight
   dedup state (each job preloads its own fingerprint cache at start), risking duplicate
   candidates. `job_registry.py` now tracks active scan scopes (same account_ids / same
   folder_paths) and rejects a second concurrent request for the same scope with a 409.

3. **No real progress.** The existing progress bar was a time-based guess derived from
   unrelated sample-data counts — not accurate for a real scan and liable to look "stuck"
   for a long time. `run_scan()` gained an `on_progress` callback fired after every resume
   (cheap, in-memory only); `ScanJob`/`ScanJobOut` gained a `progress` field the frontend
   polls and displays as real running counts (resumes processed / created / updated /
   skipped) alongside the existing simulated bar.

All verified via new/updated tests (66 → 78 passing) — deliberately not against the real
connected account, per explicit instruction to hold off on actually running it.

## 23. Reattach-after-refresh + scan-job registry pruning

Closed the one remaining soft gap from section 22: `scanning`/`scanProgress` live only in
browser JS state, so a page refresh (or a second tab) during a real scan loses visibility
into it, even though the job keeps running server-side regardless. `scan-store.ts` now
persists `activeJobId` to `localStorage` (same mechanism already used for `lastResult` etc.);
on Scan Sources page mount, `resumeActiveScanIfAny()` checks it — still running, resume
polling exactly as if nothing happened; already finished while away, surface the result/toast
immediately; 404 (backend restarted since — the job registry is deliberately in-memory only,
see section 21), silently drop the stale id. Refactored the shared "wait for job, apply
result, toast" logic into one `followJob()` helper used by both the normal button-click path
and the reattach path, with a flag controlling whether it toasts itself (the normal path
already gets a toast from the page's own try/catch; only the reattach path needs to raise one
on its own, since there's no page-level caller for it to land in).

Also added a cap on the job registry (`MAX_STORED_JOBS = 50`, pruning oldest finished jobs
once over the limit, never a running one) — the registry had no eviction at all before this,
which would slowly accumulate every scan ever run over months of the app staying open.

Verified via 4 new job-registry tests (pruning, and pruning never touching a running job) plus
a frontend typecheck/build; still not run against the real connected account.

## 24. Real scan bug fixes + split mock mode into two live-toggleable flags

Two real bugs, found by actually attempting a scan against the load-test account rather than
just reasoning about the code:

**24a. Naive/aware datetime crash.** The scan job failed after 27s with "can't compare
offset-naive and offset-aware datetimes" — the frontend's date-range picker sends
`toISOString()` (a "Z"-suffixed, timezone-aware string), Pydantic parses that as aware, but
every `date_submitted` elsewhere in the codebase is naive UTC (`datetime.utcnow()`). Fixed at
the request boundary: `ScanFolderRequest`/`ScanEmailRequest` now normalize `date_start`/
`date_end` to naive UTC via a `field_validator`, so nothing downstream needs to know
timezones exist. (Also explained why no toast/result card appeared — the frontend's poll
loop had stopped well before the 27s failure, most likely the tab losing focus or being
navigated away before it completed; a real gap closed properly in the next stage.)

**24b. Silent mock-mode scan.** Separately — and this was the bigger finding — the actual
scan that had "failed" was never going to hit the real connected Gmail account at all:
`USE_MOCK=true` controlled both the LLM client and the email ingestor with one flag, so
"Scan email now" against the real account silently ran `MockEmailIngestor` against fixture
data instead. Fixed by splitting into two independent settings, `USE_MOCK_LLM` and
`USE_MOCK_EMAIL`, and — per explicit request — making both live-toggleable from the UI
without a backend restart:

- `app/runtime_settings.py` — new module-global pair (mirrors `dependencies.py`'s pattern),
  initialized from `Settings` at startup, then mutable via `PATCH /api/v1/settings/mock-mode`.
- `DispatcherLLMClient` (`matching/llm_client.py`) — wraps a `MockLLMClient` and (if a
  provider key is configured) a real client, routing every call to whichever
  `runtime_settings.get_use_mock_llm()` says *at call time* rather than a choice baked in once
  at startup. `build_llm_client()` now always returns this dispatcher.
- Email-mock selection (`build_email_ingestor`, the scheduler, dev-tools sample-data seeding)
  switched from the frozen `settings.use_mock` to the live `runtime_settings.get_use_mock_email()`.
- New `GET`/`PATCH /api/v1/settings/mock-mode` route — the PATCH guardrail checks the
  *actual* `DispatcherLLMClient.real_client is not None`, not a fresh re-read of `.env`, since
  a key added to `.env` after the backend already started wouldn't retroactively populate the
  already-built dispatcher (caught this exact gap in self-review before it shipped).
- `Settings.expose_mock_mode_toggle` (default on) lets the UI control be hidden entirely if
  this app is ever handed to someone else.
- Frontend: new `Toggle` component, two clearly-labeled independent toggles on the Scan
  Sources page (email source, LLM processing) with a cost warning on the real-LLM one and the
  guardrail message surfaced inline when no key is configured.

`USE_MOCK` retired outright (not kept as a fallback) — every `.env`/`.env.example`/
`docker-compose.yml`/CI-workflow/doc reference updated to the two new flags.

## 25. Reattach-after-refresh was itself a real gap the datetime bug exposed

Investigating why no toast appeared for the failed scan surfaced the exact gap flagged as a
"soft, non-blocking" risk two stages earlier: the poll loop's state lives only in browser JS,
so a refresh (or the tab simply losing focus long enough) silently loses visibility into an
in-flight scan even though it keeps running server-side. Already fixed by this point (see the
reattach-after-refresh + job-registry-pruning work) — worth noting here since this was the
first time that fix's absence was actually *felt*, not just anticipated.

## 26. Real-Gmail scan validated end-to-end, and a real frontend bug it surfaced

With mock mode properly split (section 24), the user ran an actual scan against the connected
Gmail account: 623 resumes found, 607 new candidates, 16 updated, in 24.5s — the first real
end-to-end proof this pipeline works outside of mocks/tests. The one reported "error" turned
out to be harmless: a stale `selectedAccountIds` entry left in `localStorage` from before an
account was disconnected/reconnected (a fresh `EmailAccount` row gets a new id on reconnect).
Fixed by pruning `selectedAccountIds` against the live account list every time
`fetchEmailAccounts()` runs (`scan-store.ts`), instead of only ever appending to it.

## 27. Extensive filtering on All Candidates (skills, status, visa, experience)

Replaced free-text-only search with real structured filters, entirely server-side:

- `storage.candidates_page()` gained `skills`/`employment_statuses`/`work_visa_statuses`/
  `experience_min`/`experience_max` params — each multi-select is OR'd internally, all filters
  combine as AND. Skills matching stays portable (cast-to-string `ILIKE` on the quoted JSON
  value, not a SQLite-specific JSON operator) and deliberately guards against substring false
  positives (`"sql"` must not match `["postgresql"]"`).
- New `GET /candidates/facets` — distinct skills actually present in the pool (not a fixed
  list) plus the enum values for status/visa and the current max `experience_years`, so the
  filter UI never offers an option with zero matches.
- Deliberately **left out** a `role`/title field — discussed and rejected: unlike the enum
  fields, "role" has no controlled vocabulary, so an LLM-extracted value fragments instead of
  faceting cleanly, and it would need a backfill decision for existing candidates. Skills +
  experience + status + visa covers the same recruiter need without that risk.
- Frontend: `MultiSelectFilter` and `ExperienceRangeFilter` (new, reusable popover
  components), wired into `all-candidates-page.tsx`.
- **Filters became apply-on-click, not apply-on-every-change** — a follow-up request after
  the first version fired a request per checkbox click. Query text, skill/status/visa/
  experience selections now stage in the store and only fetch on an explicit "Apply filters"
  button (or Enter in the search box); sort and pagination still fetch immediately since they
  act on whichever filter set is already applied, not new criteria.

Same "apply-on-click, not per-change" pattern was applied to Match Results' job/Top-N
controls (a "Load results" button replacing auto-refetch) — which surfaced a real regression:
neither the selected job nor loaded matches were persisted anywhere, so a refresh now showed
a blank page (previously masked by the auto-fetch that just ran again on every mount). Fixed
by persisting `matches`/`topN` (`matches-store.ts`) and `selectedJobId` (`jobs-store.ts`) to
`localStorage`; a `resultsAreStale` check still catches the case where the persisted matches
belong to a job other than whichever is now selected, showing a "switched jobs, click Load
results" prompt instead of silently showing mismatched results.

## 28. Email deep-links — and a real bug in the first version

Added a link from a candidate's profile straight to the source email in Gmail/Outlook's own
web UI (so a recruiter can reply from the real thread, not compose a fresh one).
`ResumeSource.email_link` populated at ingest time; Outlook uses Graph's own `webLink` field
directly, Gmail needed one built from `https://mail.google.com/mail/u/0/#all/{id}`.

**Bug in the first version:** used the Gmail message `id` instead of `threadId`. Gmail's web
UI renders that URL fragment as a *thread* view — a reply/forward's own message id either
404s or opens the wrong item in that view; only a message that's the sole one in its thread
happens to have message id == thread id, which is why casual testing looked fine. Fixed by
fetching `threadId` (added to `GMAIL_MESSAGE_FIELDS`) and using that instead — caught only
because the user actually clicked the link and reported it didn't show the real email body,
not from re-reading the code.

Surfaced two adjacent gaps, both closed:
- A plain rescan does **not** backfill `email_link` onto already-ingested resumes — dedup in
  `ingest_service.py` keys on `(content_hash, source_ref)`, and an already-seen message hits
  that exact match and is silently skipped, never re-touching the row. This became the seed
  for the maintenance-task framework (section 30).
- Candidate cards/lists needed a *batched* "most recent email_link" lookup
  (`_batch_email_links`, mirrors the existing `_batch_origins` pattern) so All Candidates,
  Match Results, and the candidate detail page all show it without N+1 queries.

## 29. Scan-date-range picker losing its selection on tab navigation

Reported as "select a date range, switch tabs, it vanishes." Root cause: `DateRangePicker`'s
highlighted-preset state (`active`) was local `useState`, uncontrolled by its parent — the
underlying `dateStart`/`dateEnd` values were still correctly held in `scan-store` the whole
time, but the *component* unmounted on navigation and remounted with reset-to-default local
state, showing "All time" even though a range was still technically applied. Fixed by making
the component fully controlled: `scan-store` gained a `dateRangeLabel` field (which preset, or
"custom", is active) alongside `dateStart`/`dateEnd`, all three now also persisted to
`localStorage` (previously only date values existed, and even those weren't persisted) so the
selection survives both tab-switching and a full refresh.

## 30. Recent Activity was one-sided, and the maintenance-task framework it led to

Two related fixes:

**30a. Recent Activity fixed.** It only ever showed matching runs and up to 10 individual
"Added <candidate>" rows — a single 600-resume scan produced 10 near-duplicate "Added" lines
that buried any actual summary, and scans/maintenance runs had no representation at all. Added
`IngestScanHistoryEntry` (one row per completed scan — folder, email, or maintenance —
recorded by `scan.py`'s `scan_folders`/`scan_email_accounts`/the new `scan_all`, the opt-in
nightly scheduler, and `routes/maintenance.py`). `_recent_activity()` now merges matching-run
summaries with these scan summaries and drops the per-candidate rows entirely — a scan of any
size now reads as one line, e.g. "Scanned email (x@example.com) — 623 found, 607 new, 16
updated."

**30b. Maintenance-task framework.** The email-link backfill gap (section 28) is the first
instance of a pattern that will recur: a feature that reads a field on existing rows only
applies going forward once shipped, and "just rescan" doesn't fix it (dedup skips already-seen
rows). Built as a reusable registry (`app/maintenance/tasks.py`) rather than a one-off script:
a task is `{id, label, description, run_fn, pending_count_fn}`; it gets a background job for
free (reuses `job_registry.py` — the exact scan-job infra, so progress polling/dedup-guard/
pruning are already solved), a route (`GET /maintenance/tasks`, `POST /maintenance/tasks/
{id}/run`), and a UI panel. First+only task registered: `email_link_backfill` — looks up just
the thread id/webLink for existing `ResumeSource` rows directly via the Gmail/Outlook API
(no re-ingestion, no re-parsing, no LLM calls).

`pending_count` (a query, e.g. "how many resume_sources still have no `email_link`") drives a
Dashboard "Updates available" banner that only appears when a task actually has pending work —
verified against the real database: 14,115 of the account's real email sources predate this
feature and are still pending. The per-task run/poll/progress UI (`MaintenanceTaskRow`) is
shared between this banner and the full "Data maintenance" panel on Scan Sources, so the two
surfaces can't drift.

## 31. Targeted rescans — per-candidate, per-job, and bulk

Three new ways to catch updates without paying for a full mailbox scan, each scoped to a
different, deliberately-sized unit of work:

- **Per-candidate** (`POST /candidates/{id}/rescan`) — "Check for updates" on the candidate
  detail page. Narrows Gmail/Outlook search to just that person's sender address
  (`GmailIngestor`/`OutlookIngestor` gained a `sender_email` filter param) and re-scans their
  known folder path(s) as-is. Extracted as `rescan_candidate_sources()` so it's reusable, not
  duplicated, by the next scope down.
- **Per-job, bounded to matched candidates** (`POST /matches/{job_id}/rescan-matched`) — "Check
  for updates" on Match Results. Loops the per-candidate rescan over just a job's already-
  matched candidates (naturally capped by whatever `top_n` the match run used), reporting
  "checked N, updated X, unchanged Y" so it's explicit that only some candidates actually
  changed, not a bulk re-ingest.
- **All candidates, bulk** (`POST /scan/all`) — "Rescan all for updates" on the All Candidates
  page. Deliberately **not** a loop of per-candidate scoped rescans at this size — one combined
  pass over every connected account + every known folder path (same cost as a normal Scan
  Sources run), vs. hundreds of separate mailbox searches if done per-candidate. This tradeoff
  was confirmed with the user directly (`AskUserQuestion`) before building, since it materially
  changes real API cost at volume.

Also fixed while researching this: the candidate detail page's match list only showed a bare
tier badge, no red flags/missing info/judge notes — so the Dashboard's "Needs Attention →
Review" link landed somewhere that didn't explain *why* a match needed a look. `CandidateOut`'s
match rows were the lightweight `MatchSummaryItem` shape; added `CandidateMatchDetail` (extends
it with `reasons`/`missing_info`/`flags`/`judge_notes`) used only for `CandidateDetailOut`, so
the Jobs-page "top candidates" widget (which still only needs the lightweight shape) is
unaffected.

## 32. OAuth setup guidance, progress bars everywhere, Jobs page bulk actions

**OAuth setup guidance.** Clicking "Connect Gmail"/"Connect Outlook" with no OAuth client
configured hit the backend's 400 correctly, but since `connect/*` are plain `<a href>` browser
navigations (can't carry an auth header, so can't be a normal `fetch()` either), the error
rendered as raw unstyled JSON instead of reaching the app's own UI at all. New
`GET /email-accounts/oauth-status` (are `GOOGLE_OAUTH_CLIENT_ID`/`MS_OAUTH_CLIENT_ID` set)
drives an inline, collapsible setup-steps banner on Email Access *before* that click happens,
and disables the Connect button for whichever provider isn't configured yet.

**Progress bars audited across every long-running action.** Several background jobs had only
a spinner with no sense of progress: Data Maintenance tasks, per-candidate "Check for
updates," and the Jobs page's per-job "Scan & match" panel all gained the same
`ProgressBar`/`useSimulatedProgress` treatment Scan Sources already had, plus live counts where
the backend reports real interim progress (every maintenance-task checkpoint, every candidate
checked in a rescan).

**Jobs page bulk actions.** "Select all" (with indeterminate-state checkbox), "Match selected,"
and "Match all (N)" — runs matching against existing candidate data across multiple jobs in
sequence with a progress bar. Deliberately *not* given the same persisted-job-id
survive-refresh treatment the scan/rescan jobs got: each matching run is already an
independent, atomic backend call, so a refresh mid-loop only loses the client-side "how many
are left" bookkeeping, not any already-completed job's results — a smaller gap than a scan
losing all progress, so the job-registry treatment wasn't worth the added complexity here.

**Rename:** "Candidate Results" → "Match Results" throughout the UI, per user feedback that
the old name was confusing.

## 33. Job-results link bug, per-job update actions, two real chart/count bugs, and the All/Real/Mock data-mode toggle

**Job Descriptions' "View results" link lost the job.** `job-scan-match-panel.tsx`'s link
pointed at `/app/results` with no `job` query param, so Match Results just showed whatever
job's matches were last persisted in `matches-store`, not the job the user actually clicked
from — reported as "the displayed match results don't correspond to the relevant job
description." Fixed to carry `?job={jobId}`, matching the pattern `job-results-summary.tsx`'s
own link already used correctly.

**Per-job and bulk "update matched candidates."** Extended the existing per-job
rescan-matched endpoint (section 31) onto the Jobs page itself, not just Match Results: each
job card's results summary gained an "Update matched" action with its own progress bar
(`job-results-summary.tsx`), and the toolbar/selection bar gained "Update matched (N)" /
"Update selected" bulk actions (`jobs-page.tsx`) — same sequential-loop pattern as the
existing "Match all," skipping jobs with no matches yet rather than treating that as a
failure.

**The maintenance pending-count bug.** Running "Backfill email links" reported "0 updated,
14,115 skipped" and looked broken. It wasn't — checking the live database directly showed all
624 real Gmail-sourced candidates already had their link (filled at ingest time), and every
one of the 14,115 unlinked rows was `mock-demo-mailbox:`-prefixed sample/test data with no
real inbox message to link to. The real bug: `_email_link_pending_count`
(`app/maintenance/tasks.py`) counted those unresolvable rows as "pending" too, so the
Dashboard's "Updates available" banner would show ~14,115 forever and every future run would
report the same "0 updated" result permanently, looking perpetually broken. Fixed to only
count rows with a real, currently-connected account behind them (same resolution logic the
backfill itself already used to decide what it could touch).

**Inflow chart rendering all-email data with the folder color.** The Dashboard's stacked
area chart (`inflow-chart.tsx`) stacks `email` then `folder`; with zero folder-origin data,
folder's series is flat at 0 everywhere, but its 2px stroke line still rendered on top of the
email area's boundary (drawn second = higher z-order), visually overwriting the chart's edge
with the folder color even though it contributed nothing — an entirely email-sourced dataset
rendered as if it were the folder series' orange/red instead of email's blue. General fix, not
a one-off: only render a stacked series's `<Area>` when it actually has nonzero data in the
displayed window, so a flat-zero series can never visually dominate.

**The All/Real/Mock data-mode toggle.** A recruiter who loaded a large generated sample
dataset for testing (section reference: the sample-data generator, `reference` doc) had no
way to view or work with just their real, actually-scanned candidates separately from the
sample set, short of deleting one. New `app/data_classification.py` classifies a
`ResumeSource` as mock/sample without any join: `MockEmailIngestor` always writes the fixed
literal `source_ref` prefix `mock-demo-mailbox:` (never the configured demo mailbox's real
address), so origin="email" needs no `EmailAccount` lookup to tell mock from real; a
folder-origin source falls back to a path heuristic (`sample_data` in the path). A candidate
counts as "real" if it has at least one real source, "mock" only if every source is mock.

Wired as a `data_mode` query param ("all"/"real"/"mock") through: `candidates_page()` +
`candidate_facets()` (All Candidates, including its filter-bar options), `GET /matches/{job_id}`
(Match Results viewing), and every candidate/match-derived Dashboard widget (KPIs, tier
distribution, top skills, visa breakdown, jobs snapshot, needs-attention — recent activity
stays unfiltered, it's a scan log, not candidate data). Surfaced as a persistent segmented
control in the app header (`data-mode-toggle.tsx`, backed by `data-mode-store.ts`), with live
counts from a new `GET /candidates/data-mode-counts`.

Initially shipped as view-only; the user then asked for it to also scope **Run matching**
itself, not just what's displayed — `POST /matches/run/{job_id}` now takes the same
`data_mode` param and filters the candidate pool *before* scoring, so "Real" actually matches
against only real candidates rather than the whole pool with results filtered after the fact.
`matches-store.ts`'s `runMatching`/`loadMatches` read the toggle internally, so every call
site (Match Results' "Run matching," each job card's inline "Run," the Jobs page's bulk
"Match all"/"Match selected") picked it up with no per-call-site changes needed.

## 34. A four-perspective stakeholder review, then localhost binding + login rate limiting

A standing stakeholder review (`reports/stakeholder-review.md`) read the app from four
chairs — a recruitment BA, a product owner walking out of a demo, a data-governance/security
lead, and the CEO — backed by an 8-round live QA pass against a real connected Gmail account
and a 7,212-candidate dataset. Governance and the CEO agreed on one immediate, bounded pair of
fixes ahead of any feature work, explicitly scoped to this app's actual deployment model: one
instance per recruiter's own laptop, not a shared multi-tenant server.

**Server bound to `0.0.0.0` by default.** Despite being documented as local-first, the backend
listened on every network interface, not just the machine it ran on — anyone on the same
office Wi-Fi could reach the API directly. `.env.example` now sets `API_HOST=127.0.0.1`, with
the rationale for why local-first means localhost-only in an inline comment there.

**No login rate limiting.** `POST /auth/login` had no lockout or throttling — nothing stopped
online credential-stuffing against a reachable login form. New `app/auth/rate_limit.py`: an
in-memory (module-global, single-process — see ADR-002's reasoning for why this app doesn't
reach for Redis) per-email counter, 5 failed attempts locks that email out for 15 minutes,
clears on success, and returns the identical response shape for a locked-out real email vs. a
nonexistent one (no user-enumeration side channel).

**A `.env` value-extraction bug found across three QA rounds, each catching what the last
missed.** `API_HOST`/`API_PORT` overrides in `.env` silently did nothing, because `.env` is
parsed by `pydantic-settings` *inside the Python process* — the shell scripts that launch
`uvicorn` (`scripts/run_all.sh`, the Makefile's `run` target) never see it. Fixing this meant
extracting just those two keys in the shell, without `source`-ing the whole file (real `.env`
values can contain unescaped spaces — an app password — that aren't valid literal bash).
Three QA rounds, each surfacing a shape the last one's fix didn't cover: round 1 found the
naive `grep`/`cut` version broke when the key was simply absent (a `grep` returning no match
exits 1, which — under `set -euo pipefail` inside a `$(...)` assignment — silently killed the
whole script, worse than the original bug since it broke the *default* path too, not just the
override path); round 2 found quoted values, trailing whitespace, and CRLF line endings all
produced a real `uvicorn` startup failure (`nodename nor servname provided`); round 3 found
whitespace padded *inside* the quote marks survived unquoting, because the trim passes only
ran once, before the quote-strip, never after. Consolidated into one shared
`scripts/env_value.sh` (deduplicating what had been separately, and differently, implemented
in both `run_all.sh` and the Makefile) with `scripts/test_env_value.sh` covering all of the
above plus two lower-priority, deliberately-unhandled edge cases (mismatched quote types, a
literal `#` inside a quoted value) documented rather than fixed.

## 35. Pipeline stage tracking — the BA review's #1 finding

The stakeholder review's clearest gap: the app scores a candidate against a job (a *quality*
signal — poor through great, or red-flagged) but had no concept of *sourced → screened →
submitted to client → interviewing → offer → placed/declined* — a *status* signal. No way to
answer "where is this person in the process" for any candidate, which the BA called the
single most-used view in any ATS.

New `PipelineStage` enum, mirroring `MatchTier`'s existing pattern, added as a column directly
on `Match` (not a new table — pipeline status is job-specific, exactly the same shape
`tier`/`flags`/`judge_notes` already are; a candidate is "interviewing" for one role and merely
"sourced" for another). Defaults to `sourced` and backfills automatically via the existing
schema-driven `_add_missing_columns` migration (`storage/local.py`) the same way every prior
column addition on this project has. Free-form transitions, not an enforced state machine —
same philosophy as `tier`/`flags` today, since real recruiting isn't strictly linear (a
candidate can be pulled back from "submitted" to "screened"). New `POST
/matches/{id}/stage`, a stage badge + dropdown + filter on Match Results, a stage badge on
Candidate Detail's "Pipeline across jobs" list, and a new zero-filled dashboard chart
(`_pipeline_stage_distribution`, mirroring the existing tier-distribution aggregation) —
deliberately using a separate, non-tier hue family for the badge (slate → sky → blue → violet
→ amber → emerald), since stage and tier answer different questions and mixing their palettes
would read as "how good" when it means "how far along." No kanban board, no cross-job pipeline
overview page, no decline-reason taxonomy — each confirmed absent from the current UI/roadmap
and scoped out as its own future effort, not a silent omission.

## 36. Fact-checking the stakeholder review against the current code

Before picking the next items off the review, every remaining finding was re-verified against
the live codebase rather than taken on faith — the review itself was already a few days old
by the time work resumed on it. One finding turned out to be stale: "registration is
unauthenticated and unlimited" was true of no version of this codebase — `POST /auth/register`
has 403'd any registration attempt once one account exists since the *initial commit*, before
this session's own localhost-binding work and before the review was even written. That
correction reframed two other findings: governance's "no per-account data isolation" and "no
audit trail of who touched what" both assume a threat model — multiple people sharing one
running instance — that the single-account cap already forecloses by design, and that the
confirmed one-instance-per-laptop deployment model doesn't call for regardless. Treated as not
applicable under the current model, not merely deferred.

The two items that survived the fact-check as real, standalone gaps, independent of the
multi-tenancy question either way: no way to delete a single candidate's PII (only a
wipe-everything "danger zone"), and no consent step before real-LLM mode starts sending resume
text to a third-party API. See section 37.

## 37. Per-candidate PII deletion, a real-LLM consent gate, and a QA-caught orphan-file bug

**Per-candidate delete.** New `DELETE /candidates/{id}` (204) — a real, irreversible delete,
not a soft-delete, since the entire point is honoring a genuine right-to-erasure request
without wiping every other candidate the way the existing danger-zone "CLEAR" does. Removes
the on-disk mirror (resume file, `profile_summary.md`, `meta.json`) before the DB row, verified
against `meta.json`'s own `candidate_id` before touching anything, and deletes only files it
can name — never an `rmtree`. `Match` and `ResumeSource` rows cascade automatically through
the ORM's existing `delete-orphan` relationships (no manual per-table deletes needed, unlike
`clear_data`). Frontend: a per-candidate danger-zone card on Candidate Detail, adapted
directly from the existing typed-`"CLEAR"`-confirmation pattern (`components/scan/danger-zone.tsx`),
using `"DELETE"` instead — no Undo affordance, since an undo would mean the data wasn't
actually erased.

QA found a real bug in the mirror cleanup on its first pass: two resume submissions on the
same day for the same candidate land in the *same* mirror directory (`mirror_writer.py` keys
the directory on candidate + date, not per-submission) — with different file extensions, that
directory holds two resume files (`resume.pdf`, `resume.docx`) sharing one `meta.json`. The
original per-source deletion loop deleted `meta.json` while handling the first source sharing
that directory, then re-read it to safety-check the second source pointing at the same
directory, found it already gone, and defensively skipped — silently orphaning a file
containing the candidate's real name and email in a directory the app no longer tracked
anywhere. QA reproduced this against the app's own real data on a second random pick, not a
constructed edge case. Fixed by grouping sources by target directory first, reading
`meta.json` once per directory before deleting anything in it, then deleting every resume file
in that group together — confirmed via a regression test seeding the exact shape (fails
against the pre-fix code, passes after), and reproduced live a second time against real
sample-data-generated files to confirm the fix.

**Real-LLM consent gate.** New `User.real_llm_consent_given_at` — a one-time acknowledgment,
before real-LLM mode is ever switched on, that resume text and job descriptions leave the
machine for a third-party API. Persisted on `User` deliberately, not in `app/runtime_settings.py`
(which is explicitly in-memory-only by design, so the mock/real toggle itself keeps resetting
to mock on every backend restart) — re-asking for consent on every restart would be
user-hostile for something that only needs saying once. `PATCH /settings/mock-mode` 428s the
first time real mode is requested without `consent_ack: true`; once given, never re-checked.
New `LlmConsentModal` (built on the existing generic `Modal` component) intercepts the toggle
client-side before the API call ever fires. Live-verified the full state machine, including a
real backend restart: `use_mock_llm` resets to `true` afterward exactly as designed, while
`real_llm_consent_given` stays `true` — no re-prompt.

Both landed with the same verification discipline as every round before: an isolated instance
seeded via the app's own sample-data generator and a real matching run, never against the real
`:8000` instance or its database; 169/169 backend tests passing after the fix (163 before the
regression test was added); the real instance's health and `.env` confirmed unchanged
throughout.

## 38. Sample-data session tagging — generate, list, and delete by batch

Requested directly from the README (`README.md:98`): sample data had no concept of "this
batch vs. that batch" — regenerating repeatedly (testing at different volumes, after a code
change) piled everyone into one undifferentiated pool, deletable only wholesale via the
Danger Zone's "CLEAR". Confirmed with the user upfront (`AskUserQuestion`) how to treat
already-generated data from before this feature existed: bucket it as one deletable
"Unlabeled (before session tracking)" pseudo-session rather than leaving it invisible to the
new UI.

**Tagging mechanism, chosen to need zero ingestor changes.** Every file
`sample_data_generator.py` writes is prefixed with its generation's session id
(`sess-<timestamp>-<hex>__<original-name>`, `app/dev_tools/session_tagging.py`) — both
FolderIngestor (reads bare filenames off disk) and MockEmailIngestor (reads a manifest
entry's `attachment_file`, itself the same generated filename) already carry that prefix
through to `IngestedResume.filename` with no code changes on either side.
`ingest_service.py`'s single `build_resume_source()` call site extracts it back out and
stamps a new nullable `ResumeSource.generation_session_id` column (auto-migrated, same as
every prior column addition — see `_add_missing_columns`). Real/manually-added data is
simply never tagged, so `generation_session_id` staying null is itself meaningful, not a gap
to fill.

**Generation is now additive, not overwriting.** `emails_manifest.json` is read and merged
rather than replaced on each generate call — a `sessions` array of per-run summaries
(id, label, generated_at, seed, counts) alongside the existing flat `emails` array. This is
also what makes every session's filenames collision-free even at the same `--seed`
(previously identical filenames from a same-seed regenerate would silently overwrite the
prior run's files on disk) — a second, unplanned fix riding along with the tagging work,
directly addressing the "regenerate silently swapped fixtures under the running dev server"
risk flagged during an earlier QA pass (section 34).

**New endpoints:** `GET /dev-tools/sample-sessions` (manifest sessions merged with live DB
scan counts per session, plus the legacy bucket sized via the existing
`is_mock_source_condition()` heuristic) and `DELETE /dev-tools/sample-sessions/{id}`. Deletion
reuses the exact per-candidate delete pattern from ADR-012 (mirror files + cascaded rows, real
and irreversible) — but a candidate can legitimately have sources from *two* sessions (the
same deterministic person regenerated under the same default seed twice), so a candidate is
only fully deleted when 100% of its sources belong to the target session; otherwise it's
**trimmed** (just that session's sources/files removed, candidate kept). This mixed-ownership
path was exercised for real during live verification, not just in the regression test — five
generations at the default seed left most candidates shared across sessions, and deleting one
session correctly trimmed 12 shared candidates rather than deleting them outright. Session
deletion also prunes not-yet-scanned raw files and the manifest entry, so a deleted session
can't be accidentally re-scanned back into existence.

Frontend: new `SampleSessions` panel (`components/scan/sample-sessions.tsx`) on Scan Sources,
between the generator and the Danger Zone, refetching after both a new generation and a
completed scan (the latter needed its own fix — the panel initially only refreshed on
generate, so a session's "scanned" status went stale until the next generate click).

Verified against a fully isolated instance (port 8123/5183, `/tmp/verify_sessions`, never the
real `:8000`/`:5173` pair) — the complete generate → scan → list → delete loop was driven live
end-to-end through curl and a headless-browser Playwright script, not just the automated
`test_sample_sessions.py` suite. 169 backend tests passing (unchanged pre-existing failures in
`test_oauth_status_route.py`/`test_scan_all_route.py` traced to this machine's real `.env`
leaking into those specific tests — confirmed present on `main` before this work too, not a
regression).

**Found, not fixed (separate, pre-existing bug):** live verification also surfaced that the
Real/Mock data-mode classification (`data_classification.is_mock_source_condition`) undercounts
mock data for folder-origin resumes — it checks `ResumeSource.file_path` for a `sample_data`
segment, but `file_path` is the *post-mirror* copy path (`data/candidates/...`), which never
contains it; the original path that does is only preserved in `source_ref`, which the check
doesn't look at. Confirmed live: 78 synthetic folder-scanned candidates all showed under
"Real" in the header toggle. Unrelated to this feature (no code touched here affects it) and
out of scope for this batch — flagged for a future fix, not patched silently.

## 39. QA on session tagging — two real bugs, both live-reproduced and fixed

An independent QA pass on section 38's work verified the additive-manifest and
`generation_session_id`-propagation claims directly (including checking the schema migration
against a genuinely pre-change database, not just a fresh one — the exact gap that broke
`Candidate.embedding` before), then found two real bugs the new tests hadn't caught:

**Trimming orphaned a surviving session's file.** `write_mirror` keys its target directory on
candidate + date, not per-submission — regenerating the same deterministic person (same seed)
on the same day overwrites the earlier session's `resume.<ext>`/`meta.json`/
`profile_summary.md` in place, so two `ResumeSource` rows from *different* sessions can end up
pointing at the exact same physical file. The trim path was calling the ordinary
`delete_candidate_mirror` with only the session-being-deleted's sources, which unconditionally
wipes every file in that source's directory — taking the surviving session's still-referenced
file down with it (`GET /candidates/{id}/resume` 404'd afterward, even though the candidate
itself survived). Fixed with a new `delete_candidate_mirror_partial()`
(`scanning/mirror_writer.py`) that only deletes a resume file if no surviving source still
points at that exact path, and only touches `meta.json`/`profile_summary.md`/the directory
itself if no surviving source lives in that directory at all. Regression test simulates the
same-day-same-extension collision directly (two `ResumeSource` rows sharing one `file_path`)
and asserts the survivor's file, `meta.json`, and summary are all still there after the delete.

**Deleting a never-scanned session 404'd.** `list_sample_sessions`'s own docstring already
said an unscanned batch "can still be found and deleted," but `delete_sample_session` queried
`ResumeSource` first and 404'd immediately when that came back empty — never reaching the
file-cleanup path at all. Reordered: the DB pass and the on-disk cleanup pass both always run,
and the 404 only fires if *neither* found anything to remove.

Both fixed and reproduced clean afterward (live curl + the new regression tests); 171 backend
tests passing (169 + 2 new), same 3 pre-existing unrelated failures as section 38.

## 40. Speed plan, step 1 (instrumentation) — QA fix: combined multi-source scans dropped stage_timings

Following the speed-plan report (`reports/scan-match-speed-plan.md`)'s "instrument first"
recommendation, `ScanResult` gained a `stage_timings` field and `run_scan()`/
`match_job_against_pool()` were instrumented to populate it (parse/summarize/mirror_write/embed
for a scan; embed/deep_score/judge for a match run) — see section 39's continuation for the
first pass. QA found the one real gap: `POST /scan/email-accounts` and `POST /scan/all` both
loop over multiple sources (accounts, or accounts + a known-folders pass) and build a single
combined `ScanResult` by accumulating each call's fields — but `stage_timings` was never added
to that accumulation, so the completed job's result silently stayed at `{}` even though every
individual `run_scan()` call underneath computed real numbers. `/scan/all`'s live progress made
this more visible, not less: mid-run progress passes each call's raw result straight through
(showing correct non-zero timings), then the *completed* result reverted to `{}` once combined
took over — worse than uniformly missing, since it looked correct while running.

Fixed with one shared `_merge_stage_timings()` helper (`routes/scan.py`) that sums per-stage
seconds across ScanResults, used everywhere `combined.X += result.X` already happens for the
older fields, plus threaded into `scan_email_accounts`'s progress closure (which already
carefully re-based counts/errors on each account's starting point — `stage_timings` now gets
the same treatment, not just left as the current account's raw partial). Two new regression
tests reproduce the QA's exact multi-source shape (two accounts scanning identical fixtures for
`scan_email_accounts`; a folder branch that dedupes as already-seen plus a fresh email branch
for `scan_all`) and were confirmed to fail against the pre-fix code, pass after. Live-verified
against an isolated instance with the QA's own repro (`POST /scan/email-accounts` against the
auto-seeded demo mailbox) — `stage_timings` came back non-zero on the completed result instead
of `{}`. 174 backend tests passing, same 3 pre-existing unrelated failures.

## 41. Speed plan, step 1 (instrumentation) — QA fix #2: rounding before summing zeroed real work

A second QA pass on section 40's fix found `test_scan_all_does_not_drop_stage_timings_across_folder_and_email_branches`
failed reliably (5/5 in isolation), traced to `run_scan()` rounding each stage's total to 2
decimals *before* returning it — `_merge_stage_timings()` (from section 40) was summing
already-quantized numbers, so two real-but-small per-call contributions that each
independently round to `0.00` still sum to `0.00`, permanently losing work that genuinely
happened. Not unrelated flakiness: this is the merge fix's own target scenario (real work
split across multiple small combined calls) landing on the one input shape that pre-rounding
gets wrong.

Fixed by moving all rounding to a single point: `run_scan()`, `match_job_against_pool()`, and
`routes/matches.py`'s embed-timing now all return/accumulate **raw, unrounded** floats;
`_merge_stage_timings()` sums raw too. A new `_round_stage_timings()` helper is the only place
rounding happens, called exactly once at each terminal point a `ScanResult` is actually handed
to `complete_job`/`update_progress` as displayed state (`scan_folders`, both `complete_job`
sites in `scan_email_accounts`/`scan_all`, the progress closure in `scan_email_accounts`, and
`routes/matches.py`'s final result).

Verification split in two, since QA's own root-cause diagnosis was that a live-timing test on
a small enough workload is inherently flaky (the true, correctly-unrounded total can still
legitimately dip under 0.005s on a fast machine — that's not a bug, just noise at trivial
scale): a new deterministic unit test suite (`test_stage_timings_rounding.py`) proves the exact
numeric scenario (two 0.004s contributions summing to a correctly-displayed 0.01, not a lost
0.00) with no real timing involved, confirmed to fail before the fix (`_round_stage_timings`
didn't exist) and pass after; the existing live integration tests
(`test_scan_stage_timings.py`) had their sample-data volume raised (5 → 60 resumes) for
real-world margin above the rounding threshold, stress-tested 15/15 clean afterward. 177
backend tests passing, stable across repeated full-suite runs, same 3 pre-existing unrelated
failures throughout this whole stretch of work.

## 42. Speed plan, step 2 — parallelizing the ingest loop and offloading blocking work (levers 01+02)

Following the speed-plan report's #1 and #2 levers together, since #2 (offload blocking
CPU/disk work off the event loop) is what actually lets #1 (parallelize the per-resume loop)
deliver real overlap rather than just interleaved-but-still-blocking coroutines.

**Lever 02, self-contained first.** `parser.py`'s `extract_text` (pdfplumber, pypdf,
python-docx, and worst-case a Tesseract OCR subprocess call) ran synchronously inside an
`async def`, blocking the event loop for its full duration. Now wrapped in
`asyncio.to_thread`. Same treatment for `mirror_writer.write_mirror`'s disk I/O at its call
site in `ingest_service.py`.

**Lever 01 — `run_scan` restructured into two phases per batch** (`max_concurrent_processing`,
new param, defaults to 8, threaded through every call site via `settings.max_concurrent_llm_calls`
like every other concurrency dial):

- **Phase 1, concurrent** (`_parse_and_summarize`, via `bounded_gather`): parse + summarize
  every resume in the batch at once — network/CPU-bound, independent per resume. Each worker
  catches its own exceptions and returns them as data (`_ParsedItem.error`) rather than
  raising, so one bad resume can't cancel its siblings mid-`asyncio.gather` the way a raised
  exception would — preserving the isolation the old sequential per-resume try/except gave for
  free.
- **Phase 2, sequential, in the batch's original order**: identity resolution, mirror-writing,
  persistence — deliberately *not* parallelized. Two resumes for the same person landing in one
  batch must merge into the shared `fingerprints` dict in order, not race each other; two
  same-day submissions of the same candidate can collide on the same `write_mirror` target
  directory (see section 39's orphan-file bug) if written concurrently. `write_mirror` still
  runs via `asyncio.to_thread` here even though it's sequential, so the event loop stays
  responsive between writes without reintroducing that race.

**Two correctness risks found and fixed before they became bugs, not after:**
1. Within-batch duplicates (the same file yielded twice, or two same-day resubmissions) aren't
   caught by Phase 1's dedup check (`seen_sources` isn't mutated until Phase 2) — Phase 2
   re-checks and skips them there, which is what actually matters; confirmed unchanged by the
   existing `test_rescan_skips_unchanged_file_instead_of_duplicating`.
2. `_next_batch`'s first version discarded already-fetched items if the ingestor's generator
   raised mid-batch-fill (e.g. a real mailbox exhausting retries) — losing the exact "partial
   progress survives a mid-scan failure" guarantee `test_ingest_service.py`'s checkpoint test
   exists to pin, since the whole point of periodic checkpointing is that a late failure
   doesn't discard everything found before it. Caught before shipping by re-running that
   specific test against the new code, not after: `_next_batch` now returns `(batch,
   exception)` — already-fetched items are processed and checkpointed exactly as before, and
   the exception is re-raised only after, matching the old sequential `async for`'s ordering
   exactly.

**New tests:** `test_ingest_concurrency.py` proves actual overlap directly (a tracking mock LLM
client asserting `max_in_flight > 1`), independent of real wall-clock timing. Live-verified on
an isolated instance at real volume (350 generated resumes, folder scan): `parse` stage total
(2.53s, summed across concurrent calls) exceeded the scan's own `elapsed_seconds` (1.38s) — the
expected signature of genuine concurrency — with a same-content rescan afterward correctly
skipping all 350 (`duplicates_skipped: 350`, candidate count unchanged), and a mock-email scan
of the same people afterward correctly merging into the existing candidates (0 errors either
way).

**A significant process correction, surfaced by this step's own verification.** Every "3
pre-existing, unrelated test failures" claim made across this entire session's work (sections
38-41) was wrong in its framing — not because the underlying code comparisons were invalid
(each was checked apples-to-apples via git-stash red/green, which stayed valid), but because
those 3 failures were never actually pre-existing at all: they were an artifact of running
`pytest` from inside `backend/` instead of the project's actual canonical invocation,
`python -m pytest backend/tests/` from the repo root (see the `Makefile`'s `test` target).
Run correctly, the full suite has been **181 passed, 0 failed, 2 skipped** — not "177-179
passed, 3 failed" — this whole time. Confirmed reproducibly both ways (wrong directory: 3
failures, every time; repo root: clean, every time) before correcting the record with the
user. Going forward, verification in this project runs `python -m pytest backend/tests/` from
the repo root, not from inside `backend/`.

## 43. Speed plan, step 2 — QA fix: cancellation discarded already-paid-for batch work

QA on section 42's batching found the cancellation-handling code didn't match its own comment.
The comment said cancelling mid-batch still applies the rest of the *current* batch's
already-parsed items (Phase 1's parse+summarize work for them is done and paid for —
discarding it wastes it for nothing in mock mode, and wastes real spend in real-LLM mode) and
only skips *further* batches. The code instead `break`d out of the batch's Phase 2 loop the
moment cancellation was detected, throwing away the rest of that batch's already-completed
work. Not a data-integrity bug (nothing inconsistent was ever written), but a real regression
against the old one-at-a-time loop's behavior, and a comment actively misleading the next
reader. QA reproduced it directly: cancelling after 3 of 10 resumes in one batch left only 3
persisted, the other 7's already-done parse+summarize work discarded.

Fixed by making the code match the comment (the comment's reasoning was correct) rather than
watering the comment down: the cancel-check now only sets `cancelled = True` without a
`break`, so Phase 2's inner loop runs to completion over the rest of the current batch, and
only the outer `while not cancelled:` stops pulling further batches. New regression test
(`test_cancelling_mid_batch_still_applies_the_rest_of_that_batch`) is fully deterministic — a
plain counting callback, not real timing — and confirmed to fail against the pre-fix `break`
(4 resumes landed, not the expected 8) before passing after. 182 backend tests passing (181 +
this one), 0 failures, stable across repeated runs — see section 42 for the
`python -m pytest backend/tests/`-from-repo-root correction this count now reflects correctly.

## 44. Speed plan, step 3 — scanning multiple mailboxes concurrently (lever 03)

`scan_email_accounts` and `scan_all`'s account loop both ran one connected mailbox's *entire*
scan to completion before starting the next — pure wasted wall-clock time for anyone with more
than one connected account. The report's suggested fix (run each account's `run_scan()` as a
sibling task) turned out to have a real correctness trap the report didn't account for: running
several `run_scan()` calls concurrently against the *same* SQLAlchemy `Session` risks both
session corruption (overlapping `add()`/`commit()` calls) and duplicate candidates (two
accounts yielding the same person concurrently, each independently deciding "new candidate"
from its own stale in-memory fingerprint snapshot, since neither would see the other's
not-yet-committed work).

Solved with a new `FanInIngestor` (`scanning/fan_in_ingestor.py`) instead: wraps several
`ResumeIngestor`s into one, running their `scan()` generators as concurrent producer tasks
feeding a shared `asyncio.Queue`, and yielding items as they arrive — genuinely concurrent
network fetch, feeding into exactly **one** `run_scan()` call. This gets the real concurrency
win (multiple mailboxes' API calls overlapping) with zero additional correctness risk, because
identity resolution and mirror-writing stay serialized through `run_scan`'s own single
session/fingerprints dict/`seen_sources` set — the same safe design lever 01 already built,
just fed by more than one source at once. A source's mid-stream exception is forwarded through
the queue and re-raised at the consumer, matching what a single failing ingestor would have
done on its own (and letting `run_scan`'s existing `_next_batch` partial-batch handling take it
from there, unchanged).

Both routes simplified as a result: `scan_email_accounts` no longer needs the manual
base-count-plus-partial progress accumulation across accounts (there's only one `run_scan`
call now, so its own progress callback is already the whole picture) — a meaningful reduction
in that function's complexity, not just a speed win. `scan_all`'s account loop got the same
treatment; its folder branch stays a separate `run_scan()` call (smaller, more contained
change, matching the report's "small effort" framing for this lever).

New tests: `test_fan_in_ingestor.py` proves the actual mechanism directly — two slow
(`asyncio.sleep`-based) fake ingestors interleave in ~0.1s total, not the ~0.2s two fully
sequential sources would take; a failing source's exception propagates to the consumer while
still surfacing whatever it already yielded; an empty ingestor list yields nothing. Stable
10/10 on repeated runs (no timing flakiness despite using real sleeps). Live-verified against
two real connected accounts on an isolated instance: one combined scan found 80 resumes (40 per
account against identical fixtures), correctly created 40 + deduped the other 40, updated both
accounts' `last_scanned_at` together, and `parse` stage timing (0.49s summed) again exceeded
wall-clock `elapsed_seconds` (0.2s) — the same overlap signature as lever 01's verification.
185 backend tests passing (182 + 3 new), 0 failures, stable across 3 repeated runs.

## 45. Speed plan, step 3 — QA fix: one failing mailbox was truncating every healthy sibling

QA on section 44's `FanInIngestor` found a real reliability regression: any one source's
exception was treated as a poison pill that immediately cancelled every other still-producing
source sharing the same combined scan — reproduced directly by QA (a healthy 100-item source
paired with one that failed after 0.05s only got 4 of its own items out before the whole
stream was cut off). In the old per-account sequential loop, one account's failure only ever
affected that account; this broke that isolation, and since the propagated exception unwound
all the way to the route's outer `except`, the *whole job* was reported failed rather than
"completed, one account errored" — a real regression for exactly the multi-mailbox scenario
this lever targets, surfacing during exactly the kind of session that's been about protecting
this "one bad thing shouldn't take down everything else" guarantee.

Fixed by changing what a source's exception does inside `FanInIngestor`: instead of being
forwarded to the consumer and re-raised (killing the combined stream), it's now caught at the
source's own pump task, recorded on `self.errors` (label-attributed) and `self.failed_labels`,
and that's it — every other pump keeps running, `scan()` itself never raises for a source-level
failure. Both call sites (`scan_email_accounts`, `scan_all`'s account loop) updated to pass
`(account_id, ingestor)` pairs instead of bare ingestors, merge `fan_in.errors` into the job's
error list afterward, and — new correctness detail this fix surfaced — only bump
`last_scanned_at` for accounts *not* in `fan_in.failed_labels`, so a failed account no longer
gets silently credited with a fresh "successfully scanned" timestamp.

Two new tests prove it: `test_fan_in_ingestor.py`'s
`test_a_failing_source_does_not_truncate_a_healthy_sibling` reproduces QA's exact scenario
(healthy 100-item source + a source failing at 0.05s) and asserts all 100 healthy items still
land; a new `test_scan_email_accounts_isolation.py` proves the same guarantee through the real
route end-to-end (two accounts, one wired to a monkeypatched failing ingestor) — job reports
`"completed"` (not failed), the healthy account's 5 candidates are created, the failing
account's error is in `result.errors`, and only the healthy account's `last_scanned_at` moved.
Both confirmed to fail against the pre-fix poison-pill version before passing after. 187
backend tests passing (185 + 2 new), 0 failures, stable across 3 repeated runs. Live-verified
the normal (non-failing) single-account path is unaffected.

## 46. Speed plan, step 4a — retry-with-backoff on the LLM client (not raising the cap)

The last item off the speed-plan report that doesn't need a research decision first (lever
04a specifically, not 04b — raising `max_concurrent_llm_calls` itself still depends on the
user's actual OpenRouter/OpenAI rate-limit headroom, an open question, so the dial itself
wasn't touched). `OpenRouterClient`/`OpenAIClient` had zero retry logic — a single 429/5xx
failed the call outright, and for `OpenRouterClient` specifically, immediately fell through to
the OpenAI fallback rather than giving the primary provider a chance to recover from what's
often a transient blip.

Added `_post_with_retry` (`matching/llm_client.py`), mirroring the existing
`scanning/email_ingestor.py::get_with_retry` pattern already used for Gmail/Outlook fetches
(exponential backoff capped at 30s, 6 attempts, non-retryable 4xx raises immediately) — same
reasoning, applied to the scoring/embedding calls instead of the mailbox-fetch ones. Used by
both `OpenRouterClient` and `OpenAIClient`'s `complete()`/`embed()`. Retries happen *inside*
`OpenRouterClient`'s existing try/except, so the fallback path only triggers once retries are
truly exhausted, not on the first blip.

Seven new tests (`test_llm_client_retry.py`) prove: 429/5xx retried then succeeding; a
non-retryable 4xx (401) raising immediately without any retry; persistent 429s exhausting all
attempts and raising; `OpenRouterClient` recovering from a transient 429 on retry *without*
touching its fallback (a fallback that asserts it was never called); `OpenRouterClient` still
falling back once retries are truly exhausted; `OpenAIClient` getting the same retry treatment.
Confirmed to fail against the pre-fix code (reverted to the last commit, `_post_with_retry`
didn't exist) before passing after. 194 backend tests passing (187 + 7 new), 0 failures, stable
across 3 repeated runs.

This only matters in real-LLM mode — no live network-level verification was possible in this
environment (no real OpenRouter/OpenAI credentials configured), so verification stopped at
exercising the actual production `OpenRouterClient`/`OpenAIClient` code paths against a
scripted fake HTTP client returning real status codes, the closest available substitute.

With this, every speed-plan lever startable without a research decision (instrumentation,
01, 02, 03, 04a) is done. Remaining items — raising the concurrency cap (04b), summary-vs-raw-
text scoring (05), the dead `LLM_TRIAGE_MODEL` config (06), the shortlist multiplier (07),
batched multi-candidate scoring (08) — all wait on the user's answers to the report's open
questions.

## 47. Incremental email/folder scan — don't re-fetch history that's already been scanned

Not from the original speed-plan report's numbered levers — this came out of directly asking
the user how they wanted to resolve the report's "typical mailbox volume" open question. Their
answer: the real connected mailbox has 10,000+ emails across ten years, daily volume is
unknown yet, and — the actual insight — once a date range has been scanned, it shouldn't need
rescanning again unless a future parsing/matching change means it should be reprocessed. Every
scan path today (`/scan/email-accounts`, `/scan/all`, and the nightly scheduler) re-fetches and
re-parses full mailbox history on every run; `EmailAccount.last_scanned_at` and
`ScheduledSource.last_run_at` were already being written, just never read back as a scan
lower-bound.

Added `_effective_date_start` (`routes/scan.py`): an explicit `date_start` on a request always
wins (existing custom-range behavior unchanged); otherwise a new `full_rescan: bool = False`
flag on `ScanEmailRequest` (and as a query param on `POST /scan/all`) opts back into scanning
everything; otherwise the effective start defaults to the account's own `last_scanned_at` (or
full history if it's never been scanned). Because `FanInIngestor` forwards one `date_start` to
every source it fans in uniformly, and different accounts in the same request can have
different watermarks, added `_ScopedDateIngestor` — a thin wrapper that pins a source to its
own fixed date range regardless of what `scan()` is actually called with, so each account in a
multi-account request is bounded independently. The nightly scheduler (`scheduler/__init__.py`)
gets the same default — `_run_nightly_scan` now passes each source's own watermark
(`account.last_scanned_at` for mailboxes, `source.last_run_at` for folders) as `date_start`,
with no override option since that path is never user-driven.

Folder scans initiated on-demand (`/scan/folders`, and `/scan/all`'s ad hoc folder-path sweep)
were deliberately left untouched — there's no per-path last-scanned watermark for those (only
`ScheduledSource`-registered folders track one), and local-disk folder scans are cheap enough
that this wasn't the bottleneck the user was describing.

Nine new tests: `test_incremental_email_scan.py` (6 — per-account default-to-watermark,
never-scanned-defaults-to-full-history, explicit `date_start` overriding the watermark,
`full_rescan` bypassing it, two accounts in one request getting independent watermarks, and
`/scan/all` applying the same default/override behavior — the last of these also confirms the
always-present mock-mode `demo@mock.local` account, which `/scan/all` sweeps in along with
whatever the test seeds, doesn't corrupt the assertion) and `test_incremental_nightly_scan.py`
(3 — scheduled folder and email sources each scanning from their own watermark, and a
never-run scheduled source still getting full history). 203 backend tests passing (194 + 9
new), 0 failures.

### QA fix: the watermark was captured after the scan finished, not before it started

QA found (and directly reproduced) a real, silent-data-loss bug: `account.last_scanned_at` /
`source.last_run_at` were stamped with `datetime.utcnow()` *after* `run_scan()` returned — i.e.
after real parse/summarize LLM calls for every resume in the batch had already run, which at
real volume can take minutes. Any message that arrived on the mailbox during that window has a
received-date earlier than the recorded watermark but was never part of this scan's own search
results — and every future incremental scan's `after: <watermark>` filter would exclude it too,
permanently, with no error or symptom to notice by. Exactly the "silent permanent data loss"
failure class this project has repeatedly had to guard against (the candidate-delete PII
orphaning, the session-trim mirror-orphaning bug, the same-day mirror collision).

Fixed by capturing the watermark once, right before the mailbox fetch begins (`scan_started_at
= datetime.utcnow()`, immediately before the `run_scan()` call), and writing that back instead
of a freshly-taken timestamp afterward — at all three call sites (`scan_email_accounts`,
`scan_all`, and the scheduler's per-source loop). Any message that arrives during the scan is
now safely inside the next scan's window instead of permanently excluded from every future one;
the resulting small overlap is harmless, already deduped by content-hash/fingerprint in
`run_scan`.

New test `test_incremental_scan_watermark_timing.py` proves it directly: a deliberately slow
ingestor (yields after a 0.4s sleep, standing in for real parse/summarize latency) is scanned,
and the recorded watermark is asserted to land close to when the request was *sent*, not when
it *completed* — confirmed red (watermark landed at completion time) against the pre-fix code
via `git stash`, green after. 204 backend tests passing (203 + 1 new), 0 failures.

## 48. Speed plan, step 5 — score against the candidate summary, not raw resume text

The other lever that came out of directly asking the user how to resolve the report's "quality
tradeoff appetite" open question. Their framing: invest in making the summary genuinely good,
and there's little real tradeoff left. `judge_score` was already scoring against
`candidate.semantic_summary`, not raw text — only `deep_score` (the first, always-run scoring
pass) still used the raw parsed resume text, truncated at 6000 chars, carrying whatever
PDF/OCR formatting noise `parse_resume` didn't clean up.

Two changes, shipped together per the user's choice (rather than summary-quality-only first):

`SUMMARY_PROMPT` (`matching/prompts.py`) rewritten from "2-3 sentences, role fit/seniority/
skills/gaps" to "4-6 sentences, dense with specifics" — and explicitly told not to restate
skills/years/education/employment-status/work-visa (already passed to `deep_score` as separate
structured fields; a summary that only echoed them back would add nothing new to score
against). Instead it's steered toward what those structured fields miss: career narrative and
seniority trajectory, specific projects/achievements with concrete scope from the resume
(team size, scale, metrics — not invented), domain specialization, and gaps/red flags.

`matcher.py`'s `_score_one` now passes `c.get("summary") or c["resume_text"]` to `deep_score`
instead of `c["resume_text"]` — summary first, raw text only as a fallback for a candidate that
doesn't have one yet (pre-dates this feature, or summarization failed on that resume), so
nothing gets scored against an empty string.

**On the "A/B against known-good matches before trusting it broadly" ask**: this environment
has no real LLM credentials (same limitation noted in section 46), so no live quality
comparison was possible here. What *is* now in place for the user to run themselves: a new
live-only golden test, `test_golden_fixture_live_tier_scoring_against_summary` (skipped without
`RUN_LIVE_GOLDEN=true` + a real key, same gate as the existing golden suite) — it runs each
golden fixture's resume text through `summarize_candidate` first, then `deep_score`s the
resulting summary instead of the raw text (mirroring exactly what `_score_one` now does in
production), and holds the result to the *same* `expected_tier_min`/`expected_tier_max` bounds
as the raw-text version. A fixture that passes the raw-text golden test but fails the
summary-based one is the actual real-world signal that `SUMMARY_PROMPT` is losing something
`deep_score` needs — that's the concrete way to run the requested A/B before trusting this
broadly, whenever a real provider key is available.

Two new mock-LLM unit tests (`test_scoring_uses_summary.py`) prove the routing itself,
independent of quality: a candidate with a summary gets scored against it (not the raw text —
asserted by checking which marker string shows up in the actual prompt sent to the LLM), and a
candidate with no summary yet still gets scored against its raw text rather than nothing.
Checked the frontend for length assumptions before shipping the longer prompt: the one list-
view usage (`all-candidates-page.tsx`) already `line-clamp-1`s the summary, so a longer one
degrades gracefully there; the two detail-view usages show it in full by design. 206 backend
tests passing (204 + 2 new, +2 new skipped-without-live-key golden tests), 0 failures.

### QA fix: SCORING_PROMPT still called its input "Resume text" even when fed a summary

QA caught, by inspection alone (no live model needed), that `SCORING_PROMPT` hard-coded the
label `"Resume text (truncated):"` above its input slot — even in the now-common case where
`deep_score` is actually handed the AI-generated summary, not the resume. `JUDGE_PROMPT`, fed
the same kind of content one stage later, already labels it honestly as `"Candidate summary:"`
— the inconsistency was a real risk: a model told it's reading "resume text" could plausibly
read `SUMMARY_PROMPT`'s deliberate omissions (skills/years/education, already given above as
structured fields) as a sparse resume, or list them under `missing_info`, undermining the
whole point of switching to a denser, evidence-focused summary.

Fixed by parameterizing the label instead of hard-coding it: `SCORING_PROMPT` now has a
`{resume_label}` slot; `deep_score()` takes a `resume_label` param (default
`RESUME_TEXT_LABEL`, matching prior behavior) and a new `SUMMARY_LABEL` constant (both in
`matching/prompts.py`) states plainly that the input is an AI-generated summary that was told
not to restate the structured fields, so an absence there shouldn't be read as missing from
the resume itself. `matcher.py`'s `_score_one` now picks the label based on which input it
actually used — `SUMMARY_LABEL` when scoring against `c["summary"]`, `RESUME_TEXT_LABEL` on
the raw-text fallback path — so the model is told the truth in both cases, not just the common
one. The new live golden test (`test_golden_fixture_live_tier_scoring_against_summary`) updated
to pass `resume_label=SUMMARY_LABEL` too, so it now mirrors production exactly.

`test_scoring_uses_summary.py`'s two existing tests extended to also assert on which label
string appears in the actual prompt sent to the LLM (not just which content) — confirmed
against the pre-fix code that they'd have caught this. 206 backend tests passing (same count —
this was inline test coverage, not new test files), 0 failures.

## 49. Speed plan, step 6 — dual-mode triage (embedding default, optional cheap-LLM re-rank)

Resolves the report's `LLM_TRIAGE_MODEL` open question per the user's direction: keep both
modes available and switchable, favoring free embedding-similarity by default, with the option
to spend a cheap (or eventually local) LLM pass when embedding similarity alone is judged to be
missing nuance — not a one-time either/or decision.

New `settings.triage_mode` ("embedding" default | "llm"), global rather than per-request since
it's a cost/quality tradeoff meant to be tuned once real usage shows which mode earns its keep,
not decided scan-by-scan. `match_job_against_pool` gets a `triage_mode` param:
`"embedding"` reproduces the exact prior behavior (cosine-similarity picks the
`top_n * SHORTLIST_MULTIPLIER` shortlist, zero LLM calls, `stage_timings["triage"] == 0.0`).
`"llm"` casts a *wider* embedding net first (`TRIAGE_WIDENING_MULTIPLIER = 3`× the final size)
so the LLM triage pass has real candidates to promote that embedding similarity alone ranked
outside the narrow shortlist, then a new `llm_triage()` (scores each candidate's summary — never
the full deep-score prompt, that's the point of it being the cheap stage — via a new
`TRIAGE_PROMPT`, `settings.llm_triage_model`) narrows back down to the exact same final size
`deep_score` sees either way, so switching modes changes *which* candidates reach deep-scoring,
not deep-scoring's own cost.

`MockLLMClient` (`llm_client.py`) got a matching `_mock_triage` — same "actually read the
input, don't return one fixed value" principle as the existing `_mock_score_match` — so
`triage_mode="llm"` is exercisable and deterministic under `USE_MOCK_LLM=true`, not just live.

Four new tests (`test_triage_modes.py`): embedding mode makes zero LLM calls and reports
`triage: 0.0`; llm mode triages exactly the widened-net size and deep-scores exactly the same
final size as embedding mode would; the actual point of the lever proven directly — a candidate
ranked 6th by embedding similarity (inside the widened net, outside the narrow one) only
reaches the final results when the LLM triage pass, not embedding similarity, promotes it
(construed with a similarity gradient with no ties, so the ranking is deterministic); and
`MockLLMClient`'s triage path reads the prompt instead of returning a fixed value. Confirmed
red against the pre-change code (`TRIAGE_WIDENING_MULTIPLIER` didn't exist) via `git stash`
before passing after. One pre-existing test (`test_data_mode_filter.py`) updated for the new
always-present `"triage"` key in `stage_timings`. 210 backend tests passing (206 + 4 new), 0
failures.

## Cross-references

- [Design Decisions](design-decisions.md) — the ADRs behind each choice above
- [System Overview](system-overview.md), [Backend Architecture](backend-architecture.md),
  [Frontend Architecture](frontend-architecture.md)
- [Getting Started](getting-started.md), [`HOW_TO_RUN.md`](../HOW_TO_RUN.md)
