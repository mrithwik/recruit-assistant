import { useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, Database, Play, RefreshCw } from "lucide-react";
import { useScanStore } from "../../stores/scan-store";
import { useMatchesStore } from "../../stores/matches-store";
import { useToastStore } from "../../stores/toast-store";
import { Button } from "../ui/button";

type Mode = "existing_data" | "full_rescan";

// Per-job "restart a scan from existing data or re-ingest" (requirement 3),
// placed directly on the job card rather than requiring a trip to the
// Criteria or Scan Sources tabs — this is what makes Job Descriptions the
// operational hub instead of just a list.
export function JobScanMatchPanel({ jobId }: { jobId: string }) {
  const [mode, setMode] = useState<Mode>("existing_data");
  const [running, setRunning] = useState(false);
  const { folderPaths, selectedAccountIds, scanFolders, scanEmail } = useScanStore();
  const runMatching = useMatchesStore((s) => s.runMatching);
  const push = useToastStore((s) => s.push);

  const hasConfiguredSources = folderPaths.length > 0 || selectedAccountIds.length > 0;

  async function run() {
    setRunning(true);
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
    } finally {
      setRunning(false);
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
        <Link to="/app/results" className="text-xs font-medium text-indigo-600 hover:underline dark:text-indigo-400">
          View results →
        </Link>
      </div>
    </div>
  );
}
