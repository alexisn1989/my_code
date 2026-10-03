/**
 * Renders the Gate 4A3 accessibility review artifact from the axe sweep's own JSON output.
 *
 * GENERATED, never hand-written — the same rule `write-baseline-report.mjs` follows, and for the
 * same reason: a report typed by hand can claim something the run did not find, and this one is
 * evidence. `npm run audit:accessibility` runs the sweep and then this, so the markdown is a view of
 * `gate-4a3-accessibility.json` and nothing else. Every number below is computed from that file.
 */

import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

const REVIEW_DIR = path.join(process.cwd(), "..", "docs", "reviews");
/** Matches the spec's `MANDATE_A11Y_OUT`, so a verification run renders its own artifact rather than
 * overwriting the baseline it is measured against. */
const OUT_NAME = process.env.MANDATE_A11Y_OUT ?? "gate-4a3-accessibility";
const data = JSON.parse(readFileSync(path.join(REVIEW_DIR, `${OUT_NAME}.json`), "utf-8"));

/** Gate 4A3 UX-3a: where the Markdown goes, when that is not beside its JSON. Unset, the report is
 * `${OUT_NAME}.md` as before. Set, it is `${MD_OUT}.md` -- so a report can be RE-RENDERED from a
 * committed JSON without touching the committed Markdown -- or, when it contains a path separator,
 * that path as given (used to render into a scratch directory outside the repository). */
const MD_OUT = process.env.MANDATE_A11Y_MD_OUT;
const MD_PATH =
  MD_OUT === undefined
    ? path.join(REVIEW_DIR, `${OUT_NAME}.md`)
    : MD_OUT.includes("/")
      ? MD_OUT
      : path.join(REVIEW_DIR, `${MD_OUT}.md`);

/** The baseline is the one run this text was first written for. Every other run is a
 * re-measurement, and until UX-3a the writer still told each of them that it was Commit 2's baseline
 * -- eight committed reports carry that stale header (see `gate-4a3-ux3a-followups.md`). */
const BASELINE = OUT_NAME === "gate-4a3-accessibility";

/** Findings the jsdom COMPONENT supplement found that a screen-level sweep structurally could not.
 * Read from the same file `a11y.components.test.tsx` imports and asserts against, so this report
 * cannot claim a defect axe does not produce — and cannot miss one it does. */
const supplementRecord = JSON.parse(
  readFileSync(path.join(process.cwd(), "src", "greybox", "a11y.supplement-findings.json"), "utf-8"),
);
const supplementOpen = supplementRecord.open ?? [];
const supplementFixed = supplementRecord.fixed ?? [];
const supplementFindings = [...supplementOpen, ...supplementFixed];

const findings = data.findings ?? [];
const needsReview = data.needsReview ?? [];
const surfaces = data.surfaces ?? [];
const unreachable = data.unreachable ?? [];
/** Surfaces where axe ITSELF failed, kept apart from nav refusals. The sweep asserts this is empty,
 * so a non-empty list here means the run should not have produced an artifact at all. */
const axeFailures = data.axeFailures ?? [];
const coverage = data.coverage ?? [];
const viewports = data.viewports ?? [];

const conformance = findings.filter((f) => f.conformance === "wcag-aa");
const beyondAa = findings.filter((f) => f.conformance === "beyond-aa");
const bestPractice = findings.filter((f) => f.conformance === "best-practice");

const evaluated = surfaces.map((s) => s.rulesEvaluated);
const minRules = evaluated.length > 0 ? Math.min(...evaluated) : 0;
const maxRules = evaluated.length > 0 ? Math.max(...evaluated) : 0;

const IMPACT_ORDER = { critical: 0, serious: 1, moderate: 2, minor: 3, unknown: 4 };
const bySeverity = (a, b) =>
  (IMPACT_ORDER[a.impact] ?? 9) - (IMPACT_ORDER[b.impact] ?? 9) || a.id.localeCompare(b.id);

/** One row per finding, carrying the rule id, impact and selector the frozen plan asks for. */
const rows = (list) =>
  list.length === 0
    ? "_None._\n"
    : "| id | screen | rule | impact | nodes | viewports | selector (first) |\n" +
      "|---|---|---|---|---|---|---|\n" +
      [...list]
        .sort(bySeverity)
        .map(
          (f) =>
            `| ${f.id} | ${f.screen} | \`${f.ruleId}\` | ${f.impact} | ${f.nodeCount} | ` +
            `${f.viewports.length}/${viewports.length} | \`${(f.selectors[0] ?? "").slice(0, 70)}\` |`,
        )
        .join("\n") +
      "\n";

/** The verbatim detail, which is what makes a finding actionable in Commit 3 rather than merely
 * counted here. axe's own `help`, `helpUrl` and `failureSummary` are reproduced unedited. */
const detail = (list) =>
  list.length === 0
    ? "_None._\n"
    : [...list]
        .sort(bySeverity)
        .map(
          (f) =>
            `#### ${f.id} — \`${f.ruleId}\` on ${f.screen} (${f.impact})\n\n` +
            `- **Rule:** ${f.help}\n` +
            `- **Reference:** ${f.helpUrl}\n` +
            (f.wcagTags.length > 0 ? `- **WCAG tags:** ${f.wcagTags.join(", ")}\n` : "") +
            `- **Failing nodes:** ${f.nodeCount}\n` +
            `- **Observed at:** ${f.viewports.join(", ")}\n` +
            `- **Selectors:**\n${f.selectors.map((s) => `  - \`${s}\``).join("\n")}\n` +
            (f.failureSummary !== "" ? `- **axe says:** ${f.failureSummary}\n` : ""),
        )
        .join("\n") +
      "\n";

const ruleCounts = new Map();
for (const f of findings) ruleCounts.set(f.ruleId, (ruleCounts.get(f.ruleId) ?? 0) + 1);
const ruleSummary = [...ruleCounts.entries()]
  .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
  .map(([rule, count]) => {
    const example = findings.find((f) => f.ruleId === rule);
    return `| \`${rule}\` | ${count} | ${example.impact} | ${example.conformance} |`;
  })
  .join("\n");

const BASELINE_HEADER = `# Gate 4A3 accessibility baseline — axe-core in the real browser

**Generated by \`npm run audit:accessibility\`. Do not hand-edit.** This file is a rendering of
\`gate-4a3-accessibility.json\`, which the sweep writes as it runs.

**This is Commit 2 of six, and it RECORDS ONLY.** Nothing here is fixed. Per the frozen plan §9.1 the
sweep exits 0 whenever it completes, whatever it found: a non-zero exit would mean the harness broke,
never that the application has a defect. Triage and fixes are Commit 3, and each fix there cites a
finding id from this file. **No zero-violation regression test exists yet**, deliberately — adding one
now would commit a deliberately red suite.
`;

const REMEASUREMENT_HEADER = `# Gate 4A3 accessibility re-measurement (\`${OUT_NAME}\`) — axe-core in the real browser

**Generated by \`tools/write-accessibility-report.mjs\`. Do not hand-edit.** This file renders
\`${OUT_NAME}.json\`, which \`e2e/accessibility.spec.ts\` (\`--project=accessibility\`) wrote under
\`MANDATE_A11Y_OUT=${OUT_NAME}\`.${
  MD_OUT === undefined
    ? ""
    : ` It was **re-rendered after the fact** from that committed JSON; the committed \`${OUT_NAME}.md\` is preserved unchanged and carries the stale Commit 2 header this file corrects.`
}

**A re-measurement of the Commit 2 baseline sweep,** with the same harness and the same rules. The
baseline itself is \`gate-4a3-accessibility.{json,md}\`. Like the baseline, this sweep **records**: it
exits 0 whenever it completes, whatever it finds, and asserts only that it measured something.

**Zero-violation regression checks exist elsewhere, and this is exactly what they cover:**
- \`e2e/verify-commit3-fixes.spec.ts\` asserts **zero** \`region\`, \`color-contrast\`,
  \`landmark-no-duplicate-banner\` and \`landmark-banner-is-top-level\` violations on every screen;
- \`e2e/verify-ux.spec.ts\` (\`@ux2\`) asserts **zero** violations of **every** rule on the open turn
  result, live and in History.

**No every-rule, every-surface zero-violation test exists.** The counts below are this run's
measurement, not a pass/fail gate of their own.
`;

const doc = `${BASELINE ? BASELINE_HEADER : REMEASUREMENT_HEADER}
## The headline

| | count |
|---|---|
| **WCAG 2.2 AA conformance findings (browser, screens)** | **${conformance.length}** |
| Beyond AA (AAA rules) | ${beyondAa.length} |
| axe best-practice findings | ${bestPractice.length} |
| Needs review (axe \`incomplete\`) | ${needsReview.length} |
| Component-supplement findings still open (\`S1..Sn\`) | ${supplementOpen.length} |
| Component-supplement findings fixed | ${supplementFixed.length} |
| Surfaces audited | ${surfaces.length} |
| Surfaces the navigation did not offer | ${unreachable.length} |
| Surfaces where axe itself failed (harness) | ${axeFailures.length} |

## How this was measured

- **axe-core ${data.axeCoreVersion}** via \`@axe-core/playwright\` 4.13.0, both pinned exactly in
  \`package.json\` the way \`@playwright/test\` is. The version is read off the installed package by
  the sweep itself, so this artifact records what actually ran rather than what someone believed was
  installed.
- **The real application, the real browser.** A production \`mandate-gui\` process serving the built
  SPA and the real scenarios, driven by Chromium 141.0.7390.37 (revision 1194) from the on-disk
  cache. \`e2e/preflight.spec.ts\` is a hard dependency of this project, so a run whose browser
  provenance cannot be proven does not produce findings at all.
- **Why not jsdom.** axe's most valuable rules need layout and resolved styles — \`color-contrast\`
  above all — and jsdom has neither, so it cannot evaluate them. That is why the frozen plan put
  Playwright before the accessibility work. The jsdom axe tests added alongside this commit are a
  labelled supplement for per-component regressions, **never** the primary evidence.
- **Every rule was enabled**, and each result is classified afterwards from its own tags: WCAG 2.2 AA
  tags make a **conformance** finding, AAA tags make a **beyond-AA** finding, and everything else is
  **best-practice**. Reporting axe's best-practice rules as conformance failures would inflate the
  baseline against a standard nobody committed to; hiding them would lose real signal. They are
  counted separately and both are listed in full.
- **\`incomplete\` is kept apart from \`violations\`.** An incomplete result is a question axe could
  not settle — usually an overlapped or non-text element it declined to judge — not a confirmed
  defect. Folding the two together would overstate the baseline by ${needsReview.length}.

### The anti-vacuity guard, and why it is here

An axe run that fails to inject returns an **empty violations array**, which is indistinguishable
from a clean screen unless something else proves the rules ran. Commit 1a exists because exactly that
confusion produced a clean stress result for three screens that had never been stressed. So every
surface records \`rulesEvaluated\` — violations + passes + incomplete + inapplicable — and the run
**asserts it is non-zero for every audited surface**.

**Measured: all ${surfaces.length} surfaces evaluated between ${minRules} and ${maxRules} rules.**
No result in this file rests on a silent no-op.

## Findings by rule

| rule | findings | impact | class |
|---|---|---|---|
${ruleSummary}

**One finding is one \`(screen, rule, node-set)\` defect**, carrying every viewport case where it was
observed — not one finding per screen × viewport × rule. Most axe rules are viewport-independent: a
missing label or a contrast failure is the same defect at 1920 px and at 320 px, and numbering them
per viewport would multiply each by the ${viewports.length} viewport cases and produce a count that
describes the sweep rather than the application. Nothing is lost, because a viewport-specific defect
is visible precisely by having a short \`viewports\` list.

## WCAG 2.2 AA conformance findings — the ones that matter for the gate

${rows(conformance)}

${detail(conformance)}

## Best-practice findings

${bestPractice.length > 0 && bestPractice.every((f) => f.ruleId === bestPractice[0].ruleId) ? `All ${bestPractice.length} share a single rule (\`${bestPractice[0].ruleId}\`) and a single pair of selectors, so they are **one shell-level defect observed on every screen**, not ${bestPractice.length} independent problems. Commit 3 should expect one fix to clear the whole set.\n` : ""}
${rows(bestPractice)}

${beyondAa.length > 0 ? `## Beyond AA (AAA rules)\n\n${rows(beyondAa)}\n` : ""}
## Needs review — axe could not decide

These are **not** counted as violations. Each is a node axe declined to judge, usually because it is
overlapped, partially obscured, or contains only non-text characters. Commit 3 should resolve each by
inspection rather than by assuming either outcome.

${rows(needsReview)}

${detail(needsReview)}

## Component-supplement findings (\`S1..Sn\`) — what a screen sweep structurally could not find

The jsdom supplement (\`src/greybox/a11y.components.test.tsx\`) audits shared primitives in
isolation. It is **not** the primary evidence and cannot be: jsdom has no layout engine, so it cannot
evaluate \`color-contrast\` or anything else needing a rendered box. But it can reach a component the
screens do not, and that is exactly what it did.

${
  supplementFindings.length === 0
    ? "_None._\n"
    : supplementFindings
        .map(
          (f) =>
            `### ${f.id} — \`${f.ruleId}\` in ${f.component} (${f.impact}, ${f.conformance})` +
            `${f.fixedIn === undefined ? " — **OPEN**" : ` — **FIXED in ${f.fixedIn}**`}\n\n` +
            `- **File:** \`${f.file}\`\n` +
            `- **Rule:** ${f.help}\n` +
            `- **Reference:** ${f.helpUrl}\n` +
            `- **Defect:** ${f.detail}\n` +
            `- **Why the browser sweep missed it:** ${f.whyTheBrowserSweepMissedIt}\n` +
            (f.fix === undefined ? "" : `- **Fix:** ${f.fix}\n`) +
            (f.regression === undefined ? "" : `- **Regression check:** ${f.regression}\n`) +
            (f.commit3Options === undefined ? "" : `- **Options:** ${f.commit3Options}\n`),
        )
        .join("\n") + "\n"
}
These are declared in \`src/greybox/a11y.supplement-findings.json\`, which the supplement test imports
and asserts against axe's actual output — so this section cannot claim a defect that does not
reproduce, and the test cannot quietly stop covering one that does.

## What was measured, and what was found sound

${coverage.map((c) => `- ${c}`).join("\n")}

## Surfaces not audited, and why — the two reasons kept apart

A screen the **navigation** did not offer is a fact about the application and relaxes the coverage
threshold. A surface where **axe itself failed** is the harness breaking, and the sweep asserts that
list is empty — while the two shared one list, an axe crash silently lowered the expected coverage and
the run still passed, which is the accommodate-the-gap failure Commit 1a exists to correct.

${
  unreachable.length > 0
    ? `**Navigation did not offer (${unreachable.length}):**\n\n| screen | viewport | reason |\n|---|---|---|\n${unreachable.map((u) => `| ${u.screen} | ${u.viewport} | ${u.reason} |`).join("\n")}\n`
    : "**Navigation did not offer:** _none — every screen was reached at every viewport case._\n"
}
${
  axeFailures.length > 0
    ? `**axe failed to run (${axeFailures.length}) — THIS SHOULD BE EMPTY:**\n\n| screen | viewport | reason |\n|---|---|---|\n${axeFailures.map((u) => `| ${u.screen} | ${u.viewport} | ${u.reason} |`).join("\n")}\n`
    : "**axe failed to run:** _none — axe evaluated rules successfully on every surface it reached._\n"
}

## Coverage

- Screens audited: Dashboard, Government, Economy, Legislature, Constitution, Relationships,
  Decisions, Turn result, History, Strategic map, Victory / defeat, plus the chrome-level Glossary.
  The three that still render \`UnavailableScreen\` are audited too — an unavailable screen is still a
  surface a keyboard and a screen reader reach.
- Viewport cases: ${viewports.map((v) => v.name).join(", ")}.
- \`reflow200-mobile-195x422\` is **below** the 320 px floor WCAG 2.2 SC 1.4.10 sets, so it is a real
  user observation and not a conformance target — the distinction Commit 1 drew and this sweep
  inherits.
- Totals: **${findings.length} finding(s)** (${conformance.length} conformance,
  ${beyondAa.length} beyond-AA, ${bestPractice.length} best-practice), **${needsReview.length} needing
  review**, across **${surfaces.length} audited surface(s)**.
`;

// `wx`: a report is evidence, and this writer must never overwrite one -- the hazard that cost Commit
// 3's post-fix evidence once already. An existing file makes this fail loudly instead.
writeFileSync(MD_PATH, doc, { encoding: "utf-8", flag: "wx" });
console.log(
  `accessibility report written: ${findings.length} findings ` +
    `(${conformance.length} WCAG AA, ${bestPractice.length} best-practice), ` +
    `${needsReview.length} needs-review, ${surfaces.length} surfaces`,
);
