# ADR 0011: Competing political-capital uses and bloc relationships

- Status: accepted
- Date: 2026-08-12

## Context

ADR 0010 (Phase 3B1) made political capital genuinely spendable for the first time, on exactly one
thing: a budget's legislative or decree route. Its own retraction named the consequence plainly —
at capacity, a commitment can be fully refunded by the same turn's regeneration, so for a
government simultaneously at capacity and holding `UNLIMITED` decree authority, decree may weakly
dominate legislating. Three reasons were given, and the first two are exactly what this phase
closes: **no competing same-turn capital uses exist**, so "capital spent here is capital
unavailable elsewhere" was vacuous, and **legislature composition is static** —
`government_relationship_bps` is authored once and never moves, so a player can never change how a
bloc feels about the government. ADR 0010 named the unblocker by ticket id: `POL-3`, multiple
competing political-capital expenditures plus relationship consequences.

Phase 3B2A is `POL-3`'s first half. It gives political capital a second sink that competes with the
first, and makes a bloc's relationship to the government something the player can move —
deterministically, at a price, with a one-turn delay so the same capital can never both buy a vote
and improve the relationship that vote is scored against.

**⚠ ADR 0010 §7.11.2's retraction is not reversed.** Its unconditional claim — that neither route
is ever mechanically pointless — was wrong and stays withdrawn. This ADR makes a narrower, worked
claim instead, cited against real calibration evidence below: a decree's opportunity cost becomes a
real, binding, same-turn constraint even under full regeneration, because the affordability guard
is against *opening* capital, so capital committed to a decree is capital that cannot also go into a
relationship investment that same turn.

## Decisions

### A discriminated decision union, located by kind, never by tuple position

`Decision` becomes `Annotated[BudgetDecision | BlocRelationshipInvestmentDecision,
Field(discriminator="kind")]`. `BudgetDecision`'s `kind: Literal["budget"] = "budget"` is unchanged
— its own module docstring had already named this as the point to introduce the union, not before.
`DecisionSet` gains `budget_decision()` and `relationship_investment_decision()`, which locate a
member by `isinstance`, and every production call site uses them.

**This was not cosmetic.** Canonical kind ordering sorts `"bloc_relationship_investment"` before
`"budget"`, so on any turn carrying both, index 0 is the investment. Four shipped sites assumed
`decisions.decisions[0]` was the budget — two in `phases.py` (the vote and the gate), two in
`reconciliation.py` (group 16's gating check and group 18's cardinality report) — and every one of
them would have silently operated on the wrong decision the first time a real mixed turn occurred.
All four were found by a global sweep (`rg 'decisions\[[0-9]+\]'`) and converted to kind-filtered
lookups, with a dedicated regression test proving the accessors locate by kind on a mixed set where
positional index 0 is *not* the budget.

`DecisionSet` gains a canonical kind-ordering validator (ascending, rejected not normalised — the
same rule every other collection in this project uses) and a rewritten cardinality validator: the
Phase 3B1 form counted `len(self.decisions)`, which would have wrongly rejected a budget plus an
investment as "two decisions"; it now counts `isinstance(d, BudgetDecision)`.

### The relationship formula: a fraction of the remaining gap, capped per turn

```
RELATIONSHIP_HALF_GAP_CAPITAL = 500
RELATIONSHIP_INVESTMENT_CAP   = 200

gap  = 10,000 - opening_relationship_bps
gain = trunc(gap * political_capital / (RELATIONSHIP_HALF_GAP_CAPITAL + political_capital))
```

`political_capital` is asserted in `[1, 200]`, never clamped — the decision layer already rejects
anything outside that band, so silently clamping in the formula would let the two drift apart
without anyone noticing. The cap is enforced at the decision (`StrictRelationshipInvestment`), not
only inside the formula: an earlier draft let the decision accept any positive amount while the
formula silently capped its effect, so a player committing 500 capital would have had 500 deducted
while receiving exactly what 200 buys — capital destroyed for nothing, and a strictly dominated
action the engine happily accepted. `201` is now a rejected decision, not a truncated one,
consistent with reject-not-normalize everywhere else in this project.

**The guarantees this formula makes, and no others:**

1. **Monotonic non-decreasing** in committed capital, for every opening relationship. Universal,
   Hypothesis-checked.
2. **Bounded strictly below the remaining gap**: `0 <= gain < gap` whenever `gap > 0`, so a closing
   relationship never reaches `+10,000`. Universal.
3. **A smaller remaining gap never yields a larger gain** at the same committed capital. Universal,
   verified exhaustively over a wide sweep of gap/capital pairs.
4. **The unrounded rational envelope has diminishing marginal returns.** True of the envelope,
   stated *as* an envelope property.
5. **The `1..200` cap bounds one turn to at most `200/700 = 2/7`** of the remaining gap, per bloc.
6. **Repeated equal investments buy strictly less** in absolute basis points each time, because the
   gap itself shrinks.

**⚠ Two guarantees an earlier draft claimed, and does NOT hold, are explicitly disclaimed:**

- **No universal strict per-integer monotonicity.** Truncation means adjacent capital values can
  tie: at a remaining gap of 700 basis points, 16 of the 199 steps in `[1, 200]` tie; the smallest
  gap with no tie anywhere in that range is 910. This is a measured fact about `H = 500`, not a
  threshold the formula promises.
- **No discrete concavity of the realized (truncated) marginal gain.** The continuous envelope
  `gap·c/(H+c)` is concave, but flooring it means the realized marginal can *rise* at some
  integer steps: at a remaining gap of 12,000, the marginal rises at 46 of 198 steps (e.g. 23 → 24
  at `c = 5`); at a gap of 8,000 it rises at `c = 6` (15 → 16).

Both are recorded as measured behaviour in the module's own tests, specifically so a future reader
cannot quietly reintroduce either claim.

### Capital ledger: one identity, generalized

```
total_committed = legislative_or_decree_commitment + Σ relationship investments
total_committed <= opening_political_capital                       # guard, slot 1
closing         = min(capacity, opening_political_capital - total_committed + regeneration)
```

The clamp order and the closing formula are **unchanged** from ADR 0010 — what changed is only what
feeds `total_committed`. `PoliticalCapitalReport` — `TurnReport`'s eighth report — carries a
homogeneous ledger (`CapitalExpenditureReport`, one row per commitment: category, optional
`(party_id, bloc_id)` target, amount, and a provenance digest) and a homogeneous relationship-detail
tuple (`BlocRelationshipChangeReport`, re-deriving the formula from its own stored fields, never by
calling `relationships.py` — the same two-code-paths discipline `BlocVoteReport` already followed
for voting formulas). Nine self-validators live directly on the two report models; three
`TurnReport` cross-validators tie the ledger to `PoliticalReport` and `LegislativeReport`, including
route/category consistency (a decree outcome implies exactly one `DECREE` row and no influence
rows; `NO_PROPOSAL` implies neither, and permits investment rows with every route including
`NO_PROPOSAL` itself — a relationship-only turn is a valid, complete ledger).

**⚠ The ledger's extensibility claim is narrower than an earlier draft asserted.** The
total-spending identity generalizes to any number of future categories without change. The **row
schema** does not: `CapitalExpenditureReport` addresses a legislative bloc by `(party_id, bloc_id)`
and nothing else. A future expenditure with a different target kind — a character appointment, an
untargeted national campaign, repression aimed at a population group — needs a tagged target model,
tracked as `POL-4`, not claimed as free here.

### Phase placement: no sixteenth slot

The vote runs at slot 1 against **opening** relationships (already true, unchanged from Phase 3B1);
capital resolves at slot 10 against the ledger total; the relationship investment is *applied* at
slot 11 — `update_institutional_loyalty_competence_corruption_power`, previously `_noop`. No new
slot exists. The fit is not a scheduling convenience: a bloc's relationship to the government
literally is that caucus's loyalty, and slot 11 runs after both the vote (slot 1) and capital
resolution (slot 10) — the exact ordering the one-turn delay requires. `politics.legislature` gains
its first writer here; the AST source-scan discipline that protects `political_capital` extends to
guarantee this is its only writer.

**The one-turn delay is structural, not a rule enforced after the fact.** Slot 1 has already
computed every bloc's effective support and resolved the vote before slot 11 exists, so the same
capital physically cannot both buy direct influence and improve the relationship that same vote is
scored against. A dedicated test submits a relationship investment alongside a budget proposal in
the same turn and confirms the vote tally is byte-identical to the same budget submitted alone that
turn — the investment changes nothing about the vote it accompanies, only what a later vote will be
scored against.

### R13: a guaranteed zero-effect investment is refused, never charged

Slot 1 resolves each investment's target against the opening state, computes the real gain via
`relationship_gain_bps`, and raises an actionable `DecisionSetError` if that computed gain is zero
— atomically: no capital moved, no relationship moved, no turn advancement, no history entry, input
save byte-identical.

This is deliberately written against the **computed gain**, never against a bare `gap == 0` check:
truncation alone can zero out a small gap at low capital even when the gap is nonzero (a gap of 100
at 1 capital, or 400 at 1 capital, both compute to zero gain), and a rule keyed only on the ceiling
would miss both. State-dependent rejection at slot 1 does not weaken replay determinism — slot 1
already performs three other state-dependent rejections (target existence, route availability,
affordability), and replay repeats the identical check against the identical historical opening
state. The alternative — accepting the charge as an uninformative-but-valid move, on the theory that
a failed legislative vote also consumes capital for nothing — does not survive scrutiny: a failed
vote is a real attempt that genuinely could have succeeded, so the capital bought a real chance. An
investment against a zero-effect gap is a guaranteed no-op, knowable *before* resolution. Charging
for it is not an informative bad move; it is a trap.

### R12: group 12 rewritten, twice over

The Phase 3B1 reconciler gated groups 13–15 (structural chamber/party/bloc checks, matched against
the report's own rows) on whole-model `opening_legislature == closing_legislature`. Phase 3B2A makes
`government_relationship_bps` genuinely mutable, so that condition is false on every turn that
carries a real investment — exactly the turns needing the strongest structural coverage. Dropping
the gate is part of the fix, and group 14 is repointed to compare a vote row's relationship against
the **opening** state alone (the value the vote was actually scored against), never the closing one
— pinning that is what makes a retroactively-rescored vote (a report built as if it already knew
this turn's improved relationship) a reconciliation failure rather than an undetectable tamper.

**A second, sharper gap was found while writing the regression test for the first.** Groups 13–15
compare the **report's own** chamber/bloc rows against state, and a `NO_PROPOSAL` or
`ENACTED_BY_DECREE` turn carries **zero** such rows by construction — there was no vote to report.
So even with the gate correctly dropped, those groups have nothing to compare on exactly the turns
where a relationship-only investment is most likely: a turn with no legislative proposal at all.
Confirmed empirically before the fix (a corrupted chamber `total_seats` on such a turn produced an
**empty** reconciliation problem list) and after (the same corruption is caught). The fix adds a
second, independent check directly to group 12: a whole-model `==` fast path on any turn with no
reported relationship change (the O(1) common case), and a field-by-field slow path — comparing
chambers, and every party/bloc's role, discipline and both preferences, directly between the two
states, with no report row as an intermediary — the moment a relationship change is reported. This
is what actually proves D7-style structural staticness (composition is static except relationship)
on **every** turn a legislature exists, independent of whether that turn produced any report rows at
all.

Groups 19–21 are new: the capital ledger against both states; relationship-change rows against both
states, plus an independent check that every bloc **not** named by a relationship-change row is
byte-identical across the two states (the untargeted-immutability guarantee — the specific case a
naive "just drop the old gate" fix could still miss); and investment-decision provenance, mirroring
group 18's discipline for the budget exactly, including a check the budget's digest already had and
the investment's had not: `CapitalExpenditureReport.decision_digest` is now verified against
`bloc_relationship_investment_digest` of the real submitted decision, not merely checked for
well-formed hex syntax.

### Version bump 0.9.0 → 0.10.0, and the one-decision migration policy

`RULESET_VERSION` and `SUPPORTED_CONTENT_VERSIONS` move to `0.10.0`; `SAVE_FORMAT_VERSION` stays 1.
A genuine 0.9.0 save was frozen with the unmodified Phase 3B1 engine before any model or constant
change, committed as a fixture, and is rejected specifically by `UnsupportedRulesetVersionError`
before any entry payload is parsed. Each of the three scenario files changes exactly one line —
`content_version` — proved by a test that reverts only that line and confirms the reparsed result is
byte-identical to the file as it stood before the bump, so a stray calibration edit could never ride
along unnoticed.

## Calibration: the eight-turn break-even is accepted as designed

Every figure below comes from driving the real engine turn by turn, not from hand computation —
`test_relationship_calibration.py` pins them against `resolve_turn`'s actual output.

On `deficit_demo`, investing 100/turn in `citizens_bloc/moderates` (opening relationship −20%, gap
120 percentage points) alongside the cheapest legislative bargain each turn: the bargain falls from
162 on turn 1 to 0 by turn 8. The strategy is **behind** the never-invest baseline for **seven
consecutive resolved turns** (a peak deficit of 187 committed capital at turn 3) and **first becomes
cheaper after resolved turn 8**.

On `decree_state`, a strategy that decrees on turn 1 only (250 is cheaper than the turn-1 bargain of
283) and legislates from turn 2 on (200 is already cheaper than 250 by then), investing whatever
capital the route leaves up to the 200 cap: behind the always-decree baseline for the same seven
turns, first cheaper after resolved turn 8, having spent 1,899 in total and then nothing forever
after.

**The revision-1 "decree 250 + invest 200 every turn" strategy is arithmetically impossible past
its first turn**, confirmed against the real resolver: 450 fits inside `decree_state`'s opening 500
(turn 1, closing 433), but 433 cannot afford 450 on turn 2 — asserted as a genuine
`TurnResolutionError`, not merely arithmetic.

On `tiny_valid` — a majority government, where passage is never in doubt — investing 100/turn in
`rural_alliance/farmers` (opening relationship +20%, gap 8,000 basis points) widens margin, not
passage: the upper chamber's margin moves at turn 2, the lower's not until turn 3, and a second
lower seat not until turn 7. A single investment does **not** move both chambers at once.

**What this proves, stated at the strength the evidence supports and no further:**

- A decree's capital cannot also go to a relationship in the **same** turn, because the guard is
  against *opening* capital — on `decree_state`, turn 2 opens at 433 and `250 + 200` does not fit.
  This is a real same-turn bandwidth constraint, present even under full regeneration.
- A government that decrees every turn pays 250 forever with no relationship movement; the adaptive
  strategy pays more up front and then nothing, overtaking the decree baseline after resolved turn
  8.
- **Decree is not dominated.** The adaptive strategy *uses* the decree on turn 1, and the
  always-decree baseline leads for seven resolved turns. A player expecting a short game should
  decree.
- **ADR 0010's retraction stands, unreversed** — this ADR states the narrower claim above and cites
  this calibration as its evidence, and deliberately does not use language implying the earlier
  retraction was undone.

## No relationship decay in Phase 3B2A — an interim limitation, stated plainly

Relationships can only improve in this phase. A patient player eventually reaches a free budget
everywhere the formula permits it — turn 8 on both fixtures, at the constants chosen. **This is a
known, named interim limitation, not an oversight.** The counterweight — automatic relationship
reactions to policy outcomes and to being bypassed by decree, plus decay — is Phase 3B2B, the
second half of `POL-3`, deliberately split out (§ below). **No permanent-balance claim is made
here.** Improve-only relationships are correct and complete for what Phase 3B2A sets out to do —
give capital a second, competing sink with a real one-turn-delayed payoff — and incorrect as a
long-run political model on their own.

### The §24.4 constant decision, recorded verbatim

`RELATIONSHIP_HALF_GAP_CAPITAL = 500` and `RELATIONSHIP_INVESTMENT_CAP = 200` were confirmed
unchanged against the alternative of loosening `H` to accelerate the break-even, for five stated
reasons:

- Eight resolved turns is approximately a **two-year strategic horizon**.
- Relationship investment is **intentionally long-term**.
- A weaker `H` (e.g. 300) would **accelerate the improve-only ratchet** before Phase 3B2B introduces
  decay and adverse reactions — the wrong direction to tune ahead of the mechanic that is supposed
  to balance it.
- **Ignoring relationships remains viable** — the never-invest baseline is affordable out of either
  scenario's capacity, just strictly more expensive from turn 8 on.
- **No recalibration was required** — every figure in the calibration section above stands exactly
  as computed against the constants as shipped.

## Known limitations

1. **No relationship decay or automatic reaction exists.** Improve-only, as stated above. Unblocked
   by Phase 3B2B.
2. **The capital ledger's row schema is bloc-targeted only.** A future expenditure with a different
   target kind needs a tagged target model. Tracked as `POL-4`.
3. **`RELATIONSHIP_INVESTMENT_CAP = 200` is now player-visible** — it bounds a decision field, not
   merely an internal tuning constant, so changing it later is a compatibility event, not a silent
   retune.
4. **Neither guarantee an earlier draft claimed for the relationship formula holds universally**:
   per-integer strict monotonicity and discrete concavity of the truncated marginal gain are both
   explicitly disclaimed and pinned as measured non-properties (see the formula section above).
5. **The break-even horizon (eight resolved turns) makes the mechanic's value depend on session
   length.** A game expected to end within eight turns makes relationship investment a losing move
   — correctly, per the calibration above, but worth naming as a design property for future
   game-length work (Phase 3C).
6. **`HIST-1`** (the unreachable `return problems` at `history.py`'s tail) remains excluded — this
   phase touches the file again (a digest check in reconciliation, not `history.py` itself, so the
   argument for folding it in is weaker here than it was for ADR 0010).
7. Carried forward unchanged from ADR 0010: `FIN-1`, `POL-2`, `FE-1`, `EMERGENCY_ONLY` confers no
   decree power, AI-country politics do not exist.

## Consequences

- Political capital has two genuinely competing sinks for the first time, and the same-turn
  opportunity cost ADR 0010 could only gesture at is now real and calibrated.
- A bloc's relationship to the government is, for the first time, something the player can move —
  at a price, with a deliberate one-turn delay, bounded so it can never be maximized quickly or
  reached exactly.
- `TurnReport` carries an eighth report; reconciliation gains three new groups and a rewritten one,
  closing a real coverage hole (structural corruption on report-row-empty turns) found while
  building this phase's own regression tests, not merely satisfying the plan as originally
  specified.
- History replay's decision-tamper coverage extends to the new decision kind with the same
  discipline ADR 0010 established for the budget, including a digest check for the investment ledger
  row that the budget side already had.
- Three authored constants (`H = 500`, `CAP = 200`, and the `1..200` decision bound) encode how fast
  politics forgives. All are form-blind, swept against real scenario data, pinned by tests, and this
  ADR records that Phase 3B2B/3C may revise them — `CAP` is now a compatibility-relevant constant
  rather than a purely internal one.
