/**
 * Gate 4A3 (frozen-plan 4A5) — the real-browser harness.
 *
 * WHY THIS EXISTS. Every one of the 404 tests in this package runs in jsdom against a mocked
 * `fetch`. jsdom has no layout engine, no compositor and no network: it cannot tell you whether
 * text is legible, whether focus is visible, whether a panel reflows at 200%, or whether the app
 * talks to the server it was built against. The frozen plan's §9.2 puts Playwright FIRST for
 * exactly that reason — an accessibility fix list derived from jsdom would be derived from the
 * wrong renderer.
 *
 * THE BROWSER IS THE ONE ALREADY ON DISK, AND IS NEVER DOWNLOADED.
 * `PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers` is a browser CACHE ROOT, not an executable path: the
 * binary lives at `chromium-1194/chrome-linux/chrome` under it. Playwright resolves its own pinned
 * revision through that variable, which is its normal mechanism, so nothing here passes an
 * `executablePath`. `@playwright/test` is pinned EXACTLY to 1.56.0 because that release expects
 * revision 1194 (verified: `playwright-core/browsers.json` → chromium 1194, 141.0.7390.37). A
 * version expecting any other revision would try to fetch it, which
 * `PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1` blocks — surfacing as a launch failure rather than a silent
 * download. `e2e/preflight.spec.ts` proves both halves rather than trusting this comment.
 *
 * THE SERVER IS THE REAL ONE. `webServer` runs `mandate-gui`, the same production entry point an
 * operator runs, against the real built SPA and the real scenarios — so every integration claim in
 * the baseline is a claim about the application, not about a fixture. The port is allocated at
 * config load (see `pickFreePort`) rather than hard-coded, so a stale process or a parallel run
 * cannot collide with it.
 */

import { execFileSync } from "node:child_process";
import { defineConfig, devices } from "@playwright/test";

/** An OS-allocated free port, obtained by asking the kernel for one.
 *
 * Playwright loads this config SYNCHRONOUSLY and interpolates the port into `webServer.url`, so a
 * port that is only known inside a callback is no use here — `net.createServer().listen(0)` is
 * asynchronous and `address()` returns null if read immediately, which is the first thing this
 * harness got wrong. A short synchronous child process binds port 0, reads back what the kernel
 * chose, and exits; that is a real allocation rather than a guess at an unused number.
 *
 * The window between that child exiting and `mandate-gui` binding is the ordinary accept-and-retry
 * race every harness has, and `webServer.timeout` is what absorbs it. `MANDATE_E2E_PORT` overrides
 * the whole mechanism for anyone debugging against a server they started themselves.
 */
function pickFreePort(): number {
  const script =
    "const s=require('node:net').createServer();" +
    "s.listen(0,'127.0.0.1',()=>{const a=s.address();" +
    "process.stdout.write(String(typeof a==='object'&&a?a.port:0));s.close();});";
  const port = Number(execFileSync(process.execPath, ["-e", script], { encoding: "utf-8" }).trim());
  if (!Number.isInteger(port) || port <= 0) {
    throw new Error("could not allocate a free port for the baseline harness");
  }
  return port;
}

/** ONE allocation per run, propagated to the workers.
 *
 * Playwright re-imports this config in every worker process, so an unguarded `pickFreePort()` call
 * allocates a DIFFERENT port in each of them: the server binds the runner's port and the workers
 * then request the one they invented, which fails as `ECONNREFUSED` on a port nobody is listening
 * on. Writing the chosen port back into the environment makes the workers inherit the runner's
 * choice instead of repeating the draw. */
function resolvePort(): number {
  const existing = process.env.MANDATE_E2E_PORT;
  if (existing !== undefined && existing !== "") {
    return Number(existing);
  }
  const port = pickFreePort();
  process.env.MANDATE_E2E_PORT = String(port);
  return port;
}

const PORT = resolvePort();

export const BASE_URL = `http://127.0.0.1:${PORT}`;

export default defineConfig({
  testDir: "e2e",
  // One worker, because the server holds ONE process-wide `GameSession` (one save, one mutation
  // boundary). Two workers would be two browsers mutating one campaign, and every finding after
  // the first collision would be about the harness rather than the application.
  workers: 1,
  fullyParallel: false,
  reporter: [["list"]],
  timeout: 120_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: BASE_URL,
    // Headless Chromium from the cache; `channel` is deliberately unset so Playwright resolves its
    // own pinned revision rather than looking for a system Chrome.
    ...devices["Desktop Chrome"],
    screenshot: "off",
    video: "off",
    trace: "off",
  },
  // The preflight is a DEPENDENCY of the baseline, not merely a sibling: §9.2 makes it a
  // prerequisite for everything after it, so a failure to prove browser provenance stops the sweep
  // instead of producing findings nobody can attribute to a known renderer.
  projects: [
    { name: "preflight", testMatch: /preflight\.spec\.ts/ },
    { name: "baseline", testMatch: /baseline\.spec\.ts/, dependencies: ["preflight"] },
    // The stress pass runs its own server (see the spec) and is kept in the same project so
    // `npm run audit:baseline` produces the whole baseline in one command.
    { name: "stress", testMatch: /stress\.spec\.ts/, dependencies: ["preflight"] },
    // Commit 2's axe sweep. A project of its own rather than part of `baseline`, for two reasons:
    // it must be runnable without re-taking Commit 1's baseline (which would rewrite that commit's
    // committed evidence), and it depends on the same browser-provenance preflight, since an
    // accessibility finding is only attributable if the renderer that produced it is known.
    { name: "accessibility", testMatch: /accessibility\.spec\.ts/, dependencies: ["preflight"] },
  ],
  webServer: {
    // The production entry point, with explicit paths so the run cannot accidentally read a
    // different tree than the one under test.
    command: `uv run mandate-gui --port ${PORT} --frontend-dist ${process.cwd()}/dist --scenario-root ${process.cwd()}/../data/scenarios`,
    cwd: `${process.cwd()}/../backend`,
    url: `${BASE_URL}/api/scenarios`,
    reuseExistingServer: false,
    timeout: 60_000,
    stdout: "pipe",
    stderr: "pipe",
  },
});
