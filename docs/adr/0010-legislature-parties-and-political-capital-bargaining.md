# ADR 0010: Legislature, parties, blocs and political-capital bargaining

- Status: accepted
- Date: 2026-08-11

## Context

ADR 0009 (Phase 3A) established a constitution, a legitimacy metric, and political capital that
**regenerates but cannot be spent**. `core/politics.py` said so in terms ("expenditure begins in
Phase 3B"), `legitimacy.py` hardcoded `spent=0`, and `report.py` carried `political_capital_spent`
purely so the identity shipped then would already be the final one. On both committed fixtures,
political capital pinned to capacity within two turns and stayed there forever. The government had
authority, acceptance and a governing resource, and nothing whatsoever to spend that resource on.

Phase 3B1 closes that gap. It introduces chambers, parties, internal blocs and seats, then routes
**the existing budget decision** through a deterministic legislative vote the player can influence
by spending political capital. A minority government that wants to raise taxes must build support
or buy it — and can lose.

This is deliberately not an inert "law passed" record. The proposal *is* the budget, which already
drives tax bases → revenue → treasury (Phases 2A/2B2) and, through output, legitimacy (3A). A
failed vote means the tax rates genuinely do not change and the economy genuinely diverges from
the counterfactual where they did.

**The governing principle, inherited from ADR 0009 and extended:** the engine models *how a
legislature is composed* and *how it votes on a specific proposal*. It never encodes an opinion
about which forms of government deserve to be able to legislate.

## Decisions

### Chambers, parties, blocs, and canonical identity ordering

`LegislatureState` holds `chambers` (one or two) and `parties` (one or more). Each `PartyState`
carries a `government_role` and one or more `LegislativeBlocState`s; each bloc carries its own
seats per chamber, discipline, government relationship, and tax/spending preferences.

**Blocs, not parties, carry `government_relationship_bps`.** A rebel caucus inside a governing
party is the politically interesting case, and party-level-only loyalty would make it
unrepresentable. The party's *formal* role stays on the party; the bloc's *actual* relationship to
the government stays on the bloc.

Ordering is **canonical and rejected, never silently normalised** — the `resource_deposits` rule
from Phase 2C1, not the `sectors` rule:

| Collection | Identity | Canonical order | Completeness |
|---|---|---|---|
| `LegislatureState.chambers` | `LegislativeChamber` | enum declaration order | must match the constitution's chamber count |
| `LegislatureState.parties` | free-form `str` id | ascending `id` | ≥ 1 |
| `PartyState.blocs` | free-form `str` id | ascending `id` | ≥ 1 |
| `LegislativeBlocState.seats` | `LegislativeChamber` | enum declaration order | none |

Two legislatures with identical content must produce byte-identical canonical JSON regardless of
the order a caller happened to build them in, and silently reordering would hide a caller bug
rather than surface it. A bloc is addressed globally by `(party_id, bloc_id)`, which is also the
canonical tie-break key for apportionment.

### Exact seat reconciliation

For every chamber, `sum(bloc seats in that chamber) == chamber.total_seats` — **exact equality,
rejected at construction**, not merely "does not exceed".

Missing seats are not a harmless gap. Passage is measured against `total_seats`, so unheld seats
would behave as permanent, invisible abstentions that no bloc owns and no player can bargain with
— a government could be structurally unable to pass anything for a reason nothing in the model
names. `simulation.invariants` re-asserts the same identity independently, to catch a
`model_construct` bypass or a tampered save that never passed the model validator.

### Strict majority: `total_seats // 2 + 1`

```
required_yes_seats = chamber.total_seats // 2 + 1
chamber_passes     = supporting_seats >= required_yes_seats
```

100 seats require 51, so an even 50/50 split does **not** carry; 99 seats require 50, so 49 fails
and 50 passes.

**A tie fails, and no tie-breaker is introduced.** There is no casting vote, speaker, or quorum
anywhere in state, so inventing one would be exactly the undefined mechanism this project forbids.
There is no authored per-chamber passage threshold either: per-proposal-type supermajorities
arrive in a later phase together with a proposal type that actually needs one.

### Chamber-level largest-remainder apportionment

Support is converted to seats **per chamber**, over every `(party_id, bloc_id)` row seated there:

```
numerator_i  = bloc_seats_i * effective_support_bps_i     # exact, no division yet
base_i       = numerator_i // 10_000
remainder_i  = numerator_i %  10_000
target_total = sum(numerator_i) // 10_000                 # the chamber's true support mass
extras       = target_total - sum(base_i)
# one extra seat to the `extras` rows with the largest remainders,
# ties broken by canonical (party_id, bloc_id) ascending
supporting_i = base_i + bonus_i
```

**Why not per-bloc truncation.** An earlier design floored each bloc independently, discarding
every remainder. That gave identical support mass wildly different seat counts depending purely on
how finely a chamber happened to be subdivided: 100 one-seat blocs at 60% support each yielded
**0** supporting seats, while a single 100-seat bloc at 60% yielded 60. That is a fragmentation
bias with no political meaning, and it is now a pinned regression test (100×1-seat @ 60% → **60**).

The algorithm lives in its own module (`simulation/apportionment.py`) because it is a general,
provable allocation rule rather than legislative trivia, and it carries five proved properties:
the awarded seats sum to the chamber's true target; no row ever receives more seats than it holds
(a full-support row has remainder 0 and is provably never awarded a bonus, since `extras` is
strictly fewer than the number of rows with a positive remainder); support mass is invariant to
splitting or merging otherwise-identical blocs; input tuple order cannot change the result; and
tie-breaking is deterministic.

### Bicameral passage is AND, never a pooled tally

```
proposal_passes = all(chamber_passes(c) for c in legislature.chambers)
```

Each chamber independently reaches its own strict majority against its own size. **Chambers are
never pooled.** Two chambers that vote as one are one chamber.

This is load-bearing, not cosmetic. A lower chamber at 80/100 and an upper at 20/60 fails
per-chamber, while a pooled 100/160 against a pooled majority of 81 would pass — a large friendly
lower chamber would drown out a hostile upper chamber entirely. The CLI renders each chamber
separately for the same reason, and the `legislative_vote_resolved` reason ID, whose seat figures
*are* sums for concise reporting, states explicitly that they are totals across separately decided
chambers.

There is no conference committee and no override procedure. Both are named as absent rather than
stubbed.

### Vote inputs: role, relationship, preference, influence, discipline

Each bloc's support is built in explicit, independently re-derivable stages:

```
baseline_support_bps  = clamp(ROLE_ANCHOR[party.government_role]
                              + trunc(relationship_bps * RELATIONSHIP_WEIGHT_BPS / 10_000))
policy_compatibility  = tax_component + spending_component        # ±4,000 combined
raw_support_bps       = clamp(baseline_support_bps + policy_compatibility)
influence_bps         = min(MAX_INFLUENCE_BPS, allocated_capital * INFLUENCE_BPS_PER_CAPITAL)
final_support_bps     = clamp(raw_support_bps + influence_bps)
effective_support_bps = clamp(final_support_bps
                              + trunc((final_support_bps - 5_000) * discipline_bps / 10_000))
```

Role anchors are 8,000 (coalition) / 6,000 (confidence-and-supply) / 2,000 (opposition) — an
opposition anchor of 0 would make opposition literally unbuyable, which is a different game.
Influence is linear then hard-capped at 3,000 bps, so money alone can never move a bloc more than
+30 percentage points. **Discipline amplifies a bloc's lean away from the 50% midpoint**: 0 gives
pure proportionality, 10,000 doubles the lean. It is load-bearing rather than decorative — the
`deficit_demo` worked case tallies 51 with discipline applied and 46 without.

Every one of these inputs is stored on the corresponding `BlocVoteReport` row, so a report can be
replayed and re-checked from its own stored data without recomputing support from scratch.

### Spending change carries an explicit direction and a saturated intensity

A bare "percent change" cannot express a change from zero, so the model stores a direction plus a
saturated intensity, with all four branches explicit:

| Branch | Direction | Intensity | Reasoning |
|---|---|---|---|
| `0 → 0` | `UNCHANGED` | 0 | nothing changed |
| `0 → positive` | **`INCREASE`** | **10,000 (max)** | the relative change is undefined; creating a program where none existed is the *largest* possible spending change, not the smallest |
| `positive → 0` | `DECREASE` | **10,000 (max)** | exactly −100%, which saturates |
| `positive → positive` | sign of the difference | the normal relative change | |

The `old == 0` branches are decided **before any division**, so the division helper's
positive-denominator precondition is never violated. A field that could only ever lie about the
`0 → positive` case (a stored `spending_delta_bps`) was deleted rather than kept and documented.

### Government-form neutrality, extended to voting

> **No function in `apportionment.py` or `legislative_voting.py` accepts a `ConstitutionState` or
> any constitutional enum.**

This is the same compile-time, `mypy`-checked guarantee ADR 0009 established for legitimacy, now
covering seats and votes. The constitution is read in exactly **one** place — routing: which
chambers must approve, and whether a decree is constitutionally available. That is structure
deciding *procedure*, never *deservingness*. Two maximally different constitutions with identical
legislatures produce identical tallies, and the guarantee is additionally pinned by a source scan
so an import added later fails the suite.

The practical proof of this is `decree_state.yaml`: its legislature is transcribed field-for-field
from a synthetic regime originally calibrated under a *presidential* constitution, and it produces
exactly the same numbers under a *monarchy*.

### Failed votes consume the committed capital

A failed legislative vote is a normal, completed turn. It leaves `tax_policy`/`spending_plan`
byte-identical to opening, still records every chamber and bloc row including the shortfall, and
**still consumes every point of capital the player committed.**

Refunding would let a player binary-search the passage threshold across turns at zero cost,
discovering the exact price of every bloc for free. The commitment is a bid, not an escrow.

### Commitment is bounded by *opening* political capital

```
committed <= opening_political_capital                                    # guard, at slot 1
closing    = min(capacity, opening_political_capital - committed + regeneration)
```

Expenditure precedes regeneration. Regeneration is derived from *closing* legitimacy, which is not
knowable at slot 1, so spending against it is structurally impossible rather than merely
forbidden. Two Phase 3A functions had their guards tightened from `spent <= opening + regeneration`
to `spent <= opening` to enforce this; the closing *value* was arithmetically unchanged, only
admissibility moved, and that band was unreachable at the time.

### The capacity clamp is accepted as-is — and one claim is retracted

The clamp order is unchanged and the identity is unchanged. What changes is what this ADR is
willing to *claim* about it.

**Political capital in Phase 3B1 is per-turn governing bandwidth, not guaranteed long-term
depletion.** It measures how much a government can push through *this turn*, and it refills from
legitimacy each turn. The exact cost of committing `C`, measured against the no-action
counterfactual, has three exhaustive branches:

| Condition | Stock cost |
|---|---|
| `opening + regeneration <= capacity` | **exactly `C`** — the full counterfactual cost |
| `opening − C + regeneration >= capacity` | **0** — fully refunded by the same turn's regeneration |
| otherwise (straddles the cap) | strictly between 0 and `C` |

All three branches are pinned by tests, with worked figures: `deficit_demo` at 300/800 pays the
full 250 for a decree; a government at 1,000/1,000 pays **nothing**; one at 700/1,000 with
regeneration 439 pays **111** of 250.

**⚠ Retracted claim.** An earlier draft asserted that neither route is ever mechanically
pointless — that every route always carries a lasting opportunity cost. **That claim is withdrawn
as an unconditional statement.** It holds below capacity. It does **not** hold for a government
that is simultaneously *at capacity* **and** holds `UNLIMITED` decree authority: there, a decree
may weakly dominate legislating, because its committed capital can regenerate fully within the
same turn, because Phase 3B1 offers no competing same-turn use for capital, and because habitual
decree use carries no consequence yet.

This is accepted rather than papered over with a larger constant (which could not fix it anyway),
for four reasons: only one budget proposal may be attempted per turn, so bandwidth cannot be spent
repeatedly; a failed attempt still advances time and is permanently recorded in hash-chained
history, and time is the resource that always binds; governments below capacity experience the
full counterfactual cost, which is the normal condition for a government under pressure; and the
substantive fix is a named later ticket (`POL-3`, competing capital uses) rather than a constant
tweak. Neither of the two legislate-only shipped scenarios is even exposed to it — both are
`emergency_only` and cannot decree at all.

### The legislative gate applies to the real budget

The vote is not a separate record that happens alongside the budget. Slot 1 resolves the vote;
slot 2 commits the proposed tax policy and spending plan **only** when the outcome is
`PASSED_LEGISLATIVE` or `ENACTED_BY_DECREE`; slot 10 commits the capital; slot 15 assembles the
report. No new phase-order slot was added — three existing slots are used for their documented
purposes.

With **no** `BudgetDecision` the outcome is `NO_PROPOSAL`, zero capital is committed, and slot 2
behaves exactly as it did before Phase 3B1 — preserving every committed economic figure from
Phases 2A–2C2. This is a hard requirement with its own test, because it is what makes the phase
additive rather than a recalibration.

### Decree: a fixed cost of 250, and no chamber rows

A government whose constitution grants `decree_authority: unlimited` may enact the budget without
a vote, committing exactly `DECREE_POLITICAL_CAPITAL_COST = 250` under the same
`committed <= opening` guard. A decree carries no influence allocations (a decree is not voted on,
so there is nobody to whip — enforced at construction) and produces **no chamber and no bloc
rows**, because no chamber voted and anything tabulated would be invented.

The cost is fixed rather than scaled to the size of the change: a size-scaled cost would need a
second calibration axis and would make "split the change across two turns" a dominant exploit.

**250 is calibrated, not guessed.** An exhaustive dynamic program over each bloc's full marginal
support curve — exact, not sampled, because a chamber's numerator is additively separable across
blocs and per-bloc capital beyond 300 is provably incapable of buying more support — establishes
the cheapest passing legislative bargain in four regimes. The required relationship holds exactly:

```
0 < 162 < 250 < 283
```

`tiny_valid` needs 0; `deficit_demo` needs 162 (so legislating is the cheaper route there);
`decree_state` needs 283 (so decreeing is cheaper); and a hostile-supermajority regime is
legislatively **unreachable at any price** while its 250-point decree remains affordable.

### An invalid or unavailable decree aborts the turn atomically

Requesting `route: decree` where the constitution grants `none` or `emergency_only` is **not an
outcome**. It raises `DecisionSetError` (wrapped as `TurnResolutionError`) and aborts the whole
turn: no turn advancement, no capital committed, no history entry, input save byte-identical, no
output file and no temporary file left behind. The same applies to a legislative route with no
legislature, an influence allocation targeting an unknown party or bloc, an allocation targeting a
bloc holding zero seats, and a commitment exceeding opening capital.

**Why not a reported outcome.** Commanding an act the constitution does not authorise is not a
thing that *happened* and failed; it is a command the engine cannot interpret. Recording it as a
completed turn would assert that a turn legitimately resolved in which the player attempted an
extra-constitutional act and simply… did not. That is a lie about the game state, and it quietly
normalises rule-breaking. A `LegislativeOutcome.ROUTE_UNAVAILABLE` member was considered and
**deleted**; the enum has exactly four members, all describing turns that genuinely completed. It
follows that an aborted turn emits no reason ID, because no report exists to render one into.

If illegal decrees become gameplay later, they need courts, judicial review and
constitutional-crisis mechanics — a real feature with real state, not a quiet reinterpretation of
an invalid command. `judicial_review` already exists as a constitutional axis read by nothing.

`EMERGENCY_ONLY` confers no decree power in Phase 3B1: no emergency state, trigger, threshold or
duration exists to read, and inventing one would be an undefined mechanism.

### C10: an order where no organ can make law is not a government

`first_constitutional_violation` gains a tenth rule:

> With no legislature, the executive must hold **unlimited** decree authority.

An order with `legislature: none` and `decree_authority: none` or `emergency_only` describes a
state that cannot change its own laws by any route at all. That is not a hard government to play;
it is an unplayable one — the absence of a government rather than a constrained one.

C10 is a real constitutional rule, not merely a state invariant, so it is enforced on **every**
path — fresh build, scenario load, and `model_validate_json` history replay — because
`ConstitutionState`'s validator and `simulation.invariants` both call the same single function and
cannot disagree about what "valid" means.

**C10 makes `decree_authority` validity-affecting for the first time**, which changed the
constitution's own exhaustive counts. All figures were recomputed in advance rather than fitted
afterwards: valid configurations **2,862 → 2,538**, C10 is the first violation on exactly **324**
of the 10,368 configurations (2,862 − 324 = 2,538 ✓), and the count test's factorisation is now
`44 × 54 + 9 × 18 = 2,538` rather than a single `× 54` multiplier.

Note what C10 does **not** say: it constrains only the *absence* of a legislature. Unlimited decree
authority remains legal **with or without** one — which is exactly what makes a genuine
legislative-versus-decree choice representable.

### Legislature composition is static in Phase 3B1

Nothing mutates seats, roles, relationships or preferences. Reconciliation asserts staticness on
every resolved turn, and a 100-turn soak submitting a proposal every turn asserts the legislature
stays byte-identical to the authored composition through passes, failures and decrees alike.

Static is not inert: the legislature is read every turn and decides whether the budget applies.
Evolution — blocs reacting to how they are treated, realignment, defections — is Phase 3B2.

### Decision provenance and reconciliation groups 12–18

Three trust boundaries were open, and they were the same boundary seen from three sides: a report
could describe a budget nobody submitted; a report could describe a legislature that was not
there; and history replay ran a weaker check than live resolution.

`LegislativeReport` gains `budget_decision_digest: str | None` — a canonical BLAKE2b-256
fingerprint of the complete submitted `BudgetDecision`, computed over the model's own
`model_dump(mode="json")` so **every field is covered by construction** (kind, all three rate
targets, every spending update, route, and the canonically-ordered influence tuple) with no manual
field selection to drift out of sync. The report stores only the digest, never the decision. The
report's own validator checks **syntax only** — `NO_PROPOSAL` requires `None`, every other outcome
requires a lowercase 64-character hex string. Whether the digest is the *right* one is
reconciliation's job alone, keeping the two code paths independent.

The reconciler gains a required `decisions: DecisionSet | None` parameter (no default, so a caller
cannot silently lose the checks by forgetting it) and seven new check groups on top of Phase 3A's
eleven:

| Group | Proves |
|---|---|
| 12 | legislature presence matches the constitution in **both** states; opening == closing (staticness) |
| 13 | chamber identity, matched by the chamber enum itself — never tuple position; none missing, duplicated or invented |
| 14 | party/bloc identity: every reported row exists in state with matching role, relationship, discipline and both preferences |
| 15 | seat identity: chamber `total_seats` and each row's `seats` against state |
| 16 | **budget gating, per field, against the actually-submitted decision** |
| 17 | capital ordering: opening, committed, the `committed <= opening` bound, and closing |
| 18 | decision provenance: route, digest, influence by `(party_id, bloc_id)`, and staleness fields |

**Group 15 is proved by composition, not re-derivation.** State holds `seats` and `total_seats` and
nothing else; `numerator`, `base_seats`, `remainder`, `bonus_seat`, `supporting_seats` and
`required_yes_seats` exist only in the report. Reconciliation therefore compares only what state
actually holds, and the rest follows transitively: the report's own validators already tie
`required_yes_seats` to `total_seats` and the whole apportionment to each row's `seats`, on every
construction *and* every replay, and reconciliation proves those inputs equal state. This is
airtight without duplicating a single voting or apportionment formula inside reconciliation — and
it is recorded here because a future reader might otherwise "fix" the apparent gap by duplicating
them.

**Group 16 is per field, never aggregate.** Each of the three rate targets and each of the seven
spending categories is checked independently: targeted *and* passed/decreed ⇒ closing equals the
decision's target; otherwise closing equals opening. `compliance_rate_bps` is untargetable and must
always equal opening. Per-field is what catches a tamper that swaps two tax categories while
preserving their sum, or two spending categories while preserving their total — an aggregate check
structurally cannot.

### Live resolution and history replay run the identical check

`_validate_entry_payload` previously parsed `decisions_json` for its hash contribution and **never
validated it as a `DecisionSet`**, so a knowledgeable tamperer who edited a stored decision and
recomputed the chain produced a save that passed every integrity check. It now parses the decision
semantically, returns it, and `validate_history` threads it into the *same* reconciler the live
resolver calls — so replay is no weaker than live play, and a malformed payload is an actionable
problem rather than a crash.

This is what the hash chain alone never could do. The chain detects accidental corruption and
unsophisticated tampering; it cannot stop an adversary who simply recomputes it. Semantic
reconciliation can, and tests prove it for a consistently re-hashed tamper of the proposal route, a
tax target value, a spending target value, a tax category swapped preserving its aggregate, a
spending category swapped preserving its total, an influence allocation, `expected_turn`, and the
report's own digest.

### Version bump 0.8.0 → 0.9.0, and no fabricated migration

`RULESET_VERSION` and `SUPPORTED_CONTENT_VERSIONS` move to `0.9.0`; `SAVE_FORMAT_VERSION` stays 1,
because the envelope is unchanged. A genuine 0.8.0 save was frozen with the unmodified engine
*before* any model or constant change and is committed as a fixture; it is rejected specifically by
`UnsupportedRulesetVersionError`, before any entry payload is parsed.

**No migration is fabricated.** A 0.8.0 save has no chambers, parties, blocs or seats, and none may
be invented — composition is authored content, not something an engine can guess. C10 adds a second,
independent reason old content can be rejected: a 0.8.0 scenario with `legislature: none` and
non-`UNLIMITED` decree authority now violates it. Neither committed scenario is affected.

### Scenario calibration

Every figure below is derived from the scenario files themselves through the real voting and
apportionment modules, not copied from this document — if an author changes a bloc's seats,
relationship or preference, the tests recompute the tally rather than going stale.

The walkthrough proposal throughout is **+5 percentage points on the personal income rate, spending
unchanged**, measured from each scenario's own authored opening rate.

| Scenario | Constitution | Unaided result | Cheapest passage | Decree |
|---|---|---|---|---|
| `tiny_valid` | parliamentary / legislative-selection / **bicameral** / emergency-only | lower **58/100** (majority 51) and upper **33/60** (majority 31) — **passes unaided in both chambers** | **0** | unavailable |
| `deficit_demo` | presidential / direct-election / **unicameral** / emergency-only | **47/100** against a required 51 — **fails**, four seats short | **162** on `citizens_bloc/moderates` → 51/100 | unavailable |
| `decree_state` | **monarchical / hereditary / unicameral / unlimited** | **45/100** — fails | **283** on `opposition_party/main` → 51/100; **282 fails at 50/100** | **250**, enacts unconditionally |

`decree_state` is the scenario that makes the phase mean something for a player: it is the only
shipped scenario holding `decree_authority: unlimited` **alongside a real legislature**, so it is
the only one that offers a genuine route *choice* every turn. Its legislature is the exhaustively
DP-proven "Regime C" promoted field-for-field into loadable content, and its opening capital of 500
(capacity 1,000) affords either route.

`tiny_valid` and `deficit_demo` remain `emergency_only` **by design**, not by omission: they exist
to exercise the vote engine on every turn, and a decree escape hatch would undercut that.

## Known limitations

1. **`EMERGENCY_ONLY` confers no decree power.** No emergency state, trigger, threshold or duration
   exists to read. Unblocked by an emergency system (Phase 3C).
2. **At capacity with unlimited decree authority, decree may weakly dominate legislating** (see the
   retraction above). Unblocked by `POL-3` — competing political-capital uses — in Phase 3B2.
3. **A permanent hopeless minority without unlimited decree authority cannot change the budget at
   all.** Under static composition nothing moves those seats. This is a scenario-calibration
   problem rather than a structural one; it resolves in Phase 3B2 when relationships evolve, and
   Phase 3B1's obligation is met by not authoring such a scenario — asserted for all three shipped
   fixtures.
4. **Legislature composition is static.** No realignment, no defections, no confidence votes, no
   coalition collapse. Phase 3B2.
5. **The budget is the only proposal.** `BudgetDecision` was extended with `route` and `influence`
   rather than introducing a discriminated decision union, because a union of one member is not a
   union. The union arrives with the second proposal kind.
6. **AI-country politics do not exist.** Rejected outright for this phase rather than silently
   unmodelled; it follows AI economies.
7. **`InstitutionState` overlaps the new legislature.** Both committed scenarios author an inert
   institution whose id is literally `legislature`, with float metrics no formula reads. Tracked as
   `POL-2` (re-scoped from "convert the floats" to "resolve the overlap").
8. **`FinanceReport` closing balances are still not reconciled against `TreasuryState`** — a
   pre-existing, unrelated gap tracked separately as `FIN-1`. It would not have caught a gating bug
   anyway: a failed vote produces perfectly self-consistent finance numbers for the *wrong* budget.
   Group 16 is what catches that.

## Consequences

- The economy now has a political gate in front of it. A budget can be refused, and the refusal
  propagates through tax bases, revenue, treasury and — via output — legitimacy.
- Political capital is genuinely spent for the first time, and `political_capital_spent` is nonzero
  on real, tested paths.
- History replay became strictly stronger: a consistently re-hashed decision tamper that previously
  passed every check is now detected.
- The constitution gained its first validity-affecting use of `decree_authority`, and the
  exhaustive configuration counts moved accordingly.
- Three shipped scenarios now span the meaningful cases: passes unaided, must bargain, and must
  choose between bargaining and decreeing.
- Eleven authored constants encode how sharply politics responds. All are form-blind, all have
  stated rationale and pinned tests, and Phases 3B2/3C may revise them.
