import { create } from "zustand";
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

export const useJobsStore = create<JobsState>((set, get) => ({
  jobs: [],
  selectedJobId: null,
  loading: false,
  fetchJobs: async () => {
    set({ loading: true });
    const jobs = await api.listJobs();
    set({ jobs, loading: false });
    if (!get().selectedJobId && jobs.length > 0) set({ selectedJobId: jobs[0].id });
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
}));
