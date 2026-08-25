# Security

This is a personal, local-first tool that handles candidate PII (names, contact
info, resumes) and OAuth credentials for connected email accounts. It's not
open to outside contributions, but the practices below are worth stating
explicitly since real personal data flows through it.

## How data is protected

- **Passwords** are hashed with PBKDF2 before storage — never kept in plain
  text (see `backend/app/auth/security.py`).
- **Email OAuth tokens** (Gmail/Outlook) are stored in the OS keychain via
  `keyring`, never in the SQLite database or a config file — only a
  keychain reference key is persisted (see `backend/app/email_auth/oauth.py`).
- **Everything else is local by default**: candidate data, resumes, and the
  SQLite database live on disk under `data/`, which is gitignored and never
  leaves the machine unless you explicitly export it.
- **Read-only mail scopes only** — the Gmail/Outlook OAuth flow requests
  `gmail.readonly` / `Mail.Read`, never write or send access.

## Reporting a vulnerability

This repo has a single maintainer. If you find a security issue, open a
private security advisory on GitHub (Security tab → Report a vulnerability)
rather than a public issue, or email the maintainer directly.

## Scope

There is no bug bounty and no SLA on response time — this is maintained on
a best-effort basis.
