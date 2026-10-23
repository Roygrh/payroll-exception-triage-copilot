/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The API has no path prefix (/queue, /cases/..., ADR-018). In development the UI calls /api/...
// and the dev server forwards it to the local API without the prefix, so the API needs no CORS
// change (ADR-013, ADR-020).
const API_TARGET = process.env.PTC_API_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": {
        target: API_TARGET,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
        // A return or escalate decision waits for one LLM call (ADR-018): allow two minutes.
        timeout: 120_000,
        proxyTimeout: 120_000,
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
