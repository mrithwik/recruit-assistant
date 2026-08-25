import { useEffect, useState } from "react";
import { Inbox, RefreshCw, Sparkles, Wand2 } from "lucide-react";
import { api } from "../../lib/api";
import { useToastStore } from "../../stores/toast-store";
import { useScanStore } from "../../stores/scan-store";
import { Button } from "../ui/button";
import { Input, Label } from "../ui/input";
import { InfoTooltip } from "../ui/info-tooltip";
import { ProgressBar, useSimulatedProgress } from "../ui/progress-bar";
import { onNumberChange, selectOnFocus } from "../../lib/number-input";

const PRESETS = [
  { label: "Small (quick test)", initial: 60, followups: 20, upskill: 15 },
  { label: "Medium", initial: 800, followups: 250, upskill: 150 },
  { label: "Large (10k+, 10-year history)", initial: 7000, followups: 2200, upskill: 1400 },
];

const MOCK_MAILBOX_EMAIL = "demo@mock.local";

// In-app version of scripts/generate_sample_data.py — a recruiter can build
// a test dataset (personas, date spread, upskill journeys over years,
// deliberate incompleteness) without a terminal, per requirement 6. Result
// is kept in scan-store (not local state) so it survives navigating away
// from this page and back — see the store's comment for why.
export function SampleDataGenerator() {
  const [initial, setInitial] = useState(60);
  const [followups, setFollowups] = useState(20);
  const [upskill, setUpskill] = useState(15);
  const [seed, setSeed] = useState(42);
  const [generating, setGenerating] = useState(false);
  const push = useToastStore((s) => s.push);
  const {
    setFolderPaths,
    folderPaths,
    lastGenerated: result,
    setLastGenerated,
    emailAccounts,
    fetchEmailAccounts,
    selectAccountByEmail,
    selectedAccountIds,
  } = useScanStore();

  useEffect(() => {
    fetchEmailAccounts().catch(() => {});
  }, []);

  function applyPreset(p: (typeof PRESETS)[number]) {
    setInitial(p.initial);
    setFollowups(p.followups);
    setUpskill(p.upskill);
  }

  async function generate(regenerate = false) {
    setGenerating(true);
    try {
      const useSeed = regenerate ? Math.floor(Math.random() * 1_000_000) : seed;
      if (regenerate) setSeed(useSeed);
      const res = await api.generateSampleData(initial, followups, upskill, useSeed);
      setLastGenerated(res);
      await fetchEmailAccounts();
      push(`Generated ${res.total_items} items`, "success");
    } catch (e) {
      push(String(e), "error");
    } finally {
      setGenerating(false);
    }
  }

  function useAsFolderSource() {
    if (!result) return;
    if (!folderPaths.includes(result.resumes_dir)) {
      setFolderPaths([...folderPaths, result.resumes_dir]);
    }
    push("Added to Local folders above — scroll up and click Scan folders now", "info");
  }

  function useAsMailboxSource() {
    selectAccountByEmail(MOCK_MAILBOX_EMAIL);
    push(`Selected ${MOCK_MAILBOX_EMAIL} above — scroll up and click Scan email now`, "info");
  }

  const mockMailboxConnected = emailAccounts.some((a) => a.email_address === MOCK_MAILBOX_EMAIL);
  const mockMailboxSelected = emailAccounts.some(
    (a) => a.email_address === MOCK_MAILBOX_EMAIL && selectedAccountIds.includes(a.id),
  );

  const estimatedSeconds = Math.max(1, Math.round((initial + followups + upskill) / 100));
  const { pct, remainingSeconds, overrun } = useSimulatedProgress(estimatedSeconds, generating);

  return (
    <div className="rounded-lg border border-dashed border-indigo-200 bg-indigo-50/30 p-3 dark:border-indigo-900 dark:bg-indigo-500/5">
      <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-indigo-700 dark:text-indigo-300">
        <Wand2 size={12} /> Generate sample data
        <InfoTooltip text="Creates synthetic resumes, follow-up emails, and multi-year 'upskill' resubmissions on disk — writes to sample_data/ locally. Nothing is uploaded or sent anywhere." />
      </div>
      <p className="mb-3 text-xs text-zinc-500 dark:text-zinc-400">
        Synthetic applications, follow-ups, and multi-year "upskill" resubmissions (same person,
        later date, more experience) across 12 writing personas — for testing at volume without
        real candidate data. Available as both a local folder <em>and</em> a mock mailbox below.
      </p>

      <div className="mb-3 flex flex-wrap gap-1.5">
        {PRESETS.map((p) => (
          <button
            key={p.label}
            onClick={() => applyPreset(p)}
            className="rounded-full border border-indigo-200 bg-white px-2.5 py-1 text-xs font-medium text-indigo-700 hover:bg-indigo-50 dark:border-indigo-800 dark:bg-zinc-900 dark:text-indigo-300 dark:hover:bg-indigo-500/10"
          >
            {p.label}
          </button>
        ))}
      </div>

      <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <div>
          <Label>Applications</Label>
          <Input type="number" min={1} value={initial} onChange={onNumberChange(setInitial)} onFocus={selectOnFocus} />
        </div>
        <div>
          <Label>Follow-ups</Label>
          <Input type="number" min={0} value={followups} onChange={onNumberChange(setFollowups)} onFocus={selectOnFocus} />
        </div>
        <div>
          <Label>Upskill journeys</Label>
          <Input type="number" min={0} value={upskill} onChange={onNumberChange(setUpskill)} onFocus={selectOnFocus} />
        </div>
        <div>
          <Label>Seed</Label>
          <Input type="number" value={seed} onChange={onNumberChange(setSeed)} onFocus={selectOnFocus} />
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" icon={<Sparkles size={13} />} loading={generating} onClick={() => generate(false)}>
          Generate
        </Button>
        {result && (
          <Button
            size="sm"
            variant="secondary"
            icon={<RefreshCw size={13} />}
            loading={generating}
            onClick={() => generate(true)}
          >
            Regenerate (new random set)
          </Button>
        )}
        {!generating && <span className="text-xs text-zinc-400">~{estimatedSeconds}s estimated</span>}
      </div>

      {generating && (
        <div className="mt-3">
          <ProgressBar pct={pct} remainingSeconds={remainingSeconds} overrun={overrun} />
        </div>
      )}

      {result && (
        <div className="mt-3 rounded-md bg-white p-2.5 text-xs dark:bg-zinc-900">
          <p className="text-zinc-600 dark:text-zinc-300">
            {result.total_items} items ({result.initial_applications} applications,{" "}
            {result.followups} follow-ups, {result.upskill_resubmissions} upskill resubmissions
            from {result.upskill_journey_candidates} returning candidates)
          </p>
          <p className="mt-1 truncate text-zinc-400" title={result.resumes_dir}>
            {result.resumes_dir}
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            <Button variant="secondary" size="sm" onClick={useAsFolderSource}>
              Use as a Local folder source
            </Button>
            <Button
              variant="secondary"
              size="sm"
              icon={<Inbox size={13} />}
              onClick={useAsMailboxSource}
              disabled={!mockMailboxConnected}
            >
              {mockMailboxSelected ? "Mock mailbox selected ✓" : "Use as a mailbox source"}
            </Button>
          </div>
          {!mockMailboxConnected && (
            <p className="mt-1.5 text-zinc-400">
              Mock mailbox ({MOCK_MAILBOX_EMAIL}) connects automatically the next time the backend
              restarts with this data present — or scan folders now, no waiting required.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
