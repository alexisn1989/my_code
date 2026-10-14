/**
 * Gate 4A3 victory path (V-4) — the INSTALLED-ARCHIVE walkthrough of the campaign objective.
 *
 * Internal, and not one of the five external playtesters. It drives a server started from an
 * installed release archive, and nothing else (`playwright.walkthrough.config.ts` has no
 * `webServer`). It exercises exactly what the victory path added:
 *
 *   Walk A (Valdrun): the objective card in the reform stage; Constitution's "Draft the qualifying
 *     reform" activated by keyboard; Decisions with that card selected and focused; a Preview whose
 *     objective sentence begins "If enacted," and whose caveat says the amendment would not pass.
 *     It deliberately stops at the preview -- nothing is resolved.
 *   Walk B (deficit_demo): the same link; influence; a passing preview; resolve; the result's
 *     objective line and named amendment line; History's detail of that turn showing the SAME line
 *     and headline; the card in the qualifying-election stage; the checklist all met. Here the
 *     preview must agree with the resolution.
 *
 * BINDING TO THE ARCHIVE. Under `MANDATE_WALKTHROUGH_REQUIRED=1` (set by the npm script itself):
 *   - the URL, the archive path, its expected sha256, the install directory, the server's PID, the
 *     output name and the gate label are all required -- a missing one FAILS, never skips;
 *   - the archive's full outer sha256 is recomputed here and must equal the expected one;
 *   - the server PID's `/proc` cmdline must be the INSTALLED `mandate-gui` on the URL's port, and its
 *     installed `app.__file__` must lie inside the install directory.
 * The record is written with `wx` (never overwritten), and only after every assertion holds.
 *
 * Gate 4A3 map-led redesign: a SECOND, focused test -- the redesign walk -- on the same binding and
 * the same rules (installed server only, no development-server fallback, no console error, no
 * off-origin request). Arken (`tiny_valid`), with M-5's legal budget, "Lower the personal income tax":
 *   draft the proposal in Decisions -> Dashboard map -> the Parliament pin -> the bloc panel (Rural
 *   Alliance Farmers) -> stage Maret Kuusk's bargain -> Preview from Parliament -> the draft survives
 *   the way back to Decisions -> resolve -> the proposal card -> History.
 * It asserts that the draft survives navigation, that the preview agrees with the RECORDED resolution
 * chamber by chamber, and that History renders the turn exactly as the live result did.
 * Each walk runs through its own npm script, selected by `--grep`, with its own fresh output name.
 */

import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, readlinkSync, writeFileSync } from "node:fs";
import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

const REVIEW_DIR = path.join(process.cwd(), "..", "docs", "reviews");
const SAFE_NAME = /^[a-z0-9][a-z0-9.-]*$/;
const REQUIRED = process.env.MANDATE_WALKTHROUGH_REQUIRED === "1";
const ENV = {
  url: process.env.MANDATE_WALKTHROUGH_URL,
  archive: process.env.MANDATE_WALKTHROUGH_ARCHIVE,
  sha256: process.env.MANDATE_WALKTHROUGH_ARCHIVE_SHA256,
  installDir: process.env.MANDATE_WALKTHROUGH_INSTALL_DIR,
  serverPid: process.env.MANDATE_WALKTHROUGH_SERVER_PID,
  out: process.env.MANDATE_WALKTHROUGH_OUT,
  gate: process.env.MANDATE_WALKTHROUGH_GATE,
};

test.skip(!REQUIRED && ENV.url === undefined, "the walkthrough runs only through `npm run walkthrough:installed:*`");

async function visit(page: Page, name: string): Promise<void> {
  const entry = page.getByRole("navigation", { name: "Screens" }).getByRole("button", { name, exact: true });
  await entry.click();
  await expect(entry).toHaveAttribute("aria-current", "page");
}

function required(name: keyof typeof ENV): string {
  const value = ENV[name];
  if (value === undefined || value.trim() === "") {
    throw new Error(`MANDATE_WALKTHROUGH_${name.replace(/[A-Z]/g, (c) => `_${c}`).toUpperCase()} is required`);
  }
  return value;
}

/** THE BINDING, shared by both walks: every required variable, the archive's full outer sha256, and the
 * server that is actually answering -- the INSTALLED `mandate-gui` on the URL's port, whose `app` lives
 * in the install directory. A missing variable or a mismatch FAILS; there is no fallback. */
function bindToInstall() {
  expect(REQUIRED, "run through the npm script, which sets MANDATE_WALKTHROUGH_REQUIRED=1").toBe(true);
  const base = required("url").replace(/\/$/, "");
  const archive = required("archive");
  const expectedSha = required("sha256");
  const installDir = path.resolve(required("installDir"));
  const pid = required("serverPid");
  const out = required("out");
  const gate = required("gate");
  expect(out).toMatch(SAFE_NAME);
  const shots = path.join(REVIEW_DIR, `${out}-shots`);
  const recordPath = path.join(REVIEW_DIR, `${out}.json`);
  expect(existsSync(shots) || existsSync(recordPath), "a record is never overwritten").toBe(false);

  // ---- The binding: archive hash, then the server that is actually answering. ----
  const actualSha = createHash("sha256").update(readFileSync(archive)).digest("hex");
  expect(actualSha, "the archive's full outer sha256 is the candidate's").toBe(expectedSha);
  const cmdline = readFileSync(`/proc/${pid}/cmdline`, "utf-8").split("\0").filter((part) => part !== "");
  const cwd = readlinkSync(`/proc/${pid}/cwd`);
  const port = new URL(base).port;
  const installedGui = path.join(installDir, ".venv", "bin", "mandate-gui");
  expect(cmdline, "the server is the INSTALLED mandate-gui").toContain(installedGui);
  expect(cmdline[cmdline.indexOf("--port") + 1], "on the walkthrough's port").toBe(port);
  const appFile = execFileSync(path.join(installDir, ".venv", "bin", "python"), ["-I", "-c", "import app; print(app.__file__)"], {
    encoding: "utf-8",
  }).trim();
  expect(appFile.startsWith(installDir + path.sep), `the installed app (${appFile}) lives in the install`).toBe(true);
  const identity = { pid: Number(pid), cmdline, cwd, appFile };

  return { base, archive, expectedSha, actualSha, installDir, out, gate, shots, recordPath, identity };
}

/** Every request must stay on the installed server's origin, and nothing may log a console error. */
function watchPage(page: Page, base: string) {
  const consoleErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  const offOrigin: string[] = [];
  page.on("request", (request) => {
    const url = request.url();
    if (url.startsWith("data:") || url === "about:blank") return;
    if (!url.startsWith(`${base}/`)) offOrigin.push(url);
  });
  return { consoleErrors, offOrigin };
}

test("installed-archive walkthrough: the objective card, the Constitution link, the conditional preview, result and History", async ({ page }) => {
  const { base, archive, expectedSha, actualSha, gate, shots, recordPath, identity } = bindToInstall();
  mkdirSync(shots, { recursive: false });
  const { consoleErrors, offOrigin } = watchPage(page, base);
  await page.setViewportSize({ width: 1440, height: 900 });

  async function start(scenarioId: string): Promise<void> {
    await page.goto(`${base}/`);
    const scenarios = (await (await page.request.get(`${base}/api/scenarios`)).json()) as { scenario_id: string; display_name: string }[];
    const display = scenarios.find((s) => s.scenario_id === scenarioId)!.display_name;
    const created = page.waitForResponse((r) => r.url().includes("/api/game/new") && r.request().method() === "POST");
    await page.getByRole("button", { name: `Start ${display}` }).click();
    expect((await created).status()).toBe(200);
  }

  async function followQualifyingLink(byKeyboard: boolean): Promise<string> {
    await visit(page, "Constitution");
    const link = page.getByTestId("draft-qualifying-reform");
    if (byKeyboard) {
      await link.focus();
      await page.keyboard.press("Enter");
    } else {
      await link.click();
    }
    await expect(page.getByRole("navigation", { name: "Screens" }).getByRole("button", { name: "Decisions", exact: true })).toHaveAttribute("aria-current", "page");
    const summary = page.getByTestId("policy-selection-summary");
    await expect(summary).toBeFocused();
    const state = (await (await page.request.get(`${base}/api/game/state`)).json()) as { objective: { qualifying_card_id: string } };
    const options = (await (await page.request.get(`${base}/api/game/decision-options`)).json()) as { policy_cards: { card_id: string; title: string }[] };
    const title = options.policy_cards.find((card) => card.card_id === state.objective.qualifying_card_id)!.title;
    await expect(summary).toContainText(title);
    return title;
  }

  async function preview(): Promise<{ body: any; effect: string; caveat: string | null }> {
    const previewed = page.waitForResponse((r) => r.url().includes("/api/game/preview") && r.request().method() === "POST");
    await page.getByRole("button", { name: "Preview", exact: true }).click();
    const body = await (await previewed).json();
    const effect = await page.getByTestId("objective-effect").innerText();
    const caveatLocator = page.getByTestId("objective-effect-caveat");
    const caveat = (await caveatLocator.count()) ? await caveatLocator.innerText() : null;
    return { body, effect, caveat };
  }

  // ======== Walk A: Valdrun, stopping at a failing preview ========
  await start("decree_state");
  await visit(page, "Dashboard");
  const cardA = page.getByTestId("objective-card");
  await expect(cardA).toHaveAttribute("data-stage", "reform");
  await expect(cardA.getByTestId("objective-headline")).toHaveText("Reform the constitution: 0 of 3 conditions met.");
  await page.screenshot({ path: path.join(shots, "a1-valdrun-dashboard.png") });
  const titleA = await followQualifyingLink(true);
  const a = await preview();
  expect(a.body.would_pass, "Valdrun's reform without influence would not pass").toBe(false);
  expect(a.body.objective_effect_if_enacted?.effect).toBe("qualifies");
  expect(a.effect.startsWith("If enacted,"), a.effect).toBe(true);
  expect(a.caveat).toBe("This amendment would not pass as it stands, so it would not change the constitution.");
  await page.screenshot({ path: path.join(shots, "a2-valdrun-failing-preview.png") });

  // ======== Walk B: deficit_demo, the reform turn through the link ========
  await start("deficit_demo");
  await visit(page, "Dashboard");
  const cardB = page.getByTestId("objective-card");
  await expect(cardB).toHaveAttribute("data-stage", "reform");
  await expect(cardB.getByTestId("objective-headline")).toHaveText("Reform the constitution: 2 of 3 conditions met.");
  await page.screenshot({ path: path.join(shots, "b1-deficit-dashboard.png") });
  const titleB = await followQualifyingLink(false);
  const options = (await (await page.request.get(`${base}/api/game/decision-options`)).json()) as { blocs: { party_id: string; bloc_id: string; bloc_name: string }[] };
  const hardliners = options.blocs.find((b) => b.party_id === "citizens_bloc" && b.bloc_id === "hardliners")!.bloc_name;
  await page.getByLabel(`Influence capital for ${hardliners}`).fill("300");
  const b = await preview();
  expect(b.body.would_pass).toBe(true);
  expect(b.body.affordable).toBe(true);
  expect(b.effect).toBe("If enacted, this reform would record the qualifying transition; the election on turn 20 would decide.");
  expect(b.caveat).toBeNull();
  await page.screenshot({ path: path.join(shots, "b2-deficit-passing-preview.png") });

  await page.getByRole("button", { name: "Resolve turn" }).click();
  const resolved = page.waitForResponse((r) => r.url().includes("/api/game/resolve") && r.request().method() === "POST", { timeout: 120_000 });
  await page.getByRole("button", { name: "Confirm and resolve" }).click();
  const response = await resolved;
  expect(response.status()).toBe(200);
  const result = (await response.json()).turnResult as { turn: number; outcome_headline: string; objective_line: string | null; drivers: { reason_id: string }[] };
  // Preview and resolution agree (Walk B only): the preview said it passes, and it was enacted.
  const enacted = result.drivers.some((driver) => driver.reason_id === "constitutional_amendment_enacted");
  expect(enacted, "the previewed pass was enacted").toBe(b.body.would_pass);
  const line = "The constitution now qualifies, and the transition is recorded. Win the election on turn 20 to complete it.";
  expect(result.objective_line).toBe(line);
  const live = page.getByTestId("turn-result-view");
  await expect(live).toHaveAttribute("data-context", "live");
  await expect(live.getByTestId("objective-line")).toHaveText(line);
  await expect(live).toContainText("Decree authority: emergency only → none.");
  await page.screenshot({ path: path.join(shots, "b3-deficit-result.png") });

  await visit(page, "History");
  await page.getByRole("button", { name: new RegExp(`^Turn ${result.turn} — `) }).click();
  const history = page.getByTestId("turn-result-view");
  await expect(history).toHaveAttribute("data-context", "history");
  await expect(history.getByTestId("objective-line")).toHaveText(line);
  await expect(history).toContainText(result.outcome_headline);
  await expect(history).toContainText("Decree authority: emergency only → none.");
  await page.screenshot({ path: path.join(shots, "b4-deficit-history.png") });

  await visit(page, "Dashboard");
  await expect(cardB).toHaveAttribute("data-stage", "qualifying_election");
  await expect(cardB.getByTestId("objective-headline")).toHaveText("Win the qualifying election: turn 20.");
  await page.screenshot({ path: path.join(shots, "b5-deficit-dashboard-after.png") });
  await visit(page, "Constitution");
  const rows = page.getByTestId("constitution-checklist").locator("li[data-condition]");
  await expect(rows).toHaveCount(3);
  for (let i = 0; i < 3; i += 1) {
    await expect(rows.nth(i).getByTestId("condition-status")).toHaveText("Met");
  }
  await expect(page.getByTestId("objective-transition-text")).toHaveText(`Qualifying transition: recorded on turn ${result.turn}`);
  await page.screenshot({ path: path.join(shots, "b6-deficit-constitution-after.png") });

  expect(offOrigin, "every request stays on the installed server's origin").toEqual([]);
  expect(consoleErrors, "no console error anywhere in the walk").toEqual([]);
  writeFileSync(
    recordPath,
    `${JSON.stringify(
      {
        gate,
        internal: "Not one of the five external playtesters.",
        archive: { file: path.basename(archive), sha256: actualSha, expectedSha256: expectedSha },
        installedServer: { url: base, ...identity },
        walkA: { scenario: "decree_state", linkCard: titleA, preview: { would_pass: a.body.would_pass, affordable: a.body.affordable, effect: a.body.objective_effect_if_enacted, sentence: a.effect, caveat: a.caveat }, resolved: false },
        walkB: {
          scenario: "deficit_demo",
          linkCard: titleB,
          preview: { would_pass: b.body.would_pass, affordable: b.body.affordable, effect: b.body.objective_effect_if_enacted, sentence: b.effect, caveat: b.caveat },
          resolution: { turn: result.turn, headline: result.outcome_headline, enacted, objectiveLine: result.objective_line },
          historyMatchesLive: true,
          afterStage: "qualifying_election",
        },
        offOrigin,
        consoleErrors,
      },
      null,
      2,
    )}\n`,
    { flag: "wx" },
  );
});

test("installed-archive redesign walk: Dashboard map, Parliament, bloc panel, bargain, Preview, resolve, proposal card, History", async ({ page }) => {
  const { base, archive, expectedSha, actualSha, gate, shots, recordPath, identity } = bindToInstall();
  mkdirSync(shots, { recursive: false });
  const { consoleErrors, offOrigin } = watchPage(page, base);
  await page.setViewportSize({ width: 1440, height: 900 });
  const nav = (name: string) => page.getByRole("navigation", { name: "Screens" }).getByRole("button", { name, exact: true });
  const CARD = "Lower the personal income tax";

  // ---- Arken, the known scenario; the legal budget drafted FIRST. ----
  await page.goto(`${base}/`);
  const created = page.waitForResponse((r) => r.url().includes("/api/game/new") && r.request().method() === "POST");
  await page.getByRole("button", { name: "Start Republic of Arken" }).click();
  expect((await created).status()).toBe(200);
  await visit(page, "Decisions");
  await page.getByRole("group", { name: CARD }).getByRole("button", { name: "Select" }).click();
  await expect(page.getByRole("group", { name: CARD }).getByRole("button", { name: "Selected" })).toBeVisible();
  await page.screenshot({ path: path.join(shots, "c1-proposal-drafted.png") });

  // ---- The Dashboard map: the Parliament pin. ----
  await visit(page, "Dashboard");
  const pin = page.locator("[data-map-pin]").and(page.getByRole("button", { name: "Parliament: opens Legislature", exact: true }));
  await expect(pin).toHaveCount(1);
  await page.screenshot({ path: path.join(shots, "c2-dashboard-map.png") });
  await pin.focus();
  await page.keyboard.press("Enter");
  await expect(nav("Legislature")).toHaveAttribute("aria-current", "page");
  // The draft survived Decisions -> Dashboard -> Parliament.
  await expect(page.getByTestId("parliament-draft")).toContainText(CARD);

  // ---- The bloc panel: stage Maret Kuusk's bargain. ----
  await page.locator('[data-testid="chamber-card"][data-chamber="lower"] [data-bloc-open="rural_alliance/farmers"]').click();
  const panel = page.getByTestId("bloc-panel");
  await expect(panel).toBeVisible();
  await panel.getByRole("button", { name: "Stage this bargain · 105" }).click();
  await expect(panel.getByTestId("bargain-staged-here")).toContainText("Staged: endorsement from Maret Kuusk");

  // ---- Preview from Parliament: each chamber's estimate is shown, and its bloc rows sum. ----
  const previewed = page.waitForResponse((r) => r.url().includes("/api/game/preview") && r.request().method() === "POST");
  await page.getByTestId("parliament-draft").getByRole("button", { name: "Preview" }).click();
  const previewResponse = await previewed;
  const sent = previewResponse.request().postDataJSON() as { decisions: { kind: string }[] };
  expect(sent.decisions.map((d) => d.kind), "the preview carried the proposal and the bargain").toEqual(
    expect.arrayContaining(["budget", "legislative_bargain"]),
  );
  const preview = (await previewResponse.json()) as { would_pass: boolean; chambers: { chamber: string; supporting_seats: number; carries: boolean }[] };
  await expect(page.getByTestId("draft-status")).toHaveText("Preview is current for this draft");
  const tallies = await page.evaluate(() =>
    [...document.querySelectorAll<HTMLElement>('[data-testid="chamber-card"]')].map((card) => ({
      chamber: card.dataset.chamber ?? "",
      mode: card.dataset.mode ?? "",
      rowSum: [...card.querySelectorAll('[data-testid="bloc-supporting"]')].reduce((n, cell) => n + Number(cell.textContent), 0),
    })),
  );
  for (const chamber of preview.chambers) {
    const shown = tallies.find((t) => t.chamber === chamber.chamber)!;
    expect(shown.mode, `${chamber.chamber}: the live estimate is shown`).toBe("current");
    expect(shown.rowSum, `${chamber.chamber}: the bloc rows sum to the preview`).toBe(chamber.supporting_seats);
  }
  await page.screenshot({ path: path.join(shots, "c3-parliament-previewed.png"), fullPage: true });

  // ---- The draft survives the way back to Decisions. ----
  await visit(page, "Decisions");
  await expect(page.getByRole("group", { name: CARD }).getByRole("button", { name: "Selected" })).toBeVisible();
  await expect(page.getByTestId("staged-actions")).toContainText("Maret Kuusk");
  await expect(page.getByTestId("staged-count")).toHaveText("· 2 staged");

  // ---- Resolve; the preview agrees with the RECORDED resolution. ----
  await page.getByRole("button", { name: "Resolve turn" }).click();
  const resolved = page.waitForResponse((r) => r.url().includes("/api/game/resolve") && r.request().method() === "POST", { timeout: 120_000 });
  await page.getByRole("button", { name: "Confirm and resolve" }).click();
  const response = await resolved;
  expect(response.status()).toBe(200);
  const result = (await response.json()).turnResult as {
    turn: number;
    outcome_headline: string;
    recorded_vote: { outcome: string; chambers: { chamber: string; supporting_seats: number; required_seats: number; passed: boolean }[] } | null;
    drivers: { reason_id: string; params: Record<string, string | number> }[];
  };
  expect(result.recorded_vote, "a chamber vote was recorded").not.toBeNull();
  const recorded = result.recorded_vote!;
  expect(recorded.chambers.map((c) => c.chamber)).toEqual(preview.chambers.map((c) => c.chamber));
  for (const chamber of preview.chambers) {
    const vote = recorded.chambers.find((c) => c.chamber === chamber.chamber)!;
    expect(vote.supporting_seats, `${chamber.chamber}: recorded support equals the preview`).toBe(chamber.supporting_seats);
    expect(vote.passed, `${chamber.chamber}: recorded outcome equals the preview`).toBe(chamber.carries);
  }
  expect(recorded.outcome === "passed_legislative", "the recorded outcome equals the preview's verdict").toBe(preview.would_pass);

  // ---- The proposal card and the reactions. ----
  const live = page.getByTestId("turn-result-view");
  await expect(live).toHaveAttribute("data-context", "live");
  await expect(live).toHaveAttribute("data-unmatched-components", "0");
  await expect(live.getByTestId("result-verdict")).toHaveText(preview.would_pass ? "Enacted" : "Did not carry");
  const blocks = live.getByTestId("proposal-card").getByTestId("result-chamber");
  await expect(blocks).toHaveCount(recorded.chambers.length);
  for (const [i, vote] of recorded.chambers.entries()) {
    await expect(blocks.nth(i).getByTestId("result-chamber-line")).toContainText(
      `${vote.supporting_seats} supporting; ${vote.required_seats} required — ${vote.passed ? "carried" : "did not carry"}`,
    );
    const seats = blocks.nth(i).getByTestId("hemicycle");
    await expect(seats).toHaveAttribute("data-mode", "recorded");
    await expect(seats.locator('[data-seat][data-filled="true"]')).toHaveCount(vote.supporting_seats);
  }
  const bargain = result.drivers.find((d) => d.reason_id === "legislative_bargain_accepted")!;
  const leader = live.locator('[data-testid="result-person"][data-reason-id="legislative_bargain_accepted"]');
  await expect(leader).toContainText("Maret Kuusk");
  await expect(leader).toContainText("backed the budget, for 105 political capital.");
  await expect(leader.locator("[data-portrait-ref]")).toHaveAttribute("data-portrait-ref", String(bargain.params["character_portrait_ref"]));
  await page.screenshot({ path: path.join(shots, "c4-result.png"), fullPage: true });

  // ---- History renders the turn exactly as the live result did. ----
  const reading = () =>
    page.getByTestId("turn-result-view").evaluate((root) => {
      const text = (sel: string) =>
        [...root.querySelectorAll<HTMLElement>(sel)]
          .map((n) => n.innerText)
          .join("\n")
          .replace(/\s*Reviewing a past turn\. Rendered by the same component as the live result\./, "")
          .trimEnd();
      return {
        card: text('[data-testid="proposal-card"]'),
        people: text('[data-testid="result-person"]'),
        blocs: text('[data-testid="result-bloc"]'),
        portraits: [...root.querySelectorAll("[data-portrait-ref]")].map((n) => n.getAttribute("data-portrait-ref")),
        filled: [...root.querySelectorAll('[data-seat][data-filled="true"]')].map((n) => n.getAttribute("data-party")),
      };
    });
  const liveReading = await reading();
  await visit(page, "History");
  await page.getByRole("button", { name: new RegExp(`^Turn ${result.turn} — `) }).click();
  await expect(page.getByTestId("turn-result-view")).toHaveAttribute("data-context", "history");
  expect(await reading(), "History matches the live result").toEqual(liveReading);
  await page.screenshot({ path: path.join(shots, "c5-history.png"), fullPage: true });

  expect(offOrigin, "every request stays on the installed server's origin").toEqual([]);
  expect(consoleErrors, "no console error anywhere in the walk").toEqual([]);
  writeFileSync(
    recordPath,
    `${JSON.stringify(
      {
        gate,
        internal: "Not one of the five external playtesters.",
        archive: { file: path.basename(archive), sha256: actualSha, expectedSha256: expectedSha },
        installedServer: { url: base, ...identity },
        redesignWalk: {
          scenario: "tiny_valid",
          proposal: CARD,
          bargain: { leader: "Maret Kuusk", price: 105 },
          draftSurvivedNavigation: true,
          preview: { would_pass: preview.would_pass, chambers: preview.chambers },
          resolution: { turn: result.turn, headline: result.outcome_headline, outcome: recorded.outcome, chambers: recorded.chambers },
          previewAgreesWithResolution: true,
          historyMatchesLive: true,
        },
        offOrigin,
        consoleErrors,
      },
      null,
      2,
    )}\n`,
    { flag: "wx" },
  );
});
