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
**zero API keys**. Both are independent and also live-toggleable from the Scan Sources page.

## 1. Start the backend (Terminal 1)

```bash
cd /Users/mrithwik/projects/recruit-assistant
source .venv/bin/activate
make run
```

Wait for `Uvicorn running on http://0.0.0.0:8000`. Verify in another shell:

```bash
curl http://localhost:8000/health   # -> {"status":"ok"}
```

## 2. Start the frontend (Terminal 2)

```bash
cd /Users/mrithwik/projects/recruit-assistant
make run-frontend
```

Open **http://localhost:5173**.

## 3. Walk the golden path

1. **Job Descriptions** — "+ Add another job description", give it a title and paste a JD.
2. **Scan Sources** — under "Local folders", enter a path to a folder with a few
   `.pdf`/`.docx`/`.txt` resumes, then "Scan folders now". No resumes handy? Make a throwaway one:
   ```bash
   mkdir -p ~/test-resumes
   echo "Jordan Rivera, Python/FastAPI, 4 years experience" > ~/test-resumes/jordan.txt
   ```
   Then point the Scan Sources folder picker at `~/test-resumes`.
3. **Candidate Results** — pick the job in the dropdown, click "Run matching". Color-coded
   score badges appear; click "Details" for match reasons/gaps/missing info; try the 🟢/🔴
   flag buttons and "Draft email".
4. **Criteria** — see the built-in filters, add a custom one, try "Rescan".
5. **Search History** — the matching run you just did shows up here.

In mock mode, scores/summaries are canned (fixed ~72 score, "good_match" tier) — that's
expected; it proves the pipeline runs end-to-end without needing API keys, not that the
matching is discriminating between good/bad resumes yet.

## 4. Test with real LLM scoring

Edit `.env`:

```
USE_MOCK_LLM=false
OPENROUTER_API_KEY=sk-or-...
```

Restart the backend (`Ctrl+C`, then `make run` again) and re-run matching — scores/reasons
should now be real and differentiated per resume.

## 5. Run the automated tests

```bash
make test
```

13 tests (identity resolution, tier scoring, folder ingestion, golden-set matching harness).
To also check live-model scores land in the expected tier bands:

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
