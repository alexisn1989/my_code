/**
 * Gate 4A3 Commit 5 — THE CONCLUDED TERMINAL SCREEN, measured.
 *
 * TWO MEASUREMENTS HAVE BEEN OWED SINCE COMMIT 3, and both were deferred twice with the same honest
 * reason: they are about the Victory / defeat screen in a state no audit had ever entered.
 *
 *   - N6, the last of Commit 2's six axe `incomplete` results. Recorded as "no text-bearing element
 *     was present to measure on this screen in a mid-campaign session", explicitly NOT claimed as
 *     resolved.
 *   - TERMINAL-STATE REFLOW at the 320px conformance width. The existing sweep does visit the screen,
 *     so it has been reflowing a PLACEHOLDER rather than an outcome layout.
 *
 * THE TWO BLOCKERS WERE NOT THE SAME, which is why the fix is in two parts. Reflow was blocked only by
 * the missing state -- its overflow measurement already walks every element. N6 was blocked by the
 * missing state AND by the contrast scan's candidate selector, which asked for spans, SVG text and
 * aria-hidden nodes and so matched NOTHING on a screen built from headings, paragraphs and buttons.
 * That selector is fixed in `contrast-probe.ts` (`measureTextOwners`), and this file is the state.
 *
 * WHY A SEPARATE FILE WITH ITS OWN SERVER. This spec resolves an entire campaign. The shared
 * `webServer` in `playwright.config.ts` holds ONE process-wide `GameSession`, so a concluded campaign
 * here would leak into whatever ran next. Same pattern as `stress-seated-cabinet.spec.ts` and
 * `icon-coverage.spec.ts`: own server, own save root, and the REAL `data/scenarios` root, so every
 * figure below is a claim about shipped content.
 *
 * TURNS ARE DRIVEN THROUGH THE API; EVERY MEASUREMENT IS TAKEN FROM THE RENDERED DOM. Stated plainly
 * rather than implied. Thirty-two click-and-confirm round trips would add brittleness without changing
 * what is measured -- the state is the server's either way -- and driving a campaign entirely through
 * the interface is the frozen plan's T21 walkthrough, which this commit's scope excludes and which
 * remains owed.
 */

import { execFileSync, spawn, type ChildProcess } from "node:child_process";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { AxeBuilder } from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import {
  CALIBRATION,
  RATIO_TOLERANCE,
  SURFACES,
  TEXT_CONTRAST_MINIMUM,
  installColourProbe,
  measureTextOwners,
  offlineRatio,
  surfaceNameOf,
  type TextOwnerMeasurement,
} from "./contrast-probe";
import { findIdentifierLeaks } from "./player-text";

const REVIEW_DIR = path.join(process.cwd(), "..", "docs", "reviews");
const SCENARIO_ROOT = path.join(process.cwd(), "..", "data", "scenarios");
const OUT_NAME = process.env.MANDATE_TERMINAL_OUT ?? "gate-4a3-commit5-terminal";

/**
 * `tiny_valid`, resolved with EMPTY decision sets until it concludes.
 *
 * WHY THIS IS DETERMINISTIC, and why no seed override is needed. A campaign is a function of
 * (scenario, seed, decisions); with the decision set empty only the first two matter, and the seed is
 * the scenario's own authored `seed: 42`. The engine's stochastic channels are seeded from it rather
 * than from a clock -- `foreign_conflict.py` states "No I/O, no randomness, no state mutation, no
 * clock, no floating point" at its head and takes an `occurrence_draw` as a PARAMETER, and
 * `resolver.py` supplies `game_seed=working.seed`. The whole replay discipline depends on this:
 * `validate_history` re-resolves a save and expects the same result.
 *
 * AND THE ENDING IS A GAME RULE, NOT A DICE ROLL: a 2-term limit against a 16-turn election interval.
 * The incumbent wins its turn-16 election and then hits the limit at its second term, firing
 * `TERM_LIMIT_EXIT`.
 */
const SCENARIO_ID = "tiny_valid";

/**
 * The observed ending, PINNED FROM A REAL RUN rather than borrowed.
 *
 * `backend/tests/test_soak.py` records turn 32 for this scenario and calls it "the real, deterministic
 * horizon under ordinary play with no decisions submitted" -- but it measures that figure with the
 * scenario's FOREIGN DYAD DISABLED (`model_copy(update={"eligible": False})`), so a live war's
 * fluctuating security-anxiety contribution cannot perturb its pinned legitimacy figures. The shipped
 * scenario ships that dyad ENABLED (`kessia`/`vetruska`, eligible), and legitimacy feeds election
 * outcomes, so the soak's 32 was not automatically this run's 32.
 *
 * Measured directly against the shipped configuration before this spec was written: turn 32, bucket
 * `defeat`, reason `term_limit_exit`, 33 history entries, `validate_history == []`. It agrees with the
 * soak -- now for a checked reason rather than by assumption. A drift in content or engine fails here
 * loudly instead of quietly measuring a different ending.
 */
const EXPECTED_TERMINAL = {
  turn: 32,
  bucket: "defeat",
  // Commit 5b (T1): the label is the server's AUTHORED wording, no longer the engine identifier
  // `term_limit_exit` Commit 5 recorded. The headline is deliberately unchanged, byte for byte.
  reasonLabel: "Term limit exit",
  headline: "Removed from office: term limit exit, turn 32.",
} as const;

/** The engine value behind `reasonLabel`. It must reach the server's state and never the page. */
const EXPECTED_TERMINAL_IDENTIFIER = "term_limit_exit";

/** A hard stop, so a scenario that stops concluding fails instead of resolving for ever. */
const RESOLVE_CAP = 60;

/** The 320px CONFORMANCE width of WCAG 2.2 SC 1.4.10, and the below-floor case, exactly as
 * `verify-commit3-fixes.spec.ts` defines them so the two are comparable. */
const CONFORMANCE = { name: "reflow-wcag-320x512", width: 320, height: 512 } as const;
/** Below the 320px floor. Measured and RECORDED; deliberately never asserted. */
const BELOW_FLOOR = { name: "reflow200-mobile-195x422", width: 195, height: 422 } as const;

/** Every screen a concluded campaign can reach. Three of them RENDER DIFFERENTLY once `terminal` is
 * non-null, and those three are the reason this sweep is not limited to the named screen:
 *
 *   - Victory / defeat renders the outcome itself -- the named deliverable, and where N6's nodes live;
 *   - Dashboard gains a "campaign has ended" panel with a toned headline and a navigate control;
 *   - Decisions takes an EARLY RETURN that replaces the entire composer with a terminal panel, so its
 *     320px layout in this state is a completely different layout that has never been measured.
 */
const SCREENS = [
  "Dashboard",
  "Government",
  "Relationships",
  "Strategic map",
  "Decisions",
  "Turn result",
  "History",
  "Victory / defeat",
] as const;

/* GLOSSARY IS DELIBERATELY ABSENT, and the first draft of this spec got that wrong in a way worth
 * recording. It is CHROME, not a screen: `GreyboxApp.tsx` renders it from a header toggle into a
 * `role="region"` OUTSIDE `<main>`, and the nav list does not contain it. So asking the nav for a
 * button named "Glossary" found the header toggle, clicked it, navigated nowhere, and the scan -- which
 * is scoped to `main` -- measured the PREVIOUS screen a second time. The artifact then carried a
 * "Glossary" row whose every figure was identical to the terminal screen's, which is a false claim
 * about coverage rather than a harmless duplicate.
 *
 * It is excluded rather than special-cased because a concluded campaign does not change it: it renders
 * the same definition list in every campaign state, and it is already covered by Commit 2's axe sweep
 * (as one of its 89 surfaces) and by `verify:fixes`. Measuring it here would add a state-independent
 * surface to a state-specific sweep. */

let server: ChildProcess | null = null;
let base = "";

test.afterAll(() => {
  server?.kill("SIGINT");
});

function freePort(): number {
  const script =
    "const s=require('node:net').createServer();" +
    "s.listen(0,'127.0.0.1',()=>{const a=s.address();" +
    "process.stdout.write(String(typeof a==='object'&&a?a.port:0));s.close();});";
  return Number(execFileSync(process.execPath, ["-e", script], { encoding: "utf-8" }).trim());
}

interface TerminalSummary {
  bucket: string;
  headline: string;
  reason_label: string;
  turn: number;
}

interface StateView {
  campaign_id: string;
  revision: string;
  turn: number;
  terminal: TerminalSummary | null;
}

async function readState(page: Page): Promise<StateView> {
  const response = await page.request.get(`${base}/api/game/state`);
  expect(response.ok(), "the state projection must be readable").toBe(true);
  return (await response.json()) as StateView;
}

/** Navigate to a screen and PROVE it happened, returning the reason when it did not.
 *
 * A BARE CLICK IS NOT NAVIGATION, and trusting one produced a false row in this spec's first run. The
 * nav marks the active entry with `aria-current="page"` (`GreyboxApp.tsx`), so that attribute is the
 * proof: a click that silently does nothing -- a disabled control, a label that belongs to some other
 * control, a screen that refuses to mount -- leaves it unset, and this returns a reason instead of
 * letting the caller measure whatever was already on screen and attribute it to the screen it asked
 * for. The nav is addressed through its own landmark rather than the whole page, so a button elsewhere
 * that happens to share a label (the terminal screen's own "Review history", for instance) cannot be
 * mistaken for a nav entry. */
async function visit(page: Page, screen: string): Promise<{ ok: boolean; reason: string }> {
  const nav = page.getByRole("navigation", { name: "Screens" });
  const control = nav.getByRole("button", { name: screen, exact: true });
  if ((await control.count()) === 0) {
    return { ok: false, reason: "no nav entry carries this label" };
  }
  if (!(await control.isVisible().catch(() => false))) {
    return { ok: false, reason: "the nav entry is not visible" };
  }
  if (await control.isDisabled().catch(() => true)) {
    const title = (await control.getAttribute("title")) ?? "(no title)";
    return { ok: false, reason: `the nav entry is DISABLED -- title: ${title}` };
  }
  await control.click();
  // Long enough for the screen's own queries to settle; `History` in particular renders an entry list
  // it has to fetch, and a 250ms settle measured it mid-flight on the first run.
  await page.waitForLoadState("networkidle").catch(() => {});
  await page.waitForTimeout(400);
  const current = await control.getAttribute("aria-current");
  if (current !== "page") {
    return { ok: false, reason: `clicked, but aria-current is ${String(current)} rather than "page"` };
  }
  return { ok: true, reason: "navigated" };
}

/** Nodes whose content is wider than their own scroll box: real clipping, not a guess. Copied in shape
 * from `verify-commit3-fixes.spec.ts` so the conformance figures here and there mean the same thing. */
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

async function pageScrollsHorizontally(page: Page): Promise<boolean> {
  return page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
  );
}

const record: Record<string, unknown> = {
  gate: "4A3 (frozen-plan 4A5) Commit 5",
  subject: "the concluded terminal screen: N6 contrast and terminal-state reflow",
  scenario: `${SCENARIO_ID}, via the real data/scenarios root, on this spec's own server`,
  coverage: [] as string[],
};

test.describe("Gate 4A3 Commit 5 — the concluded terminal screen", () => {
  test.describe.configure({ mode: "serial" });

  test("a concluded campaign: N6 contrast measured, terminal reflow asserted at 320px", async ({
    page,
  }) => {
    test.setTimeout(900_000);
    await installColourProbe(page);

    // ---- its own server, against the REAL scenario root ----
    const saveRoot = mkdtempSync(path.join(tmpdir(), "mandate-terminal-coverage-"));
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
      if (ok) break;
      await page.waitForTimeout(500);
    }

    // The button label is READ FROM THE API rather than retyped: `Start ${display_name}` uses the
    // projected display name, which is the COUNTRY rather than the scenario file's own `name:`. A
    // hard-coded label was wrong on Commit 4a's first run for exactly that reason.
    const scenarios = (await page.request.get(`${base}/api/scenarios`).then((r) => r.json())) as {
      scenario_id: string;
      display_name: string;
    }[];
    const scenario = scenarios.find((s) => s.scenario_id === SCENARIO_ID);
    expect(scenario, `${SCENARIO_ID} must be present in the real scenario root`).toBeDefined();

    await page.goto(`${base}/`);
    const start = page.getByRole("button", { name: `Start ${scenario!.display_name}` });
    await start.waitFor({ state: "visible", timeout: 30_000 });
    // The waiter is registered BEFORE the click: register the waiter BEFORE the click; see the note at the /preview site in `icon-coverage.spec.ts`. An awaited click can complete the request before the listener attaches, and then the wait times out on an event that has already gone by.
    const startPending = page.waitForResponse(
      (r) => r.url().includes("/api/game/state") && r.status() === 200,
      { timeout: 30_000 },
    );
    await start.click();
    await startPending;

    // ================= DRIVE THE CAMPAIGN TO ITS TERMINAL STATE =================
    // Empty decision sets, the revision re-read from the server each turn rather than incremented
    // locally -- the engine's own staleness check stays load-bearing on what the client claims.
    let state = await readState(page);
    let resolved = 0;
    while (state.terminal === null && resolved < RESOLVE_CAP) {
      const response = await page.request.post(`${base}/api/game/resolve`, {
        data: { revision: state.revision, campaign_id: state.campaign_id, decisions: [] },
      });
      expect(
        response.ok(),
        `resolving turn ${state.turn} failed: ${response.status()} ${await response.text()}`,
      ).toBe(true);
      resolved += 1;
      state = await readState(page);
    }

    /* THE ANTI-VACUITY GATE. Nothing below is credited until the SERVER says the campaign concluded --
     * not the DOM, which is what a measurement of a placeholder would also satisfy. An un-concluded
     * campaign is a stop-and-report, never a silently skipped measurement. */
    expect(
      state.terminal,
      `the campaign did not conclude within ${RESOLVE_CAP} resolved turns, so neither N6 nor terminal ` +
        `reflow can be measured here; that is a stop-and-report, not a pass`,
    ).not.toBeNull();
    const terminal = state.terminal!;
    expect(terminal.turn, "the pinned terminal turn").toBe(EXPECTED_TERMINAL.turn);
    expect(terminal.bucket, "the pinned terminal bucket").toBe(EXPECTED_TERMINAL.bucket);
    expect(terminal.reason_label, "the pinned removal reason").toBe(EXPECTED_TERMINAL.reasonLabel);
    expect(terminal.headline, "the pinned projected headline").toBe(EXPECTED_TERMINAL.headline);

    record.campaign = {
      scenarioId: SCENARIO_ID,
      resolvedTurns: resolved,
      cap: RESOLVE_CAP,
      terminal,
      determinism:
        "empty decision sets throughout, so the campaign is a function of the scenario and its own " +
        "authored seed 42; the ending is the 2-term limit against a 16-turn election interval, a game " +
        "rule rather than a draw. Pinned from a direct measurement against the SHIPPED configuration " +
        "(foreign dyad enabled), which `test_soak.py` measures with that dyad disabled.",
    };

    /* BRING THE CLIENT'S OWN SESSION UP TO THE CONCLUDED STATE, through the interface.
     *
     * A RELOAD ALONE IS NOT ENOUGH, and the first run of this spec proved it. The turns above were
     * resolved through the API, so the client's stored revision was still the one it held at turn 0;
     * reloading cleared it to `null` instead. The screens that read the server directly still rendered
     * live data -- which is why the mistake was not obvious -- but `GreyboxApp` gates every
     * `requiresActiveGame` nav entry on the CLIENT's revision, so Government, Relationships and
     * Strategic map came back "DISABLED -- Load or start a game", and History rendered an empty list.
     * Three screens went unmeasured and one was measured in the wrong state.
     *
     * Loading the save through the Title screen's own control is the fix, and it is also what a player
     * does: it sets the client's campaign view from the server's, so the whole interface is genuinely
     * in the concluded state rather than merely displaying parts of it. */
    await page.reload();
    await page.waitForTimeout(600);

    const saves = (await page.request.get(`${base}/api/saves`).then((r) => r.json())) as {
      save_id: string;
      display_name: string;
      loadable: boolean;
    }[];
    const target = saves.find((entry) => entry.loadable);
    expect(target, "the concluded campaign must be present and loadable").toBeDefined();
    const loadControl = page.getByRole("button", { name: target!.display_name, exact: true });
    await loadControl.waitFor({ state: "visible", timeout: 30_000 });
    await loadControl.click();
    await page.waitForLoadState("networkidle").catch(() => {});
    await page.waitForTimeout(600);

    /* PROOF that the client session really is live, rather than the screens merely looking right. A
     * `requiresActiveGame` entry is enabled ONLY when the client holds a revision, so this single
     * assertion is what distinguishes a loaded campaign from the half-state described above. */
    const gatedNavEntry = page
      .getByRole("navigation", { name: "Screens" })
      .getByRole("button", { name: "Strategic map", exact: true });
    await expect(
      gatedNavEntry,
      "after loading, the client must hold a live campaign view -- a disabled `requiresActiveGame` " +
        "entry means the interface is in the half-state where only server-reading screens work",
    ).toBeEnabled();

    // ================= N6: CONTRAST ON THE CONCLUDED SCREENS =================
    const perScreen: {
      screen: string;
      measured: number;
      candidates: number;
      rejectedNoOwnText: number;
      rejectedHidden: number;
      worstRatio: number;
      worstOn: string;
      worstSurface: string;
      belowBar: { selector: string; text: string; ratio: number; bg: string }[];
    }[] = [];
    const all: TextOwnerMeasurement[] = [];
    /** Screens that could not be reached, WITH the reason. A bare list would leave a reader unable to
     * tell "this screen is legitimately unavailable in a concluded campaign" from "the harness failed to
     * click it", and those are very different facts about the evidence. */
    const unreachable: { screen: string; reason: string }[] = [];
    let terminalScreenScan: Awaited<ReturnType<typeof measureTextOwners>> | null = null;

    for (const screen of SCREENS) {
      const nav = await visit(page, screen);
      if (!nav.ok) {
        unreachable.push({ screen, reason: nav.reason });
        continue;
      }
      const scan = await measureTextOwners(page);
      if (screen === "Victory / defeat") terminalScreenScan = scan;
      // T1 (fixed in Commit 5b): no screen in the concluded state shows a player the engine's
      // identifier for why the campaign ended. Checked on EVERY screen, because the headline also
      // reaches Dashboard and Decisions, and the save list reaches Title.
      const leaks = await findIdentifierLeaks(page, [EXPECTED_TERMINAL_IDENTIFIER]);
      expect(leaks, `${screen} must not render the raw reason identifier`).toEqual([]);
      if (scan.measured.length === 0) {
        perScreen.push({
          screen,
          measured: 0,
          candidates: scan.candidates,
          rejectedNoOwnText: scan.rejectedNoOwnText,
          rejectedHidden: scan.rejectedHidden,
          worstRatio: -1,
          worstOn: "(nothing measured)",
          worstSurface: "(none)",
          belowBar: [],
        });
        continue;
      }
      all.push(...scan.measured);
      const worst = scan.measured.reduce((a, b) => (a.ratio <= b.ratio ? a : b));
      perScreen.push({
        screen,
        measured: scan.measured.length,
        candidates: scan.candidates,
        rejectedNoOwnText: scan.rejectedNoOwnText,
        rejectedHidden: scan.rejectedHidden,
        worstRatio: worst.ratio,
        worstOn: `${worst.selector} ${JSON.stringify(worst.text.slice(0, 40))}`,
        worstSurface: surfaceNameOf(worst.bg) ?? `NOT A PALETTE SURFACE (${worst.bg})`,
        belowBar: scan.measured
          .filter((m) => m.ratio < TEXT_CONTRAST_MINIMUM)
          .map((m) => ({ selector: m.selector, text: m.text, ratio: m.ratio, bg: m.bg })),
      });
    }

    expect(
      terminalScreenScan,
      `the Victory / defeat screen must be reachable; unreachable screens this run: ` +
        `${JSON.stringify(unreachable)}`,
    ).not.toBeNull();

    /* EVERY MEASURED SCREEN MUST BE A DISTINCT SCREEN. The first run of this spec produced two rows
     * with byte-identical figures, because a click that navigated nowhere let the previous screen be
     * measured twice under a second name. `visit` now proves navigation via `aria-current`, and this
     * asserts the consequence directly rather than trusting that proof: no two screens may report the
     * same (measured, candidates, worstRatio, worstOn) tuple. */
    const fingerprints = perScreen
      .filter((s) => s.measured > 0)
      .map((s) => `${s.measured}|${s.candidates}|${s.worstRatio}|${s.worstOn}`);
    expect(
      fingerprints.length - new Set(fingerprints).size,
      "two screens reported identical measurements, which means one of them was not actually visited",
    ).toBe(0);

    /* THE MEASUREMENT THIS COMMIT EXISTS FOR: at least one TERMINAL-OUTCOME text node, identified by
     * strings the SERVER projected rather than by anything this spec hard-codes about the layout.
     *
     * Without this the widened candidate set could produce a confident pass having measured only the
     * page chrome, or -- worse -- the screen's still-active PLACEHOLDER, which is what every previous
     * run saw. Matching on `terminal.headline` and `terminal.reason_label` proves the measured text IS
     * the outcome. The concluded branch renders exactly three text owners inside the outcome panel, and
     * all three are required. */
    const owners = terminalScreenScan!.measured;
    const bucketHeading = terminal.bucket === "victory" ? "Victory" : "Defeat";
    const headlineNode = owners.find((m) => m.text.trim() === terminal.headline.trim());
    const reasonNode = owners.find(
      (m) => m.text.includes(terminal.reason_label) && m.text.includes(String(terminal.turn)),
    );
    const headingNode = owners.find((m) => m.text.trim() === bucketHeading);

    expect(
      headlineNode,
      `the outcome HEADLINE (${JSON.stringify(terminal.headline)}) must appear as a measured text ` +
        `owner; without it N6 would be "resolved" without the outcome having been measured`,
    ).toBeDefined();
    expect(
      reasonNode,
      `the outcome REASON line (containing ${JSON.stringify(terminal.reason_label)} and turn ` +
        `${terminal.turn}) must appear as a measured text owner`,
    ).toBeDefined();
    expect(
      headingNode,
      `the outcome PANEL HEADING (${JSON.stringify(bucketHeading)}) must appear as a measured text owner`,
    ).toBeDefined();

    /* AND THEIR BACKDROP IS ASSERTED AGAINST WHAT THE COMPONENT AUTHORS, not against what the probe
     * resolved. This is the STRONG form of the backdrop rule, the one `EXPECTED_BACKDROP` applies to the
     * ten icons: all three nodes sit inside `Panel`, whose own `className` carries `bg-navy-900`
     * (`src/greybox/components.tsx`). A walk that stopped one ancestor early -- at `navy-800`, say --
     * would be a different defect wearing a less obvious value than Commit 4a's pure black, and the
     * sweep's weaker token-membership test would accept it. */
    const TERMINAL_OUTCOME_SURFACE = "navy-900" as const;
    const outcomeNodes = [
      { role: "panel heading", node: headingNode! },
      { role: "outcome headline", node: headlineNode! },
      { role: "reason and turn", node: reasonNode! },
    ];
    for (const { role, node } of outcomeNodes) {
      expect(
        surfaceNameOf(node.bg),
        `the terminal outcome's ${role} resolved ${node.bg}, but Panel authors ` +
          `bg-${TERMINAL_OUTCOME_SURFACE}`,
      ).toBe(TERMINAL_OUTCOME_SURFACE);
      expect(
        node.ratio,
        `the terminal outcome's ${role} measures ${node.ratio}:1 on ${TERMINAL_OUTCOME_SURFACE}, below ` +
          `the ${TEXT_CONTRAST_MINIMUM}:1 bar of WCAG 2.2 SC 1.4.3`,
      ).toBeGreaterThanOrEqual(TEXT_CONTRAST_MINIMUM);
    }

    // Both rejection rules must be shown to have run on this screen: a rule that excludes nothing is a
    // rule that is not running, and this is the screen whose emptiness was previously misread.
    expect(
      terminalScreenScan!.rejectedNoOwnText,
      "the own-text rule rejected nothing on the terminal screen, so it is not running",
    ).toBeGreaterThan(0);

    // THE PROBE IS CALIBRATED BEFORE ITS FIGURES ARE TRUSTED, grouped by resolved surface -- the form
    // Commit 5 gave the N1-N6 calibration after a hard-coded navy-900 expectation failed at 5.57 on a
    // node that legitimately sits on navy-950.
    const calibrationNodes = all.filter(
      (m) => m.classes.includes(CALIBRATION.className) && m.ratio > 0,
    );
    const calibrationGroups = [...new Set(calibrationNodes.map((m) => m.bg))].map((bg) => {
      const surface = surfaceNameOf(bg);
      const nodes = calibrationNodes.filter((m) => m.bg === bg);
      return {
        backdrop: bg,
        surface: surface ?? `NOT A PALETTE SURFACE (${bg})`,
        nodes: nodes.length,
        measuredRatios: [...new Set(nodes.map((m) => m.ratio))],
        offlineExpected:
          surface === null
            ? null
            : offlineRatio({ foreground: "parchment-200", backdrop: surface, alpha: 0.6 }),
      };
    });
    expect(
      calibrationGroups.length,
      `at least one ${CALIBRATION.className} node must exist to calibrate the probe`,
    ).toBeGreaterThan(0);
    for (const group of calibrationGroups) {
      expect(
        group.offlineExpected,
        `a ${CALIBRATION.className} node resolved a backdrop outside the palette (${group.backdrop})`,
      ).not.toBeNull();
      for (const measured of group.measuredRatios) {
        expect(
          Math.abs(measured - group.offlineExpected!),
          `the probe measured ${CALIBRATION.className} at ${measured}:1 on ${group.surface} where the ` +
            `offline model gives ${group.offlineExpected}:1`,
        ).toBeLessThanOrEqual(RATIO_TOLERANCE);
      }
    }

    // Every backdrop must be an authored surface -- the weaker, sweep-wide form of the rule above. Pure
    // black is not among them, which is the bug that actually happened.
    const foreignBackdrops = [...new Set(all.filter((m) => m.ratio > 0).map((m) => m.bg))].filter(
      (bg) => surfaceNameOf(bg) === null,
    );
    expect(
      foreignBackdrops,
      "every resolved backdrop must be one of the palette's authored surfaces",
    ).toEqual([]);

    // Nothing may be left UNMEASURED: an unparseable colour is a hole in the evidence, not a pass.
    expect(
      all.filter((m) => m.ratio === -1).map((m) => `${m.selector}: ${m.rawColor}`),
      "every measured element must be measurable; an unparseable colour is a broken probe",
    ).toEqual([]);

    for (const s of perScreen) {
      expect(
        s.belowBar,
        `${s.screen}: these elements measure below ${TEXT_CONTRAST_MINIMUM}:1 in a CONCLUDED campaign`,
      ).toEqual([]);
    }

    record.n6 = {
      finding: "N6",
      status: "RESOLVED BY MEASUREMENT in the state where it exists",
      bar: `${TEXT_CONTRAST_MINIMUM}:1, WCAG 2.2 SC 1.4.3`,
      whyItCouldNotBeMeasuredBefore:
        "The terminal OUTCOME renders only once `terminal` is non-null. Every earlier audit ran " +
        "mid-campaign, where this screen shows a still-active placeholder instead -- and Commit 3's " +
        "contrast selector (`main [aria-hidden], main span, main text`) additionally matched NOTHING " +
        "on it, because the placeholder is built from an h2, two Panel headings, two paragraphs and " +
        "two buttons. So 'no text-bearing element was present' described the selector, not the DOM.",
      terminalOutcomeNodes: outcomeNodes.map(({ role, node }) => ({
        role,
        selector: node.selector,
        text: node.text,
        ratio: node.ratio,
        authoredSurface: TERMINAL_OUTCOME_SURFACE,
        resolvedSurface: surfaceNameOf(node.bg),
        alpha: node.alpha,
        normalised: node.normalised,
        fontPx: node.fontPx,
      })),
      anchoring:
        "The three outcome nodes are identified by strings the SERVER projected (`terminal.headline`, " +
        "`terminal.reason_label`, and the bucket heading), never by layout position, so the assertion " +
        "proves the measured text IS the outcome rather than something that resembles it. Their " +
        "backdrop is asserted against what `Panel` authors (bg-navy-900) rather than against what the " +
        "probe resolved -- the strong form of the rule, which the sweep-wide token-membership test " +
        "below is deliberately weaker than.",
      calibration: { className: CALIBRATION.className, tolerance: RATIO_TOLERANCE, groups: calibrationGroups },
      perScreen,
      unreachableScreens: unreachable,
    };

    // ================= TERMINAL-STATE REFLOW =================
    const conformance: { screen: string; overflow: string[]; scrolls: boolean }[] = [];
    await page.setViewportSize({ width: CONFORMANCE.width, height: CONFORMANCE.height });
    for (const screen of SCREENS) {
      if (!(await visit(page, screen)).ok) continue;
      const scrolls = await pageScrollsHorizontally(page);
      const overflow = await overflowingNodes(page);
      conformance.push({ screen, overflow, scrolls });
      expect(
        scrolls,
        `${screen} must not scroll horizontally at ${CONFORMANCE.width}px in a CONCLUDED campaign`,
      ).toBe(false);
      expect(
        overflow,
        `${screen} must have no overflowing node at ${CONFORMANCE.width}px in a CONCLUDED campaign`,
      ).toEqual([]);
    }

    // BELOW the floor: measured so the evidence survives, NEVER asserted. 195px is narrower than the
    // 320px the standard requires, and treating it as conformance would invent a bar.
    const belowFloor: { screen: string; overflow: string[]; scrolls: boolean }[] = [];
    await page.setViewportSize({ width: BELOW_FLOOR.width, height: BELOW_FLOOR.height });
    for (const screen of SCREENS) {
      if (!(await visit(page, screen)).ok) continue;
      belowFloor.push({
        screen,
        overflow: await overflowingNodes(page),
        scrolls: await pageScrollsHorizontally(page),
      });
    }
    await page.setViewportSize({ width: 1440, height: 900 });

    record.reflow = {
      conformance: {
        viewport: CONFORMANCE,
        asserted: true,
        standard: "WCAG 2.2 SC 1.4.10 Reflow, whose conformance width is 320 CSS px",
        whyItCouldNotBeMeasuredBefore:
          "The existing 320px sweep does visit this screen, so it has been reflowing the still-active " +
          "PLACEHOLDER. A concluded campaign changes three screens: the terminal outcome itself, the " +
          "Dashboard's 'campaign has ended' panel, and Decisions -- which takes an early return that " +
          "replaces the whole composer, so its 320px layout in this state is a different layout that " +
          "had never been measured.",
        screens: conformance,
      },
      belowFloor: { viewport: BELOW_FLOOR, asserted: false, screens: belowFloor },
    };

    // ================= AXE ON THE CONCLUDED SCREENS =================
    // Included because N6 IS an axe `incomplete`: resolving it means answering the question axe
    // declined to answer, on the screen in the state where it exists.
    const axe: {
      screen: string;
      violations: { id: string; impact: string; nodes: number }[];
      incomplete: { id: string; nodes: number }[];
      rulesEvaluated: number;
    }[] = [];
    for (const screen of SCREENS) {
      if (!(await visit(page, screen)).ok) continue;
      const results = await new AxeBuilder({ page }).analyze();
      // ANTI-VACUITY: an empty `violations` array means nothing unless rules actually ran.
      const rulesEvaluated =
        results.violations.length + results.passes.length + results.incomplete.length +
        results.inapplicable.length;
      expect(rulesEvaluated, `axe must have evaluated rules on ${screen}`).toBeGreaterThan(0);
      axe.push({
        screen,
        violations: results.violations.map((v) => ({
          id: v.id,
          impact: String(v.impact ?? "unknown"),
          nodes: v.nodes.length,
        })),
        incomplete: results.incomplete.map((v) => ({ id: v.id, nodes: v.nodes.length })),
        rulesEvaluated,
      });
    }
    /* EVERY axe `incomplete` GETS A DISPOSITION, because leaving one unmentioned is exactly how N6
     * survived two commits. axe returns `incomplete` when it declines to judge -- for `color-contrast`
     * that means it could not determine a background because elements overlap -- and a needs-review is
     * a question, never a verdict. This run answers each one on the same screen, in the same state, with
     * its own contrast measurement: the probe walks ancestors for the first painted background, which is
     * the step axe skips. An incomplete on a screen this run did NOT measure would be a gap, and is
     * recorded as one rather than passed over. */
    const incompleteDisposition = axe.flatMap((entry) =>
      entry.incomplete.map((item) => {
        const measured = perScreen.find((p) => p.screen === entry.screen);
        return {
          screen: entry.screen,
          rule: item.id,
          nodes: item.nodes,
          disposition:
            measured === undefined || measured.measured === 0
              ? "NOT dispositioned: this run measured no text on that screen, so the question stays open"
              : `answered by this run's own measurement: ${measured.measured} element(s) owning painted ` +
                `text on this screen, worst ratio ${measured.worstRatio}:1 on ${measured.worstSurface}, ` +
                `against a ${TEXT_CONTRAST_MINIMUM}:1 bar, with the effective background resolved by ` +
                `ancestor walk -- the step axe declines when elements overlap`,
        };
      }),
    );
    expect(
      incompleteDisposition.filter((d) => d.disposition.startsWith("NOT dispositioned")),
      "every axe needs-review result must be answered by a measurement on the same screen in the same " +
        "state; an unanswered one is how N6 stayed open for two commits",
    ).toEqual([]);

    record.axe = {
      method: "@axe-core/playwright against the running application, on a CONCLUDED campaign",
      antiVacuity:
        "Each screen records `rulesEvaluated` and the run asserts it non-zero, so an empty violation " +
        "list can never be read as clean when in fact no rule ran.",
      screens: axe,
      violationTotal: axe.reduce((n, s) => n + s.violations.length, 0),
      incompleteDisposition,
    };
    expect(
      axe.flatMap((s) => s.violations.map((v) => `${s.screen}: ${v.id} (${v.impact})`)),
      "a concluded campaign must introduce no axe violation",
    ).toEqual([]);

    (record.coverage as string[]).push(
      `N6: ${all.length} elements owning painted text measured across ${perScreen.length} screens of a ` +
        `CONCLUDED campaign; the terminal outcome's own three nodes measured at ` +
        `${outcomeNodes.map(({ node }) => `${node.ratio}:1`).join(", ")} against a ` +
        `${TEXT_CONTRAST_MINIMUM}:1 bar, each on its authored bg-${TERMINAL_OUTCOME_SURFACE}`,
      `Terminal reflow: ${conformance.length} screens clean at ${CONFORMANCE.width}px (ASSERTED); ` +
        `${belowFloor.reduce((n, s) => n + s.overflow.length, 0)} overflow observation(s) at ` +
        `${BELOW_FLOOR.width}px (RECORDED, below the WCAG floor, never asserted)`,
      `Campaign: ${resolved} turns resolved to reach ${terminal.bucket} at turn ${terminal.turn} ` +
        `(${terminal.reason_label}); pinned, with a cap of ${RESOLVE_CAP}`,
    );
  });

  test.afterAll(() => {
    mkdirSync(REVIEW_DIR, { recursive: true });
    record.surfaces = SURFACES;
    writeFileSync(path.join(REVIEW_DIR, `${OUT_NAME}.json`), `${JSON.stringify(record, null, 2)}\n`);
  });
});
