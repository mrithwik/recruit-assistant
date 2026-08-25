import { create } from "zustand";

interface SettingsState {
  theme: "light" | "dark";
  toggleTheme: () => void;
}

const stored = (typeof localStorage !== "undefined" && localStorage.getItem("theme")) as "light" | "dark" | null;

export const useSettingsStore = create<SettingsState>((set, get) => ({
  theme: stored ?? "light",
  toggleTheme: () => {
    const next = get().theme === "light" ? "dark" : "light";
    localStorage.setItem("theme", next);
    document.documentElement.classList.toggle("dark", next === "dark");
    set({ theme: next });
  },
}));
