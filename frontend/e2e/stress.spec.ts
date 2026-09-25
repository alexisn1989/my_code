/**
 * The stress pass (plan §9.3) — overflow and truncation under the WORST CONTENT THE ENGINE ALLOWS.
 *
 * CORRECTED after Commit 1. That commit reported "0 stress findings" across four screens on the
 * strength of one assertion: that SOME text node of at least 60 characters had rendered. That
 * assertion was too weak to support the claim, and a read-only probe showed why — the 90-character
 * node it matched was Dashboard PROSE, not a stressed name. Measured per screen, the authored
 * 64-character names reached Relationships (7 of them) and reached NONE of Dashboard, Government or
 * Decisions. So three quarters of Commit 1's clean result was an absent check wearing the look of a
 * clean one.
 *
 * The fix is not a stronger version of the same assertion but a different shape: every screen
 * declares whether it is STRESS-APPLICABLE at all, an applicable screen must prove the exact
 * authored name reached it before any result is recorded for it, and a non-applicable screen is
 * recorded as `not-stress-applicable` WITH ITS REASON rather than as zero findings.
 *
 * Still the real server and the real projections: a second `mandate-gui` on its own port with an
 * assembled scenario root. Only the CONTENT is synthetic — display names stretched to exactly 64
 * characters, `StrictDisplayName`'s documented maximum.
 */

import { execFileSync, spawn, type ChildProcess } from "node:child_process";
import { copyFileSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { expect, test } from "@playwright/test";

const REVIEW_DIR = path.join(process.cwd(), "..", "docs", "reviews");
const SHOT_DIR = path.join(REVIEW_DIR, "gate-4a3-baseline");
const FIXTURE = path.join(process.cwd(), "e2e", "fixtures", "stress_long_names.yaml");

/**
 * Which screens this fixture can actually stress, and why the others cannot.
 *
 * Recorded as data rather than decided in prose, because "no findings" and "nothing to find" are
 * different results and Commit 1 conflated them. A screen that never renders a character name
 * cannot be stressed by stretching character names, and saying so is the honest answer — not a
 * zero.
 */
const APPLICABILITY = [
  {
    screen: "Relationships",
    applicable: true,
    reason:
      "projects party leaders and foreign counterparts by display name, so the stretched names render here",
  },
  {
    screen: "Dashboard",
    applicable: false,
    reason: "displays no character names at all; its longest text is UI prose",
  },
  {
    screen: "Decisions",
    applicable: false,
    reason: "composes proposals and capital terms; it renders no character display name",
  },
  {
    screen: "Government",
    applicable: false,
    reason:
      "would render cabinet holders, but this fixture derives from deficit_demo, which opens with BOTH posts vacant -- so there is no holder name to stretch. A seated-cabinet stress case belongs with that screen's own audit",
  },
] as const;

/** The authored 64-character names, read from the fixture so the check compares against the source
 * of truth rather than against a string retyped in a test. */
function authoredNames(): string[] {
  const yaml = readFileSync(FIXTURE, "utf-8");
  return [...yaml.matchAll(/display_name:\s*"([^"]{64})"/g)].map((m) => m[1]);
}

function freePort(): number {
  const script =
    "const s=require('node:net').createServer();" +
    "s.listen(0,'127.0.0.1',()=>{const a=s.address();" +
    "process.stdout.write(String(typeof a==='object'&&a?a.port:0));s.close();});";
  return Number(execFileSync(process.execPath, ["-e", script], { encoding: "utf-8" }).trim());
}

let server: ChildProcess | null = null;
const stressFindings: {
  id: string;
  screen: string;
  viewport: string;
  source: string;
  kind: string;
  detail: string;
}[] = [];
const stressCoverage: string[] = [];

test.afterAll(() => {
  server?.kill("SIGINT");
});

test("stress: maximum-length display names, per screen, against the real server", async ({ page }) => {
  test.setTimeout(240_000);

  const names = authoredNames();
  expect(names.length, "the fixture must carry authored 64-character names").toBeGreaterThan(0);
  expect(
    names.every((n) => n.length === 64),
    "every authored stress name must be exactly 64 characters",
  ).toBe(true);

  const root = mkdtempSync(path.join(tmpdir(), "mandate-stress-"));
  copyFileSync(FIXTURE, path.join(root, "stress_long_names.yaml"));

  const port = freePort();
  server = spawn(
    "uv",
    [
      "run", "mandate-gui",
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
  let n = 0;

  for (const entry of APPLICABILITY) {
    if (!entry.applicable) {
      stressCoverage.push(`${entry.screen}: not-stress-applicable -- ${entry.reason}`);
      continue;
    }

    for (const viewport of [
      { name: "stress-laptop-1440x900", width: 1440, height: 900 },
      { name: "stress-mobile-390x844", width: 390, height: 844 },
    ]) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      const control = page.getByRole("button", { name: entry.screen, exact: true }).first();
      expect(
        await control.isVisible().catch(() => false),
        `${entry.screen} is declared stress-applicable but its nav control is absent`,
      ).toBe(true);
      await control.click();
      await page.waitForTimeout(350);

      // THE ASSERTION COMMIT 1 LACKED: the exact authored names must be on THIS screen before any
      // result is recorded for it. Two named party leaders are used because Relationships is
      // required to project both, so a partial render cannot pass.
      const rendered = await page.locator("main").innerText();
      const present = names.filter((name) => rendered.includes(name));
      for (const who of ["Petra Almas", "Sofia Renn"]) {
        const expected = names.find((name) => name.startsWith(who));
        expect(expected, `the fixture must stretch ${who}'s name`).toBeDefined();
        expect(
          rendered.includes(expected as string),
          `${entry.screen} at ${viewport.name}: the authored 64-character name for ${who} did not render, so a stress result here would be unsupported`,
        ).toBe(true);
      }
      stressCoverage.push(
        `${entry.screen} at ${viewport.name}: ${present.length} exact authored 64-character name(s) rendered, including Petra Almas's and Sofia Renn's`,
      );

      await page.screenshot({ path: path.join(SHOT_DIR, `${viewport.name}__${entry.screen}.png`) });

      const scrolls = await page.evaluate(
        () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 2,
      );
      if (scrolls) {
        n += 1;
        stressFindings.push({
          id: `S${n}`, screen: entry.screen, viewport: viewport.name, source: "stress-fixture",
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
          id: `S${n}`, screen: entry.screen, viewport: viewport.name, source: "stress-fixture",
          kind: "overflow", detail: `content wider than its box: ${node}`,
        });
      }
    }
  }

  writeFileSync(
    path.join(REVIEW_DIR, "gate-4a3-stress.json"),
    JSON.stringify(
      { stressFindings, stressCoverage, applicability: APPLICABILITY, authoredNameCount: names.length },
      null,
      2,
    ) + "\n",
    "utf-8",
  );

  // Coverage, not quality (§9.1) -- but coverage that cannot be satisfied by declaring everything
  // inapplicable. A non-empty `stressCoverage` alone would pass on three "not-stress-applicable"
  // lines and no proof at all, which is the same shape of hole this commit exists to close.
  const applicableScreens = APPLICABILITY.filter((e) => e.applicable);
  expect(
    applicableScreens.length,
    "a stress fixture that stresses no screen proves nothing; at least one must be applicable",
  ).toBeGreaterThan(0);
  const proofs = stressCoverage.filter((line) => line.includes("exact authored"));
  expect(
    proofs.length,
    "every applicable screen must carry a rendered-name proof at every stress viewport",
  ).toBe(applicableScreens.length * 2);
});
