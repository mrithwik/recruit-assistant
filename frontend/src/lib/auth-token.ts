// Shared by api.ts (attaches the header) and stores/auth-store.ts (owns the
// state) — split out to avoid a circular import between the two.
const STORAGE_KEY = "recruit-assistant-token";

export function getToken(): string | null {
  return localStorage.getItem(STORAGE_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(STORAGE_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(STORAGE_KEY);
}
