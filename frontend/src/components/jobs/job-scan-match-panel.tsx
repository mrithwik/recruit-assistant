import { useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, Database, Play, RefreshCw } from "lucide-react";
import { useScanStore } from "../../stores/scan-store";
import { useMatchesStore } from "../../stores/matches-store";
import { useToastStore } from "../../stores/toast-store";
import { Button } from "../ui/button";
import { ProgressBar, useSimulatedProgress } from "../ui/progress-bar";

type Mode = "existing_data" | "full_rescan";
type Phase = "idle" | "scanning" | "matching";

const MATCHING_ESTIMATED_SECONDS = 15;
const SCAN_ESTIMATED_SECONDS = 20;

// Per-job "restart a scan from existing data or re-ingest" (requirement 3),
// placed directly on the job card rather than requiring a trip to the
// Criteria or Scan Sources tabs — this is what makes Job Descriptions the
// operational hub instead of just a list.
export function JobScanMatchPanel({ jobId }: { jobId: string }) {
  const [mode, setMode] = useState<Mode>("existing_data");
  const [phase, setPhase] = useState<Phase>("idle");
  const { folderPaths, selectedAccountIds, scanFolders, scanEmail, scanning, scanProgress } = useScanStore();
  const runMatching = useMatchesStore((s) => s.runMatching);
  const matchingLoading = useMatchesStore((s) => s.loading);
  const push = useToastStore((s) => s.push);
  const { pct: matchPct, remainingSeconds: matchRemaining, overrun: matchOverrun } = useSimulatedProgress(
    MATCHING_ESTIMATED_SECONDS,
    phase === "matching",
  );
  const { pct: scanPct, remainingSeconds: scanRemaining, overrun: scanOverrun } = useSimulatedProgress(
    SCAN_ESTIMATED_SECONDS,
    phase === "scanning",
  );

  const hasConfiguredSources = folderPaths.length > 0 || selectedAccountIds.length > 0;
  const running = phase !== "idle";

  async function run() {
    setPhase(mode === "full_rescan" ? "scanning" : "matching");
    try {
      if (mode === "full_rescan") {
        if (folderPaths.length > 0) await scanFolders();
        if (selectedAccountIds.length > 0) await scanEmail();
        setPhase("matching");
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
    } finally {
      setPhase("idle");
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
          loading={running || matchingLoading}
          disabled={mode === "full_rescan" && !hasConfiguredSources}
          onClick={run}
        >
          Run
        </Button>
        <Link to="/app/results" className="text-xs font-medium text-indigo-600 hover:underline dark:text-indigo-400">
          View results →
        </Link>
      </div>

      {phase === "scanning" && scanning && (
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
      {phase === "matching" && (
        <div className="mt-3">
          <ProgressBar pct={matchPct} label="Scoring candidates…" remainingSeconds={matchRemaining} overrun={matchOverrun} />
        </div>
      )}
    </div>
  );
}
