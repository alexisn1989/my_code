# Gate 4A3 W-2: what investments and cabinet posts do (playtest feedback)

**Scope:** explanations only. Nothing changes what an investment or a cabinet post does.
- each drafted investment's own gain, shown in the preview;
- one guidance sentence on the investment panel;
- an investment that would change nothing, flagged before resolving;
- each cabinet post's one real effect, and each candidate's effect at their competence.

Left separate, and not touched: the pacing diagnosis (W-3), the chamber and negotiation ideas,
movement cost and caching. **No engine, ruleset, scenario or save-format change**:
`git diff -- backend/app/simulation backend/data backend/tests/fixtures` is empty.

## 1. What changed

1. **The preview reports each investment's own gain** (`app/api/preview.py`, `_investment_effects`).
   - It is computed with the inputs resolution uses in slot 1: the bloc's opening relationship, the
     capital, and the opening cabinet's chief of staff, read through the engine's
     `holder_competence_bps` and gain function `relationship_gain_bps`.
   - A chief of staff appointed **in the same draft contributes nothing**, which is what resolution
     does too, because an appointment counts from the next turn.
   - Each row carries the gain, the chief of staff's share of it, and `no_effect` when the gain is 0.
     Resolution refuses such an investment ("would have no effect"), so the preview now says so first.
2. **The preview panel words each row** (`ConsequencesPanel`, `format.ts` `investmentEffectSentence`),
   under "Relationship investments (their own effect only):". For example:
   - "National Front Conservatives: +16.68 points from 50 capital, including +1.23 points from your
     chief of staff (relationship -70.00% before this turn).";
   - "Crown Party Core: 50 capital would change nothing here (relationship 100.00%), so resolving
     would refuse this investment."
3. **The investment panel explains what investments are for** (`DecisionsScreen`), in engine facts
   only: relationships shape how blocs vote on budgets and amendments; Lower-chamber relationships
   make up half of election support; relationships drift back toward each bloc's usual stance; the
   same capital adds less near the ceiling; and a no-effect investment is refused.
4. **Each cabinet post states its one real effect** (`app/api/projections.py`, `POST_EFFECT_TEXT`,
   shown on Government under "Candidates for …"):
   - chief of staff: "Makes relationship investments more effective: a fully competent chief of staff
     adds up to 25.00% to each investment's gain. A new appointee starts to count from the next turn.";
   - foreign minister: "Improves the terms of foreign assistance: a fully competent foreign minister
     adds up to 6.00 percentage points to the share of its remaining pool a counterpart grants. A new
     appointee starts to count from the next turn."

   The maxima are the engine's constants, formatted, never retyped. The table is indexed rather than
   read with a default, so a new post fails a test rather than reaching a player unexplained.
5. **Each candidate's effect scales with their competence** (`candidate_effect_text`), computed by the
   engine's own functions:
   - chief of staff: "With competence 86.00%: investments would gain about 21.50% more.";
   - foreign minister: "With competence 86.00%: a counterpart would grant **up to** 5.16 percentage
     points more of its remaining pool."

     It says "up to" because the engine floors a counterpart's share at 1 bps. Where the other
     terms would take the share below that floor, the minister's addition is smaller.

## 2. Contract change, itemised

`generate:api` exited 0. The schemas went from 65 to 66 and the paths stayed at 13.
`docs/contracts/phase4a-openapi.json` and `frontend/src/api/schema.d.ts` gained:

| change | kind |
|---|---|
| `InvestmentEffectPreview` (new schema): `party_id`, `bloc_id`, `bloc_display_name`, `political_capital`, `opening_relationship_bps`, `gain_bps`, `chief_of_staff_bonus_bps`, `no_effect` | new |
| `PreviewProjection.investment_effects`: an array of `InvestmentEffectPreview`, default `[]` | new field, optional |
| `CabinetPostOption.post_effect_text`: string | new field, required |
| `CabinetCandidateOption.effect_text`: string | new field, required |

The only removed line in the OpenAPI diff is `"candidates"`, which gained a trailing comma. Nothing
was renamed or removed. A newer client against an older server would miss the two required strings,
but they ship together in one archive.

**The pinned fixtures were regenerated** (`MANDATE_REGENERATE_OBJECTIVE_FIXTURES=1`). The diff only
adds lines:
- `decision-options-valdrun.json`: the two new text fields on every post and candidate; the two `-`
  lines gained a comma;
- `objective-results.json`: `"investment_effects": []` on the two existing previews, plus the new
  `previewInvestments` (`tiny_valid`, 50 capital on each of 5 blocs, with a serving chief of staff)
  and `previewInvestmentNoEffect` (every bloc at the 100% ceiling);
- `objective-stages.json` and the e2e fixtures are unchanged.

## 3. Tests

- **Backend, `tests/test_effect_explanations.py` (12).** Checked against the engine, never against
  the explanation's own arithmetic:
  - **the preview's gain equals the resolved `investment_component_bps`** for every bloc in
    `tiny_valid` (with a serving chief of staff, whose bonus is > 0), `decree_state` and
    `deficit_demo`;
  - a chief of staff appointed in the same draft gives a bonus of 0, and the gains still equal
    resolution;
  - every bloc at the ceiling: every row has `no_effect`, and resolution raises
    `TurnResolutionError` "would have no effect";
  - `POST_EFFECT_TEXT` covers every `CabinetPost`, and quotes the engine maxima;
  - **candidate effects are the engine functions,** at competence 0, 3,200, 8,600 and 10,000:
    - chief of staff: equal to `chief_of_staff_gain_bonus_bps` on a 10,000 base, and to a real
      gain's growth within truncation;
    - foreign minister: `0 <= with − without <= stated` over three term sets, and equal wherever
      the 1-bps floor does not clip. **The sentence must say "up to"**;
  - the decision options carry exactly these texts;
  - **a future-start appointment is rejected by the engine.** It is added at your review, and backs
    mutation M3. On the real `tiny_valid` state, the opening chief of staff is moved to
    `effective_from_turn = state.turn + 1`, and `check_invariants` must return exactly
    `["cabinet_appointment_not_yet_effective"]`.
- **Fixtures (`test_objective_fixtures.py`):** the two new previews, pinned and regenerated.
- **Unit (`greybox/w2.test.tsx`, 5):**
  - the exact sentences for real preview rows, including the chief-of-staff share;
  - the no-effect sentence and `data-no-effect`;
  - no list when nothing is invested;
  - the guidance on Decisions;
  - every post's and willing candidate's text on Government, taken from the server's options.
- **Browser (`@w2` in `verify-ux.spec.ts`, 3 viewports):**
  - on Valdrun, the guidance is visible;
  - 100 capital on Reform Opposition Main, then Preview: the API's row is not `no_effect`, and the
    page's row names the bloc, the gain and "from 100 capital";
  - on Government, each post's `post-effect` and each willing candidate's effect equal the options
    texts;
  - axe finds 0 violations on the new elements, and there is no page overflow.

## 4. Gates (final runs; each its own command and its own `$?`)

| gate | exit | result |
|---|---:|---|
| `npm test` | 0 | 45 files, **665** passed (660 + 5 in `w2.test.tsx`) |
| `typecheck`, `build`, `check:bundle`, `check:palette`, `check:copy`, `check:css-sources` | 0 each | |
| `generate:api` | 0 | identical to the regenerated contract itemised in §2 |
| backend `ruff check` / `ruff format --check` / `mypy` (final tree) | 0 / 0 / 0 | |
| backend full suite (final tree) | 0 | **36,547 passed** (+12: `test_effect_explanations.py`), 29 min 51 s |
| `verify:victory:w2` | 0 | 10 passed |
| **`verify:ux:w2`** | 0 | **29 passed** (26 + the 3 `@w2` viewports) |
| `verify:fixes:w2` | 0 | 13 passed |
| `verify:icons:w2` | 0 | 7 passed |
| `verify:terminal:w2` | 0 | 6 passed |
| `verify:campaigns:w2` | 0 | 7 passed |
| `audit:stress:seated:w2` | 0 | 6 passed |
| `audit:accessibility:verify:w2` | 0 | 6 passed |

**The artifacts compared with W-1's:**
- **identical:** `victory`, `icon-coverage`, `terminal`, `stress-seated` (the JSON and both
  screenshots), and the accessibility JSON;
- **`verification`:** one more painted-text element on a `navy-900` backdrop (210 → 211; Decisions'
  candidates 151 → 152, measured 75 → 76). That is the new guidance paragraph. The worst ratio is
  unchanged at 5.45:1, and none is below 4.5;
- **`campaigns`:** only the bundle filename;
- **`verify-ux`:** the output name, plus the `w2` result rows.

## 5. Mutation checks (final code; each restored and checked with `cmp`, the whole diff equal before and after)

| mutation | result |
|---|---|
| M1: the preview ignores the chief of staff | pytest exit 1: `test_preview_gain_equals_the_resolved_investment_component[tiny_valid-50]` and the fixture test |
| M2: `no_effect` always false | pytest exit 1: `…flagged_and_refused` and the fixture test |
| M3: the opening chief read as effective one turn later | **survived (pytest exit 0): an equivalent mutant.** No valid state holds an appointment with `effective_from_turn > state.turn`, so `state.turn` and `state.turn + 1` select the same holder on every valid state. **That rejection is now proved by a test** (`test_a_future_start_appointment_is_rejected_by_the_engine`), and M8 shows the test detects its absence. The same-draft property is pinned by the same-draft test, because the preview reads only the opening cabinet |
| M4: the foreign-minister text claims an exact amount | pytest exit 1: four `test_candidate_effects_are_the_engine_functions` cases, and the options fixture test |
| M5: the chief-of-staff clause dropped | vitest exit 1: "words each real preview row…" |
| M6: the guidance removed | vitest exit 1: "explains what investments are for…"; `@w2` desktop exit 1 |
| M7: the effects list not rendered | vitest exit 1: both preview-row tests; `@w2` desktop exit 1 |
| M8: the engine's `cabinet_appointment_not_yet_effective` check disabled (`app/simulation/invariants.py`, restored; `app/simulation` has no diff afterwards) | pytest exit 1: `test_a_future_start_appointment_is_rejected_by_the_engine` |

M3's first attempt did not apply: the replacement target was not unique. It was re-run with a unique
anchor; that attempt is the one recorded above.

## 6. Superseded attempts, recorded and not omitted

- **The first final backend run predates the rejection test.** That run gave 36,546 passed, with
  ruff, ruff format and mypy at exit 0, in 31 min 46 s. It is superseded by the final-tree run in
  §4.
  - That test is the only change since: one new test in `test_effect_explanations.py`, with no
    source change. The tracked diff is byte-identical to the one the frontend and browser gates
    ran on.
  - So those gates' results in §4 stand for the final tree. They were not re-run.

- **The foreign-minister wording first claimed an exact addition.** The engine floors the share at
  1 bps, so the addition is an upper bound. The text says "up to", and a test pins it.
- **The guidance first said "the lower chamber".** That failed an existing raw-identifier test
  (`lower`). It now reads "relationships in the Lower chamber".
- **The decision-options fixture lacked the new fields** until it was regenerated. That diff is the
  new fields only.

**Committed on your instruction.** It was conditional on every final-tree gate passing, and they
all did.
- The playable archives are unchanged: the approved playtest build stays `083c7a98…`, and the
  candidate stays `8848c0e9…`.
- These explanations reach testers only through a separately approved rebuild and switch.
