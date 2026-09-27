/**
 * Gate 4A3 Commit 3 — THE REGRESSION CHECKS FOR EVERY ACCEPTED FIX.
 *
 * THIS FILE ASSERTS. That is the deliberate difference from Commits 1 and 2, whose specs report and
 * exit 0 whatever they find (§9.1) because a baseline must not be made to fail by finding defects.
 * Commit 3 FIXES those defects, and a fix without a failing-on-regression check is a claim rather than
 * a guarantee. So every accepted fix below is a hard assertion: if the defect comes back, this fails.
 *
 * WHAT IS ASSERTED, and which finding each one guards:
 *
 *   A8   Every `aria-controls` in the live DOM resolves. Tab ids are unique and contain no whitespace,
 *        which is the actual defect (an id built from the label "Budget policy" made
 *        `aria-controls="policy-panel-Budget policy-taxation"` read as two references, neither real).
 *        Arrow-key navigation still moves focus, so the fix did not trade a11y for keyboard breakage.
 *   A2-A7, A10-A15  No content outside a landmark, on every screen and the Glossary, plus exactly one
 *        banner -- the trap the fix had to avoid, since making the title bar a `<header>` while
 *        `NationalHeader` was also one would have produced two banners. The twelve landmark findings
 *        are A2-A7 and A10-A15, NOT a contiguous A2-A15 range: A8 is the tab defect above and A9 is a
 *        contrast defect below, so a range spanning them would credit this fix with two it did not
 *        make.
 *   A1, A9  Zero `color-contrast` violations. Measured by axe in the real browser, because that is the
 *        only renderer that can evaluate contrast at all.
 *   V1-V3   No horizontal page scroll and no overflowing node at the 320px CONFORMANCE width, across
 *        every screen. The 195px case is measured too but RECORDED, never asserted: halving a 390px
 *        phone lands below the 320px floor WCAG 2.2 SC 1.4.10 sets, so a finding there is a real user
 *        observation and not a conformance failure. Commit 1 drew that line; asserting it would quietly
 *        redefine the standard.
 *   F4   Under the browser's own reduced-motion setting, the media query is active AND no element
 *        reports a non-zero transition or animation duration. This is what makes F4's completion a
 *        measurement rather than the three-line CSS block being taken on trust.
 *
 * COVERAGE IS ASSERTED EXPLICITLY, not inferred. A missing screen, a missing viewport, or an axe run
 * that failed to execute fails this spec — because a verification that silently checked less than it
 * claimed would be exactly the vacuity Commit 1a was written to correct.
 */

import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

import { AxeBuilder } from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import {
  CALIBRATION,
  NON_TEXT_CONTRAST_MINIMUM,
  TEXT_CONTRAST_MINIMUM,
  installColourProbe,
} from "./contrast-probe";

const REVIEW_DIR = path.join(process.cwd(), "..", "docs", "reviews");

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

/** The conformance width WCAG 2.2 SC 1.4.10 actually names. */
const CONFORMANCE = { name: "reflow-wcag-320x512", width: 320, height: 512 } as const;

/** Below the 320px floor. Measured and recorded; deliberately NOT asserted. */
const BELOW_FLOOR = { name: "reflow200-mobile-195x422", width: 195, height: 422 } as const;

const record: {
  conformanceOverflow: { screen: string; detail: string }[];
  belowFloorObservations: { screen: string; detail: string }[];
  coverage: string[];
  reducedMotion: Record<string, unknown>;
  needsReviewDisposition: Record<string, unknown>;
  /** Gate 4A3 Commit 4. */
  iconContrast: Record<string, unknown>;
  introductionKeyboard: Record<string, unknown>;
  renderedCopy: Record<string, unknown>;
} = {
  conformanceOverflow: [],
  belowFloorObservations: [],
  coverage: [],
  reducedMotion: {},
  needsReviewDisposition: {},
  iconContrast: {},
  introductionKeyboard: {},
  renderedCopy: {},
};

/** Gate 4A3 Commit 4: the words that belong to the build and not to the game. The same list
 * `tools/check-copy.mjs` enforces on SOURCE -- asserted here against the LIVE DOM, which is the only
 * place a claim about what reaches a player can honestly be made.
 *
 * `revision` is absent from this list on purpose, and it is the one word where the two checks must
 * differ: it is a real player-facing concept with its own Glossary entry, so it is EXPECTED in the
 * rendered Glossary. The source check permits it in exactly one entry; a DOM scan cannot tell which
 * source entry a rendered word came from, so asserting its absence here would fail on the definition
 * that legitimises it. The source check is the one that keeps that allowance narrow. */
const BUILD_VOCABULARY = [
  "gate",
  "gates",
  "projected",
  "projection",
  "projections",
  "slot",
  "slots",
  "preflight",
  "ruleset",
  "fixture",
  "fixtures",
  "digest",
] as const;

async function startCampaign(page: Page): Promise<void> {
  await page.goto("/");
  const start = page.getByRole("button", { name: /^Start / }).first();
  await start.waitFor({ state: "visible", timeout: 30_000 });
  await start.click();
  const response = await page.waitForResponse(
    (r) => r.url().includes("/api/game/state") && r.status() === 200,
    { timeout: 30_000 },
  );
  expect(response.ok(), "the campaign must actually start, or nothing below means anything").toBe(true);
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

/** Nodes whose content is wider than their own scroll box: real clipping, not a guess. Mirrors the
 * baseline sweep's measurement exactly so the two are comparable. */
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

test.describe("Gate 4A3 Commit 3 — fix verification", () => {
  test.describe.configure({ mode: "serial" });

  test("A8: every aria-controls resolves, ids are unique and whitespace-free, arrows still work", async ({
    page,
  }) => {
    test.setTimeout(240_000);
    await startCampaign(page);
    expect(await visit(page, "Decisions"), "Decisions must be reachable").toBe(true);

    // The defect, checked at its root: an `aria-controls` value is a space-separated IDREF LIST, so an
    // id containing a space silently becomes two references. Every token must resolve.
    const dangling = await page.evaluate(() => {
      const out: string[] = [];
      for (const el of Array.from(document.querySelectorAll("[aria-controls]"))) {
        const value = el.getAttribute("aria-controls") ?? "";
        for (const token of value.split(/\s+/).filter((t) => t !== "")) {
          if (document.getElementById(token) === null) {
            out.push(`${el.tagName.toLowerCase()}[aria-controls="${value}"] -> no #${token}`);
          }
        }
      }
      return out;
    });
    expect(dangling, "every aria-controls token must resolve to a real element").toEqual([]);

    // Anti-vacuity: there must BE tabs with aria-controls, or the check above proves nothing.
    const tabInfo = await page.evaluate(() => {
      const tabs = Array.from(document.querySelectorAll('[role="tab"]'));
      return {
        total: tabs.length,
        withControls: tabs.filter((t) => t.getAttribute("aria-controls") !== null).length,
        ids: tabs.map((t) => t.id),
        panelIds: Array.from(document.querySelectorAll('[role="tabpanel"]')).map((p) => p.id),
      };
    });
    expect(tabInfo.total, "Decisions must render tabs for this check to mean anything").toBeGreaterThan(2);
    expect(tabInfo.withControls, "every tab must carry aria-controls").toBe(tabInfo.total);

    // Ids: present, unique, and free of the whitespace that caused A8.
    expect(tabInfo.ids.filter((id) => id === ""), "every tab needs an id").toEqual([]);
    expect(
      tabInfo.ids.filter((id) => /\s/.test(id)),
      "no tab id may contain whitespace: that is precisely what made aria-controls parse as two refs",
    ).toEqual([]);
    expect(new Set(tabInfo.ids).size, "tab ids must be unique").toBe(tabInfo.ids.length);
    expect(tabInfo.panelIds.filter((id) => id !== "").length, "the panel must carry an id").toBeGreaterThan(0);

    // The panel names its active tab, and that reference resolves too.
    const labelledBy = await page.evaluate(() => {
      const panel = document.querySelector('[role="tabpanel"]');
      const value = panel?.getAttribute("aria-labelledby") ?? "";
      return { value, resolves: value !== "" && document.getElementById(value) !== null };
    });
    expect(labelledBy.value, "the panel must name the active tab").not.toBe("");
    expect(labelledBy.resolves, "aria-labelledby must resolve").toBe(true);

    // Keyboard navigation still works, so the fix did not trade one defect for another.
    const tabs = page.locator('[role="tab"]');
    const first = tabs.nth(0);
    await first.focus();
    const before = await page.evaluate(() => document.activeElement?.id ?? "");
    await page.keyboard.press("ArrowRight");
    await page.waitForTimeout(150);
    const after = await page.evaluate(() => document.activeElement?.id ?? "");
    expect(before, "focus should start on a tab with an id").not.toBe("");
    expect(after, "ArrowRight must move focus to another tab").not.toBe(before);
    expect(tabInfo.ids, "ArrowRight must land on a tab, not somewhere else").toContain(after);

    record.coverage.push(
      `A8: ${tabInfo.total} tabs, all carrying aria-controls; ${tabInfo.ids.length} unique whitespace-free ids; ` +
        `every aria-controls token resolves; ArrowRight moved focus ${before} -> ${after}`,
    );
  });

  test("A2-A7, A10-A15 and A1/A9: no content outside landmarks, one banner, zero contrast violations", async ({
    page,
  }) => {
    test.setTimeout(600_000);
    await startCampaign(page);

    let audited = 0;
    for (const screen of SCREENS) {
      if (!(await visit(page, screen))) continue;
      audited += 1;

      const results = await new AxeBuilder({ page })
        .withRules(["region", "color-contrast", "landmark-no-duplicate-banner", "landmark-banner-is-top-level"])
        .analyze();

      // An axe run that evaluated nothing must fail, not pass quietly.
      const evaluated =
        results.violations.length +
        results.passes.length +
        results.incomplete.length +
        results.inapplicable.length;
      expect(evaluated, `axe evaluated no rules on ${screen}`).toBeGreaterThan(0);

      expect(
        results.violations.map((v) => `${v.id}: ${v.nodes.length} node(s)`),
        `${screen} must have no landmark, banner or contrast violations`,
      ).toEqual([]);

      // The landmark fix is also asserted structurally, because `region` passing is not the same claim
      // as "exactly one banner exists": a page with NO banner would also pass `region`.
      const landmarks = await page.evaluate(() => ({
        banners: document.querySelectorAll('header:not([role]), [role="banner"]').length,
        mains: document.querySelectorAll('main, [role="main"]').length,
        navs: document.querySelectorAll('nav, [role="navigation"]').length,
      }));
      expect(landmarks.banners, `${screen} must have exactly one banner`).toBe(1);
      expect(landmarks.mains, `${screen} must have exactly one main`).toBe(1);
      expect(landmarks.navs, `${screen} must have a navigation landmark`).toBeGreaterThanOrEqual(1);
    }

    // COVERAGE, asserted rather than assumed.
    expect(audited, "every screen must be audited").toBe(SCREENS.length);

    // The Glossary is chrome-level, so it is reached through its own toggle and audited too.
    const glossary = page.getByRole("button", { name: /glossary/i }).first();
    expect(await glossary.isVisible(), "the Glossary toggle must exist").toBe(true);
    await glossary.click();
    await page.waitForTimeout(250);
    const glossaryResults = await new AxeBuilder({ page })
      .withRules(["region", "color-contrast", "landmark-no-duplicate-banner"])
      .analyze();
    expect(
      glossaryResults.violations.map((v) => v.id),
      "the open Glossary must have no landmark or contrast violations",
    ).toEqual([]);
    await glossary.click();

    record.coverage.push(
      `A2-A7, A10-A15 + A1/A9: ${audited} screens plus the Glossary, each with zero ` +
        `region/contrast/banner ` +
        `violations and exactly one banner, one main and at least one navigation landmark`,
    );
  });

  test("V1-V3: no overflow at the 320px conformance width; 195px recorded, not asserted", async ({
    page,
  }) => {
    test.setTimeout(600_000);
    await startCampaign(page);

    // The CONFORMANCE width. Hard assertions.
    await page.setViewportSize({ width: CONFORMANCE.width, height: CONFORMANCE.height });
    let checked = 0;
    for (const screen of SCREENS) {
      if (!(await visit(page, screen))) continue;
      checked += 1;
      const scrolls = await page.evaluate(
        () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 2,
      );
      const overflowing = await overflowingNodes(page);
      if (scrolls) record.conformanceOverflow.push({ screen, detail: "page scrolls horizontally" });
      for (const node of overflowing) record.conformanceOverflow.push({ screen, detail: node });

      expect(scrolls, `${screen} must not scroll horizontally at ${CONFORMANCE.width}px`).toBe(false);
      expect(overflowing, `${screen} must have no overflowing node at ${CONFORMANCE.width}px`).toEqual([]);
    }
    expect(checked, "every screen must be checked at the conformance width").toBe(SCREENS.length);

    // BELOW the floor. Measured and recorded so the evidence survives; NOT asserted, because 195px is
    // narrower than the 320px the standard requires and treating it as conformance would invent a bar.
    await page.setViewportSize({ width: BELOW_FLOOR.width, height: BELOW_FLOOR.height });
    for (const screen of SCREENS) {
      if (!(await visit(page, screen))) continue;
      const scrolls = await page.evaluate(
        () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 2,
      );
      if (scrolls) record.belowFloorObservations.push({ screen, detail: "page scrolls horizontally" });
      for (const node of await overflowingNodes(page)) {
        record.belowFloorObservations.push({ screen, detail: node });
      }
    }

    record.coverage.push(
      `V1-V3: ${checked} screens clean at ${CONFORMANCE.width}px (asserted); ` +
        `${record.belowFloorObservations.length} observation(s) at ${BELOW_FLOOR.width}px (recorded, below the floor)`,
    );
  });

  test("F4: under the browser's reduced-motion setting nothing animates", async ({ browser }) => {
    test.setTimeout(240_000);

    // Playwright emulates the real user preference, so this is the browser's own setting rather than a
    // class the app opts into.
    const context = await browser.newContext({
      reducedMotion: "reduce",
      viewport: { width: 1440, height: 900 },
    });
    const page = await context.newPage();
    await startCampaign(page);

    // 1. The preference really is active. Without this the rest could pass because nothing animates
    //    anyway, which is true here but would stop being true the moment motion is added.
    const queryMatches = await page.evaluate(
      () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    );
    expect(queryMatches, "the reduced-motion media query must be active in this context").toBe(true);

    // 2. The guard in tokens.css is actually reachable -- a rule present in the stylesheet but never
    //    matched would be an inert mechanic, which is the defect F4's premise nearly shipped.
    const guardApplies = await page.evaluate(() => {
      const probe = document.createElement("div");
      probe.style.transitionDuration = "5s";
      document.body.appendChild(probe);
      const applied = getComputedStyle(probe).transitionDuration;
      probe.remove();
      return applied;
    });
    expect(
      guardApplies,
      "the reduced-motion block must override an inline 5s transition, proving the guard matches",
    ).not.toBe("5s");

    // 3. And nothing on the real screens animates.
    const animated: string[] = [];
    for (const screen of ["Dashboard", "Government", "Relationships", "Decisions"]) {
      if (!(await visit(page, screen))) continue;
      const moving = await page.evaluate(() => {
        const out: string[] = [];
        for (const el of Array.from(document.querySelectorAll("body *"))) {
          const style = getComputedStyle(el);
          const t = parseFloat(style.transitionDuration) || 0;
          const a = parseFloat(style.animationDuration) || 0;
          // The guard clamps to 0.01ms, so anything at or below 1ms is honouring it.
          if (t > 0.001 || a > 0.001) {
            out.push(`${el.tagName.toLowerCase()}: transition ${style.transitionDuration}, animation ${style.animationDuration}`);
          }
        }
        return out.slice(0, 5);
      });
      animated.push(...moving.map((m) => `${screen}: ${m}`));
    }
    expect(animated, "no element may report a non-zero transition or animation under reduced motion").toEqual([]);

    record.reducedMotion = {
      mediaQueryActive: queryMatches,
      inlineTransitionOverriddenTo: guardApplies,
      animatedElements: animated.length,
      screensChecked: ["Dashboard", "Government", "Relationships", "Decisions"],
    };
    record.coverage.push(
      `F4: reduced-motion active, a 5s inline transition clamped to ${guardApplies}, ` +
        `and 0 animating elements across 4 screens`,
    );

    await context.close();
  });

  /**
   * N1-N6: the six axe `incomplete` results, RESOLVED BY MEASUREMENT rather than by assumption.
   *
   * axe declined to judge these, and its stated reasons fall into two kinds:
   *
   *   - "Element content contains only non-text characters" (N1, N2). These are the tone GLYPHS --
   *     `✓ ✗ ▲ ■` inside `aria-hidden="true"` spans, each paired with an `sr-only` word. axe will not
   *     rate a glyph as text, which is correct of it.
   *   - "Background colour could not be determined because it is overlapped / partially obscured"
   *     (N3-N6). axe walks the DOM to find an effective background and gives up when elements overlap.
   *
   * Neither reason is a verdict, so neither can be dispositioned by inspection alone. This test does
   * what axe could not: for every element axe flagged, it reads the COMPUTED foreground colour, walks
   * ancestors for the first non-transparent background, and computes the WCAG ratio in the page. The
   * numbers are recorded, and any element carrying real text is asserted against 4.5:1.
   *
   * The glyph cases are asserted too, at the same 4.5:1, even though a decorative glyph is arguably out
   * of SC 1.4.3's scope: they sit in the same element as the value they decorate and inherit the tone
   * colour, so holding them to the text bar costs nothing and closes the question rather than arguing
   * it.
   */
  test("N1-N6: the six needs-review results, measured and dispositioned", async ({ page }) => {
    test.setTimeout(600_000);
    // Before any navigation: `addInitScript` is what makes the probe survive the SPA's own
    // navigations as well as the initial load.
    await installColourProbe(page);
    await startCampaign(page);

    /** Compute the real contrast of every element matching a selector, resolving the background by
     * walking ancestors -- the step axe declines to take when elements overlap. */
    const measureScreen = async (screen: string) => {
      if (!(await visit(page, screen))) return [];
      return page.evaluate(() => {
        /*
         * THE COLOUR MACHINERY NOW LIVES IN ONE PLACE: `e2e/contrast-probe.ts`, installed on
         * `window.__mandateColour` by `installColourProbe`. Commit 4 needed the same machinery for the
         * icon set's 2px strokes (SC 1.4.11), and a second copy would have been a second chance to
         * regress independently into the three failures this probe already survived -- an `rgba` regex
         * that missed Tailwind v4's OKLab output, a canvas round-trip this Chromium rejects, and
         * `.sr-only` nodes being measured although they are never painted. The probe's own module
         * documents all three. The numbers below are unchanged by the move, which the calibration
         * assertion and the recorded worst-case ratios are what prove.
         */
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

        const out: {
          selector: string;
          text: string;
          ratio: number;
          hasRealText: boolean;
          fontPx: number;
          rawColor: string;
          normalised: string;
          bg: string;
          classes: string;
        }[] = [];
        const candidates = new Set<Element>();
        for (const el of Array.from(
          document.querySelectorAll('main [aria-hidden="true"], main span, main text'),
        )) {
          candidates.add(el);
        }
        for (const el of candidates) {
          if (isVisuallyHidden(el)) continue;
          const own = Array.from(el.childNodes)
            .filter((n) => n.nodeType === Node.TEXT_NODE)
            .map((n) => n.textContent ?? "")
            .join("")
            .trim();
          if (own === "") continue;
          const style = getComputedStyle(el);
          const [fr, fg2, fb, fa] = normalise(style.color);
          const bg = effectiveBg(el);
          if (!Number.isFinite(fr) || !Number.isFinite(fa)) {
            out.push({
              selector: `${el.tagName.toLowerCase()}.${el.className.toString().slice(0, 30)}`,
              text: own.slice(0, 24),
              ratio: -1, // sentinel: UNMEASURED, not "measured as bad"
              hasRealText: /[A-Za-z0-9]/.test(own),
              fontPx: parseFloat(style.fontSize) || 0,
              rawColor: style.color,
              normalised: "UNPARSEABLE",
              bg: `rgb(${bg[0]},${bg[1]},${bg[2]})`,
              classes: el.className.toString(),
            });
            continue;
          }
          const fg = fa < 1 ? composite([fr, fg2, fb], bg, fa) : [fr, fg2, fb];
          out.push({
            selector: `${el.tagName.toLowerCase()}.${el.className.toString().slice(0, 30)}`,
            text: own.slice(0, 24),
            ratio: Math.round(ratio(fg, bg) * 100) / 100,
            hasRealText: /[A-Za-z0-9]/.test(own),
            fontPx: parseFloat(style.fontSize) || 0,
            // Carried so a below-bar result names the colour it measured. A ratio without its inputs
            // cannot be told apart from a broken probe -- which is exactly how the first two versions
            // of this measurement failed.
            rawColor: style.color,
            normalised: `rgba(${fr},${fg2},${fb},${fa})`,
            bg: `rgb(${bg[0]},${bg[1]},${bg[2]})`,
            classes: el.className.toString(),
          });
        }
        return out;
      });
    };

    const dispositions: {
      screen: string;
      measured: number;
      worstRatio: number;
      worstOn: string;
      glyphOnlyNodes: number;
      belowBar: {
        selector: string;
        text: string;
        ratio: number;
        rawColor: string;
        normalised: string;
      }[];
    }[] = [];

    // The screens the six needs-review results named.
    const allMeasurements: Awaited<ReturnType<typeof measureScreen>> = [];
    /** Screens that were flagged but produced nothing to measure, WITH the reason. A flagged screen
     * silently yielding no measurements would let the conclusion below claim more than the evidence
     * supports -- which a first run of this test did, until this list was added. */
    const notMeasured: { screen: string; reason: string }[] = [];
    for (const screen of ["Dashboard", "Decisions", "Relationships", "Strategic map", "Victory / defeat"]) {
      const measurements = await measureScreen(screen);
      if (measurements.length === 0) {
        notMeasured.push({
          screen,
          reason:
            "no text-bearing element was present to measure on this screen in a mid-campaign session",
        });
        continue;
      }
      allMeasurements.push(...measurements);
      // Large text (>=24px, or >=18.66px bold) has a 3:1 bar; nothing here relies on that, so the
      // stricter 4.5:1 is applied throughout rather than arguing size case by case.
      const belowBar = measurements
        .filter((m) => m.ratio < TEXT_CONTRAST_MINIMUM)
        .map((m) => ({
          selector: m.selector,
          text: m.text,
          ratio: m.ratio,
          rawColor: m.rawColor,
          normalised: m.normalised,
        }));
      const worst = measurements.reduce((a, b) => (a.ratio <= b.ratio ? a : b));
      dispositions.push({
        screen,
        measured: measurements.length,
        worstRatio: worst.ratio,
        worstOn: `${worst.selector} ${JSON.stringify(worst.text)}`,
        glyphOnlyNodes: measurements.filter((m) => !m.hasRealText).length,
        belowBar,
      });
    }

    expect(dispositions.length, "the needs-review screens must be measurable").toBeGreaterThan(3);

    // THE PROBE IS ITSELF CHECKED, against a figure computed independently of the browser.
    //
    // `text-parchment-200/60` is parchment-200 (#e8dcc0) at 60% over navy-900 (#0f1626), which an
    // offline WCAG calculation puts at 5.45:1 -- and axe independently reported 4.16:1 for the same
    // token at 50%, matching that same calculation. If this in-page measurement cannot reproduce the
    // known figure, its other numbers mean nothing, so this is asserted BEFORE they are trusted.
    const knownToken = allMeasurements.find(
      (m) => m.classes.includes(CALIBRATION.className) && m.ratio > 0,
    );
    expect(knownToken, "a text-parchment-200/60 node must exist to calibrate the probe").toBeDefined();
    expect(
      knownToken!.ratio,
      `the probe measured text-parchment-200/60 at ${knownToken!.ratio}:1; an independent calculation ` +
        `gives 5.45:1 on navy-900 and 5.57:1 on navy-950, so a figure outside that band means the ` +
        `probe is wrong rather than the application`,
    ).toBeGreaterThan(CALIBRATION.minRatio);
    expect(knownToken!.ratio).toBeLessThan(CALIBRATION.maxRatio);

    // Nothing may be left UNMEASURED. A colour the probe cannot parse is a hole in the evidence, not a
    // pass -- this is the assertion that would have caught the two earlier false results immediately.
    const unmeasured = allMeasurements.filter((m) => m.ratio === -1);
    expect(
      unmeasured.map((m) => `${m.selector}: ${m.rawColor}`),
      "every flagged element must be measurable; an unparseable colour is a broken probe",
    ).toEqual([]);
    for (const d of dispositions) {
      expect(d.measured, `${d.screen} must yield measurements`).toBeGreaterThan(0);
      expect(
        d.belowBar,
        `${d.screen}: these elements measure below 4.5:1 once the effective background is resolved, ` +
          `which is what axe could not determine`,
      ).toEqual([]);
    }

    // Which of the six each screen accounts for, so the disposition is per FINDING and not merely per
    // screen: N1 Dashboard, N2 + N5 Decisions, N3 Strategic map, N4 Relationships, N6 Victory / defeat.
    const measuredScreens = new Set(dispositions.map((d) => d.screen));
    const resolved = [
      { id: "N1", screen: "Dashboard" },
      { id: "N2", screen: "Decisions" },
      { id: "N3", screen: "Strategic map" },
      { id: "N4", screen: "Relationships" },
      { id: "N5", screen: "Decisions" },
      { id: "N6", screen: "Victory / defeat" },
    ].map((n) => ({
      ...n,
      disposition: measuredScreens.has(n.screen)
        ? "resolved by measurement: above the 4.5:1 AA bar once the effective background is resolved"
        : "NOT measured here -- see `deferred` below",
    }));

    record.needsReviewDisposition = {
      method:
        "For every text-bearing element on the screens axe flagged, the computed foreground colour " +
        "(converted from Tailwind v4's OKLab output and composited with its own alpha) was measured " +
        "against the first non-transparent ancestor background -- the resolution step axe skips when " +
        "elements overlap. Ratios are computed in-page with the WCAG relative-luminance formula, and " +
        "the probe is calibrated against an independently computed figure for a known token before any " +
        "of its numbers are trusted. Visually hidden nodes (`.sr-only`) are excluded: they are never " +
        "painted, so contrast does not apply to them.",
      precision:
        "The OKLab -> sRGB round trip can shift a channel by a unit, so a ratio here may differ from an " +
        "offline calculation by roughly 1-2% (the calibration node measured 5.65:1 against 5.45-5.57:1 " +
        "computed offline). That is immaterial at these margins -- the smallest measured ratio is 5.65:1 " +
        "against a 4.5:1 bar -- but it is stated rather than presented as exact.",
      conclusion:
        "FIVE of the six resolve ABOVE the 4.5:1 AA bar, and one is deferred with a reason. N1 and N2 " +
        "are the aria-hidden tone glyphs, which inherit a measured tone token and are paired with an " +
        "sr-only word, so meaning never rests on the glyph. N3, N4 and N5 were overlap cases where axe " +
        "could not find a background; resolving it by ancestor walk gives a passing ratio on every node.",
      deferred:
        notMeasured.length === 0
          ? []
          : notMeasured.map((n) => ({
              ...n,
              finding: n.screen === "Victory / defeat" ? "N6" : "(none)",
              disposition:
                "The terminal screen renders its outcome only in a CONCLUDED campaign, and this " +
                "verification runs mid-campaign, so N6's node does not exist to be measured here. It " +
                "is NOT claimed as resolved. Commit 5's end-to-end campaign drives a scenario to its " +
                "terminal screen, which is where this measurement belongs; recorded as owed rather " +
                "than folded into the passing count.",
            })),
      findings: resolved,
      dispositions,
      notMeasured,
    };
    record.coverage.push(
      `N1-N6: ${dispositions.reduce((n, d) => n + d.measured, 0)} text-bearing elements measured across ` +
        `${dispositions.length} of 5 flagged screens; worst ratio ` +
        `${Math.min(...dispositions.map((d) => d.worstRatio))}:1; none below 4.5:1; ` +
        `${notMeasured.length} screen(s) not measurable mid-campaign and recorded as owed`,
    );
  });

  /* ==============================================================================================
   * Gate 4A3 Commit 4 -- the icon set, the copy pass, and the introduction.
   * ============================================================================================ */

  test("Commit 4 icons: every mark clears 3:1 AT ITS OWN PLACEMENT, in all three groups", async ({
    page,
  }) => {
    test.setTimeout(600_000);
    await installColourProbe(page);
    await startCampaign(page);

    /* WHY THE TONE FIGURES DO NOT TRANSFER, which is the whole reason this test exists rather than a
     * citation of Commit 3's numbers. A 2px stroke is a graphical object under WCAG 2.2 SC 1.4.11 and
     * needs 3:1. Commit 3 measured the four TONE tokens at 6.24-8.86:1 -- on the navy backgrounds
     * TONE text sits on. The other two groups sit elsewhere: direction icons render inside `DeltaText`
     * (`text-parchment-200/70`) and inside the policy cards' effect chips (`text-parchment-200/80` on
     * a card surface), and the legend icons sit on the strategic map's own panel. Borrowing the tone
     * figures for those would be asserting a measurement nobody took.
     *
     * `stroke="currentColor"` is what makes this measurable at all: the stroke colour IS the element's
     * computed `color`, so the probe resolves it exactly as it resolves text. */
    const measureIcons = async (screen: string) => {
      if (!(await visit(page, screen))) return [];
      return page.evaluate(() => {
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

        const out: {
          icon: string;
          group: string;
          ratio: number;
          strokeWidth: string;
          rawColor: string;
          bg: string;
          placement: string;
        }[] = [];
        const group = (name: string) =>
          name === "route-one-way" || name === "route-two-way" || name === "capital"
            ? "map-legend"
            : name === "up" || name === "down" || name === "unchanged"
              ? "direction"
              : "tone";

        for (const el of Array.from(document.querySelectorAll("svg[data-icon]"))) {
          if (isVisuallyHidden(el)) continue;
          const name = el.getAttribute("data-icon") ?? "(unnamed)";
          const style = getComputedStyle(el);
          const parsed = normalise(style.color);
          const bg = effectiveBg(el);
          const alpha = parsed[3] ?? Number.NaN;
          if (!Number.isFinite(parsed[0]) || !Number.isFinite(alpha)) {
            out.push({
              icon: name,
              group: group(name),
              ratio: -1, // UNMEASURED, never "measured as bad".
              strokeWidth: style.strokeWidth,
              rawColor: style.color,
              bg: `rgb(${bg[0]},${bg[1]},${bg[2]})`,
              placement: (el.parentElement?.className ?? "").toString().slice(0, 60),
            });
            continue;
          }
          const fg =
            alpha < 1
              ? composite([parsed[0]!, parsed[1]!, parsed[2]!], bg, alpha)
              : [parsed[0]!, parsed[1]!, parsed[2]!];
          out.push({
            icon: name,
            group: group(name),
            ratio: Math.round(ratio(fg, bg) * 100) / 100,
            strokeWidth: style.strokeWidth,
            rawColor: style.color,
            bg: `rgb(${bg[0]},${bg[1]},${bg[2]})`,
            placement: (el.parentElement?.className ?? "").toString().slice(0, 60),
          });
        }
        return out;
      });
    };

    /** The probe is calibrated on the same page before its icon numbers are trusted -- the discipline
     * Commit 3's three false 1.00:1 results earned. Measured on a text node, because the known figure
     * is a text token's. */
    const calibrate = async () =>
      page.evaluate((className: string) => {
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
        for (const el of Array.from(document.querySelectorAll(`[class*="${className}"]`))) {
          if (isVisuallyHidden(el)) continue;
          const own = Array.from(el.childNodes)
            .filter((n) => n.nodeType === Node.TEXT_NODE)
            .map((n) => n.textContent ?? "")
            .join("")
            .trim();
          if (own === "") continue;
          const style = getComputedStyle(el);
          const parsed = normalise(style.color);
          if (!Number.isFinite(parsed[0])) continue;
          const bg = effectiveBg(el);
          const alpha = parsed[3] ?? 1;
          const fg =
            alpha < 1
              ? composite([parsed[0]!, parsed[1]!, parsed[2]!], bg, alpha)
              : [parsed[0]!, parsed[1]!, parsed[2]!];
          return Math.round(ratio(fg, bg) * 100) / 100;
        }
        return null;
      }, CALIBRATION.className);

    const all: Awaited<ReturnType<typeof measureIcons>> = [];
    const perScreen: { screen: string; icons: number; worst: number }[] = [];
    let calibrated: number | null = null;

    for (const screen of SCREENS) {
      const icons = await measureIcons(screen);
      if (calibrated === null) calibrated = await calibrate();
      if (icons.length === 0) continue;
      all.push(...icons);
      perScreen.push({
        screen,
        icons: icons.length,
        worst: Math.min(...icons.map((i) => i.ratio)),
      });
    }

    /* THE PREVIEW PANEL, reached deliberately. A first run of this test measured only 6 of the 10
     * icons: the POSITIVE and NEGATIVE tone marks render in `ConsequencesPanel`, which exists only
     * after a player presses Preview, so a sweep that only navigates never sees them. Measuring six
     * icons and reporting the tone group as "clear" would have been the same vacuity as folding N6
     * into the passing count -- so the panel is opened rather than the gap being argued away. */
    if (await visit(page, "Decisions")) {
      const previewButton = page.getByRole("button", { name: "Preview" }).first();
      if (await previewButton.isVisible().catch(() => false)) {
        await previewButton.click();
        await page
          .waitForResponse((r) => r.url().includes("/api/game/preview"), { timeout: 30_000 })
          .catch(() => undefined);
        await page.waitForTimeout(600);
        const previewIcons = await page.evaluate(() => {
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
          const out: {
            icon: string;
            group: string;
            ratio: number;
            strokeWidth: string;
            rawColor: string;
            bg: string;
            placement: string;
          }[] = [];
          for (const el of Array.from(document.querySelectorAll("svg[data-icon]"))) {
            if (isVisuallyHidden(el)) continue;
            const name = el.getAttribute("data-icon") ?? "(unnamed)";
            const style = getComputedStyle(el);
            const parsed = normalise(style.color);
            const bg = effectiveBg(el);
            const alpha = parsed[3] ?? Number.NaN;
            if (!Number.isFinite(parsed[0]) || !Number.isFinite(alpha)) {
              out.push({
                icon: name,
                group: "tone",
                ratio: -1,
                strokeWidth: style.strokeWidth,
                rawColor: style.color,
                bg: `rgb(${bg[0]},${bg[1]},${bg[2]})`,
                placement: "preview panel",
              });
              continue;
            }
            const fg =
              alpha < 1
                ? composite([parsed[0]!, parsed[1]!, parsed[2]!], bg, alpha)
                : [parsed[0]!, parsed[1]!, parsed[2]!];
            out.push({
              icon: name,
              group:
                name === "route-one-way" || name === "route-two-way" || name === "capital"
                  ? "map-legend"
                  : name === "up" || name === "down" || name === "unchanged"
                    ? "direction"
                    : "tone",
              ratio: Math.round(ratio(fg, bg) * 100) / 100,
              strokeWidth: style.strokeWidth,
              rawColor: style.color,
              bg: `rgb(${bg[0]},${bg[1]},${bg[2]})`,
              placement: `preview panel: ${(el.parentElement?.className ?? "").toString().slice(0, 40)}`,
            });
          }
          return out;
        });
        if (previewIcons.length > 0) {
          all.push(...previewIcons);
          perScreen.push({
            screen: "Decisions (preview panel)",
            icons: previewIcons.length,
            worst: Math.min(...previewIcons.map((i) => i.ratio)),
          });
        }
      }
    }

    expect(
      calibrated,
      `the probe must reproduce ${CALIBRATION.className}'s known ratio before its icon figures are ` +
        `trusted (${CALIBRATION.offlineNote})`,
    ).not.toBeNull();
    expect(calibrated!).toBeGreaterThan(CALIBRATION.minRatio);
    expect(calibrated!).toBeLessThan(CALIBRATION.maxRatio);

    // COVERAGE, asserted rather than assumed: all three groups must have been reached. A run that
    // happened to visit no screen rendering a legend icon would otherwise report "all clear" for a
    // group it never measured -- the vacuity this whole gate is written against.
    const groups = new Set(all.map((i) => i.group));
    for (const required of ["tone", "direction", "map-legend"]) {
      expect(
        groups.has(required),
        `no ${required} icon was reached; this group's contrast is UNMEASURED, not clean`,
      ).toBe(true);
    }

    const unmeasured = all.filter((i) => i.ratio === -1);
    expect(
      unmeasured.map((i) => `${i.icon}: ${i.rawColor}`),
      "an unparseable colour is a broken probe, not a passing icon",
    ).toEqual([]);

    // Every icon must be a 2px stroke, since that is the premise the 3:1 bar is applied under.
    const wrongWidth = all.filter((i) => parseFloat(i.strokeWidth) !== 2);
    expect(
      wrongWidth.map((i) => `${i.icon}: ${i.strokeWidth}`),
      "every icon is specified at a 2px stroke; a thinner one would change which WCAG bar applies",
    ).toEqual([]);

    const belowBar = all
      .filter((i) => i.ratio < NON_TEXT_CONTRAST_MINIMUM)
      .map((i) => `${i.icon} (${i.group}) at ${i.ratio}:1 on ${i.bg} -- ${i.placement}`);
    expect(
      belowBar,
      `every icon must clear ${NON_TEXT_CONTRAST_MINIMUM}:1 at its own placement (SC 1.4.11)`,
    ).toEqual([]);

    /* PER-ICON COVERAGE, recorded explicitly. Group coverage alone would let a whole status token go
     * unmeasured behind a neutral one -- so every icon this set exports is accounted for as either
     * MEASURED or NOT REACHED WITH A REASON, and the two lists must together cover all ten. This is
     * Commit 3's "screens that yielded nothing" discipline applied per symbol. */
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
    const reached = new Set(all.map((i) => i.icon));
    const notReached = EVERY_ICON.filter((name) => !reached.has(name)).map((name) => ({
      icon: name,
      reason:
        "not rendered in any state this sweep enters: the sweep starts a campaign, visits every " +
        "screen and opens the preview panel, but a mark only appears when the projected value it " +
        "describes occurs. Its contrast here is UNMEASURED, not clean.",
      mitigation:
        "Every icon inherits its stroke from the tone token of the element it sits in " +
        "(`stroke=\"currentColor\"`), and Commit 3 measured all four status tokens as TEXT at " +
        "6.24-8.86:1 -- a 4.5:1 bar, stricter than the 3:1 this test applies. That is evidence about " +
        "the token, not a measurement of this placement, and it is recorded as such.",
    }));
    expect(
      [...reached].filter((name) => !EVERY_ICON.includes(name as (typeof EVERY_ICON)[number])),
      "every measured icon must be one this set declares; an unknown `data-icon` is a drift",
    ).toEqual([]);
    expect(
      reached.size + notReached.length,
      "every icon must be accounted for as measured or explicitly not reached",
    ).toBe(EVERY_ICON.length);

    const worstByGroup = Object.fromEntries(
      ["tone", "direction", "map-legend"].map((g) => {
        const ratios = all.filter((i) => i.group === g).map((i) => i.ratio);
        return [g, ratios.length === 0 ? null : Math.min(...ratios)];
      }),
    );

    record.iconContrast = {
      bar: `${NON_TEXT_CONTRAST_MINIMUM}:1, WCAG 2.2 SC 1.4.11 (a 2px stroke is a graphical object)`,
      method:
        "Every `svg[data-icon]` in the live DOM, measured at ITS OWN placement rather than borrowing " +
        "Commit 3's tone-token figures: `stroke=\"currentColor\"` means the stroke colour is the " +
        "element's computed `color`, resolved against the first non-transparent ancestor background " +
        "with the same calibrated probe the N1-N6 measurement uses (`e2e/contrast-probe.ts`).",
      calibrationRatio: calibrated,
      measured: all.length,
      distinctIcons: [...new Set(all.map((i) => i.icon))].sort(),
      worstByGroup,
      perScreen,
      iconsMeasured: [...reached].sort(),
      iconsNotReached: notReached,
    };
    record.coverage.push(
      `Commit 4 icons: ${all.length} icon placements measured across ${perScreen.length} surfaces; ` +
        `${reached.size} of ${EVERY_ICON.length} icons reached, ${notReached.length} recorded as not ` +
        `reached with a reason; all three groups covered; worst ratios ` +
        `${JSON.stringify(worstByGroup)}; none below ${NON_TEXT_CONTRAST_MINIMUM}:1`,
    );
  });

  test("Commit 4 introduction: real Tab traversal, in both directions, and a predictable landing", async ({
    page,
  }) => {
    test.setTimeout(300_000);
    await page.goto("/");

    const note = page.getByRole("complementary", { name: "How to govern" });
    await note.waitFor({ state: "visible", timeout: 30_000 });

    /* WHY THIS IS A TRAVERSAL AND NOT AN INFERENCE. An operable Start button and an absent
     * `aria-modal` do NOT establish that focus cannot be trapped: a trap is a property of what Tab
     * actually does, so Tab is what this has to do. jsdom cannot answer it at all -- it has no focus
     * model for Tab -- which is why this half of the proof is here and not in the unit suite. */

    const focused = () =>
      page.evaluate(() => {
        const el = document.activeElement;
        if (el === null) return { tag: "none", text: "", inNote: false };
        return {
          tag: el.tagName.toLowerCase(),
          text: (el.textContent ?? "").replace(/\s+/g, " ").trim().slice(0, 40),
          inNote: el.closest('aside[aria-label="How to govern"]') !== null,
        };
      });

    // (1) FORWARD. Tab from the top; focus must pass through the note and leave it for the page.
    await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
    const forward: { tag: string; text: string; inNote: boolean }[] = [];
    let sawNote = false;
    let leftNote = false;
    for (let i = 0; i < 30; i += 1) {
      await page.keyboard.press("Tab");
      const state = await focused();
      forward.push(state);
      if (state.inNote) sawNote = true;
      if (sawNote && !state.inNote) {
        leftNote = true;
        break;
      }
    }
    expect(sawNote, "the introduction's Dismiss control must be Tab-reachable").toBe(true);
    expect(
      leftNote,
      `focus never left the introduction in ${forward.length} forward tabs; that is a keyboard trap. ` +
        `Sequence: ${JSON.stringify(forward)}`,
    ).toBe(true);

    // (2) BACKWARD. A one-directional check misses a trap that only bites going back.
    let leftBackwards = false;
    const backward: { tag: string; text: string; inNote: boolean }[] = [];
    for (let i = 0; i < 30; i += 1) {
      await page.keyboard.press("Shift+Tab");
      const state = await focused();
      backward.push(state);
      if (state.inNote) {
        // Keep going: leaving the note in the reverse direction is what is being proven.
        continue;
      }
      if (backward.some((entry) => entry.inNote)) {
        leftBackwards = true;
        break;
      }
    }
    expect(
      leftBackwards,
      `focus never left the introduction going backwards. Sequence: ${JSON.stringify(backward)}`,
    ).toBe(true);

    // (5) START STAYS OPERABLE while the note is open -- checked here, with the note still present.
    const start = page.getByRole("button", { name: /^Start / }).first();
    await expect(start).toBeEnabled();
    await start.focus();
    expect(await focused()).toMatchObject({ tag: "button" });

    // (3) DISMISSAL WHILE THE DISMISS BUTTON HOLDS FOCUS -- the case most likely to break, because the
    // focused element is removed from the DOM. The landing element is NAMED rather than accepted:
    // `<body>` with the tab position lost is a real regression a lenient check would pass.
    const dismiss = page.getByRole("button", { name: "Dismiss" });
    await dismiss.focus();
    expect(await focused(), "Dismiss must be able to hold focus").toMatchObject({ inNote: true });
    await page.keyboard.press("Enter");
    await expect(note).toBeHidden();
    const afterDismiss = await focused();

    // Whatever the browser does with focus after removing its holder, the next Tab must land on a real
    // control -- that is the property a player depends on, and it is what "predictable" has to mean
    // when the focused node no longer exists.
    await page.keyboard.press("Tab");
    const afterTab = await focused();
    expect(
      ["button", "a", "input", "select", "textarea"],
      `after dismissing from the Dismiss button, the next Tab landed on <${afterTab.tag}> ` +
        `(${JSON.stringify(afterTab.text)}), so the tab position was lost`,
    ).toContain(afterTab.tag);

    // (4) REOPENING BY KEYBOARD, with `aria-expanded` tracking the state.
    const toggle = page.getByRole("button", { name: "How to govern" });
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await toggle.focus();
    await page.keyboard.press("Enter");
    await expect(note).toBeVisible();
    await expect(toggle).toHaveAttribute("aria-expanded", "true");
    await expect(note).toContainText(
      "Review your country, prepare your actions, preview their consequences, resolve the turn, " +
        "and read what happened.",
    );

    // And it is never a dialog: no `aria-modal`, no `role`, nothing inert behind it.
    expect(await note.getAttribute("aria-modal")).toBeNull();
    expect(await note.getAttribute("role")).toBeNull();
    expect(await page.locator("[inert]").count()).toBe(0);

    // THE HEADER TOGGLE AT THE 320px CONFORMANCE WIDTH. It is new chrome on every screen, so it is new
    // opportunity for the header to overflow at the narrowest conforming viewport.
    await page.setViewportSize({ width: CONFORMANCE.width, height: CONFORMANCE.height });
    await page.waitForTimeout(200);
    const narrow = await page.evaluate(() => {
      const header = document.querySelector("header");
      const buttons = Array.from(document.querySelectorAll("header button")).map((b) => ({
        name: (b.textContent ?? "").trim(),
        right: Math.round(b.getBoundingClientRect().right),
        width: Math.round(b.getBoundingClientRect().width),
      }));
      return {
        pageScrolls:
          document.documentElement.scrollWidth > document.documentElement.clientWidth + 2,
        headerOverflows:
          header !== null && header.scrollWidth > header.clientWidth + 2,
        viewportWidth: document.documentElement.clientWidth,
        buttons,
      };
    });
    expect(narrow.pageScrolls, `the page must not scroll horizontally at ${CONFORMANCE.width}px`).toBe(
      false,
    );
    expect(
      narrow.headerOverflows,
      `the header must not overflow at ${CONFORMANCE.width}px now that it carries two controls`,
    ).toBe(false);
    expect(
      narrow.buttons.map((b) => b.name).sort(),
      "both header controls must be present at the conformance width",
    ).toEqual(["Glossary", "How to govern"]);
    for (const button of narrow.buttons) {
      expect(button.width, `${button.name} must be rendered, not collapsed`).toBeGreaterThan(0);
      expect(
        button.right,
        `${button.name} must sit inside the ${narrow.viewportWidth}px viewport`,
      ).toBeLessThanOrEqual(narrow.viewportWidth + 1);
    }

    record.introductionKeyboard = {
      forwardTabs: forward,
      backwardTabs: backward,
      focusAfterDismissal: afterDismiss,
      focusAfterNextTab: afterTab,
      narrowHeader: narrow,
      conclusion:
        "Focus enters and leaves the introduction in BOTH directions, so it is not a trap; dismissing " +
        "while the Dismiss button holds focus leaves the next Tab landing on a real control; the note " +
        "reopens from the header toggle by keyboard with `aria-expanded` tracking it; Start stays " +
        "operable throughout; and both header controls fit inside the 320px conformance width.",
    };
    record.coverage.push(
      `Commit 4 introduction: ${forward.length} forward and ${backward.length} backward tabs traversed, ` +
        `dismissal-under-focus and keyboard reopening proven, header toggle clean at ` +
        `${CONFORMANCE.width}px`,
    );
  });

  test("Commit 4 copy: no build vocabulary reaches a player IN THE AUDITED STATES", async ({ page }) => {
    test.setTimeout(600_000);
    await startCampaign(page);

    /* THE CLAIM IS EXACTLY AS WIDE AS THE COVERAGE, and the test name says so. `document.body
     * .textContent` alone would be two different kinds of wrong: it MISSES every `aria-label`,
     * `title`, `placeholder` and `alt` -- the strings a screen-reader user hears and a sighted user
     * never sees, and the panel title that said "(separate slot)" was exactly such a `title` -- and it
     * INCLUDES text that is present but never painted. So both halves are scanned, and the audited
     * states are named rather than generalised to "the player". */
    const scanScreen = async (screen: string) => {
      if (!(await visit(page, screen))) return null;
      return page.evaluate(() => {
        const attributes = ["aria-label", "aria-description", "title", "placeholder", "alt"];
        const attributeValues: { attribute: string; value: string }[] = [];
        for (const el of Array.from(
          document.querySelectorAll("[aria-label], [aria-description], [title], [placeholder], [alt]"),
        )) {
          for (const attribute of attributes) {
            const value = el.getAttribute(attribute);
            if (value !== null && value.trim() !== "") attributeValues.push({ attribute, value });
          }
        }
        return {
          textContent: (document.body.textContent ?? "").replace(/\s+/g, " "),
          attributeValues,
        };
      });
    };

    const scanned: string[] = [];
    const offences: { screen: string; word: string; where: string; sample: string }[] = [];

    for (const screen of SCREENS) {
      const result = await scanScreen(screen);
      if (result === null) continue;
      scanned.push(screen);
      for (const word of BUILD_VOCABULARY) {
        const pattern = new RegExp(`\\b${word}\\b`, "i");
        const textMatch = pattern.exec(result.textContent);
        if (textMatch !== null) {
          const at = Math.max(0, textMatch.index - 40);
          offences.push({
            screen,
            word,
            where: "text node",
            sample: result.textContent.slice(at, at + 120),
          });
        }
        for (const { attribute, value } of result.attributeValues) {
          if (pattern.test(value)) {
            offences.push({ screen, word, where: `@${attribute}`, sample: value.slice(0, 120) });
          }
        }
      }
    }

    // The Glossary is chrome, opened by its own toggle rather than reached from the nav, so it is
    // scanned separately -- and it is where `revision` legitimately appears, which is why that word is
    // not in `BUILD_VOCABULARY` (see the list's own note).
    await page.getByRole("button", { name: "Glossary" }).click();
    await page.waitForTimeout(200);
    const glossary = await page.evaluate(() => {
      const region = document.querySelector('[aria-label="Glossary"]');
      return (region?.textContent ?? "").replace(/\s+/g, " ");
    });
    expect(glossary, "the Glossary must actually be open, or scanning it proves nothing").toContain(
      "Political capital",
    );
    for (const word of BUILD_VOCABULARY) {
      const pattern = new RegExp(`\\b${word}\\b`, "i");
      const match = pattern.exec(glossary);
      if (match !== null) {
        offences.push({
          screen: "Glossary",
          word,
          where: "text node",
          sample: glossary.slice(Math.max(0, match.index - 40), match.index + 80),
        });
      }
    }
    // And `revision` IS expected here: the Glossary is what teaches the word, which is the whole basis
    // of the narrowly scoped source-check exception.
    expect(
      glossary,
      "the Glossary must still define `revision`; the narrow source-check allowance depends on it",
    ).toContain("Revision");

    // ANTI-VACUITY: a scan that reached almost nothing would report "clean" for the wrong reason.
    expect(scanned.length, "every screen must be scanned").toBe(SCREENS.length);
    expect(offences, "no build vocabulary may reach a player in the audited states").toEqual([]);

    record.renderedCopy = {
      claim:
        "No forbidden whole word appears in the rendered text nodes OR the player-visible attributes " +
        "of the audited states: " +
        `${scanned.length} screens plus the Glossary at the default viewport.`,
      notClaimed:
        "This is NOT a claim about every state of the application. The concluded-campaign terminal " +
        "screen is not entered here -- the same reason N6's contrast and the terminal screen's reflow " +
        "are both owed to Commit 5 -- so an unqualified \"no build vocabulary reaches the player\" " +
        "would assert coverage this run does not have.",
      inspected: {
        textNodes: "document.body.textContent",
        attributes: ["aria-label", "aria-description", "title", "placeholder", "alt"],
      },
      vocabulary: [...BUILD_VOCABULARY],
      permittedByDesign: {
        revision:
          "a real player-facing concept with its own Glossary entry, so it is EXPECTED in the rendered " +
          "Glossary and is therefore not in this scan's vocabulary; `tools/check-copy.mjs` is what " +
          "keeps the allowance scoped to that single entry in source.",
      },
      screensScanned: scanned,
      offences,
    };
    record.coverage.push(
      `Commit 4 copy: ${scanned.length} screens plus the Glossary scanned for ` +
        `${BUILD_VOCABULARY.length} forbidden whole words, in text nodes AND five player-visible ` +
        `attributes; ${offences.length} offence(s)`,
    );
  });

  test.afterAll(() => {
    mkdirSync(REVIEW_DIR, { recursive: true });
    writeFileSync(
      path.join(REVIEW_DIR, "gate-4a3-commit3-verification.json"),
      JSON.stringify(record, null, 2) + "\n",
      "utf-8",
    );
  });
});
