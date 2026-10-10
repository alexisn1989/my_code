# Gate 4A3 victory path, V-1: the campaign objective on the backend

**Plan:** Victory path, Revision 2a, as you approved it. This is commit V-1 of three.
- **V-2** adds the frontend: the card, the Constitution screen, the links, the preview sentence, the
  result line, D-V1, and the `victory` browser project.
- **V-3** records the candidate release.

**What V-1 changes:**
- `app/api/` only;
- the regenerated contract;
- one frontend grouping entry, without which the new catalogue card would crash Decisions (§4).

**No engine, ruleset, scenario or save-format change.** `app/simulation/**`, `data/` and the 22
fixtures are untouched.

## 1. What was built

**`app/api/objective.py` (new)** derives the campaign objective from engine state. It classifies
**only** with the engine's two predicates, `is_noncompetitive_constitution` and
`is_competitive_elected_constitution`.

- **`constitution_class`:** `noncompetitive`, `competitive` or `neither`. A test proves the three
  classes partition every coherent constitution, and that `neither` is reachable.
- **`condition_met`:** each of the three conditions is asked of the competitive-elected predicate
  itself, with the other two axes held at values it accepts. No enum set is restated.
- **`build_objective`:** the stage, decided in this order:
  1. a terminal outcome gives `concluded`;
  2. the marker gives `qualifying_election`;
  3. otherwise the class gives `reform`, or `cannot_qualify` (`missing_interval` /
     `already_competitive`).

  The two facts are reported separately: "Constitutional conditions: K of 3 met" and "Qualifying
  transition: recorded on turn T / not recorded".
- **Links:**
  - each unmet condition names the existing catalogue card that meets it alone, with
    `if_enacted_alone`;
  - a link whose result would be `cannot_qualify` is **withheld**, with its reason;
  - `qualifying_card_id` names the one amendment completing every unmet condition: the existing card
    when one condition is unmet, otherwise `constitution_qualifying_reform`.
- **`amendment_effect_if_enacted` / `preview_effect`:** the drafted amendment's effect **if enacted**.
  It never says whether it will be enacted.
- **`objective_line`:** the result line, from the stored report, the closing state and the
  **opening** marker. The precedence is:
  1. a terminal outcome;
  2. qualifies;
  3. keeps the transition;
  4. ends the transition;
  5. reform continues;
  6. cannot qualify;
  7. failed;
  8. election won without a transition;
  9. otherwise none.

**The three contract fields, exactly as planned:**
- `DashboardProjection.objective`;
- `TurnResultProjection.objective_line`;
- `PreviewProjection.objective_effect_if_enacted`.

`build_turn_result` gains a keyword `opening_state`.
- **Live resolve** passes the save's previous entry, and **History** passes `entry_at(turn - 1)`, so
  the two are identical (tested through the API).
- **Without an opening state,** the line is omitted rather than guessed.

**The catalogue card:** `constitution_qualifying_reform` is built with the existing `_amendment_card`
machinery.
- It exists only in Valdrun, where all three conditions are unmet.
- Its legislative template is decree `none`, direct election, presidential, interval 4. That is
  **exactly the audit's winning amendment**, and the engine's own slot 2 qualifies it (tested).

**D-V2 to D-V4:**
- **D-V2:** ledger targets name the bloc, for example "Hardliners", not `citizens_bloc/hardliners`.
- **D-V3:** an amendment turn with no budget says "No budget was proposed."
- **D-V4:** `COMPANION_CHANGE_TEXT` gives an authored companion sentence for every C1–C10 code. The
  Valdrun three-axis refusal now says: "…a monarch can't be directly elected or selected by the
  legislature. Change Executive system too (for example, to presidential for a directly elected
  executive), or keep a hereditary or appointed executive." The status and codes are unchanged.

**Refactor, behaviour unchanged:** the constitution label tables moved from `policy_cards.py` to
`app/api/constitution_labels.py`, so `objective.py` can use them without an import cycle.
`policy_cards.py` keeps its old names as aliases.

## 2. Two engine facts found while testing (the plan's text is corrected, not the engine)

1. **The marker and the election schedule use the turn a resolution PRODUCES** (opening turn + 1).
   - Slot 2 runs on the working state, whose turn is already incremented.
   - So a reform resolved from turn 0 records `set_at_turn = 1`, and an interval-4 target schedules
     the election for turn 5. The existing `test_constitutional_amendment_gating.py` already pins
     this (opening turn 2 records marker 3).
   - `preview_effect` computes the deciding election from `state.turn + 1`. A "same-turn" election
     is one scheduled for that produced turn.
   - All user-facing turn numbers are therefore in the same numbering as the existing "An election
     is scheduled for turn N." alert.
2. **`resolve_turn` refuses an unaffordable set with `TurnResolutionError`,** which wraps the engine's
   `DecisionSetError`. The plan named the latter. The test asserts the former, plus the message
   "exceeds opening political capital 500", and that the state is unchanged.

## 3. Tests (`backend/tests/test_campaign_objective.py`, 64 tests)

- **The partition and the conditions,** over every coherent constitution in the product of
  executive system × selection × decree × interval (none or 4) × legislature × term limit
  (none or 2).
- **A source drift guard:** no executive-selection or decree member is named in `objective.py`. This
  is secondary to the behavioural tests.
- **Openings:** all three scenarios are in `reform`, with 2, 2 and 0 conditions met. Every offered
  link names an available catalogue card, and 4 is the shortest catalogue preset.
- **§1 engine resolutions** (real `resolve_turn`, with the legislature made supportive):
  - the unsafe order (form, decree, interval) leaves **no marker**, giving `cannot_qualify`
    (`missing_interval`, then `already_competitive`);
  - the safe order (interval, form, decree) records it;
  - the four-axis reform records it;
  - the stated way back (restore emergency decree, then reform) records it;
  - removing the interval clears it;
  - changing the interval keeps it and reschedules;
  - a qualifying reform on an election turn: that election is won but not victory, and the next
    one decides;
  - **any lost election is defeat,** with or without a marker, and defeat clears the marker;
  - winning the qualifying election is victory and consumes the marker;
  - a term-limit exit concludes even though the engine **keeps** the marker.
- **Links from the state they would be clicked in:** after decree `none` alone, the
  elected-executive link is withheld ("Not on its own: …"). The engine confirms that enacting it
  alone strands the constitution.
- **Parity, in three layers:**
  - **Layer 1:** ten cases. `objective_effect_if_enacted` equals the engine's slot-2 outcome with
    enactment forced.
  - **Layer 2:** the same ten on the real amendment phase. When enacted, `qualifies` and the slot-2
    marker equal the prediction.
    - **The failed vote:** a Valdrun four-axis reform with no influence predicts `qualifies` with
      `would_pass` false. Resolution records nothing, and the result line says the amendment
      failed.
    - **The unaffordable draft:** the preview has `affordable` false and predicts `qualifies`.
      Resolution refuses it, and the state is unchanged.
  - **Layer 3:** the closing stage and result line, never compared with a preview.
- **The result lines:** every row against a real resolved turn, with exact strings.
- **History equals live through the API** (`deficit_demo`'s audited reform), plus D-V2 and D-V3 on
  that turn.
- **D-V4:** all ten reachable C-codes have a sentence, and the exact Valdrun refusal is pinned.
- **One itemised change to an existing test:** `test_policy_cards.py`'s `_KNOWN_CARD_COUNTS` for
  `decree_state` goes from (44, 31) to (45, 32). That is the qualifying card.

## 4. The frontend accommodation in V-1

`groupPolicyCards.ts` **throws** on an unrecognised constitutional card id, by design. Without an entry
for `constitution_qualifying_reform`, Valdrun's Decisions screen would fail as soon as the backend
served the card.
- So V-1 adds the `qualifying_reform` family, labelled "Qualifying reform" and listed first under
  Constitutional reform, plus one unit test.
- That is the only `src/` change in V-1.

## 5. Contract (`generate:api`, exit 0): additions only

| | before | after |
|---|---:|---:|
| paths | 13 | 13 |
| component schemas | 62 | 65 (`ObjectiveCondition`, `ObjectiveEffectProjection`, `ObjectiveProjection`) |
| `DashboardProjection` | | `+objective` (required) |
| `TurnResultProjection` | | `+objective_line` |
| `PreviewProjection` | | `+objective_effect_if_enacted` |
| ruleset / version | `0.23.0` | `0.23.0` |

The files changed are `docs/contracts/phase4a-openapi.json` (+282 lines) and
`frontend/src/api/schema.d.ts` (+87 lines). There are no deletions.

## 6. Gates (each its own command; its own `$?`)

| gate | exit | result |
|---|---:|---|
| backend `ruff check app tests` | 0 | |
| backend `ruff format --check app tests` | 0 | |
| backend `mypy` (project config) | 0 | 59 source files |
| backend full suite | 0 | **36,524 passed** (36,460 + 64), 17 min 28 s |
| `npm run generate:api` | 0 | the contract as in §5 |
| `npm test` | 0 | 41 files, **614** passed (613 + 1 grouping test) |
| `typecheck` | 0 | |
| `build` | 0 | |
| `check:bundle`, `check:palette`, `check:copy`, `check:css-sources` | 0 each | |
| `verify:ux:v1` | 0 | 26 passed |
| `verify:fixes:v1` | 0 | 13 passed |
| `verify:icons:v1` | 0 | 7 passed |
| `verify:terminal:v1` | 0 | 6 passed |
| `verify:campaigns:v1` | 0 | 7 passed |
| `audit:stress:seated:v1` | 0 | 6 passed |
| `audit:accessibility:verify:v1` | 0 | 6 passed |

**The browser artifacts compared with UX-4g's, structurally:**
- **Identical:** `verification`, `icon-coverage`, `terminal`, `stress-seated-cabinet`, and both of its
  screenshots (byte-identical), and the accessibility JSON.
- **`verify-ux`:** only its own `out` name differs.
- **`campaigns`:** only the bundle filename in `distinctPaths` differs (`index-BumrhHF5.js` →
  `index-C6SLmtm5.js`), from the grouping change.

**The `victory` browser project is not a V-1 gate.** V-2 introduces it.

**Mutation checks:** each was applied to `objective.py`, run, then restored and checked with `cmp`.

| mutation | failed tests |
|---|---|
| stage ignores the marker | 5, including `…four_axis_reform_records_the_marker` and `…identical_live_and_from_history` |
| `neither` folded into `reform` | 5, including `test_unsafe_order_leaves_no_marker_and_the_cannot_qualify_stage` |
| marker clearing narrowed to non-competitive only | layer 1 and layer 2, case 8 ("marker: remove interval") |
| a stranding link offered | `test_a_link_that_would_strand_the_constitution_is_withheld_with_its_reason` |
| `objective_line` reads the closing marker as the opening one | 3 `test_line_*` |
| qualifying interval 4 → 8 | `test_qualifying_interval_is_a_catalog_preset`, and 2 more |

The two frontend mutations, a link merging rather than replacing and a preview sentence without "If
enacted", belong to V-2.
