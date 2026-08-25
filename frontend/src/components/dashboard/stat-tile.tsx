import type { LucideIcon } from "lucide-react";
import { Link } from "react-router-dom";

// Stat-tile contract per the dataviz skill: label (sentence case, no colon),
// value (semibold, proportional figures — never tabular-nums at this size).
export function StatTile({
  label,
  value,
  icon: Icon,
  tone = "default",
  to,
}: {
  label: string;
  value: number | string;
  icon: LucideIcon;
  tone?: "default" | "attention";
  to?: string;
}) {
  const content = (
    <>
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400">{label}</span>
        <div
          className={`flex h-7 w-7 items-center justify-center rounded-lg ${
            tone === "attention"
              ? "bg-red-50 text-red-600 dark:bg-red-500/10 dark:text-red-400"
              : "bg-indigo-50 text-indigo-600 dark:bg-indigo-500/10 dark:text-indigo-400"
          }`}
        >
          <Icon size={14} />
        </div>
      </div>
      <div className="text-2xl font-semibold text-zinc-900 dark:text-white">{value}</div>
    </>
  );

  const className = `block rounded-xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900 ${
    to ? "transition-colors hover:border-indigo-300 hover:shadow-md dark:hover:border-indigo-700" : ""
  }`;

  if (to) {
    return (
      <Link to={to} className={className}>
        {content}
      </Link>
    );
  }
  return <div className={className}>{content}</div>;
}
