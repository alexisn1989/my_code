import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: __dirname,
  testMatch: /victory-routes\.spec\.ts$/,
  workers: 1,
  reporter: "line",
  use: { headless: true },
});
