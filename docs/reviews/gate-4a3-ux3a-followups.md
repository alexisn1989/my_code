# Gate 4A3 UX-3a: two UX-3 follow-ups, closed

This is a forward-only commit on top of UX-3 (`9c08dac`). It closes the two items from the user's
review of `9c08dac`, which had to close before release verification:
1. the approved check that the rendered tint changes when legitimacy changes had never been made;
2. the accessibility Markdown reports stated the wrong provenance.

The commit adds a browser check, fixes the report writer, adds a corrected report and records an
erratum. It does not change any application source (`src/`), backend, scenario, contract or
committed artifact.

## 1. The tint follows legitimacy after a turn (`e2e/verify-ux.spec.ts`, `@ux3`)

**What was missing.** `@ux3` read the tint only before any turn was resolved. The approved plan asked
for proof that the rendered tint changes with legitimacy.

**The check.**
- **Before the block's one turn,** it records:
  - the API's `map.tint_value_bps` and `concerns.legitimacy.headline`;
  - the box's `data-tint-bps` and accessible name;
  - the mix percentage in its inline style;
  - its computed `backgroundColor`.
- **After "Plan turn N",** it reads the API again, returns to the Dashboard, and asserts:
  - **non-vacuity first:** `tint_value_bps` and the legitimacy headline both changed. A turn that
    stopped moving legitimacy fails here; it does not pass on two equal tints;
  - the metric is "Legitimacy" both times;
  - `data-tint-bps` shows the new value;
  - the accessible name states the new legitimacy;
  - the inline mix equals `expectedMixPercent(bps)` for each value. That function restates
    `format.ts`'s rule in the test (15 at 0 bps, 60 at 10,000, linear, clamped), so the check is an
    independent computation and not a self-comparison;
  - the mix and the **computed fill** both differ from before;
  - the country name is still the only text on the tint, on its `navy-950` label, at ≥ 4.5:1.

**Measured** (`gate-4a3-ux3a-verify-ux.json`, identical at 1440, 390 and 320):

| | legitimacy | `data-tint-bps` | mix | computed fill |
|---|---|---:|---:|---|
| before | 60.00% | 6000 | 42% | `oklab(0.341267 0.00420278 0.025815)` |
| after one turn | 61.00% | 6100 | 42.45% | `oklab(0.34311 0.00426987 0.0263533)` |

**The check bites.** I froze the tint in the component to `tintFill(6000)`, rebuilt, and ran
`@ux3`. It failed at the post-turn assertion: "the authored mix follows the rule", expected 42.45,
received 42. I then restored the component (verified with `cmp`) and rebuilt. The bundle returned to
the same hashes (`index-s42Jmb-m.js`, `index-ClnHb-Eg.css`), and the scratch artifact was removed.

## 2. The accessibility reports state what actually ran

**What was wrong.** `frontend/tools/write-accessibility-report.mjs` hard-coded the Commit 2 header
into every report, whatever run it rendered:
- "This file is a rendering of `gate-4a3-accessibility.json`";
- "**This is Commit 2 of six, and it RECORDS ONLY.** … Triage and fixes are Commit 3";
- "**No zero-violation regression test exists yet**".

Every re-measurement since Commit 3 therefore described itself as the baseline, cited the wrong JSON
file, and denied regression tests that exist. **Measured: eight committed reports carry it, not one**
(erratum, §3).

**The fix.**
- **Baseline mode** applies when `MANDATE_A11Y_OUT` is the baseline name, `gate-4a3-accessibility`.
  It keeps the Commit 2 header **verbatim**, because for that run it is true.
- **Re-measurement mode** applies to every other name. It titles the report with its own artifact
  name and states:
  - that it renders `${OUT_NAME}.json`, written by `e2e/accessibility.spec.ts` under that
    `MANDATE_A11Y_OUT`;
  - that it is a re-measurement of the Commit 2 sweep, which records and does not fail on a finding;
  - **exactly which zero-violation regression checks exist,** read from the specs:
    `verify-commit3-fixes.spec.ts` asserts zero `region`, `color-contrast`,
    `landmark-no-duplicate-banner` and `landmark-banner-is-top-level` violations on every screen, and
    `verify-ux.spec.ts` `@ux2` asserts zero violations of every rule on the open turn result, live
    and in History;
  - **and that no every-rule, every-surface zero-violation test exists**, which is still true.
- **`MANDATE_A11Y_MD_OUT`** (optional) writes the Markdown under another name, or to a path outside
  the repository. When it renders a committed JSON under a new name, the header says it was
  re-rendered after the fact and that the committed `.md` is preserved.
- **The Markdown is written with `flag: "wx"`.** A second `npm run report:accessibility:ux3-corrected`
  exited **1** on the existing file, so the writer can no longer overwrite a report.
  - The sweep's own JSON write still overwrites. That is the known npm default-name hazard, still
    owed, and it is not changed here.

**The baseline is unaffected.** I rendered the baseline JSON to a scratch path with the new writer,
then ran the **unchanged HEAD writer** on the same inputs, in an isolated copy outside the
repository. The two outputs are **byte-identical**.

Both differ from the committed `gate-4a3-accessibility.md`, but **only** in the component-supplement
section. That is pre-existing drift: Commit 3 (`b909032`) recorded S1 as fixed in
`a11y.supplement-findings.json` after the baseline Markdown was written. It is reported here, not
introduced or hidden. The same isolated copy of the unchanged writer **reproduces the committed
`…-after-ux3.md` byte for byte**, so the corrected report's diff below can come only from the header.

## 3. The corrected artifact, and the erratum

**`gate-4a3-accessibility-after-ux3-corrected.md`** is new. `npm run report:accessibility:ux3-corrected`
rendered it from the **committed** `gate-4a3-accessibility-after-ux3.json`. Its full diff against the
preserved `gate-4a3-accessibility-after-ux3.md` touches **lines 1–18 only**: the title and the header
paragraphs. Every table, count, finding and needs-review row is identical:

```
1c1   title: "accessibility baseline" → "accessibility re-measurement (`gate-4a3-accessibility-after-ux3`)"
3,4c3,5   provenance: renders gate-4a3-accessibility-after-ux3.json, written by e2e/accessibility.spec.ts
          under MANDATE_A11Y_OUT=gate-4a3-accessibility-after-ux3; re-rendered after the fact; the
          committed .md is preserved
6,10c7,18 "This is Commit 2 of six … No zero-violation regression test exists yet" → the
          re-measurement statement, the two regression checks that exist and their exact scope,
          and "No every-rule, every-surface zero-violation test exists."
```

**A live run shows the same header.** `audit:accessibility:verify:ux3a` ran the sweep and the fixed
writer end to end. Its `gate-4a3-accessibility-after-ux3a.json` is **byte-identical** to UX-3's JSON
(the bundle is unchanged). Its Markdown differs from the corrected UX-3 report only in the artifact
name and in the absence of the "re-rendered" sentence.

**Erratum: eight committed reports state the wrong provenance.** All eight are **preserved
byte-identical**. Their JSON evidence, and every count in them, is unaffected; only the header text
is wrong. Each one falsely claims to be:
- (a) a rendering of `gate-4a3-accessibility.json`;
- (b) "Commit 2 of six", recording only, with fixes still to come in Commit 3;
- (c) a record with no zero-violation regression test.

| report | blob | produced by | in commit | true provenance |
|---|---|---|---|---|
| `gate-4a3-accessibility-after-commit3.md` | `bd75fe5ae913` | `npm run audit:accessibility:verify` | `b909032` (3/6) | renders `…-after-commit3.json`; Commit 3's post-fix re-measurement |
| `gate-4a3-accessibility-after-commit4.md` | `67c106be2b5d` | `…:verify:commit4` | `b1b12f6` (4/6) | renders `…-after-commit4.json` |
| `gate-4a3-accessibility-after-commit5.md` | `67c106be2b5d` | `…:verify:commit5` | `5e61b94` (5/6) | renders `…-after-commit5.json` |
| `gate-4a3-accessibility-after-commit5b.md` | `67c106be2b5d` | `…:verify:commit5b` | `abcc9a9` (5b/6) | renders `…-after-commit5b.json` |
| `gate-4a3-accessibility-after-commit6.md` | `67c106be2b5d` | `…:verify:commit6` | `fb19b5f` (6/6) | renders `…-after-commit6.json` |
| `gate-4a3-accessibility-after-ux1.md` | `67c106be2b5d` | `…:verify:ux1` | `bf66b8e` (UX-1) | renders `…-after-ux1.json` |
| `gate-4a3-accessibility-after-ux2.md` | `67c106be2b5d` | `…:verify:ux2` | `99c8f73` (UX-2) | renders `…-after-ux2.json` |
| `gate-4a3-accessibility-after-ux3.md` | `feb8b8e10477` | `…:verify:ux3` | `9c08dac` (UX-3) | renders `…-after-ux3.json`; **corrected copy:** `…-after-ux3-corrected.md` |

From Commit 3 on, claim (c) is false for the rules `verify-commit3-fixes.spec.ts` asserts. From UX-2
on, it is also false for the open turn result. Six reports share one blob because their measurements
did not change between those commits. Corrected copies of the other seven can be rendered the same
way, under new names, if wanted.

## 4. Gates

Each gate was run separately, and each exit status is the command's own `$?`.

| command | exit | result |
|---|---:|---|
| `npm test` | 0 | `Tests  541 passed (541)`: unchanged, because no `src/` change |
| `npm run typecheck` | 0 | clean |
| `npm run build` | 0 | **byte-identical by hash to UX-3**: `index-s42Jmb-m.js`, `index-ClnHb-Eg.css` |
| `npm run check:bundle` | 0 | `check-bundle: OK -- … initial JS 98.52 KiB gzip …` |
| `npm run check:palette` | 0 | `check-palette: OK -- 41 source file(s), 16 colour token(s) defined, …` |
| `npm run check:copy` | 0 | `check-copy OK: 344 player-visible strings across 41 files, 15 forbidden words, whole-word matched.` |
| `npm run check:css-sources` | 0 | `check-css-sources: OK -- …` |
| `npm run report:accessibility:ux3-corrected` | 0 | `0 findings (0 WCAG AA, 0 best-practice), 4 needs-review, 89 surfaces`; a second run exits **1** (`wx`) |
| `npm run verify:ux:3a` | 0 | `14 passed (29.3s)`: `@ux1`, `@ux2` and `@ux3` at three viewports each, plus preflight |
| `npm run verify:campaigns:ux3a` | 0 | `7 passed (23.4s)` |
| `npm run verify:terminal:ux3a` | 0 | `6 passed (32.1s)` |
| `npm run verify:fixes:ux3a` | 0 | `13 passed (36.7s)` |
| `npm run verify:icons:ux3a` | 0 | `7 passed (10.8s)` |
| `npm run audit:stress:seated:ux3a` | 0 | `6 passed (6.0s)` |
| `npm run audit:accessibility:verify:ux3a` | 0 | `6 passed (1.3m)`; `0 findings (0 WCAG AA, 0 best-practice), 4 needs-review, 89 surfaces` |

**Not run, and why.** No backend code, backend test, scenario or contract changed, so neither the
backend suite nor `generate:api` was re-run. UX-3's suite (36,380 passed) stands.

**Artifacts compared with UX-3's:**

| artifact | disposition |
|---|---|
| `gate-4a3-ux3a-verification.json`, `-icon-coverage.json`, `-terminal.json`, `-campaigns.json`, `-stress-seated-cabinet.json` and both screenshots | **byte-identical** to their UX-3 counterparts |
| `gate-4a3-accessibility-after-ux3a.json` | **byte-identical** to `…-after-ux3.json` |
| `gate-4a3-accessibility-after-ux3a.md` | the fixed header, as in §3 |
| `gate-4a3-ux3a-verify-ux.json` | 4 differences from UX-3's: `out`, and one `tintAcrossTurn` entry added per viewport |

## 5. Scope

- **e2e:** `verify-ux.spec.ts` (`@ux3` only).
- **tools:** `write-accessibility-report.mjs`.
- **`package.json`:** the `:ux3a` scripts and `report:accessibility:ux3-corrected`.
- **New records:** this file, `gate-4a3-accessibility-after-ux3-corrected.md`, and the `gate-4a3-ux3a-*`
  and `gate-4a3-accessibility-after-ux3a.*` artifacts.
- **Unchanged:** `src/`, the backend, every scenario and fixture, the contract, and **every committed
  artifact, including all eight reports in the erratum.**
