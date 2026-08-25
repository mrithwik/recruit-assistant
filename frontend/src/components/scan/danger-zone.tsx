import { useState } from "react";
import { AlertTriangle, Trash2 } from "lucide-react";
import { api } from "../../lib/api";
import { useToastStore } from "../../stores/toast-store";
import { Button } from "../ui/button";

// Item 5: code/testing iterations shouldn't force losing job descriptions
// or scanned data — that now just doesn't happen (no automatic wiping
// anywhere). This is the explicit, opt-in counterpart: a recruiter who
// *does* want a clean slate (switching test scenarios, before a demo) can
// clear everything deliberately, with a typed confirmation since it's
// irreversible.
export function DangerZone() {
  const push = useToastStore((s) => s.push);
  const [open, setOpen] = useState(false);
  const [confirmText, setConfirmText] = useState("");
  const [clearing, setClearing] = useState(false);

  async function handleClear() {
    setClearing(true);
    try {
      const result = await api.clearData();
      push(
        `Cleared ${result.jobs_deleted} job(s), ${result.candidates_deleted} candidate(s), ${result.matches_deleted} match(es).`,
        "success",
      );
      // Every store in the app holds now-stale data (jobs, candidates,
      // matches, history) — reload is the simplest way to guarantee none
      // of them show deleted rows.
      window.location.reload();
    } catch (e) {
      push(String(e), "error");
      setClearing(false);
    }
  }

  return (
    <div className="rounded-lg border border-dashed border-red-200 bg-red-50/30 p-3 dark:border-red-900 dark:bg-red-500/5">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-red-700 dark:text-red-400"
      >
        <AlertTriangle size={12} /> Danger zone
      </button>

      {open && (
        <div className="mt-3">
          <p className="mb-3 text-xs text-zinc-500 dark:text-zinc-400">
            Permanently deletes every job description, candidate, match, and connected mailbox from
            the database. Generated files on disk (in <code>sample_data/</code>) and your login are
            not affected — you can regenerate or re-scan afterward. This cannot be undone.
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <input
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              placeholder='Type "CLEAR" to confirm'
              className="rounded-lg border border-red-200 bg-white px-2.5 py-1.5 text-xs text-zinc-700 focus:border-red-400 focus:outline-none dark:border-red-900 dark:bg-zinc-900 dark:text-zinc-200"
            />
            <Button
              variant="danger"
              size="sm"
              icon={<Trash2 size={13} />}
              loading={clearing}
              disabled={confirmText !== "CLEAR"}
              onClick={handleClear}
            >
              Clear all data
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
