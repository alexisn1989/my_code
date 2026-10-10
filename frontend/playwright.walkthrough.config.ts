/**
 * Gate 4A3 victory path (V-4) — the configuration for the INSTALLED-ARCHIVE walkthrough only.
 *
 * Separate from `playwright.config.ts` on purpose: that file's `webServer` starts the repository's
 * own server for every run, and Playwright cannot switch it off per project. This one has NO
 * `webServer` and NO `baseURL`, so the walkthrough can only reach the server it is given
 * (`MANDATE_WALKTHROUGH_URL`), which must be one started from the installed release archive. There
 * is no development server to fall back to.
 */

import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "e2e",
  testMatch: /installed-walkthrough\.spec\.ts$/,
  workers: 1,
  fullyParallel: false,
  reporter: [["list"]],
  timeout: 600_000,
  expect: { timeout: 15_000 },
  use: {
    ...devices["Desktop Chrome"],
    screenshot: "off",
    video: "off",
    trace: "off",
  },
  projects: [{ name: "installed-walkthrough" }],
});
