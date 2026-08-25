<!-- Version: v0 | Last updated: 2026-08-01 | Status: current -->

# Recruit Assistant Architecture Documentation

Local-first AI recruiting assistant — scans resumes from email and folders, matches them
against job descriptions with LLM scoring, and helps a recruiter act on the results.

## Document Index

| Document | Purpose |
|----------|---------|
| [How It Works](how-it-works.html) | Illustrated, plain-language walkthrough — start here if you're non-technical or just want the big picture visually |
| [System Overview](system-overview.md) | High-level architecture, tech stack, repo structure |
| [Backend Architecture](backend-architecture.md) | FastAPI app internals: scanning, matching, storage, DI |
| [Frontend Architecture](frontend-architecture.md) | React SPA: nav, pages, stores, API client |
| [API Reference](api-reference.md) | Endpoint reference with schemas |
| [Data Flow](data-flow.md) | Ingestion, matching, and draft-email sequence diagrams |
| [Design Decisions](design-decisions.md) | ADRs — why things are built this way |
| [Project Log](project-log.md) | Chronological history — every planning decision and build phase |
| [Getting Started](getting-started.md) | Setup guide, mock mode, OAuth app registration |
| [Infrastructure](infrastructure.md) | Local run modes, data layout, path to production |

## Reading Order

**New to the project?**
1. [How It Works](how-it-works.html) — the big picture, visually, no technical background needed
2. [Getting Started](getting-started.md) — run it locally in mock mode
3. [System Overview](system-overview.md) — the technical big picture
4. [Project Log](project-log.md) — how we got here and what's next
5. [Data Flow](data-flow.md) — how a resume becomes a scored match

**Backend developer?** [Backend Architecture](backend-architecture.md) → [API Reference](api-reference.md)

**Frontend developer?** [Frontend Architecture](frontend-architecture.md) → [API Reference](api-reference.md)

**Understanding design choices?** [Design Decisions](design-decisions.md)

## Versioning Policy

Version 0 (v0) — initial architecture as of 2026-08-01. Version when service boundaries,
storage backends, or API contracts change materially; not for typo fixes or added detail.

### Changelog

| Version | Date | Summary |
|---------|------|---------|
| v0 | 2026-08-01 | Initial architecture: single-process FastAPI backend, folder + email ingestion converging on one pipeline, two-stage LLM matching with judge review, React/Vite frontend with all 8 nav tabs. |
