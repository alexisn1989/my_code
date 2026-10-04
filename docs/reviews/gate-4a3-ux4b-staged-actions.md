# Gate 4A3 UX-4b: one definition of "staged actions" (U8)

This is the second of the split UX-4 commits, approved in the UX-4 plan and its addendum, which
includes Clarification 2: no phantom staged actions. It is frontend only. The engine, backend,
scenarios, contract and budgets are unchanged, and so is `buildDecisions`, the wire format.

## 1. What was wrong (O5)

Actions are staged on four screens: Decisions, Government, Relationships and Strategic map. Before
this commit:
- nothing staged elsewhere was visible from Decisions;
- the nav showed nothing at all;
- the confirmation read "Confirm resolving this turn with 1 decision(s) committed.", which counted
  **wire decisions**. Two cabinet changes are one `cabinet` decision, and three investments are one
  `bloc_relationship_investment`.

## 2. What changed

- **`src/state/stagedActions.ts: stagedActions(draft)`** is the single definition. It returns one
  entry per **player action that will be submitted**:
  - **The policy proposal,** exactly when `policyProposalDecision(draft)` is non-null.
    - That function is newly exported from `buildDecisionSet.ts`, and `buildDecisions` itself now
      calls it, so the counter and the builder share **one** rule; it is not restated.
    - An untouched budget, a target-less amendment, either of those with influence or a decree
      route, and "no major action" all count **0**. None of them is submitted.
  - **Each explicit cabinet order.** A transfer's generated companion is not counted; it is attached
    to that transfer as its consequence.
  - **Each investment row,** plus the bargain, the assistance request, the promise and the movement
    order.
- **One wording per action.** The staged-summary sentences in `MeetingScreen` (bargain, assistance,
  promise and release) and `StrategicMapScreen` (movement) moved into `format.ts` helpers. Their
  text is unchanged, and their screens' 111 existing tests pass. New helpers word a proposal and an
  investment. Cabinet entries reuse `becomesLine` and `leftVacantLine`.
- **The three surfaces read the same list:**
  - **Nav:** "· N staged" appears under Decisions, hidden at 0. It is the button's
    `aria-describedby`, **not part of its name**, so the control is still "Decisions" to every screen
    reader and every spec.
  - **Decisions:** a new "This turn's draft" panel (`greybox/StagedActionsList.tsx`) lists each
    action in its staging screen's words. A transfer shows "As a result: {post} is left vacant."
    beneath it. Names come from decision-options, plus the military projection for a movement; a
    missing name falls back to neutral words, never an identifier.
  - **Confirmation:** "Resolve turn T with N staged actions?", pluralised, with T the dashboard's own
    turn. With nothing staged it reads "Resolve turn T with nothing staged?".

## 3. Tests

**Frontend: new, 19 (550 → 569)**
- **`src/state/stagedActions.test.ts` (11).** Each phantom case asserts **both** that the proposal
  counts 0 **and** that `buildDecisions` submits no budget or amendment. The cases:
  - a budget slot with no target;
  - an amendment slot with no target;
  - influence on a target-less budget (the influence is not submitted either);
  - influence on a target-less amendment;
  - target-less budget and amendment on the decree route;
  - "no major action" with a budget draft left behind in state.

  Then the controls and the action/wire distinction:
  - **positive controls:** one rate target makes the budget count 1, and exactly that budget is
    submitted; the same for one amendment target;
  - one transfer is **1 staged action and 2 wire orders**, with the vacated post as its consequence;
  - a mixed draft has 4 actions against 3 wire decisions, and every action maps to one submitted
    decision;
  - the singletons count once each.
- **`src/greybox/ux4b.test.tsx` (8),** through the real `GreyboxApp` nav and the real
  `DecisionsScreen`:
  - a transfer plus two investments shows "· 3 staged", 3 list items, and "Resolve turn 4 with 3
    staged actions?", against **2** wire decisions;
  - the list words each action as its staging screen does, including the transfer's consequence;
  - **five phantom cases** — an empty budget, an empty amendment, influence on each with no target,
    and "no major action". Each is 0 on every surface: no nav count, "Nothing is staged yet.", and
    "…with nothing staged?". `stagedActions` and `buildDecisions` are both empty;
  - one action is singular.
- **Mutation check.** I made the proposal count on `policySlot !== null` alone, which is the phantom
  behaviour. **10 tests failed**: all six phantom and control cases in the state file, and the four
  slot-selected phantom cases on the surfaces. The file was then restored and verified with `cmp`.

**Browser: `@ux4b` in `e2e/verify-ux.spec.ts`, Valdrun at 1440, 390 and 320.**
- A fresh campaign shows no count.
- One cabinet change is staged on Government, through the interface, choosing a willing non-incumbent
  from the API. The nav then shows "· 1 staged".
- Two investments are staged on Decisions. The nav then shows "· 3 staged", and the button's
  accessible name is still "Decisions".
- The list has 3 entries, worded as staged. Measured: "Edda Thorne becomes chief of staff.", "20
  political capital invested in Crown Party Core.", and "30 political capital invested in Reform
  Opposition Main.".
- **What would be submitted:** the Preview request's body carries exactly
  `["bloc_relationship_investment", "cabinet"]`, with 2 investment rows. Three actions are two
  decisions.
- The confirmation reads "Resolve turn N with 3 staged actions?".

**An existing spec, updated for the changed sentence.** `e2e/campaigns.spec.ts`'s
`resolveThroughInterface` asserted the old sentence with its count as a guard against a draft that
silently lost or gained a decision. Every one of its five calls stages one action per decision, so
the count is the same number under both definitions.
- The helper now asserts the new sentence with that count.
- It **also** asserts that the resolve request carries exactly that many decisions.

The guard is therefore stricter than before and no longer depends on the wording.

## 4. Gates

Each gate was run separately, and each exit status is the command's own `$?`.

**The campaigns gate's first run failed and was superseded.** `verify:campaigns:ux4b` first failed
(`1 failed, 5 passed, 1 did not run`) on the old sentence, before the update above. Its
`gate-4a3-ux4b-campaigns.json` was confirmed **untracked** and moved out of the repository. The gate
was re-run under the same name. No other gate's spec or build changed between the two runs.

| command | exit | result |
|---|---:|---|
| `npm test` | 0 | `Tests  569 passed (569)`: 550 → 569, +19 |
| `npm run typecheck` | 0 | clean |
| `npm run build` | 0 | JS `index-Ds8vuoDo.js` 357.73 kB / 103.29 kB gzip; CSS `index-ClnHb-Eg.css`, unchanged |
| `npm run check:bundle` | 0 | `check-bundle: OK -- … initial JS 99.60 KiB gzip (level 9) of a 250 KiB budget …` |
| `npm run check:palette` | 0 | `check-palette: OK -- 43 source file(s), 16 colour token(s) defined, …` |
| `npm run check:copy` | 0 | `check-copy OK: 343 player-visible strings across 43 files, 15 forbidden words, whole-word matched.` |
| `npm run check:css-sources` | 0 | `check-css-sources: OK -- …` |
| `npm run verify:ux:4b` | 0 | `20 passed (21.4s)`: preflight, then `@ux1`, `@ux2`, `@ux3`, `@ux4a` and `@ux4b` at three viewports each |
| `npm run verify:campaigns:ux4b` (re-run) | 0 | `7 passed (22.7s)` |
| `npm run verify:terminal:ux4b` | 0 | `6 passed (29.6s)` |
| `npm run verify:fixes:ux4b` | 0 | `13 passed (34.7s)` |
| `npm run verify:icons:ux4b` | 0 | `7 passed (10.2s)` |
| `npm run audit:stress:seated:ux4b` | 0 | `6 passed (5.5s)` |
| `npm run audit:accessibility:verify:ux4b` | 0 | `6 passed (1.2m)`; `0 findings (0 WCAG AA, 0 best-practice), 4 needs-review, 89 surfaces` |
| backend tests that read frontend source | 0 | `54 passed`: `test_money_display.py`, `test_orientation_copy.py`, `test_portraits.py`, `test_sector_label_drift.py` |

**Not run, and why.** No backend code, contract or scenario changed. The full backend suite and
`generate:api` were not re-run; UX-4a's suite (36,391 passed) stands. The four backend tests that
read frontend source were re-run, because `format.ts` changed.

**Artifacts compared with UX-4a's:**

| artifact | disposition |
|---|---|
| `gate-4a3-ux4b-icon-coverage.json`, `-terminal.json`, `-stress-seated-cabinet.json` and both screenshots | **byte-identical** |
| `gate-4a3-accessibility-after-ux4b.json` | **byte-identical** to `…-after-ux4a.json` |
| `gate-4a3-ux4b-verification.json` | 6 differences, all on **Decisions**, from the new "This turn's draft" panel. Candidates 147 → 151, measured 72 → 75, no-own-text 68 → 69. Overall: 195 → 198 measured, 612 → 616 candidates, navy-900 188 → 191, and calibration nodes 35 → 36. |
| `gate-4a3-ux4b-campaigns.json` | differs only in `sameOrigin.distinctPaths[10..11]`: the new JS filename sorts after the unchanged CSS |
| `gate-4a3-ux4b-verify-ux.json` | new |

## 5. Scope

- **State:** the new `stagedActions.ts`; `buildDecisionSet.ts` (exported `policyProposalDecision`,
  with `buildDecisions` producing identical output, pinned by its 76 existing tests).
- **Format:** `format.ts`, the staged-action helpers and the count and confirm sentences.
- **Components:** the new `StagedActionsList.tsx`; `GreyboxApp.tsx` (nav count); `DecisionsScreen.tsx`
  (draft panel and confirm); `MeetingScreen.tsx` and `StrategicMapScreen.tsx` (shared wording, text
  unchanged).
- **Tests:** the two new test files.
- **e2e:** `verify-ux.spec.ts` (`@ux4b`); `campaigns.spec.ts` (`resolveThroughInterface`, §3); the
  `:ux4b` scripts.
- **Unchanged:** the backend, the contract, every scenario and fixture, and every committed artifact.
