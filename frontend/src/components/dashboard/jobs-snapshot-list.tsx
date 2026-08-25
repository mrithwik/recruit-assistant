import { Link } from "react-router-dom";
import { ArrowRight, Briefcase } from "lucide-react";
import type { JobSnapshot } from "../../lib/types";
import { EmptyState } from "../ui/empty-state";

export function JobsSnapshotList({ jobs }: { jobs: JobSnapshot[] }) {
  if (jobs.length === 0) {
    return (
      <EmptyState
        icon={<Briefcase size={18} />}
        title="No active jobs yet"
        description="Add a job description to start building a pipeline."
      />
    );
  }

  return (
    <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
      {jobs.map((j) => (
        <li key={j.id} className="flex items-center justify-between py-2.5 text-sm">
          <div>
            <p className="font-medium text-zinc-900 dark:text-white">{j.title}</p>
            <p className="text-xs text-zinc-500 dark:text-zinc-400">
              {j.candidate_count} candidate{j.candidate_count === 1 ? "" : "s"} matched
              {j.top_score !== null && <> · top score {Math.round(j.top_score)}</>}
            </p>
          </div>
          <Link
            to={`/app/results?job=${j.id}`}
            className="flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-indigo-600 hover:bg-indigo-50 dark:text-indigo-400 dark:hover:bg-indigo-500/10"
          >
            View <ArrowRight size={12} />
          </Link>
        </li>
      ))}
    </ul>
  );
}
