import { create } from "zustand";
import { persist } from "zustand/middleware";
import { api } from "../lib/api";
import { useToastStore } from "./toast-store";
import type { EmailAccount, GenerateSampleDataResult, MockMode, ScanJob, ScanResult, ScheduledSource } from "../lib/types";

const POLL_INTERVAL_MS = 1500;

// A scan now runs as a background job (see backend/app/scanning/job_registry.py)
// instead of blocking the triggering request, since a real email scan can take
// long enough that holding one fetch open for it is bad UX and risks a
// browser/proxy timeout. This polls until the job finishes one way or another.
async function pollScanJob(jobId: string, onProgress: (progress: ScanResult | undefined) => void): Promise<ScanJob> {
  while (true) {
    const job = await api.getScanJob(jobId);
    if (job.status === "completed" || job.status === "failed") {
      return job;
    }
    onProgress(job.progress);
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
  }
}

interface ScanState {
  folderPaths: string[];
  includeSubfolders: boolean;
  emailAccounts: EmailAccount[];
  selectedAccountIds: string[];
  dateStart?: string;
  dateEnd?: string;
  // Which preset (or "custom") is highlighted in DateRangePicker — kept
  // here rather than as component-local state so it survives navigating
  // away and back (component-local state was resetting to "nothing
  // selected" on remount even though dateStart/dateEnd underneath were
  // still set, reported as "date range vanishes when I switch tabs").
  dateRangeLabel?: string;
  lastResult: ScanResult | null;
  scanning: boolean;
  scanError: string | null;
  // Live counters while a background scan job is running (see
  // job_registry.py's progress field) — replaces the old time-estimate-only
  // simulated progress bar with real numbers for a scan that can take
  // minutes at real-mailbox scale.
  scanProgress: ScanResult | null;
  // The in-flight job's id, persisted to localStorage — a page refresh (or
  // a second tab on the same origin) can't see the poll loop's in-memory
  // state, but the actual scan keeps running server-side regardless. On
  // reload, resumeActiveScanIfAny() checks this id and reattaches instead
  // of silently losing visibility into an already-running scan.
  activeJobId: string | null;
  // Persisted separately from component state (see components/scan/sample-data-generator.tsx)
  // so navigating away from Scan Sources and back doesn't lose the last-generated dataset —
  // this was reported as "generated data not showing up when I go between tabs".
  lastGenerated: GenerateSampleDataResult | null;
  // Opt-in nightly auto-scan (off by default, see backend/app/scheduler) —
  // not persisted client-side like the fields above, since the server is
  // the source of truth for which sources are scheduled.
  scheduledSources: ScheduledSource[];
  // Runtime mock/real toggles (see backend/app/runtime_settings.py) — not
  // persisted client-side, the backend is the source of truth.
  mockMode: MockMode | null;
  setFolderPaths: (paths: string[]) => void;
  setIncludeSubfolders: (v: boolean) => void;
  setDateRange: (start?: string, end?: string, label?: string) => void;
  toggleAccount: (id: string) => void;
  selectAccountByEmail: (email: string) => void;
  fetchEmailAccounts: () => Promise<void>;
  scanFolders: () => Promise<void>;
  scanEmail: () => Promise<void>;
  resumeActiveScanIfAny: () => Promise<void>;
  setLastGenerated: (result: GenerateSampleDataResult) => void;
  fetchScheduledSources: () => Promise<void>;
  setSourceAutoScan: (kind: "folder" | "email_account", ref: string, enabled: boolean, includeSubfolders?: boolean) => Promise<void>;
  fetchMockMode: () => Promise<void>;
  setUseMockLlm: (value: boolean) => Promise<void>;
  setUseMockEmail: (value: boolean) => Promise<void>;
}

export const useScanStore = create<ScanState>()(
  persist(
    (set, get) => {
      // Shared by a freshly-started scan and a reattached one: waits for
      // the job to finish, applies the result/error, and clears activeJobId
      // either way. announceViaToast is only true for the reattach path —
      // the normal button-click flow already toasts from the page's own
      // try/catch around scanFolders()/scanEmail(), so toasting here too
      // would double up.
      async function followJob(jobId: string, announceViaToast: boolean): Promise<void> {
        set({ scanning: true, scanError: null, scanProgress: null, activeJobId: jobId });
        try {
          const job = await pollScanJob(jobId, (progress) => set({ scanProgress: progress ?? null }));
          if (job.status === "failed") {
            const message = job.error ?? "Scan failed.";
            set({ scanError: message });
            if (announceViaToast) useToastStore.getState().push(message, "error");
            throw new Error(message);
          }
          set({ lastResult: job.result ?? null });
          if (announceViaToast) useToastStore.getState().push("Scan complete", "success");
        } finally {
          set({ scanning: false, scanProgress: null, activeJobId: null });
        }
      }

      return {
        folderPaths: [],
        includeSubfolders: true,
        emailAccounts: [],
        selectedAccountIds: [],
        lastResult: null,
        scanning: false,
        scanError: null,
        scanProgress: null,
        activeJobId: null,
        lastGenerated: null,
        scheduledSources: [],
        mockMode: null,
        setFolderPaths: (paths) => set({ folderPaths: paths }),
        setIncludeSubfolders: (v) => set({ includeSubfolders: v }),
        setDateRange: (start, end, label) => set({ dateStart: start, dateEnd: end, dateRangeLabel: label }),
        toggleAccount: (id) =>
          set((s) => ({
            selectedAccountIds: s.selectedAccountIds.includes(id)
              ? s.selectedAccountIds.filter((a) => a !== id)
              : [...s.selectedAccountIds, id],
          })),
        selectAccountByEmail: (email) => {
          const account = get().emailAccounts.find((a) => a.email_address === email);
          if (!account) return;
          set((s) =>
            s.selectedAccountIds.includes(account.id)
              ? s
              : { selectedAccountIds: [...s.selectedAccountIds, account.id] },
          );
        },
        fetchEmailAccounts: async () => {
          const emailAccounts = await api.listEmailAccounts();
          // selectedAccountIds is persisted to localStorage, so an id from
          // a disconnected/reconnected account (which gets a new row and a
          // new id) can linger and get silently sent on the next scan even
          // though nothing shows it as selected — prune against the fresh
          // account list every time it's fetched.
          const validIds = new Set(emailAccounts.map((a) => a.id));
          set((s) => ({
            emailAccounts,
            selectedAccountIds: s.selectedAccountIds.filter((id) => validIds.has(id)),
          }));
        },
        scanFolders: async () => {
          const { folderPaths, includeSubfolders, dateStart, dateEnd } = get();
          const started = await api.scanFolders(folderPaths, includeSubfolders, dateStart, dateEnd);
          await followJob(started.id, false);
        },
        scanEmail: async () => {
          const { selectedAccountIds, dateStart, dateEnd } = get();
          const started = await api.scanEmailAccounts(selectedAccountIds, dateStart, dateEnd);
          await followJob(started.id, false);
        },
        resumeActiveScanIfAny: async () => {
          const { activeJobId, scanning } = get();
          if (!activeJobId || scanning) return; // already following it, or nothing to resume
          try {
            const job = await api.getScanJob(activeJobId);
            if (job.status === "running") {
              await followJob(activeJobId, true);
            } else {
              // Finished while we were away (refresh, closed tab, another
              // device) — surface it now instead of leaving it unseen.
              if (job.status === "failed") {
                useToastStore.getState().push(job.error ?? "Scan failed.", "error");
              } else {
                set({ lastResult: job.result ?? null });
                useToastStore.getState().push("Scan complete", "success");
              }
              set({ activeJobId: null });
            }
          } catch {
            // 404 — backend restarted since (job registry is intentionally
            // in-memory only) or some other lookup failure. Nothing to
            // reattach to; just drop the stale reference.
            set({ activeJobId: null });
          }
        },
        setLastGenerated: (result) => set({ lastGenerated: result }),
        fetchScheduledSources: async () => {
          const scheduledSources = await api.listScheduledSources();
          set({ scheduledSources });
        },
        setSourceAutoScan: async (kind, ref, enabled, includeSubfolders = true) => {
          const { scheduledSources } = get();
          const existing = scheduledSources.find((s) => s.kind === kind && s.ref === ref);
          if (enabled) {
            if (existing) return;
            const created = await api.addScheduledSource(kind, ref, includeSubfolders);
            set({ scheduledSources: [...scheduledSources, created] });
          } else {
            if (!existing) return;
            await api.removeScheduledSource(existing.id);
            set({ scheduledSources: scheduledSources.filter((s) => s.id !== existing.id) });
          }
        },
        fetchMockMode: async () => {
          const mockMode = await api.getMockMode();
          set({ mockMode });
        },
        setUseMockLlm: async (value) => {
          const mockMode = await api.updateMockMode({ use_mock_llm: value });
          set({ mockMode });
        },
        setUseMockEmail: async (value) => {
          const mockMode = await api.updateMockMode({ use_mock_email: value });
          set({ mockMode });
        },
      };
    },
    {
      name: "recruit-assistant-scan-store",
      partialize: (s) => ({
        folderPaths: s.folderPaths,
        includeSubfolders: s.includeSubfolders,
        selectedAccountIds: s.selectedAccountIds,
        dateStart: s.dateStart,
        dateEnd: s.dateEnd,
        dateRangeLabel: s.dateRangeLabel,
        lastResult: s.lastResult,
        lastGenerated: s.lastGenerated,
        activeJobId: s.activeJobId,
      }),
    },
  ),
);
