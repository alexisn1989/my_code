/**
 * Gate 4A3 victory path (V-2) — a winning campaign in every shipped scenario, played through the
 * interface with each reform built from the CONSTITUTION SCREEN'S OWN LINK.
 *
 * Promoted from the victory-route audit (`docs/reviews/gate-4a3-victory-route-audit/tools/
 * victory-routes.spec.ts`), with one change in how the reform is made: the audit typed it into
 * "Customize policy"; this opens Constitution and clicks "Draft the qualifying reform". Every turn,
 * the decisions the interface sends to `/api/game/resolve` must EQUAL the audit route's recorded
 * ones (`engine-search/*.json`), so each campaign is the audited winner, now reached through the
 * links -- and it must end in victory.
 *
 * Along the way it asserts what the player sees: the objective card's stage (reform, then the
 * qualifying election, then concluded), the checklist before and after, the "If enacted" preview
 * sentence, and the result's objective line. At each of those checkpoints the Dashboard card and
 * the Constitution screen are checked for reflow (six widths), every control fully in view, axe
 * (0 violations; colour contrast decided), and keyboard activation.
 *
 * A second test covers what a winning replay cannot reach: the replacement announcement, and the
 * `cannot_qualify` stages and a withheld link, rendered in the real browser from dashboards the
 * BACKEND built for constructed states (`e2e/fixtures/objective-*.json`, pinned by
 * `backend/tests/test_objective_fixtures.py`).
 *
 * Its own server, like `campaigns`: it resolves whole campaigns.
 */

import { execFileSync, spawn, type ChildProcess } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { AxeBuilder } from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const REVIEW_DIR = path.join(process.cwd(), "..", "docs", "reviews");
const ROUTES_DIR = path.join(REVIEW_DIR, "gate-4a3-victory-route-audit", "engine-search");
const FIXTURES_DIR = path.join(process.cwd(), "e2e", "fixtures");
const SCENARIO_ROOT = path.join(process.cwd(), "..", "data", "scenarios");
const OUT_NAME = process.env.MANDATE_VICTORY_OUT ?? "gate-4a3-v2-victory";

const WIDTHS = [
  { width: 1440, height: 900 },
  { width: 960, height: 900 },
  { width: 820, height: 900 },
  { width: 720, height: 450 },
  { width: 390, height: 844 },
  { width: 320, height: 512 },
] as const;

type Decision = Record<string, any>;
type RouteTurn = { turn: number; submitted: Decision[] };

function freePort(): number {
  const script =
    "const s=require('node:net').createServer();" +
    "s.listen(0,'127.0.0.1',()=>{const a=s.address();" +
    "process.stdout.write(String(typeof a==='object'&&a?a.port:0));s.close();});";
  return Number(execFileSync(process.execPath, ["-e", script], { encoding: "utf-8" }).trim());
}

let server: ChildProcess | null = null;
let base = "";
const record: Record<string, unknown> = {};

test.describe.configure({ mode: "serial" });

test.afterAll(() => {
  server?.kill("SIGINT");
  mkdirSync(REVIEW_DIR, { recursive: true });
  writeFileSync(
    path.join(REVIEW_DIR, `${OUT_NAME}.json`),
    `${JSON.stringify({ gate: "4A3 victory path", commit: "V-2", ...record }, null, 2)}\n`,
  );
});

async function ensureServer(page: Page): Promise<void> {
  if (server !== null) return;
  const saveRoot = mkdtempSync(path.join(tmpdir(), "mandate-victory-"));
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
    const ok = await page.request.get(`${base}/api/scenarios`).then((r) => r.ok()).catch(() => false);
    if (ok) return;
    await page.waitForTimeout(500);
  }
  throw new Error("the victory server never became ready");
}

async function api<T>(page: Page, url: string): Promise<T> {
  const response = await page.request.get(`${base}${url}`);
  expect(response.status(), `GET ${url}`).toBe(200);
  return (await response.json()) as T;
}

async function visit(page: Page, name: string): Promise<void> {
  const entry = page.getByRole("navigation", { name: "Screens" }).getByRole("button", { name, exact: true });
  await entry.click();
  await expect(entry).toHaveAttribute("aria-current", "page");
}

async function startScenario(page: Page, scenarioId: string): Promise<void> {
  await page.goto(`${base}/`);
  const scenarios = await api<{ scenario_id: string; display_name: string }[]>(page, "/api/scenarios");
  const display = scenarios.find((s) => s.scenario_id === scenarioId)!.display_name;
  const created = page.waitForResponse((r) => r.url().includes("/api/game/new") && r.request().method() === "POST");
  await page.getByRole("button", { name: `Start ${display}` }).click();
  expect((await created).status()).toBe(200);
}

function canonical(decisions: Decision[]): string {
  const norm = (d: Decision): Decision => {
    const out: Decision = { ...d };
    for (const key of ["influence", "investments"]) {
      if (Array.isArray(out[key])) out[key] = [...out[key]].sort((a, b) => `${a.party_id}/${a.bloc_id}`.localeCompare(`${b.party_id}/${b.bloc_id}`));
    }
    if (Array.isArray(out.targets)) out.targets = [...out.targets].sort((a, b) => a.axis.localeCompare(b.axis));
    if (out.kind === "constitutional_amendment" && out.route === undefined) out.route = "legislative";
    return out;
  };
  return JSON.stringify([...decisions].map(norm).sort((a, b) => a.kind.localeCompare(b.kind)));
}

/** Reflow, in-view controls, axe and decided contrast for one surface, at every width. */
async function checkSurface(page: Page, selector: string, label: string, log: unknown[]): Promise<void> {
  for (const size of WIDTHS) {
    await page.setViewportSize(size);
    const overflow = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }));
    expect(overflow.scrollWidth, `${label} at ${size.width}: no page overflow`).toBeLessThanOrEqual(overflow.clientWidth);
    const controls = page.locator(`${selector} button`);
    for (let i = 0; i < (await controls.count()); i += 1) {
      const control = controls.nth(i);
      await control.scrollIntoViewIfNeeded();
      const box = await control.boundingBox();
      expect(box, `${label} at ${size.width}: control ${i} rendered`).not.toBeNull();
      expect(box!.x, `${label} at ${size.width}: control ${i} left edge in view`).toBeGreaterThanOrEqual(0);
      expect(box!.x + box!.width, `${label} at ${size.width}: control ${i} right edge in view`).toBeLessThanOrEqual(size.width);
    }
    await page.locator(selector).first().scrollIntoViewIfNeeded();
    const all = await new AxeBuilder({ page }).include(selector).analyze();
    expect(all.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`), `${label} at ${size.width}: axe`).toEqual([]);
    const contrast = await new AxeBuilder({ page }).include(selector).withRules(["color-contrast"]).analyze();
    expect(contrast.incomplete.map((v) => v.id), `${label} at ${size.width}: contrast decided`).toEqual([]);
    log.push({ surface: label, width: size.width, overflow, axePasses: all.passes.length });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
}

async function objectiveStage(page: Page): Promise<string | null> {
  await visit(page, "Dashboard");
  return page.getByTestId("objective-card").getAttribute("data-stage");
}

async function checklist(page: Page): Promise<Record<string, boolean>> {
  await visit(page, "Constitution");
  const rows = page.getByTestId("constitution-checklist").locator("li[data-condition]");
  await expect(rows).toHaveCount(3);
  const out: Record<string, boolean> = {};
  for (let i = 0; i < (await rows.count()); i += 1) {
    const row = rows.nth(i);
    out[(await row.getAttribute("data-condition"))!] = (await row.getAttribute("data-met")) === "true";
    await expect(row.getByTestId("condition-status")).toHaveText((await row.getAttribute("data-met")) === "true" ? "Met" : "Not yet");
  }
  return out;
}

const EXPECTED_START: Record<string, Record<string, boolean>> = {
  deficit_demo: { elected_executive: true, no_decree_authority: false, election_interval: true },
  tiny_valid: { elected_executive: true, no_decree_authority: false, election_interval: true },
  decree_state: { elected_executive: false, no_decree_authority: false, election_interval: false },
};
const ALL_MET = { elected_executive: true, no_decree_authority: true, election_interval: true };

for (const scenario of ["deficit_demo", "tiny_valid", "decree_state"] as const) {
  test(`a winning campaign through the Constitution links: ${scenario}`, async ({ page }) => {
    test.setTimeout(1_800_000);
    await ensureServer(page);
    const file = scenario === "decree_state" ? "search-v2-decree_state.json" : `search-${scenario}.json`;
    const route = JSON.parse(readFileSync(path.join(ROUTES_DIR, file), "utf-8")) as { turns: RouteTurn[]; outcome: any };
    expect(route.outcome?.bucket, "the audited route ends in victory").toBe("victory");
    const consoleErrors: string[] = [];
    page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(m.text()); });
    const surfaces: unknown[] = [];
    const log: Record<string, unknown>[] = [];

    await page.setViewportSize({ width: 390, height: 844 });
    await startScenario(page, scenario);
    await visit(page, "Dashboard");
    // The phone's first screen shows the objective's headline without scrolling.
    const headline = page.getByTestId("objective-card").getByTestId("objective-headline");
    await expect(headline).toBeVisible();
    const headBox = await headline.boundingBox();
    expect(headBox!.y + headBox!.height, "objective headline inside the first 390x844 screen").toBeLessThanOrEqual(844);
    await page.setViewportSize({ width: 1440, height: 900 });

    expect(await objectiveStage(page)).toBe("reform");
    await checkSurface(page, '[data-testid="objective-card"]', "Dashboard objective card (reform)", surfaces);
    expect(await checklist(page)).toEqual(EXPECTED_START[scenario]);
    await checkSurface(page, "main", "Constitution (reform)", surfaces);

    for (const turn of route.turns) {
      const options = await api<{ blocs: { party_id: string; bloc_id: string; bloc_name: string }[] }>(page, "/api/game/decision-options");
      const blocName = (p: string, b: string) => options.blocs.find((x) => x.party_id === p && x.bloc_id === b)!.bloc_name;
      const kinds = turn.submitted.map((d) => d.kind);
      const amendment = turn.submitted.find((d) => d.kind === "constitutional_amendment");
      if (amendment) {
        // THE LINK, by keyboard: focus the button and press Enter.
        await visit(page, "Constitution");
        const link = page.getByTestId("draft-qualifying-reform");
        await link.focus();
        await page.keyboard.press("Enter");
        await expect(page.getByRole("navigation", { name: "Screens" }).getByRole("button", { name: "Decisions", exact: true })).toHaveAttribute("aria-current", "page");
        const summary = page.getByTestId("policy-selection-summary");
        await expect(summary).toBeFocused();
        const objective = (await api<{ objective: { qualifying_card_id: string } }>(page, "/api/game/state")).objective;
        const cards = (await api<{ policy_cards: { card_id: string; title: string }[] }>(page, "/api/game/decision-options")).policy_cards;
        await expect(summary).toContainText(cards.find((c) => c.card_id === objective.qualifying_card_id)!.title);
      } else {
        await visit(page, "Decisions");
      }
      for (const decision of turn.submitted) {
        if (decision.kind === "bloc_relationship_investment") {
          for (const row of decision.investments) {
            await page.getByLabel(`Relationship investment for ${blocName(row.party_id, row.bloc_id)}`).fill(String(row.political_capital));
          }
        } else if (decision.kind === "constitutional_amendment") {
          for (const row of decision.influence) {
            await page.getByLabel(`Influence capital for ${blocName(row.party_id, row.bloc_id)}`).fill(String(row.political_capital));
          }
        }
      }
      const bargain = turn.submitted.find((d) => d.kind === "legislative_bargain");
      if (bargain) {
        await visit(page, "Relationships");
        await page.getByTestId("meeting-panel").locator(`[data-leader-option="${bargain.character_id}"]`).click();
        await page.getByTestId("confirm-meeting").click();
        await visit(page, "Decisions");
      }
      let previewEffect: string | null = null;
      if (amendment) {
        const previewed = page.waitForResponse((r) => r.url().includes("/api/game/preview") && r.request().method() === "POST");
        await page.getByRole("button", { name: "Preview", exact: true }).click();
        const preview = await (await previewed).json();
        expect(preview.would_pass, "the interface's own preview says the reform passes").toBe(true);
        expect(preview.objective_effect_if_enacted?.effect).toBe("qualifies");
        previewEffect = await page.getByTestId("objective-effect").innerText();
        expect(previewEffect.startsWith("If enacted,"), "the preview speaks conditionally").toBe(true);
      }
      await page.getByRole("button", { name: "Resolve turn" }).click();
      const resolved = page.waitForResponse((r) => r.url().includes("/api/game/resolve") && r.request().method() === "POST", { timeout: 120_000 });
      await page.getByRole("button", { name: "Confirm and resolve" }).click();
      const response = await resolved;
      expect(response.status()).toBe(200);
      const sent = response.request().postDataJSON() as { decisions: Decision[] };
      expect(canonical(sent.decisions), `turn ${turn.turn}: the links sent the audited decisions`).toBe(canonical(turn.submitted));
      const body = await response.json();
      const line = body.turnResult.objective_line as string | null;
      if (line !== null) {
        await expect(page.getByTestId("objective-line")).toHaveText(line);
      } else {
        await expect(page.getByTestId("objective-line")).toHaveCount(0);
      }
      log.push({ turn: turn.turn, kinds, headline: body.turnResult.outcome_headline, objectiveLine: line, previewEffect });

      if (amendment) {
        expect(line).toMatch(/^The constitution now qualifies, and the transition is recorded\. Win the election on turn \d+ to complete it\.$/);
        expect(await objectiveStage(page)).toBe("qualifying_election");
        const dashboard = await api<{ objective: { headline: string; election_turn: number } }>(page, "/api/game/state");
        await expect(page.getByTestId("objective-card").getByTestId("objective-headline")).toHaveText(dashboard.objective.headline);
        expect(dashboard.objective.headline).toBe(`Win the qualifying election: turn ${dashboard.objective.election_turn}.`);
        await expect(page.getByTestId("objective-risks")).toBeVisible();
        await checkSurface(page, '[data-testid="objective-card"]', "Dashboard objective card (qualifying election)", surfaces);
        expect(await checklist(page)).toEqual(ALL_MET);
        await expect(page.getByTestId("objective-transition-text")).toHaveText(/^Qualifying transition: recorded on turn \d+$/);
        await checkSurface(page, "main", "Constitution (qualifying election)", surfaces);
      }
      const state = await api<{ terminal: unknown }>(page, "/api/game/state");
      if (state.terminal !== null) break;
      await visit(page, "Turn result");
      const plan = page.getByRole("button", { name: /^Plan turn \d+$/ });
      if (await plan.count()) await plan.click();
    }

    const final = await api<{ terminal: { bucket: string; headline: string } | null }>(page, "/api/game/state");
    expect(final.terminal?.bucket).toBe("victory");
    expect(log[log.length - 1]!.objectiveLine).toBe("Objective complete: you won the qualifying election.");
    expect(await objectiveStage(page)).toBe("concluded");
    await expect(page.getByTestId("objective-card").getByTestId("objective-headline")).toHaveText(
      "Objective complete: the qualifying election was won.",
    );
    await checkSurface(page, '[data-testid="objective-card"]', "Dashboard objective card (concluded)", surfaces);
    await visit(page, "Victory / defeat");
    await expect(page.locator("main")).toContainText(final.terminal!.headline);
    expect(consoleErrors).toEqual([]);
    record[scenario] = { turnsPlayed: log.length, terminal: final.terminal, log, surfaces: surfaces.length, consoleErrors };
  });
}

test("a link replaces a staged proposal, and the stages a win cannot reach render and pass", async ({ page }) => {
  test.setTimeout(600_000);
  await ensureServer(page);
  const consoleErrors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(m.text()); });
  const surfaces: unknown[] = [];
  await page.setViewportSize({ width: 1440, height: 900 });
  await startScenario(page, "decree_state");

  // Replacement: stage a budget card, then follow the link. The link REPLACES it, and says so.
  await visit(page, "Decisions");
  await page.getByRole("tab", { name: /^Budget policy/ }).click();
  await page.getByRole("tabpanel").getByRole("button", { name: "Select" }).first().click();
  await visit(page, "Constitution");
  await page.getByTestId("draft-qualifying-reform").click();
  await expect(page.getByRole("alert")).toHaveText(
    "Replaced your drafted budget with: Complete the constitutional conditions in one reform.",
  );
  const staged = await page.evaluate(() => document.querySelector('[data-testid="policy-selection-summary"]')?.textContent ?? "");
  expect(staged).toContain("Complete the constitutional conditions in one reform");

  // Constructed states the backend built (fixtures), served in place of the dashboard.
  const fixtures: Record<string, { stage: string; reason: string | null }> = {
    "objective-after-decree-none": { stage: "reform", reason: null },
    "objective-cannot-qualify-missing-interval": { stage: "cannot_qualify", reason: "missing_interval" },
    "objective-cannot-qualify-already-competitive": { stage: "cannot_qualify", reason: "already_competitive" },
  };
  for (const [name, expected] of Object.entries(fixtures)) {
    const dashboard = JSON.parse(readFileSync(path.join(FIXTURES_DIR, `${name}.json`), "utf-8"));
    expect(dashboard.objective.stage).toBe(expected.stage);
    expect(dashboard.objective.cannot_qualify_reason).toBe(expected.reason);
    await page.route("**/api/game/state", (r) => r.fulfill({ json: dashboard }));
    // A fresh campaign gives a fresh revision, so the dashboard query is fetched -- from the route.
    await startScenario(page, "decree_state");
    await visit(page, "Dashboard");
    await expect(page.getByTestId("objective-card")).toHaveAttribute("data-stage", expected.stage);
    await expect(page.getByTestId("objective-card").getByTestId("objective-headline")).toHaveText(dashboard.objective.headline);
    await checkSurface(page, '[data-testid="objective-card"]', `Dashboard objective card (${name})`, surfaces);
    await visit(page, "Constitution");
    if (name === "objective-after-decree-none") {
      const executive = page.getByTestId("constitution-checklist").locator('li[data-condition="elected_executive"]');
      await expect(executive.getByRole("button")).toHaveCount(0);
      await expect(executive.getByTestId("condition-note")).toHaveText(/^Not on its own:/);
      await expect(page.getByTestId("constitution-checklist").locator('li[data-condition="election_interval"]').getByRole("button")).toHaveCount(1);
    } else {
      await expect(page.getByTestId("draft-qualifying-reform")).toHaveCount(0);
      await expect(page.getByTestId("constitution-checklist").getByRole("button")).toHaveCount(0);
    }
    await checkSurface(page, "main", `Constitution (${name})`, surfaces);
    await page.unroute("**/api/game/state");
  }
  expect(consoleErrors).toEqual([]);
  record.fixtures = { surfaces: surfaces.length, consoleErrors };
});
