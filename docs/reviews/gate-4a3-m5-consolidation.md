# Gate 4A3 M-5: consolidation

**Authorized by:** your instruction "Implement M-5 with the default choices", on the M-5 plan.

**The defaults:**
1. **The concluded state** is checked at the real `victory` wins.
2. **The mockup images stay out of the repository;** this record cites them by file name.
3. **`audit:baseline` is not run.** It writes fixed names and would overwrite committed baseline
   evidence.

**Not authorized:** a commit, a push, a candidate build or a build switch. None was done. The
external playtest was not run, and is not claimed.

**Scope:**
- **Tests, a gate step and records only.** No application, backend, data or contract change.
- `generate:api` is byte-identical to `HEAD` (`b2864c6`).
- **Three findings came up** (§6). On your ruling, **F1 and F2 are fixed** (§10), and **F3 is accepted**
  as is.
- The fixes are two small application changes: the introduction's default, and the offer's wording.

## 1. The gaps, and what closed each

| # | gap (from the audit of the redesign's acceptance criteria) | closed by |
|---|---|---|
| G1 | No test ran the whole chain from the Dashboard map; 390 px steps clicked; nothing ran at 320 | `@m5` journeys A (Arken, bargain) and B (Valdrun, amendment influence) **from the map**, at 1440×900 (keyboard: Tab to the pin, then Space or Enter), 390×844 and 320×800 (every step tapped). Each covers: objective → place → bloc → stage → Preview (supporting seats, rows summing) → resolve → card and reactions → History equal to live |
| G2 | No proof that the bloc panel stages the same draft as the existing screens; no persistence across Dashboard → Parliament → Decisions | `greybox/m5.test.tsx`: the same bargain, influence and investment staged through the panel and through Relationships plus Decisions give a **deep-equal** `buildDecisions()` and `stagedActions()`. The selected card and every staged action survive Decisions → Dashboard → Parliament → Decisions → Parliament. Journey A also checks the selected card, the staged list and the nav count after the round trip |
| G3 | The unaffordable draft on Parliament had no test | `@m5 states` (1440, 390): the backend's `previewUnaffordable` set from the panel (400 influence plus a 200 investment). The tallies show, the "would be refused" sentence shows, and nothing claims enactment. **The server refuses the same set** (422), and the turn does not move |
| G4 | The concluded campaign was not checked in a browser | **At the three real wins** (`victory`):<ul><li>Parliament: "The campaign has ended.", no Preview, every chamber in seats mode;</li><li>the bloc panel: readable, with every action disabled;</li><li>the winning turn's result: the proposal card, "This turn ended the campaign", and no "Plan turn".</li></ul>Contrast is decided on each |
| G5 | A failed vote's result card was not checked in a browser | `@m5 states` (1440, 390): Valdrun's legislative budget fails; "Did not carry", the blocking sentence and the recorded tallies; History equals live |
| G6 | No Tab reachability, no Space, no tap on Places | `@m5 input`: every pin and every Places button is a Tab stop, and opens its place by **Enter** and by **Space**, landing on the same heading. At 390 every Places button opens by **tap** |
| G7 | axe's "incomplete" contrast was never asserted on the new surfaces | `e2e/contrast-decided.ts` (§2) on the map, Parliament with the panel open, and the result at all three sizes, and on the concluded Parliament and result |
| G8 | Body background and seat-diagram boxes were not asserted | each journey checks that `body`'s background equals `--color-navy-950`, and that every seat diagram on screen has a non-zero box |
| G9 | "Rules and saves unchanged since before M-0" was stated only in prose | **a new gate step:** `git diff --exit-code a9e006b -- backend/app/simulation data backend/tests/fixtures frontend/e2e/fixtures`, plus no untracked file under those paths. `a9e006b` is the parent of M-0. The step is mutation-tested (Y3) |
| G10 | No mockup comparison for the map or the bloc panel | the visual record (§5): the 11 approved views re-shot at the mockups' own sizes (33 screenshots) and compared |

## 2. Contrast decided: the rule, and one widening stated

**The plan said:** axe 0 violations and 0 "incomplete"; undecidable SVG text measured offline.

**Measuring first** showed that axe also leaves **HTML** text undecided in two cases:
- single glyphs: the "▲"/"▼" marks on the result's bloc rows (M-4);
- table cells scrolled out of the table's own scroll box at 390 and 320 px.

Those are measured too. **The rule in `e2e/contrast-decided.ts`, used by both specs:**
- **SVG `<text>`:**
  - brought into view first;
  - measured against the SVG shapes actually painted under its centre, composited bottom-up over
    the page backdrop;
  - a gradient is bounded by its **worst** stop.
- **HTML text:** its colour against its first painted ancestor. This is the conformance sweeps'
  own rule.
- **Every measured node must reach 4.5:1.** A node that cannot be measured fails.
- **The calibrated probe must reproduce its calibration first:** 5.45:1, within 0.05.

**What it measured** (from `final2`'s artifacts; the same figures as `final1`):

| surface | nodes axe left undecided | measured |
|---|---|---|
| map | neighbour labels (KESSIA, VETRUSKA) on the sea gradient; the compass "N" | 4.86:1 (worst gradient stop); 11.55:1 |
| Parliament (1440) | the seat-arc labels | 13.27:1 |
| Parliament (390, 320) | Relationship and Supporting cells scrolled out of the table's box | 7.01:1 to 15.31:1 |
| result | the ▲ / ▼ marks | 15.31:1 |
| concluded Parliament and result (victory) | seat-arc labels in all three scenarios; the ▲ mark | 13.27:1; 15.31:1 |

**Two artefacts were found and fixed in the helper during development (§4), not in the product:**
- an off-screen label measured 1:1, before it was scrolled into view;
- a gradient was "unmeasured" before its stops were bounded.

## 3. Tests added
- **`greybox/m5.test.tsx` (2 tests):** draft equality, and persistence across screens.
- **`e2e/redesign.spec.ts` `@m5` (15 browser tests):**
  - journeys A and B at three sizes (6);
  - input by keyboard and by touch (2);
  - unaffordable and failed, at 1440 and 390 (4);
  - the visual record at three sizes (3).
- **`e2e/victory.spec.ts`:** the concluded Parliament, bloc panel and result, inside each of the
  three winning replays. The probe is installed for them.
- **`e2e/contrast-decided.ts` (new):** the shared contrast rule.
- **The gate script:** the rules-unchanged step.

**No existing test was changed.**

## 4. Development failures found and fixed (before the gates)
1. **A `{timeout}` fallback hack** in the first draft of the equality test was replaced with the
   leader selector MeetingScreen's own tests use.
2. **The first contrast rule rejected every undecided node.** The map's neighbour labels and compass
   are SVG text axe cannot judge, so the rule was extended to measure them, as the plan says.
3. **A gradient backdrop was "unmeasured".** The sea is a radial gradient, which the probe cannot
   parse, so gradients are now bounded by their worst stop.
4. **HTML single glyphs and scrolled-out cells were undecided** (§2). They are now measured as HTML
   text, against the authored surface.
5. **At 390 px a label measured 1:1, because it sat above the viewport and hit-testing found nothing
   under it.** It is now scrolled into view first, and an off-screen point counts as unmeasured, never
   as the page backdrop.
6. **The concluded Parliament in `victory` had undecided seat-arc labels.** The helper moved into the
   shared module so both specs apply one rule.

## 5. The visual record (`gate-4a3-m5-redesign-shots/visual-*`)

**33 screenshots:**
- 11 views × 1440×900, 390×844 and 320×800;
- viewport size, each scrolled to the part the mockup shows.

**The mockups** are `docs/reviews/gate-4a3-mv-mockups/round2/screenshots/{view}__{size}.png`, which
are untracked (decision 2).

**What was compared:**
- **every desktop pair by viewing both;**
- **the phone shots** for framing (bloc-staged at 390, parliament-tiny-recorded at 320);
- **the Parliament views** were also compared in M-2 §7, and the result in M-4 §1.1.

| view | matches | intended differences (with the decision behind each) |
|---|---|---|
| `dashboard` | status bar, objective and priority, the country with the walled capital, the Places list, one national wash | navy cards, not parchment (the authored-surface rule); priority and objective side by side; the summaries folded (M-1 feedback rounds 1 and 2). **Finding F1, now fixed** (§10): the introduction starts closed, and the map starts at 511 px |
| `parliament-valdrun-draft` | one chamber, both thresholds, seats by bloc, "No recorded vote yet." | the engine's thresholds, not the mockup's calculated asterisk (M-0); "supporting if resolved now", not "projected" (`check:copy`) |
| `parliament-valdrun-preview` | the preview's verdict and per-bloc rows | the mockup's draft carried 300 influence (56 supporting); the record's shot has none (45). Same wording differences |
| `parliament-tiny-preview` | both chambers, 61 of 51 and 35 of 31 "Would carry", the bloc rows, the colours | the same wording and threshold differences; bloc names are buttons that open the panel (M-3) |
| `parliament-tiny-recorded` | "Last recorded vote · turn 1", both chambers' stored tallies, the stored bloc rows | at 320 the table's last column is reached by scrolling the table itself (finding F3) |
| `bloc-offer` / `bloc-staged` | the bloc, the leader with portrait and traits, the fixed price, Stage, then "Staged … one bloc" with Withdraw | no before-and-after effect figure (M-3 default 1); plain navy surfaces; the panel beside the chambers from 1280 px |
| `bloc-refuses` | "Will not deal at any price.", no price, influence available | as above |
| `bloc-no-proposal` | the offer shown, staging disabled with its reason, influence unavailable | **finding F2:** the offer reads "Endorse your budget." with no proposal drafted |
| `bloc-replace` | the second offer at 137, the replacement sentence, Replace and Keep | on M-3's labelled altered response, not the mockup's engine fixture; no effect figure; no preview in this shot |
| `result` | verdict, the proposal, both chambers' recorded seats, the leader with portrait, the bloc moves, routine/ledger/trace collapsed | as recorded in M-4 §1.1 (navy card, no card title, reactions kept under each bloc) |

## 6. Findings (as first reported; their outcomes are in §10)
- **F1, the Dashboard's first desktop screen:**
  - **What happens:** at 1440×900 the map starts about 590 px down and only its top is visible.
    The mockup showed the whole map and the Places list above the fold.
  - **Why:** the "How to govern" introduction, open by default on desktop, and the two-row header
    take about 250 px.
  - **Not ruled on:** nothing in M-1's feedback rounds addressed this fold.
  - **Possible changes:** close the introduction by default on desktop too, or compact the header.
- **F2, wording, from M-3:**
  - **What happens:** with no proposal drafted, the panel's offer reads "Endorse your budget.".
  - **Why:** `offerLine(null)` falls through to the budget text (`format/parliament.ts:282`), and no
    test covered that case.
  - **The fix:** one line, "Endorse your proposal." when nothing is drafted, with a unit test.
- **F3, narrow tables (noted in M-3, seen again):**
  - **What happens:** at 390 and 320 px the chamber tables' last columns, and the recorded-vote
    table's Supporting column, are reached by scrolling the table itself.
  - **This is not page overflow.** The cells are measured readable (§2).
  - **A possible change:** a stacked narrow layout.

## 7. Gates
**Run `final2`**, after the F1 and F2 fixes (`scratchpad/m5/final2/run.sh`). Each command was run on
its own, and its real `$?` was recorded.

| gate | exit | result |
|---|---|---|
| `npm test` | 0 | 54 files, 810 tests passed (806 before M-5; plus the 2 M-5 tests and the 2 fix tests) |
| `typecheck` | 0 | |
| `build` | 0 | |
| `check:bundle`, `check:palette`, `check:copy`, `check:css-sources` | 0 each | |
| `generate:api` | 0 | schema and contract byte-identical to `HEAD` |
| **rules unchanged since pre-M-0** (new, G9) | 0 | no change against `a9e006b`, and no untracked file, under `backend/app/simulation`, `data`, `backend/tests/fixtures` and `frontend/e2e/fixtures` |
| `verify:redesign:m5` (`@m1` to `@m5`) | 0 | 58 passed (42 before M-5, plus 15 `@m5`, plus the F1 check) |
| `verify:victory:m5` | 0 | 10 passed; each winning replay also checks the concluded Parliament, bloc panel and result |
| `verify:ux:m5` | 0 | 29 passed |
| `verify:fixes:m5` | 0 | 13 passed |
| `verify:icons:m5` | 0 | 7 passed |
| `verify:terminal:m5` | 0 | 6 passed |
| `verify:campaigns:m5` | 0 | 7 passed |
| `audit:stress:seated:m5` | 0 | 6 passed |
| `audit:accessibility:verify:m5` | 0 | 6 passed |
| ruff check / ruff format --check / mypy | 0 / 0 / 0 | |
| backend suite | 0 | 36,587 passed, 1 skipped (as before) |
| tree unchanged during the run | 0 | |

**Superseded: run `final1`.**
- It passed every gate on the M-5 tree before the fixes, with 808 unit tests and 57 in `redesign`.
- **It is superseded because F1 and F2 were then fixed.** Its artifacts, including the first version
  of this record, were **moved**, not deleted, to `scratchpad/m5/final1/artifacts-superseded/`.

**Already gated, and named here for G9:**
- `RULESET_VERSION` is pinned at `0.23.0` (`backend/tests/test_legislative_bargain.py:1396`);
- the 22 save fixtures load inside the backend suite.

## 8. Mutation checks
Each mutation was applied from a scratch backup, run, restored, and checked with `cmp`. The bundle
was rebuilt for the browser cases and at the end. The raw results are in
`scratchpad/m5/mutations/results.txt`.

**Valid, failing as intended (8):**

| # | mutation | failing test(s) |
|---|---|---|
| Y1 | the panel writes influence under a different key | `m5.test.tsx`: draft equality, and persistence |
| Y2 | the selected card cleared on leaving Decisions | `m5.test.tsx`: persistence |
| Y3 | a dummy edit to `backend/app/simulation/state.py` | the rules-unchanged gate step (exit 1) |
| B1 | the map pins taken out of the Tab order | `@m5 input`: "Palace: opens Government: a pin and a Places button, both Tab stops" |
| B2 | Space swallowed on the pins (keydown and keyup) | `@m5 input`: activation by Space (`redesign.spec.ts:1370`, after the Tab sweep passed) |
| B3b | the unaffordable sentence hidden | `@m5 states`: unaffordable, at 1440 |
| B4 | a failed vote shown as "Enacted" | `@m5 states`: the failed vote's card, at 1440 |
| B5 | Parliament ignores a concluded campaign | `victory` (deficit_demo): "The campaign has ended." on Parliament |

**Invalid (1):** B3, removing the unaffordable sentence outright. The mutated source did not compile
(TS6133, the sentence's import unused), so nothing ran. It is superseded by B3b.

**The fixes' mutations (3, all failing as intended), run after `final2`:**

| # | mutation | failing test(s) |
|---|---|---|
| Z1 | the offer says "Endorse your budget." with nothing drafted (F2 reverted) | `m3.test.tsx`: the no-proposal case, and "names what is drafted in the offer, and only that" |
| Z2u | the introduction open by default (F1 reverted) | the default-closed unit test; `ux3`'s "keeps the stakes out of How to govern" |
| Z2b | the same, in the browser | `@m5 F1`: "the note starts closed" |

**Not re-run:** the eight mutations above were not re-run after the fixes. The sources they mutate
(`BlocPanel.tsx`, `DecisionsScreen.tsx`, `CountryMap.tsx`, `ParliamentScreen.tsx`, `result.ts` and
`state.py`) are unchanged since they ran.

**After all mutations:** the tracked diff equalled `final2/tree-at-end.diff`, the untracked sources
matched their hashes, and no mutation or development artifact was left in `docs/reviews`.

## 9. Not done
- No commit or push; no candidate build or build switch.
- `packaged`, `dry-run` and `installed-walkthrough` need a candidate build and were not run.
  `audit:baseline` was not run (decision 3).
- F3 is accepted, not changed (§10).

## 10. Findings: F1 and F2 fixed, F3 accepted (your rulings)

**F2, the offer's wording (fixed):**
- **The change:** `offerLine(null)` now returns "Endorse your proposal.", the mockup's wording. The
  budget and amendment wordings are unchanged (`format/parliament.ts`).
- **Tests:**
  - `m3.test.tsx`'s no-proposal case asserts the offer begins "Endorse your proposal." and never
    names a budget;
  - a format-level test covers all three slots.

**F1, the Dashboard's first desktop screen (fixed as ruled: the introduction starts closed at every
width):**
- **The changes:**
  - the store's initial `dismissedHelp` is now `true` (`state/draft.ts`);
  - `GreyboxApp.tsx`'s mount-time `matchMedia` effect, which closed the note only below `lg`, is
    removed as redundant;
  - the header's "How to govern" toggle and Dismiss are unchanged;
  - the choice is still not persisted.
- **Measured at 1440×900, on a fresh load:**

  | | the map frame's top | buildings within the first 900 px |
  |---|---|---|
  | before (`final1`'s screenshot, read by eye) | about 645 px | Palace only, partly |
  | after (`final2`, measured by `@m5 F1`) | **511 px** | **Parliament, Palace, Constitution hall** |

  **The fix does not bring the whole map above the fold.** The capital's lower four buildings (pin
  bottoms 928 to 1,119 px) and the Places list still lie below it. `@m5 F1` pins exactly what was
  achieved: the frame top at or above 520 px, and those three buildings in the first screen.
  - **The before figure is approximate.** The reverted-fix mutation Z2b stopped at its first
    assertion (the note is open), before measuring.
- **Tests:**
  - a unit test: the store's initial state has the note closed, the toggle is collapsed, and it opens;
  - `@m5 F1` in the browser.
- **Forward-only updates** (the same facts, with the note opened first, as the phone paths already
  did):
  - `ux3.test.tsx`, "keeps the stakes out of How to govern";
  - `e2e/verify-ux.spec.ts` `@ux3`: the note now starts closed at every width;
  - `e2e/verify-commit3-fixes.spec.ts`, the Commit 4 Tab traversal: the note is opened with its
    toggle first, and every later step is unchanged.
- **Expected artifact differences:** the desktop sweeps (accessibility, verification, terminal), the
  1440 stress screenshot and the visual record's `dashboard` shots now show no open introduction.

**F3, narrow tables (accepted, no change):**
- **What it is:** at 390 and 320 px the chamber tables' Relationship column, and the recorded-vote
  table's Supporting column, are reached by scrolling the table itself.
- **Why it is accepted:**
  - it is a contained scroll, keyboard-focusable and labelled, not page overflow, and WCAG 1.4.10
    exempts data tables;
  - the cells are measured readable (§2);
  - the bloc panel shows each bloc's relationship in full.

