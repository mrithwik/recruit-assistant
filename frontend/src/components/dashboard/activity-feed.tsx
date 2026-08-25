import { Link } from "react-router-dom";
import { ScanSearch, UserPlus } from "lucide-react";
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
  return null;
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
      {items.map((item, i) => {
        const target = targetFor(item);
        const row = (
          <>
            <div
              className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full ${
                item.type === "scan"
                  ? "bg-indigo-50 text-indigo-600 dark:bg-indigo-500/10 dark:text-indigo-400"
                  : "bg-emerald-50 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400"
              }`}
            >
              {item.type === "scan" ? <ScanSearch size={12} /> : <UserPlus size={12} />}
            </div>
            <div className="min-w-0 flex-1">
              <p className={`text-zinc-700 dark:text-zinc-300 ${target ? "group-hover:text-indigo-600 dark:group-hover:text-indigo-400" : ""}`}>
                {item.description}
              </p>
              <p className="text-xs text-zinc-400">{timeAgo(item.timestamp)}</p>
            </div>
          </>
        );
        return (
          <li key={i}>
            {target ? (
              <Link to={target} className="group flex items-start gap-2.5 rounded-lg text-sm transition-colors hover:bg-zinc-50 dark:hover:bg-zinc-800/40">
                {row}
              </Link>
            ) : (
              <div className="flex items-start gap-2.5 text-sm">{row}</div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
