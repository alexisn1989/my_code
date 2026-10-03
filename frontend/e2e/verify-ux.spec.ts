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

import { expect, test, type Page } from "@playwright/test";

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
