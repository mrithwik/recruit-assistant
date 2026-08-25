import { create } from "zustand";
import { api } from "../lib/api";
import type { Criterion } from "../lib/types";

interface CriteriaState {
  criteria: Criterion[];
  fetchCriteria: (jobId?: string) => Promise<void>;
  addCriterion: (name: string, description: string, weight: number, jobId: string | null) => Promise<void>;
  rescan: (jobId: string, mode: "existing_data" | "full_rescan") => Promise<void>;
}

export const useCriteriaStore = create<CriteriaState>((set) => ({
  criteria: [],
  fetchCriteria: async (jobId) => {
    const criteria = await api.listCriteria(jobId);
    set({ criteria });
  },
  addCriterion: async (name, description, weight, jobId) => {
    const criterion = await api.addCriterion(name, description, weight, jobId);
    set((s) => ({ criteria: [...s.criteria, criterion] }));
  },
  rescan: async (jobId, mode) => {
    await api.rescan(jobId, mode);
  },
}));
