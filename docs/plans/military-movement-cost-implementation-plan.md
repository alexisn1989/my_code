# Military movement cost — implementation plan

**Status: Revision 1, DRAFT for approval. Not frozen; nothing here is to be executed until approved.**

Prepared after the user's two rulings of 2026-10-08:
- the currency is **political capital**;
- the scope is **cost only**.

It builds on the military movement vertical slice (frozen plan
`military-movement-vertical-slice-implementation-plan.md`, ADR 0018). Every claim about current code
below was read from the tree at `cd338e0`, and file and line references are to that commit.

## 0. What this slice is, honestly

ADR 0018 shipped movement as infrastructure: an order is legal, applied, reported and reconciled, and
**free**. The ADR names the next question: "a free action with no consequence is not yet a strategic
choice."

This slice prices the existing order in political capital, the currency every other player action
already spends.

**It changes nothing else**, and the following stay true after this slice:
- one order a turn, one edge, one branch;
- no transit, combat, casualties, supply, readiness or foreign entry;
- a formation's location affects no other mechanic: not legitimacy, coup risk, the economy, or the
  W1 conflict progression.

**What it makes true that was false.** Moving a formation now competes, in the same turn and from the
same pool, with:
- a decree (250);
- a cabinet appointment (120–300);
- a legislative bargain (105–165);
- a promise release (250);
- an amendment by decree (400);
- relationship investment and legislative influence.

Capital not spent is still regenerated and capped exactly as now.

**A correction to the question that framed this plan.** When asking for the currency ruling, I said
Valdrun "regains about 133 a turn". **That was wrong**: the figure came from a unit-test fixture
(`frontend/src/format/consequences.test.ts`), not from the engine. The engine's rule is
`legitimacy.political_capital_regeneration`:
`200 + legitimacy_bps × 300 / 10,000` (`app/simulation/legitimacy.py:259`), clamped by capacity in
`resolve_political_capital`. So Valdrun, at 60% legitimacy, regenerates **380** a turn. The
calibration in §3 uses the engine's figure.

## 1. Where the cost lives: a seventh capital sink

**Today** (`app/simulation/phases.py:2423–2526`, `_finish_validate_and_reserve_actions`), slot 1 sums
six sinks:
- the legislative route or decree;
- relationship investment;
- amendment;
- cabinet appointment;
- legislative bargain;
- promise release.

It raises `DecisionSetError` when the total exceeds **opening** capital, and builds one canonical
expenditure ledger (`CapitalLedgerScratch`). Slot 10 spends `total_committed`, and slot 15 reports
the ledger.

**This slice adds movement as the seventh sink, in the same function and with the same shape:**

| item | decision |
|---|---|
| category | new `CapitalExpenditureCategory.MILITARY_REDEPLOYMENT = "military_redeployment"` (`app/simulation/legislature.py:117`). The values are alphabetical and declaration order is canonical, so it is declared **between `LEGISLATIVE_INFLUENCE` and `PROMISE_RELEASE`**. The enum docstring's "position is load-bearing" rule applies. |
| shape | **untargeted**, as `DECREE`, `CABINET_APPOINTMENT`, `LEGISLATIVE_BARGAIN` and `PROMISE_RELEASE` are: `party_id` and `bloc_id` are `None`. **At most one row a turn, carrying the summed cost.** That keeps the ledger order a property of the sort key, and the enum docstring requires it of untargeted categories. Which formation moved, and where, stays on `MovementReport` (`FormationMovementRow`), where it is already typed. |
| price | `MOVEMENT_ORDER_CAPITAL_COST × len(decision.orders)`. It is a constant in `app/simulation/military.py`, beside the classifier. With the cap at one order (`MOVEMENT_ORDERS_PER_DECISION`, `decisions.py:499`), the total is the constant or 0. **Pricing per order means a later cap increase changes no formula.** |
| digest | each untargeted row carries `decision_digest`. A new `military_movement_decision_digest(decision)` joins `cabinet_decision_digest` and the rest in `decisions.py:1004–1073`, built the same way. |
| when priced | slot 1, from the decision alone. Legality was already decided before any phase by `resolver._validate_decision_set` → `movement_order_problems`, which is unchanged. So an illegal order never reaches pricing, and **a legal order is always charged**. There is no refusal path like the bargain's: a legal move is applied. |
| affordability | the existing total-versus-opening guard, with no new guard. The `DecisionSetError` message gains a `military redeployment {n}` term, so the refusal names every component as it does today. |
| applied | **unchanged.** Slot 8's `_apply_military_movement` still moves the formation, and slot 10 spends the ledger total, which now includes the movement row. |

**Why political capital is the right currency here, stated as a design claim for your review.**
Ordering a redeployment is a government act that spends the same scarce attention as a decree or an
appointment. Treasury money (the `defense` spending line) and transit time were the alternatives you
declined. Both remain open for later gates, and nothing here forecloses either.

## 2. What each surface shows

| surface | change | how |
|---|---|---|
| **`/preview`** (`app/api/preview.py:166–237`) | a new term in `committed_capital` | `_movement_cost(state, decision_set)` returns `MOVEMENT_ORDER_CAPITAL_COST × len(orders)` for a set `movement_order_problems` accepts. It imports the engine constant, so the preview cannot quote a different price. A set with a movement problem is already refused at `preview.py:129`, before pricing. |
| **`PreviewProjection`** (`projections.py:495–524`) | **new field `military_redeployment_capital: int = 0`**, beside `cabinet_capital` and `promise_release_capital` | **A contract change.** `generate:api` changes `schema.d.ts`, and the openapi schema field count rises by one. This is recorded, not hidden. |
| **`MilitaryProjection`** (`projections.py:1894`) | **new field `order_capital_cost: int`** | **A contract change.** The map's review step can then say what the order will cost before it is staged. Today it can't know, and a price shown only after staging would be a surprise. |
| Decisions, `ConsequencesPanel` (`frontend/src/greybox/policy/ConsequencesPanel.tsx:47`) | a "Military redeployment" row in the committed-capital list | Zero terms are already hidden (UX-1), so it appears only when a move is staged. |
| Strategic map, review step | one sentence: "Moving {formation} to {theater} costs {N} political capital." | Composed in `format.ts` beside `movementStagedLine` (`format.ts:913`), from `order_capital_cost`. |
| "This turn's draft" (UX-4b, `StagedActionsList`) | the movement entry gains its price as a consequence line | The same pattern as a cabinet transfer's companion line. `stagedActions` counts are unchanged, because the movement is still one action. |
| Turn result ledger (`projections.py:2034–2049`) | a "Military redeployment — N" row | **No change needed.** The label is derived from the category value (`value.replace("_", " ").capitalize()`), so this is automatic. A test pins the exact text. |
| `political_capital_ledger_resolved` driver params (`phases.py:5154`) and CLI renderer (`cli.py:299`) | **unchanged** | The params today split `legislative_committed` and `relationship_committed`, and every other sink is already reported only through `total_committed` and the ledger rows. This slice follows that rather than adding a third split. Noted as a deliberate non-change. |

**Copy is fixed by this plan and checked by `check:copy`:**
- **Map:** "Moving {formation} to {theater} costs {N} political capital."
- **Ledger:** "Military redeployment".
- **The refusal term:** "military redeployment {n}".

## 3. Calibration — REQUIRES APPROVAL

**Proposed: `MOVEMENT_ORDER_CAPITAL_COST = 150`.**

**The method.** The value must satisfy three properties, each computed from the shipped scenarios'
authored values and pinned by a test (§5, T7) that reads the scenario files, not a hand-copied table:

1. **A real conflict on turn 1 in the showcase scenario.** In Valdrun (opening 500):
   - a decree plus a move is affordable: 250 + 150 = 400 ≤ 500;
   - a decree plus a move plus even the cheapest appointment is not: 400 + 120 = 520 > 500.

   So the player must choose.
2. **Not affordable alongside a decree in the tight scenario.** In `deficit_demo` (opening 300),
   250 + 150 = 400 > 300. A move and a decree cannot both happen on turn 1. That is the "capital spent
   here is unavailable elsewhere" claim in its plainest form.
3. **Sustainable alone, not free in a loop.**
   - Valdrun regenerates 380 a turn at 60% legitimacy.
   - A move every turn (150) is below that, so moving alone never drains the stock.
   - A decree and a move every turn (400) is above it, so doing both every turn draws the stock down
     by 20 a turn until legitimacy changes the regeneration.

**Against the existing price landscape:**
- 150 sits above the bargain's floor (105) and the cheapest appointment (120);
- it sits below a decree and a promise release (250 each).

That fits a routine government act cheaper than acting by fiat.

**Alternatives you may prefer:**
- **120** equals the cheapest appointment. A decree plus a move plus an appointment would then be
  exactly 490, which is affordable, so property 1 is lost.
- **200** keeps all three properties, but a move every turn takes over half of Valdrun's regeneration.

| scenario | opening / capacity | legitimacy | regeneration | decree + move (150) | + cheapest appointment |
|---|---|---|---:|---|---|
| `decree_state` (Valdrun) | 500 / 1,000 | 60.00% | 380 | 400: affordable | 520: **refused** |
| `deficit_demo` | 300 / 800 | 60.00% | 380 | 400: **refused** | — |
| `tiny_valid` | 500 / 1,000 | 70.00% | 410 | 400: affordable | 520: **refused** |

The regeneration column is `200 + legitimacy_bps × 300 / 10,000` from each file's authored
`legitimacy_bps`, and test T7 recomputes every cell.

## 4. Ruleset, saves and the playtest — REQUIRES APPROVAL on sequencing

- **Ruleset `0.23.0` → `0.24.0`.** Turn resolution changes, since a legal move now spends capital.
  `SUPPORTED_RULESET_VERSIONS` is the current ruleset only (`save_format.py:50`), so **every
  `0.23.0` save becomes unloadable**. That includes any save a playtester makes on the approved
  build. This is the established trade (ADR 0018 made the same one).
- **A new fixture** joins the 22 in `backend/tests/fixtures`:
  `movement_cost_save_ruleset_0.24.0.json`, holding a campaign with one paid move. The existing
  fixtures stay byte-identical. A test asserts that a `0.23.0` save is refused with
  `UnsupportedRulesetVersionError`, extending `backend/tests/test_compatibility.py`.
- **`SUPPORTED_CONTENT_VERSIONS` is unchanged** (`0.19.0`). No scenario file changes: the cost is an
  engine constant, as every other price is.
- **Sequencing — recommended: freeze this plan now, and implement only after the five-person playtest
  has reported.** Two reasons:
  - The playtest protocol says that if fewer than three of five want another turn, "Stop. Do not add
    systems" (`docs/playtest/gate-4a3-external-playtest-protocol.md`). A movement price is a new
    system.
  - Implementing it first would also change the build under test. The alternative is to implement now
    on this branch, leaving the approved archive (`f542cf28…`) untouched for the playtest. That is
    possible, but the next release from this branch would no longer be the playtested game.

## 5. Tests

| id | what | where |
|---|---|---|
| T1 | a legal one-order movement turn charges exactly `MOVEMENT_ORDER_CAPITAL_COST`: one `MILITARY_REDEPLOYMENT` row, untargeted, with the movement decision's digest | `tests/test_military_movement_cost.py` (new) |
| T2 | a turn with no movement has **no** such row, and its ledger is byte-identical to the same turn resolved under the old rule | same |
| T3 | **affordability, at the boundary:** opening capital exactly equal to the total is accepted, and one short is refused with a `DecisionSetError` naming "military redeployment 150" | same |
| T4 | the illegal-order paths are unchanged: every `MovementSubmissionCode` is still raised before pricing, and no capital is charged | same, over the existing negative matrix |
| T5 | **preview parity:** `/preview`'s `military_redeployment_capital` and `committed_capital` equal the resolver's ledger, row for row, for a move alone, a move plus a decree, a move plus an appointment, and the refused combination | `tests/test_api_preview_parity.py` (extended) |
| T6 | reconciliation group 61 (below): a positive case plus negative controls, one per field (category, amount, target, digest, presence when moved, absence when not) | `tests/test_reconciliation*.py` pattern |
| T7 | **calibration:** reads all three scenario files and recomputes every cell of the §3 table from the engine functions | new |
| T8 | the category's position: the enum is sorted by value, and ledger order is canonical with the new row present | extends the existing enum test |
| T9 | **contract:** `PreviewProjection` and `MilitaryProjection` carry the new fields, and `generate:api` output is committed | `npm run generate:api`, then the contract tests |
| T10 | **frontend unit:** the map sentence, the panel row, the draft-list consequence line and the ledger label, as exact strings. Zero hides the panel row | `format/*.test.ts`, `greybox/*.test.tsx` |
| T11 | **browser:** stage a move on the map, see the price, preview on Decisions, see the row, resolve, see the ledger row. A move plus a decree plus an appointment in Valdrun is refused with the named components | a new `@mc1` block in `verify-ux.spec.ts` |
| T12 | **determinism:** the new fixture replays byte-identically, and two runs of the same seed and decisions produce identical saves | the fixture-replay pattern |

**Reconciliation group 61** (`app/simulation/reconciliation.py`, after group 60) is the flat-cost
check group 60 makes for `PROMISE_RELEASE`, made for movement:
- a movement decision with k ≥ 1 orders ⇔ exactly one `MILITARY_REDEPLOYMENT` row;
- that row charges `k × MOVEMENT_ORDER_CAPITAL_COST`, is untargeted, and carries the digest of that
  decision;
- no movement decision ⇔ no such row.

Group 54 (formation movement) is unchanged.

**The report-level validators** at `report.py:2608–2615` and `3008–3010` enumerate the untargeted
categories. The new member is added there, and their tests extend to it.

**Mutation checks:**
- charging 0, which fails T1, T5 and group 61;
- charging before legality, which fails T4;
- a mis-ordered enum member, which fails T8;
- a preview price that is not the engine's constant, which fails T5.

## 6. Proposed commits — DO NOT EXECUTE

1. **MC-1: engine, contract and surfaces together.**
   - **Engine and contract:** the category, constant, digest, slot-1 sink, report validators, group 61,
     the ruleset bump, the fixture, the preview term, the two projection fields and `generate:api`.
   - **Frontend:** the panel, map sentence, draft line and copy.
   - **Tests:** T1–T12.

   One commit, for ADR 0018's reason: an intermediate state where a move is charged but the interface
   can't say so, or is priced in the preview but not by the engine, is a defect no focused test makes
   safe.
2. **MC-2: records and release.** An ADR (`0021-military-movement-cost.md`), the roadmap entry, every
   browser gate under fresh names, and a release verification and enforced dry run of the resulting
   archive under fresh names. **It does not replace the approved playtest build** unless you rule so.

**Gates, each with its real `$?`:**
- **Backend:** ruff, mypy and the full suite.
- **Frontend:** `npm test`, typecheck, build and `check:*`.
- **Contract:** `generate:api`, a **changed** contract that is committed and itemised.
- **Browser:** every browser gate.
- **Stop and report on:**
  - any existing fixture changing bytes;
  - a preview and resolver disagreement;
  - a calibration cell that does not hold;
  - any formation-location effect appearing anywhere outside slot 8.

## 7. Explicit exclusions

**Not changed by this slice:**
- one order a turn;
- one edge, one branch;
- no transit, combat, casualties, supply, readiness, morale or foreign entry;
- no effect of location on any mechanic;
- no treasury charge and no `defense` spending link;
- no change to regeneration or capacity;
- no scenario file change;
- no cost that varies by route, distance or formation.

Each is a later gate's question, to be asked by its own audited plan.
