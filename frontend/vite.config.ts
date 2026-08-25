import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev mode proxies /api/* and /health straight to the backend on :8000 —
// no nginx needed locally, matching the Prodigon dev-mode convention.
// VITE_BACKEND_PORT overrides the target (e.g. running a second isolated
// backend instance for verification without touching the primary one).
const backendPort = process.env.VITE_BACKEND_PORT || "8000";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": `http://localhost:${backendPort}`,
      "/health": `http://localhost:${backendPort}`,
    },
  },
});
