import { useState } from "react";
import { Link } from "react-router-dom";
import { ChevronDown, Inbox, ScanSearch, UserPlus } from "lucide-react";
import type { ActivityItem } from "../../lib/types";
import { EmptyState } from "../ui/empty-state";

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
  if (item.type === "scan" && item.job_id) return `/app/history?job=${item.job_id}`;
  if (item.type === "candidate" && item.candidate_id) return `/app/candidates/${item.candidate_id}`;
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

export function ActivityFeed({ items }: { items: ActivityItem[] }) {
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
    <ul className="space-y-3">
      {items.map((item, i) => (
        <ActivityRow key={i} item={item} />
      ))}
    </ul>
  );
}
