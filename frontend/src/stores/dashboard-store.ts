import { create } from "zustand";
import { api } from "../lib/api";
import type { DashboardSummary } from "../lib/types";

interface DashboardState {
  summary: DashboardSummary | null;
  loading: boolean;
  fetchSummary: (dataMode?: string) => Promise<void>;
}

export const useDashboardStore = create<DashboardState>((set) => ({
  summary: null,
  loading: false,
  fetchSummary: async (dataMode) => {
    set({ loading: true });
    const summary = await api.dashboardSummary(dataMode);
    set({ summary, loading: false });
  },
}));
