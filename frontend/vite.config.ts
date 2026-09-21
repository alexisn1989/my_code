/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    // Vitest owns `src/` ONLY. The Gate 4A3 browser harness lives in `e2e/` and is run by
    // Playwright, which brings its own `test`/`expect`: left unexcluded, Vitest collects those
    // specs, fails to resolve `@playwright/test`'s runner, and reports failing test FILES beside a
    // green test count -- which is how this was caught.
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    exclude: ["e2e/**", "node_modules/**", "dist/**", "tools/openapi-gen/**"],
  },
});
