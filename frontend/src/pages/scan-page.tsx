import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, CheckCircle2, Clock, FolderPlus, History, Inbox, Mail, Plus, ScanSearch, X } from "lucide-react";
import { DateRangePicker } from "../components/ui/date-range-picker";
import { useScanStore } from "../stores/scan-store";
import { useToastStore } from "../stores/toast-store";
import { PageHeader } from "../components/ui/page-header";
import { Card } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { InfoTooltip } from "../components/ui/info-tooltip";
import { Toggle } from "../components/ui/toggle";
import { ProgressBar, useSimulatedProgress } from "../components/ui/progress-bar";
import { CancelJobButton } from "../components/ui/cancel-job-button";
import { TimingBadge } from "../components/ui/timing-badge";
import { SampleDataGenerator } from "../components/scan/sample-data-generator";
import { DangerZone } from "../components/scan/danger-zone";
import { MaintenanceTasks } from "../components/scan/maintenance-tasks";
import { LlmConsentModal } from "../components/scan/llm-consent-modal";

// Redesigned per feedback that the page read as one undifferentiated block —
// this lays it out as three explicit numbered steps (pick a source, set a
// range, scan), with a tooltip on each source explaining what it actually
// does, since "local folder" vs "connected mailbox" wasn't obvious to a
// first-time recruiter.
function StepBadge({ n }: { n: number }) {
  return (
    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-indigo-600 text-[11px] font-bold text-white">
      {n}
    </span>
  );
}

export function ScanPage() {
  const {
    folderPaths,
    setFolderPaths,
    includeSubfolders,
    setIncludeSubfolders,
    dateStart,
    dateEnd,
    dateRangeLabel,
    setDateRange,
    emailAccounts,
    selectedAccountIds,
    toggleAccount,
    fetchEmailAccounts,
    scanFolders,
    scanEmail,
    resumeActiveScanIfAny,
    lastResult,
    scanning,
    scanProgress,
    cancelActiveScan,
    lastGenerated,
    scheduledSources,
    fetchScheduledSources,
    setSourceAutoScan,
    mockMode,
    fetchMockMode,
    setUseMockLlm,
    setUseMockEmail,
  } = useScanStore();
  const push = useToastStore((s) => s.push);
  const [folderInput, setFolderInput] = useState("");
  const isAutoScanned = (kind: "folder" | "email_account", ref: string) =>
    scheduledSources.some((s) => s.kind === kind && s.ref === ref);
  // Best available proxy for scan volume: the last generated dataset's item
  // count (the overwhelmingly common case for mock-mode testing). Falls
  // back to a flat guess only when nothing's been generated yet — a flat
  // guess regardless of real volume is what made large scans look stuck at
  // 95% for a long time previously.
  const estimatedTotalItems = lastGenerated?.total_items ?? (folderPaths.length + selectedAccountIds.length) * 200;
  const estimatedSeconds = Math.max(4, Math.round(estimatedTotalItems / 150));
  const { pct, remainingSeconds, overrun } = useSimulatedProgress(estimatedSeconds, scanning);

  useEffect(() => {
    fetchEmailAccounts().catch(() => {});
    fetchScheduledSources().catch(() => {});
    fetchMockMode().catch(() => {});
    // Reattach to a scan that was already running before a refresh (or in
    // another tab) instead of silently losing visibility into it — see
    // scan-store.ts's resumeActiveScanIfAny.
    resumeActiveScanIfAny().catch(() => {});
  }, []);

  const [showLlmConsent, setShowLlmConsent] = useState(false);

  async function toggleMockLlm(next: boolean) {
    // Turning real mode on for the first time ever needs an explicit
    // acknowledgment before resume text/job descriptions leave the machine
    // (see llm-consent-modal.tsx) — once given, it's never asked again, so
    // this only intercepts when consent isn't already on record.
    if (next === false && mockMode && !mockMode.real_llm_consent_given) {
      setShowLlmConsent(true);
      return;
    }
    try {
      await setUseMockLlm(next);
    } catch (e) {
      push(String(e), "error");
    }
  }

  async function confirmLlmConsent() {
    try {
      await setUseMockLlm(false, true);
    } catch (e) {
      push(String(e), "error");
    } finally {
      setShowLlmConsent(false);
    }
  }

  async function toggleMockEmail(next: boolean) {
    try {
      await setUseMockEmail(next);
    } catch (e) {
      push(String(e), "error");
    }
  }

  function addFolder() {
    if (!folderInput.trim()) return;
    setFolderPaths([...folderPaths, folderInput.trim()]);
    setFolderInput("");
  }

  async function runFolderScan() {
    try {
      await scanFolders();
      push("Folder scan complete", "success");
    } catch (e) {
      push(String(e), "error");
    }
  }

  async function runEmailScan() {
    try {
      await scanEmail();
      push("Email scan complete", "success");
    } catch (e) {
      push(String(e), "error");
    }
  }

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title="Scan Sources"
        description="Three steps: pick where to look, set a date range, then scan. Local folders and connected mailboxes both work — alone or together."
        action={
          <Link
            to="/app/scan/logs"
            className="flex items-center gap-1 text-xs font-medium text-indigo-600 hover:underline dark:text-indigo-400"
          >
            <History size={13} /> View scan activity log
          </Link>
        }
      />

      {mockMode?.expose_toggle && (
        <Card className="mb-6 border-amber-200 bg-amber-50/40 dark:border-amber-900 dark:bg-amber-500/5">
          <h2 className="mb-3 text-sm font-semibold text-zinc-700 dark:text-zinc-200">Data mode</h2>
          <div className="space-y-3">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-1.5">
                <span className="text-sm text-zinc-700 dark:text-zinc-200">
                  Email source: {mockMode.use_mock_email ? "Mock fixtures" : "Real connected accounts"}
                </span>
                <InfoTooltip text="Mock scans a small built-in fixture inbox — no OAuth or real data touched. Real scans your actually-connected Gmail/Outlook accounts." />
              </div>
              <Toggle
                label="Use real connected email accounts instead of mock fixtures"
                checked={!mockMode.use_mock_email}
                onChange={(checked) => toggleMockEmail(!checked)}
              />
            </div>
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-1.5">
                <span className="text-sm text-zinc-700 dark:text-zinc-200">
                  LLM processing: {mockMode.use_mock_llm ? "Mock (free, instant)" : "Real (uses your API key)"}
                </span>
                <InfoTooltip text="Mock parsing/summarization/embedding is free and instant, using canned logic instead of a real model. Real mode calls your configured OpenRouter/OpenAI key for every resume — for a large scan that's real cost and real time." />
              </div>
              <Toggle
                label="Use real LLM processing instead of mock responses"
                checked={!mockMode.use_mock_llm}
                onChange={(checked) => toggleMockLlm(!checked)}
                disabled={!mockMode.real_llm_available && mockMode.use_mock_llm}
              />
            </div>
            {!mockMode.real_llm_available && (
              <p className="flex items-center gap-1.5 text-xs text-amber-700 dark:text-amber-400">
                <AlertTriangle size={12} /> No OPENROUTER_API_KEY or OPENAI_API_KEY configured — add one to
                .env and restart the backend to enable real LLM processing.
              </p>
            )}
            {!mockMode.use_mock_llm && (
              <p className="flex items-center gap-1.5 text-xs text-amber-700 dark:text-amber-400">
                <AlertTriangle size={12} /> Real LLM processing is on — every resume in your next scan will
                call your configured provider and incur real cost.
              </p>
            )}
          </div>
        </Card>
      )}

      <div className="space-y-6">
        <div>
          <div className="mb-2 flex items-center gap-2">
            <StepBadge n={1} />
            <h2 className="text-sm font-semibold text-zinc-700 dark:text-zinc-200">
              Choose one or both sources
            </h2>
          </div>
          <p className="mb-2 flex items-center gap-1 text-xs text-zinc-400">
            <Clock size={11} /> next to a source toggles nightly auto-scan for it — off by
            default, and only takes effect if a server admin has also enabled the scheduler
            (<code className="rounded bg-zinc-100 px-1 dark:bg-zinc-800">SCHEDULER_ENABLED=true</code>).
          </p>

          <div className="space-y-3">
            <Card>
              <div className="mb-3 flex items-center gap-2">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600 dark:bg-indigo-500/10 dark:text-indigo-400">
                  <FolderPlus size={15} />
                </div>
                <h3 className="font-medium text-zinc-900 dark:text-white">Local folders</h3>
                <InfoTooltip text="Points the scanner at folders already on this computer. It reads every PDF/DOCX/TXT inside (and subfolders, if enabled) — nothing leaves your machine." />
              </div>

              <div className="mb-3 flex gap-2">
                <Input
                  value={folderInput}
                  onChange={(e) => setFolderInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && addFolder()}
                  placeholder="/Users/you/Resumes"
                />
                <Button variant="secondary" icon={<Plus size={15} />} onClick={addFolder}>
                  Add
                </Button>
              </div>

              {folderPaths.length > 0 && (
                <ul className="mb-4 flex flex-wrap gap-2">
                  {folderPaths.map((p) => (
                    <li
                      key={p}
                      className="flex items-center gap-1.5 rounded-md bg-zinc-100 py-1 pl-2.5 pr-1.5 text-xs font-medium text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300"
                    >
                      {p}
                      <button
                        title={isAutoScanned("folder", p) ? "Auto-scan nightly: on" : "Auto-scan nightly: off"}
                        className={`rounded p-0.5 hover:bg-zinc-200 dark:hover:bg-zinc-700 ${isAutoScanned("folder", p) ? "text-indigo-600 dark:text-indigo-400" : "text-zinc-400"}`}
                        onClick={() => setSourceAutoScan("folder", p, !isAutoScanned("folder", p), includeSubfolders)}
                      >
                        <Clock size={12} />
                      </button>
                      <button
                        className="rounded p-0.5 text-zinc-400 hover:bg-zinc-200 hover:text-red-600 dark:hover:bg-zinc-700"
                        onClick={() => setFolderPaths(folderPaths.filter((f) => f !== p))}
                      >
                        <X size={12} />
                      </button>
                    </li>
                  ))}
                </ul>
              )}

              <label className="flex items-center gap-2 text-sm text-zinc-600 dark:text-zinc-300">
                <input
                  type="checkbox"
                  checked={includeSubfolders}
                  onChange={(e) => setIncludeSubfolders(e.target.checked)}
                  className="h-4 w-4 rounded border-zinc-300 text-indigo-600 focus:ring-indigo-500"
                />
                Include subfolders
              </label>
            </Card>

            <Card>
              <div className="mb-3 flex items-center gap-2">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600 dark:bg-indigo-500/10 dark:text-indigo-400">
                  <Mail size={15} />
                </div>
                <h3 className="font-medium text-zinc-900 dark:text-white">Connected mailboxes</h3>
                <InfoTooltip text="Scans read-only for resume attachments in the date range below, in any mailbox you've connected on the Email Access tab. Resumes found are also saved locally so they're browsable offline afterward." />
              </div>

              {emailAccounts.length === 0 ? (
                <p className="flex items-center gap-2 rounded-lg bg-zinc-50 px-3 py-2.5 text-sm text-zinc-500 dark:bg-zinc-800/50 dark:text-zinc-400">
                  <Inbox size={15} className="shrink-0" />
                  No email accounts connected — go to the Email Access tab to connect Gmail or Outlook
                  (or generate a mock mailbox below for testing).
                </p>
              ) : (
                <ul className="flex flex-col gap-1.5">
                  {emailAccounts.map((a) => (
                    <li key={a.id} className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm hover:bg-zinc-50 dark:hover:bg-zinc-800/60">
                      <input
                        type="checkbox"
                        checked={selectedAccountIds.includes(a.id)}
                        onChange={() => toggleAccount(a.id)}
                        className="h-4 w-4 rounded border-zinc-300 text-indigo-600 focus:ring-indigo-500"
                      />
                      <span className="text-zinc-700 dark:text-zinc-200">{a.email_address}</span>
                      <span className="text-zinc-400">({a.provider})</span>
                      <button
                        title={isAutoScanned("email_account", a.id) ? "Auto-scan nightly: on" : "Auto-scan nightly: off"}
                        className={`ml-auto rounded p-0.5 hover:bg-zinc-200 dark:hover:bg-zinc-700 ${isAutoScanned("email_account", a.id) ? "text-indigo-600 dark:text-indigo-400" : "text-zinc-400"}`}
                        onClick={() => setSourceAutoScan("email_account", a.id, !isAutoScanned("email_account", a.id))}
                      >
                        <Clock size={13} />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
        </div>

        <div>
          <div className="mb-2 flex items-center gap-2">
            <StepBadge n={2} />
            <h2 className="text-sm font-semibold text-zinc-700 dark:text-zinc-200">Set a date range</h2>
            <InfoTooltip text="Applies to both sources at once — narrows the scan to resumes/emails submitted in this window. Leave it open-ended to scan everything." />
          </div>
          <DateRangePicker start={dateStart} end={dateEnd} activeLabel={dateRangeLabel} onChange={setDateRange} />
        </div>

        <div>
          <div className="mb-2 flex items-center gap-2">
            <StepBadge n={3} />
            <h2 className="text-sm font-semibold text-zinc-700 dark:text-zinc-200">Scan</h2>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button icon={<ScanSearch size={15} />} loading={scanning} disabled={folderPaths.length === 0} onClick={runFolderScan}>
              Scan folders now
            </Button>
            <Button
              icon={<ScanSearch size={15} />}
              loading={scanning}
              disabled={selectedAccountIds.length === 0}
              onClick={runEmailScan}
            >
              Scan email now
            </Button>
          </div>

          {scanning && (
            <div className="mt-3">
              <ProgressBar pct={pct} label="Scanning and matching candidate identities…" remainingSeconds={remainingSeconds} overrun={overrun} />
              <div className="mt-2 flex items-center justify-between">
                {scanProgress ? (
                  <p className="text-xs text-zinc-500 dark:text-zinc-400" aria-live="polite">
                    {scanProgress.resumes_found} resume(s) processed so far — {scanProgress.candidates_created} new,{" "}
                    {scanProgress.candidates_updated} updated, {scanProgress.duplicates_skipped} already scanned
                    {scanProgress.errors.length > 0 && `, ${scanProgress.errors.length} error(s)`}
                  </p>
                ) : (
                  <span />
                )}
                <CancelJobButton onCancel={cancelActiveScan} />
              </div>
            </div>
          )}
        </div>

        {lastResult && (
          <Card className="border-emerald-200 bg-emerald-50/40 dark:border-emerald-900 dark:bg-emerald-500/5">
            <div className="mb-2 flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 text-emerald-700 dark:text-emerald-400">
                <CheckCircle2 size={15} />
                <span className="text-sm font-semibold">Scan complete</span>
              </div>
              <TimingBadge seconds={lastResult.elapsed_seconds} label="Processed" />
            </div>
            <dl className="grid grid-cols-4 gap-3 text-sm">
              <div>
                <dt className="text-zinc-500 dark:text-zinc-400">Resumes found</dt>
                <dd className="text-lg font-semibold text-zinc-900 dark:text-white">{lastResult.resumes_found}</dd>
              </div>
              <div>
                <dt className="text-zinc-500 dark:text-zinc-400">New candidates</dt>
                <dd className="text-lg font-semibold text-zinc-900 dark:text-white">{lastResult.candidates_created}</dd>
              </div>
              <div>
                <dt className="text-zinc-500 dark:text-zinc-400">Profiles updated</dt>
                <dd className="text-lg font-semibold text-zinc-900 dark:text-white">{lastResult.candidates_updated}</dd>
              </div>
              <div>
                <dt className="text-zinc-500 dark:text-zinc-400">Already scanned</dt>
                <dd className="text-lg font-semibold text-zinc-900 dark:text-white">{lastResult.duplicates_skipped}</dd>
              </div>
            </dl>
            {lastResult.errors.length > 0 && (
              <p className="mt-3 flex items-center gap-1.5 text-sm text-red-600 dark:text-red-400">
                <AlertTriangle size={14} /> {lastResult.errors.length} error(s) — see logs
              </p>
            )}
          </Card>
        )}

        <SampleDataGenerator />
        <MaintenanceTasks />
        <DangerZone />
      </div>

      {showLlmConsent && (
        <LlmConsentModal onConfirm={confirmLlmConsent} onClose={() => setShowLlmConsent(false)} />
      )}
    </div>
  );
}
