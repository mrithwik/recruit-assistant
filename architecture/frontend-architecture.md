<!-- Version: v0 | Last updated: 2026-09-01 | Status: current -->

# Frontend Architecture

React 18 + TypeScript + Vite. Zustand for state (one store per resource, no providers,
module-level singletons — same rationale as Prodigon's ADR-001). Tailwind CSS v4 for styling
with class-based dark mode.

## Auth

`login-page.tsx` + `auth-store.ts` — register-once (the backend 403s a second registration
attempt, so the UI routes straight to login once `GET /auth/status` reports `setup_complete`),
bearer token stored client-side, attached by `lib/api.ts`'s `request()` wrapper to every call.
A 401 anywhere clears the token and bounces to login.

## Navigation

`lib/nav.ts` is the single source of truth for the nav tabs, rendered by
`components/layout/sidebar.tsx` (left nav — the only navigation surface; an earlier version also
had a top dropdown mirroring it per requirement 1.2, but it was removed as redundant once the
sidebar was in place). `components/layout/header.tsx` reads the current route from it just to show
a breadcrumb-style page label next to the logo, alongside the global All/Real/Mock data-mode
toggle (`components/layout/data-mode-toggle.tsx`).

Draft Email (2.6) is not a standalone tab — it's a modal opened from a candidate match row
(`components/candidates/draft-email-modal.tsx`), since it only makes sense in the context of
a specific match.

## Pages (`src/pages/`)

| Page | Backs |
|---|---|
| `dashboard-page.tsx` | 1 — KPIs, inflow/tier/pipeline-stage charts, jobs snapshot, recent activity, pending-updates banner |
| `jobs-page.tsx` | 2.1 — searchable, paginated (10/page) job list; the operational hub — inline criteria + scan/rescan per job |
| `scan-page.tsx` | 2.2 — folder picker + connected-mailbox picker + shared date range, mock/real toggles, sample-data generator, maintenance tasks, danger zone |
| `email-access-page.tsx` | 2.3 — connect/disconnect Gmail/Outlook |
| `connections-page.tsx` | 2.4 — Phase 2 stub (company server / cloud) |
| `results-page.tsx` | 2.5 — color-coded matches, top-N, flags, pipeline-stage badge/dropdown/filter, expandable reasons, CSV export |
| `all-candidates-page.tsx` | filterable candidate pool across every job (skills, status, visa, experience, date range) |
| `candidate-detail-page.tsx` | one candidate's full profile — pipeline across jobs, notes, history, source documents, per-candidate danger zone |
| `criteria-page.tsx` | requirement 5 — built-in + custom criteria, rescan trigger |
| `history-page.tsx` | 2.7 — past search runs |
| `screening-sources-page.tsx` | 2.10 — active vs. planned sources |
| `scan-logs-page.tsx` | full paginated ingest log, "see more" beyond the Scan Sources page's recent slice |
| `login-page.tsx` / `landing-page.tsx` / `not-found-page.tsx` | auth entry, marketing/root redirect, catch-all route |

## Stores (`src/stores/`)

`auth-store`, `jobs-store`, `matches-store`, `scan-store`, `criteria-store`, `history-store`,
`candidates-store`, `dashboard-store`, `data-mode-store` (persisted), `bulk-jobs-store`
(multi-job bulk match/update sequencing), `maintenance-store`, `settings-store` (theme),
`toast-store`. Each wraps the corresponding `lib/api.ts` calls and holds only the state its
page(s) need — no global app state blob.

## API client (`src/lib/api.ts`)

Thin `fetch` wrapper against `/api/v1/*`, attaching the bearer token from `auth-store` and
clearing it on a 401. In dev, `vite.config.ts` proxies `/api` and `/health` straight to the
backend on `:8000` (`VITE_BACKEND_PORT` env-overridable, used to point a dev server at an
isolated test instance) — no CORS dance, matching Prodigon's dev-mode convention.

## Color coding

`components/ui/match-badge.tsx` maps the five `MatchTier` values (quality) to shade bands:
darker green for great matches, lighter green for good, orange for average, red shades for
poor/red-flagged — implementing requirement 2.5 directly rather than through a generic
"status color" system, since the tiers are a fixed, meaningful set.

`components/ui/pipeline-stage-badge.tsx` maps the 7 `PipelineStage` values (status) to a
**deliberately different** hue family — slate → sky → blue → violet → amber → emerald,
declined stays neutral rather than red — since mixing tier's green-to-red quality scale with
stage's badge would read as "how good" when it means "how far along." Both badges render
side by side wherever a match appears (Match Results, Candidate Detail's per-job list).

## Dashboard charts (`components/dashboard/`)

`tier-chart.tsx` / `pipeline-chart.tsx` — ordinal bar charts via Recharts, colors from
`lib/chart-colors.ts`'s validated palette (light/dark, CVD-safe categorical order). Zero-filled
against a fixed ordinal list so every tier/stage always renders, even at zero, rather than
silently omitting an empty bucket.
