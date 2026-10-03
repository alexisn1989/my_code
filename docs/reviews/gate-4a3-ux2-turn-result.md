# Gate 4A3 UX-2: the turn result puts the cause first, and the headline matches the ledger

This commit is the second of the four approved UX-pass commits. It implements U4 and U6 from the
approved plan (`mandate-master-build-breezy-puppy.md`):
- U4: the turn result. Bookkeeping is folded into a collapsible section, consequential events stay
  visible, and reason IDs move into the Trace (T2).
- U6: the blocked-budget headline agrees with the ledger.

It does not change the engine (`app/simulation/**`), `app/core/**`, any scenario, the contract
shape, the budgets or the playtest protocol. It is internal work and is not one of the five external
testers.

## 1. U4: the turn result

### 1.1 What was wrong (O6, T2)

On Valdrun's first turn the result listed 12 driver lines. Only one of them, "The legislature blocked
the budget.", concerned the player's choice. Each line also painted its engine identifier in a
`<code>` element (`labor_market_resolved`, `sector_inactive` and so on). That is T2, the same class
of problem as T1. The two `sector_inactive` lines read "A sector was inactive this turn." and did not
name the sector, although the entry stores it.

### 1.2 What changed

**`frontend/src/format/format.ts`**
- `SECTOR_LABEL` gives display names for the 11 `SectorCategory` values. An unknown value falls back
  to the generic driver label, never to the raw identifier.
- `driverSentence` gains wording for six reasons. Each sentence is composed only from that driver's
  stored params; there is no new data and no derived game state.

  | reason | sentence |
  |---|---|
  | `sector_inactive` | "The {Sector} sector produced nothing this turn." |
  | `resource_extraction_resolved` | It names any deposits that ran dry and any unplaced resource workers. In the quiet case it says that extraction ran normally. |
  | `labor_market_resolved` | "Labour market: {total_employment} employed, {unemployment_rate} unemployment, {unfilled_jobs} unfilled jobs." The rate is `unemployment_rate_bps` rendered through the existing `formatBpsPercent`. |
  | `production_summary` | "Production: {total_gross_output} output; {sectors_capacity_constrained} sectors at capacity, {sectors_labor_constrained} short of workers." |
  | `tax_bases_derived` | "Tax bases: personal income {…}, corporate profit {…}, consumption {…}." |
  | `turn_resolved` | "Turn {turn} resolved." |

  Every count and amount is digit-grouped through `formatAmount`. A missing param falls back to the
  generic label, which is the rule every existing driver already follows.
- `isRoutineDriver(driver)` is the one authored rule. It reads only `reason_id` and stored params.
  - **Routine:** `labor_market_resolved`, `production_summary`, `tax_bases_derived` and
    `turn_resolved`.
  - **`resource_extraction_resolved`** is routine **only when** `deposits_depleted == 0` **and**
    `unassigned_resource_workers == 0`. If either figure is missing it stays visible, so only a
    confirmed quiet extraction is folded.
  - **`sector_inactive` is never routine.**
  - Every other reason stays visible, in server order.

**`frontend/src/greybox/TurnResultView.tsx`**

This component is shared by the live Turn result and History, so everything below applies to both.
- Consequential drivers render first, in "Why this happened" (`data-testid="drivers-consequential"`).
- Routine drivers render in a **controlled** `<details>` titled "Routine steps this turn (N)"
  (`drivers-routine`). It is closed by default, and its sentences carry their figures.
- **T2.** No reason ID is painted beside a sentence any more.
  - Each driver `<li>` has an anchor `id`, `data-reason-id` and `tabIndex={-1}`.
  - The collapsed Trace ("Show exact values") gains a "Reasons recorded" list. It has one real link
    (`href="#…"`) per driver, in the same order, showing the reason ID.
  - Activating a link by click or by Enter does three things:
    1. opens Routine steps if the target is inside it;
    2. scrolls to the target;
    3. moves focus to that `<li>`.
- **Deviation from the plan, recorded:** the anchor is `{useId()}driver-{index}` rather than a bare
  `driver-{index}`. The prefix scopes the ID to one rendered view, so two views on one page cannot
  collide. Links resolve with `getElementById`, so the prefix's characters need no escaping.

## 2. U6: the headline matches the ledger

**What was wrong (O7).** A blocked budget always read "The budget was blocked. Committed capital was
still spent.", even directly above a ledger that said "Nothing was committed this turn."

**What changed (`backend/app/api/projections.py`).** In the `FAILED_LEGISLATIVE` branch the clause
is appended only when `_capital_committed_to_the_vote(report)` holds. That means a
`political_capital.expenditures` row in category `LEGISLATIVE_INFLUENCE` or `LEGISLATIVE_BARGAIN`
with a positive amount. Otherwise the headline is "The budget was blocked.". The tone is unchanged
(`negative`), and every other headline is byte-identical.

**A deliberate refinement of the approved plan, recorded here as planned.** The plan said "only when
the turn's ledger is non-empty". The implementation is narrower: a relationship investment made in
the same turn is **not** spending on the vote, so on its own it does not trigger the clause. Under the
plan's literal rule, a blocked budget plus an unrelated investment would still have said "Committed
capital was still spent", which implies that capital went to the vote when none did. A test pins this
case.

## 3. Tests

**Backend: new, 5**
- `tests/test_api_blocked_headline.py` (3). Each resolves a real Valdrun turn whose budget the
  legislature blocks, and asserts that precondition first.
  - `test_a_blocked_budget_with_nothing_committed_does_not_claim_capital_was_spent`: the ledger is
    `[]` and the headline is exactly "The budget was blocked.".
  - `test_a_blocked_budget_with_influence_spent_says_so`: 10 capital of influence on
    `opposition_party/main` gives the full clause.
  - `test_a_relationship_investment_alone_is_not_spending_on_the_vote`: the ledger is non-empty, and
    there is no clause.
- `tests/test_sector_label_drift.py` (2).
  - `test_sector_labels_equal_the_engine_sectors`: the `SECTOR_LABEL` keys, read from `format.ts`,
    equal `{c.value for c in SectorCategory}`, with no duplicates.
  - `test_the_block_is_actually_parsed`: an anti-vacuity check that exactly 11 entries were parsed.
  - **Mutation check:** I deleted the `technology` line from `format.ts` and both tests failed
    (`2 failed`). The file was then restored and verified with `cmp`.

**Frontend: new, 26 (494 → 520)**
- `src/format/turn-result.test.ts` (16), using the engine's real param names:
  - `unemployment_rate_bps` 0, 520 and 10,000 render as "0.00%", "5.20%" and "100.00%";
  - production, tax bases and turn sentences;
  - the missing-param fallback;
  - the named inactive sector, and the fallback for an unknown sector;
  - depleted and unplaced extraction sentences;
  - `isRoutineDriver` for the four routine reasons, `sector_inactive`, both extraction branches
    (and missing params), and other reasons;
  - `SECTOR_LABEL` has 11 non-empty entries without underscores.
- `src/greybox/TurnResultView.ux2.test.tsx` (5 cases × {live, History} = 10). They render through the
  real `ResultScreen` and the real `HistoryScreen`, with a turn selected:
  - no reason ID in the painted text;
  - consequential drivers stay visible, and Routine steps are closed with a count of 3;
  - the Trace lists one link per driver, in order, each resolving to an existing anchor with a
    matching `data-reason-id`;
  - Enter on a routine reason opens Routine steps and focuses that `<li>`;
  - Enter on a visible reason focuses it and leaves Routine steps closed.

  jsdom does not move focus on Tab or turn Enter on a link into activation. So these tests assert
  that the link is a real, tabbable `href` link, focus it, and dispatch the click that Enter produces.
  **The genuine key presses are exercised in the browser** (next item).

**Browser**
- `e2e/verify-ux.spec.ts`, new block `@ux2`, at 1440, 390 and 320. It plays Valdrun through the
  interface: select the tax card, then Resolve, then Confirm. A legislative route with no capital
  blocks the budget. The block then checks:
  - **U6:** the ledger is `[]`, the headline is exactly "The budget was blocked.", and the clause is
    not on the page;
  - **U4:** `findIdentifierLeaks` finds no reason ID in rendered text or player-visible attributes;
    Routine steps is closed and non-empty; the blocked-budget sentence is visible;
  - **keyboard only, live:** Enter on "Show exact values", Tab until the `labor_market_resolved` link
    has focus, then Enter. Focus is that `<li>`, its sentence matches the labour wording, and Routine
    steps is open;
  - **History:** the same turn's drivers text equals live text for text, there are no leaks, and the
    same keyboard path ends on the same element.
  - **axe on the new parts:** with Routine steps open and the Trace links rendered, axe over
    `turn-result-view` reports **0 violations**, live and in History, at each viewport (25–26 rules
    passed each time, so it did evaluate). See §5 for why this was added.
- `e2e/campaigns.spec.ts`: the T2 observation is now an assertion. No driver line contains a `<code>`
  element, and `findIdentifierLeaks` over the turn's reason IDs is `[]` on live and on History. The
  record's `t2ReasonIdCodeElements` field becomes `t2ReasonIds`.
- `verify:ux:2` runs `--grep "@ux1|@ux2"`, so UX-1's block is re-proved.

## 4. Gates

Each gate was run separately, and each exit status is the command's own `$?`.

| command | exit | result |
|---|---:|---|
| `npm test` | 0 | `Tests  520 passed (520)`: 494 → 520, +26 (16 in `format/turn-result.test.ts`, 10 in `greybox/TurnResultView.ux2.test.tsx`) |
| `npm run typecheck` | 0 | clean |
| `npm run build` | 0 | JS `index-gQH7iXGV.js` 350.75 kB / 101.43 kB gzip |
| `npm run check:bundle` | 0 | `check-bundle: OK -- … initial JS 97.80 KiB gzip (level 9) of a 250 KiB budget, 152.20 KiB headroom.` |
| `npm run check:palette` | 0 | `check-palette: OK -- 40 source file(s), 16 colour token(s) defined, no default-palette colour, no sub-60 text alpha, every referenced token defined.` |
| `npm run check:copy` | 0 | clean (allowlist printed, unchanged) |
| `npm run check:css-sources` | 0 | `check-css-sources: OK -- source(none), 2 shipped source pattern(s), 1 exclusion(s): …` |
| `npm run verify:ux:2` | 0 | `11 passed (14.0s)`: 5 preflight, the `@ux1` block ×3 and the `@ux2` block ×3 (1440, 390, 320). This is the **re-run** after the axe check was added (§5). |
| `npm run verify:campaigns:ux2` | 0 | `7 passed (24.3s)` |
| `npm run verify:terminal:ux2` | 0 | `6 passed (31.4s)` |
| `npm run verify:fixes:ux2` | 0 | `13 passed (36.1s)` |
| `npm run verify:icons:ux2` | 0 | `7 passed (10.6s)` |
| `npm run audit:stress:seated:ux2` | 0 | `6 passed (6.0s)` |
| `npm run audit:accessibility:verify:ux2` | 0 | `6 passed (1.3m)`; `accessibility report written: 0 findings (0 WCAG AA, 0 best-practice), 4 needs-review, 89 surfaces` |
| `ruff check .` (backend) | 0 | `All checks passed!` |
| `ruff format --check .` (backend) | 0 | `192 files already formatted` |
| bare `mypy` | 0 | `Success: no issues found in 56 source files` |
| `npm run generate:api` | 0 | no change to `docs/contracts/` or `frontend/src/api/`: **byte-identical** (62 / 13 / `0.23.0`) |
| full backend suite on `bf66b8e6` + UX-2 | **0** | `36368 passed, 1 warning in 1444.74s (0:24:04)`: +5 from 36,363 (3 headline tests and 2 drift-guard tests) |
| full backend suite on `8923843` (UX-1a) + UX-2, **the tree committed here** | **0** | `36369 passed, 1 warning in 1408.86s (0:23:28)`: 36,364 + 5 |

The suite was run twice because the UX-1a correction landed beneath this work while it was
uncommitted. The second run covers the exact tree this commit records. The 1 warning is the known
`StarletteDeprecationWarning`.

**Artifacts compared with UX-1's:**

| artifact | disposition |
|---|---|
| `gate-4a3-ux2-verification.json` | byte-identical to `gate-4a3-ux1-verification.json` |
| `gate-4a3-ux2-icon-coverage.json` | byte-identical to `gate-4a3-ux1-icon-coverage.json` |
| `gate-4a3-ux2-terminal.json` | byte-identical to `gate-4a3-ux1-terminal.json` |
| `gate-4a3-accessibility-after-ux2.{json,md}` | byte-identical to `…-after-ux1.{json,md}`. §5 explains why this is expected. |
| `gate-4a3-ux2-stress-seated-cabinet.json` + both screenshots | byte-identical to UX-1's |
| `gate-4a3-ux2-campaigns.json` | It differs in exactly these fields: `newFeatures.t2ReasonIdCodeElements` (UX-1: `count 27, painted 27`) is replaced by `newFeatures.t2ReasonIds` (`codeElementsInDriverLines 0`, `leaksOutsideTraceLive 0`, `leaksOutsideTraceHistory 0`); and `sameOrigin.distinctPaths[10..11]`, because both built asset names changed: JS `index-BM4phN3N.js` → `index-gQH7iXGV.js`, and CSS `index-DjFAPDAb.css` → `index-DKT4_7kz.css`. The CSS changed because UX-2 uses a utility class the build did not emit before: `list-decimal`, for the Trace's numbered reasons list. Every other field is equal. |
| `gate-4a3-ux2-verify-ux.json` | new; the `@ux1` entries plus the `@ux2` entries with their axe counts |

## 5. A coverage gap found while gating, and closed here

`gate-4a3-accessibility-after-ux2` came out **byte-identical** to UX-1's, even though UX-2 changes the
Turn result's DOM. The reason is that the accessibility baseline (`e2e/accessibility.spec.ts`) starts a
campaign and visits every screen **without resolving a turn**. So its eight "Turn result" surfaces are
the empty state. They never rendered a driver, the Routine steps disclosure or a Trace link, under UX-1
or under UX-2. That baseline is unchanged and keeps its exact scope.

Without a further check, the new UX-2 elements would have gone unaudited by axe. The `@ux2` block
therefore runs axe over `turn-result-view` with Routine steps open and the Trace links rendered, live
and in History, at each viewport. It requires 0 violations and more than 0 passed rules. The result
was 0 violations everywhere.

**The superseded artifact.** The first `verify:ux:2` run (`11 passed`, exit 0) was made before this
axe check existed. Its output, `gate-4a3-ux2-verify-ux.json`, was **untracked** (confirmed with
`git ls-files --error-unmatch`). I moved a copy out of the repository and removed it, then re-ran
`verify:ux:2` against the final spec under the same name. No committed artifact was touched.

## 6. Scope

- **Backend:** `app/api/projections.py` (U6), plus the two new test files.
- **Frontend:** `format.ts`, `TurnResultView.tsx`, and two new test files.
- **e2e:** `verify-ux.spec.ts` (`@ux2`), `campaigns.spec.ts` (the T2 assertion), and the `:ux2`
  scripts in `package.json`.
- **Records:** this file and the `gate-4a3-ux2-*` and `gate-4a3-accessibility-after-ux2.*` artifacts.
- **Out of scope, and not in the diff:** `app/simulation/`, `app/core/`, any scenario, fixture, frozen
  plan, the contract, and every earlier review artifact.
