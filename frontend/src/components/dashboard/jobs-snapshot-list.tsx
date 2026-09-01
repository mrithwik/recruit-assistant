import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Briefcase, ChevronLeft, ChevronRight } from "lucide-react";
import type { JobSnapshot } from "../../lib/types";
import { EmptyState } from "../ui/empty-state";

const PAGE_SIZE = 5;

// Active jobs are capped at 10 (see routes/jobs.py), so the full snapshot
// list is already in `jobs` — no server round-trip needed, unlike
// ActivityFeed's page-past-the-summary pattern for an unbounded log.
export function JobsSnapshotList({ jobs }: { jobs: JobSnapshot[] }) {
  const [page, setPage] = useState(0);
  const totalPages = Math.max(1, Math.ceil(jobs.length / PAGE_SIZE));

  // Jobs are added/removed elsewhere on the app (Jobs page) — if the
  // current page falls out of range after that, snap back rather than
  // showing an empty page.
  useEffect(() => {
    if (page > 0 && page >= totalPages) setPage(Math.max(0, totalPages - 1));
  }, [totalPages, page]);

  if (jobs.length === 0) {
    return (
      <EmptyState
        icon={<Briefcase size={18} />}
        title="No active jobs yet"
        description="Add a job description to start building a pipeline."
      />
    );
  }

  const shown = jobs.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  return (
    <div>
      {/* A border here (matching the pagination footer's border-t below)
          keeps the card's title/subtitle reading as a distinct header block
          instead of blending into the first row — divide-y alone only
          separated rows from each other, not the header from the list. */}
      <ul className="divide-y divide-zinc-100 border-t border-zinc-100 dark:divide-zinc-800 dark:border-zinc-800">
        {shown.map((j) => (
          <li key={j.id} className="flex items-center gap-3 py-3 text-sm">
            {/* An icon chip gives each row its own visual anchor, the same
                treatment ActivityFeed uses — so a row title doesn't have to
                rely on font-weight/color alone to read as clearly one level
                below the card's own semibold header. */}
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600 dark:bg-indigo-500/10 dark:text-indigo-400">
              <Briefcase size={14} />
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium text-zinc-700 dark:text-zinc-200">{j.title}</p>
              <p className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">
                {j.candidate_count} candidate{j.candidate_count === 1 ? "" : "s"} matched
                {j.top_score !== null && <> · top score {Math.round(j.top_score)}</>}
              </p>
            </div>
            <Link
              to={`/app/results?job=${j.id}`}
              className="flex shrink-0 items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-indigo-600 hover:bg-indigo-50 dark:text-indigo-400 dark:hover:bg-indigo-500/10"
            >
              View <ArrowRight size={12} />
            </Link>
          </li>
        ))}
      </ul>
      {jobs.length > PAGE_SIZE && (
        <div className="mt-3 flex items-center justify-between border-t border-zinc-100 pt-3 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            className="flex items-center gap-1 rounded-md px-2 py-1 font-medium hover:bg-zinc-50 disabled:opacity-40 dark:hover:bg-zinc-800/40"
          >
            <ChevronLeft size={13} /> Previous
          </button>
          <span>Page {page + 1} of {totalPages}</span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
            disabled={page + 1 >= totalPages}
            className="flex items-center gap-1 rounded-md px-2 py-1 font-medium hover:bg-zinc-50 disabled:opacity-40 dark:hover:bg-zinc-800/40"
          >
            Next <ChevronRight size={13} />
          </button>
        </div>
      )}
    </div>
  );
}
