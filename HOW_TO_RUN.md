# How to Run & Test Recruit Assistant

Quick-reference for running the app locally and walking through the golden path. For
deeper setup (real LLM keys, email OAuth registration, troubleshooting), see
[architecture/getting-started.md](architecture/getting-started.md).

## 0. One-time setup

```bash
cd /Users/mrithwik/projects/recruit-assistant
make setup              # installs backend deps into .venv, creates .env from .env.example
make install-frontend   # installs frontend node_modules
```

`.env` defaults to `USE_MOCK_LLM=true` and `USE_MOCK_EMAIL=true` — everything works with
**zero API keys**. Both are independent and also live-toggleable from the Scan Sources page
(flipping LLM mode to real for the first time shows a one-time consent dialog — see step 4).

## 1. Start the backend (Terminal 1)

```bash
cd /Users/mrithwik/projects/recruit-assistant
source .venv/bin/activate
make run
```

Wait for `Uvicorn running on http://127.0.0.1:8000`. The backend binds to localhost only by
default (`API_HOST` in `.env.example`), not every network interface — deliberate, see
[architecture/design-decisions.md](architecture/design-decisions.md) ADR-010. Verify in
another shell:

```bash
curl http://localhost:8000/health   # -> {"status":"ok"}
```

## 2. Start the frontend (Terminal 2)

```bash
cd /Users/mrithwik/projects/recruit-assistant
make run-frontend
```

Open **http://localhost:5173**.

## 3. Create your account and walk the golden path

The app is single-account — the first visit shows a **register** form; every visit after that
shows **login** instead (`POST /auth/register` 403s once an account exists, by design, not a
bug — see ADR-010). Failed logins lock that email out for 15 minutes after 5 attempts.

1. **Dashboard** — empty at first; fills in as you use the app below.
2. **Job Descriptions** — "+ Add another job description", give it a title and paste a JD.
3. **Scan Sources** — under "Local folders", enter a path to a folder with a few
   `.pdf`/`.docx`/`.txt` resumes, then "Scan folders now". No resumes handy? Make a throwaway one:
   ```bash
   mkdir -p ~/test-resumes
   echo "Jordan Rivera, Python/FastAPI, 4 years experience" > ~/test-resumes/jordan.txt
   ```
   Then point the Scan Sources folder picker at `~/test-resumes`.
4. **Match Results** — pick the job in the dropdown, click "Run matching". Color-coded
   score badges (quality/tier) appear alongside a separate pipeline-stage badge/dropdown
   (status — sourced through placed/declined, independent of match quality); click "Details"
   for match reasons/gaps/missing info; try the 🟢/🔴 flag buttons and "Draft email".
5. **Candidate Detail** — click a candidate's name to see their full profile, notes, history,
   source documents, and pipeline status across every job they're matched to.
6. **Criteria** — see the built-in filters, add a custom one, try "Rescan".
7. **Search History** — the matching run you just did shows up here.

In mock mode, scores/summaries are canned (fixed ~72 score, "good_match" tier) — that's
expected; it proves the pipeline runs end-to-end without needing API keys, not that the
matching is discriminating between good/bad resumes yet.

## 4. Test with real LLM scoring

Edit `.env`:

```
USE_MOCK_LLM=false
OPENROUTER_API_KEY=sk-or-...
```

Restart the backend (`Ctrl+C`, then `make run` again). The first time you flip real mode on
from the Scan Sources page (or restart with `USE_MOCK_LLM=false` already set), a one-time
consent dialog explains that resume text and job descriptions will be sent to your configured
provider — accept it once and it's remembered for this installation going forward (it's
persisted on your account, not reset by future restarts, even though the mock/real toggle
itself resets to mock on every restart by design). Re-run matching — scores/reasons should now
be real and differentiated per resume.

## 5. Run the automated tests

```bash
make test
```

169 tests as of this writing (auth, rate limiting, identity resolution, tier + pipeline-stage
scoring, folder/email ingestion, per-candidate deletion incl. on-disk mirror cleanup, mock-mode
consent gate, dashboard aggregation, golden-set matching harness). To also check live-model
scores land in the expected tier bands:

```bash
RUN_LIVE_GOLDEN=true OPENROUTER_API_KEY=sk-or-... make test
```

## 6. Test at scale with a generated sample dataset

For testing beyond a handful of hand-made resumes — thousands of applications and
follow-ups, spread across a two-year date range, in a dozen writing personas, with a
deliberate slice of missing/garbled data:

```bash
python scripts/generate_sample_data.py     # ~20s, writes sample_data/ (gitignored)
```

This gives you two ways to load it, testable together:

**Folder scan (works immediately):** Scan Sources → Local folders → add the full path to
`sample_data/resumes` printed at the end of generation, include subfolders, Scan. File
dates are set to match each item's synthetic submission date, so the date-range picker
works against it everywhere (Scan Sources, Candidate Results, Search History).

**Mock email scan (no OAuth needed):** add to `.env`:

```
MOCK_EMAIL_FIXTURES_PATH=/absolute/path/to/sample_data/emails_manifest.json
```

Restart the backend — a demo mailbox (`demo@mock.local`) auto-appears in Email Access /
Scan Sources. Scan it like a real mailbox and it'll ingest the same dataset through the
email path instead of (or alongside) folder scanning.

Scanning both paths against the same generated people is a good test of cross-source
identity merging — most follow-ups reference a real prior application by the same email
address, so they should merge into one candidate profile, not create a duplicate.

Regenerate with `--seed N` for a different (but still reproducible) dataset, or
`--initial`/`--followups` to change the volume. See `sample_data/README.md` (written
alongside the data) for exact counts and what's deliberately imperfect in it.

## Stopping / restarting

`Ctrl+C` in each terminal stops that server. If a port seems stuck:

```bash
lsof -ti :8000 | xargs kill -9   # backend
lsof -ti :5173 | xargs kill -9   # frontend
```

## Troubleshooting

- **"No LLM provider configured"** — set `USE_MOCK_LLM=true` in `.env`, or set an API key.
- **Scan finds 0 resumes** — only `.pdf`, `.docx`, `.txt` are supported.
- **Frontend loads but API calls fail** — make sure the backend (port 8000) is running;
  the frontend proxies `/api/*` to it and shows nothing useful if it's down.
- **Email Access tab errors on connect** — expected until you register an OAuth app; see
  [architecture/getting-started.md](architecture/getting-started.md#5-enable-email-scanning-gmail--outlook-oauth).
  Folder scanning works independently of email setup.
- **"Invalid or expired session" / repeatedly bounced to login** — the login lockout is
  per-email, 5 failed attempts, 15 minutes; wait it out or double-check the password.
- **Flipping real LLM mode on does nothing / a dialog appears instead** — expected the first
  time only, see step 4 above; it's a one-time consent step, not a bug.

## Roadmap / what's next

- **Speed** — mailbox scanning and LLM matching both have known, unimplemented optimizations
  (parallelizing the per-resume ingest loop, offloading blocking parse/OCR work, retry/backoff
  + higher LLM concurrency, reusing the existing semantic summary instead of full resume text
  in scoring prompts). Fully mapped, not yet built.
- **A locally-hosted, recruiting-fine-tuned LLM** — long-term: replacing or supplementing the
  OpenRouter/OpenAI real-mode path with a small open-source model fine-tuned specifically for
  resume/JD scoring, run locally, to cut real-mode LLM cost toward zero for an established
  installation. Not yet scoped — would need a training-data plan (this app's own judge-verified
  match history is a plausible source), a decision on model size vs. laptop-hardware
  feasibility, and a quality bar to clear before it could replace OpenRouter's frontier models
  as the default rather than an opt-in alternative.
