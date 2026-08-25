import { create } from "zustand";
import { api } from "../lib/api";
import type { Match } from "../lib/types";

interface MatchesState {
  matches: Match[];
  topN: number;
  loading: boolean;
  lastElapsedSeconds: number | null;
  lastLoadWasFullRun: boolean;
  setTopN: (n: number) => void;
  loadMatches: (jobId: string) => Promise<void>;
  runMatching: (jobId: string) => Promise<Match[]>;
  flag: (matchId: string, color: "green" | "red", note: string) => Promise<void>;
}

export const useMatchesStore = create<MatchesState>((set, get) => ({
  matches: [],
  topN: 20,
  loading: false,
  lastElapsedSeconds: null,
  lastLoadWasFullRun: false,
  setTopN: (n) => set({ topN: n }),
  loadMatches: async (jobId) => {
    set({ loading: true });
    const result = await api.listMatches(jobId, get().topN);
    set({ matches: result.matches, loading: false, lastElapsedSeconds: result.elapsed_seconds, lastLoadWasFullRun: false });
  },
  runMatching: async (jobId) => {
    set({ loading: true });
    const result = await api.runMatching(jobId, get().topN);
    set({ matches: result.matches, loading: false, lastElapsedSeconds: result.elapsed_seconds, lastLoadWasFullRun: true });
    return result.matches;
  },
  flag: async (matchId, color, note) => {
    const updated = await api.flagMatch(matchId, color, note);
    set((s) => ({ matches: s.matches.map((m) => (m.id === matchId ? updated : m)) }));
  },
}));
