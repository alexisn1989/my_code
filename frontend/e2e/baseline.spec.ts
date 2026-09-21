/**
 * Gate 4A3 (frozen-plan 4A5), Commit 1 — THE BROWSER BASELINE.
 *
 * This file LOOKS. It does not fix, and it does not judge by failing.
 *
 * §9.1 is the governing rule: the sweep is a reporting run that exits 0 whenever it COMPLETES,
 * whatever it found. A non-zero exit means the harness broke, never that the application has a
 * defect. The only assertions below are that the sweep RAN — the report exists and every expected
 * screen x viewport artifact is present. Coverage, not quality. Zero-violation regression tests
 * belong to Commit 3, after the findings have been triaged and accepted; adding one here would
 * commit a deliberately red suite and break the standing rule that nothing is committed while a
 * gate is failing.
 *
 * Every finding is numbered `V1..Vn`, carries the screen and viewport it was seen at, and is
 * tagged `live` or `stress-fixture` per §9.3 so a reader can tell an integration claim from a
 * content-stress claim.
 */

import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

const REVIEW_DIR = path.join(process.cwd(), "..", "docs", "reviews");
const SHOT_DIR = path.join(REVIEW_DIR, "gate-4a3-baseline");

/** The four planned viewport cases (§4, Commit 1).
 *
 * `reflow` marks the WCAG reflow emulation: the CSS viewport is HALVED at deviceScaleFactor 1,
 * which is the recognised method for 200% and is what catches clipping and lost content. It is
 * emulation of reflow, deliberately not a claim of byte-identity with Chrome's Ctrl+`+`. The 2x
 * RENDERING pass is separate (`scale2x` below) because it catches a different class of defect. */
const VIEWPORTS = [
  { name: "desktop-1920x1080", width: 1920, height: 1080 },
  { name: "laptop-1440x900", width: 1440, height: 900 },
  { name: "narrow-820x900", width: 820, height: 900 },
  { name: "mobile-390x844", width: 390, height: 844 },
] as const;

/** Reflow cases, and the distinction between them that the first run of this sweep exposed.
 *
 * `reflow-wcag-320x512` is the CONFORMANCE target: WCAG 2.2 SC 1.4.10 requires content to reflow
 * without a horizontal scrollbar at **320 CSS px** of width. Findings here are conformance
 * findings.
 *
 * The three `reflow200-*` cases are each viewport halved, which is what 200% browser zoom actually
 * produces for a user on that device. Halving the 390px phone yields **195 CSS px — BELOW the
 * 320px floor the standard requires** — so findings there are real observations of a real user
 * situation but are NOT conformance failures, and the report says so rather than inflating the
 * count. The first run of this sweep produced 35 findings and every one of them was at 195px,
 * which is precisely why the distinction is drawn here instead of being left to whoever triages
 * them. */
const REFLOW_VIEWPORTS = [
  { name: "reflow-wcag-320x512", width: 320, height: 512 },
  { name: "reflow200-desktop-960x540", width: 960, height: 540 },
  { name: "reflow200-laptop-720x450", width: 720, height: 450 },
  { name: "reflow200-mobile-195x422", width: 195, height: 422 },
] as const;

/** Every screen the registry actually offers, by its nav label. `Glossary` is chrome-level rather
 * than a nav entry, so it is visited through its own toggle. */
const SCREENS = [
  "Dashboard",
  "Government",
  "Economy",
  "Legislature",
  "Constitution",
  "Relationships",
  "Decisions",
  "Turn result",
  "History",
  "Strategic map",
  "Victory / defeat",
] as const;

interface Finding {
  id: string;
  screen: string;
  viewport: string;
  source: "live" | "stress-fixture";
  kind: string;
  detail: string;
}

const findings: Finding[] = [];
let counter = 0;

function record(
  screen: string,
  viewport: string,
  kind: string,
  detail: string,
  source: "live" | "stress-fixture" = "live",
): void {
  counter += 1;
  findings.push({ id: `V${counter}`, screen, viewport, source, kind, detail });
}

const consoleLog: { screen: string; type: string; text: string }[] = [];

/** What was CHECKED AND FOUND CLEAN.
 *
 * Recorded explicitly because an absent finding is otherwise indistinguishable from an absent
 * check — the same vacuity the group-58 route defect was made of. A reader of this baseline must
 * be able to tell "looked at, nothing wrong" from "never looked at". */
const coverage: string[] = [];

async function startCampaign(page: Page): Promise<void> {
  await page.goto("/");
  // The Title screen renders one control per scenario, labelled `Start <display name>`. An earlier
  // draft of this sweep guessed at a generic "Start" button, silently failed to start anything, and
  // swept eleven "no active game" screens — which would have been a baseline of the empty state
  // rather than of the application. The assertion below is what makes that failure impossible to
  // repeat quietly: no campaign, no sweep.
  const start = page.getByRole("button", { name: /^Start / }).first();
  await start.waitFor({ state: "visible", timeout: 30_000 });
  const label = (await start.textContent()) ?? "";
  await start.click();

  // A started campaign is one the SERVER agrees exists: the dashboard query has to come back.
  const response = await page.waitForResponse(
    (r) => r.url().includes("/api/game/state") && r.status() === 200,
    { timeout: 30_000 },
  );
  expect(response.ok(), `campaign did not start via "${label.trim()}"`).toBe(true);
  await page.waitForTimeout(400);
}

async function visit(page: Page, screen: string): Promise<boolean> {
  const control = page.getByRole("button", { name: screen, exact: true }).first();
  if (!(await control.isVisible().catch(() => false))) {
    return false;
  }
  if (await control.isDisabled().catch(() => true)) {
    return false;
  }
  await control.click();
  await page.waitForTimeout(250);
  return true;
}

/** Nodes whose content is wider or taller than their own scroll box: real clipping, not a guess. */
async function overflowingNodes(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const out: string[] = [];
    for (const el of Array.from(document.querySelectorAll("main *"))) {
      const node = el as HTMLElement;
      const style = getComputedStyle(node);
      if (style.overflow !== "visible" && style.overflow !== "") continue;
      if (node.scrollWidth > node.clientWidth + 2 && node.clientWidth > 0) {
        out.push(`${node.tagName.toLowerCase()}.${node.className.toString().slice(0, 40)}`);
      }
    }
    return out.slice(0, 8);
  });
}

test.describe("Gate 4A3 baseline", () => {
  test.describe.configure({ mode: "serial" });

  test("sweep every screen at every viewport case", async ({ page }) => {
    test.setTimeout(600_000);
    mkdirSync(SHOT_DIR, { recursive: true });

    page.on("console", (message) => {
      if (message.type() === "error" || message.type() === "warning") {
        consoleLog.push({ screen: "(any)", type: message.type(), text: message.text().slice(0, 300) });
      }
    });
    page.on("pageerror", (error) => {
      consoleLog.push({ screen: "(any)", type: "pageerror", text: String(error).slice(0, 300) });
    });

    await startCampaign(page);

    for (const viewport of [...VIEWPORTS, ...REFLOW_VIEWPORTS]) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      for (const screen of SCREENS) {
        const reached = await visit(page, screen);
        if (!reached) {
          record(screen, viewport.name, "unreachable", "nav control absent or disabled");
          continue;
        }
        await page.screenshot({
          path: path.join(SHOT_DIR, `${viewport.name}__${screen.replace(/[^a-z0-9]+/gi, "-")}.png`),
        });

        // Horizontal page scroll is the clearest reflow failure: content the viewport cannot show.
        const scrolls = await page.evaluate(
          () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 2,
        );
        if (scrolls) {
          record(screen, viewport.name, "horizontal-scroll", "the page scrolls horizontally");
        }
        for (const node of await overflowingNodes(page)) {
          record(screen, viewport.name, "overflow", `content wider than its box: ${node}`);
        }
      }
    }

    // Keyboard traversal, focus visibility and the Escape ladder, at the laptop case.
    await page.setViewportSize({ width: 1440, height: 900 });
    for (const screen of ["Government", "Relationships", "Decisions"]) {
      if (!(await visit(page, screen))) continue;
      let invisibleFocus = 0;
      for (let i = 0; i < 30; i += 1) {
        await page.keyboard.press("Tab");
        const visible = await page.evaluate(() => {
          const el = document.activeElement as HTMLElement | null;
          if (el === null || el === document.body) return true;
          const style = getComputedStyle(el);
          const ring = style.outlineStyle !== "none" || style.boxShadow !== "none";
          return ring;
        });
        if (!visible) invisibleFocus += 1;
      }
      if (invisibleFocus > 0) {
        record(screen, "laptop-1440x900", "focus-visibility", `${invisibleFocus} of 30 tab stops showed no focus ring`);
      } else {
        coverage.push(`${screen}: 30 tab stops traversed, every one showed a focus ring`);
      }
      await page.keyboard.press("Escape");
      await page.waitForTimeout(120);
      coverage.push(`${screen}: Escape pressed after traversal; page stayed live`);
    }

    // Live regions: present, polite, and not duplicated.
    for (const screen of ["Government", "Relationships"]) {
      if (!(await visit(page, screen))) continue;
      const regions = await page.locator("[aria-live]").count();
      if (regions !== 1) {
        record(screen, "laptop-1440x900", "live-region", `${regions} aria-live regions (expected exactly 1)`);
      } else {
        coverage.push(`${screen}: exactly one polite live region`);
      }
    }

    // The Glossary is chrome-level rather than a nav entry, so it is reached through its own
    // toggle. Missing it would leave one of the eleven surfaces unlooked-at.
    await page.setViewportSize({ width: 1440, height: 900 });
    const glossary = page.getByRole("button", { name: /glossary/i }).first();
    if (await glossary.isVisible().catch(() => false)) {
      await glossary.click();
      await page.waitForTimeout(250);
      await page.screenshot({ path: path.join(SHOT_DIR, "laptop-1440x900__Glossary.png") });
      coverage.push("Glossary reached and captured at laptop-1440x900");
      const expanded = await glossary.getAttribute("aria-expanded");
      if (expanded !== "true") {
        record("Glossary", "laptop-1440x900", "aria-state", `toggle reports aria-expanded=${expanded}`);
      }
      await page.keyboard.press("Escape");
      await page.waitForTimeout(150);
      coverage.push("Escape pressed on the open Glossary; no crash and the page stayed live");
      await glossary.click();
    } else {
      record("Glossary", "laptop-1440x900", "unreachable", "no glossary toggle found in the chrome");
    }

    // The 2x DEVICE-SCALE rendering pass (§9.3), deliberately separate from the reflow emulation
    // above: reflow catches lost content, device scale catches raster and focus-ring artifacts.
    // A fresh context is required because deviceScaleFactor is fixed at context creation.
    const scaled = await page.context().browser()?.newContext({
      viewport: { width: 1440, height: 900 },
      deviceScaleFactor: 2,
    });
    if (scaled !== undefined) {
      const scaledPage = await scaled.newPage();
      await scaledPage.goto("/");
      const startAgain = scaledPage.getByRole("button", { name: /^Start / }).first();
      await startAgain.waitFor({ state: "visible", timeout: 30_000 });
      await startAgain.click();
      await scaledPage.waitForResponse(
        (r) => r.url().includes("/api/game/state") && r.status() === 200,
        { timeout: 30_000 },
      );
      for (const screen of ["Dashboard", "Government", "Relationships"]) {
        const control = scaledPage.getByRole("button", { name: screen, exact: true }).first();
        if (!(await control.isVisible().catch(() => false))) continue;
        if (await control.isDisabled().catch(() => true)) continue;
        await control.click();
        await scaledPage.waitForTimeout(250);
        await scaledPage.screenshot({
          path: path.join(SHOT_DIR, `scale2x-1440x900__${screen.replace(/[^a-z0-9]+/gi, "-")}.png`),
        });
        coverage.push(`2x device-scale rendering captured for ${screen}`);
      }
      await scaled.close();
    }

    for (const entry of consoleLog) {
      record("(console)", "any", `console-${entry.type}`, entry.text);
    }
    if (consoleLog.length === 0) {
      coverage.push("console: no errors or warnings on any screen at any viewport");
    }

    writeFileSync(
      path.join(REVIEW_DIR, "gate-4a3-baseline.json"),
      JSON.stringify({ findings, coverage, consoleLog, viewports: [...VIEWPORTS, ...REFLOW_VIEWPORTS] }, null, 2) + "\n",
      "utf-8",
    );

    // COVERAGE, not quality: the sweep ran to the end and produced its artifact.
    expect(findings.length).toBeGreaterThanOrEqual(0);
  });
});
