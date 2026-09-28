/**
 * Gate 4A3 Commit 2 — the jsdom axe SUPPLEMENT.
 *
 * READ THIS BEFORE TRUSTING ANYTHING HERE. This file is explicitly **not** the accessibility
 * evidence for this gate. The evidence is `docs/reviews/gate-4a3-accessibility.md`, produced by
 * `npm run audit:accessibility` against a real Chromium rendering the real application. The frozen
 * plan's Commit 2 asks for "supplementary jsdom `axe-core` unit tests for per-component
 * regressions — explicitly a supplement, never the primary evidence", and that is exactly the
 * standing of this file.
 *
 * WHAT JSDOM CANNOT DO, stated so nobody reads a pass here as a clean bill of health. jsdom has no
 * layout engine and no compositor, so it cannot evaluate `color-contrast` (it has no resolved
 * colours to compare), `target-size` (no box geometry), or anything else that needs a rendered box.
 * axe reports those as `incomplete` or skips them. A green run of this file therefore means
 * "no STRUCTURAL regression in these components", and nothing wider.
 *
 * WHY IT IS STILL WORTH HAVING. The browser sweep audits SCREENS. It cannot reach a shared leaf
 * component on its own, and it cannot fail fast in the ordinary `npm test` loop. These tests can:
 * they run in 26 files' worth of existing jsdom infrastructure, and they catch a regression in a
 * shared primitive at the moment it is introduced rather than at the next full audit. S1 below is
 * that value realised on the first run.
 *
 * ONE HOUSEKEEPING NOTE, because it cost three builds to learn properly. Tailwind v4 extracts bare
 * words from scanned files as utility candidates, and it scanned BOTH this file and
 * `e2e/accessibility.spec.ts` — a wider reach than `tailwind.config.ts`'s own `src` glob suggests,
 * because v4 layers automatic source detection over the configured globs.
 *
 * Three times while writing this commit, a word in a COMMENT was also the name of a Tailwind utility,
 * and Tailwind duly emitted that utility's rule into the PRODUCTION stylesheet — 27 bytes each time,
 * from prose that is not code at all. The third instance was this very note, which leaked by NAMING
 * the utility it was warning about. So the names are omitted deliberately: the two culprits were
 * ordinary English verbs describing layout-ish and containment-ish ideas, and writing either one here
 * would reproduce the defect a third time. The build was re-measured after each wording change until
 * the stylesheet returned to its committed bytes, which it now has.
 *
 * The general problem — dev-only and test-only files contributing to the shipped CSS, from comments —
 * is recorded for **Commit 6's packaging and bundle-hygiene review** rather than fixed here:
 * constraining the scanned sources is a build-config change outside this commit's subject, and
 * Commit 2 fixes nothing by design.
 *
 * THE KNOWN-OPEN ALLOWLIST IS THE HONEST PART. Commit 2 records defects and fixes none of them
 * (§9.1), so three rules currently fail in the real browser. Asserting zero violations overall would
 * make this file red, and committing a red suite breaks the standing rule that nothing is committed
 * while a gate is failing. So each currently-open rule is disabled BY NAME, with its finding id and
 * its reason — §9.1's "a won't-fix gets a recorded reason and an explicit allowlist entry naming it,
 * never a silently-passing scan", applied to known-open findings. Every other rule is asserted at
 * zero, which is where the regression value lives. Commit 3 deletes entries from this list as it
 * fixes them, and the list going empty is the signal that it is done.
 */

import { render } from "@testing-library/react";
import axe from "axe-core";
import { describe, expect, it } from "vitest";

import supplement from "./a11y.supplement-findings.json";
import { DataTable, DeltaText, EmptyNote, Panel, RatioBar, ToneValue } from "./components";

/** The declared supplement findings, verified below against what axe actually reports. The review
 * artifact renders this same file, so the report and the test cannot disagree about what is open.
 *
 * Both lists are checked, in opposite directions: an `open` finding must still reproduce, and a
 * `fixed` one must no longer reproduce. A record that only tracked open findings would let a "fixed"
 * claim rot silently the moment someone reverted the fix. */
const OPEN = supplement.open;
const FIXED = supplement.fixed;

/**
 * Rules the REAL-BROWSER baseline already records as open, disabled here by name so this suite is
 * green while Commit 2 records rather than fixes. Each entry names the finding it defers to; none is
 * a judgement that the defect is acceptable.
 */
const KNOWN_OPEN_RULES: Record<string, string> = {
  "color-contrast":
    "NOT a deferred defect: A1 and A9 were FIXED in Commit 3, and `tools/check-palette.mjs` now " +
    "enforces the measured floor that keeps them fixed. This rule stays disabled here for a " +
    "different and permanent reason -- jsdom has no layout engine and cannot evaluate contrast at " +
    "all, so a pass would be meaningless rather than merely incomplete. The real contrast evidence " +
    "is the browser sweep.",
};

const DISABLED_RULES = Object.fromEntries(
  Object.keys(KNOWN_OPEN_RULES).map((rule) => [rule, { enabled: false }]),
);

/** Run axe over one rendered container, with the known-open rules disabled by name. */
async function analyze(container: HTMLElement): Promise<axe.AxeResults> {
  return axe.run(container, { rules: DISABLED_RULES });
}

/** The anti-vacuity guard, same contract as the browser sweep: an axe run that evaluated nothing
 * reports no violations, and that must never read as a pass. */
function assertRulesActuallyRan(results: axe.AxeResults, what: string): void {
  const evaluated =
    results.violations.length +
    results.passes.length +
    results.incomplete.length +
    results.inapplicable.length;
  expect(
    evaluated,
    `axe evaluated no rules at all against ${what}, so a zero-violation result there would be an ` +
      "absent check wearing the look of a clean one",
  ).toBeGreaterThan(0);
}

function describeViolations(results: axe.AxeResults): string {
  return results.violations
    .map(
      (v) =>
        `${v.id} (${v.impact}): ${v.help} -- ${v.nodes
          .map((n) => (n.target as unknown[]).join(" "))
          .slice(0, 3)
          .join("; ")}`,
    )
    .join("\n");
}

describe("jsdom axe supplement (NOT the primary evidence)", () => {
  it("the disabled-rule list is down to the one jsdom structurally cannot judge", () => {
    // Commit 2 disabled THREE rules here, each deferring to an open browser finding. Commit 3 fixed
    // all three defects, so two exclusions are gone and the list going shorter is the visible
    // evidence of that. What remains is not a deferral at all: jsdom has no layout engine, so
    // `color-contrast` is unevaluable there whatever the code does.
    expect(Object.keys(KNOWN_OPEN_RULES).sort()).toEqual(["color-contrast"]);
    for (const [rule, reason] of Object.entries(KNOWN_OPEN_RULES)) {
      expect(reason, `the exclusion of "${rule}" must explain itself`).toMatch(/jsdom/);
    }
  });

  it("every supplement finding recorded as FIXED no longer reproduces", async () => {
    // The other half of the record. A `fixed` claim that nobody re-checks is just a claim; this walks
    // the list and proves each one is actually gone, so reverting a fix fails here.
    expect(FIXED.length, "the fixed list should hold S1").toBeGreaterThan(0);
    const { container } = render(
      <RatioBar label="Debt to GDP" valueText="62.4%" ratioBps={6240} />,
    );
    const results = await analyze(container);
    assertRulesActuallyRan(results, "RatioBar");
    const stillFailing = results.violations.map((v) => v.id);
    for (const finding of FIXED) {
      expect(
        stillFailing,
        `${finding.id} is recorded as fixed in ${finding.fixedIn} but ${finding.ruleId} still fires`,
      ).not.toContain(finding.ruleId);
    }
  });

  it("no supplement finding is left OPEN", () => {
    // Commit 3 closed S1, so this is empty. If a later commit records a new open finding it must also
    // add its reproducing test, and this assertion is the reminder.
    expect(OPEN).toEqual([]);
  });

  it("Panel is structurally clean", async () => {
    const { container } = render(
      <Panel title="Treasury" headingLevel={2}>
        <p>Body copy.</p>
      </Panel>,
    );
    const results = await analyze(container);
    assertRulesActuallyRan(results, "Panel");
    expect(describeViolations(results)).toBe("");
  });

  it("DataTable is structurally clean, caption and column scopes included", async () => {
    const { container } = render(
      <DataTable
        caption="Revenue by source"
        columns={["Source", "Amount"]}
        rows={[
          { key: "a", cells: ["Income tax", "120"] },
          { key: "b", cells: ["VAT", "80"] },
        ]}
      />,
    );
    const results = await analyze(container);
    assertRulesActuallyRan(results, "DataTable");
    expect(describeViolations(results)).toBe("");
  });

  it("ToneValue and DeltaText never carry meaning by colour alone", async () => {
    const { container } = render(
      <p>
        <ToneValue tone="positive">Surplus</ToneValue>{" "}
        <DeltaText deltaText="+3.2" direction="up" />
      </p>,
    );
    const results = await analyze(container);
    assertRulesActuallyRan(results, "ToneValue and DeltaText");
    expect(describeViolations(results)).toBe("");

    // The never-colour-alone rule is a structural property axe does not check, so it is asserted
    // directly: a glyph for sighted users, a visually-hidden word for everyone else.
    expect(container.querySelector('[aria-hidden="true"]')).not.toBeNull();
    expect(container.querySelector(".sr-only")?.textContent).toBeTruthy();
  });

  it("EmptyNote is structurally clean", async () => {
    const { container } = render(<EmptyNote>No promises outstanding.</EmptyNote>);
    const results = await analyze(container);
    assertRulesActuallyRan(results, "EmptyNote");
    expect(describeViolations(results)).toBe("");
  });

  /**
   * S1 — A DEFECT THIS SUPPLEMENT FOUND AND THE BROWSER SWEEP COULD NOT.
   *
   * `RatioBar` declares `role="meter"` with `aria-label` and `aria-valuetext` but **no
   * `aria-valuenow`**, which ARIA requires for that role. axe rates it `critical`.
   *
   * The browser sweep did not report it, and the reason is not a gap in the sweep: **nothing renders
   * `RatioBar`.** It is exported from `components.tsx` and has no call site anywhere in `src/`, so no
   * screen can exhibit the defect and no screen-level audit could ever have found it. That is
   * precisely the case the frozen plan wanted a per-component supplement for.
   *
   * FIXED in Commit 3. This test was a CHARACTERISATION of the defect while Commit 2 recorded without
   * fixing; it is now the regression test for the fix, asserting the component is clean and that all
   * three value attributes a `meter` needs are present. The value of S1 does not evaporate with the
   * fix -- it is the standing evidence that a component-level audit reaches what a screen-level one
   * cannot -- so it stays on the record in `a11y.supplement-findings.json` under `fixed`.
   */
  it("RatioBar's meter carries the ARIA a meter role requires (S1, fixed)", async () => {
    const { container } = render(
      <RatioBar label="Debt to GDP" valueText="62.4%" ratioBps={6240} />,
    );
    const results = await analyze(container);
    assertRulesActuallyRan(results, "RatioBar");
    expect(describeViolations(results)).toBe("");

    const meter = container.querySelector('[role="meter"]');
    expect(meter, "RatioBar should render a meter").not.toBeNull();
    // `aria-valuenow` is the numeric value and `aria-valuetext` the human form -- the division of
    // labour ARIA intends, and the reason the raw basis-point figure is the right `valuenow`.
    expect(meter?.getAttribute("aria-valuenow")).toBe("6240");
    expect(meter?.getAttribute("aria-valuemin")).toBe("0");
    expect(meter?.getAttribute("aria-valuemax")).toBe("10000");
    expect(meter?.getAttribute("aria-valuetext")).toBe("62.4%");
    expect(meter?.getAttribute("aria-label")).toBe("Debt to GDP");
  });

  it("RatioBar is unused, which is why only a component-level audit could find S1", () => {
    // The claim S1's reasoning rests on, asserted rather than left in a comment. If a screen ever
    // starts rendering RatioBar, this fails and S1 is promoted to a real user-facing defect that the
    // browser sweep must also see.
    //
    // `import.meta.glob` with `query: "?raw"` reads the sources at build time, which is how
    // `format-boundary.test.ts` already inspects sibling files from inside a test.
    const sources = import.meta.glob("./**/*.{ts,tsx}", {
      query: "?raw",
      import: "default",
      eager: true,
    }) as Record<string, string>;

    const callSites = Object.entries(sources).filter(
      ([file, text]) =>
        !file.includes("a11y.components.test") &&
        !file.endsWith("components.tsx") &&
        /<RatioBar[\s/>]/.test(text),
    );
    expect(
      callSites.map(([file]) => file),
      "RatioBar now has a call site, so S1 is user-facing and belongs in the browser baseline too",
    ).toEqual([]);
  });

  /**
   * I1 — `DeltaText` IS UNRENDERED TOO, and Commit 4's record said otherwise.
   *
   * Commit 4's icon docstring and its review record both described the direction icons as rendering
   * "inside `DeltaText` (`text-parchment-200/70`) and inside the policy cards' effect chips". The
   * second half is right; the first names a component **nothing renders**. `DeltaText` is exported from
   * `components.tsx` and has no call site anywhere in `src/` — the Dashboard concern card renders
   * `concern.delta_text` as plain text and discards `concern.direction` entirely.
   *
   * So `DIRECTION_ICON` reaches the DOM through the effect chips ALONE, at `text-parchment-200/80`, and
   * the `/70` figure Commit 4 quoted for it described a context that never paints. Commit 4a measured
   * the real one at 8.78:1.
   *
   * This joins `RatioBar` as the second exported-but-unrendered component, which is why it is asserted
   * here rather than left as prose: a claim about what does not exist rots silently.
   */
  it("DeltaText is unused, so the effect chips are the only direction-icon placement (I1)", () => {
    const sources = import.meta.glob("./**/*.{ts,tsx}", {
      query: "?raw",
      import: "default",
      eager: true,
    }) as Record<string, string>;

    const callSites = Object.entries(sources).filter(
      ([file, text]) =>
        !file.includes("a11y.components.test") &&
        !file.includes("icons.test") &&
        !file.endsWith("components.tsx") &&
        /<DeltaText[\s/>]/.test(text),
    );
    expect(
      callSites.map(([file]) => file),
      "DeltaText now has a call site, so it IS a live direction-icon placement and its own backdrop " +
        "must be added to EXPECTED_BACKDROP in e2e/contrast-probe.ts and measured",
    ).toEqual([]);
  });
});
