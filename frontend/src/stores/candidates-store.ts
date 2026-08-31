import { create } from "zustand";
import { persist } from "zustand/middleware";
import { api } from "../lib/api";
import { useToastStore } from "./toast-store";
import { useDataModeStore } from "./data-mode-store";
import type { Candidate, CandidateFacets, ScanResult } from "../lib/types";

const PAGE_SIZE = 50;
const POLL_INTERVAL_MS = 1500;

interface CandidatesState {
  candidates: Candidate[];
  total: number;
  dateStart?: string;
  dateEnd?: string;
  source?: string;
  query: string;
  sort: string;
  page: number;
  loading: boolean;
  lastElapsedSeconds: number | null;
  // Multi-select filters — each is an "any of" match, combined with every
  // other active filter (including the ones above) as AND. See
  // storage.candidates_page()'s docstring for the exact semantics.
  skills: string[];
  employmentStatuses: string[];
  workVisaStatuses: string[];
  experienceMin?: number;
  experienceMax?: number;
  // Same definition as the Dashboard's "Needs attention" tile — a
  // candidate with at least one red-flagged match or one match missing
  // required info, across any job. A single on/off toggle rather than a
  // multi-select since a candidate either needs a look or doesn't.
  needsAttention: boolean;
  facets: CandidateFacets | null;
  facetsLoading: boolean;
  // "Rescan all for updates" — one bulk pass over every connected account +
  // known folder (see backend routes/scan.py's scan_all). activeJobId is
  // persisted so a refresh mid-run reattaches instead of losing visibility
  // into an already-running job (same pattern as scan-store's scan jobs).
  rescanningAll: boolean;
  rescanAllProgress: ScanResult | null;
  rescanAllJobId: string | null;
  // Candidate Detail's "Check for updates" — scoped to one person's own
  // sources (see routes/candidate_rescan.py). Persisted the same way, so it
  // survives navigating off the candidate's page, a refresh, or a
  // logout/login rather than resetting the moment the page unmounts.
  rescanningCandidate: boolean;
  candidateRescanProgress: ScanResult | null;
  candidateRescanJobId: string | null;
  candidateRescanForId: string | null;
  fetchCandidates: () => Promise<void>;
  fetchFacets: () => Promise<void>;
  setFilters: (filters: { dateStart?: string; dateEnd?: string; source?: string }) => void;
  setQuery: (query: string) => void;
  setSort: (sort: string) => void;
  setPage: (page: number) => void;
  toggleSkill: (skill: string) => void;
  toggleEmploymentStatus: (status: string) => void;
  toggleWorkVisaStatus: (status: string) => void;
  setExperienceRange: (min: number | undefined, max: number | undefined) => void;
  setNeedsAttention: (value: boolean) => void;
  clearAdvancedFilters: () => void;
  rescanAll: () => Promise<void>;
  resumeRescanAllIfAny: () => Promise<void>;
  rescanCandidate: (id: string) => Promise<ScanResult | null>;
  resumeCandidateRescanIfAny: (id: string) => Promise<ScanResult | null>;
  cancelRescanAll: () => Promise<void>;
  cancelCandidateRescan: () => Promise<void>;
}

function toggleIn(list: string[], value: string): string[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

// Search/sort/pagination/filtering all happen server-side (see /candidates
// route) — this store's job is just tracking the current filter state and
// re-fetching when it changes, not filtering an already-loaded list
// client-side (that only worked because the whole pool was loaded up front,
// which is exactly what made "All Candidates" slow at real volume).
export const useCandidatesStore = create<CandidatesState>()(
  persist(
    (set, get) => {
      async function followRescanAllJob(jobId: string): Promise<void> {
        set({ rescanningAll: true, rescanAllJobId: jobId, rescanAllProgress: null });
        try {
          while (true) {
            const job = await api.getScanJob(jobId);
            if (job.status === "completed") {
              const r = job.result;
              const push = useToastStore.getState().push;
              if (r) {
                push(
                  (job.cancelled ? "Rescan cancelled — kept " : "Rescan complete — ") +
                    `${r.candidates_created} new, ${r.candidates_updated} updated, ${r.duplicates_skipped} unchanged` +
                    (r.errors.length ? `, ${r.errors.length} error(s)` : ""),
                  "success",
                );
              }
              get().fetchCandidates().catch(() => {});
              return;
            }
            if (job.status === "failed") {
              useToastStore.getState().push(job.error ?? "Rescan failed.", "error");
              return;
            }
            set({ rescanAllProgress: job.progress ?? null });
            await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
          }
        } finally {
          set({ rescanningAll: false, rescanAllJobId: null, rescanAllProgress: null });
        }
      }

      async function followCandidateRescanJob(jobId: string, forId: string): Promise<ScanResult | null> {
        set({ rescanningCandidate: true, candidateRescanJobId: jobId, candidateRescanForId: forId, candidateRescanProgress: null });
        try {
          while (true) {
            const job = await api.getScanJob(jobId);
            if (job.status === "completed") {
              return job.result ?? null;
            }
            if (job.status === "failed") {
              useToastStore.getState().push(job.error ?? "Rescan failed.", "error");
              return null;
            }
            set({ candidateRescanProgress: job.progress ?? null });
            await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
          }
        } finally {
          set({ rescanningCandidate: false, candidateRescanJobId: null, candidateRescanForId: null, candidateRescanProgress: null });
        }
      }

      return {
        candidates: [],
        total: 0,
        query: "",
        sort: "recent",
        page: 1,
        loading: false,
        lastElapsedSeconds: null,
        skills: [],
        employmentStatuses: [],
        workVisaStatuses: [],
        needsAttention: false,
        facets: null,
        facetsLoading: false,
        rescanningAll: false,
        rescanAllProgress: null,
        rescanAllJobId: null,
        rescanningCandidate: false,
        candidateRescanProgress: null,
        candidateRescanJobId: null,
        candidateRescanForId: null,
        fetchCandidates: async () => {
          const {
            dateStart,
            dateEnd,
            source,
            query,
            sort,
            page,
            skills,
            employmentStatuses,
            workVisaStatuses,
            experienceMin,
            experienceMax,
            needsAttention,
          } = get();
          set({ loading: true });
          try {
            const result = await api.listCandidates({
              date_start: dateStart,
              date_end: dateEnd,
              source,
              q: query || undefined,
              sort,
              limit: PAGE_SIZE,
              offset: (page - 1) * PAGE_SIZE,
              skill: skills.length ? skills : undefined,
              employment_status: employmentStatuses.length ? employmentStatuses : undefined,
              work_visa_status: workVisaStatuses.length ? workVisaStatuses : undefined,
              experience_min: experienceMin,
              experience_max: experienceMax,
              needs_attention: needsAttention || undefined,
              data_mode: useDataModeStore.getState().dataMode,
            });
            set({ candidates: result.candidates, total: result.total, lastElapsedSeconds: result.elapsed_seconds });
          } finally {
            set({ loading: false });
          }
        },
        fetchFacets: async () => {
          set({ facetsLoading: true });
          try {
            const facets = await api.getCandidateFacets(useDataModeStore.getState().dataMode);
            set({ facets });
          } finally {
            set({ facetsLoading: false });
          }
        },
        setFilters: (filters) =>
          set({ dateStart: filters.dateStart, dateEnd: filters.dateEnd, source: filters.source, page: 1 }),
        setQuery: (query) => set({ query, page: 1 }),
        setSort: (sort) => set({ sort, page: 1 }),
        setPage: (page) => set({ page }),
        toggleSkill: (skill) => set((s) => ({ skills: toggleIn(s.skills, skill), page: 1 })),
        toggleEmploymentStatus: (status) =>
          set((s) => ({ employmentStatuses: toggleIn(s.employmentStatuses, status), page: 1 })),
        toggleWorkVisaStatus: (status) =>
          set((s) => ({ workVisaStatuses: toggleIn(s.workVisaStatuses, status), page: 1 })),
        setExperienceRange: (min, max) => set({ experienceMin: min, experienceMax: max, page: 1 }),
        setNeedsAttention: (value) => set({ needsAttention: value, page: 1 }),
        clearAdvancedFilters: () =>
          set({
            skills: [],
            employmentStatuses: [],
            workVisaStatuses: [],
            experienceMin: undefined,
            experienceMax: undefined,
            needsAttention: false,
            page: 1,
          }),
        rescanAll: async () => {
          const job = await api.scanAll();
          await followRescanAllJob(job.id);
        },
        resumeRescanAllIfAny: async () => {
          const { rescanAllJobId, rescanningAll } = get();
          if (!rescanAllJobId || rescanningAll) return;
          try {
            const job = await api.getScanJob(rescanAllJobId);
            if (job.status === "running") {
              await followRescanAllJob(rescanAllJobId);
            } else {
              set({ rescanAllJobId: null });
            }
          } catch {
            set({ rescanAllJobId: null });
          }
        },
        rescanCandidate: async (id) => {
          const job = await api.rescanCandidate(id);
          return followCandidateRescanJob(job.id, id);
        },
        resumeCandidateRescanIfAny: async (id) => {
          const { candidateRescanJobId, candidateRescanForId, rescanningCandidate } = get();
          if (!candidateRescanJobId || candidateRescanForId !== id || rescanningCandidate) return null;
          try {
            const job = await api.getScanJob(candidateRescanJobId);
            if (job.status === "running") {
              return followCandidateRescanJob(candidateRescanJobId, id);
            }
            set({ candidateRescanJobId: null, candidateRescanForId: null });
            return null;
          } catch {
            set({ candidateRescanJobId: null, candidateRescanForId: null });
            return null;
          }
        },
        cancelRescanAll: async () => {
          const { rescanAllJobId } = get();
          if (!rescanAllJobId) return;
          await api.cancelScanJob(rescanAllJobId);
        },
        cancelCandidateRescan: async () => {
          const { candidateRescanJobId } = get();
          if (!candidateRescanJobId) return;
          await api.cancelScanJob(candidateRescanJobId);
        },
      };
    },
    {
      name: "recruit-assistant-candidates-store",
      partialize: (s) => ({
        rescanAllJobId: s.rescanAllJobId,
        candidateRescanJobId: s.candidateRescanJobId,
        candidateRescanForId: s.candidateRescanForId,
      }),
    },
  ),
);

export const CANDIDATES_PAGE_SIZE = PAGE_SIZE;
