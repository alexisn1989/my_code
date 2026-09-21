/**
 * The stress pass (plan §9.3) — overflow and truncation under the WORST CONTENT THE ENGINE ALLOWS.
 *
 * Still the real server and the real projections: this spawns a SECOND `mandate-gui` on its own
 * port with an assembled scenario root, so nothing here is a mocked `fetch` and every layout claim
 * is a claim about the application. What is synthetic is only the CONTENT — display names stretched
 * to exactly 64 characters, `StrictDisplayName`'s documented maximum.
 *
 * A second server rather than a fourth scenario card on the main one: the main sweep must run
 * against shipped content exactly as a player sees it, and adding a joke scenario to its list would
 * have changed what that sweep was measuring.
 *
 * Every finding here is tagged `stress-fixture`. None of them is a finding about shipped content.
 */

import { execFileSync, spawn, type ChildProcess } from "node:child_process";
import { copyFileSync, mkdirSync, mkdtempSync, readdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { expect, test } from "@playwright/test";

const REVIEW_DIR = path.join(process.cwd(), "..", "docs", "reviews");
const SHOT_DIR = path.join(REVIEW_DIR, "gate-4a3-baseline");

function freePort(): number {
  const script =
    "const s=require('node:net').createServer();" +
    "s.listen(0,'127.0.0.1',()=>{const a=s.address();" +
    "process.stdout.write(String(typeof a==='object'&&a?a.port:0));s.close();});";
  return Number(execFileSync(process.execPath, ["-e", script], { encoding: "utf-8" }).trim());
}

let server: ChildProcess | null = null;
const stressFindings: { id: string; screen: string; viewport: string; source: string; kind: string; detail: string }[] = [];
const stressCoverage: string[] = [];

test.afterAll(() => {
  server?.kill("SIGINT");
});

test("stress: maximum-length display names, against the real server", async ({ page }) => {
  test.setTimeout(240_000);

  // An assembled scenario root: the stress fixture ALONE, so the Title screen offers exactly it and
  // the run cannot accidentally start a shipped scenario and report its layout as stressed.
  const root = mkdtempSync(path.join(tmpdir(), "mandate-stress-"));
  copyFileSync(
    path.join(process.cwd(), "e2e", "fixtures", "stress_long_names.yaml"),
    path.join(root, "stress_long_names.yaml"),
  );

  const port = freePort();
  server = spawn(
    "uv",
    [
      "run",
      "mandate-gui",
      "--port", String(port),
      "--frontend-dist", path.join(process.cwd(), "dist"),
      "--scenario-root", root,
      "--save-root", path.join(root, "saves"),
    ],
    { cwd: path.join(process.cwd(), "..", "backend"), stdio: "ignore" },
  );

  const base = `http://127.0.0.1:${port}`;
  for (let i = 0; i < 60; i += 1) {
    const ok = await page.request.get(`${base}/api/scenarios`).then((r) => r.ok()).catch(() => false);
    if (ok) break;
    await page.waitForTimeout(500);
  }

  await page.goto(`${base}/`);
  const start = page.getByRole("button", { name: /^Start / }).first();
  await start.waitFor({ state: "visible", timeout: 30_000 });
  await start.click();
  await page.waitForResponse((r) => r.url().includes("/api/game/state") && r.status() === 200, {
    timeout: 30_000,
  });
  await page.waitForTimeout(400);

  mkdirSync(SHOT_DIR, { recursive: true });

  // ANTI-VACUITY. "0 stress findings" is worthless unless the stressed content actually rendered:
  // a server that quietly served something else, or a campaign that failed to start, would also
  // produce zero. So prove a 64-character name reached the DOM before believing any result below.
  const longestRendered = await page.evaluate(() => {
    let longest = 0;
    for (const el of Array.from(document.querySelectorAll("main *, header *"))) {
      for (const node of Array.from(el.childNodes)) {
        if (node.nodeType === Node.TEXT_NODE) {
          longest = Math.max(longest, (node.textContent ?? "").trim().length);
        }
      }
    }
    return longest;
  });
  expect(
    longestRendered,
    "the stress fixture's 64-character names did not reach the DOM, so any result here would be vacuous",
  ).toBeGreaterThanOrEqual(60);
  stressCoverage.push(
    `longest rendered text node was ${longestRendered} characters, so the 64-character names really rendered`,
  );

  let n = 0;
  for (const viewport of [
    { name: "stress-laptop-1440x900", width: 1440, height: 900 },
    { name: "stress-mobile-390x844", width: 390, height: 844 },
  ]) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    for (const screen of ["Dashboard", "Government", "Relationships", "Decisions"]) {
      const control = page.getByRole("button", { name: screen, exact: true }).first();
      if (!(await control.isVisible().catch(() => false))) continue;
      if (await control.isDisabled().catch(() => true)) continue;
      await control.click();
      await page.waitForTimeout(300);
      await page.screenshot({ path: path.join(SHOT_DIR, `${viewport.name}__${screen}.png`) });

      const scrolls = await page.evaluate(
        () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 2,
      );
      if (scrolls) {
        n += 1;
        stressFindings.push({
          id: `S${n}`, screen, viewport: viewport.name, source: "stress-fixture",
          kind: "horizontal-scroll", detail: "the page scrolls horizontally at 64-character names",
        });
      }
      const clipped = await page.evaluate(() => {
        const out: string[] = [];
        for (const el of Array.from(document.querySelectorAll("main *"))) {
          const node = el as HTMLElement;
          if (node.scrollWidth > node.clientWidth + 2 && node.clientWidth > 0) {
            const style = getComputedStyle(node);
            if (style.overflow === "visible" || style.overflow === "") {
              out.push(`${node.tagName.toLowerCase()}.${node.className.toString().slice(0, 40)}`);
            }
          }
        }
        return out.slice(0, 6);
      });
      for (const node of clipped) {
        n += 1;
        stressFindings.push({
          id: `S${n}`, screen, viewport: viewport.name, source: "stress-fixture",
          kind: "overflow", detail: `content wider than its box: ${node}`,
        });
      }
    }
  }

  writeFileSync(
    path.join(REVIEW_DIR, "gate-4a3-stress.json"),
    JSON.stringify({ stressFindings, stressCoverage }, null, 2) + "\n",
    "utf-8",
  );

  // Coverage, not quality (§9.1): the pass ran and wrote its artifact.
  expect(readdirSync(SHOT_DIR).some((f) => f.startsWith("stress-"))).toBe(true);
});
