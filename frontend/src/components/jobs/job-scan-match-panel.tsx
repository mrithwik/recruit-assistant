import { useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, Database, Play, RefreshCw } from "lucide-react";
import { useScanStore } from "../../stores/scan-store";
import { useMatchesStore } from "../../stores/matches-store";
import { useToastStore } from "../../stores/toast-store";
import { Button } from "../ui/button";
import { ProgressBar, useSimulatedProgress } from "../ui/progress-bar";

type Mode = "existing_data" | "full_rescan";

const MATCHING_ESTIMATED_SECONDS = 15;
const SCAN_ESTIMATED_SECONDS = 20;

// Per-job "restart a scan from existing data or re-ingest" (requirement 3),
// placed directly on the job card rather than requiring a trip to the
// Criteria or Scan Sources tabs — this is what makes Job Descriptions the
// operational hub instead of just a list.
//
// Progress is derived entirely from the global scan-store/matches-store
// (both job-registry-backed, both persisted) rather than local component
// state — a local "phase" used to reset to idle the moment this card
// unmounted (switching tabs, or just collapsing the card), even though the
// backend job was still running. Deriving from the stores instead means the
// progress bar reappears correctly on remount, a page refresh, or a
// logout/login, exactly like every other long-running action in the app.
export function JobScanMatchPanel({ jobId }: { jobId: string }) {
  const [mode, setMode] = useState<Mode>("existing_data");
  const { folderPaths, selectedAccountIds, scanFolders, scanEmail, scanning, scanProgress } = useScanStore();
  const runMatching = useMatchesStore((s) => s.runMatching);
  const matchingLoading = useMatchesStore((s) => s.loading);
  const activeRunForJobId = useMatchesStore((s) => s.activeRunForJobId);
  const push = useToastStore((s) => s.push);
  const isMatchingThisJob = matchingLoading && activeRunForJobId === jobId;
  const { pct: matchPct, remainingSeconds: matchRemaining, overrun: matchOverrun } = useSimulatedProgress(
    MATCHING_ESTIMATED_SECONDS,
    isMatchingThisJob,
  );
  const { pct: scanPct, remainingSeconds: scanRemaining, overrun: scanOverrun } = useSimulatedProgress(
    SCAN_ESTIMATED_SECONDS,
    scanning,
  );

  const hasConfiguredSources = folderPaths.length > 0 || selectedAccountIds.length > 0;
  // Scanning isn't job-scoped (it scans folders/mailboxes, not a specific
  // job) so this card can only say "a scan is running," not "a scan I
  // started" — matching current behavior everywhere else scanning shows up.
  const running = scanning || isMatchingThisJob;

  async function run() {
    try {
      if (mode === "full_rescan") {
        if (folderPaths.length > 0) await scanFolders();
        if (selectedAccountIds.length > 0) await scanEmail();
      }
      const matches = await runMatching(jobId);
      const count = matches?.length ?? 0;
      if (count === 0) {
        push(
          "No candidate data available to match against yet — go to Scan Sources and scan a folder or mailbox first.",
          "info",
        );
      } else {
        push(
          mode === "full_rescan"
            ? `Re-scanned sources and matched ${count} candidate(s).`
            : `Matched ${count} candidate(s) from existing data.`,
          "success",
        );
      }
    } catch (e) {
      push(String(e), "error");
    }
  }

  return (
    <div className="rounded-lg border border-zinc-100 bg-zinc-50/60 p-3 dark:border-zinc-800 dark:bg-zinc-950/40">
      <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
        <RefreshCw size={12} /> Scan & match
      </div>
      <div className="mb-2 flex rounded-lg bg-zinc-100 p-0.5 text-xs dark:bg-zinc-800">
        <button
          onClick={() => setMode("existing_data")}
          className={`flex-1 rounded-md px-2 py-1 font-medium ${mode === "existing_data" ? "bg-white shadow-sm dark:bg-zinc-900" : "text-zinc-500"}`}
        >
          Use existing data
        </button>
        <button
          onClick={() => setMode("full_rescan")}
          className={`flex-1 rounded-md px-2 py-1 font-medium ${mode === "full_rescan" ? "bg-white shadow-sm dark:bg-zinc-900" : "text-zinc-500"}`}
        >
          Re-scan sources
        </button>
      </div>

      {mode === "full_rescan" && !hasConfiguredSources && (
        <p className="mb-2 flex items-center gap-1.5 text-xs text-orange-600 dark:text-orange-400">
          <AlertTriangle size={12} />
          No sources configured yet —{" "}
          <Link to="/app/scan" className="underline">
            set up Scan Sources
          </Link>{" "}
          first.
        </p>
      )}

      <div className="flex items-center gap-2">
        <Button
          size="sm"
          icon={mode === "existing_data" ? <Database size={13} /> : <Play size={13} />}
          loading={running}
          disabled={mode === "full_rescan" && !hasConfiguredSources}
          onClick={run}
        >
          Run
        </Button>
        <Link to={`/app/results?job=${jobId}`} className="text-xs font-medium text-indigo-600 hover:underline dark:text-indigo-400">
          View results →
        </Link>
      </div>

      {scanning && (
        <div className="mt-3">
          <ProgressBar pct={scanPct} label="Scanning sources…" remainingSeconds={scanRemaining} overrun={scanOverrun} />
          {scanProgress && (
            <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
              {scanProgress.resumes_found} resume(s) processed — {scanProgress.candidates_created} new,{" "}
              {scanProgress.candidates_updated} updated
            </p>
          )}
        </div>
      )}
      {!scanning && isMatchingThisJob && (
        <div className="mt-3">
          <ProgressBar pct={matchPct} label="Scoring candidates…" remainingSeconds={matchRemaining} overrun={matchOverrun} />
        </div>
      )}
    </div>
  );
}
