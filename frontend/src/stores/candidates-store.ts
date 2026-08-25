import { create } from "zustand";
import { api } from "../lib/api";
import type { Candidate } from "../lib/types";

const PAGE_SIZE = 50;

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
  fetchCandidates: () => Promise<void>;
  setFilters: (filters: { dateStart?: string; dateEnd?: string; source?: string }) => void;
  setQuery: (query: string) => void;
  setSort: (sort: string) => void;
  setPage: (page: number) => void;
}

// Search/sort/pagination all happen server-side (see /candidates route) —
// this store's job is just tracking the current filter state and re-fetching
// when it changes, not filtering an already-loaded list client-side (that
// only worked because the whole pool was loaded up front, which is exactly
// what made "All Candidates" slow at real volume).
export const useCandidatesStore = create<CandidatesState>((set, get) => ({
  candidates: [],
  total: 0,
  query: "",
  sort: "recent",
  page: 1,
  loading: false,
  lastElapsedSeconds: null,
  fetchCandidates: async () => {
    const { dateStart, dateEnd, source, query, sort, page } = get();
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
      });
      set({ candidates: result.candidates, total: result.total, lastElapsedSeconds: result.elapsed_seconds });
    } finally {
      set({ loading: false });
    }
  },
  setFilters: (filters) =>
    set({ dateStart: filters.dateStart, dateEnd: filters.dateEnd, source: filters.source, page: 1 }),
  setQuery: (query) => set({ query, page: 1 }),
  setSort: (sort) => set({ sort, page: 1 }),
  setPage: (page) => set({ page }),
}));

export const CANDIDATES_PAGE_SIZE = PAGE_SIZE;
