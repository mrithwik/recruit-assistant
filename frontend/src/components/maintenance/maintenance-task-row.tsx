import { useEffect } from "react";
import { Sparkles } from "lucide-react";
import { useToastStore } from "../../stores/toast-store";
import { useMaintenanceStore, useTaskRun } from "../../stores/maintenance-store";
import { Button } from "../ui/button";
import { ProgressBar, useSimulatedProgress } from "../ui/progress-bar";
import type { MaintenanceTask, ScanResult } from "../../lib/types";

// No fixed size for a maintenance task ahead of time (it depends on how
// much existing data needs touching), so this is a rough floor just to
// give the simulated bar some initial motion — the real counts underneath
// are what actually tells the user something's happening.
const ESTIMATED_SECONDS = 20;

function summarize(result: ScanResult): string {
  const parts = [`${result.candidates_created} updated`];
  if (result.duplicates_skipped) parts.push(`${result.duplicates_skipped} skipped`);
  if (result.errors.length) parts.push(`${result.errors.length} error(s)`);
  return `${result.resumes_found} checked — ${parts.join(", ")}`;
}

// One task's label/description/Run button/progress — shared by the full
// "Data maintenance" panel on Scan Sources and the Dashboard's "Updates
// available" banner (which only shows tasks with pending work), so the
// run/poll/progress logic exists in exactly one place. Backed by
// maintenance-store (persisted per task id) rather than local state, so a
// run started here is still visible after navigating away and back, a
// refresh, or a logout/login — and stays in sync between the two surfaces
// that render the same task.
export function MaintenanceTaskRow({ task, onDone }: { task: MaintenanceTask; onDone?: () => void }) {
  const push = useToastStore((s) => s.push);
  const { jobId, running, progress, lastResult } = useTaskRun(task.id);
  const { run: runTask, resumeIfAny } = useMaintenanceStore();
  const { pct, remainingSeconds, overrun } = useSimulatedProgress(ESTIMATED_SECONDS, running);

  useEffect(() => {
    if (jobId && !running) {
      resumeIfAny(task.id)
        .then(() => onDone?.())
        .catch(() => {});
    }
    // Only re-check on mount / task change — jobId and running are read
    // once to decide whether a resume is needed, not tracked as deps (that
    // would re-fire this effect on every progress tick).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [task.id]);

  async function run() {
    try {
      await runTask(task.id);
      onDone?.();
    } catch (e) {
      push(String(e), "error");
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="flex items-center gap-1.5 text-sm font-medium text-zinc-800 dark:text-zinc-200">
            <Sparkles size={13} className="text-indigo-500" /> {task.label}
          </p>
          <p className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">{task.description}</p>
          {lastResult && !running && (
            <p className="mt-1 text-xs text-emerald-600 dark:text-emerald-400">Last run: {summarize(lastResult)}</p>
          )}
        </div>
        <Button variant="secondary" size="sm" loading={running} onClick={run}>
          Run
        </Button>
      </div>
      {running && (
        <div>
          <ProgressBar pct={pct} label="Working…" remainingSeconds={remainingSeconds} overrun={overrun} />
          {progress && (
            <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
              {progress.resumes_found} checked so far — {progress.candidates_created} updated
              {progress.duplicates_skipped > 0 && `, ${progress.duplicates_skipped} skipped`}
              {progress.errors.length > 0 && `, ${progress.errors.length} error(s)`}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
