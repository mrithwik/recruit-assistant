import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, Sparkles, Users } from "lucide-react";
import { api } from "../../lib/api";
import { useMatchesStore } from "../../stores/matches-store";
import { useToastStore } from "../../stores/toast-store";
import { MatchBadge } from "../ui/match-badge";
import { ProgressBar, useSimulatedProgress } from "../ui/progress-bar";
import type { JobMatchSummary } from "../../lib/types";

// Requirement: a recruiter running matches for several jobs was losing
// track of results — switching to the Match Results tab shows only one
// job at a time, and it's not obvious which job a result belongs to. This
// gives each job card an inline "latest results" glance without leaving
// the Job Descriptions page, with a link into the full, filterable view.
export function JobResultsSummary({ jobId }: { jobId: string }) {
  const [summary, setSummary] = useState<JobMatchSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();
  const push = useToastStore((s) => s.push);
  const {
    rescanMatched,
    rescanningMatched,
    rescanMatchedProgress,
    activeRescanForJobId,
  } = useMatchesStore();
  const thisJobRescanning = rescanningMatched && activeRescanForJobId === jobId;
  const otherJobRescanning = rescanningMatched && activeRescanForJobId !== jobId;
  const { pct: rescanPct, remainingSeconds: rescanRemaining, overrun: rescanOverrun } = useSimulatedProgress(
    Math.max(10, (summary?.total_matches ?? 1) * 3),
    thisJobRescanning,
  );

  function refetchSummary() {
    api
      .getMatchSummary(jobId)
      .then((s) => setSummary(s))
      .catch(() => {});
  }

  async function handleUpdateMatched() {
    try {
      await rescanMatched(jobId);
      refetchSummary();
    } catch (e) {
      push(String(e), "error");
    }
  }

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .getMatchSummary(jobId)
      .then((s) => !cancelled && setSummary(s))
      .catch(() => !cancelled && setSummary(null))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  if (loading) {
    return <p className="text-xs text-zinc-400">Loading results…</p>;
  }

  if (!summary || summary.total_matches === 0) {
    return (
      <div className="flex items-center justify-between rounded-lg bg-zinc-50 px-3 py-2 text-xs text-zinc-500 dark:bg-zinc-800/40 dark:text-zinc-400">
        <span className="flex items-center gap-1.5">
          <Users size={13} /> No matches yet — scan a source above, then click Run.
        </span>
      </div>
    );
  }

  return (
    <div className="rounded-lg bg-zinc-50 p-3 dark:bg-zinc-800/40">
      <div className="mb-2 flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
          Latest results — {summary.total_matches} candidate{summary.total_matches === 1 ? "" : "s"} scored
          {summary.last_matched_at && (
            <span className="ml-1.5 font-normal normal-case text-zinc-400">
              · {new Date(summary.last_matched_at).toLocaleDateString()}
            </span>
          )}
        </p>
        <div className="flex items-center gap-3">
          <button
            onClick={handleUpdateMatched}
            disabled={rescanningMatched}
            title="Re-check only this job's matched candidates for updates — faster than a full rescan"
            className="flex items-center gap-1 text-xs font-medium text-indigo-600 hover:underline disabled:cursor-not-allowed disabled:opacity-50 dark:text-indigo-400"
          >
            <Sparkles size={11} /> {thisJobRescanning ? "Updating…" : "Update matched"}
          </button>
          <button
            onClick={() => navigate(`/app/results?job=${jobId}`)}
            className="flex items-center gap-1 text-xs font-medium text-indigo-600 hover:underline dark:text-indigo-400"
          >
            View full results <ArrowRight size={11} />
          </button>
        </div>
      </div>
      {thisJobRescanning && (
        <div className="mb-2">
          <ProgressBar
            pct={rescanPct}
            label="Checking matched candidates for updates…"
            remainingSeconds={rescanRemaining}
            overrun={rescanOverrun}
          />
          {rescanMatchedProgress && (
            <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
              {rescanMatchedProgress.resumes_found} checked — {rescanMatchedProgress.candidates_updated} updated so far
            </p>
          )}
        </div>
      )}
      {otherJobRescanning && (
        <p className="mb-2 text-xs text-zinc-400">Another job's update is in progress — try again once it finishes.</p>
      )}
      <ul className="flex flex-col gap-1.5">
        {summary.top_candidates.map((c) => (
          <li key={c.match_id} className="flex items-center justify-between gap-2 text-sm">
            <button
              onClick={() => navigate(`/app/candidates/${c.candidate_id}`)}
              className="truncate text-zinc-700 hover:underline dark:text-zinc-200"
            >
              {c.candidate_name}
            </button>
            <MatchBadge tier={c.tier} score={c.score} />
          </li>
        ))}
      </ul>
    </div>
  );
}
