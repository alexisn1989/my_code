/**
 * Gate 4A3 (frozen-plan 4A5), Commit 2 — THE ACCESSIBILITY BASELINE.
 *
 * This file MEASURES. It does not fix, and it does not judge by failing.
 *
 * §9.1 governs, exactly as it governs Commit 1: this is a reporting run that exits 0 whenever it
 * COMPLETES, whatever it found. A non-zero exit means the harness broke, never that the application
 * has a defect. The assertions below are about COVERAGE — that every surface was really audited —
 * and never about the violation count. A zero-violation regression test belongs to Commit 3, after
 * the findings are triaged and accepted; adding one here would commit a deliberately red suite and
 * break the standing rule that nothing is committed while a gate is failing.
 *
 * WHY THE REAL BROWSER, RESTATED. axe-core's most valuable rules — `color-contrast` above all —
 * need layout, compositing and resolved styles. jsdom has none of those, so it cannot evaluate
 * them: it reports them `incomplete` at best and silently skips them at worst. That is the whole
 * reason the frozen plan put Playwright before the accessibility work rather than after. The jsdom
 * axe tests added alongside this commit (`src/greybox/a11y.components.test.tsx`) are an explicitly
 * labelled SUPPLEMENT for per-component regressions, never the primary evidence.
 *
 * THE ANTI-VACUITY GUARD, which is the lesson of Commit 1a and of the group-58 route defect.
 * An axe run that fails to inject returns an empty `violations` array, and an empty `violations`
 * array is indistinguishable from a clean screen unless something else proves the rules actually
 * ran. So every audited surface records `rulesEvaluated` — violations + passes + incomplete +
 * inapplicable — and the run asserts it is non-zero. "No violations here" is only ever recorded
 * against a surface that demonstrably evaluated rules. Commit 1 claimed a clean stress result on
 * four screens where three of them had never been stressed at all; that must not happen twice in
 * the same gate.
 *
 * THE UNIT OF A FINDING, and why it is deduplicated across viewports.
 * Most axe rules are viewport-INDEPENDENT: a missing label or a contrast failure is the same defect
 * at 1920px and at 320px. Numbering one finding per screen x viewport x rule would multiply every
 * such defect by the eight viewport cases and produce a count that says more about the sweep than
 * about the application. So a finding is one `(screen, rule, node selectors)` triple, and it
 * carries `viewports` — EVERY viewport case where it was observed. Nothing is lost: a
 * viewport-specific defect is visible precisely because its `viewports` list is short, and a
 * universal one is visible because the list is long. The count is honest at the cost of one
 * sentence of explanation.
 *
 * Findings are numbered `A1..An`. axe's "needs review" results are numbered `N1..Nn` and kept
 * SEPARATE, because an incomplete result is a question, not a defect, and folding the two together
 * would overstate the baseline.
 */

import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

import { AxeBuilder } from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import type { AxeResults, Result } from "axe-core";

const REVIEW_DIR = path.join(process.cwd(), "..", "docs", "reviews");

/** The axe-core version that produced this artifact, read off the installed package rather than
 * retyped — so the report records what actually ran instead of what someone believed was installed.
 * `package.json` pins it exactly (4.13.0), the same way `@playwright/test` is pinned. */
const AXE_VERSION: string = (
  JSON.parse(
    readFileSync(path.join(process.cwd(), "node_modules", "axe-core", "package.json"), "utf-8"),
  ) as { version: string }
).version;

/** The same eight viewport cases Commit 1 swept, so the two baselines describe one application.
 *
 * `reflow-wcag-320x512` is the CONFORMANCE width: WCAG 2.2 SC 1.4.10 requires reflow without a
 * horizontal scrollbar at 320 CSS px. `reflow200-mobile-195x422` is BELOW that floor — halving a
 * 390px phone for 200% zoom lands at 195px — so it is a real user observation and not a conformance
 * target. Commit 1 drew that line after its first run put all 35 findings below the floor, and this
 * sweep inherits it rather than re-deriving it. */
const VIEWPORTS = [
  { name: "desktop-1920x1080", width: 1920, height: 1080, conformanceWidth: true },
  { name: "laptop-1440x900", width: 1440, height: 900, conformanceWidth: true },
  { name: "narrow-820x900", width: 820, height: 900, conformanceWidth: true },
  { name: "mobile-390x844", width: 390, height: 844, conformanceWidth: true },
  { name: "reflow-wcag-320x512", width: 320, height: 512, conformanceWidth: true },
  { name: "reflow200-desktop-960x540", width: 960, height: 540, conformanceWidth: true },
  { name: "reflow200-laptop-720x450", width: 720, height: 450, conformanceWidth: true },
  { name: "reflow200-mobile-195x422", width: 195, height: 422, conformanceWidth: false },
] as const;

/** Every screen the registry offers, by nav label — Commit 1's list unchanged. The three that still
 * render `UnavailableScreen` (Economy, Legislature, Constitution) are audited too: an unavailable
 * screen is still a surface a keyboard and a screen reader reach. */
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

/** WCAG 2.2 AA is the target the frozen plan's §13 accessibility floor sets, so its tags decide
 * what counts as a CONFORMANCE finding. AAA rules and axe's own best-practice rules are recorded in
 * full but classified separately — reporting them as conformance failures would inflate the
 * baseline against a standard nobody committed to. */
const AA_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22a", "wcag22aa"];
const AAA_TAGS = ["wcag2aaa", "wcag21aaa", "wcag22aaa"];

type Conformance = "wcag-aa" | "beyond-aa" | "best-practice";

function classify(tags: string[]): Conformance {
  if (tags.some((t) => AA_TAGS.includes(t))) return "wcag-aa";
  if (tags.some((t) => AAA_TAGS.includes(t))) return "beyond-aa";
  return "best-practice";
}

interface Finding {
  id: string;
  screen: string;
  ruleId: string;
  impact: string;
  conformance: Conformance;
  wcagTags: string[];
  help: string;
  helpUrl: string;
  nodeCount: number;
  selectors: string[];
  failureSummary: string;
  viewports: string[];
}

/** One audited surface, and the proof that it WAS audited. `rulesEvaluated` is the anti-vacuity
 * number: a surface reporting zero violations and zero evaluated rules was never really measured,
 * and the run refuses to record it as clean. */
interface Surface {
  screen: string;
  viewport: string;
  rulesEvaluated: number;
  violations: number;
  passes: number;
  incomplete: number;
  inapplicable: number;
}

const findings = new Map<string, Finding>();
const incompletes = new Map<string, Finding>();
const surfaces: Surface[] = [];
/** A surface the NAVIGATION legitimately did not offer — a nav control absent or disabled. This is a
 * fact about the application, so it relaxes the coverage threshold below. */
const unreachable: { screen: string; viewport: string; reason: string }[] = [];

/** A surface where AXE ITSELF failed — injection refused, evaluation threw. This is the harness
 * breaking, not the application refusing, and the two must never share a list.
 *
 * Kept separate deliberately: while both lived in `unreachable`, an axe crash silently LOWERED the
 * coverage threshold and the run still passed, so a sweep that failed to audit half the application
 * could report success. That is the same accommodate-the-gap failure Commit 1a was written to
 * correct. Any entry here fails the run outright. */
const axeFailures: { screen: string; viewport: string; reason: string }[] = [];
const coverage: string[] = [];
let findingCounter = 0;
let incompleteCounter = 0;

/** Verbatim selectors, flattened. axe's `target` is an array because a node may live inside nested
 * frames; joining with " >>> " is axe's own convention for that and keeps the value quotable. */
function selectorsOf(result: Result): string[] {
  return result.nodes.flatMap((node) =>
    (node.target as unknown[]).map((t) => (Array.isArray(t) ? t.join(" >>> ") : String(t))),
  );
}

/** Record into the deduplicating map. The key is the DEFECT — screen, rule, and the exact nodes —
 * so the same defect seen at eight viewports is one finding with eight viewports listed, and two
 * different nodes failing one rule stay two findings. */
function record(
  into: Map<string, Finding>,
  nextId: () => string,
  screen: string,
  viewport: string,
  result: Result,
): void {
  const selectors = selectorsOf(result);
  const key = `${screen}||${result.id}||${selectors.join(",")}`;
  const existing = into.get(key);
  if (existing !== undefined) {
    if (!existing.viewports.includes(viewport)) existing.viewports.push(viewport);
    return;
  }
  into.set(key, {
    id: nextId(),
    screen,
    ruleId: result.id,
    impact: result.impact ?? "unknown",
    conformance: classify(result.tags),
    wcagTags: result.tags.filter((t) => t.startsWith("wcag")),
    help: result.help,
    helpUrl: result.helpUrl,
    nodeCount: result.nodes.length,
    selectors: selectors.slice(0, 6),
    failureSummary: (result.nodes[0]?.failureSummary ?? "").replace(/\s+/g, " ").trim().slice(0, 400),
    viewports: [viewport],
  });
}

async function startCampaign(page: Page): Promise<void> {
  await page.goto("/");
  // The Title screen renders one control per scenario, labelled `Start <display name>`. Commit 1
  // learned this the hard way: a guessed generic "Start" selector silently started nothing and swept
  // eleven empty screens. The response assertion is what makes that impossible to repeat quietly —
  // an accessibility baseline of the "no active game" state would be worse than no baseline.
  const start = page.getByRole("button", { name: /^Start / }).first();
  await start.waitFor({ state: "visible", timeout: 30_000 });
  const label = (await start.textContent()) ?? "";
  await start.click();
  const response = await page.waitForResponse(
    (r) => r.url().includes("/api/game/state") && r.status() === 200,
    { timeout: 30_000 },
  );
  expect(response.ok(), `campaign did not start via "${label.trim()}"`).toBe(true);
  await page.waitForTimeout(400);
}

async function visit(page: Page, screen: string): Promise<boolean> {
  const control = page.getByRole("button", { name: screen, exact: true }).first();
  if (!(await control.isVisible().catch(() => false))) return false;
  if (await control.isDisabled().catch(() => true)) return false;
  await control.click();
  await page.waitForTimeout(250);
  return true;
}

/** Audit one surface and return whether rules actually ran. Every rule is enabled: classification
 * happens afterwards from each result's own tags, so one pass yields the conformance view and the
 * best-practice view without running axe twice. */
async function audit(page: Page, screen: string, viewport: string): Promise<void> {
  let results: AxeResults;
  try {
    results = await new AxeBuilder({ page }).analyze();
  } catch (error) {
    // A HARNESS failure, recorded in its own list and asserted empty at the end. It is deliberately
    // not a clean result, not a finding about the application, and not filed beside a nav control
    // that was merely disabled: an audit that could not run has measured nothing, and must fail the
    // run rather than quietly reduce the expected coverage.
    axeFailures.push({ screen, viewport, reason: `axe failed to run: ${String(error).slice(0, 200)}` });
    return;
  }

  const rulesEvaluated =
    results.violations.length +
    results.passes.length +
    results.incomplete.length +
    results.inapplicable.length;

  surfaces.push({
    screen,
    viewport,
    rulesEvaluated,
    violations: results.violations.length,
    passes: results.passes.length,
    incomplete: results.incomplete.length,
    inapplicable: results.inapplicable.length,
  });

  for (const violation of results.violations) {
    record(findings, () => `A${(findingCounter += 1)}`, screen, viewport, violation);
  }
  for (const item of results.incomplete) {
    record(incompletes, () => `N${(incompleteCounter += 1)}`, screen, viewport, item);
  }
}

test.describe("Gate 4A3 accessibility baseline", () => {
  test.describe.configure({ mode: "serial" });

  test("audit every screen at every viewport case with axe-core", async ({ page }) => {
    test.setTimeout(1_800_000);
    mkdirSync(REVIEW_DIR, { recursive: true });

    await startCampaign(page);

    for (const viewport of VIEWPORTS) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      for (const screen of SCREENS) {
        if (!(await visit(page, screen))) {
          unreachable.push({
            screen,
            viewport: viewport.name,
            reason: "nav control absent or disabled",
          });
          continue;
        }
        await audit(page, screen, viewport.name);
      }
    }

    // The Glossary is chrome-level rather than a nav entry, so it is reached through its own toggle.
    // Skipping it would leave one of the twelve surfaces unaudited while the report implied
    // otherwise — the same absent-check-as-clean-result trap Commit 1a corrected.
    await page.setViewportSize({ width: 1440, height: 900 });
    const glossary = page.getByRole("button", { name: /glossary/i }).first();
    if (await glossary.isVisible().catch(() => false)) {
      await glossary.click();
      await page.waitForTimeout(250);
      await audit(page, "Glossary", "laptop-1440x900");
      await page.keyboard.press("Escape");
      await glossary.click().catch(() => undefined);
    } else {
      unreachable.push({
        screen: "Glossary",
        viewport: "laptop-1440x900",
        reason: "no glossary toggle found in the chrome",
      });
    }

    // THE MEASUREMENT RECORD, stated positively and first.
    //
    // Commit 1 recorded 14 clean results and no measurement proof, which is what let three
    // never-stressed screens read as clean in the stress pass. So this run records what it MEASURED
    // before it records what it found sound — and if every surface turns out to carry a violation,
    // the clean list below is legitimately empty rather than broken. An empty clean list plus a
    // populated measurement record is an unambiguous statement: everything was audited, nothing was
    // spotless.
    const evaluated = surfaces.map((s) => s.rulesEvaluated);
    if (evaluated.length > 0) {
      coverage.push(
        `${surfaces.length} surface(s) audited, each evaluating between ${Math.min(...evaluated)} and ` +
          `${Math.max(...evaluated)} axe rules — so every recorded result rests on rules that demonstrably ran`,
      );
    }

    // What was audited and found CLEAN — but only where rules demonstrably ran. This is the whole
    // anti-vacuity contract in four lines.
    const clean = surfaces.filter((s) => s.violations === 0 && s.rulesEvaluated > 0);
    for (const surface of clean) {
      coverage.push(
        `${surface.screen} at ${surface.viewport}: 0 violations with ${surface.rulesEvaluated} rules evaluated ` +
          `(${surface.passes} passed, ${surface.inapplicable} inapplicable)`,
      );
    }
    if (clean.length === 0 && surfaces.length > 0) {
      coverage.push(
        "no surface was violation-free: every audited surface carries at least one finding below, " +
          "which is a statement about the application and not a gap in the sweep",
      );
    }

    const all = [...findings.values()];
    const needsReview = [...incompletes.values()];

    writeFileSync(
      path.join(REVIEW_DIR, "gate-4a3-accessibility.json"),
      JSON.stringify(
        {
          axeCoreVersion: AXE_VERSION,
          findings: all,
          needsReview,
          surfaces,
          unreachable,
          axeFailures,
          coverage,
          viewports: VIEWPORTS.map((v) => ({ name: v.name, conformanceWidth: v.conformanceWidth })),
        },
        null,
        2,
      ) + "\n",
      "utf-8",
    );

    // ---- COVERAGE ASSERTIONS. None of these is about the violation count. ----

    // 1. Every surface that was audited really evaluated rules. This is the assertion that makes a
    //    recorded clean result mean something.
    const vacuous = surfaces.filter((s) => s.rulesEvaluated === 0);
    expect(
      vacuous.map((s) => `${s.screen}@${s.viewport}`),
      "a surface reporting zero evaluated rules was never really audited; a clean result there " +
        "would be an absent check wearing the look of a clean one",
    ).toEqual([]);

    // 2. axe itself never failed. A harness failure must be loud: it is the one thing §9.1 says a
    //    non-zero exit is FOR. Asserted before the coverage count, because a crash would otherwise
    //    relax that count and let a half-audited sweep pass.
    expect(
      axeFailures.map((f) => `${f.screen}@${f.viewport}: ${f.reason}`),
      "axe failed to run on at least one surface; that is the harness breaking, not a defect found",
    ).toEqual([]);

    // 3. The sweep reached enough surfaces to be a baseline at all. Eleven screens across eight
    //    viewport cases, minus whatever the NAVIGATION legitimately refuses, plus the Glossary — a run
    //    that audited a handful and stopped must not pass as a sweep. Only `unreachable` relaxes this
    //    bound, and it holds nav refusals alone.
    expect(
      surfaces.length,
      "too few surfaces audited for this to be a baseline of the application",
    ).toBeGreaterThanOrEqual(SCREENS.length * VIEWPORTS.length - unreachable.length);

    // 4. Every screen was audited at the conformance width, since that is the width the standard
    //    actually names and Commit 3 will triage against.
    const atWcag = new Set(
      surfaces.filter((s) => s.viewport === "reflow-wcag-320x512").map((s) => s.screen),
    );
    const missing = SCREENS.filter(
      (s) => !atWcag.has(s) && !unreachable.some((u) => u.screen === s && u.viewport === "reflow-wcag-320x512"),
    );
    expect(missing, "every reachable screen must be audited at the 320px conformance width").toEqual([]);

    // 5. axe itself was the real thing and its version is on the record.
    expect(AXE_VERSION, "axe-core version must be recorded for provenance").toMatch(/^\d+\.\d+\.\d+/);
  });
});
