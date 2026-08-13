# ADR 0012: Political memory, policy reactions and relationship decay

- Status: accepted
- Date: 2026-08-13

## Context

Phase 3B2A (ADR 0011) gave `government_relationship_bps` its first writer, but only in one
direction. `relationships.relationship_gain_bps` says so in its own docstring: it never returns a
negative value. A player who invests in a bloc and then stops keeps the improvement forever, for
free, and no bloc's opinion depends on anything the government actually *did* — only on what was
paid. Phase 3B2B closes that loop: blocs acquire memory. They decay back toward an authored
structural baseline when unmaintained, react to policy the government actually enacted, and resent
being bypassed by decree — a separate, procedural cost from the policy content itself.

## Decisions

### An authored baseline, distinct from the mutable current relationship

`LegislativeBlocState` gains `baseline_government_relationship_bps` (Option A of three considered
in the working plan: authored baseline + mutable current, rejected alternatives being an
accumulated-modifier split and universal decay toward zero — the latter would have erased authored
political history, drifting a structurally hostile faction to neutral for free). All three
scenarios author it equal to each bloc's opening `government_relationship_bps`, so turn 1 opens at
zero deviation and decay is a no-op until something moves the relationship away from it. The field
is authored, never derived from `government_role` or any constitutional axis — government-form
neutrality holds exactly as it does for every other political formula in this codebase.

### Three pure formulas, one combining identity — `simulation/political_memory.py`

```
decay      = relationship_decay_bps(opening, baseline)       # proportional 1/8, min-1 step, no overshoot
policy     = enacted_policy_reaction_bps(tax/spending prefs, tax/spending direction+intensity)
decree     = decree_bypass_reaction_bps(is_seated_bloc)       # -200 bps, procedural, decree-route only

uncapped_total = decay + investment + policy + decree
closing        = clamp_relationship_bps(opening + uncapped_total)
applied_total  = closing - opening
```

All four components are computed from the **same** opening relationship value and summed as plain
integers before a single clamp — the result is provably independent of the order the four are
evaluated in, and boundary truncation (`uncapped != applied`) is stored, never silently absorbed
into one component.

**Decay** is proportional (1/8 of the deviation) with a minimum one-bps step, so a residual that
truncation alone would freeze (e.g. `trunc(7/8) == 0`) still terminates in finitely many turns; the
half-life is short (~5.2 quarters) but the tail is long — a 10,000-bps deviation takes 65 turns to
reach exactly zero.

**The policy reaction** re-implements the same two-axis compatibility shape
`legislative_voting._axis_component_bps` uses for the vote, independently (the two-code-paths
discipline this codebase follows everywhere else) — never imported. It is derived from the
**proposal's own** stored direction/intensity and **the bloc's own** preferences, never from
`BlocVoteReport.policy_compatibility_bps`, because that field does not exist on the two outcomes
this phase cares about most (`ENACTED_BY_DECREE` and `NO_PROPOSAL` both set `bloc_reports = ()`).

**Critically, a budget target is absolute, not relative.** Resubmitting or holding an already-active
rate scores `ChangeDirection.UNCHANGED` and a provably zero reaction — a policy reaction is
therefore inherently a finite, per-genuine-change event, never a standing quantity a player can
lock in by repeating the same decision. An earlier draft of the working plan modeled an
indefinitely-repeated reaction; that scenario cannot occur under the real budget-target semantics
and the claim was withdrawn before implementation (see the plan's own R12 revision).

**The decree-bypass penalty** is uniform (200 bps, ≈ -2.00 percentage points of relationship) for
every seated bloc when the outcome is `ENACTED_BY_DECREE`, regardless of whether the decreed
content itself changed — the bypass is procedural. It is the one component that repeats
indefinitely on its own (a decree can be habitually chosen every turn), and in isolation converges
into an eight-wide band (`floor(|deviation|/8) == 200`) rather than a single point, because
`floor(x/8)` is constant across eight consecutive values of `x`.

### Report architecture: a ninth top-level report, not an extension of the eighth

`PoliticalCapitalReport.relationship_changes` (3B2A) is **removed**. Keeping it while a new report
also described relationships would have left `closing_relationship_bps` meaning "opening +
investment only" once decay could also move the same value the same turn — exactly the kind of
field that could only lie, the same defect ADR 0011 itself removed `spending_delta_bps` for. The
full per-bloc story — decay, investment, policy reaction, decree bypass, closing — moves to a new
top-level report, `PoliticalRelationshipReport`, with row model `BlocRelationshipMemoryReport`
(superseding `BlocRelationshipChangeReport`).

Both models are self-validating from their own stored fields — including the proposal's own
`tax_direction`/`tax_intensity_bps`/`spending_direction`/`spending_intensity_bps` and each row's own
`tax_preference_bps`/`spending_preference_bps` — so policy-reaction and decree-bypass arithmetic
never need to consult another report that might not exist that turn. `TurnReport` keeps exactly two
genuinely cross-report checks: the relocated investment/ledger correspondence (needs
`PoliticalCapitalReport`) and a new proposal-metadata-vs-`LegislativeReport` check (catches a report
that is internally self-consistent while lying about what was actually proposed). Everything else —
row coverage, preference correspondence against the bloc's *authored* value, and whether
`legislature_present` truthfully describes the opening state — is a reconciliation fact
(`simulation.reconciliation` groups 22-23), because a report cannot see `GameState` on its own.

Slot 11 (`_apply_bloc_relationship_investments`) is the sole writer of `government_relationship_bps`
and now follows a strict three-step procedure: compute all four components from the opening
legislature, construct and validate every `BlocRelationshipMemoryReport` row (Pydantic validation
runs here, on real data, before anything touches state), and only then write each row's own
validated `closing_relationship_bps` into state — never a raw formula result. Slot 15 wraps the
same validated rows into the top-level report without recomputing anything, so the report and the
resulting state provably came from identical values.

### Compatibility: ruleset 0.10.0 → 0.11.0, no fabricated migration

A new required state field, report schema growth (eight reports → nine, one field removed from an
existing report) and new turn semantics (slot 11 now writes on turns with no decisions at all)
together justify the bump. A 0.10.0 save has no authored baseline and none is defaulted — that
would assert every historical bloc sat exactly at its structural baseline at save time, a claim
about political history the save does not contain, in a format whose entire purpose is that it
cannot lie. A frozen genuine 0.10.0 fixture is rejected with `UnsupportedRulesetVersionError` before
any entry payload is parsed.

## Calibration — verified against the real engine, not merely derived

Every figure below was produced by actually driving `resolve_turn` against the real, unmodified
`deficit_demo.yaml`/`decree_state.yaml` content — not hand-computed and not assumed from the
pre-implementation plan.

**The controlled fixed point.** `citizens_bloc/moderates` (`deficit_demo`, baseline -2,000),
investing 100/turn against decay alone (no budget decision ever submitted), settles at **exactly
+4,856** and holds it indefinitely — confirmed turn 1 (0), turn 20 (4,850), turn 25 (4,856), turn 60
(4,856). This is the phase's central, load-bearing claim: 3B2A would have frozen wherever
investment stopped, forever; 3B2B decays it back down the moment investment stops, confirmed by
actually stopping investment mid-run and watching the relationship fall.

**The decree-only penalty band.** Re-decreeing the currently-active rate every turn on
`decree_state` (`UNCHANGED` content, so the policy component is always exactly 0) settles
`governing_party/core` (baseline +6,000) at **4,400** and `opposition_party/main` (baseline -8,000)
at **-9,600** — both a deviation of exactly -1,600 from their own baseline, stable from turn 46,
independent of which side of zero the baseline sits on. A single decree, with no further decision
of any kind, visibly recovers instead: `governing_party/core` closes turn 1 below its baseline
(policy +50, decree bypass -200, net negative) and its relationship strictly increases every
subsequent turn.

**A real formula bug was caught by this calibration work, not before it.** The report's policy-
reaction validator (`PoliticalRelationshipReport._policy_reaction_components_match_the_proposal_and_preferences`)
originally re-derived the expected reaction from the report's stored proposal fields
unconditionally, without checking whether the outcome had actually enacted anything. A
`FAILED_LEGISLATIVE` turn genuinely carries a real (rejected) proposed rate change, so its
`tax_intensity_bps` is nonzero — the validator therefore demanded a nonzero reaction that the
sibling existence check (validator 3, gating on outcome) had just forbidden, an internal
contradiction. This reproduced immediately on turn 1 of a `decree_state` soak run and was fixed by
gating validator 4 on the same outcome condition validator 3 already uses. A second bug of the same
shape was found in `reconciliation.py`: the new legislature-presence check (group 23c) was nested
inside the same `opening_legislature is not None` guard that the row-coverage and
preference-correspondence checks legitimately need — which made the presence check unreachable in
the one scenario it exists to catch (a fabricated `legislature_present=True` on a country with no
legislature at all, where `opening_legislature` is `None` by definition). Both were caught by
building the calibration/reconciliation tests against the real engine rather than trusting the
formulas in isolation, and both are fixed in the shipped code.

## Performance

Soak timing was re-measured (one discarded warm-up, three measured samples, medians compared)
against the five existing 100-turn soaks. All five ratios (post-3B2B median / pre-3B2B baseline)
land between 1.19x and 1.34x — comfortably under the 2.0x stop-and-report threshold the working
plan set. The two `decree_state` soaks (a proposal every turn; mixed budget + relationship
investment every turn) already exercise repeated decrees and mixed political-memory activity every
turn, so they serve the same role the plan's two originally-proposed new soaks would have, and no
additional soak test was added.

## What the working plan predicted but did not materialize

The plan's own risk analysis (M12, M13) predicted that budget→politics phase isolation would
necessarily widen — a tax-rate change would move `PoliticalReport` and break
`test_phase_isolation.py`'s existing byte-identical assertions, requiring a deliberate inversion.
That did not happen: because policy reactions live entirely on the new, separate
`PoliticalRelationshipReport` rather than being folded into `PoliticalReport` (the R4-revised
report architecture, resolved before implementation began), `PoliticalReport` itself stays exactly
as isolated from budget content as it always was. All 16 `test_phase_isolation.py` tests pass
unmodified. Likewise, the resource-deposits/economic-baseline exclusion test predicted to need a
matching `politics.legislature` exclusion did not: that test's two runs share an identical
legislature and submit no relationship-moving decisions, so decay produces byte-identical results
on both sides regardless. Only M11's soak-test predictions (a bloc's relationship is no longer
non-decreasing; the legislature is no longer byte-identical to the authored copy once
`government_relationship_bps` is excluded) materialized as predicted, and both were fixed.

## What is deferred

The pre-implementation plan's full §12 calibration matrix (three `deficit_demo` strategies, eight
`decree_state` strategies, five `tiny_valid` cases, each pinned turn-by-turn for the plan's full
horizon) is not reproduced verbatim in the shipped test suite. A reduced-scope replacement,
`test_relationship_memory_calibration.py`, pins the phase's central claims (the 4,856 fixed point,
the -1,600 decree-only band, single-decree recovery, the affordability guarantee) against the real
resolver. The full exhaustive matrix — every bargain cost and capital-ledger figure across all 16
strategies — is tracked as follow-up work, not lost: §12 of the working plan remains the reference
for what a complete pass would need to verify.

Elections, seat redistribution, defections, coalition collapse, confidence votes, characters,
ministers, coups, protests, repression, civil war, an emergency system and courts remain out of
scope, unchanged from ADR 0011's own list. `FIN-1`, `POL-2`, `HIST-1`, `FE-1` are untouched.
`TEST-1` (the AST float/division/randomness determinism scan covers only `relationships.py` and, as
of this phase, `political_memory.py` — not `apportionment.py`/`legislative_voting.py`) remains open,
tracked, and deliberately not fixed here.
