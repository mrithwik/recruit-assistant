import { useState } from "react";
import { X } from "lucide-react";

// Small inline "Cancel" control for a running background job — stops it at
// its next checkpoint and keeps whatever progress was already made (see
// backend/app/scanning/job_registry.py's request_cancel). Deliberately not
// a "discard results" option: candidates/matches already saved during the
// run stay saved, only the not-yet-done remainder is skipped.
export function CancelJobButton({ onCancel }: { onCancel: () => void | Promise<void> }) {
  const [cancelling, setCancelling] = useState(false);

  async function handleClick() {
    if (cancelling) return;
    setCancelling(true);
    try {
      await onCancel();
    } finally {
      setCancelling(false);
    }
  }

  return (
    <button
      onClick={handleClick}
      disabled={cancelling}
      title="Stop now and keep whatever's already been found/saved"
      className="flex items-center gap-1 text-xs font-medium text-zinc-500 hover:text-red-600 disabled:cursor-not-allowed disabled:opacity-50 dark:text-zinc-400 dark:hover:text-red-400"
    >
      <X size={12} /> {cancelling ? "Cancelling…" : "Cancel"}
    </button>
  );
}
