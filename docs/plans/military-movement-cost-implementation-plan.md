# Military movement cost — implementation plan

**Status: Revision 2a — accepted by the user as DEFERRED PLANNING ONLY. NOT AUTHORIZED FOR
IMPLEMENTATION.** Nothing here may be executed
until two conditions both hold: the five-person external playtest has reported, **and** the user has
given a separate go-ahead. The price of **150 is provisional**. The approved playtest build (the
archive built from `a322484`, `f542cf28…`) is unchanged by this document and by anything it proposes.

**Records note (2026-10-10).** By the user's ruling in `956cb05`, the approved playtest build is now
the archive built from `5236ddb` (`083c7a98…`). The build named above is historical. Nothing else in
this plan has changed.

> **Deliberate loss of save compatibility.** Implementing this plan bumps the ruleset from
> `0.23.0` to `0.24.0`. The engine supports only the current ruleset
> (`SUPPORTED_RULESET_VERSIONS`, `backend/app/simulation/save_format.py:50`), so **every `0.23.0`
> save becomes unloadable**. That includes every save made on the approved playtest build. This is
> intended, the same trade ADR 0018 made, and it is the main reason implementation waits for the
> playtest.

**Rulings this revision rests on:**
- **2026-10-08:** the currency is **political capital**, and the scope is **cost only**.
- **The Revision 1 review:**
  - 150 as a **provisional** price;
  - implementation **deferred** until after the playtest **and** a separate go-ahead;
  - three corrections, listed in §8.

It builds on the military movement vertical slice (frozen plan
`military-movement-vertical-slice-implementation-plan.md`, ADR 0018). Code references are to
`cd338e0`, and every scenario figure in §3 was read from the engine's own `/api/game/decision-options`
on a fresh campaign of each scenario at that commit.

## 0. What this slice is, honestly

ADR 0018 shipped movement as infrastructure: an order is legal, applied, reported and reconciled, and
**free**.

**This slice prices that existing order in political capital, and does nothing else.**

**What stays true after it:**
- one order a turn, one edge, one branch;
- no transit, combat, casualties, supply, readiness or foreign entry;
- a formation's location affects no other mechanic: not legitimacy, coup risk, the economy, or the
  W1 conflict progression.

**The central caveat: this is pricing existing infrastructure, not proven gameplay balance.**
Moving a formation still **gains the player nothing mechanically**. Charging 150 makes movement a
*sacrifice*, because the capital is then unavailable for an appointment, a bargain or a decree that
turn. It does **not** make movement a strategically *useful* choice. A price without a benefit can
only discourage an action. Whether movement becomes worth paying for is a question for later gates
(supply, readiness, conflict effects), each needing its own audited plan. Nothing in this document
claims that 150 is balanced, only that it creates the conflicts in §3.

**A correction carried from Revision 1.** The question that framed this plan said Valdrun "regains
about 133 a turn". That figure came from a unit-test fixture
(`frontend/src/format/consequences.test.ts`), not from the engine. See §3.3 for what the engine
actually does.

## 1. Where the cost lives: a seventh capital sink

**Today** (`app/simulation/phases.py:2423–2526`, `_finish_validate_and_reserve_actions`), slot 1 sums
six sinks:
- the legislative route or decree;
- relationship investment;
- amendment;
- cabinet appointment;
- legislative bargain;
- promise release.

It raises `DecisionSetError` when the total exceeds **opening** capital, before any state is written,
and builds one canonical expenditure ledger. Slot 10 spends `total_committed`, and slot 15 reports the
ledger.

**Movement becomes the seventh sink, in the same function and with the same shape:**

| item | decision |
|---|---|
| category | new `CapitalExpenditureCategory.MILITARY_REDEPLOYMENT = "military_redeployment"` (`app/simulation/legislature.py:117`). The values are alphabetical and declaration order is canonical, so it is declared **between `LEGISLATIVE_INFLUENCE` and `PROMISE_RELEASE`**. |
| shape | **untargeted**, like `DECREE`, `CABINET_APPOINTMENT`, `LEGISLATIVE_BARGAIN` and `PROMISE_RELEASE`: `party_id` and `bloc_id` are `None`, with **at most one row a turn** carrying the summed cost. Which formation moved, and where, stays on `MovementReport` (`FormationMovementRow`). |
| price | `MOVEMENT_ORDER_CAPITAL_COST × len(decision.orders)`, a constant in `app/simulation/military.py`. With the cap at one (`MOVEMENT_ORDERS_PER_DECISION`, `decisions.py:499`), the total is the constant or 0. Pricing per order means a later cap change changes no formula. |
| digest | a new `military_movement_decision_digest`, beside `cabinet_decision_digest` and the rest (`decisions.py:1004–1073`). |
| when priced | slot 1, from the decision. Legality is decided earlier by `resolver._validate_decision_set` → `movement_order_problems`, which is unchanged. An illegal order never reaches pricing, and a legal order on an affordable turn is always charged. |
| affordability | **the existing** total-versus-opening guard, with no new guard. The `DecisionSetError` message gains a `military redeployment {n}` term. |
| applied | unchanged: slot 8 moves the formation, and slot 10 spends the ledger total. |

## 2. Preview versus resolution: two different outcomes, kept apart

**A preview and a resolution do different things with an overbudget turn, and the plan does not
conflate them.**

**Preview (`/api/game/preview`)** never rejects for cost. `decision_preflight` deliberately leaves
affordability out (`app/api/decision_preflight.py:24–27`). For a structurally valid draft that
includes a move, the preview returns:
- every capital term, including the new `military_redeployment_capital`;
- the `committed_capital` total and `opening_capital`;
- `affordable = committed_capital <= opening_capital`.

**An overbudget draft therefore previews successfully, shows every cost, and has
`affordable = false`.** The interface's existing refusal wording (UX-1) then says that resolving would
be refused.

**Resolution (`/api/game/resolve`)** of that same overbudget draft raises `DecisionSetError` in slot 1,
**before any phase writes state**. The turn is rejected:
- no state changes;
- no history entry is appended;
- no ledger, report or save is produced;
- the HTTP surface returns the existing 422 envelope.

**There is therefore no completed ledger for a rejected turn**, and no test compares one.

**What each kind of turn is compared against:**
- **An accepted turn:** the preview's capital terms are compared **row for row** with the resolver's
  ledger, and the total with `PoliticalCapitalReport.total_committed`.
- **A rejected turn:** the preview's terms are compared with the **engine's own prices** (the
  constant, `appointment_cost_capital`, the bargain's asking price, `DECREE_POLITICAL_CAPITAL_COST`).
  The test then asserts that resolution raises, and that the campaign's state, history and on-disk
  save are byte-identical before and after the attempt.

| surface | change |
|---|---|
| `/preview` (`app/api/preview.py:166–237`) | `_movement_cost(state, decision_set)` returns the constant × orders for a set `movement_order_problems` accepts (an invalid one is already refused at `preview.py:129`). It imports the engine constant, so the preview cannot quote another price. |
| `PreviewProjection` (`projections.py:495–524`) | **new field `military_redeployment_capital: int = 0`**. A contract change, recorded. |
| `MilitaryProjection` (`projections.py:1894`) | **new field `order_capital_cost: int`**, so the map can state the price before staging. A contract change, recorded. |
| Decisions, `ConsequencesPanel` | a "Military redeployment" row in the committed-capital list. It is hidden at zero, as every term is (UX-1). |
| Strategic map, review step | "Moving {formation} to {theater} costs {N} political capital." (`format.ts`, beside `movementStagedLine`) |
| "This turn's draft" (UX-4b) | the movement entry gains its price as a consequence line. Counts are unchanged. |
| Turn-result ledger (`projections.py:2034–2049`) | "Military redeployment", derived automatically from the category value. A test pins the text. |
| `political_capital_ledger_resolved` params, CLI renderer | **unchanged**, deliberately. Other sinks also appear only through `total_committed` and the ledger rows. |

## 3. Calibration — 150, PROVISIONAL

### 3.1 Legal acts with fixed engine prices, turn 1 (read from `/api/game/decision-options`)

| scenario | opening / capacity | budget by decree | cheapest accepted appointment | other accepted appointment | bargain that will deal |
|---|---|---|---|---|---|
| `decree_state` (Valdrun) | 500 / 1,000 | **available**, 250 (`decree_available: true`) | 147 (Edda Thorne, chief of staff) | 197 (Yannic Pell) | **none**: the only leader refuses (`refused_will_not_deal`) |
| `deficit_demo` | 300 / 800 | **route unavailable**: `decree_authority: emergency_only`, `decree_available: false` | 147 (Bela Ronsard) | 197 (Freya Lund) | Sofia Renn (independents), **113** |
| `tiny_valid` | 500 / 1,000 | **route unavailable**: `decree_authority: emergency_only`, `decree_available: false` | 147 (Hal Verrin; listed by the engine but used in no conflict below) | 276 (Ilse Marovec, replacing at chief of staff) | Maret Kuusk (rural alliance), **105** |

**Revision 1 mispriced the cheapest appointment.** It assumed 120, but `CABINET_APPOINTMENT_BASE_COST`
is the formula's floor at independence 0, and no shipped candidate has independence 0. The cheapest
accepted appointment in every scenario is **147**.

### 3.2 The conflicts a price of 150 creates, using legal combinations only

| scenario | without a move | with a move (150) | effect |
|---|---|---|---|
| Valdrun | decree + cheapest appointment = 397 ≤ 500: affordable | decree + move = 400: affordable; decree + move + cheapest appointment = **547 > 500: refused** | a decree, a move and an appointment cannot all happen on turn 1 |
| `deficit_demo` | bargain + cheapest appointment = 260 ≤ 300: affordable | move + cheapest appointment = 297: affordable; move + bargain = 263: affordable; move + bargain + appointment = **410 > 300: refused** | with a move, the player gets the bargain **or** the appointment, not both |
| `tiny_valid` | bargain + Marovec appointment = 381 ≤ 500: affordable | move + Marovec appointment = 426: affordable; move + bargain + Marovec appointment = **531 > 500: refused** | as in `deficit_demo` |

**Decree combinations in `deficit_demo` and `tiny_valid` are marked "route unavailable"**, and no cost
argument is made about them.

**A bargain is legal only for a proposal on the legislative route** (`bargain_route_is_legislative`,
`app/simulation/legislative_bargaining.py:192`; a decree-route bargain is refused). So every
bargain combination is built with a legislative budget proposal, and its legality is verified as in
§3.4 rather than assumed.

**Every listed conflict holds for any price from 120 to 153 inclusive:**
- the lowest bound is `tiny_valid`'s refusal, which needs 276 + 105 + m > 500, so m ≥ 120;
- the highest is `deficit_demo`'s "move + cheapest appointment fits", which needs m ≤ 153.

So **150 is inside that window, but it is not derived from it**. 120 would do equally well by these
tests. 150 is chosen against the existing price landscape: above the bargains (105–113 on offer) and
the cheapest appointment (147), and below a decree and a promise release (250). It is provisional
until the user confirms it at go-ahead.

### 3.3 Regeneration is an illustration, not a guarantee

Regeneration is `200 + legitimacy_bps × 300 / 10,000` (`legitimacy.political_capital_regeneration`,
`app/simulation/legitimacy.py:259`). It is computed from **closing** legitimacy, and the closing
capital is `min(capacity, opening + regeneration − spent)` (`resolve_political_capital`). Closing
legitimacy depends on the turn's own events, so **regeneration is not known when capital is
committed**.

**The illustration below assumes legitimacy stays at 60%,** which no turn guarantees:
- Valdrun, or `deficit_demo`, at 60%: about **380** a turn;
- `tiny_valid` at 70%: about **410** a turn.

**Under that assumption:**
- a move every turn (150) would be well inside regeneration;
- in Valdrun, a decree and a move every turn (400) would exceed it by about 20 a turn.

These are **illustrations, not predicted outcomes**. A turn that moves legitimacy changes them, and
the tests pin only the formula, never a trajectory.

### 3.4 What the calibration test verifies (T7)

For each combination in §3.2, on a fresh campaign of the named scenario:
- **Legality:** the draft *without* the move previews with no structural problem and
  `affordable: true`, and **resolves successfully**. The move alone is a legal order per
  `movement_order_problems`. The combination with the move previews successfully with every term
  present.
- **Arithmetic:** each preview term equals the engine's own price, and `committed_capital` equals
  their sum.
- **The outcome:**
  - every "affordable" row resolves;
  - every "refused" row previews with `affordable: false`, and resolution raises `DecisionSetError`
    leaving state, history and the save byte-identical (§2).
- **Unavailability:** for `deficit_demo` and `tiny_valid`, a budget submitted on the decree route is
  **refused for legality** (the existing route check), not for cost. That asserts the "route
  unavailable" cells.

## 4. Ruleset, saves and sequencing

- **The ruleset goes from `0.23.0` to `0.24.0`, and every `0.23.0` save becomes unloadable** (see the
  boxed warning at the top). A test in `backend/tests/test_compatibility.py` asserts that a `0.23.0`
  save is refused with `UnsupportedRulesetVersionError`.
- **A new fixture**, `movement_cost_save_ruleset_0.24.0.json`, holds a campaign with one paid move.
  The existing 22 fixtures stay byte-identical.
- **No scenario file or content version changes.** The price is an engine constant, as every other
  price is.
- **Sequencing:** implementation waits for the playtest's report **and** a separate go-ahead.
  - The protocol forbids adding systems after a failed playtest.
  - Implementing first would change the game under test.
- **The approved playtest build is not to be replaced** by any release built from this work unless
  the user rules so.

## 5. Tests

| id | what |
|---|---|
| T1 | a legal, affordable one-order turn charges exactly the constant: one untargeted `MILITARY_REDEPLOYMENT` row, with the movement decision's digest |
| T2 | a turn with no move has no such row, and its ledger is identical to the same turn without this slice's sink |
| T3 | **affordability at the boundary, on resolution:** total equal to opening is accepted. One over is refused with `DecisionSetError` naming "military redeployment 150", and **state, history and the save are byte-identical** before and after |
| T4 | the illegal-order paths are unchanged: each `MovementSubmissionCode` is still raised before pricing, and nothing is charged |
| T5 | **preview:** for **accepted** turns, the preview's terms equal the resolver's ledger row for row. For **refused** turns, the preview's terms equal the engine's prices, `affordable` is false, and **no ledger comparison is made** (§2) |
| T6 | reconciliation group 61: a positive case, plus one negative control per field (category, amount, target, digest, present when moved, absent when not) |
| T7 | **calibration, legality and arithmetic together** (§3.4), for every row of §3.2, plus the decree-route refusals behind "route unavailable" |
| T8 | the enum is sorted by value, and ledger order is canonical with the new row present |
| T9 | **contract:** the two new fields exist, and the regenerated `schema.d.ts` is committed and itemised |
| T10 | **frontend unit:** the map sentence, the panel row, the draft-list line and the ledger label, as exact strings. The panel row is hidden at zero |
| T11 | **browser** (`@mc1`): stage, see the price, preview, resolve, see the ledger row. Valdrun's decree + move + appointment previews as unaffordable, with every term shown |
| T12 | **determinism:** the new fixture replays byte-identically, and two identical runs give identical saves |

**Reconciliation group 61** is the flat-cost check group 60 makes for `PROMISE_RELEASE`:
- a movement decision with k ≥ 1 orders ⇔ exactly one `MILITARY_REDEPLOYMENT` row, charging
  `k × MOVEMENT_ORDER_CAPITAL_COST`, untargeted, with that decision's digest;
- no movement ⇔ no such row.

Group 54 is unchanged. The untargeted-category validators at `report.py:2608–2615` and `3008–3010`
gain the new member.

**Mutation checks:**
- charging 0, which fails T1, T5 and group 61;
- pricing before legality, which fails T4;
- a mis-ordered enum member, which fails T8;
- a preview price that is not the engine constant, which fails T5 and T7;
- a refusal that writes state, which fails T3.

## 6. Proposed commits — NOT AUTHORIZED; for the record only

1. **MC-1: engine, contract and surfaces together.**
   - **Engine and contract:** the category, constant, digest, slot-1 sink, report validators,
     group 61, the ruleset bump, the fixture, the preview term, the two projection fields and
     `generate:api`.
   - **Frontend:** the panel, map sentence, draft line and copy.
   - **Tests:** T1–T12.

   Done as one commit for ADR 0018's reason: a state where the engine charges but the interface
   cannot say so is a defect.
2. **MC-2: records.** ADR `0021-military-movement-cost.md`, the roadmap, every browser gate under fresh
   names, and the release verification and enforced dry run of the resulting archive. **It does not
   replace the approved playtest build** without a ruling.

**Verification checklist, restored from Revision 1 §6 and made explicit.**

**How each gate is recorded:**
- Each gate is run as **its own command**.
- Its **real exit status is captured as that command's own `$?`**, for example
  `pytest -q; PYTEST_EXIT=$?`. It is never a pipeline's status, and never inferred from output.
- Every gate's status goes in the commit's record, in a gates table, with its result line.
- **No staging or committing while any gate is running or failing.**

| # | gate | command | required result |
|---|---|---|---|
| G1 | backend lint | `ruff check .`, `ruff format --check .` | exit 0, exit 0 |
| G2 | backend types | `mypy` (the project's configured packages) | exit 0 |
| G3 | the new and extended tests | `pytest` on the T1–T8 and T12 files | exit 0, with the count stated |
| G4 | **backend full suite** | `pytest -q` | exit 0. The count is the previous suite plus the new tests, itemised |
| G5 | mutation checks (§5) | each mutation applied, the named tests run, then restored and checked with `cmp` | each named test fails under its mutation, and the file is byte-identical afterwards |
| G6 | frontend unit | `npm test` | exit 0, with the count delta itemised |
| G7 | frontend static | `npm run typecheck`, `build`, `check:bundle`, `check:palette`, `check:copy`, `check:css-sources` | exit 0 each |
| G8 | **contract** | `npm run generate:api` | exit 0. The contract **changes** (the two new fields). The regenerated files are committed, and the diff is itemised to exactly those fields |
| G9 | browser | every browser gate (`verify:ux` with the new `@mc1` block, `verify:fixes`, `verify:icons`, `verify:terminal`, `verify:campaigns`, `audit:stress:seated`, `audit:accessibility:verify`), each under **fresh** script and artifact names | exit 0 each. Every artifact is compared with the previous gate's, and each difference is itemised |
| G10 | fixtures | `git diff --stat` on `backend/tests/fixtures` | the existing 22 fixtures are unchanged, and only the new `0.24.0` fixture is added |
| G11 | **release (MC-2)** | `build_release.py --check-reproducible`, a fresh-clone rebuild, `verify_release.py` **once** under fresh names, then the enforced dry run | exit 0 each. `verify_release` is not retried; a breach is recorded and reported |
| G12 | after the push | local == remote, a clean tree, and every earlier artifact byte-identical | holds |

**Stop and report on:**
- any gate with a non-zero exit;
- any existing fixture changing bytes;
- a preview and resolver disagreement on an accepted turn;
- a refused turn that writes anything;
- a §3.2 combination that is not legal or does not give its stated outcome;
- any effect of formation location outside slot 8.

## 7. Explicit exclusions

**Not changed by this slice:**
- one order a turn, one edge, one branch;
- no transit, combat, casualties, supply, readiness, morale or foreign entry;
- no effect of location on any mechanic, and **no benefit from moving**;
- no treasury charge and no `defense` spending link;
- no change to regeneration or capacity;
- no scenario file change;
- no price that varies by route, distance or formation.

## 8. Revision history

**Revision 1 (`622ab8b`)** was the draft for approval.

**Revision 2** (`afc7a2d`) applied the review of Revision 1:
1. **Legal calibration examples.**
   - `deficit_demo` and `tiny_valid` have `emergency_only` decree authority, so their decree cells
     are marked **route unavailable**.
   - The `deficit_demo` example is replaced by a legal conflict: move, bargain and appointment.
   - Every example was read from the engine's decision options, and T7 verifies legality as well as
     arithmetic.
   - Also corrected: the cheapest appointment actually on offer is **147**, not the formula floor of
     120. Revision 1's "decree + move + 120 = 520", and its argument that a price of 120 loses the
     Valdrun conflict, were both wrong. The valid window for every listed conflict is 120–153.
2. **Preview and resolution are separated.** An overbudget preview shows every cost with
   `affordable = false`. Resolution rejects it with no change to state, history or save, and **no
   completed ledger exists to compare** for a rejected turn (§2, T3, T5).
3. **Regeneration is qualified.** It is computed from closing legitimacy. 380 a turn and the 20-a-turn
   drain are illustrations assuming legitimacy stays at 60%, not guaranteed outcomes (§3.3).

**Also added:**
- the design caveat: this prices existing infrastructure and is not proven balance, since movement
  still has no mechanical benefit (§0);
- the price is marked **provisional**;
- the status is marked **deferred, not authorized**;
- the loss of `0.23.0` save compatibility is made prominent.

**Revision 2a** (this one) records the user's acceptance of Revision 2 as **deferred planning only**.
- It restores Revision 1 §6's gate list, which Revision 2 had dropped, as the explicit verification
  checklist G1–G12, with the real-`$?` recording rule.
- 150 stays provisional.
- Implementation still requires the playtest report **and** the user's separate authorization.
