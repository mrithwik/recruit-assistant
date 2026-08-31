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

`.env` defaults to `USE_MOCK_LLM=true` and `USE_MOCK_EMAIL=true` — the whole pipeline
(parsing, matching, judge, even email ingestion via a fixture inbox) runs with zero external
API calls. This is also what `make test` runs against. Both are independent (a real-Gmail
scan doesn't require real LLM calls too) and both are also live-toggleable from the Scan
Sources page without restarting the backend.

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
USE_MOCK_LLM=false
OPENROUTER_API_KEY=sk-or-...
# or, as a fallback provider:
OPENAI_API_KEY=sk-...
```

Restart the backend. Run `RUN_LIVE_GOLDEN=true OPENROUTER_API_KEY=... python -m pytest
backend/tests/golden/ -v` to check the golden fixtures score in the expected tier bands
before relying on it for real candidates.

## 5. Enable email scanning (Gmail / Outlook OAuth)

Email scanning requires registering an OAuth app — this is a one-time setup per provider. For
testing against your own real inbox rather than mock mode, the Google side has one easy-to-miss
step (below) that blocks the whole flow if skipped.

**Gmail:**
1. [Google Cloud Console](https://console.cloud.google.com/) → new project → APIs & Services →
   enable the **Gmail API**.
2. OAuth consent screen → External (unless you have a Workspace org) → add scopes
   `gmail.readonly` and `userinfo.email` (the second is what lets the app show the real
   connected address instead of a placeholder — see project-log section 17).
3. **Add yourself as a test user**, on the same consent-screen page. This step is easy to
   miss and the failure mode is confusing: Google apps start in "Testing" publishing status,
   and an unverified app in that status **rejects sign-in from any Google account not listed
   as a test user** — including your own, if you skip this. There's no verification review
   needed for personal/local use, just this allowlist entry.
4. Credentials → OAuth client ID (type: Web application) → redirect URI:
   `http://localhost:8000/api/v1/email-accounts/callback/google`
5. Put the client ID/secret in `.env` as `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET`

**Outlook:**
1. [Azure Portal](https://portal.azure.com/) → App registrations → new registration.
2. API permissions → Microsoft Graph → `Mail.Read` (delegated) → grant admin consent if
   prompted (not required for a personal Microsoft account).
3. Certificates & secrets → new client secret (this is `MS_OAUTH_CLIENT_SECRET`).
4. Redirect URI (under Authentication, type "Web"):
   `http://localhost:8000/api/v1/email-accounts/callback/microsoft`
5. Put the client ID/secret in `.env` as `MS_OAUTH_CLIENT_ID` / `MS_OAUTH_CLIENT_SECRET`

Restart the backend, then go to the Email Access tab and connect an account — the connected
list should show your real email address, not a placeholder. Tokens (plus what's needed to
refresh them — Google access tokens expire in about an hour) are stored in your OS keychain,
never in the app's database or a config file.

## 6. Enable OCR for scanned/image resumes (optional)

A resume that's a scanned image rather than a real text PDF (common with older or
paper-scanned applications) extracts as empty text by default, producing a mostly-blank
candidate profile. OCR fixes this but needs both a Python package group and a system OCR
engine — neither is installed by default since most resumes don't need it:

```bash
pip install -e ".[ocr]"       # pytesseract + pdf2image
brew install tesseract poppler   # macOS; apt-get install tesseract-ocr poppler-utils on Linux
```

Nothing else to configure — `scanning/parser.py` only tries OCR when normal text extraction
comes back thin, and degrades silently (no OCR attempt, same behavior as before this existed)
if either the Python packages or the system binaries aren't present.

## Troubleshooting

- **"No LLM provider configured"** — set `USE_MOCK_LLM=true`, or set an API key.
- **"GOOGLE_OAUTH_CLIENT_ID not configured"** — expected until you complete step 5 above;
  folder scanning works independently of email setup.
- **Google sign-in says the app is blocked / not verified, even for your own account** — you
  weren't added as a test user on the OAuth consent screen (step 3 above). This is the most
  common snag connecting a real Gmail account.
- **A connected account still shows a placeholder instead of the real address, or a scan
  starts failing partway through with auth errors** — reconnect the account; both are
  symptoms of a token stored before the profile-fetch/refresh support existed (see
  project-log section 17).
- **Scan finds 0 resumes** — only `.pdf`, `.docx`, `.txt` are supported (`SUPPORTED_EXTENSIONS`
  in `scanning/folder_ingestor.py`).
