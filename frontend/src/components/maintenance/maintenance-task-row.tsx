import { useState } from "react";
import { Sparkles } from "lucide-react";
import { api } from "../../lib/api";
import { useToastStore } from "../../stores/toast-store";
import { Button } from "../ui/button";
import { ProgressBar, useSimulatedProgress } from "../ui/progress-bar";
import type { MaintenanceTask, ScanResult } from "../../lib/types";

const POLL_INTERVAL_MS = 1500;
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
// run/poll/progress logic exists in exactly one place.
export function MaintenanceTaskRow({ task, onDone }: { task: MaintenanceTask; onDone?: () => void }) {
  const push = useToastStore((s) => s.push);
  const [running, setRunning] = useState(false);
  const [liveProgress, setLiveProgress] = useState<ScanResult | null>(null);
  const [lastResult, setLastResult] = useState<ScanResult | null>(null);
  const { pct, remainingSeconds, overrun } = useSimulatedProgress(ESTIMATED_SECONDS, running);

  async function run() {
    setRunning(true);
    setLiveProgress(null);
    try {
      const job = await api.runMaintenanceTask(task.id);
      let current = job;
      while (current.status === "running") {
        await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
        current = await api.getScanJob(current.id);
        setLiveProgress(current.progress ?? null);
      }
      if (current.status === "failed") {
        push(current.error ?? "Maintenance task failed.", "error");
      } else if (current.result) {
        setLastResult(current.result);
        push("Done — " + summarize(current.result), "success");
        onDone?.();
      }
    } catch (e) {
      push(String(e), "error");
    } finally {
      setRunning(false);
      setLiveProgress(null);
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
          {liveProgress && (
            <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
              {liveProgress.resumes_found} checked so far — {liveProgress.candidates_created} updated
              {liveProgress.duplicates_skipped > 0 && `, ${liveProgress.duplicates_skipped} skipped`}
              {liveProgress.errors.length > 0 && `, ${liveProgress.errors.length} error(s)`}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
