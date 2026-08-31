import { create } from "zustand";

interface ToastAction {
  label: string;
  onClick: () => void;
}

interface Toast {
  id: string;
  message: string;
  variant: "info" | "success" | "error";
  action?: ToastAction;
}

interface PushOptions {
  action?: ToastAction;
  durationMs?: number;
}

interface ToastState {
  toasts: Toast[];
  push: (message: string, variant?: Toast["variant"], options?: PushOptions) => void;
  dismiss: (id: string) => void;
}

// Default duration is short (informational). A toast carrying an action —
// currently only "Undo" on job deletion — gets longer on-screen time by
// default (see DEFAULT_ACTION_DURATION_MS below), since reading the action
// and deciding to click it takes longer than just reading the message.
const DEFAULT_DURATION_MS = 4000;
const DEFAULT_ACTION_DURATION_MS = 8000;

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],
  push: (message, variant = "info", options) => {
    const id = crypto.randomUUID();
    set((s) => ({ toasts: [...s.toasts, { id, message, variant, action: options?.action }] }));
    const duration = options?.durationMs ?? (options?.action ? DEFAULT_ACTION_DURATION_MS : DEFAULT_DURATION_MS);
    setTimeout(() => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })), duration);
  },
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));
