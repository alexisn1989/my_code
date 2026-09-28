/**
 * Gate 4A3 Commit 4a — ALL TEN ICONS, MEASURED AT THEIR OWN PLACEMENTS.
 *
 * WHAT COMMIT 4 LEFT OPEN. It measured seven of ten marks in the browser and recorded `negative`,
 * `caution` and `unchanged` as "not reached, with reasons". That was an honest disposition and a real
 * evidence gap: three of ten had no measurement where they actually render, and the mitigation offered
 * for them — their tokens were measured as TEXT by Commit 3 — is evidence about a token, not about a
 * placement.
 *
 * ALL THREE ARE REACHABLE IN SHIPPED CONTENT. No fixture scenario is authored, and no state is
 * invented:
 *
 *   `unchanged`  Every constitutional-amendment card family hard-codes `direction="unchanged"` on its
 *                effects (`backend/app/api/policy_cards.py:548,579,586,642,674`), present at turn 0 in
 *                every scenario. Commit 4 missed them only because it never activated a policy-card
 *                tab: the default-open Taxation family is the one family that is always `up`/`down`.
 *   `negative`   In `deficit_demo`, raising personal income from the authored 1500 bps to 2000 — the
 *                `tax_personal_income_increase` card's own template — tallies 47 against a required 51,
 *                so `carries` and `would_pass` both go false. Commit 4 previewed an EMPTY draft, which
 *                produces no chamber rows and no "Would pass" line at all.
 *   `caution`    The Survival concern card is caution iff `coup.attempt_risk_bps > 0`
 *                (`projections.py:1586`), and `BASE_COUP_ATTEMPT_RISK_BPS = 8` is added before the
 *                clamp (`government_survival.py:317`), so it is ALWAYS >= 8. At turn 0 there is no
 *                report, so the card reads "Not yet assessed". One resolved turn makes it certain.
 *
 * The other `caution` producer, the Legitimacy card at `legitimacy_bps < 5_000`, is effectively
 * unreachable in shipped play — legitimacy drifts UP toward `constitutional_order_support_bps`, and the
 * capped downward channels put `deficit_demo`'s fixed point at exactly 5000 against a strict `<`. A
 * fixture could force it and that route was REJECTED: it would depict a state the game cannot produce,
 * where the survival card is the real one.
 *
 * WHY ITS OWN SERVER. This spec RESOLVES A TURN, and the shared config server holds one process-wide
 * `GameSession` (`playwright.config.ts`), so a resolve here would leak into whatever ran next. It
 * spawns its own against the REAL scenario root with its own save root — the
 * `stress-seated-cabinet.spec.ts` pattern, for the same reason.
 *
 * THE DIFFERENCE FROM COMMIT 4'S TEST, and the point of this commit: `notReached` must be EMPTY.
 */

import { execFileSync, spawn, type ChildProcess } from "node:child_process";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

import {
  CALIBRATION,
  CHANNEL_TOLERANCE,
  EXPECTED_BACKDROP,
  FOREGROUNDS,
  NON_TEXT_CONTRAST_MINIMUM,
  RATIO_TOLERANCE,
  SURFACES,
  installColourProbe,
  offlineRatio,
  type ForegroundName,
} from "./contrast-probe";

const REVIEW_DIR = path.join(process.cwd(), "..", "docs", "reviews");
const SCENARIO_ROOT = path.join(process.cwd(), "..", "data", "scenarios");

/** `deficit_demo`, chosen for stated reasons rather than by taking the first Start button: it is the
 * only shipped scenario with a negative pre-financing balance under no decisions (-458,800,000, its own
 * header records the derivation), it has the failing 47-vs-51 tax tally, and its 300 opening capital
 * makes unaffordability cheap if it is ever needed.
 *
 * The BUTTON LABEL is read from the API rather than retyped. `Start ${scenario.display_name}` uses the
 * projected display name, which for this scenario is the COUNTRY -- "Republic of Strapped" -- not the
 * file's own `name:` ("Deficit Demo Fixture"). A hard-coded label was wrong on the first run for
 * exactly that reason, and reading it from the source of truth means a content rename changes what the
 * spec looks for instead of breaking it silently. */
const SCENARIO_ID = "deficit_demo";

/** Every icon the set declares. The run must account for each one as MEASURED. */
const EVERY_ICON = [
  "positive",
  "negative",
  "caution",
  "neutral",
  "up",
  "down",
  "unchanged",
  "route-one-way",
  "route-two-way",
  "capital",
] as const;

type IconName = (typeof EVERY_ICON)[number];

interface Measurement {
  icon: string;
  group: string;
  /** Which authored placement this icon sits in -- the key into `EXPECTED_BACKDROP`. */
  placement: string;
  ratio: number;
  strokeWidth: string;
  rawColor: string;
  /** The probe's normalised foreground, before compositing. */
  normalised: string;
  alpha: number;
  /** The backdrop the probe RESOLVED. Compared against the authored expectation, never trusted. */
  bg: string;
  screen: string;
  classes: string;
}

function toRgbString(hex: string): string {
  const h = hex.replace("#", "");
  return `rgb(${parseInt(h.slice(0, 2), 16)},${parseInt(h.slice(2, 4), 16)},${parseInt(h.slice(4, 6), 16)})`;
}

function surfaceNameOf(rgb: string): string | null {
  const hit = Object.entries(SURFACES).find(([, hex]) => toRgbString(hex) === rgb);
  return hit ? hit[0] : null;
}

/** Which authored foreground token a normalised sRGB triple is, within the channel tolerance. */
function foregroundNameOf(normalised: string): ForegroundName | null {
  const m = /^rgb\((\d+),(\d+),(\d+)\)$/.exec(normalised);
  if (m === null) return null;
  const got = [Number(m[1]), Number(m[2]), Number(m[3])];
  for (const [name, hex] of Object.entries(FOREGROUNDS)) {
    const h = hex.replace("#", "");
    const want = [
      parseInt(h.slice(0, 2), 16),
      parseInt(h.slice(2, 4), 16),
      parseInt(h.slice(4, 6), 16),
    ];
    if (want.every((w, i) => Math.abs(w - got[i]!) <= CHANNEL_TOLERANCE)) return name as ForegroundName;
  }
  return null;
}

function freePort(): number {
  const script =
    "const s=require('node:net').createServer();" +
    "s.listen(0,'127.0.0.1',()=>{const a=s.address();" +
    "process.stdout.write(String(typeof a==='object'&&a?a.port:0));s.close();});";
  return Number(execFileSync(process.execPath, ["-e", script], { encoding: "utf-8" }).trim());
}

let server: ChildProcess | null = null;
let base = "";

test.afterAll(() => {
  server?.kill("SIGINT");
});

/** Measure every visible `svg[data-icon]` on the current screen, tagging each with its PLACEMENT. */
async function measureIcons(page: Page, screen: string): Promise<Measurement[]> {
  return page.evaluate((screenName: string) => {
    const { normalise, ratio, effectiveBg, composite, isVisuallyHidden } = (
      window as unknown as {
        __mandateColour: {
          normalise: (colour: string) => number[];
          ratio: (fg: number[], bg: number[]) => number;
          effectiveBg: (el: Element) => number[];
          composite: (fg: number[], bg: number[], alpha: number) => number[];
          isVisuallyHidden: (el: Element) => boolean;
        };
      }
    ).__mandateColour;

    /* PLACEMENT comes from a NAMED CONTAINER, never from the backdrop the probe found -- that
     * independence is what lets the authored expectation be checked against the measurement. An icon
     * in none of these containers is tagged `unknown`, which fails the run rather than being
     * attributed to a guess. */
    const placementOf = (el: Element): string => {
      if (el.closest('[data-testid="concern-cards"]') !== null) return "dashboard-concern";
      if (el.closest('[data-testid="strategic-map-legend"]') !== null) return "map-legend";
      if (el.closest('[data-testid="turn-result-view"]') !== null) return "turn-result";
      if (el.closest('[data-testid="consequences-panel"]') !== null) return "preview-panel";
      if (el.closest('[role="tabpanel"]') !== null) return "policy-card";
      return "unknown";
    };
    const groupOf = (name: string): string =>
      name === "route-one-way" || name === "route-two-way" || name === "capital"
        ? "map-legend"
        : name === "up" || name === "down" || name === "unchanged"
          ? "direction"
          : "tone";

    const out: Record<string, unknown>[] = [];
    for (const el of Array.from(document.querySelectorAll("svg[data-icon]"))) {
      if (isVisuallyHidden(el)) continue;
      const name = el.getAttribute("data-icon") ?? "(unnamed)";
      const style = getComputedStyle(el);
      const parsed = normalise(style.color);
      const bg = effectiveBg(el);
      const alpha = parsed[3] ?? Number.NaN;
      const bgString = `rgb(${bg[0]},${bg[1]},${bg[2]})`;
      if (!Number.isFinite(parsed[0]) || !Number.isFinite(alpha)) {
        out.push({
          icon: name,
          group: groupOf(name),
          placement: placementOf(el),
          ratio: -1, // UNMEASURED, never "measured as bad".
          strokeWidth: style.strokeWidth,
          rawColor: style.color,
          normalised: "UNPARSEABLE",
          alpha: -1,
          bg: bgString,
          screen: screenName,
          classes: (el.parentElement?.className ?? "").toString().slice(0, 80),
        });
        continue;
      }
      const fgTriple = [parsed[0]!, parsed[1]!, parsed[2]!];
      const fg = alpha < 1 ? composite(fgTriple, bg, alpha) : fgTriple;
      out.push({
        icon: name,
        group: groupOf(name),
        placement: placementOf(el),
        ratio: Math.round(ratio(fg, bg) * 100) / 100,
        strokeWidth: style.strokeWidth,
        rawColor: style.color,
        normalised: `rgb(${fgTriple[0]},${fgTriple[1]},${fgTriple[2]})`,
        alpha,
        bg: bgString,
        screen: screenName,
        classes: (el.parentElement?.className ?? "").toString().slice(0, 80),
      });
    }
    return out as unknown as Measurement[];
  }, screen);
}

async function visit(page: Page, screen: string): Promise<boolean> {
  const control = page.getByRole("button", { name: screen, exact: true }).first();
  if (!(await control.isVisible().catch(() => false))) return false;
  if (await control.isDisabled().catch(() => true)) return false;
  await control.click();
  await page.waitForTimeout(250);
  return true;
}

test.describe("Gate 4A3 Commit 4a — ten-icon coverage", () => {
  test.describe.configure({ mode: "serial" });

  test("the colour probe parses every spelling a browser can hand it", async ({ page }) => {
    test.setTimeout(120_000);
    await installColourProbe(page);
    await page.goto("about:blank");

    /* THE REGRESSION GUARD FOR THE BUG THIS COMMIT FIXED, run against the probe as actually installed
     * in a page rather than against a copy of its source. `getComputedStyle().backgroundColor` returns
     * the LEGACY COMMA form for a transparent background -- `rgba(0, 0, 0, 0)` -- and the probe used to
     * read alpha only after a slash, so it saw opaque black and `effectiveBg` stopped at the first
     * transparent ancestor. Every ratio Commits 3 and 4 recorded was inflated as a result. */
    const parsed = await page.evaluate(() => {
      const { normalise } = (
        window as unknown as { __mandateColour: { normalise: (c: string) => number[] } }
      ).__mandateColour;
      return {
        legacyTransparent: normalise("rgba(0, 0, 0, 0)"),
        legacyOpaque: normalise("rgba(15, 22, 38, 1)"),
        legacyNoAlpha: normalise("rgb(15, 22, 38)"),
        modernSlash: normalise("rgb(0 0 0 / 0)"),
        legacyRealAlpha: normalise("rgba(232, 220, 192, 0.8)"),
        oklabSlash: normalise("oklab(0.896735 0.00171477 0.0394163 / 0.6)"),
        hex: normalise("#e8dcc0"),
        nonsense: normalise("not-a-colour"),
      };
    });

    expect(
      parsed.legacyTransparent,
      "rgba(0, 0, 0, 0) is what a transparent background serializes to; reading its alpha as 1 is the " +
        "bug that made every backdrop pure black",
    ).toEqual([0, 0, 0, 0]);
    expect(parsed.legacyOpaque).toEqual([15, 22, 38, 1]);
    expect(parsed.legacyNoAlpha).toEqual([15, 22, 38, 1]);
    expect(parsed.modernSlash).toEqual([0, 0, 0, 0]);
    expect(parsed.legacyRealAlpha).toEqual([232, 220, 192, 0.8]);
    // The OKLab conversion must land on the authored token within the channel tolerance -- NOT
    // "exactly", because CSS Color 4 does not require serialization to preserve component text.
    for (const [i, want] of [232, 220, 192].entries()) {
      expect(Math.abs(parsed.oklabSlash[i]! - want)).toBeLessThanOrEqual(CHANNEL_TOLERANCE);
    }
    expect(parsed.oklabSlash[3]).toBeCloseTo(0.6, 6);
    expect(parsed.hex).toEqual([232, 220, 192, 1]);
    // An unrecognised colour must stay NON-FINITE so the caller reports UNMEASURED rather than
    // silently substituting a plausible value.
    expect(parsed.nonsense.every((v) => !Number.isFinite(v))).toBe(true);
  });

  test("every one of the ten icons is measured at its own placement, at or above 3:1", async ({
    page,
  }) => {
    test.setTimeout(900_000);
    await installColourProbe(page);

    // ---- its own server, against the REAL scenario root ----
    const saveRoot = mkdtempSync(path.join(tmpdir(), "mandate-icon-coverage-"));
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

    const scenarios = (await page.request.get(`${base}/api/scenarios`).then((r) => r.json())) as {
      scenario_id: string;
      display_name: string;
    }[];
    const scenario = scenarios.find((s) => s.scenario_id === SCENARIO_ID);
    expect(scenario, `${SCENARIO_ID} must be present in the real scenario root`).toBeDefined();
    const startLabel = `Start ${scenario!.display_name}`;

    await page.goto(`${base}/`);
    const start = page.getByRole("button", { name: startLabel });
    await start.waitFor({ state: "visible", timeout: 30_000 });
    await start.click();
    const startResponse = await page.waitForResponse(
      (r) => r.url().includes("/api/game/state") && r.status() === 200,
      { timeout: 30_000 },
    );
    expect(startResponse.ok(), "the campaign must actually start").toBe(true);
    await page.waitForTimeout(400);

    const all: Measurement[] = [];
    const coverage: string[] = [];

    // ================= STAGE 1: turn 0, the six Commit 4 already reached =================
    for (const screen of ["Dashboard", "Strategic map", "Decisions"]) {
      if (!(await visit(page, screen))) continue;
      if (screen === "Strategic map") {
        // The legend is a collapsed <details>. Commit 4 measured it closed (the probe's
        // `isVisuallyHidden` only excludes `.sr-only`), but opening it is what a player does and makes
        // the measurement one about painted pixels rather than about a hidden subtree.
        const summary = page.getByText("Map legend", { exact: true });
        if (await summary.isVisible().catch(() => false)) {
          await summary.click();
          await page.waitForTimeout(200);
        }
      }
      const found = await measureIcons(page, screen);
      all.push(...found);
      coverage.push(`${screen}: ${found.length} icon(s)`);
    }

    // ================= STAGE 2: `unchanged`, from the amendment cards =================
    // Server-side precondition FIRST: the projection must really carry an `unchanged` effect, or a
    // clean DOM result would prove nothing about this icon.
    const options = await page.request.get(`${base}/api/game/decision-options`).then((r) => r.json());
    const unchangedEffects = ((options.policy_cards ?? []) as {
      card_id: string;
      effects?: { direction: string }[[]] | { direction: string }[];
    }[]).filter((card) => (card.effects ?? []).some((e) => e.direction === "unchanged"));
    expect(
      unchangedEffects.length,
      "the decision-options projection must carry at least one policy-card effect with " +
        "direction=unchanged, or there is nothing for the DOM to render",
    ).toBeGreaterThan(0);
    coverage.push(
      `server projection carries ${unchangedEffects.length} card(s) with an unchanged-direction effect`,
    );

    expect(await visit(page, "Decisions")).toBe(true);
    const constitutionTab = page.getByRole("tab", { name: /^Constitutional reform/ });
    await constitutionTab.waitFor({ state: "visible", timeout: 15_000 });
    await constitutionTab.click();
    await page.waitForTimeout(300);
    const amendmentIcons = await measureIcons(page, "Decisions (Constitutional reform)");
    expect(
      amendmentIcons.some((i) => i.icon === "unchanged"),
      "the Constitutional reform panel must render at least one `unchanged` mark",
    ).toBe(true);
    all.push(...amendmentIcons);
    coverage.push(
      `Decisions / Constitutional reform: ${amendmentIcons.length} icon(s), including ` +
        `${amendmentIcons.filter((i) => i.icon === "unchanged").length} unchanged`,
    );

    // ================= STAGE 3: `negative`, from a FAILING preview =================
    const taxationTab = page.getByRole("tab", { name: /^Budget policy/ });
    await taxationTab.click();
    await page.waitForTimeout(250);
    const taxTab = page.getByRole("tab", { name: /^Taxation/ });
    if (await taxTab.isVisible().catch(() => false)) {
      await taxTab.click();
      await page.waitForTimeout(250);
    }
    // The personal-income-increase card: its own template is the authored 1500 bps + 5pp, which is
    // exactly the proposal that tallies 47 against a required 51 in this scenario.
    const raiseCard = page
      .getByRole("group")
      .filter({ hasText: /personal income/i })
      .first();
    await raiseCard.waitFor({ state: "visible", timeout: 15_000 });
    await raiseCard.getByRole("button", { name: "Select" }).click();
    await page.waitForTimeout(300);

    const previewButton = page.getByRole("button", { name: "Preview" }).first();
    await previewButton.click();
    const previewResponse = await page.waitForResponse(
      (r) => r.url().includes("/api/game/preview") && r.status() === 200,
      { timeout: 30_000 },
    );
    const preview = await previewResponse.json();
    // Server-side precondition: the preview must REALLY be a failing one.
    expect(preview.has_proposal, "the preview must carry a proposal").toBe(true);
    expect(
      preview.would_pass,
      "the selected card must produce a FAILING vote, or `negative` has nothing to render from",
    ).toBe(false);
    expect(
      (preview.chambers ?? []).some((c: { carries: boolean }) => !c.carries),
      "at least one chamber must fail to carry",
    ).toBe(true);
    coverage.push(
      `preview: has_proposal=true, would_pass=false, ` +
        `${(preview.chambers ?? []).filter((c: { carries: boolean }) => !c.carries).length} chamber(s) ` +
        `not carrying`,
    );
    await page.waitForTimeout(500);
    const previewIcons = await measureIcons(page, "Decisions (preview, failing vote)");
    expect(
      previewIcons.some((i) => i.icon === "negative"),
      "a failing preview must render at least one `negative` mark",
    ).toBe(true);
    all.push(...previewIcons);
    coverage.push(`Decisions / preview: ${previewIcons.length} icon(s)`);

    // ================= STAGE 4: `caution`, after one resolved turn =================
    const resolveButton = page.getByRole("button", { name: "Resolve turn" });
    await resolveButton.click();
    const confirm = page.getByRole("button", { name: "Confirm and resolve" });
    await confirm.waitFor({ state: "visible", timeout: 15_000 });
    await confirm.click();
    const resolved = await page.waitForResponse(
      (r) => r.url().includes("/api/game/resolve") && r.status() === 200,
      { timeout: 120_000 },
    );
    expect(resolved.ok(), "the turn must actually resolve").toBe(true);
    await page.waitForTimeout(1_200);

    // Server-side precondition: the dashboard must REALLY carry a caution tone and a negative tone.
    const state = await page.request.get(`${base}/api/game/state`).then((r) => r.json());
    const concerns = (state.concerns ?? {}) as Record<string, { label: string; tone: string }>;
    const tones = Object.values(concerns).map((c) => c.tone);
    expect(
      tones,
      "after one resolved turn the Survival card must be caution (base coup risk is always >= 8 bps)",
    ).toContain("caution");
    expect(
      tones,
      "deficit_demo's pre-financing balance is -458,800,000, so the Money card must be negative",
    ).toContain("negative");
    coverage.push(
      `after one resolved turn the dashboard concerns are: ` +
        Object.values(concerns)
          .map((c) => `${c.label}=${c.tone}`)
          .join(", "),
    );

    for (const screen of ["Turn result", "Dashboard"]) {
      if (!(await visit(page, screen))) continue;
      const found = await measureIcons(page, `${screen} (turn 1)`);
      all.push(...found);
      coverage.push(`${screen} after the resolve: ${found.length} icon(s)`);
    }

    // ================= THE ASSERTIONS =================

    // Nothing unparseable. A colour the probe cannot read is a hole in the evidence, not a pass.
    expect(
      all.filter((m) => m.ratio === -1).map((m) => `${m.icon}: ${m.rawColor}`),
      "an unparseable colour is a broken probe, not a passing icon",
    ).toEqual([]);

    // Every icon must be attributable to a NAMED placement.
    expect(
      all.filter((m) => m.placement === "unknown").map((m) => `${m.icon} on ${m.screen}: ${m.classes}`),
      "every measured icon must sit in a named container, so its authored backdrop is a fact",
    ).toEqual([]);

    // Every icon must be one the set declares.
    expect(
      [...new Set(all.map((m) => m.icon))].filter((n) => !EVERY_ICON.includes(n as IconName)),
      "an unknown `data-icon` is drift between the icon set and its consumers",
    ).toEqual([]);

    // 2px stroke, since that is the premise the 3:1 bar is applied under.
    expect(
      all.filter((m) => parseFloat(m.strokeWidth) !== 2).map((m) => `${m.icon}: ${m.strokeWidth}`),
      "every icon is specified at a 2px stroke; a thinner one would change which WCAG bar applies",
    ).toEqual([]);

    // THE BACKDROP, asserted against the AUTHORED expectation for that placement -- never accepted
    // from the probe. This is the assertion the pure-black parser bug would have failed immediately.
    const backdropProblems: string[] = [];
    for (const m of all) {
      const expectedSurface = EXPECTED_BACKDROP[m.placement];
      if (expectedSurface === undefined) {
        backdropProblems.push(`${m.placement} has no authored expectation`);
        continue;
      }
      const wanted = toRgbString(SURFACES[expectedSurface]);
      if (m.bg !== wanted) {
        backdropProblems.push(
          `${m.icon} in ${m.placement} on ${m.screen}: probe resolved ${m.bg} ` +
            `(${surfaceNameOf(m.bg) ?? "not a palette surface"}), authored ${expectedSurface} ${wanted}`,
        );
      }
    }
    expect(
      backdropProblems,
      "each icon's resolved backdrop must equal the surface its placement authors; a mismatch means " +
        "either the ancestor walk is wrong or EXPECTED_BACKDROP is stale, and both must stop the run",
    ).toEqual([]);

    // THE INDEPENDENCE CHECK: each ratio recomputed from AUTHORED values -- the token hex, the alpha,
    // and the backdrop the placement authors -- never from the probe's own numbers.
    const reconciliation: {
      icon: string;
      placement: string;
      screen: string;
      measured: number;
      offline: number;
      token: string;
      alpha: number;
    }[] = [];
    const ratioProblems: string[] = [];
    for (const m of all) {
      const token = foregroundNameOf(m.normalised);
      if (token === null) {
        ratioProblems.push(
          `${m.icon} in ${m.placement}: normalised ${m.normalised} matches no authored token within ` +
            `${CHANNEL_TOLERANCE} per channel (raw ${m.rawColor})`,
        );
        continue;
      }
      const expected = offlineRatio({
        foreground: token,
        backdrop: EXPECTED_BACKDROP[m.placement]!,
        alpha: m.alpha,
      });
      reconciliation.push({
        icon: m.icon,
        placement: m.placement,
        screen: m.screen,
        measured: m.ratio,
        offline: expected,
        token,
        alpha: m.alpha,
      });
      if (Math.abs(m.ratio - expected) > RATIO_TOLERANCE) {
        ratioProblems.push(
          `${m.icon} in ${m.placement} on ${m.screen}: probe ${m.ratio}:1, offline ${expected}:1 ` +
            `(${token} at alpha ${m.alpha} on ${EXPECTED_BACKDROP[m.placement]})`,
        );
      }
    }
    expect(
      ratioProblems,
      `every measured ratio must agree with an offline computation from AUTHORED values within ` +
        `${RATIO_TOLERANCE}. A gap is a probe finding to explain, never grounds for widening this`,
    ).toEqual([]);

    // THE BAR.
    expect(
      all
        .filter((m) => m.ratio < NON_TEXT_CONTRAST_MINIMUM)
        .map((m) => `${m.icon} (${m.group}) at ${m.ratio}:1 in ${m.placement}`),
      `every icon must clear ${NON_TEXT_CONTRAST_MINIMUM}:1 at its own placement (WCAG 2.2 SC 1.4.11)`,
    ).toEqual([]);

    // AND THE POINT OF THIS COMMIT: all ten reached. Commit 4's test allowed a recorded gap; this one
    // does not.
    const reached = new Set(all.map((m) => m.icon));
    const notReached = EVERY_ICON.filter((n) => !reached.has(n));
    expect(
      notReached,
      "every icon the set declares must be MEASURED at a real placement; a recorded reason is what " +
        "Commit 4 had and what this commit exists to replace",
    ).toEqual([]);

    // ---- the record ----
    const perIcon = EVERY_ICON.map((name) => {
      const rows = all.filter((m) => m.icon === name);
      const worst = rows.reduce((a, b) => (a.ratio <= b.ratio ? a : b));
      return {
        icon: name,
        group: worst.group,
        placements: [...new Set(rows.map((r) => r.placement))].sort(),
        screens: [...new Set(rows.map((r) => r.screen))].sort(),
        occurrences: rows.length,
        worstRatio: worst.ratio,
        token: foregroundNameOf(worst.normalised),
        alpha: worst.alpha,
        backdrop: worst.bg,
        backdropSurface: surfaceNameOf(worst.bg),
        offlineExpected: reconciliation.find((r) => r.icon === name)?.offline ?? null,
        clearsBar: worst.ratio >= NON_TEXT_CONTRAST_MINIMUM,
      };
    });

    mkdirSync(REVIEW_DIR, { recursive: true });
    writeFileSync(
      path.join(REVIEW_DIR, "gate-4a3-commit4a-icon-coverage.json"),
      JSON.stringify(
        {
          bar: `${NON_TEXT_CONTRAST_MINIMUM}:1, WCAG 2.2 SC 1.4.11 (a 2px stroke is a graphical object)`,
          scenario: "deficit_demo, via the real data/scenarios root, on this spec's own server",
          method:
            "Every `svg[data-icon]` in the live DOM, measured at its own placement. Placement comes " +
            "from a NAMED container, and each placement's backdrop expectation comes from the " +
            "component's authored `className` -- never from what the probe resolved. Each ratio is " +
            "then reconciled against an offline computation from authored values: the `tokens.css` " +
            "hex, the alpha, and that authored backdrop.",
          tolerances: {
            channel: CHANNEL_TOLERANCE,
            ratio: RATIO_TOLERANCE,
            fixedBeforeTheRun: true,
            note:
              "Fixed in `e2e/contrast-probe.ts` before this run. The previous calibration was a " +
              "5.2-5.7 BAND wide enough to contain navy-900 (5.45), navy-950 (5.57) and the 5.65 the " +
              "broken parser produced from a pure-black backdrop -- so it could not detect the bug.",
          },
          probeFix:
            "`numbers()` read alpha only from a slash component, so legacy `rgba(0, 0, 0, 0)` -- what " +
            "`getComputedStyle().backgroundColor` returns for a transparent background -- parsed as " +
            "OPAQUE BLACK and `effectiveBg` stopped at the first transparent ancestor. Every figure " +
            "Commits 3 and 4 recorded was inflated. Fixed in Commit 4a.",
          calibration: CALIBRATION,
          totalMeasurements: all.length,
          iconsMeasured: [...reached].sort(),
          iconsNotReached: notReached,
          perIcon,
          reconciliation,
          coverage,
          measurements: all,
        },
        null,
        2,
      ) + "\n",
      "utf-8",
    );
  });
});
