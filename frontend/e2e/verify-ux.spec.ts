/**
 * Gate 4A3 UX pass — the CUMULATIVE browser verification for the four UX commits.
 *
 * Every assertion block is tagged with the commit that introduced its behaviour (`@ux1` … `@ux4`).
 * Each commit's script greps every tag up to and including its own (UX-1 runs `@ux1`; UX-2 runs
 * `@ux1|@ux2`; …), so a commit never asserts work scheduled later, and every later commit re-proves
 * the earlier ones.
 *
 * Its own server, on the REAL scenarios, with a temporary save root -- the pattern
 * `campaigns.spec.ts` established -- and Kingdom of Valdrun (`decree_state`) throughout, because it
 * is the scenario the external playtest starts on. Everything is driven through the interface; the
 * API is read only to learn what the interface should show.
 *
 * Output: `MANDATE_UX_OUT` names the artifact and is REQUIRED (no default -- a default once pointed
 * at committed evidence). It is written with `wx`, so an existing record is never overwritten.
 */

import { execFileSync, spawn, type ChildProcess } from "node:child_process";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { AxeBuilder } from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import {
  RATIO_TOLERANCE,
  TEXT_CONTRAST_MINIMUM,
  installColourProbe,
  measureTextOwners,
  offlineRatio,
  surfaceNameOf,
} from "./contrast-probe";
import { findIdentifierLeaks } from "./player-text";

const REVIEW_DIR = path.join(process.cwd(), "..", "docs", "reviews");
const SCENARIO_ROOT = path.join(process.cwd(), "..", "data", "scenarios");
const OUT_NAME = process.env.MANDATE_UX_OUT;
const SAFE_NAME = /^[a-z0-9][a-z0-9.-]*$/;

const VIEWPORTS = [
  { name: "desktop", width: 1440, height: 900 },
  { name: "mobile", width: 390, height: 844 },
  { name: "narrow", width: 320, height: 800 },
] as const;

function freePort(): number {
  const script =
    "const s=require('node:net').createServer();" +
    "s.listen(0,'127.0.0.1',()=>{const a=s.address();" +
    "process.stdout.write(String(typeof a==='object'&&a?a.port:0));s.close();});";
  return Number(execFileSync(process.execPath, ["-e", script], { encoding: "utf-8" }).trim());
}

let server: ChildProcess | null = null;
let base = "";
const results: Record<string, unknown>[] = [];

test.describe.configure({ mode: "serial" });

test.beforeAll(() => {
  if (OUT_NAME === undefined || !SAFE_NAME.test(OUT_NAME) || OUT_NAME.includes("..")) {
    throw new Error("MANDATE_UX_OUT is required and must be a safe artifact name");
  }
});

test.afterAll(() => {
  server?.kill("SIGINT");
  if (OUT_NAME === undefined) return;
  mkdirSync(REVIEW_DIR, { recursive: true });
  writeFileSync(
    path.join(REVIEW_DIR, `${OUT_NAME}.json`),
    `${JSON.stringify({ gate: "4A3 UX", out: OUT_NAME, results }, null, 2)}\n`,
    { flag: "wx" },
  );
});

async function ensureServer(page: Page): Promise<void> {
  if (server !== null) return;
  const saveRoot = mkdtempSync(path.join(tmpdir(), "mandate-ux-"));
  const port = freePort();
  server = spawn(
    "uv",
    [
      "run", "mandate-gui",
      "--port", String(port),
      "--frontend-dist", path.join(process.cwd(), "dist"),
      "--scenario-root", SCENARIO_ROOT,
      "--save-root", path.join(saveRoot, "saves"),
    ],
    { cwd: path.join(process.cwd(), "..", "backend"), stdio: "ignore" },
  );
  base = `http://127.0.0.1:${port}`;
  for (let i = 0; i < 60; i += 1) {
    const ok = await page.request
      .get(`${base}/api/scenarios`)
      .then((r) => r.ok())
      .catch(() => false);
    if (ok) return;
    await page.waitForTimeout(500);
  }
  throw new Error("the UX server never became ready");
}

async function startValdrun(page: Page): Promise<void> {
  await page.goto(`${base}/`);
  const start = page.getByRole("button", { name: "Start Kingdom of Valdrun" });
  await start.waitFor({ state: "visible", timeout: 30_000 });
  const pending = page.waitForResponse(
    (r) => r.url().includes("/api/game/new") && r.request().method() === "POST",
    { timeout: 60_000 },
  );
  await start.click();
  expect((await pending).status()).toBe(200);
  await page.getByRole("navigation", { name: "Screens" }).waitFor();
}

async function visit(page: Page, name: string): Promise<void> {
  const entry = page.getByRole("navigation", { name: "Screens" }).getByRole("button", { name, exact: true });
  await entry.click();
  await expect(entry).toHaveAttribute("aria-current", "page");
}

async function selectCard(page: Page, title: string): Promise<void> {
  await page.getByRole("group", { name: title }).getByRole("button", { name: "Select" }).click();
}

async function preview(page: Page): Promise<Record<string, any>> {
  const pending = page.waitForResponse(
    (r) => r.url().includes("/api/game/preview") && r.request().method() === "POST",
    { timeout: 60_000 },
  );
  await page.getByRole("button", { name: "Preview", exact: true }).click();
  const response = await pending;
  expect(response.status()).toBe(200);
  await page.getByTestId("consequences-panel").waitFor({ state: "visible" });
  return (await response.json()) as Record<string, any>;
}

for (const viewport of VIEWPORTS) {
  test(`@ux1 route visible, preview route-aware and actionable — ${viewport.name}`, async ({ page }) => {
    test.setTimeout(240_000);
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await ensureServer(page);
    await startValdrun(page);
    const options = await (await page.request.get(`${base}/api/game/decision-options`)).json();
    await visit(page, "Decisions");

    await selectCard(page, "Raise the personal income tax");
    const routeGroups = page.getByRole("radiogroup", { name: "Route" });
    await expect(routeGroups, "one route control").toHaveCount(1);
    await expect(routeGroups).toBeVisible();
    const insideDetails = await routeGroups.evaluate((el) => el.closest("details") !== null);
    expect(insideDetails, "the route is not hidden inside Customize").toBe(false);
    const decreeRadio = routeGroups.getByRole("radio", { name: /^Decree/ });
    await expect(decreeRadio).toBeEnabled();
    await expect(decreeRadio).toContainText(String(options.decree_legislative_capital_cost));

    // Legislative: the estimate fails in Valdrun, and the advice names each failing chamber.
    const legislative = await preview(page);
    const focusedId = await page.evaluate(() => document.activeElement?.id ?? null);
    expect(focusedId, "focus lands on the estimate").toBe("preview-result-heading");
    expect(legislative.would_pass).toBe(false);
    const failing = (legislative.chambers as any[]).filter((c) => !c.carries);
    const advice = page.getByTestId("failing-vote-advice");
    await expect(advice.locator("li")).toHaveCount(failing.length);
    for (const chamber of failing) {
      await expect(advice).toContainText(
        `short of ${chamber.required_seats}.`,
      );
    }
    await expect(advice).toContainText(
      `or switch the route to decree (cost ${options.decree_legislative_capital_cost}).`,
    );
    const panelText = await page.getByTestId("consequences-panel").innerText();
    expect(panelText).not.toMatch(/\blower\b|\blegislative\b/);

    // Decree: no vote, and pre-resolution wording.
    await decreeRadio.click();
    const decree = await preview(page);
    expect(decree.chambers).toEqual([]);
    expect(decree.would_pass).toBe(true);
    await expect(page.getByTestId("decree-preview")).toContainText(
      "If resolved now: enacted by decree — the legislature is bypassed.",
    );
    await expect(page.getByTestId("consequences-panel").getByRole("table")).toHaveCount(0);

    // An amendment in Valdrun (a legislature sits) is never offered a decree.
    const summary = page.locator("summary", { hasText: "Customize policy" });
    if ((await summary.locator("xpath=..").getAttribute("open")) === null) await summary.click();
    await page
      .getByRole("radiogroup", { name: "Policy proposal" })
      .getByRole("radio", { name: "Constitutional amendment" })
      .click();
    await expect(page.getByRole("radiogroup", { name: "Route" }).getByRole("radio", { name: /^Decree/ })).toBeDisabled();

    let headline: string | null = null;
    if (viewport.name === "desktop") {
      // Resolve the decree and confirm the turn result reports what the preview said.
      await page
        .getByRole("radiogroup", { name: "Policy proposal" })
        .getByRole("radio", { name: "Budget" })
        .click();
      await selectCard(page, "Raise the personal income tax");
      await page.getByRole("radiogroup", { name: "Route" }).getByRole("radio", { name: /^Decree/ }).click();
      await page.getByRole("button", { name: "Resolve turn" }).click();
      const pending = page.waitForResponse(
        (r) => r.url().includes("/api/game/resolve") && r.request().method() === "POST",
        { timeout: 120_000 },
      );
      await page.getByRole("button", { name: "Confirm and resolve" }).click();
      const resolved = await pending;
      expect(resolved.status()).toBe(200);
      headline = ((await resolved.json()) as any).turnResult.outcome_headline as string;
      expect(headline.toLowerCase()).toContain("enacted by decree");
    }

    results.push({
      block: "ux1",
      viewport: viewport.name,
      legislative: { would_pass: legislative.would_pass, failingChambers: failing.length },
      decree: { chambers: decree.chambers.length, would_pass: decree.would_pass, affordable: decree.affordable },
      focusAfterPreview: focusedId,
      resolvedHeadline: headline,
    });
  });
}

async function driversText(page: Page): Promise<string> {
  const heading = page.getByRole("heading", { name: "Why this happened" });
  await heading.waitFor({ state: "visible", timeout: 15_000 });
  return heading.locator("xpath=ancestor::section[1]").innerText();
}

/** Opens the Trace and follows one reason link with the KEYBOARD only: Enter on the toggle, Tab
 * until the link for `reasonId` has focus, then Enter. Returns the focused element afterwards. */
async function followReasonByKeyboard(page: Page, reasonId: string): Promise<{ tag: string; reason: string | null; text: string }> {
  const view = page.getByTestId("turn-result-view");
  const toggle = view.getByRole("button", { name: "Show exact values" });
  await toggle.focus();
  await page.keyboard.press("Enter");
  await expect(view.getByRole("button", { name: "Hide exact values" })).toBeFocused();
  let reached = false;
  for (let i = 0; i < 60 && !reached; i += 1) {
    await page.keyboard.press("Tab");
    reached = await page.evaluate(
      (id) => document.activeElement?.tagName === "A" && document.activeElement.textContent === id,
      reasonId,
    );
  }
  expect(reached, `Tab reaches the Trace link for ${reasonId}`).toBe(true);
  await page.keyboard.press("Enter");
  await expect.poll(() => page.evaluate(() => document.activeElement?.tagName)).toBe("LI");
  return page.evaluate(() => {
    const el = document.activeElement as HTMLElement;
    return { tag: el.tagName, reason: el.getAttribute("data-reason-id"), text: el.innerText };
  });
}

/** axe over the turn result with its NEW UX-2 parts on screen: Routine steps open and the Trace's
 * "Reasons recorded" links rendered. The accessibility baseline audits Turn result only before any
 * turn is resolved -- its empty state -- so without this no gate would evaluate these elements. */
async function axeOpenTurnResult(page: Page): Promise<{ violations: string[]; passes: number }> {
  const view = page.getByTestId("turn-result-view");
  await expect(view.getByTestId("drivers-routine")).toHaveAttribute("open", "");
  await expect(view.getByTestId("trace-reasons").getByRole("link").first()).toBeVisible();
  const results = await new AxeBuilder({ page }).include('[data-testid="turn-result-view"]').analyze();
  return {
    violations: results.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`),
    passes: results.passes.length,
  };
}

async function closeTrace(page: Page): Promise<void> {
  await page.getByTestId("turn-result-view").getByRole("button", { name: "Hide exact values" }).click();
}

for (const viewport of VIEWPORTS) {
  test(`@ux2 turn result: cause first, routine folded, reasons in Trace — ${viewport.name}`, async ({ page }) => {
    test.setTimeout(240_000);
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await ensureServer(page);
    await startValdrun(page);
    await visit(page, "Decisions");

    // A legislative tax rise with no capital committed: Valdrun's legislature blocks it.
    await selectCard(page, "Raise the personal income tax");
    await page.getByRole("button", { name: "Resolve turn" }).click();
    const pending = page.waitForResponse(
      (r) => r.url().includes("/api/game/resolve") && r.request().method() === "POST",
      { timeout: 120_000 },
    );
    await page.getByRole("button", { name: "Confirm and resolve" }).click();
    const resolved = await pending;
    expect(resolved.status()).toBe(200);
    const turnResult = ((await resolved.json()) as any).turnResult as {
      turn: number;
      outcome_headline: string;
      ledger: unknown[];
      drivers: { reason_id: string }[];
    };
    const view = page.getByTestId("turn-result-view");
    await expect(view).toHaveAttribute("data-context", "live");

    // U6: the headline speaks of spent capital only when capital went to the vote.
    expect(turnResult.ledger).toEqual([]);
    expect(turnResult.outcome_headline).toBe("The budget was blocked.");
    await expect(view).toContainText("The budget was blocked.");
    await expect(view).not.toContainText("Committed capital was still spent.");

    // U4: no reason id is player-visible with the Trace closed; bookkeeping is folded.
    const reasonIds = [...new Set(turnResult.drivers.map((d) => d.reason_id))];
    expect(await findIdentifierLeaks(page, reasonIds), "live: no reason id outside the Trace").toEqual([]);
    const routine = view.getByTestId("drivers-routine");
    await expect(routine).not.toHaveAttribute("open", /.*/);
    const routineCount = await routine.locator("li[data-reason-id]").count();
    expect(routineCount, "turn 1 records routine bookkeeping").toBeGreaterThan(0);
    await expect(view.getByTestId("drivers-consequential")).toContainText("The legislature blocked the budget.");
    const live = await driversText(page);

    // T2 keyboard path, live: a routine reason opens Routine steps and lands on its sentence.
    const liveFocus = await followReasonByKeyboard(page, "labor_market_resolved");
    expect(liveFocus.reason).toBe("labor_market_resolved");
    expect(liveFocus.text).toMatch(/^Labour market: [\d,]+ employed, \d+\.\d{2}% unemployment, [\d,]+ unfilled jobs\.$/);
    await expect(routine).toHaveAttribute("open", "");
    const liveAxe = await axeOpenTurnResult(page);
    expect(liveAxe.violations, "axe: live turn result, Routine steps and Trace open").toEqual([]);
    expect(liveAxe.passes, "axe evaluated rules on the live turn result").toBeGreaterThan(0);

    // History: the same turn reads the same, and the same keyboard path works.
    await visit(page, "History");
    const turnButton = page.getByRole("button", { name: new RegExp(`^Turn ${turnResult.turn} — `) });
    await turnButton.click();
    await expect(page.getByTestId("turn-result-view")).toHaveAttribute("data-context", "history");
    const history = await driversText(page);
    expect(history, "History re-renders the drivers text-for-text").toBe(live);
    expect(await findIdentifierLeaks(page, reasonIds), "history: no reason id outside the Trace").toEqual([]);
    const historyFocus = await followReasonByKeyboard(page, "labor_market_resolved");
    expect(historyFocus).toEqual(liveFocus);
    const historyAxe = await axeOpenTurnResult(page);
    expect(historyAxe.violations, "axe: History turn result, Routine steps and Trace open").toEqual([]);
    expect(historyAxe.passes, "axe evaluated rules on the History turn result").toBeGreaterThan(0);
    await closeTrace(page);

    results.push({
      block: "ux2",
      viewport: viewport.name,
      headline: turnResult.outcome_headline,
      ledgerEntries: turnResult.ledger.length,
      drivers: turnResult.drivers.length,
      routineFolded: routineCount,
      leaksOutsideTrace: 0,
      historyIdenticalToLive: history === live,
      keyboardFocus: liveFocus,
      axeOpenTurnResult: {
        live: { violations: liveAxe.violations.length, passes: liveAxe.passes },
        history: { violations: historyAxe.violations.length, passes: historyAxe.passes },
      },
    });
  });
}

const CAPITAL_DEFINITION =
  "The government's spendable political standing. It regenerates each turn up to a capacity, and is consumed whether a proposal passes or fails.";
const WIN_LINE_START = "You win by turning this into a competitive constitution";

for (const viewport of VIEWPORTS) {
  test(`@ux3 orientation, next action, no dead ends — ${viewport.name}`, async ({ page }) => {
    test.setTimeout(240_000);
    await installColourProbe(page);
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await ensureServer(page);
    await startValdrun(page);
    const dashboard = (await (await page.request.get(`${base}/api/game/state`)).json()) as {
      turn: number;
      country_name: string;
      concerns: Record<string, { label: string; headline: string; detail_screen: string }>;
    };

    // ---- U1: the stakes and the first action, where a new player first looks ----
    await visit(page, "Dashboard");
    const priority = page.getByRole("heading", { name: "Your current priority" }).locator("xpath=ancestor::section[1]");
    const winLine = priority.getByTestId("win-and-loss");
    await expect(winLine).toContainText(WIN_LINE_START);
    const build = priority.getByRole("button", { name: "Build a decision" });
    await expect(build).toBeVisible();
    let firstViewport: { winBottom: number; buttonBottom: number } | null = null;
    if (viewport.name === "desktop") {
      await page.evaluate(() => window.scrollTo(0, 0));
      const winBox = (await winLine.boundingBox())!;
      const buttonBox = (await build.boundingBox())!;
      firstViewport = { winBottom: winBox.y + winBox.height, buttonBottom: buttonBox.y + buttonBox.height };
      expect(firstViewport.winBottom, "the stakes are inside the first 1440x900 viewport").toBeLessThanOrEqual(viewport.height);
      expect(firstViewport.buttonBottom, "Build a decision is inside the first viewport").toBeLessThanOrEqual(viewport.height);
    }
    await expect(page.getByRole("complementary", { name: "How to govern" }).getByTestId("win-and-loss")).toContainText(
      WIN_LINE_START,
    );
    const meter = page.getByTestId("capital-meter");
    await expect(meter).toHaveAttribute("title", CAPITAL_DEFINITION);
    await expect(meter).toHaveAttribute("aria-description", CAPITAL_DEFINITION);

    // ---- U10: the tint draws what it claims, legibly ----
    const tint = page.getByTestId("national-tint");
    const tintBg = await tint.evaluate((el) => getComputedStyle(el).backgroundColor);
    expect(tintBg, "the tint box is filled").not.toMatch(/rgba?\(0, 0, 0, 0\)|transparent/);
    await expect(tint).toContainText(dashboard.country_name);
    const scan = await measureTextOwners(page, '[data-testid="national-tint"]');
    // Calibrate before trusting a figure: the caption is parchment-200 at 70% on the panel's navy-900.
    const calibration = scan.measured.filter((m) => m.classes.includes("text-parchment-200/70") && m.ratio > 0);
    expect(calibration.length, "a calibration node exists on the Dashboard").toBeGreaterThan(0);
    for (const node of calibration) {
      const surface = surfaceNameOf(node.bg);
      expect(surface, `calibration backdrop ${node.bg} is a palette surface`).not.toBeNull();
      const expected = offlineRatio({ foreground: "parchment-200", backdrop: surface!, alpha: 0.7 });
      expect(Math.abs(node.ratio - expected), `probe ${node.ratio} vs offline ${expected}`).toBeLessThanOrEqual(
        RATIO_TOLERANCE,
      );
    }
    // The fill is the mix, visibly distinct from the navy-950 label the name sits on.
    const labelBg = await tint.locator("span").evaluate((el) => getComputedStyle(el).backgroundColor);
    expect(tintBg, "the tint differs from the label's navy-950").not.toBe(labelBg);
    // The name has its own navy-950 label: an authored surface, as every text backdrop must be.
    const onTint = scan.measured.filter((m) => m.inRegion);
    expect(onTint.map((m) => m.text.trim())).toEqual([dashboard.country_name]);
    const countryName = onTint[0]!;
    expect(countryName.ratio, "measured, not the unmeasured sentinel").toBeGreaterThan(0);
    expect(surfaceNameOf(countryName.bg), "the name's backdrop is an authored surface").toBe("navy-950");
    expect(countryName.ratio, "country name on its label").toBeGreaterThanOrEqual(TEXT_CONTRAST_MINIMUM);
    const devCopy = await findIdentifierLeaks(page, ["placeholder", "province", "mechanics", "Stylised outline"]);
    expect(devCopy, "no developer-facing map copy").toEqual([]);

    // ---- U10: every Details link lands on its own card ----
    const landed: Record<string, string> = {};
    for (const concern of Object.values(dashboard.concerns)) {
      await visit(page, "Dashboard");
      await page.getByRole("button", { name: `Details: ${concern.label}` }).click();
      const summaries = page.getByTestId("concern-summaries");
      await expect(summaries.getByRole("heading", { name: concern.label, exact: true })).toBeVisible();
      await expect(summaries).toContainText(concern.headline);
      landed[concern.label] = concern.detail_screen;
    }
    expect(Object.keys(landed)).toHaveLength(5);
    const nav = page.getByRole("navigation", { name: "Screens" });
    await expect(nav.getByRole("list", { name: "Summaries" }).getByRole("button")).toHaveText([
      "Economy",
      "Legislature",
      "Constitution",
    ]);

    // ---- U5: after a turn, the next action is the next turn ----
    await visit(page, "Decisions");
    await selectCard(page, "Raise the personal income tax");
    await page.getByRole("button", { name: "Resolve turn" }).click();
    const pending = page.waitForResponse(
      (r) => r.url().includes("/api/game/resolve") && r.request().method() === "POST",
      { timeout: 120_000 },
    );
    await page.getByRole("button", { name: "Confirm and resolve" }).click();
    const resolved = (await (await pending).json()) as { turnResult: { turn: number } };
    const n = resolved.turnResult.turn;
    await expect(page.getByTestId("national-header")).toContainText(new RegExp(`Turn ${n}(?!\\d)`));
    await page.getByRole("button", { name: `Plan turn ${n}` }).click();
    await expect(nav.getByRole("button", { name: "Decisions", exact: true })).toHaveAttribute("aria-current", "page");
    await expect(page.getByTestId("national-header")).toContainText(new RegExp(`Turn ${n}(?!\\d)`));

    results.push({
      block: "ux3",
      viewport: viewport.name,
      firstViewport,
      capitalTooltip: CAPITAL_DEFINITION,
      tint: {
        background: tintBg,
        labelBackground: labelBg,
        countryNameBackdrop: surfaceNameOf(countryName.bg),
        countryNameRatio: countryName.ratio,
        calibrationNodes: calibration.length,
      },
      detailsLanded: landed,
      planTurn: { resultTurn: n, headerTurn: n, landedOn: "Decisions" },
    });
  });
}
