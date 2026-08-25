<!-- Version: v0 | Last updated: 2026-08-01 | Status: current -->

# Frontend Architecture

React 18 + TypeScript + Vite. Zustand for state (one store per resource, no providers,
module-level singletons — same rationale as Prodigon's ADR-001). Tailwind CSS v4 for styling
with class-based dark mode.

## Navigation

`lib/nav.ts` is the single source of truth for the 8 nav tabs, rendered by
`components/layout/sidebar.tsx` (left nav — the only navigation surface; an earlier version also
had a top dropdown mirroring it per requirement 1.2, but it was removed as redundant once the
sidebar was in place). `components/layout/header.tsx` reads the current route from it just to show
a breadcrumb-style page label next to the logo.

Draft Email (2.6) is not a standalone tab — it's a modal opened from a candidate match row
(`components/candidates/draft-email-modal.tsx`), since it only makes sense in the context of
a specific match.

## Pages (`src/pages/`)

| Page | Backs |
|---|---|
| `jobs-page.tsx` | 2.1 — searchable, paginated (10/page) job list; the operational hub — inline criteria + scan/rescan per job |
| `scan-page.tsx` | 2.2 — folder picker + connected-mailbox picker + shared date range, both live |
| `email-access-page.tsx` | 2.3 — connect/disconnect Gmail/Outlook |
| `connections-page.tsx` | 2.4 — Phase 2 stub (company server / cloud) |
| `results-page.tsx` | 2.5 — color-coded matches, top-N, flags, expandable reasons |
| `criteria-page.tsx` | requirement 5 — built-in + custom criteria, rescan trigger |
| `history-page.tsx` | 2.7 — past search runs |
| `screening-sources-page.tsx` | 2.10 — active vs. planned sources |

## Stores (`src/stores/`)

`jobs-store`, `matches-store`, `scan-store`, `criteria-store`, `history-store`,
`candidates-store`, `settings-store` (theme), `toast-store`. Each wraps the corresponding
`lib/api.ts` calls and holds only the state its page(s) need — no global app state blob.

## API client (`src/lib/api.ts`)

Thin `fetch` wrapper against `/api/v1/*`. In dev, `vite.config.ts` proxies `/api` and
`/health` straight to the backend on `:8000` — no CORS dance, matching Prodigon's dev-mode
convention.

## Color coding (2.5)

`components/ui/match-badge.tsx` maps the five `MatchTier` values to shade bands: darker green
for great matches, lighter green for good, orange for average, red shades for poor/red-flagged
— implementing the requirement directly rather than through a generic "status color" system,
since the tiers are a fixed, meaningful set.
