import { create } from "zustand";
import { persist } from "zustand/middleware";
import { api } from "../lib/api";
import type { Job } from "../lib/types";

interface JobsState {
  jobs: Job[];
  selectedJobId: string | null;
  loading: boolean;
  fetchJobs: () => Promise<void>;
  createJob: (title: string, rawText: string, company?: string) => Promise<Job>;
  deactivateJob: (id: string) => Promise<void>;
  bulkDeactivateJobs: (ids: string[]) => Promise<void>;
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
      fetchJobs: async () => {
        set({ loading: true });
        const jobs = await api.listJobs();
        set({ jobs, loading: false });
        const { selectedJobId } = get();
        const stillExists = selectedJobId && jobs.some((j) => j.id === selectedJobId);
        if (!stillExists && jobs.length > 0) set({ selectedJobId: jobs[0].id });
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
      selectJob: (id) => set({ selectedJobId: id }),
    }),
    {
      name: "recruit-assistant-jobs-store",
      partialize: (s) => ({ selectedJobId: s.selectedJobId }),
    },
  ),
);
