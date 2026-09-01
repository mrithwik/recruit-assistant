<!-- Version: v0 | Last updated: 2026-09-01 | Status: current -->

# Testing Report

A consolidated record of every QA round on this project — what was found, how it was
verified, and how it was fixed. Two eras: an 8-round live QA pass against a real connected
Gmail account and a 7,212-candidate dataset (feeding the stakeholder review), and a series of
targeted rounds on the security/deletion/consent work that followed it. Every round in both
eras was verified against real, scaled data on an **isolated instance** — never the user's own
live `:8000` process or database.

## Verification discipline

Consistent across every round in this report:

- Test instances run on throwaway ports, seeded via the app's own sample-data generator (not
  hand-written fixtures alone) plus a real matching/scan run, so QA sees the same shape of
  data — including its imperfections — a real installation would.
- The real, running instance's health (`curl /health` → 200) and process identity (same PID
  throughout) are reconfirmed after every round.
- `.env` and the real SQLite database are never edited in place without a confirmed revert
  (`git diff .env` empty) — any temporary edit for a test is undone before the round ends.
- A fix is not reported as done until re-verified live, not just re-read. Two cases in the
  first era (below) were a "fix" that only addressed the visible symptom while the underlying
  bug was still there on the next pass — caught precisely because verification meant retesting,
  not re-reading the diff.

## Era 1 — the 8-round pass behind the stakeholder review

Full detail in [`reports/stakeholder-review.md`](../reports/stakeholder-review.md). Summary:
**8** rounds, **11** distinct issues found, **11** fixed and re-verified, **7,212** real
candidates tested at.

| Round | Focus | Finding | Outcome |
|---|---|---|---|
| 1 | Dashboard & Match Results | Needs-attention KPI counted matches, not candidates — disagreed with its own linked page (103 vs. 97) | Fixed |
| 1 | Match Results paging | Expand/Collapse-all button mislabeled after paging | Fixed |
| 1 | All Candidates | Empty state ignored the active data-mode filter, pointed at the wrong fix | Fixed |
| 1 | Routing | No catch-all route — any mistyped URL rendered a fully blank page | Fixed |
| 2 | Match Results paging | Expand-all fix only relabeled the button — underlying state was still silently discarded across pages | Fixed |
| 2 | All Candidates | Data-mode empty-state fix didn't compose with the Needs-attention filter | Fixed |
| 2 | Jobs page | Single-job delete had no confirmation while bulk delete did | Fixed + Undo |
| 2 | Candidate detail | No way to view or download a candidate's original resume file | Built |
| 2 | All Candidates / Match Results | No CSV export of candidates or match results | Built |
| 4 | All Candidates bulk select | Selection bar vanished entirely when a filtered view returned zero results | Fixed |
| 4 | Candidate notes | Note deletion had no confirmation and no recovery path | Fixed + Undo |
| 5 | Email Access | `EmailAccount.last_scanned_at` was never written by any code path — always showed "never" | Fixed |
| 6 | Email Access | Newly-populated timestamp rendered as a raw ISO string instead of a formatted date | Fixed |
| 3 · 7 | Full regression sweep | Re-verified every prior fix live, no new issues, zero console errors | Clean |

The two "fix only addressed the symptom" cases the CEO's section of the review specifically
called out: the Match Results expand-all mislabel (round 1 → still broken underneath in round
2) and the All Candidates data-mode empty state (fixed for one filter combination in round 1,
didn't compose with Needs-attention until round 2).

## Era 2 — security hardening, pipeline stage, deletion, and consent

### Round A — localhost binding + login rate limiting

Straightforward: rate limiting confirmed effective at exactly 5 attempts, lockout expiry
confirmed at 15 minutes, identical response for a locked-out real email vs. a nonexistent one
(no enumeration side channel), localhost binding confirmed via `lsof -iTCP -sTCP:LISTEN`. No
issues found.

### Round B — `.env` `API_HOST`/`API_PORT` override, three sub-rounds

Not a fresh feature — a real bug found immediately after Round A shipped: `.env` overrides for
`API_HOST`/`API_PORT` silently did nothing, because `.env` is only parsed by
`pydantic-settings` inside the Python process, never by the shell scripts that launch
`uvicorn`. Each of the three follow-up rounds found a shape the previous fix didn't cover:

| Round | Finding | Outcome |
|---|---|---|
| B1 | `.env` overrides silently ignored — shell never sees them | Fixed (targeted `grep`/`cut` extraction, not a `source`) |
| B2 | The B1 fix broke the *default* (no-override) path — `grep` finding nothing exits 1, which under `set -euo pipefail` inside a `$(...)` assignment killed the whole script silently | Fixed (`{ grep ... \|\| true; }`) |
| B3 | Quoted values, trailing whitespace, and CRLF line endings all produced a real `uvicorn` startup failure (`nodename nor servname provided`) — caught by feeding the *actual extracted value* into real `uvicorn`, not just inspecting the shell variable | Fixed, deduplicated into `scripts/env_value.sh` |
| B4 | Whitespace padded *inside* the quote marks (`API_HOST=" 0.0.0.0 "`) survived unquoting — the trim only ran once, before the quote-strip | Fixed (trim runs again after quote-stripping); 15/15 cases in `scripts/test_env_value.sh` |

Two edge cases were found and deliberately **not** fixed, documented instead: mismatched
quote types (`API_HOST="0.0.0.0'`), and a literal `#` inside a quoted value — both require
deliberately malformed `.env` syntax rather than a plausible real config shape.

### Round C — pipeline stage tracking

No bugs found. Verified: new matches default to `sourced`; the stage filter correctly narrows
to exactly the matching cards, tested at both a 1-result and many-result count; changing a
card's stage while the list is filtered to a *different* stage correctly makes the card
vanish from the filtered view and backfills the next item from pagination (`19 → 18` on the
"Showing X–Y of Z" count); Candidate Detail's "Pipeline across jobs" shows tier and stage
badges side by side as designed; the dashboard chart's math checked out exactly against a
seeded distribution (30 scored, 1 moved to Offer, 29 remained Sourced). One factual correction,
not a bug: a reported test count (163) was double-checked and confirmed *correct* — QA's own
"155 prior + 5 new = 160" arithmetic had undercounted the actual baseline by 3.

### Round D — per-candidate PII deletion + real-LLM consent gate

**Consent gate: no issues found**, tested extensively at both the API and UI layer — no-key-configured precedence over the consent check, the 428 response and confirmed-unchanged state
when consent is withheld, `consent_ack: true` recording correctly, consent asked exactly once
across repeated mock→real→mock→real toggles, and a **real backend process restart** confirmed
the designed split behavior precisely: the mock/real toggle itself resets to mock (in-memory,
by design) while consent stays granted (DB-persisted) — no re-prompt.

**Per-candidate delete: one real, meaningful bug.** The typed-`"DELETE"` confirmation UI and
the DB-side cascade (`Match`, `ResumeSource`) were both clean. The on-disk mirror cleanup had a
gap: two resume submissions on the same day for the same candidate land in the same mirror
directory (keyed on candidate + date, not per-submission); with different file extensions that
directory holds two resume files sharing one `meta.json`. Deleting that candidate reported
success (204) and fully emptied the database, but the second submission's resume file — real
PII, the candidate's name and email in plaintext — was left behind, silently, in a directory
the app no longer tracked anywhere. **Found in the app's own real sample data on a second
random pick**, not a constructed edge case.

Root cause: the original per-source deletion loop deleted `meta.json` while handling the first
source sharing that directory, then re-read it to safety-check the second source pointing at
the same directory, found it already gone, and defensively skipped rather than risk deleting
something unverified — silently orphaning the file instead. Fixed by grouping sources by
target directory first, reading `meta.json` once per directory before deleting anything in it,
then deleting every resume file in that group together. Confirmed via a regression test that
fails against the pre-fix code and passes after, then reproduced live a second time against
real sample-data-generated files (the identical two-extension-one-directory shape) to confirm
the fix holds outside the constructed test case too.

Also performed every round in this era: a **migration check** against a copy of the real,
populated database — confirmed each new column (`Match.pipeline_stage`, then
`User.real_llm_consent_given_at`) auto-migrated cleanly with correct defaults and zero
corruption of existing rows.

## Current test suite

`make test` — **169 passing**, 2 skipped, as of this entry (up from 132 at the start of Era 2).
No known-failing tests; three previously-noted pre-existing failures
(`test_oauth_status_route.py`, `test_scan_all_route.py` ×2, real-OAuth-env/job-registry-state
leakage into the test process, not a regression) have since cleared on their own as the test
process environment stabilized — reproduce a full `make test` run to confirm before assuming
they're still present.

## Cross-references

- [Project Log](project-log.md) — the narrative behind each fix above
- [Design Decisions](design-decisions.md) — ADR-010 through ADR-013 cover this era's choices
- [`reports/stakeholder-review.md`](../reports/stakeholder-review.md) — full Era 1 detail, four
  stakeholder perspectives
