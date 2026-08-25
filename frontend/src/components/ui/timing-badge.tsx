import { Zap } from "lucide-react";

// Surfaces real backend processing time next to results — added after
// fixing N+1 queries (All Candidates, Results) and caching match
// embeddings at ingest time instead of recomputing them on every match
// run (see project-log). Lets a recruiter actually see the speedup rather
// than take it on faith.
export function TimingBadge({ seconds, label = "Loaded" }: { seconds: number | null | undefined; label?: string }) {
  if (seconds === null || seconds === undefined) return null;
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300">
      <Zap size={11} />
      {label} in {seconds < 1 ? `${Math.round(seconds * 1000)}ms` : `${seconds.toFixed(2)}s`}
    </span>
  );
}
