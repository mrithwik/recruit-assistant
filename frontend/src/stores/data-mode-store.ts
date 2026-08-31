import { create } from "zustand";
import { persist } from "zustand/middleware";
import { api } from "../lib/api";
import type { DataModeCounts } from "../lib/types";

export type DataMode = "all" | "real" | "mock";

interface DataModeState {
  dataMode: DataMode;
  counts: DataModeCounts | null;
  setDataMode: (mode: DataMode) => void;
  fetchCounts: () => Promise<void>;
}

// A global "All / Real / Mock" toggle — lets a recruiter who loaded a large
// sample dataset for testing (see the sample-data generator) view or work
// with just their real candidates, or just the sample set, without deleting
// either. Persisted so it survives a refresh; consumed by All Candidates,
// Match Results, and the Dashboard.
export const useDataModeStore = create<DataModeState>()(
  persist(
    (set) => ({
      dataMode: "all",
      counts: null,
      setDataMode: (mode) => set({ dataMode: mode }),
      fetchCounts: async () => {
        const counts = await api.getDataModeCounts();
        set({ counts });
      },
    }),
    { name: "recruit-assistant-data-mode-store" },
  ),
);
