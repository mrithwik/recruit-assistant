import { useEffect, useState } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";
import { Modal } from "../ui/modal";
import { Input, Label, Textarea } from "../ui/input";
import { api } from "../../lib/api";
import type { DraftEmail, Match } from "../../lib/types";

export function DraftEmailModal({ match, onClose }: { match: Match; onClose: () => void }) {
  const [draft, setDraft] = useState<DraftEmail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .draftEmail(match.id)
      .then(setDraft)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [match.id]);

  return (
    <Modal title={`Draft email to ${match.candidate.legal_first_name}`} onClose={onClose}>
      {loading && (
        <div className="flex items-center gap-2 py-6 text-sm text-zinc-500 dark:text-zinc-400">
          <Loader2 size={16} className="animate-spin" /> Generating draft…
        </div>
      )}
      {error && (
        <p className="flex items-center gap-2 rounded-lg bg-red-50 p-3 text-sm text-red-700 dark:bg-red-500/10 dark:text-red-300">
          <AlertTriangle size={14} /> {error}
        </p>
      )}
      {draft && (
        <div className="space-y-4 text-sm">
          {draft.missing_required_fields.length > 0 && (
            <div className="flex items-start gap-2 rounded-lg bg-orange-50 p-3 text-orange-800 dark:bg-orange-500/10 dark:text-orange-300">
              <AlertTriangle size={15} className="mt-0.5 shrink-0" />
              <span>Missing required fields before sending: {draft.missing_required_fields.join(", ")}</span>
            </div>
          )}
          <div>
            <Label>Subject</Label>
            <Input defaultValue={draft.subject} />
          </div>
          <div>
            <Label>Body</Label>
            <Textarea defaultValue={draft.body} rows={10} />
          </div>
        </div>
      )}
    </Modal>
  );
}
