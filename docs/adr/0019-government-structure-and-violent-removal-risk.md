# ADR 0019: Government structure and violent-removal risk

**Status:** accepted. Ruleset `0.16.0 -> 0.17.0`.
**Supersedes, in part:** ADR 0013's claim that no violent-removal channel reads a constitutional
axis. It does not supersede ADR 0009's legitimacy neutrality, which stands unchanged.

## The gap

A player governs a country, may change how it is governed, and tries to stay in power. Phase 3C
gave them four ways to lose power: an election, an impeachment, a coup, and a popular uprising. Two
of those already knew what kind of government they were removing — an election happens only because
`national_election_interval_turns` schedules one, and impeachment is gated on
`legislature`/`judicial_review`/`executive_selection` and scaled by how strong the courts are.

The two *violent* channels knew nothing. Their formulas read loyalty, power, competence, legitimacy,
opposition seat share, transition pressure, radicalization, organization and disapproval — and not
one constitutional axis. A hereditary monarch ruling by unlimited decree and an accountable
electoral republic, given identical armies and identical public mood, faced identical odds of a
coup and identical odds of an uprising.

That is a real modelling claim, and it is the wrong one. An electoral government under strain has a
scheduled, lawful way for its opponents to remove it. A government with no such route is where a
coup or an uprising becomes the substitute. The channel that should differ most by government form
was the only one that did not differ at all.

ADR 0013 stated the old behaviour plainly (`docs/adr/0013-government-survival.md`):

> None of the three channels reads a constitutional axis directly; every input is loyalty, power,
> competence, corruption, radicalization, approval, organization, or legitimacy — the same
> government-form-neutrality guarantee every prior political formula in this codebase carries.

The first clause of that sentence is what this ADR supersedes, for the coup and popular-unrest
channels only. The reference to a codebase-wide neutrality guarantee was always an overstatement of
what that guarantee covers — see "What is NOT superseded" below.

## Decision

One shared pure function, `structural_removal_exposure_bps`
(`backend/app/simulation/government_survival.py`), scores how much a constitution's SHAPE exposes
its executive to violent removal, in basis points. Its result feeds a new named contribution on
both violent channels' attempt risk, and nothing else.

It answers two orthogonal questions from axes that already exist:

**Can voters remove this executive?**

| Condition | bps |
|---|---|
| `executive_selection` is `HEREDITARY` or `APPOINTED` | 4,000 |
| elected selection, but `national_election_interval_turns` is `None` | 2,000 |
| elected selection with a scheduled election | 0 |

**Is the executive constrained by other organs?**

| Condition | bps |
|---|---|
| `decree_authority` `UNLIMITED` / `EMERGENCY_ONLY` / `NONE` | 3,000 / 500 / 0 |
| `legislature` is `NONE` | 2,000 |
| `judicial_review` `NONE` / `WEAK` / `STRONG` | 1,000 / 500 / 0 |

The components sum to exactly 10,000 at the unrestricted-personal-rule endpoint, so the clamp is
defensive and never engages — the same property `coup_success_probability_bps`'s 3,500-of-7,000
headroom has, and pinned by a test for the same reason.

Each channel scales the exposure by its own weight, with one truncating division, and the result
joins the existing sum **before** the existing clamp:

```
coup_structural_contribution_bps   = trunc(exposure_bps * COUP_STRUCTURAL_WEIGHT_BPS   / 10_000)   # weight 400
unrest_structural_contribution_bps = trunc(exposure_bps * UNREST_STRUCTURAL_WEIGHT_BPS / 10_000)   # weight 300
```

The weights and component values are **game-balance choices**. They are not measurements of real
countries, they were not supplied by anyone, and they are meant to be re-tuned from calibration.

### Measured effect on the shipped scenarios

| scenario | exposure | coup risk (was) | unrest risk (was) |
|---|---|---|---|
| `tiny_valid` — parliamentary, elected, strong courts, emergency decree | 500 | 58 (38) | 30 (15) |
| `deficit_demo` — presidential, elected, weak courts, emergency decree | 1,000 | 88 (48) | 45 (15) |
| `decree_state` — hereditary monarch, unlimited decree, weak courts | 7,500 | 352 (52) | 240 (15) |

`decree_state`'s military is authored identically to `tiny_valid`'s. The six-fold gap in coup risk
is its constitution and nothing else.

Over twenty 100-turn campaigns per scenario (seeds 0–19, wars disabled to isolate the effect):

| scenario | turns at risk | coup attempts | coup removals | unrest attempts | unrest removals | how campaigns ended |
|---|---|---|---|---|---|---|
| `tiny_valid` | 512 | 5 | 0 | 5 | 0 | 12 term-limit exits, 8 electoral defeats |
| `deficit_demo` | 560 | 7 | 0 | 5 | 0 | 20 electoral defeats |
| `decree_state` | 1,812 | 70 | **3** | 40 | 0 | 3 coups (turns 9, 23, 80); 17 survived the horizon |

Both halves are the point. A dictatorship is genuinely in danger — and seventeen of twenty
campaigns still survive a century. The electoral scenarios are heavily right-censored: they end at
their own scheduled elections, which is why they accumulate a third of the turns at risk. Comparing
raw counts across rows without that context would overstate the gap.

## Two exceptions, pinned

**At a saturated cap the risk does not move.** Structure is added before the clamp, so conditions
already bad enough to max out the risk leave nothing for structure to add. The guarantee is
"greater or equal, never lower", with "strictly greater" holding only below the cap.

**Where conditional success is zero, more attempts produce no removals.** This feature does not
touch `coup_success_probability_bps` or `unrest_success_probability_bps`. All three shipped
scenarios have an unrest success probability of exactly 0 at genesis, and the 100-turn sweep
confirms it end to end: `decree_state` made 40 popular-uprising attempts and lost power to none of
them. Structure raises how often something is tried; it cannot manufacture an outcome the
conditional formula rules out.

## Why not `is_noncompetitive_constitution`

That helper already exists and already classifies constitutions — and it was deliberately not
reused. It answers Phase 3C's *victory* question, and it counts any non-`NONE` decree authority as
noncompetitive. Under it, `tiny_valid` and `deficit_demo` are both noncompetitive, purely because
they author `emergency_only`. Both are elected governments on an election schedule.

Emergency powers held by an accountable government are not a dictatorship. Here they are worth 500
of a possible 10,000 — an eighth of what being unelected costs, a twentieth of full personal rule,
and 2 bps of coup risk once scaled. The two functions are pinned against each other in
`test_structural_exposure.py` so that a future edit to either has to notice the other exists.

The same scale distinguishes a **constrained monarchy** (hereditary, but sitting with a chamber
under strong courts and unable to legislate alone — 4,000) from **unrestricted personal rule**
(10,000). Being unelected is not the same as being unchecked.

## What is NOT superseded

- **Legitimacy stays government-form neutral.** No function in `simulation/legitimacy.py` accepts a
  constitutional type, and that is enforced structurally by an `inspect`-based scan, not by
  convention. A dictatorship earns no automatic legitimacy penalty. It is not less *accepted* for
  being a dictatorship; it is more exposed to one particular way of being removed.
- **Political-capital generation, public acceptance, and economic production stay neutral.**
  `test_legitimacy_neutrality.py`, `test_legislative_neutrality.py` and `test_phase_isolation.py`
  required no change for this feature. That they still pass unmodified is itself the evidence that
  the term did not leak.
- **Conditional success formulas are untouched**, on every channel.
- **Impeachment is untouched.** It already had its own constitutional dependency; adding a second
  would have double-counted the same courts.
- **Victory conditions are untouched.** The mismatch between survival-oriented play and automatic
  peaceful-liberalization victory is real and is left for a separate objectives mandate.

## Integration and timing

Slot 12 computes the exposure once, from `politics.constitution` — the same object it already reads
for impeachment eligibility, which is the **closing** constitution, after slot 2 commits any
enacted amendment. A government that liberalized this turn is scored on what it became; a failed
amendment commits nothing and is scored on the unchanged opening shape.

Exposure and `regime_transition_pressure_bps` are separate terms and cannot double-count: pressure
is a decaying memory of having recently changed the constitution, exposure is what the constitution
now is. A government that amended nothing carries zero pressure and whatever exposure its shape
implies.

RNG stream names and order, the conditional-draw policy, phase order, terminal-outcome priority and
atomic resolution are all unchanged. Raising an attempt probability does legitimately change *which*
success draws occur in a given campaign — the policy is preserved, not the draw count.

## Explainability

Both channel reports publish `structural_exposure_bps` (a raw input) and
`structural_contribution_bps` (a named contribution), so the contribution is re-derivable from the
row alone. Reconciliation groups 24 and 27 recompute the exposure from the closing state's
constitution and compare it to both rows — which is what rejects a forged structural figure whose
own arithmetic and entry hash are self-consistent. The `coup_risk_assessed` reason carries the
figures to every surface, and the dashboard survival card says how much of the risk is the
government's shape rather than its conditions. Nothing was added to the strategic-map projection,
which is generation-keyed and cached indefinitely.

## Compatibility

`RULESET_VERSION` `0.16.0 -> 0.17.0`. No state shape changes — not one field is added to
`GameState` — which makes this the first bump justified purely by turn-resolution behaviour rather
than by a new required field. `SAVE_FORMAT_VERSION` stays `1`. `content_version` stays `0.16.0`: no
scenario-authored field changes shape, and the weights are engine constants, not content.

A 0.16.0 save is rejected, never reinterpreted. Its turns were resolved under rules where form did
not matter; continuing it here would silently apply the new rules to a campaign that never faced
them, and re-deriving its history under them would contradict its own stored hashes.
`government_structure_save_ruleset_0.16.0.json` was frozen from the unmodified engine before the
bump, because that save became impossible to produce afterwards.
