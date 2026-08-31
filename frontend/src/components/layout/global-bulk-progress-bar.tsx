import { Link } from "react-router-dom";
import { Sparkles } from "lucide-react";
import { useBulkJobsStore } from "../../stores/bulk-jobs-store";
import { useJobsStore } from "../../stores/jobs-store";
import { CancelJobButton } from "../ui/cancel-job-button";

// A Jobs-page bulk "Match all"/"Update matched" run is real work happening
// across many jobs, one at a time — visible only on the Jobs page card it
// started from, and (per-job) on Match Results if you happen to have the
// right job selected there. Neither is enough on its own: navigate away
// from Jobs mid-run and there was previously no sign anything was still
// happening, which read as the app having silently dropped the work (or,
// worse, made Match Results look "frozen" when its own per-job state
// fought with the loop's side effects — see matches-store's
// followRescanJob fix). This renders once, in the app shell, so the run is
// visible from every page without either page needing to reconstruct it.
export function GlobalBulkProgressBar() {
  const { opType, jobIds, index, running, stop } = useBulkJobsStore();
  const jobs = useJobsStore((s) => s.jobs);

  if (!running || !opType) return null;

  const total = jobIds.length;
  const currentJobId = jobIds[index];
  const currentJobTitle = jobs.find((j) => j.id === currentJobId)?.title;
  const pct = total > 0 ? Math.round((index / total) * 100) : 0;
  const label = opType === "match" ? "Matching" : "Checking for updates";

  return (
    <div className="border-b border-indigo-100 bg-indigo-50/80 px-4 py-1.5 dark:border-indigo-500/20 dark:bg-indigo-500/10">
      <div className="mx-auto flex max-w-6xl items-center gap-3 text-xs">
        <Sparkles size={13} className="shrink-0 animate-pulse text-indigo-600 dark:text-indigo-400" />
        <span className="shrink-0 font-medium text-indigo-700 dark:text-indigo-300">
          {label} job {index + 1} of {total}
        </span>
        {currentJobTitle && (
          <Link
            to={`/app/results?job=${currentJobId}`}
            className="min-w-0 truncate text-indigo-600 hover:underline dark:text-indigo-400"
            title="View this job's results"
          >
            “{currentJobTitle}”
          </Link>
        )}
        <div className="ml-auto h-1.5 w-32 shrink-0 overflow-hidden rounded-full bg-indigo-100 dark:bg-indigo-500/20">
          <div
            className="h-full rounded-full bg-indigo-500 transition-all dark:bg-indigo-400"
            style={{ width: `${pct}%` }}
          />
        </div>
        <CancelJobButton onCancel={stop} />
      </div>
    </div>
  );
}
