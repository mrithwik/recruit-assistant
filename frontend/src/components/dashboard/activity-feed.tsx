import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ChevronDown, ChevronLeft, ChevronRight, Inbox, ScanSearch, UserPlus } from "lucide-react";
import { api } from "../../lib/api";
import type { ActivityItem } from "../../lib/types";
import { EmptyState } from "../ui/empty-state";

const PAGE_SIZE = 10;

function timeAgo(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const minutes = Math.round(diffMs / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return `${days}d ago`;
}

function targetFor(item: ActivityItem): string | null {
  // A "scan" entry is a matching run (see SearchHistoryEntry) — the results
  // it produced live on that job's Match Results, not the Search History
  // list (which only logs that a run happened, not what it found).
  if (item.type === "scan" && item.job_id) return `/app/results?job=${item.job_id}`;
  if (item.type === "candidate" && item.candidate_id) return `/app/candidates/${item.candidate_id}`;
  // A "rescan matched"/"update matched" ingest entry belongs to one job
  // (see match_rescan.py, which now records job_id) — link straight to
  // that job's Match Results instead of the generic All Candidates every
  // other ingest entry (a plain scan, or a maintenance run) falls back to.
  if (item.type === "ingest" && item.job_id) return `/app/results?job=${item.job_id}`;
  if (item.type === "ingest") return "/app/candidates";
  return null;
}

function ActivityIcon({ type }: { type: ActivityItem["type"] }) {
  return (
    <div
      className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full ${
        type === "scan"
          ? "bg-indigo-50 text-indigo-600 dark:bg-indigo-500/10 dark:text-indigo-400"
          : type === "ingest"
            ? "bg-amber-50 text-amber-600 dark:bg-amber-500/10 dark:text-amber-400"
            : "bg-emerald-50 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400"
      }`}
    >
      {type === "scan" ? <ScanSearch size={12} /> : type === "ingest" ? <Inbox size={12} /> : <UserPlus size={12} />}
    </div>
  );
}

// One row — used both for a top-level entry and, indented, for each
// sub-item of an expanded batch. A batch entry (sub_items.length > 0, from
// a Jobs-page bulk "Match all"/"Update matched" run — see
// dashboard/service.py's _recent_activity) is a toggle instead of a link:
// its own description is a summary, so the point of clicking is to reveal
// the per-job detail underneath, not to navigate away.
function ActivityRow({ item }: { item: ActivityItem }) {
  const [expanded, setExpanded] = useState(false);
  const target = targetFor(item);
  const hasSubItems = item.sub_items.length > 0;

  const content = (
    <>
      <ActivityIcon type={item.type} />
      <div className="min-w-0 flex-1">
        <p className={`text-zinc-700 dark:text-zinc-300 ${target ? "group-hover:text-indigo-600 dark:group-hover:text-indigo-400" : ""}`}>
          {item.description}
        </p>
        <p className="text-xs text-zinc-400">{timeAgo(item.timestamp)}</p>
      </div>
      {hasSubItems && (
        <ChevronDown
          size={14}
          className={`mt-1 shrink-0 text-zinc-400 transition-transform ${expanded ? "rotate-180" : ""}`}
        />
      )}
    </>
  );

  const rowClass = "group flex items-start gap-2.5 rounded-lg text-sm transition-colors hover:bg-zinc-50 dark:hover:bg-zinc-800/40";

  return (
    <li>
      {hasSubItems ? (
        <button onClick={() => setExpanded((v) => !v)} className={`w-full text-left ${rowClass}`}>
          {content}
        </button>
      ) : target ? (
        <Link to={target} className={rowClass}>
          {content}
        </Link>
      ) : (
        <div className="flex items-start gap-2.5 text-sm">{content}</div>
      )}
      {hasSubItems && expanded && (
        <ul className="ml-8 mt-2 space-y-2 border-l border-zinc-100 pl-3 dark:border-zinc-800">
          {item.sub_items.map((sub, i) => (
            <ActivityRow key={i} item={sub} />
          ))}
        </ul>
      )}
    </li>
  );
}

// Takes the Dashboard summary's latest-10 as the initial page (so the card
// renders instantly on load, same as before), then switches to its own
// paginated fetch (GET /dashboard/activity) the moment the user pages past
// what the summary already gave it — a full history log to page back
// through, not just a glanceable top-10.
export function ActivityFeed({ items }: { items: ActivityItem[] }) {
  const [page, setPage] = useState(0);
  const [pageItems, setPageItems] = useState<ActivityItem[] | null>(null);
  const [total, setTotal] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (page === 0) {
      setPageItems(null);
      return;
    }
    setLoading(true);
    api
      .activityLog(PAGE_SIZE, page * PAGE_SIZE)
      .then((res) => {
        setPageItems(res.items);
        setTotal(res.total);
      })
      .finally(() => setLoading(false));
  }, [page]);

  const shown = page === 0 ? items : pageItems ?? [];
  const totalPages = total !== null ? Math.max(1, Math.ceil(total / PAGE_SIZE)) : null;
  const hasMore = totalPages === null ? items.length >= PAGE_SIZE : page + 1 < totalPages;

  if (items.length === 0) {
    return (
      <EmptyState
        icon={<ScanSearch size={18} />}
        title="No activity yet"
        description="Scans and new candidates will show up here as they happen."
      />
    );
  }

  return (
    <div>
      <ul className="space-y-3">
        {shown.map((item, i) => (
          <ActivityRow key={`${page}-${i}`} item={item} />
        ))}
      </ul>
      {(page > 0 || hasMore) && (
        <div className="mt-3 flex items-center justify-between border-t border-zinc-100 pt-3 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0 || loading}
            className="flex items-center gap-1 rounded-md px-2 py-1 font-medium hover:bg-zinc-50 disabled:opacity-40 dark:hover:bg-zinc-800/40"
          >
            <ChevronLeft size={13} /> Previous
          </button>
          <span>{totalPages !== null ? `Page ${page + 1} of ${totalPages}` : `Page ${page + 1}`}</span>
          <button
            onClick={() => setPage((p) => p + 1)}
            disabled={!hasMore || loading}
            className="flex items-center gap-1 rounded-md px-2 py-1 font-medium hover:bg-zinc-50 disabled:opacity-40 dark:hover:bg-zinc-800/40"
          >
            Next <ChevronRight size={13} />
          </button>
        </div>
      )}
    </div>
  );
}
