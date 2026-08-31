import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, ChevronLeft, ChevronRight, Clock, FolderSearch, Mail, Wrench } from "lucide-react";
import { api } from "../lib/api";
import { PageHeader } from "../components/ui/page-header";
import { Card } from "../components/ui/card";
import { EmptyState } from "../components/ui/empty-state";
import type { IngestScanLogEntry } from "../lib/types";

const PAGE_SIZE = 20;

const ORIGIN_META: Record<IngestScanLogEntry["origin"], { icon: typeof Mail; label: string }> = {
  email: { icon: Mail, label: "Email" },
  folder: { icon: FolderSearch, label: "Folder" },
  maintenance: { icon: Wrench, label: "Maintenance" },
};

// The Dashboard's Recent Activity summarizes and collapses bulk runs for a
// quick glance — this is the opposite: every completed scan/rescan/
// maintenance run in full, one row each, for actually monitoring what
// happened (source, counts, errors), not navigating to results.
export function ScanLogsPage() {
  const [entries, setEntries] = useState<IngestScanLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [originFilter, setOriginFilter] = useState<string>("");
  const [page, setPage] = useState(0);

  useEffect(() => {
    api
      .listScanLogs()
      .then(setEntries)
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(
    () => entries.filter((e) => !originFilter || e.origin === originFilter),
    [entries, originFilter],
  );

  useEffect(() => setPage(0), [originFilter]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const pageEntries = filtered.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE);

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title="Scan Activity Log"
        description="Every completed scan, rescan, and maintenance run — for monitoring what actually happened, not just a summary."
      />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <select
          value={originFilter}
          onChange={(e) => setOriginFilter(e.target.value)}
          className="rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-700 shadow-sm dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200"
        >
          <option value="">All sources</option>
          <option value="folder">Folder scans</option>
          <option value="email">Email scans</option>
          <option value="maintenance">Maintenance runs</option>
        </select>
      </div>

      {loading ? (
        <p className="py-8 text-center text-sm text-zinc-400">Loading…</p>
      ) : entries.length === 0 ? (
        <EmptyState icon={<Clock size={20} />} title="No runs logged yet" description="Scan a folder or mailbox to see a detailed log here." />
      ) : filtered.length === 0 ? (
        <p className="py-8 text-center text-sm text-zinc-400">No runs match this filter.</p>
      ) : (
        <>
          <Card className="p-0">
            <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
              {pageEntries.map((e) => {
                const meta = ORIGIN_META[e.origin];
                const Icon = meta.icon;
                return (
                  <li key={e.id} className="flex items-start gap-3 p-4 text-sm">
                    <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
                      <Icon size={15} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="font-medium text-zinc-900 dark:text-white">
                        {meta.label}
                        {e.source_label ? ` — ${e.source_label}` : ""}
                      </p>
                      <p className="text-zinc-500 dark:text-zinc-400">
                        {new Date(e.ran_at).toLocaleString()} · {e.resumes_found} checked · {e.candidates_created} new ·{" "}
                        {e.candidates_updated} updated · {e.duplicates_skipped} already seen
                      </p>
                      {e.error_count > 0 && (
                        <p className="mt-1 flex items-center gap-1 text-amber-600 dark:text-amber-400">
                          <AlertTriangle size={12} /> {e.error_count} error(s) during this run
                        </p>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          </Card>

          <div className="mt-3 flex items-center justify-between text-xs text-zinc-500 dark:text-zinc-400">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="flex items-center gap-1 rounded-md px-2 py-1 font-medium hover:bg-zinc-50 disabled:opacity-40 dark:hover:bg-zinc-800/40"
            >
              <ChevronLeft size={13} /> Previous
            </button>
            <span>
              Page {page + 1} of {totalPages}
            </span>
            <button
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page + 1 >= totalPages}
              className="flex items-center gap-1 rounded-md px-2 py-1 font-medium hover:bg-zinc-50 disabled:opacity-40 dark:hover:bg-zinc-800/40"
            >
              Next <ChevronRight size={13} />
            </button>
          </div>
        </>
      )}
    </div>
  );
}
