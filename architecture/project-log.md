<!-- Version: v0 | Last updated: 2026-08-24 | Status: current -->

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

First stage of the hardening plan (see `.claude/plans` at the time, and the research pass that
preceded it): four confirmed performance gaps, all fixed.

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

## Cross-references

- [Design Decisions](design-decisions.md) — the ADRs behind each choice above
- [System Overview](system-overview.md), [Backend Architecture](backend-architecture.md),
  [Frontend Architecture](frontend-architecture.md)
- [Getting Started](getting-started.md), [`HOW_TO_RUN.md`](../HOW_TO_RUN.md)
