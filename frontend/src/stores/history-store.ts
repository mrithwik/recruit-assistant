import { create } from "zustand";
import { api } from "../lib/api";
import type { SearchHistoryEntry } from "../lib/types";

interface HistoryState {
  entries: SearchHistoryEntry[];
  fetchHistory: (jobId?: string) => Promise<void>;
}

export const useHistoryStore = create<HistoryState>((set) => ({
  entries: [],
  fetchHistory: async (jobId) => {
    const entries = await api.listHistory(jobId);
    set({ entries });
  },
}));
