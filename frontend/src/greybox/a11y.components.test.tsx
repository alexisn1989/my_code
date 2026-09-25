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
 * artifact renders this same file, so the report and the test cannot disagree about what is open. */
const S1 = supplement.findings.find((f) => f.id === "S1");

/**
 * Rules the REAL-BROWSER baseline already records as open, disabled here by name so this suite is
 * green while Commit 2 records rather than fixes. Each entry names the finding it defers to; none is
 * a judgement that the defect is acceptable.
 */
const KNOWN_OPEN_RULES: Record<string, string> = {
  region:
    "A2-A15: one shell-level landmark defect observed on every screen. Not reachable from an " +
    "isolated component anyway, since landmarks live in the app shell.",
  "aria-valid-attr-value":
    "A8: the Decisions policy tabs build `aria-controls` from a label containing a space, so it " +
    "references an id that does not exist.",
  "color-contrast":
    "A1 and A9. Disabled for a second, independent reason: jsdom cannot evaluate contrast at all, " +
    "so a pass here would be meaningless rather than merely incomplete.",
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
  it("the known-open list names only rules the browser baseline actually recorded", () => {
    // Guards against the allowlist quietly growing into a way to keep this file green. Every entry
    // must cite a finding id from the committed artifact, so adding a rule here without a recorded
    // browser finding fails.
    for (const [rule, reason] of Object.entries(KNOWN_OPEN_RULES)) {
      expect(reason, `the exclusion of "${rule}" must cite its finding id`).toMatch(/A\d+/);
    }
    // Pinned by count so a silent addition is a failure rather than a diff nobody reads.
    expect(Object.keys(KNOWN_OPEN_RULES).sort()).toEqual([
      "aria-valid-attr-value",
      "color-contrast",
      "region",
    ]);
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
   * Recorded, NOT fixed — Commit 2 records and Commit 3 fixes (§9.1). This test therefore
   * CHARACTERISES the current defect rather than asserting cleanliness: it stays green while the
   * defect stands, and it fails the moment the defect changes, which forces Commit 3 to come back
   * here. Commit 3's choice is to add `aria-valuenow` or to delete the unused component; either way
   * this test must be updated, and that is the intended pressure.
   */
  it("RatioBar has a recorded, unfixed ARIA defect (S1) — characterised, not fixed", async () => {
    const { container } = render(
      <RatioBar label="Debt to GDP" valueText="62.4%" ratioBps={6240} />,
    );
    const results = await analyze(container);
    assertRulesActuallyRan(results, "RatioBar");

    // Exactly one violation, and exactly the one on record — read FROM the declaration the report
    // also renders, so the artifact cannot claim a defect axe does not actually produce, nor miss one
    // it does. Asserting the precise set is what makes this a characterisation rather than a blanket
    // exemption: a NEW defect in this component still fails here.
    expect(S1, "S1 must be declared in a11y.supplement-findings.json").toBeDefined();
    expect(results.violations.map((v) => v.id)).toEqual([S1?.ruleId]);
    expect(results.violations[0]?.impact).toBe(S1?.impact);

    // The missing attribute, named, so the finding is actionable without re-running axe.
    const meter = container.querySelector('[role="meter"]');
    expect(meter, "RatioBar should still render a meter").not.toBeNull();
    expect(meter?.getAttribute("aria-valuenow"), "S1: the required aria-valuenow is absent").toBeNull();
    expect(meter?.getAttribute("aria-valuetext")).toBe("62.4%");
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
});
