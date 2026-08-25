import { create } from "zustand";
import { persist } from "zustand/middleware";
import { api } from "../lib/api";
import type { EmailAccount, GenerateSampleDataResult, ScanResult } from "../lib/types";

interface ScanState {
  folderPaths: string[];
  includeSubfolders: boolean;
  emailAccounts: EmailAccount[];
  selectedAccountIds: string[];
  dateStart?: string;
  dateEnd?: string;
  lastResult: ScanResult | null;
  scanning: boolean;
  // Persisted separately from component state (see components/scan/sample-data-generator.tsx)
  // so navigating away from Scan Sources and back doesn't lose the last-generated dataset —
  // this was reported as "generated data not showing up when I go between tabs".
  lastGenerated: GenerateSampleDataResult | null;
  setFolderPaths: (paths: string[]) => void;
  setIncludeSubfolders: (v: boolean) => void;
  setDateRange: (start?: string, end?: string) => void;
  toggleAccount: (id: string) => void;
  selectAccountByEmail: (email: string) => void;
  fetchEmailAccounts: () => Promise<void>;
  scanFolders: () => Promise<void>;
  scanEmail: () => Promise<void>;
  setLastGenerated: (result: GenerateSampleDataResult) => void;
}

export const useScanStore = create<ScanState>()(
  persist(
    (set, get) => ({
      folderPaths: [],
      includeSubfolders: true,
      emailAccounts: [],
      selectedAccountIds: [],
      lastResult: null,
      scanning: false,
      lastGenerated: null,
      setFolderPaths: (paths) => set({ folderPaths: paths }),
      setIncludeSubfolders: (v) => set({ includeSubfolders: v }),
      setDateRange: (start, end) => set({ dateStart: start, dateEnd: end }),
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
        set({ emailAccounts });
      },
      scanFolders: async () => {
        const { folderPaths, includeSubfolders, dateStart, dateEnd } = get();
        set({ scanning: true });
        try {
          const result = await api.scanFolders(folderPaths, includeSubfolders, dateStart, dateEnd);
          set({ lastResult: result });
        } finally {
          set({ scanning: false });
        }
      },
      scanEmail: async () => {
        const { selectedAccountIds, dateStart, dateEnd } = get();
        set({ scanning: true });
        try {
          const result = await api.scanEmailAccounts(selectedAccountIds, dateStart, dateEnd);
          set({ lastResult: result });
        } finally {
          set({ scanning: false });
        }
      },
      setLastGenerated: (result) => set({ lastGenerated: result }),
    }),
    {
      name: "recruit-assistant-scan-store",
      partialize: (s) => ({
        folderPaths: s.folderPaths,
        includeSubfolders: s.includeSubfolders,
        selectedAccountIds: s.selectedAccountIds,
        lastResult: s.lastResult,
        lastGenerated: s.lastGenerated,
      }),
    },
  ),
);
