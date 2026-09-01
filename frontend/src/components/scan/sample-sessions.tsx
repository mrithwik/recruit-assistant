import { useEffect, useState } from "react";
import { Layers, Trash2 } from "lucide-react";
import { api } from "../../lib/api";
import { useToastStore } from "../../stores/toast-store";
import { Button } from "../ui/button";
import { InfoTooltip } from "../ui/info-tooltip";
import type { SampleSession } from "../../lib/types";

// Each "Generate sample data" click is tagged with its own session id (see
// backend app/dev_tools/session_tagging.py) so a recruiter who generated
// several batches over time — testing different sizes, or regenerating
// after a code change — can tell them apart and remove just one, instead
// of only having the wipe-everything Danger zone below.
export function SampleSessions({ refreshKey }: { refreshKey?: unknown }) {
  const [sessions, setSessions] = useState<SampleSession[] | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const push = useToastStore((s) => s.push);

  async function load() {
    try {
      setSessions(await api.listSampleSessions());
    } catch (e) {
      push(String(e), "error");
    }
  }

  useEffect(() => {
    load();
  }, [refreshKey]);

  async function handleDelete(session: SampleSession) {
    if (!confirm(`Delete "${session.label}"? This permanently removes its candidates and files.`)) return;
    setDeletingId(session.id);
    try {
      const result = await api.deleteSampleSession(session.id);
      const parts = [];
      if (result.candidates_deleted) parts.push(`${result.candidates_deleted} candidate(s) deleted`);
      if (result.candidates_trimmed) parts.push(`${result.candidates_trimmed} trimmed`);
      push(parts.length ? parts.join(", ") : "Session removed", "success");
      await load();
    } catch (e) {
      push(String(e), "error");
    } finally {
      setDeletingId(null);
    }
  }

  if (!sessions || sessions.length === 0) return null;

  return (
    <div className="rounded-lg border border-dashed border-zinc-200 bg-zinc-50/50 p-3 dark:border-zinc-800 dark:bg-zinc-900/30">
      <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-zinc-600 dark:text-zinc-300">
        <Layers size={12} /> Generated sessions
        <InfoTooltip text="Every 'Generate sample data' run is tagged with its own session, so you can remove just one batch of synthetic candidates without wiping everything else." />
      </div>
      <ul className="space-y-1.5">
        {sessions.map((s) => (
          <li
            key={s.id}
            className="flex items-center justify-between gap-3 rounded-md bg-white px-2.5 py-2 text-xs dark:bg-zinc-900"
          >
            <div className="min-w-0">
              <p className="truncate font-medium text-zinc-700 dark:text-zinc-200">{s.label}</p>
              <p className="text-zinc-400">
                {s.generated_at ? new Date(s.generated_at).toLocaleString() : "before session tracking"}
                {" · "}
                {s.scanned
                  ? `${s.candidates_scanned.toLocaleString()} candidate(s) scanned`
                  : `${s.total_items.toLocaleString()} item(s) generated, not yet scanned`}
              </p>
            </div>
            <Button
              variant="danger"
              size="sm"
              icon={<Trash2 size={13} />}
              loading={deletingId === s.id}
              onClick={() => handleDelete(s)}
            >
              Delete
            </Button>
          </li>
        ))}
      </ul>
    </div>
  );
}
