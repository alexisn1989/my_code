/**
 * Gate 4A3 Commit 5b — TWO CAMPAIGNS, PLAYED ENTIRELY THROUGH THE INTERFACE.
 *
 * Every earlier browser gate reaches its state at least partly through the API, so a break between
 * the interface and a live server could pass all of them (finding F11). The frozen plan's Commit 5
 * owes two walkthroughs that close that gap, and this spec is both:
 *
 *   T21              `decree_state` at its authored seed 77: invest 85, invest 118, then the five-axis
 *                    constitutional amendment with 300 capital of influence, then empty turns to the
 *                    scheduled election, which the incumbent LOSES. Every figure asserted here is the
 *                    one `backend/tests/test_liberalization_campaign.py` pins for the same campaign
 *                    driven through the engine directly, so a disagreement is a real integration
 *                    finding, never a pin to adjust.
 *   new features     `deficit_demo`, one decision set that uses every screen the frozen plan predates:
 *                    a Government appointment, a Relationships bargain, an assistance request and a
 *                    promise, previewed on Decisions, resolved, read on Turn result and re-read on
 *                    History.
 *
 * NOTHING IS RESOLVED THROUGH THE API. Every turn goes `Resolve turn` -> `Confirm and resolve`, and the
 * API is read only to CHECK what the interface did. Every response waiter is registered before the
 * click that causes it (the race Commit 5 found at four sites). Every request the page makes in both
 * campaigns is recorded and must be same-origin.
 *
 * ITS OWN SERVER against the REAL scenario root, because it resolves turns and the shared config server
 * holds one process-wide session -- the `icon-coverage.spec.ts` pattern.
 */

import { execFileSync, spawn, type ChildProcess } from "node:child_process";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { expect, test, type Page, type Response } from "@playwright/test";

import { findIdentifierLeaks } from "./player-text";

const REVIEW_DIR = path.join(process.cwd(), "..", "docs", "reviews");
const SCENARIO_ROOT = path.join(process.cwd(), "..", "data", "scenarios");
/** One script per commit: see `_comment:commit5b` in package.json. */
const OUT_NAME = process.env.MANDATE_CAMPAIGNS_OUT ?? "gate-4a3-commit5b-campaigns";

/** Resolves allowed before T21 must have concluded. Its election is at turn 11. */
const T21_RESOLVE_CAP = 12;

/** The figures `test_liberalization_campaign.py` pins for this campaign at seed 77. */
const T21_EXPECTED = {
  seed: 77,
  capitalAfterTurn1: 798,
  capitalAfterTurn2: 1_000,
  amendmentTally: { supporting: 67, total: 100, required: 67 },
  terminal: {
    turn: 11,
    bucket: "defeat",
    reasonLabel: "Electoral defeat",
    headline: "Removed from office: electoral defeat, turn 11.",
  },
  terminalIdentifier: "electoral_defeat",
} as const;

/** The figures `test_legislative_bargain.py` and `test_cabinet_appointments.py` pin for the same
 * choices in `deficit_demo`: Bela Ronsard costs 147, Sofia Renn's price is 113, and her endorsement
 * carries the known-good budget at exactly 51 of a required 51. */
const NEW_FEATURES_EXPECTED = {
  openingCapital: 300,
  cabinetCapital: 147,
  bargainCapital: 113,
  committed: 260,
  lowerChamber: { supporting: 51, required: 51 },
  budget: { personalIncomeBps: 1225, health: 220_000_000 },
  appointment: { post: "chief_of_staff", characterId: "bela_ronsard" },
  bargainLeader: "leader_independents",
  assistanceProfile: "marnil",
  promiseKey: "leader_independents/legislative_support/budget",
  reasonIds: ["cabinet_appointed", "legislative_bargain_accepted", "foreign_assistance_granted", "promise_made"],
} as const;

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
const requestsSeen: string[] = [];

test.describe.configure({ mode: "serial" });

test.afterAll(() => {
  server?.kill("SIGINT");
  mkdirSync(REVIEW_DIR, { recursive: true });
  const offOrigin = requestsSeen.filter((url) => !url.startsWith(`${base}/`));
  writeFileSync(
    path.join(REVIEW_DIR, `${OUT_NAME}.json`),
    `${JSON.stringify(
      {
        gate: "4A3",
        commit: "5b",
        method:
          "Both campaigns are played through the interface only; the API is read to check what the " +
          "interface did and is never used to resolve a turn. Every response waiter is registered " +
          "before the click that causes it.",
        sameOrigin: {
          requests: requestsSeen.length,
          distinctPaths: [...new Set(requestsSeen.map((u) => new URL(u).pathname))].sort(),
          offOrigin,
        },
        ...record,
      },
      null,
      2,
    )}\n`,
  );
});

async function ensureServer(page: Page): Promise<void> {
  if (server !== null) return;
  const saveRoot = mkdtempSync(path.join(tmpdir(), "mandate-campaigns-"));
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
  throw new Error("the campaign server never became ready");
}

function recordRequests(page: Page): void {
  page.on("request", (request) => {
    const url = request.url();
    if (url.startsWith("data:") || url === "about:blank") return;
    requestsSeen.push(url);
  });
}

async function api<T>(page: Page, route: string): Promise<T> {
  const response = await page.request.get(`${base}${route}`);
  expect(response.ok(), `GET ${route}`).toBe(true);
  return (await response.json()) as T;
}

/** Start a scenario through the Title screen's own button, whose label is read from the API. */
async function startScenario(page: Page, scenarioId: string): Promise<void> {
  const scenarios = await api<{ scenario_id: string; display_name: string }[]>(page, "/api/scenarios");
  const scenario = scenarios.find((s) => s.scenario_id === scenarioId);
  expect(scenario, `${scenarioId} must ship`).toBeDefined();
  await page.goto(`${base}/`);
  const start = page.getByRole("button", { name: `Start ${scenario!.display_name}` });
  await start.waitFor({ state: "visible", timeout: 30_000 });
  const pending = page.waitForResponse(
    (r) => r.url().includes("/api/game/new") && r.request().method() === "POST",
    { timeout: 60_000 },
  );
  await start.click();
  expect((await pending).status(), `starting ${scenarioId}`).toBe(200);
  await page.waitForTimeout(400);
}

/** Navigate, and PROVE it: the entry must become the current page. A click that navigated nowhere is
 * how Commit 5's first run measured one screen twice. */
async function visit(page: Page, name: string): Promise<void> {
  const entry = page.getByRole("navigation", { name: "Screens" }).getByRole("button", { name, exact: true });
  await expect(entry, `${name} must be enabled`).toBeEnabled();
  await entry.click();
  await expect(entry, `${name} must become the current screen`).toHaveAttribute("aria-current", "page");
  await page.waitForTimeout(250);
}

/** Resolve the drafted turn through the interface. The confirm sentence states how many decisions
 * the interface is about to submit, so a draft that silently lost (or gained) a decision fails here. */
async function resolveThroughInterface(page: Page, expectedDecisions: number): Promise<Response> {
  await visit(page, "Decisions");
  await page.getByRole("button", { name: "Resolve turn" }).click();
  await expect(
    page.getByText(`Confirm resolving this turn with ${expectedDecisions} decision(s) committed.`),
  ).toBeVisible();
  const pending = page.waitForResponse(
    (r) => r.url().includes("/api/game/resolve") && r.request().method() === "POST",
    { timeout: 120_000 },
  );
  await page.getByRole("button", { name: "Confirm and resolve" }).click();
  const response = await pending;
  expect(response.status(), "the turn must resolve").toBe(200);
  await page.waitForTimeout(500);
  return response;
}

async function previewThroughInterface(page: Page): Promise<Record<string, any>> {
  await visit(page, "Decisions");
  const pending = page.waitForResponse(
    (r) => r.url().includes("/api/game/preview") && r.request().method() === "POST",
    { timeout: 60_000 },
  );
  await page.getByRole("button", { name: "Preview", exact: true }).click();
  const response = await pending;
  expect(response.status(), "the preview must succeed").toBe(200);
  await page.getByTestId("consequences-panel").waitFor({ state: "visible", timeout: 15_000 });
  return (await response.json()) as Record<string, any>;
}

async function openCustomize(page: Page): Promise<void> {
  const summary = page.locator("summary", { hasText: "Customize policy" });
  const details = summary.locator("xpath=..");
  if ((await details.getAttribute("open")) === null) await summary.click();
}

/** The "Why this happened" list, as a player reads it. */
async function driversText(page: Page): Promise<string> {
  const heading = page.getByRole("heading", { name: "Why this happened" });
  await heading.waitFor({ state: "visible", timeout: 15_000 });
  return heading.locator("xpath=ancestor::section[1]").innerText();
}

test.describe("Gate 4A3 Commit 5b: campaigns through the interface", () => {
  test("T21: decree_state, 85 / 118 / 300, to the lost turn-11 election", async ({ page }) => {
    test.setTimeout(900_000);
    await ensureServer(page);
    recordRequests(page);
    await startScenario(page, "decree_state");

    type Dashboard = {
      turn: number;
      political_capital: { current: number };
      terminal: { turn: number; bucket: string; reason_label: string; headline: string } | null;
    };
    const options = await api<{ blocs: { party_id: string; bloc_id: string; bloc_name: string }[] }>(
      page,
      "/api/game/decision-options",
    );
    const opposition = options.blocs.find((b) => b.party_id === "opposition_party" && b.bloc_id === "main");
    expect(opposition, "decree_state's opposition bloc must be offered").toBeDefined();
    const blocName = opposition!.bloc_name;
    const steps: string[] = [];

    // ---- turn 1: invest 85 ----
    await visit(page, "Decisions");
    await page.getByLabel(`Relationship investment for ${blocName}`).fill("85");
    await resolveThroughInterface(page, 1);
    const afterTurn1 = await api<Dashboard>(page, "/api/game/state");
    expect(afterTurn1.political_capital.current, "capital after turn 1").toBe(T21_EXPECTED.capitalAfterTurn1);
    steps.push(`turn 1: invested 85 in ${blocName}; capital ${afterTurn1.political_capital.current}`);

    // ---- turn 2: invest 118 ----
    await visit(page, "Decisions");
    await page.getByLabel(`Relationship investment for ${blocName}`).fill("118");
    await resolveThroughInterface(page, 1);
    const afterTurn2 = await api<Dashboard>(page, "/api/game/state");
    expect(afterTurn2.political_capital.current, "capital after turn 2").toBe(T21_EXPECTED.capitalAfterTurn2);
    steps.push(`turn 2: invested 118; capital ${afterTurn2.political_capital.current}`);

    // ---- turn 3: the five-axis amendment, 300 influence, through Customize policy ----
    await visit(page, "Decisions");
    await openCustomize(page);
    const amendmentRadio = page
      .getByRole("radiogroup", { name: "Policy proposal" })
      .getByRole("radio", { name: "Constitutional amendment" });
    await expect(amendmentRadio, "the slot starts empty, so one click selects it").toHaveAttribute(
      "aria-checked",
      "false",
    );
    await amendmentRadio.click();
    await expect(amendmentRadio).toHaveAttribute("aria-checked", "true");
    await page.getByRole("combobox", { name: /^Decree authority/ }).selectOption("none");
    await page.getByRole("combobox", { name: /^Executive selection/ }).selectOption("direct_election");
    await page.getByRole("combobox", { name: /^Executive system/ }).selectOption("presidential");
    await page.getByRole("spinbutton", { name: /^Executive term limit/ }).fill("2");
    await page.getByRole("spinbutton", { name: /^Election interval/ }).fill("8");
    const route = page.getByRole("radiogroup", { name: "Route" });
    await expect(route.getByRole("radio", { name: "Legislative vote" })).toHaveAttribute("aria-checked", "true");
    await page.getByLabel(`Influence capital for ${blocName}`).fill("300");

    const amendmentPreview = await previewThroughInterface(page);
    const chambers = amendmentPreview.chambers as {
      supporting_seats: number;
      total_seats: number;
      required_seats: number;
      carries: boolean;
    }[];
    expect(chambers, "decree_state's legislature is unicameral").toHaveLength(1);
    expect(
      [chambers[0]!.supporting_seats, chambers[0]!.total_seats, chambers[0]!.required_seats],
      "the amendment must tally exactly 67 of 100 against 67 required, as the engine test pins",
    ).toEqual([
      T21_EXPECTED.amendmentTally.supporting,
      T21_EXPECTED.amendmentTally.total,
      T21_EXPECTED.amendmentTally.required,
    ]);
    expect(amendmentPreview.would_pass).toBe(true);
    expect(amendmentPreview.influence_capital).toBe(300);
    await expect(page.getByTestId("consequences-panel")).toContainText("Would pass");
    steps.push("turn 3: previewed the five-axis amendment with 300 influence: 67 of 100, 67 required, would pass");
    await resolveThroughInterface(page, 1);
    steps.push("turn 3: resolved");

    // ---- turns 4 onward: empty resolves until the campaign concludes ----
    let dashboard = await api<Dashboard>(page, "/api/game/state");
    let resolves = 3;
    while (dashboard.terminal === null && resolves < T21_RESOLVE_CAP) {
      await resolveThroughInterface(page, 0);
      resolves += 1;
      dashboard = await api<Dashboard>(page, "/api/game/state");
    }
    expect(dashboard.terminal, `T21 must conclude within ${T21_RESOLVE_CAP} resolves`).not.toBeNull();
    const terminal = dashboard.terminal!;
    expect(terminal.turn).toBe(T21_EXPECTED.terminal.turn);
    expect(terminal.bucket).toBe(T21_EXPECTED.terminal.bucket);
    expect(terminal.reason_label, "T1: the AUTHORED label, never the identifier").toBe(
      T21_EXPECTED.terminal.reasonLabel,
    );
    expect(terminal.headline).toBe(T21_EXPECTED.terminal.headline);
    steps.push(`concluded after ${resolves} resolves: ${terminal.headline}`);

    /* The live result the interface navigated to says so -- ONCE. The first run of this spec found
     * two adjacent headings with this exact text (a ResultScreen Panel duplicating TurnResultView's),
     * fixed in this commit; the count is asserted so it cannot return. */
    await expect(page.getByRole("heading", { name: "This turn ended the campaign" })).toHaveCount(1);
    await expect(page.getByRole("button", { name: "Review the outcome" })).toBeVisible();

    // ---- the terminal screen, and T1 on every screen a concluded campaign changes ----
    const leaksByScreen: Record<string, unknown[]> = {};
    for (const screen of ["Victory / defeat", "Dashboard", "Decisions", "Turn result"]) {
      await visit(page, screen);
      if (screen === "Victory / defeat") {
        await expect(page.locator("main")).toContainText(`${T21_EXPECTED.terminal.reasonLabel}, turn 11`);
        await expect(page.locator("main")).toContainText(T21_EXPECTED.terminal.headline);
      }
      const leaks = await findIdentifierLeaks(page, [T21_EXPECTED.terminalIdentifier]);
      leaksByScreen[screen] = leaks;
      expect(leaks, `${screen} must not show the raw identifier ${T21_EXPECTED.terminalIdentifier}`).toEqual([]);
    }

    record.t21 = {
      scenario: "decree_state",
      seed: T21_EXPECTED.seed,
      steps,
      resolvesThroughInterface: resolves,
      terminal,
      t1LeaksByScreen: leaksByScreen,
      notDirectlyVisible:
        "The opposition bloc's relationship figures (-5,385 after turn 1, -2,774 after turn 2) are not " +
        "carried by any projection, so they are proved by what they cause: the 67-of-100 tally and the " +
        "turn-11 election.",
    };
  });

  test("new features: appoint, bargain, request aid and promise, then read it back", async ({ page }) => {
    test.setTimeout(600_000);
    await ensureServer(page);
    recordRequests(page);
    await startScenario(page, "deficit_demo");
    const expected = NEW_FEATURES_EXPECTED;
    const steps: string[] = [];

    // ---- Decisions: the known-good budget, which a bargain needs staged first ----
    await visit(page, "Decisions");
    await openCustomize(page);
    await page.getByRole("radiogroup", { name: "Policy proposal" }).getByRole("radio", { name: "Budget" }).click();
    await page.getByRole("spinbutton", { name: /^Personal income/ }).fill(String(expected.budget.personalIncomeBps));
    await page.getByRole("spinbutton", { name: /^Health/ }).fill(String(expected.budget.health));
    steps.push("Decisions: staged the budget (personal income 1225 bps, health 220,000,000)");

    // ---- Government: appoint a chief of staff ----
    await visit(page, "Government");
    const cabinet = page.getByTestId("cabinet-panel");
    await cabinet.locator(`[data-post-option="${expected.appointment.post}"]`).click();
    await expect(cabinet).toHaveAttribute("data-cabinet-state", "postSelected");
    await cabinet.locator(`[data-candidate-option="${expected.appointment.characterId}"]`).click();
    await expect(cabinet).toHaveAttribute("data-cabinet-state", "candidateSelected");
    await page.getByTestId("confirm-cabinet-order").click();
    await expect(page.getByTestId("staged-cabinet-summary")).toContainText("chief of staff");
    steps.push(`Government: staged ${expected.appointment.characterId} as chief of staff`);

    // ---- Relationships: bargain, assistance, promise ----
    await visit(page, "Relationships");
    const meeting = page.getByTestId("meeting-panel");
    const leader = meeting.locator(`[data-leader-option="${expected.bargainLeader}"]`);
    await expect(leader).toContainText(`${expected.bargainCapital} political capital`);
    await leader.click();
    await expect(page.getByTestId("bargain-blocked")).toHaveCount(0);
    await page.getByTestId("confirm-meeting").click();
    await meeting.locator(`[data-counterpart-option="${expected.assistanceProfile}"]`).click();
    await page.getByTestId("confirm-meeting").click();
    await meeting.locator(`[data-promise-option="${expected.promiseKey}"]`).click();
    await page.getByTestId("confirm-meeting").click();
    const staged = page.getByTestId("staged-meeting-summary");
    await expect(staged.locator(`[data-staged-bargain="${expected.bargainLeader}"]`)).toBeVisible();
    await expect(staged.locator(`[data-staged-assistance="${expected.assistanceProfile}"]`)).toBeVisible();
    await expect(staged.locator('[data-staged-promise="make"]')).toBeVisible();
    steps.push("Relationships: staged the bargain, the assistance request and the promise");

    // ---- Decisions: preview. Navigation dropped any earlier preview, so it is taken last. ----
    const preview = await previewThroughInterface(page);
    expect(preview.cabinet_capital).toBe(expected.cabinetCapital);
    expect(preview.legislative_bargain_capital).toBe(expected.bargainCapital);
    expect(preview.promise_release_capital).toBe(0);
    expect(preview.foreign_assistance_estimate, "the grant estimate must be positive").toBeGreaterThan(0);
    expect(preview.committed_capital).toBe(expected.committed);
    expect(preview.opening_capital).toBe(expected.openingCapital);
    expect(preview.affordable).toBe(true);
    expect(preview.would_pass, "Sofia Renn's endorsement carries the budget").toBe(true);
    const lower = (preview.chambers as { supporting_seats: number; required_seats: number }[])[0]!;
    expect([lower.supporting_seats, lower.required_seats]).toEqual([
      expected.lowerChamber.supporting,
      expected.lowerChamber.required,
    ]);
    const panel = page.getByTestId("consequences-panel");
    await expect(panel).toContainText("Would pass");
    await expect(page.getByTestId("bargain-capital")).toHaveText(String(expected.bargainCapital));
    // Gate 4A3 UX-1 hides capital terms this draft does not spend, so a zero release is not listed.
    await expect(page.getByTestId("promise-release-capital")).toHaveCount(0);
    await expect(page.getByTestId("assistance-estimate")).toBeVisible();
    await expect(panel).toContainText("money received");
    await expect(panel).toContainText(`${expected.committed} of ${expected.openingCapital} committed`);
    steps.push(
      `Decisions: previewed -- cabinet ${preview.cabinet_capital}, bargain ${preview.legislative_bargain_capital}, ` +
        `release ${preview.promise_release_capital}, assistance estimate ${preview.foreign_assistance_estimate}, ` +
        `${lower.supporting_seats} of ${lower.required_seats} required, ${preview.committed_capital} of ` +
        `${preview.opening_capital} committed`,
    );

    // ---- resolve: budget + cabinet + bargain + assistance + promise = five decisions ----
    const resolved = await resolveThroughInterface(page, 5);
    const body = (await resolved.json()) as {
      turnResult: { turn: number; drivers: { reason_id: string; label: string }[] };
    };
    const reasonIds = body.turnResult.drivers.map((d) => d.reason_id);
    for (const id of expected.reasonIds) expect(reasonIds, `a ${id} driver`).toContain(id);

    // Turn result renders each of them as a sentence.
    const live = await driversText(page);
    await expect(page.getByTestId("turn-result-view")).toHaveAttribute("data-context", "live");
    expect(live).toContain("backed the budget, for 113 political capital.");
    steps.push(`Turn result: drivers ${reasonIds.join(", ")}`);

    /* T2, RECORDED, NOT FIXED. Each driver line also renders its `reason_id` in a <code> element. That
     * is an engine identifier shown to the player -- T1's class -- so the run records whether it is
     * painted rather than letting it pass unremarked. It is not absorbed into this commit. */
    const codeProbe = await page.getByTestId("turn-result-view").locator("li code").evaluateAll((nodes) =>
      nodes.map((n) => {
        const rect = n.getBoundingClientRect();
        const style = getComputedStyle(n);
        return {
          text: n.textContent ?? "",
          painted: rect.width > 1 && rect.height > 1 && style.visibility !== "hidden" && style.display !== "none",
        };
      }),
    );

    // ---- History: the same turn, re-read, must say exactly the same thing ----
    await visit(page, "History");
    const turnButton = page.getByRole("button", { name: new RegExp(`^Turn ${body.turnResult.turn} — `) });
    await turnButton.click();
    await expect(turnButton).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByTestId("turn-result-view")).toHaveAttribute("data-context", "history");
    const history = await driversText(page);
    expect(history, "History must re-render the turn's drivers text-for-text").toBe(live);
    steps.push("History: the turn's drivers re-read identically");

    // ---- the consequences persist where a player would look for them ----
    await visit(page, "Relationships");
    await expect(page.locator("[data-active-promise]"), "the promise is now outstanding").toHaveCount(1);
    await visit(page, "Government");
    await expect(page.getByTestId("cabinet-panel")).toContainText("Bela Ronsard");
    steps.push("Relationships lists the promise as active; Government shows the new chief of staff");

    record.newFeatures = {
      scenario: "deficit_demo",
      steps,
      preview: {
        cabinet_capital: preview.cabinet_capital,
        legislative_bargain_capital: preview.legislative_bargain_capital,
        promise_release_capital: preview.promise_release_capital,
        foreign_assistance_estimate: preview.foreign_assistance_estimate,
        committed_capital: preview.committed_capital,
        opening_capital: preview.opening_capital,
        affordable: preview.affordable,
        would_pass: preview.would_pass,
        lowerChamber: lower,
      },
      driverReasonIds: reasonIds,
      historyIdenticalToLive: history === live,
      t2ReasonIdCodeElements: {
        count: codeProbe.length,
        painted: codeProbe.filter((c) => c.painted).length,
        sample: codeProbe.slice(0, 5),
        disposition:
          "Recorded, not fixed: an engine identifier rendered beside each driver sentence. Same class " +
          "as T1; owner to be assigned in the Commit 6 closeout.",
      },
      f11: "closed -- the first automated test that plays Government and Relationships against a live server",
    };
  });
});
