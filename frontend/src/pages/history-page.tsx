import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { CalendarClock, History as HistoryIcon, Search } from "lucide-react";
import { useHistoryStore } from "../stores/history-store";
import { useJobsStore } from "../stores/jobs-store";
import { PageHeader } from "../components/ui/page-header";
import { Card } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { EmptyState } from "../components/ui/empty-state";

// Previously implicitly filtered by whichever job happened to be selected
// elsewhere in the app (Match Results shares that selection), so this
// page could look empty or partial without explaining why. Now always loads
// every run and offers its own independent job filter + text search.
export function HistoryPage() {
  const { entries, fetchHistory } = useHistoryStore();
  const { jobs, fetchJobs } = useJobsStore();
  const [searchParams] = useSearchParams();
  const [query, setQuery] = useState("");
  const [jobFilter, setJobFilter] = useState<string>(searchParams.get("job") ?? "");

  useEffect(() => {
    fetchHistory().catch(() => {});
    if (jobs.length === 0) fetchJobs().catch(() => {});
  }, []);

  useEffect(() => {
    const fromQuery = searchParams.get("job");
    if (fromQuery) setJobFilter(fromQuery);
  }, [searchParams]);

  const jobTitle = (id: string) => jobs.find((j) => j.id === id)?.title ?? id;

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return entries
      .filter((e) => !jobFilter || e.job_id === jobFilter)
      .filter((e) => !q || jobTitle(e.job_id).toLowerCase().includes(q))
      .sort((a, b) => new Date(b.run_at).getTime() - new Date(a.run_at).getTime());
  }, [entries, query, jobFilter, jobs]);

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader title="Search History" description="Every matching run across every job, with date range, source, and criteria version." />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[200px]">
          <Search size={14} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-400" />
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search by job title…" className="pl-8" />
        </div>
        <select
          value={jobFilter}
          onChange={(e) => setJobFilter(e.target.value)}
          className="rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-700 shadow-sm dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200"
        >
          <option value="">All jobs</option>
          {jobs.map((j) => (
            <option key={j.id} value={j.id}>
              {j.title}
            </option>
          ))}
        </select>
      </div>

      {entries.length === 0 ? (
        <EmptyState icon={<HistoryIcon size={20} />} title="No search runs recorded yet" description="Run matching from the Match Results tab to see history here." />
      ) : filtered.length === 0 ? (
        <p className="py-8 text-center text-sm text-zinc-400">No runs match this filter.</p>
      ) : (
        <Card className="p-0">
          <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {filtered.map((e) => (
              <li key={e.id} className="flex items-start gap-3 p-4 text-sm">
                <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
                  <CalendarClock size={15} />
                </div>
                <div>
                  <p className="font-medium text-zinc-900 dark:text-white">{jobTitle(e.job_id)}</p>
                  <p className="text-zinc-500 dark:text-zinc-400">
                    Run at {new Date(e.run_at).toLocaleString()} · {e.candidate_count} candidates · criteria v{e.criteria_version}
                  </p>
                  {(e.date_range_start || e.date_range_end) && (
                    <p className="text-zinc-400 dark:text-zinc-500">
                      Scanned range: {e.date_range_start ? new Date(e.date_range_start).toLocaleDateString() : "…"} –{" "}
                      {e.date_range_end ? new Date(e.date_range_end).toLocaleDateString() : "…"}
                    </p>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
