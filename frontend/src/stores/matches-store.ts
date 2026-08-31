import { create } from "zustand";
import { persist } from "zustand/middleware";
import { api } from "../lib/api";
import { useToastStore } from "./toast-store";
import { useDataModeStore } from "./data-mode-store";
import type { Match, ScanResult } from "../lib/types";

const POLL_INTERVAL_MS = 1500;

interface MatchesState {
  matches: Match[];
  topN: number;
  loading: boolean;
  lastElapsedSeconds: number | null;
  lastLoadWasFullRun: boolean;
  // "Check for updates" on Match Results — bounded to this job's already-
  // matched candidates (see backend routes/match_rescan.py). jobId is
  // tracked alongside the job so a refresh can tell whether the persisted
  // activeRescanJobId still belongs to whatever job is now selected.
  rescanningMatched: boolean;
  rescanMatchedProgress: ScanResult | null;
  activeRescanJobId: string | null;
  activeRescanForJobId: string | null;
  setTopN: (n: number) => void;
  loadMatches: (jobId: string) => Promise<void>;
  runMatching: (jobId: string) => Promise<Match[]>;
  flag: (matchId: string, color: "green" | "red", note: string) => Promise<void>;
  rescanMatched: (jobId: string) => Promise<void>;
  resumeRescanIfAny: () => Promise<void>;
}

// Persisted (matches + topN) so a page refresh on Match Results shows
// the same results you were just looking at instead of an empty page —
// results-page.tsx no longer auto-fetches on job/topN change (see its
// "Load results" button), so without this a refresh had nothing to
// re-populate from and the page went blank (reported as a regression).
// results-page.tsx's resultsAreStale check still catches the case where the
// persisted matches belong to a job other than whatever's now selected.
export const useMatchesStore = create<MatchesState>()(
  persist(
    (set, get) => {
      async function followRescanJob(jobId: string, jobForId: string): Promise<void> {
        set({ rescanningMatched: true, activeRescanJobId: jobId, activeRescanForJobId: jobForId, rescanMatchedProgress: null });
        try {
          while (true) {
            const job = await api.getScanJob(jobId);
            if (job.status === "completed") {
              const r = job.result;
              const push = useToastStore.getState().push;
              if (r) {
                // duplicates_skipped here means "checked, nothing new" (see
                // match_rescan.py) — deliberately worded so it reads as
                // "only these specific candidates changed", not a bulk count.
                push(
                  `Checked ${r.resumes_found} matched candidate(s) — ${r.candidates_updated} updated, ${r.duplicates_skipped} unchanged` +
                    (r.errors.length ? `, ${r.errors.length} error(s)` : ""),
                  "success",
                );
              }
              if (r && r.candidates_updated > 0) {
                get().loadMatches(jobForId).catch(() => {});
              }
              return;
            }
            if (job.status === "failed") {
              useToastStore.getState().push(job.error ?? "Rescan failed.", "error");
              return;
            }
            set({ rescanMatchedProgress: job.progress ?? null });
            await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
          }
        } finally {
          set({ rescanningMatched: false, activeRescanJobId: null, activeRescanForJobId: null, rescanMatchedProgress: null });
        }
      }

      return {
        matches: [],
        topN: 20,
        loading: false,
        lastElapsedSeconds: null,
        lastLoadWasFullRun: false,
        rescanningMatched: false,
        rescanMatchedProgress: null,
        activeRescanJobId: null,
        activeRescanForJobId: null,
        setTopN: (n) => set({ topN: n }),
        loadMatches: async (jobId) => {
          set({ loading: true });
          const result = await api.listMatches(jobId, get().topN, useDataModeStore.getState().dataMode);
          set({ matches: result.matches, loading: false, lastElapsedSeconds: result.elapsed_seconds, lastLoadWasFullRun: false });
        },
        runMatching: async (jobId) => {
          set({ loading: true });
          const result = await api.runMatching(jobId, get().topN, useDataModeStore.getState().dataMode);
          set({ matches: result.matches, loading: false, lastElapsedSeconds: result.elapsed_seconds, lastLoadWasFullRun: true });
          return result.matches;
        },
        flag: async (matchId, color, note) => {
          const updated = await api.flagMatch(matchId, color, note);
          set((s) => ({ matches: s.matches.map((m) => (m.id === matchId ? updated : m)) }));
        },
        rescanMatched: async (jobId) => {
          const job = await api.rescanMatched(jobId);
          await followRescanJob(job.id, jobId);
        },
        resumeRescanIfAny: async () => {
          const { activeRescanJobId, activeRescanForJobId, rescanningMatched } = get();
          if (!activeRescanJobId || !activeRescanForJobId || rescanningMatched) return;
          try {
            const job = await api.getScanJob(activeRescanJobId);
            if (job.status === "running") {
              await followRescanJob(activeRescanJobId, activeRescanForJobId);
            } else {
              set({ activeRescanJobId: null, activeRescanForJobId: null });
            }
          } catch {
            set({ activeRescanJobId: null, activeRescanForJobId: null });
          }
        },
      };
    },
    {
      name: "recruit-assistant-matches-store",
      partialize: (s) => ({ matches: s.matches, topN: s.topN, activeRescanJobId: s.activeRescanJobId, activeRescanForJobId: s.activeRescanForJobId }),
    },
  ),
);
