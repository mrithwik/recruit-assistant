<!-- Version: v0 | Last updated: 2026-08-31 | Status: current -->

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

## Cross-references

- [Design Decisions](design-decisions.md) — the ADRs behind each choice above
- [System Overview](system-overview.md), [Backend Architecture](backend-architecture.md),
  [Frontend Architecture](frontend-architecture.md)
- [Getting Started](getting-started.md), [`HOW_TO_RUN.md`](../HOW_TO_RUN.md)
