import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, FolderPlus, Inbox, Mail, Plus, ScanSearch, X } from "lucide-react";
import { DateRangePicker } from "../components/ui/date-range-picker";
import { useScanStore } from "../stores/scan-store";
import { useToastStore } from "../stores/toast-store";
import { PageHeader } from "../components/ui/page-header";
import { Card } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { InfoTooltip } from "../components/ui/info-tooltip";
import { ProgressBar, useSimulatedProgress } from "../components/ui/progress-bar";
import { TimingBadge } from "../components/ui/timing-badge";
import { SampleDataGenerator } from "../components/scan/sample-data-generator";
import { DangerZone } from "../components/scan/danger-zone";

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
    setDateRange,
    emailAccounts,
    selectedAccountIds,
    toggleAccount,
    fetchEmailAccounts,
    scanFolders,
    scanEmail,
    lastResult,
    scanning,
    lastGenerated,
  } = useScanStore();
  const push = useToastStore((s) => s.push);
  const [folderInput, setFolderInput] = useState("");
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
  }, []);

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
      />

      <div className="space-y-6">
        <div>
          <div className="mb-2 flex items-center gap-2">
            <StepBadge n={1} />
            <h2 className="text-sm font-semibold text-zinc-700 dark:text-zinc-200">
              Choose one or both sources
            </h2>
          </div>

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
          <DateRangePicker onChange={setDateRange} />
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
        <DangerZone />
      </div>
    </div>
  );
}
