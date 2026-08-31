import { create } from "zustand";
import { persist } from "zustand/middleware";
import { useMatchesStore } from "./matches-store";
import { useJobsStore } from "./jobs-store";
import { useToastStore } from "./toast-store";

export type BulkJobsOp = "match" | "update_matched";

interface BulkJobsState {
  opType: BulkJobsOp | null;
  jobIds: string[];
  index: number;
  running: boolean;
  successCount: number;
  skippedCount: number;
  failures: string[];
  // One id per bulk run, sent with every step (see routes/matches.py's
  // batch_id param) so Recent Activity collapses the whole run into one
  // expandable entry instead of one row per job. Persisted so a resumed
  // loop (after a refresh) keeps grouping under the same batch instead of
  // splitting into "before" and "after" entries.
  batchId: string | null;
  // In-memory only (not persisted — a stop request only means anything for
  // the loop instance currently executing; after a refresh there's nothing
  // running to stop, resumeIfAny would just start a fresh loop). Checked
  // between steps; also cancels whichever step is actually in flight right
  // now so "stop" doesn't just mean "stop queuing more" while the current
  // one keeps running to completion regardless.
  stopRequested: boolean;
  start: (op: BulkJobsOp, jobIds: string[]) => Promise<void>;
  resumeIfAny: () => Promise<void>;
  stop: () => Promise<void>;
}

function jobTitleFor(jobId: string): string {
  const job = useJobsStore.getState().jobs.find((j) => j.id === jobId);
  return job?.title ?? jobId;
}

// One step of a bulk match/update-matched run. If a refresh happened mid-step,
// matches-store's own activeRunForJobId/activeRescanForJobId will already
// point at this exact job (its persisted job-id tracking survives the
// reload) — reattach to that instead of firing a second request, which
// would otherwise 409 against the backend's still-running job for the same
// scope.
async function runOneStep(op: BulkJobsOp, jobId: string, batchId: string | null): Promise<"success" | "skipped" | "failed"> {
  const matchesStore = useMatchesStore.getState();
  try {
    if (op === "match") {
      if (matchesStore.activeRunForJobId === jobId) {
        await matchesStore.resumeRunMatchingIfAny();
      } else {
        await matchesStore.runMatching(jobId, batchId ?? undefined);
      }
    } else {
      if (matchesStore.activeRescanForJobId === jobId) {
        await matchesStore.resumeRescanIfAny();
      } else {
        await matchesStore.rescanMatched(jobId, batchId ?? undefined);
      }
    }
    return "success";
  } catch (e) {
    const msg = String(e);
    if (op === "update_matched" && msg.includes("No matches yet")) return "skipped";
    return "failed";
  }
}

// Bulk "Match all"/"Match selected" and "Update matched (N)"/"Update
// selected" on the Jobs page — a sequential loop over N jobs, persisted so
// it survives a tab switch (the old version lived in JobsPage's local
// useState and silently kept running in the background with no visible
// progress once the page unmounted), a refresh, or a logout/login (each
// individual step is itself a job-registry-backed background job; this
// store just tracks which step the loop is on).
export const useBulkJobsStore = create<BulkJobsState>()(
  persist(
    (set, get) => {
      async function loop(): Promise<void> {
        set({ running: true, stopRequested: false });
        try {
          while (get().index < get().jobIds.length && !get().stopRequested) {
            const { jobIds, index, opType, batchId } = get();
            const jobId = jobIds[index];
            const outcome = await runOneStep(opType as BulkJobsOp, jobId, batchId);
            set((s) => ({
              index: s.index + 1,
              successCount: outcome === "success" ? s.successCount + 1 : s.successCount,
              skippedCount: outcome === "skipped" ? s.skippedCount + 1 : s.skippedCount,
              failures: outcome === "failed" ? [...s.failures, jobTitleFor(jobId)] : s.failures,
            }));
          }
          const { opType, successCount, skippedCount, failures, stopRequested } = get();
          const push = useToastStore.getState().push;
          const prefix = stopRequested ? "Stopped — " : "";
          if (opType === "match") {
            push(
              `${prefix}Matched ${successCount} job(s)` + (failures.length ? `. Failed: ${failures.join(", ")}` : ""),
              failures.length ? "error" : "success",
            );
          } else {
            push(
              `${prefix}Checked matched candidates for ${successCount} job(s)` +
                (skippedCount ? `, skipped ${skippedCount} with no matches yet` : "") +
                (failures.length ? `. Failed: ${failures.join(", ")}` : ""),
              failures.length ? "error" : "success",
            );
          }
        } finally {
          set({
            running: false,
            opType: null,
            jobIds: [],
            index: 0,
            successCount: 0,
            skippedCount: 0,
            failures: [],
            batchId: null,
            stopRequested: false,
          });
        }
      }

      return {
        opType: null,
        jobIds: [],
        index: 0,
        running: false,
        successCount: 0,
        skippedCount: 0,
        failures: [],
        batchId: null,
        stopRequested: false,
        start: async (op, jobIds) => {
          if (jobIds.length === 0 || get().running) return;
          set({
            opType: op,
            jobIds,
            index: 0,
            successCount: 0,
            skippedCount: 0,
            failures: [],
            // Only worth grouping when there's actually more than one run —
            // a single-job "bulk" action behaves identically to clicking
            // that job's own button, so it stays its own ungrouped entry.
            batchId: jobIds.length > 1 ? crypto.randomUUID() : null,
          });
          await loop();
        },
        resumeIfAny: async () => {
          const { opType, jobIds, index, running } = get();
          if (!opType || running || index >= jobIds.length) return;
          await loop();
        },
        stop: async () => {
          const { opType, jobIds, index, running } = get();
          if (!running) return;
          set({ stopRequested: true });
          // Also cancel the step actually in flight right now — otherwise
          // "stop" only means "don't queue more," and the current job would
          // keep running server-side to completion regardless.
          const jobId = jobIds[index];
          const matchesStore = useMatchesStore.getState();
          if (opType === "match" && matchesStore.activeRunForJobId === jobId) {
            await matchesStore.cancelRunMatching();
          } else if (opType === "update_matched" && matchesStore.activeRescanForJobId === jobId) {
            await matchesStore.cancelRescanMatched();
          }
        },
      };
    },
    {
      name: "recruit-assistant-bulk-jobs-store",
      partialize: (s) => ({
        opType: s.opType,
        jobIds: s.jobIds,
        index: s.index,
        successCount: s.successCount,
        skippedCount: s.skippedCount,
        failures: s.failures,
        batchId: s.batchId,
      }),
    },
  ),
);
