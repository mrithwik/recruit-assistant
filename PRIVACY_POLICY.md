# Privacy Policy

_Last updated: 2026-08-26_

Recruit Assistant is a **local-first, single-user application**. This policy
exists to satisfy Google/Microsoft OAuth consent-screen requirements and to be
transparent about how the app handles data — not because data leaves your
machine, because it doesn't.

## What data the app accesses

When you connect a Gmail or Outlook account, Recruit Assistant requests
**read-only** access to your mailbox (`gmail.readonly` / `Mail.Read`) plus
your email address (`userinfo.email`), in order to:

- Scan for resume attachments (PDF/DOCX) within a date range you choose.
- Extract candidate information (name, contact details, experience) from
  those resumes for matching against job descriptions you've entered.

The app never sends, deletes, or modifies anything in your mailbox, and never
requests any scope beyond read access to mail and your basic profile email.

## Where data is stored

- All extracted candidate data, resumes, and job descriptions are stored
  **locally on your machine**, in a SQLite database and files under `data/`
  (see the repo's `.gitignore` — this directory is never committed or synced
  anywhere).
- OAuth tokens (Gmail/Outlook) are stored in your operating system's native
  keychain via the `keyring` library — never in the database, never in a
  config file, never transmitted anywhere except directly to
  Google's/Microsoft's own token-refresh endpoints.
- Passwords for the app's own local login are hashed (PBKDF2) before storage.

## What data leaves your machine

- OAuth token exchange/refresh requests go directly to Google's or
  Microsoft's servers, as required by the OAuth protocol itself.
- If you configure a real LLM provider (OpenRouter/OpenAI) instead of the
  built-in mock mode, resume text and job descriptions are sent to that
  provider's API to generate match scores — this is opt-in and off by
  default (`USE_MOCK_LLM=true` out of the box).
- Nothing else. There is no analytics, telemetry, or third-party tracking of
  any kind in this application.

## Data retention and deletion

Since everything lives on your machine, you control retention entirely:
deleting the `data/` directory removes all candidate/resume/job data;
disconnecting an email account in the app removes its token from your OS
keychain.

## Contact

This is a single-maintainer, personal project. For questions, open an issue
on the GitHub repository.
