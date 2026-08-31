import { useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { AlertTriangle, ListFilter, Mail, RefreshCw, Search, Users, X } from "lucide-react";
import { useCandidatesStore, CANDIDATES_PAGE_SIZE } from "../stores/candidates-store";
import { useToastStore } from "../stores/toast-store";
import { useDataModeStore } from "../stores/data-mode-store";
import { PageHeader } from "../components/ui/page-header";
import { Card } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Button } from "../components/ui/button";
import { EmptyState } from "../components/ui/empty-state";
import { SourceBadges } from "../components/ui/source-badges";
import { SortSelect } from "../components/ui/sort-select";
import { TimingBadge } from "../components/ui/timing-badge";
import { MultiSelectFilter } from "../components/ui/multi-select-filter";
import { ExperienceRangeFilter } from "../components/ui/experience-range-filter";
import { ProgressBar, useSimulatedProgress } from "../components/ui/progress-bar";
import { CancelJobButton } from "../components/ui/cancel-job-button";
import type { Candidate } from "../lib/types";

const RESCAN_ALL_ESTIMATED_SECONDS = 45;

type SortKey = "recent" | "oldest" | "name_asc" | "name_desc";

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: "recent", label: "Most recent" },
  { value: "oldest", label: "Oldest first" },
  { value: "name_asc", label: "Name A–Z" },
  { value: "name_desc", label: "Name Z–A" },
];

// Reached from the dashboard's "Total candidates" tile — a paginated browse
// of the whole candidate pool, independent of any one job (Candidate
// Results is job-scoped; this isn't). Search/sort/pagination all run
// server-side (see /candidates route + candidates-store) — this page never
// holds more than one page of candidates in memory, unlike the old version
// which loaded the entire pool up front and filtered/sliced it client-side.
export function AllCandidatesPage() {
  const {
    candidates,
    total,
    query,
    sort,
    page,
    loading,
    lastElapsedSeconds,
    skills,
    employmentStatuses,
    workVisaStatuses,
    experienceMin,
    experienceMax,
    needsAttention,
    facets,
    fetchCandidates,
    fetchFacets,
    setQuery,
    setSort,
    setPage,
    toggleSkill,
    toggleEmploymentStatus,
    toggleWorkVisaStatus,
    setExperienceRange,
    setNeedsAttention,
    clearAdvancedFilters,
    rescanAll,
    cancelRescanAll,
    rescanningAll,
    rescanAllProgress,
    resumeRescanAllIfAny,
  } = useCandidatesStore();
  const push = useToastStore((s) => s.push);
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const dataMode = useDataModeStore((s) => s.dataMode);
  const { pct: rescanPct, remainingSeconds: rescanRemaining, overrun: rescanOverrun } = useSimulatedProgress(
    RESCAN_ALL_ESTIMATED_SECONDS,
    rescanningAll,
  );

  // Search text and the filter chips below are staged in the store as the
  // user picks them, but nothing is fetched until they explicitly hit
  // "Apply filters" (or press Enter in search) — picking several filters
  // one at a time used to fire a request after every click. Sort and
  // pagination act on whatever filter set is already applied, so those
  // still fetch immediately.
  useEffect(() => {
    // Reattaches to an already-running "Rescan all" job if one was started
    // before a refresh/reopen — see candidates-store's rescanAllJobId.
    resumeRescanAllIfAny().catch(() => {});
  }, []);

  // Also covers the initial load. The global "All / Real / Mock" toggle
  // (header) changes what counts as "the pool" — re-fetch immediately
  // rather than waiting for the next manual "Apply filters" click, since
  // switching data sets is its own deliberate action already. Arriving via
  // a "needs attention" link (Dashboard's KPI tile / chart) is an explicit
  // request to see that filtered view, so it's applied here — before the
  // one fetch this effect makes — rather than firing a second, racing
  // fetch afterward.
  useEffect(() => {
    if (searchParams.get("needs_attention") === "true") {
      setNeedsAttention(true);
    }
    fetchFacets().catch((e) => push(String(e), "error"));
    setPage(1);
    fetchCandidates().catch((e) => push(String(e), "error"));
  }, [dataMode]);

  function handleRescanAll() {
    rescanAll().catch((e) => push(String(e), "error"));
  }

  function applyFilters() {
    setPage(1);
    fetchCandidates().catch((e) => push(String(e), "error"));
  }

  // Unlike the staged multi-select filters below (skills/status/visa/
  // experience — picked, then applied together via "Apply filters"),
  // "Needs attention" is a single on/off toggle a recruiter reaches for to
  // jump straight to red-flagged or incomplete profiles — it applies the
  // moment it's clicked rather than waiting for a second click.
  function toggleNeedsAttention() {
    setNeedsAttention(!needsAttention);
    fetchCandidates().catch((e) => push(String(e), "error"));
  }

  function changeSort(v: SortKey) {
    setSort(v);
    fetchCandidates().catch((e) => push(String(e), "error"));
  }

  function changePage(p: number) {
    setPage(p);
    fetchCandidates().catch((e) => push(String(e), "error"));
  }

  const totalPages = Math.max(1, Math.ceil(total / CANDIDATES_PAGE_SIZE));
  const hasAdvancedFilters =
    skills.length > 0 || employmentStatuses.length > 0 || workVisaStatuses.length > 0 || experienceMin !== undefined || experienceMax !== undefined;
  const hasAnyFilters = hasAdvancedFilters || needsAttention;

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader
        title="All Candidates"
        description="Every candidate in the pool, independent of any one job — search by name, email, or skill."
        action={
          <div className="flex items-center gap-2">
            <TimingBadge seconds={lastElapsedSeconds} />
            <span className="rounded-full bg-zinc-100 px-3 py-1 text-xs font-semibold text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
              {total} total
            </span>
            <Button
              variant="secondary"
              size="sm"
              icon={<RefreshCw size={13} />}
              loading={rescanningAll}
              onClick={handleRescanAll}
              title="One combined pass over every connected account and known folder"
            >
              Rescan all for updates
            </Button>
          </div>
        }
      />

      {rescanningAll && (
        <div className="mb-4">
          <ProgressBar
            pct={rescanPct}
            label="Rescanning all connected sources…"
            remainingSeconds={rescanRemaining}
            overrun={rescanOverrun}
          />
          <div className="mt-1 flex items-center justify-between">
            {rescanAllProgress ? (
              <p className="text-xs text-zinc-500 dark:text-zinc-400">
                {rescanAllProgress.resumes_found} resume(s) processed — {rescanAllProgress.candidates_created} new,{" "}
                {rescanAllProgress.candidates_updated} updated, {rescanAllProgress.duplicates_skipped} unchanged
                {rescanAllProgress.errors.length > 0 && `, ${rescanAllProgress.errors.length} error(s)`}
              </p>
            ) : (
              <span />
            )}
            <CancelJobButton onCancel={cancelRescanAll} />
          </div>
        </div>
      )}

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[200px]">
          <Search size={14} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-400" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && applyFilters()}
            placeholder="Search name, email, or skill…"
            className="pl-8"
          />
        </div>
        <SortSelect value={sort as SortKey} onChange={changeSort} options={SORT_OPTIONS} />
        <button
          type="button"
          onClick={toggleNeedsAttention}
          title="Red-flagged, or missing required info, on at least one job"
          className={`flex shrink-0 items-center gap-1.5 rounded-lg border px-3 py-2 text-sm font-medium transition-colors ${
            needsAttention
              ? "border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-700 dark:bg-amber-500/10 dark:text-amber-400"
              : "border-zinc-200 bg-white text-zinc-600 hover:border-amber-300 hover:text-amber-700 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300 dark:hover:border-amber-700 dark:hover:text-amber-400"
          }`}
        >
          <AlertTriangle size={13} /> Needs attention
        </button>
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <MultiSelectFilter label="Skills" options={facets?.skills ?? []} selected={skills} onToggle={toggleSkill} />
        <MultiSelectFilter
          label="Employment status"
          options={facets?.employment_statuses ?? []}
          selected={employmentStatuses}
          onToggle={toggleEmploymentStatus}
          humanizeLabels
        />
        <MultiSelectFilter
          label="Work authorization"
          options={facets?.work_visa_statuses ?? []}
          selected={workVisaStatuses}
          onToggle={toggleWorkVisaStatus}
          humanizeLabels
        />
        <ExperienceRangeFilter
          min={experienceMin}
          max={experienceMax}
          ceiling={Math.max(1, Math.ceil(facets?.experience_years_max ?? 0))}
          onChange={setExperienceRange}
        />
        <Button size="sm" icon={<ListFilter size={13} />} loading={loading} onClick={applyFilters}>
          Apply filters
        </Button>
        {hasAnyFilters && (
          <button
            type="button"
            onClick={() => {
              clearAdvancedFilters();
              applyFilters();
            }}
            className="flex items-center gap-1 text-xs font-medium text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300"
          >
            <X size={12} /> Clear filters
          </button>
        )}
      </div>

      {!loading && total === 0 && !query && !hasAnyFilters && (
        <EmptyState
          icon={<Users size={20} />}
          title="No candidates yet"
          description="Scan a local folder or connected mailbox from Scan Sources to build the pool."
        />
      )}

      {!loading && total === 0 && (query || hasAnyFilters) && (
        <p className="py-8 text-center text-sm text-zinc-400">
          {query
            ? `No candidates match "${query}".`
            : needsAttention && !hasAdvancedFilters
              ? "No candidates currently need attention — nothing red-flagged or missing info."
              : "No candidates match the current filters."}
        </p>
      )}

      <div className="flex flex-col gap-2">
        {candidates.map((c: Candidate) => (
          <Card
            key={c.id}
            interactive
            className="cursor-pointer p-3"
            onClick={() => navigate(`/app/candidates/${c.id}`)}
          >
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="font-medium text-zinc-900 dark:text-white">
                  {c.legal_first_name || c.legal_last_name ? `${c.legal_first_name} ${c.legal_last_name}`.trim() : c.email || "Unnamed candidate"}
                </p>
                <p className="mt-0.5 line-clamp-1 text-sm text-zinc-500 dark:text-zinc-400">
                  {c.semantic_summary || "No summary yet"}
                </p>
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1 text-xs text-zinc-400">
                <span>Submitted {new Date(c.date_submitted).toLocaleDateString()}</span>
                <SourceBadges sources={c.sources} />
                {c.email_link && (
                  <a
                    href={c.email_link}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={(e) => e.stopPropagation()}
                    className="flex items-center gap-1 text-indigo-600 hover:underline dark:text-indigo-400"
                  >
                    <Mail size={11} /> Open email
                  </a>
                )}
              </div>
            </div>
            {c.skills.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {c.skills.slice(0, 8).map((s) => (
                  <span key={s} className="rounded-full bg-indigo-50 px-2 py-0.5 text-[11px] font-medium text-indigo-700 dark:bg-indigo-500/10 dark:text-indigo-300">
                    {s}
                  </span>
                ))}
                {c.skills.length > 8 && <span className="text-[11px] text-zinc-400">+{c.skills.length - 8} more</span>}
              </div>
            )}
          </Card>
        ))}
      </div>

      {totalPages > 1 && (
        <div className="mt-4 flex items-center justify-center gap-2 text-sm">
          <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => changePage(page - 1)}>
            Previous
          </Button>
          <span className="text-zinc-500 dark:text-zinc-400">
            Page {page} of {totalPages}
          </span>
          <Button variant="secondary" size="sm" disabled={page >= totalPages} onClick={() => changePage(page + 1)}>
            Next
          </Button>
        </div>
      )}
    </div>
  );
}
