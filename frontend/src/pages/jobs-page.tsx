import { useEffect, useMemo, useState } from "react";
import {
  Briefcase,
  Building2,
  CalendarPlus,
  Check,
  ChevronDown,
  ChevronsDownUp,
  ChevronsUpDown,
  Play,
  Plus,
  Search,
  SlidersHorizontal,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { useJobsStore } from "../stores/jobs-store";
import { useMatchesStore } from "../stores/matches-store";
import { useToastStore } from "../stores/toast-store";
import { PageHeader } from "../components/ui/page-header";
import { Card, CardDashed } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input, Label, Textarea } from "../components/ui/input";
import { EmptyState } from "../components/ui/empty-state";
import { JobCriteriaPanel } from "../components/jobs/job-criteria-panel";
import { JobScanMatchPanel } from "../components/jobs/job-scan-match-panel";
import { JobResultsSummary } from "../components/jobs/job-results-summary";
import { SortSelect } from "../components/ui/sort-select";
import { ProgressBar } from "../components/ui/progress-bar";
import type { Job } from "../lib/types";

const PAGE_SIZE = 10;

type SortKey = "newest" | "oldest" | "title_asc" | "title_desc";

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: "newest", label: "Newest first" },
  { value: "oldest", label: "Oldest first" },
  { value: "title_asc", label: "Title A–Z" },
  { value: "title_desc", label: "Title Z–A" },
];

function sortJobs(list: Job[], sort: SortKey): Job[] {
  const sorted = [...list];
  switch (sort) {
    case "newest":
      return sorted.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
    case "oldest":
      return sorted.sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());
    case "title_asc":
      return sorted.sort((a, b) => a.title.localeCompare(b.title));
    case "title_desc":
      return sorted.sort((a, b) => b.title.localeCompare(a.title));
  }
}

export function JobsPage() {
  const { jobs, fetchJobs, createJob, deactivateJob, bulkDeactivateJobs, selectJob, selectedJobId } =
    useJobsStore();
  const push = useToastStore((s) => s.push);
  const [adding, setAdding] = useState(false);
  const [title, setTitle] = useState("");
  const [company, setCompany] = useState("");
  const [rawText, setRawText] = useState("");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<SortKey>("newest");
  const [page, setPage] = useState(1);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [companyFilters, setCompanyFilters] = useState<Set<string>>(new Set());
  // Bulk "match selected"/"match all" — N independent matching runs (each
  // already a fast, atomic backend call), looped from here rather than as
  // one trackable background job. A refresh mid-run only loses the
  // "remaining jobs in the queue" bookkeeping, not any already-completed
  // job's results (those persisted server-side the moment each call
  // returned) — a smaller gap than a scan losing all progress, so this
  // doesn't need the job_registry survive-refresh treatment those get.
  const [bulkMatching, setBulkMatching] = useState(false);
  const [bulkProgress, setBulkProgress] = useState<{ done: number; total: number } | null>(null);

  useEffect(() => {
    fetchJobs().catch((e) => push(String(e), "error"));
  }, []);

  const allCompanies = useMemo(
    () => Array.from(new Set(jobs.map((j) => j.company).filter(Boolean))).sort(),
    [jobs],
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const base = jobs.filter((j) => {
      const matchesQuery =
        !q ||
        j.title.toLowerCase().includes(q) ||
        j.company.toLowerCase().includes(q) ||
        j.raw_text.toLowerCase().includes(q);
      const matchesCompany = companyFilters.size === 0 || companyFilters.has(j.company);
      return matchesQuery && matchesCompany;
    });
    return sortJobs(base, sort);
  }, [jobs, query, companyFilters, sort]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const pageJobs = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  useEffect(() => {
    setPage(1);
  }, [query]);

  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [totalPages, page]);

  async function submit() {
    if (!title.trim() || !rawText.trim()) return;
    try {
      const job = await createJob(title, rawText, company);
      setTitle("");
      setCompany("");
      setRawText("");
      setAdding(false);
      setExpandedIds((prev) => new Set(prev).add(job.id));
      push("Job description added — default criteria applied, adjust below", "success");
    } catch (e) {
      push(String(e), "error");
    }
  }

  function toggleCompanyFilter(c: string) {
    setCompanyFilters((prev) => {
      const next = new Set(prev);
      if (next.has(c)) next.delete(c);
      else next.add(c);
      return next;
    });
  }

  function toggleSelected(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleExpanded(id: string) {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function deleteOne(id: string) {
    try {
      await deactivateJob(id);
      push("Job removed", "success");
    } catch (e) {
      push(String(e), "error");
    }
  }

  async function deleteSelected() {
    if (selectedIds.size === 0) return;
    if (!window.confirm(`Delete ${selectedIds.size} selected job(s)?`)) return;
    try {
      await bulkDeactivateJobs(Array.from(selectedIds));
      setSelectedIds(new Set());
      push("Selected jobs removed", "success");
    } catch (e) {
      push(String(e), "error");
    }
  }

  function toggleSelectAll() {
    setSelectedIds((prev) => (prev.size === filtered.length ? new Set() : new Set(filtered.map((j) => j.id))));
  }

  async function matchJobs(jobIds: string[]) {
    if (jobIds.length === 0) return;
    setBulkMatching(true);
    setBulkProgress({ done: 0, total: jobIds.length });
    const failures: string[] = [];
    let totalMatched = 0;
    try {
      for (let i = 0; i < jobIds.length; i++) {
        try {
          const matches = await useMatchesStore.getState().runMatching(jobIds[i]);
          totalMatched += matches?.length ?? 0;
        } catch {
          const job = jobs.find((j) => j.id === jobIds[i]);
          failures.push(job?.title ?? jobIds[i]);
        }
        setBulkProgress({ done: i + 1, total: jobIds.length });
      }
      push(
        `Matched ${jobIds.length - failures.length} job(s) — ${totalMatched} candidate match(es) total` +
          (failures.length ? `. Failed: ${failures.join(", ")}` : ""),
        failures.length ? "error" : "success",
      );
    } finally {
      setBulkMatching(false);
      setBulkProgress(null);
    }
  }

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title="Job Descriptions"
        description="Add, search, and manage every open role — set matching criteria and trigger scans right from here."
        action={
          <span className="rounded-full bg-zinc-100 px-3 py-1 text-xs font-semibold text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
            {jobs.length} total
          </span>
        }
      />

      <div className="mb-2 flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[200px]">
          <Search size={14} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-400" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search job titles, companies, or descriptions…"
            className="pl-8"
          />
        </div>
        <SortSelect value={sort} onChange={setSort} options={SORT_OPTIONS} />
        {allCompanies.length > 0 && (
          <Button
            variant="secondary"
            size="md"
            icon={<SlidersHorizontal size={14} />}
            onClick={() => setShowAdvanced((v) => !v)}
          >
            Advanced{companyFilters.size > 0 ? ` (${companyFilters.size})` : ""}
          </Button>
        )}
        {pageJobs.length > 1 && (
          <Button
            variant="secondary"
            size="md"
            icon={expandedIds.size > 0 ? <ChevronsDownUp size={14} /> : <ChevronsUpDown size={14} />}
            onClick={() =>
              setExpandedIds(expandedIds.size > 0 ? new Set() : new Set(pageJobs.map((j) => j.id)))
            }
          >
            {expandedIds.size > 0 ? "Collapse all" : "Expand all"}
          </Button>
        )}
        {filtered.length > 1 && (
          <Button
            variant="secondary"
            size="md"
            icon={<Sparkles size={14} />}
            loading={bulkMatching}
            onClick={() => matchJobs(filtered.map((j) => j.id))}
            title="Runs matching against existing candidate data for every job currently shown"
          >
            Match all ({filtered.length})
          </Button>
        )}
        <Button icon={<Plus size={15} />} onClick={() => setAdding(true)}>
          Add job description
        </Button>
      </div>

      {bulkMatching && bulkProgress && (
        <div className="mb-4">
          <ProgressBar
            pct={Math.round((bulkProgress.done / bulkProgress.total) * 100)}
            label={`Matching job ${bulkProgress.done} of ${bulkProgress.total}…`}
          />
        </div>
      )}

      {showAdvanced && allCompanies.length > 0 && (
        <div className="mb-4 rounded-lg border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-900">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
            Filter by company
          </p>
          <div className="flex flex-wrap gap-1.5">
            {allCompanies.map((c) => (
              <button
                key={c}
                onClick={() => toggleCompanyFilter(c)}
                className={`rounded-full px-2.5 py-1 text-xs font-medium ${
                  companyFilters.has(c)
                    ? "bg-indigo-600 text-white"
                    : "bg-zinc-100 text-zinc-600 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700"
                }`}
              >
                {c}
              </button>
            ))}
            {companyFilters.size > 0 && (
              <button
                onClick={() => setCompanyFilters(new Set())}
                className="rounded-full px-2.5 py-1 text-xs font-medium text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200"
              >
                Clear
              </button>
            )}
          </div>
        </div>
      )}

      {filtered.length > 0 && (
        <div className="mb-3 flex items-center gap-2 text-sm">
          <label className="flex items-center gap-1.5 text-zinc-500 dark:text-zinc-400">
            <input
              type="checkbox"
              checked={selectedIds.size > 0 && selectedIds.size === filtered.length}
              ref={(el) => {
                if (el) el.indeterminate = selectedIds.size > 0 && selectedIds.size < filtered.length;
              }}
              onChange={toggleSelectAll}
              className="h-4 w-4 rounded border-zinc-300 text-indigo-600 focus:ring-indigo-500"
            />
            Select all
          </label>
          {selectedIds.size > 0 && (
            <div className="flex flex-1 items-center justify-between rounded-lg bg-indigo-50 px-3 py-2 dark:bg-indigo-500/10">
              <span className="text-indigo-700 dark:text-indigo-300">{selectedIds.size} selected</span>
              <div className="flex gap-3">
                <button
                  onClick={() => matchJobs(Array.from(selectedIds))}
                  disabled={bulkMatching}
                  className="flex items-center gap-1 font-medium text-indigo-600 hover:underline disabled:cursor-not-allowed disabled:opacity-50 dark:text-indigo-400"
                >
                  <Play size={13} /> Match selected
                </button>
                <button onClick={() => setSelectedIds(new Set())} className="text-zinc-500 hover:underline dark:text-zinc-400">
                  Clear
                </button>
                <button
                  onClick={deleteSelected}
                  className="flex items-center gap-1 font-medium text-red-600 hover:underline dark:text-red-400"
                >
                  <Trash2 size={13} /> Delete selected
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {adding && (
        <CardDashed className="mb-4 border-indigo-200 dark:border-indigo-800">
          <div className="mb-3 grid gap-3 sm:grid-cols-2">
            <div>
              <Label>Job title</Label>
              <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Senior Backend Engineer" />
            </div>
            <div>
              <Label>Company</Label>
              <Input value={company} onChange={(e) => setCompany(e.target.value)} placeholder="e.g. Acme Corp" />
            </div>
          </div>
          <div className="mb-3">
            <Label>Job description</Label>
            <Textarea value={rawText} onChange={(e) => setRawText(e.target.value)} placeholder="Paste the job description..." rows={6} />
          </div>
          <p className="mb-3 text-xs text-zinc-500 dark:text-zinc-400">
            Default matching criteria (skills, experience, location/remote, visa sponsorship) apply
            automatically on save with sensible defaults — you'll see the full checklist to adjust
            right after.
          </p>
          <div className="flex gap-2">
            <Button icon={<Check size={15} />} onClick={submit}>
              Save
            </Button>
            <Button variant="secondary" icon={<X size={15} />} onClick={() => setAdding(false)}>
              Cancel
            </Button>
          </div>
        </CardDashed>
      )}

      <div className="flex flex-col gap-3">
        {jobs.length === 0 && !adding && (
          <EmptyState
            icon={<Briefcase size={20} />}
            title="No job descriptions yet"
            description="Add your first role to start scanning and matching candidates against it."
            action={
              <Button icon={<Plus size={15} />} onClick={() => setAdding(true)}>
                Add job description
              </Button>
            }
          />
        )}

        {jobs.length > 0 && filtered.length === 0 && (
          <p className="py-8 text-center text-sm text-zinc-400">No jobs match "{query}".</p>
        )}

        {pageJobs.map((job) => {
          const expanded = expandedIds.has(job.id);
          return (
            <Card key={job.id} selected={selectedJobId === job.id} className="p-0">
              <div className="flex items-start gap-3 p-4">
                <input
                  type="checkbox"
                  checked={selectedIds.has(job.id)}
                  onChange={() => toggleSelected(job.id)}
                  onClick={(e) => e.stopPropagation()}
                  className="mt-1 h-4 w-4 shrink-0 rounded border-zinc-300 text-indigo-600 focus:ring-indigo-500"
                />
                <div className="flex flex-1 cursor-pointer items-start gap-3" onClick={() => selectJob(job.id)}>
                  <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600 dark:bg-indigo-500/10 dark:text-indigo-400">
                    <Briefcase size={15} />
                  </div>
                  <div className="min-w-0">
                    <h2 className="flex items-center gap-1.5 font-medium text-zinc-900 dark:text-white">
                      {job.title}
                      {job.company && (
                        <span className="flex items-center gap-1 text-sm font-normal text-zinc-400">
                          <Building2 size={12} /> {job.company}
                        </span>
                      )}
                    </h2>
                    <p className="mt-0.5 line-clamp-2 text-sm text-zinc-500 dark:text-zinc-400">{job.raw_text}</p>
                    <p className="mt-1 flex items-center gap-1 text-xs text-zinc-400">
                      <CalendarPlus size={11} /> Posted {new Date(job.created_at).toLocaleDateString()}
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => toggleExpanded(job.id)}
                  className="shrink-0 rounded-md p-1.5 text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800"
                  aria-label="Toggle details"
                >
                  <ChevronDown size={15} className={`transition-transform ${expanded ? "rotate-180" : ""}`} />
                </button>
                <button
                  onClick={() => deleteOne(job.id)}
                  className="shrink-0 rounded-md p-1.5 text-zinc-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950"
                  aria-label="Remove job"
                >
                  <Trash2 size={14} />
                </button>
              </div>

              {expanded && (
                <div className="space-y-4 border-t border-zinc-100 bg-zinc-50/40 p-4 dark:border-zinc-800 dark:bg-zinc-950/30">
                  <JobScanMatchPanel jobId={job.id} />
                  <JobResultsSummary jobId={job.id} />
                  <JobCriteriaPanel jobId={job.id} />
                </div>
              )}
            </Card>
          );
        })}

        {totalPages > 1 && (
          <div className="flex items-center justify-center gap-2 pt-2 text-sm">
            <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
              Previous
            </Button>
            <span className="text-zinc-500 dark:text-zinc-400">
              Page {page} of {totalPages}
            </span>
            <Button variant="secondary" size="sm" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
              Next
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
