# ADR 0013: Government survival — elections, coups, unrest, impeachment, and constitutional amendments

- Status: accepted
- Date: 2026-08-17

## Context

Every phase through 3B2B left the player structurally unremovable. `PoliticalState` had no notion
of a term, an election, or a threat to the government's survival — the product spec's own §3.1
claim that "removal from office" was possible was, as ADR 0012 said outright, "still not
mechanically possible in any form." Phase 3C closes that gap in three gates:

- **Gate 3C1** gives elections a real schedule and a real outcome: `next_election_turn`,
  `consecutive_terms_held`, term limits, and a deterministic support formula blending legislative
  support, population approval, and legitimacy, resolved against a seeded polling swing.
- **Gate 3C2** gives the government real, ongoing risk between elections: coup attempts, popular
  unrest, and impeachment motions, each with an attempt-risk and a success-probability formula
  driven by institutional loyalty/power/competence, population radicalization/approval, opposition
  strength, and legitimacy — plus a `regime_transition_pressure_bps` state that a constitutional
  amendment (Gate 3C3) can raise and that decays on its own between amendments.
- **Gate 3C3** gives the constitution itself a mechanism to change: a five-axis
  `ConstitutionalAmendmentDecision` (decree authority, executive selection, executive system,
  executive term limit, national election interval), routed through the same
  legislative-vote-or-decree choice Phase 3B1 established for budgets, and the one new terminal
  outcome that closes the game as a **VICTORY** rather than a defeat — `peaceful_liberalization_completed`,
  earned by transitioning a noncompetitive constitution to a competitive one and then winning the
  first election held under it.

All three gates share one terminal-state model (`TerminalOutcomeState`, set exactly once, never
cleared) and one election/support formula. This ADR covers all three together, following this
repository's "one ADR, one bump, per phase" convention (`docs/adr/0012-...md` did the same for
Phase 3B2B's two gates).

## Decisions

### Elections: a blended support formula, not a poll

`election_baseline_support_bps` (`simulation/government_survival.py`) blends three inputs at fixed
weights — legislative support (5,000 bps), population-weighted approval (4,000 bps), and
legitimacy (1,000 bps) — into one baseline. A seeded polling swing (`derive_rng(seed, turn,
"election")`, bounded to ±1,000 bps by `MAX_POLLING_UNCERTAINTY_SWING_BPS`) is added once to
produce `final_support_bps`, compared against `REQUIRED_ELECTION_SUPPORT_BPS = 5,000`. `won` sets
`consecutive_terms_held += 1` and reschedules `next_election_turn`; a term-limit breach after a win
is `TERM_LIMIT_EXIT`, a defeat is `ELECTORAL_DEFEAT` — both terminal, both `DEFEAT`. **The RNG
stream is always keyed by the OPENING (resolving) turn, never the closing one** — the same
convention every other Gate 3C channel (coup/unrest/impeachment) uses, and the one this ADR's
Calibration section below had to correct a planning error against.

### Coup, unrest, and impeachment: attempt risk, then success, then consequence

Each of the three channels (`simulation/government_survival.py`) follows the identical shape: an
**attempt-risk** formula (a base rate plus weighted shortfalls against loyalty/legitimacy/opposition
thresholds, capped) is drawn against a seeded `_attempt` stream; on attempt, a **success-probability**
formula (weighted institutional/population/legitimacy defenses, capped) is drawn against a seeded
`_outcome` stream. A successful coup or impeachment is terminal (`DEFEAT`, `COUP` or `IMPEACHMENT`);
unrest has a third, `_severity`-streamed roll that can additionally trigger a loyalty-driven
`removal_triggered` reason without independently concluding the game — the same `_evaluate_elections`
slot that resolves elections is what turns a sufently collapsed institution into a terminal outcome.
None of the three channels reads a constitutional axis directly; every input is loyalty, power,
competence, corruption, radicalization, approval, organization, or legitimacy — the same
government-form-neutrality guarantee every prior political formula in this codebase carries.

### Constitutional amendments: five axes, one route choice, one vote formula

`ConstitutionalAmendmentDecision` (`simulation/decisions.py`) is a tuple of `axis`-discriminated
targets — `DecreeAuthorityTarget`, `ExecutiveSelectionTarget`, `ExecutiveSystemTarget`,
`TermLimitTarget`, `ElectionIntervalTarget` — in canonical alphabetical axis order, submitted
alongside an `InfluenceAllocation` tuple exactly like a `BudgetDecision`'s. `DecisionSet` accepts at
most one policy proposal per turn: a `BudgetDecision` and a `ConstitutionalAmendmentDecision` can
never appear together (`_at_most_one_policy_proposal`). `resolve_amendment_support`
(`simulation/legislative_voting.py`) reuses the budget-vote chain with policy compatibility fixed at
zero (amendments carry no tax/spending content of their own) and scales the passage threshold by
`AmendmentThreshold` — `SIMPLE_MAJORITY` (`total//2+1`), `SUPERMAJORITY` (`(2*total+2)//3`), or
`ENTRENCHED` (`(3*total+3)//4`) — read from the constitution's own `amendment_difficulty` axis. A
decree route costs a flat `CONSTITUTIONAL_AMENDMENT_DECREE_COST = 400`, distinct from a budget
decree's flat cost, and is only legal when `legislature == Legislature.NONE`.

`ConstitutionalAmendmentReport` stores full opening/closing six-axis constitution snapshots (five
amendable axes plus `amendment_difficulty`) and self-validates: canonical target/influence order,
outcome-vs-chamber-tally consistency, per-axis opening/closing correspondence to the submitted
targets (an untargeted axis provably does not move), and `transition_pressure_added_bps` /
`qualifies_as_liberalization_transition` re-derived from the two stored snapshots alone — a report
that can prove its own arithmetic without consulting any other report. The final constitution is
validated **after** every target is applied, not one axis at a time (`test_final_constitution_is_
validated_after_all_targets_not_one_at_a_time`), so an amendment whose intermediate state would
violate C1–C10 is still legal as one atomic set if the final combination is coherent.

### Peaceful liberalization: a persisted, provenance-checked victory

An amendment that transitions the constitution from **noncompetitive**
(`executive_selection ∈ {HEREDITARY, APPOINTED}` or `decree_authority != NONE`) to **competitive**
(`executive_selection ∈ {DIRECT_ELECTION, LEGISLATIVE_SELECTION}` and `decree_authority == NONE`
and a national election interval is set) sets `pending_liberalization` — the opening and closing
constitution digests, and the turn it was set. The next scheduled election checks that pending
state: a win with `pending_liberalization` set completes the liberalization
(`peaceful_liberalization_completed`, a `VICTORY`, and the pending state clears); a loss clears the
pending state without completing anything; the election schedule itself is frozen regardless of
outcome. **A starting democracy cannot win this way**: `tiny_valid` ships already competitive, so
`pending_liberalization` is never set by anything short of a real amendment, and reconciliation
group 42 makes the guarantee structural rather than incidental — `opening_pending.set_at_turn <
closing_state.turn` is required, so no tampered save can fabricate a same-turn transition-and-win
as a liberalization victory (`test_history.py`, case 27).

### Version boundary: one bump for the whole phase, not one per gate

`RULESET_VERSION` moved `0.9.0 → 0.12.0` once, at Gate 3C1, and stayed there through 3C2 and 3C3 —
this repository's established "one bump per phase" convention (`docs/adr/0012-...md` did the same
across its two gates). Its docstring previously undersold what the bump covers, describing only a
tenth report; Gate 3C3 commit 25 corrected the rationale to name all three Gate 3C reports
(`election`, `coup_unrest`, `constitutional_amendment`) the bump actually protects, without
widening the version number itself — no 0.10.0 save has authored election/survival state to
migrate from, so `UnsupportedRulesetVersionError` is the only honest response, exactly as every
prior boundary in this codebase has been.

## Calibration — verified against the real engine, not merely derived

The load-bearing campaign named by this phase's own working plan: on `decree_state.yaml` (100-seat
unicameral legislature, `amendment_difficulty: supermajority`, so passage requires exactly
`(2*100+2)//3 = 67` yes seats), invest 85 political capital in `opposition_party/main` (turn 1,
closing relationship −5,385, capital 798); invest 118 more (turn 2, closing relationship −2,774,
capital 1,000); submit the five-axis amendment (`decree_authority → none`, `executive_selection →
direct_election`, `executive_system → presidential`, `executive_term_limit_terms → 2`,
`national_election_interval_turns → 8`) with 300 PC of influence on the same bloc (turn 3).
Cumulative commitment: 85 + 118 + 300 = **503**. The vote passes at exactly **67/100**, the
narrowest possible margin. `next_election_turn` is set to **11**. `regime_transition_pressure_bps`
decays from the amendment's full 10,000 by 1/6 per turn
(`TRANSITION_PRESSURE_DECAY_DENOMINATOR = 6`): 8,334 → 6,945 → 5,788 → 4,824 → 4,020 → 3,350 → 2,792
across turns 4–10, with no coup, unrest, or impeachment channel firing at any point. All of this was
driven through the real, hash-chained `new_game`/`advance_game` history layer — the same layer the
CLI uses — not a synthetic opening state, and is pinned as literals in
`backend/tests/test_liberalization_campaign.py`.

### The seed correction (load-bearing, disclosed in full)

The phase's own original planning walkthrough claimed the turn-11 election, at `decree_state`'s
authored seed 77, resolves with polling swing **+615**, final support **5,706**, a **WON** election,
and immediate **VICTORY**. Driving the real engine against the identical campaign at seed 77
produces a different, honest result: baseline support **5,091**, swing **−269**, final support
**4,822**, a **LOST** election, and a **DEFEAT** (`electoral_defeat`) terminal outcome — not a
victory. The discrepancy was root-caused exactly: `derive_rng(77, 11, "election")` (the RNG stream
keyed on the **closing** turn, 11) reproduces the plan's claimed +615 exactly. The real engine
always keys every Gate 3C RNG stream — `coup_attempt`, `coup_outcome`, `unrest_attempt`,
`unrest_outcome`, `unrest_severity`, `impeachment_attempt`, `impeachment_outcome`, and `election` —
on the **opening/resolving** turn (10, not 11), the convention Gate 3C1 established and
reconciliation group 38 independently re-derives. The plan's own scratch script indexed the RNG
stream by the wrong turn; the shipped engine does not share the bug. **This is recorded here as a
corrected scratch-script error in the phase's planning material — never as an engine result, and
never repeated as a claimed outcome.** Every other figure in the original walkthrough (the 85/118/300
campaign, the 503 cumulative commitment, the 67/100 passage, the relationship-decay curve, the
5,091 baseline support, `next_election_turn == 11`) matched the real engine exactly to the digit;
only the closing-vs-opening RNG indexing was wrong.

**The victory path is real and is proven separately**, at a declared alternative seed, 0, driving
the identical campaign (same 85/118/300 investments, same amendment, same 67/100 passage): baseline
support **5,091** (unchanged — the baseline formula does not depend on the RNG seed), swing **+719**,
final support **5,810**, a **WON** election, and `peaceful_liberalization_completed` — a genuine
`VICTORY`. Both results — the pinned fixture-seed loss and the declared-seed victory — are asserted
in `test_liberalization_campaign.py`, so the victory condition is proven to exist and to fire
correctly, without ever presenting the fixture seed's real outcome as anything other than what it
is.

### Boundary proofs

- **299 PC of influence** on the same turn-3 amendment produces exactly **66/100** — one seat short
  — and `FAILED_LEGISLATIVE`; the constitution and `next_election_turn` are both left untouched.
- **One fewer preparation turn** — investing only the turn-1 85 PC and submitting the amendment on
  turn 2 instead of turn 3, skipping the second investment turn entirely — reaches only **61/100**,
  six seats short. The two preparation turns are not an arbitrary pacing choice: a single
  `BlocInvestment` is capped at 200 PC, so the real turn-1 + turn-2 total (203 PC) could never be
  submitted in one turn regardless of available capital, making a one-turn substitute for the real
  campaign structurally unreachable, not merely undesirable.
- **A failed amendment changes no constitutional axis** — the opening and closing constitution
  digests are identical, verified axis by axis.
- **A passed amendment changes exactly the five submitted axes** — every other constitution field
  (`amendment_difficulty`) is unchanged, verified directly against the report's own opening/closing
  snapshots.
- **A starting democracy cannot receive this victory** — `tiny_valid`, which ships already
  competitive-elected, wins its first scheduled election without ever setting
  `pending_liberalization`, so the win is `won` but never `liberalization_completed`.
- **No simultaneous `BudgetDecision` and `ConstitutionalAmendmentDecision`** is ever accepted, at
  both the `DecisionSet` construction boundary and the real resolver.

### Final constitution validity

The five-axis amendment's closing constitution (`decree_authority=none`,
`executive_selection=direct_election`, `executive_system=presidential`,
`executive_term_limit_terms=2`, `national_election_interval_turns=8`) passes every constitutional
rule C1–C10 (`first_constitutional_violation` returns `None`) — proven directly, not merely implied
by `resolve_turn` not raising. `executive_term_limit_terms=2` (not 1, which was checked and produces
an immediate `TERM_LIMIT_EXIT` defeat on the very next election instead of a chance at victory) was
the fifth axis's calibrated value, matching `tiny_valid`'s own authored limit.

## Performance

Soak timing was re-measured (one discarded warm-up, three measured samples, medians compared)
against the five existing 100-turn soaks, using Gate 3C2's own measured baseline (125.73 ms/turn and
129.22 ms/turn on the two `decree_state` soaks) as the pre-Gate-3C3 reference. All measured ratios
stayed within the 2.0x stop-and-report threshold; see the final verification report for the exact
post-3C3 figures.

## Known limitations

- **Characters and cabinet ministers are deferred**, unchanged from every prior Phase 3C planning
  document. Every removal reason (`COUP`, `FORCED_ABDICATION`, `ASSASSINATION`, `IMPEACHMENT`,
  `ELECTORAL_DEFEAT`, `TERM_LIMIT_EXIT`) is a fact about the office, never about a named actor — this
  engine has no character layer, by design, through the end of Phase 3C.
- **An emergency system and courts/judicial-review mechanics remain unbuilt.**
  `DecreeAuthority.EMERGENCY_ONLY` is still unreachable without an emergency system to grant it
  meaning, and `judicial_review` is still a constitutional axis read by no formula.
- **AI-country politics, seat realignment, defections, confidence votes, and coalition collapse**
  remain out of scope, carried forward from Phase 3B2B's own deferred list.
- **The engine is now frozen for Phase 3C.** No further formula, constant, relationship, seat count,
  or RNG convention changes are authorized without a new mandate; GUI/frontend work for these
  systems is explicitly out of scope for this phase.

## Consequences

Phase 3C is the first phase in which the player can genuinely lose the game — by coup, unrest,
impeachment, electoral defeat, or term limit — and the first in which the player can genuinely win
it, by peacefully liberalizing a noncompetitive government and then winning the resulting election.
Every terminal outcome is set exactly once (`TerminalOutcomeState`, `resolve_turn` refuses to
resolve any further turn once it is set) and is reachable only through the real, seeded,
government-form-neutral formulas this ADR documents — never through a shortcut, a fabricated
provenance, or a mis-indexed RNG stream. `POL-2` (the `InstitutionState`/`LegislatureState` overlap),
`FIN-1`, `HIST-1` (closed), `FE-1`, and `TEST-1` are untouched by this phase.
