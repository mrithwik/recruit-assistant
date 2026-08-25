import { create } from "zustand";
import { api } from "../lib/api";
import { clearToken, getToken, setToken } from "../lib/auth-token";
import type { AuthUser } from "../lib/types";

interface AuthState {
  user: AuthUser | null;
  status: "checking" | "authenticated" | "unauthenticated";
  setupComplete: boolean | null;
  checkAuthStatus: () => Promise<void>;
  login: (email: string, password: string, remember: boolean) => Promise<void>;
  register: (email: string, password: string, name: string, remember: boolean) => Promise<void>;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  status: "checking",
  setupComplete: null,

  checkAuthStatus: async () => {
    const { setup_complete } = await api.authStatus();
    set({ setupComplete: setup_complete });

    const token = getToken();
    if (!token) {
      set({ status: "unauthenticated" });
      return;
    }
    try {
      const user = await api.me();
      set({ user, status: "authenticated" });
    } catch {
      clearToken();
      set({ status: "unauthenticated", user: null });
    }
  },

  login: async (email, password, remember) => {
    const session = await api.login(email, password, remember);
    setToken(session.token);
    set({ user: session.user, status: "authenticated" });
  },

  register: async (email, password, name, remember) => {
    const session = await api.register(email, password, name, remember);
    setToken(session.token);
    set({ user: session.user, status: "authenticated", setupComplete: true });
  },

  logout: () => {
    clearToken();
    set({ user: null, status: "unauthenticated" });
  },
}));

window.addEventListener("auth:unauthorized", () => {
  useAuthStore.setState({ user: null, status: "unauthenticated" });
});
