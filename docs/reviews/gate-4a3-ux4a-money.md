# Gate 4A3 UX-4a: plain money (U9), and a unit defect in UX-2 fixed

This is the first of the split UX-4 commits, approved in the UX-4 plan and its addendum. It
implements U9 and fixes a defect I introduced in UX-2. It changes no engine, `app/core`, scenario,
contract shape, budget or playtest protocol, and the CLI and the reports are untouched.

## 1. U9: money a player can read (O8)

**What was wrong.** The Dashboard's Money card and the national header showed the treasury as
`100000000.00`, and the card's balance line as an unsigned `3150000.00`.

**What changed.**
- **New `app/api/display.py: format_money_display(amount, *, signed=False)`.**
  - It renders digit grouping and two decimals.
  - A negative amount always carries `-`.
  - `signed=True` adds `+` to a positive amount, because that text states a change.
  - Zero is never signed.
- **Where it is used.** Only the Money concern in `projections.py` uses it:
  - `headline` is unsigned, so the treasury reads `100,000,000.00`;
  - `delta_text` is signed, so the balance after a turn reads `+3,150,000.00`.

  The header renders the concern headlines, so it reads the same.
- **What is unchanged.** `app.core.money.format_money` is byte-identical to its `d1c09201` blob (a
  test asserts this). The CLI and reports still print `100000000.00`, which is also tested.
- **The contract** is unchanged. These are the same string fields with different text, and
  `generate:api` is byte-identical.

## 2. A defect in UX-2, found while planning this commit, and fixed

**What was wrong.** UX-2's routine "Tax bases" sentence rendered `personal_income`, `corporate_profit`
and `taxable_consumption` with `formatAmount`, which is a count formatter. Those params are
**`Money`, an integer count of minor units at 100 to the denar** (`MINOR_UNITS_PER_DENAR`), and the
CLI renders them with `format_money`. So every tax base appeared **100 times too large**. On Valdrun's
first turn, personal income showed as `4,000,000,000` instead of `40,000,000.00`.

**Why UX-2's tests missed it.** The UX-2 unit test pinned the wrong output: it fed
`100,000,000` minor units and expected `"100,000,000"`. That expectation is corrected here, with the
reason in a comment, to `"1,000,000.00"`. Nothing else in UX-2 depended on it.

**The fix.**
- A new `formatMoney(minorUnits)` in `format.ts` mirrors `format_money_display`.
- The tax-bases sentence now uses it.

**The guard that would have caught it.**
`tests/test_money_display.py::test_every_money_param_the_browser_words_goes_through_format_money`
works like this:
- It reads `app/cli.py` and lists every param the CLI renders through `format_money(...)`.
- For each one that `format.ts` also words, it requires the bound name to reach `formatMoney` and
  never `formatAmount`.
- **Mutation check:** I put `formatAmount(personal)` back and exactly that test failed. The file was
  then restored and verified with `cmp`.

## 3. R4, recorded and not fixed (as ruled)

Foreign-assistance amounts ("sent 38,150,000 in assistance") are minor units as well, so that
example is 381,500.00 denars. The CLI and the browser render them identically, and a test on each side
pins that parity. The CLI is out of scope for U9, so this is added to the UX risk list rather than
fixed.

## 4. Tests

**Backend: new, 11** (`tests/test_money_display.py`)
- `format_money_display`, 6 parametrised cases: `100,000,000.00`; `+3,150,000.00`; `-12.05`, both
  signed and unsigned; `0.00` with `signed=True`, which stays unsigned; and `0.07`.
- The Money headline through the real API is grouped.
- `app/core/money.py` equals its `d1c09201` blob.
- The CLI's tax-bases line still prints `21500000.00`.
- An anti-vacuity check: the CLI's money params are really found (at least the three tax bases and
  `amount`).
- The drift guard (§2).

**Frontend: new, 9** (`src/format/money.test.ts`; 541 → 550)
- `formatMoney`, 6 cases: `100,000,000.00`, `3,150,000.00`, `12.05`, `-12.05`, `0.07` and `0.00`.
- 100 minor units to the denar.
- `formatAmount` and `formatMoney` differ by exactly that factor, which states the defect.
- The tax-bases sentence in denars.

**Frontend: one existing expectation corrected.** In `src/format/turn-result.test.ts`, the
tax-bases expectation is changed for the reason given in §2.

**Browser: `@ux4a` in `e2e/verify-ux.spec.ts`, Valdrun at 1440, 390 and 320.**
- The API's Money headline is grouped, and the Dashboard card and the national header both show it.
- After one turn, the tax-bases line in Routine steps equals a sentence built **independently in the
  test** from the resolve response's own params, at 100 minor units to the denar.
- After one turn, the Money delta is signed and grouped, and the card shows it.
- Measured: `100,000,000.00`, then `+3,150,000.00` after the turn. The tax bases read `40,000,000.00`,
  `20,000,000.00` and `30,000,000.00`.

## 5. Gates

Each gate was run separately, and each exit status is the command's own `$?`.

| command | exit | result |
|---|---:|---|
| `npm test` | 0 | `Tests  550 passed (550)`: 541 → 550, +9 (`format/money.test.ts`) |
| `npm run typecheck` | 0 | clean |
| `npm run build` | 0 | JS `index-CP0bckiT.js` 353.53 kB / 102.23 kB gzip; CSS `index-ClnHb-Eg.css`, **unchanged** from UX-3a |
| `npm run check:bundle` | 0 | `check-bundle: OK -- … initial JS 98.56 KiB gzip (level 9) of a 250 KiB budget …` |
| `npm run check:palette` | 0 | `check-palette: OK -- 41 source file(s), 16 colour token(s) defined, …` |
| `npm run check:copy` | 0 | `check-copy OK: 344 player-visible strings across 41 files, 15 forbidden words, whole-word matched.` |
| `npm run check:css-sources` | 0 | `check-css-sources: OK -- …` |
| `npm run verify:ux:4a` | 0 | `17 passed (18.0s)`: 5 preflight, then `@ux1`, `@ux2`, `@ux3` and `@ux4a` at three viewports each |
| `npm run verify:campaigns:ux4a` | 0 | `7 passed (22.4s)` |
| `npm run verify:terminal:ux4a` | 0 | `6 passed (29.1s)` |
| `npm run verify:fixes:ux4a` | 0 | `13 passed (34.5s)` |
| `npm run verify:icons:ux4a` | 0 | `7 passed (10.2s)` |
| `npm run audit:stress:seated:ux4a` | 0 | `6 passed (5.7s)` |
| `npm run audit:accessibility:verify:ux4a` | 0 | `6 passed (1.2m)`; `0 findings (0 WCAG AA, 0 best-practice), 4 needs-review, 89 surfaces` |
| `ruff check .` (backend) | 0 | `All checks passed!` |
| `ruff format --check .` (backend) | 0 | `195 files already formatted` |
| bare `mypy` | 0 | `Success: no issues found in 57 source files` |
| `npm run generate:api` | 0 | no change to `docs/contracts/` or `frontend/src/api/`: **byte-identical** |
| full backend suite `uv run pytest -q; echo PYTEST_EXIT=$?` | **0** | `36391 passed, 1 warning in 1344.13s (0:22:24)`: 36,380 + 11, exactly the new money tests |

**Artifacts compared with UX-3a's:**

| artifact | disposition |
|---|---|
| `gate-4a3-ux4a-verification.json`, `-icon-coverage.json`, `-terminal.json`, `-stress-seated-cabinet.json` | **byte-identical** |
| `gate-4a3-accessibility-after-ux4a.json` | **byte-identical** to `…-after-ux3a.json` |
| `gate-4a3-accessibility-after-ux4a.md` | differs only in its own artifact name (lines 1, 4 and 5) |
| `gate-4a3-ux4a-campaigns.json` | differs only in `sameOrigin.distinctPaths[10..11]`: the new JS filename `index-CP0bckiT.js` sorts ahead of the unchanged CSS |
| both seated-cabinet **screenshots** | differ: the national header now reads "Money: 500,000.00", where it read "500000.00". Inspected at 390×844. |
| `gate-4a3-ux4a-verify-ux.json` | new |

## 6. Scope

- **Backend:** the new `app/api/display.py`, two lines in `app/api/projections.py` (and one unused
  import removed), and the new `tests/test_money_display.py`.
- **Frontend:** `format.ts` (`formatMoney`, and the tax-bases sentence), the new
  `format/money.test.ts`, and one corrected expectation in `format/turn-result.test.ts`.
- **e2e:** `verify-ux.spec.ts` (`@ux4a`, and a `delta_text` field on its dashboard type) and the
  `:ux4a` scripts.
- **Unchanged:** `app/core/` (asserted), the CLI, `app/simulation/`, every scenario and fixture, the
  contract, and every committed artifact.
