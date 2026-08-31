import { create } from "zustand";
import { persist } from "zustand/middleware";
import { api } from "../lib/api";
import { useToastStore } from "./toast-store";
import type { ScanResult } from "../lib/types";

const POLL_INTERVAL_MS = 1500;

interface TaskRunState {
  jobId: string | null;
  running: boolean;
  progress: ScanResult | null;
  lastResult: ScanResult | null;
}

interface MaintenanceState {
  runs: Record<string, TaskRunState>;
  run: (taskId: string) => Promise<void>;
  resumeIfAny: (taskId: string) => Promise<void>;
}

const EMPTY_RUN: TaskRunState = { jobId: null, running: false, progress: null, lastResult: null };

function runFor(runs: Record<string, TaskRunState>, taskId: string): TaskRunState {
  return runs[taskId] ?? EMPTY_RUN;
}

// Data maintenance tasks (Scan Sources panel + Dashboard's "Updates
// available" banner both render MaintenanceTaskRow for the same task, so a
// run started from either surface stays visible on both) — persisted per
// task id so a run survives navigating away, a refresh, or a logout/login,
// same as every other long-running action.
export const useMaintenanceStore = create<MaintenanceState>()(
  persist(
    (set, get) => {
      async function follow(taskId: string, jobId: string): Promise<void> {
        set((s) => ({ runs: { ...s.runs, [taskId]: { ...runFor(s.runs, taskId), jobId, running: true, progress: null } } }));
        try {
          while (true) {
            const job = await api.getScanJob(jobId);
            if (job.status === "completed") {
              const push = useToastStore.getState().push;
              if (job.result) {
                const r = job.result;
                const parts = [`${r.candidates_created} updated`];
                if (r.duplicates_skipped) parts.push(`${r.duplicates_skipped} skipped`);
                if (r.errors.length) parts.push(`${r.errors.length} error(s)`);
                push(`Done — ${r.resumes_found} checked — ${parts.join(", ")}`, "success");
              }
              set((s) => ({
                runs: { ...s.runs, [taskId]: { jobId: null, running: false, progress: null, lastResult: job.result ?? null } },
              }));
              return;
            }
            if (job.status === "failed") {
              useToastStore.getState().push(job.error ?? "Maintenance task failed.", "error");
              set((s) => ({ runs: { ...s.runs, [taskId]: { ...runFor(s.runs, taskId), jobId: null, running: false, progress: null } } }));
              return;
            }
            set((s) => ({ runs: { ...s.runs, [taskId]: { ...runFor(s.runs, taskId), progress: job.progress ?? null } } }));
            await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
          }
        } catch {
          set((s) => ({ runs: { ...s.runs, [taskId]: { ...runFor(s.runs, taskId), jobId: null, running: false, progress: null } } }));
        }
      }

      return {
        runs: {},
        run: async (taskId) => {
          const job = await api.runMaintenanceTask(taskId);
          await follow(taskId, job.id);
        },
        resumeIfAny: async (taskId) => {
          const current = runFor(get().runs, taskId);
          if (!current.jobId || current.running) return;
          try {
            const job = await api.getScanJob(current.jobId);
            if (job.status === "running") {
              await follow(taskId, current.jobId);
            } else {
              set((s) => ({ runs: { ...s.runs, [taskId]: { ...runFor(s.runs, taskId), jobId: null } } }));
            }
          } catch {
            set((s) => ({ runs: { ...s.runs, [taskId]: { ...runFor(s.runs, taskId), jobId: null } } }));
          }
        },
      };
    },
    {
      name: "recruit-assistant-maintenance-store",
      partialize: (s) => ({ runs: s.runs }),
    },
  ),
);

export function useTaskRun(taskId: string): TaskRunState {
  return useMaintenanceStore((s) => runFor(s.runs, taskId));
}
