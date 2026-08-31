import { create } from "zustand";
import { persist } from "zustand/middleware";
import { api } from "../lib/api";
import type { Job } from "../lib/types";

interface JobsState {
  jobs: Job[];
  selectedJobId: string | null;
  loading: boolean;
  // Deactivated jobs — the undo path for a single delete once the toast's
  // own "Undo" button has timed out. Fetched on demand (Jobs page's
  // "Inactive jobs" section), not kept in sync automatically.
  inactiveJobs: Job[];
  inactiveJobsLoading: boolean;
  fetchJobs: () => Promise<void>;
  fetchInactiveJobs: () => Promise<void>;
  createJob: (title: string, rawText: string, company?: string) => Promise<Job>;
  deactivateJob: (id: string) => Promise<void>;
  bulkDeactivateJobs: (ids: string[]) => Promise<void>;
  reactivateJob: (id: string) => Promise<void>;
  selectJob: (id: string) => void;
}

// selectedJobId is persisted so Match Results shows the same job (and,
// via matches-store's own persistence, the same results) after a refresh
// instead of silently falling back to jobs[0] — see results-page.tsx's
// "Load results" button change for why this mattered more once loads
// stopped happening automatically on every state change.
export const useJobsStore = create<JobsState>()(
  persist(
    (set, get) => ({
      jobs: [],
      selectedJobId: null,
      loading: false,
      inactiveJobs: [],
      inactiveJobsLoading: false,
      fetchJobs: async () => {
        set({ loading: true });
        const jobs = await api.listJobs();
        set({ jobs, loading: false });
        const { selectedJobId } = get();
        const stillExists = selectedJobId && jobs.some((j) => j.id === selectedJobId);
        if (!stillExists && jobs.length > 0) set({ selectedJobId: jobs[0].id });
      },
      fetchInactiveJobs: async () => {
        set({ inactiveJobsLoading: true });
        try {
          const inactiveJobs = await api.listInactiveJobs();
          set({ inactiveJobs });
        } finally {
          set({ inactiveJobsLoading: false });
        }
      },
      createJob: async (title, rawText, company = "") => {
        const job = await api.createJob(title, rawText, company);
        set((s) => ({ jobs: [job, ...s.jobs], selectedJobId: job.id }));
        return job;
      },
      deactivateJob: async (id) => {
        await api.deactivateJob(id);
        set((s) => ({ jobs: s.jobs.filter((j) => j.id !== id) }));
      },
      bulkDeactivateJobs: async (ids) => {
        await api.bulkDeleteJobs(ids);
        set((s) => ({ jobs: s.jobs.filter((j) => !ids.includes(j.id)) }));
      },
      reactivateJob: async (id) => {
        const job = await api.reactivateJob(id);
        set((s) => ({
          jobs: s.jobs.some((j) => j.id === id) ? s.jobs : [job, ...s.jobs],
          inactiveJobs: s.inactiveJobs.filter((j) => j.id !== id),
        }));
      },
      selectJob: (id) => set({ selectedJobId: id }),
    }),
    {
      name: "recruit-assistant-jobs-store",
      partialize: (s) => ({ selectedJobId: s.selectedJobId }),
    },
  ),
);
