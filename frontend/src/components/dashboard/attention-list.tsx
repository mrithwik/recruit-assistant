import { Link } from "react-router-dom";
import { AlertTriangle, ShieldCheck } from "lucide-react";
import type { AttentionItem } from "../../lib/types";
import { EmptyState } from "../ui/empty-state";

export function AttentionList({ items }: { items: AttentionItem[] }) {
  if (items.length === 0) {
    return (
      <EmptyState
        icon={<ShieldCheck size={18} />}
        title="Nothing needs attention"
        description="Red-flagged matches and profiles missing required info will show up here."
      />
    );
  }

  return (
    <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
      {items.map((item) => (
        <li key={item.match_id} className="flex items-start gap-2.5 py-2.5 text-sm">
          <AlertTriangle size={14} className="mt-0.5 shrink-0 text-red-500" />
          <div className="min-w-0 flex-1">
            <p className="truncate font-medium text-zinc-900 dark:text-white">{item.candidate_name}</p>
            <p className="truncate text-xs text-zinc-500 dark:text-zinc-400">
              {item.job_title} · {item.reason}
            </p>
          </div>
          <Link
            to={`/app/candidates/${item.candidate_id}`}
            className="shrink-0 rounded-md px-2 py-1 text-xs font-medium text-indigo-600 hover:bg-indigo-50 dark:text-indigo-400 dark:hover:bg-indigo-500/10"
          >
            Review
          </Link>
        </li>
      ))}
    </ul>
  );
}
