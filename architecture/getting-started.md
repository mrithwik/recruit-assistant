<!-- Version: v0 | Last updated: 2026-08-01 | Status: current -->

# Getting Started

## Prerequisites

Python 3.11+, Node.js 20+.

## 1. Backend setup (mock mode — no API keys needed)

```bash
make setup            # pip install -e ".[dev]", creates .env from .env.example
make run               # starts FastAPI on :8000
curl http://localhost:8000/health
```

`.env` defaults to `USE_MOCK=true` — the whole pipeline (parsing, matching, judge, even
email ingestion via a fixture inbox) runs with zero external API calls. This is also what
`make test` runs against.

## 2. Frontend setup

```bash
make install-frontend
make run-frontend      # Vite dev server on :5173, proxies /api and /health to :8000
```

Open http://localhost:5173.

## 3. Try the golden path (folder scanning)

1. Job Descriptions tab → "+ Add another job description"
2. Scan Sources tab → add a local folder path containing a few .pdf/.docx/.txt resumes → Scan folders now
3. Candidate Results tab → select the job → Run matching
4. Expand a result to see match reasons, missing info; flag green/red; Draft email

## 4. Enable real LLM scoring (OpenRouter or OpenAI)

Edit `.env`:

```
USE_MOCK=false
OPENROUTER_API_KEY=sk-or-...
# or, as a fallback provider:
OPENAI_API_KEY=sk-...
```

Restart the backend. Run `RUN_LIVE_GOLDEN=true OPENROUTER_API_KEY=... python -m pytest
backend/tests/golden/ -v` to check the golden fixtures score in the expected tier bands
before relying on it for real candidates.

## 5. Enable email scanning (Gmail / Outlook OAuth)

Email scanning requires registering an OAuth app — this is a one-time setup per provider:

**Gmail:**
1. Google Cloud Console → new project → enable the Gmail API
2. OAuth consent screen → add the `gmail.readonly` scope
3. Credentials → OAuth client ID (type: Web application) → redirect URI:
   `http://localhost:8000/api/v1/email-accounts/callback/google`
4. Put the client ID/secret in `.env` as `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET`

**Outlook:**
1. Azure Portal → App registrations → new registration
2. API permissions → Microsoft Graph → `Mail.Read` (delegated)
3. Redirect URI: `http://localhost:8000/api/v1/email-accounts/callback/microsoft`
4. Put the client ID/secret in `.env` as `MS_OAUTH_CLIENT_ID` / `MS_OAUTH_CLIENT_SECRET`

Restart the backend, then go to the Email Access tab and connect an account. Tokens are
stored in your OS keychain, never in the app's database.

## Troubleshooting

- **"No LLM provider configured"** — set `USE_MOCK=true`, or set an API key.
- **"GOOGLE_OAUTH_CLIENT_ID not configured"** — expected until you complete step 5 above;
  folder scanning works independently of email setup.
- **Scan finds 0 resumes** — only `.pdf`, `.docx`, `.txt` are supported (`SUPPORTED_EXTENSIONS`
  in `scanning/folder_ingestor.py`).
