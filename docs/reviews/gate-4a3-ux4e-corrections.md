# Gate 4A3 UX-4e: the turn result tells the truth, and three claims corrected

This is a forward-only follow-up to UX-4 (`13603b7`), from your review of it and your rulings on
DR1–DR3, including the approved extension: two more reasons fold into Routine steps. **Every
committed record is preserved unchanged.** Where an earlier record overstated something, the
correction is here.

The engine, the scenarios, the contract and the budgets are unchanged. `generate:api` is
byte-identical. The single backend change is in `app/api/` and is presentation only.

## 1. A decree turn no longer says the legislature voted (correction 1, DR1)

**What was wrong.** The UX-4d dry run's decree turn showed "The budget was enacted by decree. The
legislature was bypassed." and also "The legislature voted.". The second line was the generic label
for `legislative_vote_resolved`, which is emitted on every budget turn, decree or not.

**What changed.** That driver stores how the budget was resolved: `route`, `outcome`,
`chambers_passed` and `chambers_total`. The sentence now comes from those params
(`format.ts`, `consequenceSentence`):

| `outcome` | sentence |
|---|---|
| `enacted_by_decree` | "Enacted by decree — no vote was held." |
| `passed_legislative` | "The legislature passed the budget: {p} of {t} chamber(s) carried." |
| `failed_legislative` | "The legislature voted the budget down: {p} of {t} chamber(s) carried." |
| `no_proposal` | "No budget was put to a vote." |

The blocking chamber is named, with its tally: "Lower chamber blocked the budget: 45 of 51 seats, 6
short.".

## 2. Outcome first; generic lines replaced with named consequences (DR1, ruled)

- **Outcome first.** `driverPriority` and `outcomeFirst` (`format.ts`) put the outcome reasons first,
  in server order. These are the vote, the blocking chamber, amendments, tax and spending changes,
  cabinet, bargain, assistance and promise results, and the coup, impeachment, election and terminal
  events. Everything else follows in server order. This applies to the visible list only, live and
  in History alike.
- **Named, with figures.** Every sentence is built only from the driver's stored params. A missing
  param falls back to the generic label, never an identifier.
  - **Tax rate:** "Personal income tax: 20.00% → 25.00%."
  - **Spending, in denars:** "Defence spending: 1,200,000.00 → 1,500,000.00."
  - **Legitimacy:** "Legitimacy: 60.00% → 61.00% (+1.00 points)."
  - **Capital:** "Political capital: 500 → 633 of 1,000 (250 spent, 383 regained)."
  - **Survival:** "Risk of an attempt this turn: coup 3.52%, unrest 2.40%." It states the risk of an
    attempt and never an outcome, matching the CLI and the Survival card.
  - **Blocs:** "Crown Party Core resented being bypassed by decree (-2.00 points).", "Crown Party
    Core: relationship 60.00% → 58.50% (-1.50 points).", and a reaction to the enacted policy.
- **Naming the bloc without an engine or contract change.** Relationship drivers store only
  `party_id`/`bloc_id`.
  - `build_turn_result` (`app/api/projections.py`) adds `bloc_display_name`, the bloc's authored
    `name`, from **the same state the result is built from**.
  - `params` keeps its type, `dict[str, str | int]`.
  - **The stored report is untouched.** A test asserts that no stored entry carries the key.
  - Live and History share the builder, and a test asserts the two serialise identically.
- **Two more reasons fold into Routine steps (ruled):**
  - `political_capital_ledger_resolved`, now "Capital committed this turn: 250 (250 to the vote or
    decree, 0 to relationships).", repeats the capital line and the "What your decision committed"
    panel;
  - `relationship_decay_resolved` ("{Bloc} drifted toward its usual stance (±x points).") is
    mechanical drift, not a result of the turn's choice.
- **DR2 (ruled):** the worker warning ("Resource extraction: 6,000 resource workers had no deposit to
  work.") stays visible. `@ux4e` asserts it.

**What a Valdrun decree turn now shows** (`@ux4e`, desktop):
1. Personal income tax: 20.00% → 25.00%.
2. Enacted by decree — no vote was held.
3. Resource extraction: 6,000 resource workers had no deposit to work.
4. The Construction sector produced nothing this turn.
5. The Public services sector produced nothing this turn.
6. Legitimacy: 60.00% → 61.00% (+1.00 points).
7. Political capital: 500 → 633 of 1,000 (250 spent, 383 regained).
8. Risk of an attempt this turn: coup 3.52%, unrest 2.40%.
9. Crown Party Core reacted to the enacted policy (+0.50 points).
10. Crown Party Core resented being bypassed by decree (-2.00 points).
11. Crown Party Core: relationship 60.00% → 58.50% (-1.50 points).
12. Reform Opposition Main reacted to the enacted policy (-1.50 points).
13. Reform Opposition Main resented being bypassed by decree (-2.00 points).
14. Reform Opposition Main: relationship -80.00% → -83.50% (-3.50 points).

The following legislative turn opens with "The legislature voted the budget down: 0 of 1 chamber
carried." and then "Lower chamber blocked the budget: 45 of 51 seats, 6 short.".

## 3. DR3 (ruled): a neutral heading

The result's outcome panel is titled **"Turn outcome"**, not "Turn {N} — outcome". That heading named
the turn the result *produced*, one more than the turn just resolved ("Resolve turn 0…" was followed
by "Turn 1 — outcome"). The History timeline's "Turn N — …" buttons are unchanged, so **R3 is
narrowed, not closed**.

## 4. Correction: the accessibility claim in the UX-4c record (correction 2)

**What `gate-4a3-ux4c-reflow-frame-mobile.md` §5 said, and what is true.** It said "55 of the 56 are
axe `color-contrast` results on nav buttons". Measured from the committed
`gate-4a3-accessibility-after-ux4c.json`, those 55 items **touch** nav buttons, but they also contain
**9 other selectors**:

| selector | items | screens / viewports | status |
|---|---|---|---|
| `#nav-summaries` (the "Summaries" caption, **new in UX-3/UX-4c**) | N12, N13, N16, N46, N47, N48 | Constitution, Dashboard, Economy, Government; 390, 320, 195 | **resolved by a new check (below)** |
| `text[data-theater-label=…]` ×5 and `text[y="-330"]` (Strategic map labels) | N1, N38 | 1920, 1440, 960 | **unresolved**, pre-existing (the old N1): SVG text over map shapes, which axe cannot decide |
| a Decisions policy card's figures row | N52 | 195 only | **unresolved**, pre-existing (the old N3), below the 320 px floor |
| the Victory / defeat button row | N56 | 195 only | **unresolved**, pre-existing (the old N4), below the 320 px floor |

The UX-4c record also understated a gap. Its in-view check measured the nav buttons at **390 and 320
only**, but the sweep also reports below-`lg` widths of 960, 820, 720 and 195.

**What now resolves the nav and caption items.** The desktop run of `@ux4c` steps through **every
below-`lg` width the sweep uses: 960, 820, 720, 390, 320 and 195**. At each one it:
- brings each of the 12 nav buttons **and the "Summaries" caption** fully into view, one at a time;
- runs axe `color-contrast` on that one element, requiring **0 violations, 0 undecided and at least
  one rule evaluated** (78 measurements: 13 elements × 6 widths);
- computes the caption's ratio offline (`parchment-200` at 70% on the surface it resolves to), which
  must be at least 4.5:1.

All pass.

**What remains unresolved.** The sweep still **records** these items as needs-review: its behaviour
is unchanged, and so is the count. N1/N38, N52 and N56 remain axe-undecided. Each predates this
pass, and **no contrast failure has been demonstrated for any of them**. This record states them as
open, not cleared.

## 5. Correction: the dry run now enforces what it records (correction 3)

**What was wrong.** The UX-4d `e2e/dry-run.spec.ts` recorded console errors and each turn's preview,
but asserted neither. It also **skipped** when `MANDATE_DRYRUN_URL` was missing. UX-4d's recorded run
did show matching outcomes and no console errors; the harness just did not enforce them.

**What changed.**
- **A missing address fails.** The new `npm run dryrun:installed:ux4f` sets
  `MANDATE_DRYRUN_REQUIRED=1`, and then a missing `MANDATE_DRYRUN_URL` fails. Only an unrelated
  all-projects run, without that flag, still skips.
- **Each turn's preview must agree with its resolution.** `preview.would_pass` must equal "the
  recorded vote outcome is `passed_legislative` or `enacted_by_decree`". A decree must also be
  affordable and recorded as `enacted_by_decree`.
- **`consoleErrors` must be `[]`,** as `offOrigin` already was.
- **The record is written only after every assertion holds.**

**Each enforcement bites.** These were run against a scratch server, and each scratch output was then
removed:

| run | result |
|---|---|
| `MANDATE_DRYRUN_REQUIRED=1`, no URL | **fails**: "MANDATE_DRYRUN_URL is required…" |
| control, against the server | passes (`1 passed`) |
| a forced console error | **fails**: "no console error anywhere in the walk" |
| a forced disagreement (expecting `!enacted`) | **fails**: "turn 1: preview would_pass vs resolved outcome enacted_by_decree" |

UX-4d's spec, script (`dryrun:installed:ux4`) and record are preserved. The enforced run is UX-4f's.

## 6. Tests

**Frontend: new, 24 (569 → 593).**
- `src/format/consequences.test.ts` (18), with the real param names:
  - every vote outcome, including **decree, which never says "voted"**;
  - the blocking chamber;
  - the tax and spending lines;
  - legitimacy, capital and survival;
  - the four bloc sentences;
  - the fallback when the name is missing;
  - outcome-first ordering;
  - the two newly folded reasons, and DR2's warning still visible;
  - signed points.
- `src/greybox/ux4e.test.tsx` (6, live and History). For a decree turn:
  - nothing says "voted";
  - the visible list is outcome first, with the bloc named;
  - the ledger is in Routine steps;
  - the heading is "Turn outcome", and no "Turn N — outcome" heading remains.

**Backend: new, 4 (`tests/test_turn_result_naming.py`).**
- Relationship drivers carry `bloc_display_name`, equal to the legislature's `bloc.name`. It uses a
  decree turn, because an empty turn records no relationship drivers; the anti-vacuity check caught
  that in the first draft.
- The stored report entries never carry the key.
- History serialises byte-identically to live.
- `TAX_FIELD_LABEL` and `SPENDING_LABEL` keys equal the engine's tax fields and `SpendingCategory`.

**Browser.**
- `@ux2`'s blocked-budget assertion now expects the named chamber sentence.
- `@ux4c` gains the six-width nav and caption check described in §4.
- A new **`@ux4e`** block, at 1440, 390 and 320:
  - **a decree turn:** "the legislature was bypassed", with no "voted" anywhere in the result; "Enacted
    by decree — no vote was held."; outcome lines before all others; every bloc line starts with a
    real bloc name; no generic bloc line; every relationship driver in the response carries
    `bloc_display_name`; the heading is "Turn outcome";
  - **a legislative turn:** "voted the budget down…", the blocking chamber sentence, outcome first,
    and the worker warning still visible.

**Mutation checks**, each restored and verified with `cmp`:

| mutation | result |
|---|---|
| the enrichment removed (`params=entry.params`) | `test_relationship_drivers_name_their_bloc_from_the_turns_own_state` fails |
| the decree branch removed from the vote sentence | 5 frontend tests fail (the unit decree case, and the live and History view cases) |
| the dry-run enforcements | the table in §5 |

## 7. Gates

Each gate was run separately, and each exit status is the command's own `$?`.

| command | exit | result |
|---|---:|---|
| `npm test` | 0 | `Tests  593 passed (593)`: 569 → 593, +24 |
| `npm run typecheck` | 0 | clean |
| `npm run build` | 0 | JS `index-CxgBPlll.js` 362.42 kB / 104.68 kB gzip; CSS `index-DVVZ_8_3.css`, unchanged |
| `npm run check:bundle` | 0 | `check-bundle: OK -- …` |
| `npm run check:palette` | 0 | `check-palette: OK -- 43 source file(s), 16 colour token(s) defined, …` |
| `npm run check:copy` | 0 | `check-copy OK: 342 player-visible strings across 43 files, 15 forbidden words, whole-word matched.` |
| `npm run check:css-sources` | 0 | `check-css-sources: OK -- …` |
| `npm run verify:ux:4e` | 0 | `26 passed (45.1s)`: preflight, then every block `@ux1` to `@ux4e` at three viewports each |
| `npm run verify:campaigns:ux4e` | 0 | `7 passed (22.5s)` |
| `npm run verify:terminal:ux4e` | 0 | `6 passed (29.4s)` |
| `npm run verify:fixes:ux4e` | 0 | `13 passed (34.9s)` |
| `npm run verify:icons:ux4e` | 0 | `7 passed (10.2s)` |
| `npm run audit:stress:seated:ux4e` | 0 | `6 passed (5.5s)` |
| `npm run audit:accessibility:verify:ux4e` | 0 | `6 passed (1.2m)`; `0 findings (0 WCAG AA, 0 best-practice), 56 needs-review, 89 surfaces`, as itemised in §4 |
| `ruff check .` (backend) | 0 | `All checks passed!` |
| `ruff format --check .` (backend) | 0 | `197 files already formatted` |
| bare `mypy` | 0 | `Success: no issues found in 57 source files` |
| `npm run generate:api` | 0 | no change to `docs/contracts/` or `frontend/src/api/`: **byte-identical** |
| full backend suite `uv run pytest -q; echo PYTEST_EXIT=$?` | **0** | `36398 passed, 1 warning in 1329.83s (0:22:09)`: 36,394 + 4, exactly the naming tests |

**Artifacts compared with UX-4c's:**

| artifact | disposition |
|---|---|
| `gate-4a3-ux4e-verification.json`, `-icon-coverage.json`, `-terminal.json`, `-stress-seated-cabinet.json` and both screenshots | **byte-identical** |
| `gate-4a3-accessibility-after-ux4e.json` | **byte-identical** to `…-after-ux4c.json`. The sweep's needs-review items are unchanged; §4 says which are now measured in view and which remain open. |
| `gate-4a3-ux4e-campaigns.json` | differs only in `sameOrigin.distinctPaths[10]`, the new JS filename |
| `gate-4a3-ux4e-verify-ux.json` | new, with the `@ux4e` entries and the six-width nav and caption measurements |

## 8. Scope

- **Backend:** `app/api/projections.py` (`_bloc_display_names` and `_with_bloc_display_name`, used
  by `build_turn_result`) and the new `tests/test_turn_result_naming.py`.
- **Frontend:** `format/format.ts` (the sentences, `TAX_FIELD_LABEL`, `SPENDING_LABEL`,
  `formatSignedPoints`, `driverPriority`/`outcomeFirst`, two routine reasons) and
  `greybox/TurnResultView.tsx` (outcome first, "Turn outcome"), plus the two new test files.
- **e2e:** `verify-ux.spec.ts` (`@ux2` expectation, `@ux4c` six-width check, `@ux4e`);
  `dry-run.spec.ts` (enforcement); the `:ux4e` scripts and `dryrun:installed:ux4f`.
- **Unchanged:** the engine, `app/core`, every scenario and fixture, the contract, and **every
  committed record**, including the UX-4c and UX-4d records this file corrects.
