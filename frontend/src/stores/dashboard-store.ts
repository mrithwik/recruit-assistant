import { create } from "zustand";
import { api } from "../lib/api";
import type { DashboardSummary } from "../lib/types";

interface DashboardState {
  summary: DashboardSummary | null;
  loading: boolean;
  fetchSummary: () => Promise<void>;
}

export const useDashboardStore = create<DashboardState>((set) => ({
  summary: null,
  loading: false,
  fetchSummary: async () => {
    set({ loading: true });
    const summary = await api.dashboardSummary();
    set({ summary, loading: false });
  },
}));
