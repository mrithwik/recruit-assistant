import { useState } from "react";
import { AlertTriangle } from "lucide-react";
import { Modal } from "../ui/modal";
import { Button } from "../ui/button";

// One-time gate the first time real LLM mode is turned on — see
// scan-page.tsx. Persisted server-side (User.real_llm_consent_given_at, see
// mock_mode.py), so this is never shown again on this installation once
// accepted, even though the mock/real toggle itself resets to mock on every
// backend restart (existing, unchanged behavior — this modal is only about
// the one-time acknowledgment, not the toggle's own persistence).
export function LlmConsentModal({ onConfirm, onClose }: { onConfirm: () => void; onClose: () => void }) {
  const [confirming, setConfirming] = useState(false);

  async function handleConfirm() {
    setConfirming(true);
    onConfirm();
  }

  return (
    <Modal title="Turn on real LLM processing?" onClose={onClose}>
      <div className="space-y-3 text-sm text-zinc-600 dark:text-zinc-300">
        <p className="flex items-start gap-2 rounded-lg bg-amber-50 p-3 text-amber-800 dark:bg-amber-500/10 dark:text-amber-300">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
          <span>
            Turning this on sends the full text of every resume being scored, plus the job
            description, to your configured OpenRouter/OpenAI API key — for as long as real mode
            stays on.
          </span>
        </p>
        <p>
          This is a one-time acknowledgment — you won't be asked again on this installation. The
          toggle itself still resets to mock mode on every backend restart, so you may need to
          turn it back on in a future session, but you won't see this dialog again.
        </p>
      </div>
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="secondary" size="sm" onClick={onClose}>
          Cancel
        </Button>
        <Button variant="danger" size="sm" loading={confirming} onClick={handleConfirm}>
          I understand, enable real matching
        </Button>
      </div>
    </Modal>
  );
}
