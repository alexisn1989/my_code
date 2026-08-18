# MANDATE — Phase 3C: elections, coups, removal from office, victory and defeat

> **PLAN ONLY.** No branch created, no repository file edited, nothing implemented, committed or
> pushed. Phase 3B2B is shipped and merged (PR #11, `origin/main` = `73824a4`, head `d289869`);
> its design record lives in `docs/adr/0012-*.md` and in git history, and is not reproduced here.
> The merge gate was verified read-only before this plan was written.
>
> **Revision history.** This is Revision 2, responding to eleven binding corrections (R1–R11) a
> review of Revision 1 raised. Every one of R1–R10 identified a genuine bug or an unspecified gap
> in the first draft; the corrections are folded in below, not appended as a patch list, so the
> plan reads as one coherent design. Where a correction is substantial enough to be worth a reader
> knowing what changed and why, a short note says so at the relevant section. **A final,
> plan-only correction (below §17 and the amendment-formula parts of §2.4/§7.2/§11) reopened two
> things after Revision 2 was first presented**: the character/leaders question (§17, resolved as
> genuinely undecided rather than permanently foreclosed) and the exact reachability/affordability
> of `decree_state`'s liberalizing amendment (§2.4/§11(b), computed in full via a scratch script
> driving the real engine — this surfaced a real, provable unreachability in the amendment-support
> formula as first specified, which is now corrected and the full campaign is reported as an exact
> result, not deferred to implementation time). Note: this file was reconstructed verbatim after an
> infrastructure restart discarded the on-disk copy of the fully-corrected Revision 2; every section
> below matches what was reviewed and approved section-by-section in conversation before the
> restart.

---

## Context

Phase 3B2B closed the last item on `docs/roadmap.md`'s standing list of things that make political
capital and legislative bargaining meaningful — relationships now decay, react to policy, and resent
being bypassed by decree. But every phase through 3B2B shares one property: **the game cannot end.**
`resolve_turn` is a pure function that always assumes another turn follows; `advance_game` always
appends another entry; nothing anywhere checks whether the player is still in office. Product spec
§3.1 states the design intent plainly — *"losing office ends the game"* — and its own §41 confirms
this is *"still not mechanically possible in any form"* as of the most recent phase. `docs/roadmap.md`
names Phase 3C, in almost identical words, as *"the first sub-phase that can remove the player from
power — by construction, not by omission."*

Two of the engine's fifteen phase-resolution slots have sat as registered no-ops since Phase 1,
reserved by name for exactly this: `evaluate_protests_strikes_insurgency_coups_revolutions` (slot 12)
and `evaluate_elections_and_constitutional_events` (slot 13). A `PhaseContext.rng(stream)` method has
existed since it was written, with zero call sites, clearly built for whatever needed genuine,
seed-reproducible uncertainty first. `national_election_interval_turns` is a fully validated,
scenario-authored constitutional field that nothing has ever read. `constitutional_order_support_bps`
carries a docstring naming it the coup/amendment write-target. `decree_authority: EMERGENCY_ONLY` has
been unreachable since Phase 3B1. None of this is incidental — the engine was built with this phase's
shape already in mind.

**The outcome this phase is building toward:** a government can now genuinely lose power — to a
coup, a lost election, popular unrest, impeachment, or running out its constitutional term — and the
game recognizes that as its own defined end, the same way it already recognizes an invalid decision
as its own defined failure. A government can also, for the first time, *complete* something: a
dictatorship that peacefully liberalizes and then survives its own first free election has *won*, in
a real, checkable, terminal sense. A democracy that instead tightens into a more authoritarian form
has not won or lost anything — it has changed shape, at a real cost, and must go on being survived
like every other form of government the engine already treats as equally valid. **No constitutional
path is scored as morally better than another; the same formulas decide every government's fate,
form-blind except where the constitution itself is the very thing at stake.**

---

## 0. Design decisions this plan makes (confirmed with the user, or corrected per R1–R11)

1. **No leader/cabinet character system in Phase 3C itself**, confirmed with the user before
   Revision 1. "The government" — the incumbent coalition holding office — is the single unit that
   is elected, removed, or survives a coup. Every removal reason is a label describing *what
   happened to the office*, never data about a named person. **Whether Version 1 ever needs more
   than this is left genuinely open, not foreclosed — see §17's final correction.**
2. **Coup attempts and election results use genuine seeded randomness**, confirmed with the user,
   via `PhaseContext.rng(stream)`.
3. **This plan builds only the 22 items the user listed**, not `docs/roadmap.md`'s full Phase 3C
   scope paragraph (emergency-declaration system, general courts doctrine, non-stock decree cost,
   second proposal kind beyond the one this plan adds, confidence votes, coalition collapse,
   conference committees, per-proposal supermajorities for ordinary law, seat realignment/
   defections, AI-country politics). None of these are built here; see §16.
4. **Both `InstitutionState`'s and `PopulationGroupState`'s float metric fields become strict
   basis points (0–10,000) in this phase, not a future one — R8 correction.** Revision 1 proposed
   converting only `InstitutionState` and reading `PopulationGroupState`'s floats through a
   round-half-to-even bridge function, deferring the second conversion as `POL-2b`. That was wrong:
   this phase is the first real formula consumer of *both* models' metrics, and a "permanent
   float→bps bridge" is exactly the kind of unconverted-precision debt this codebase's own
   discipline forbids building on top of. **Both models convert in the same commit, before the
   frozen-fixture rule even applies** (§10). `POL-2` (the `InstitutionState`/`LegislatureState`
   overlap — redundant `id: "legislature"` rows) closes fully as a side effect; there is no
   remaining `POL-2b`.
5. **One new pure module**, `simulation/government_survival.py`, holds every new formula. It is
   **not** added to `NEUTRAL_MODULES` — the opposite discipline applies on purpose (§3).
6. **Three new top-level reports** — `CoupUnrestReport` (slot 12), `ElectionReport` (slot 13), and
   `ConstitutionalAmendmentReport` (slot 1/2) — **not two, per R5.** Revision 1 tried to describe
   constitutional-amendment voting without a report to carry it, which left it unspecified how a
   second proposal kind gets tallied, digested, and reconciled. §7 now gives the amendment its own
   report, structurally separate from `LegislativeReport` (Option B of R5's two choices — see §7.2
   for why Option A, generalizing `LegislativeReport` itself, was rejected).
7. **One unified terminal-outcome field**, `PoliticalState.terminal_outcome: TerminalOutcomeState |
   None`, covering both victory and defeat.
8. **Elections are a referendum on the incumbent's continuation, not a legislative reapportionment.**
   `LegislatureState`'s seats/blocs/parties stay exactly as static as they are today.
9. **The amendable constitutional axes are five, not three — R2 correction.** Revision 1 restricted
   amendments to `decree_authority`/`national_election_interval_turns`/`executive_term_limit_terms`,
   which cannot construct a coherent liberalized government for a hereditary monarchy (`decree_state`)
   at all: `executive_selection: hereditary` and `executive_system: monarchical` are load-bearing
   for *who holds office*, and no amount of touching decree authority or election scheduling changes
   that a hereditary monarch is still not "elected" by any real process. **`executive_system` and
   `executive_selection` join the amendable set.** §2.4 gives the exact target shapes and the C1–C10
   re-validation rule; §11 gives the exact atomic five-target change that liberalizes `decree_state`,
   now fully computed (§11(b)), not merely asserted legal.
10. **`decree_state.yaml` keeps its real, calibrated unicameral legislature (45 governing / 55
    opposition seats) exactly as shipped — R1 correction.** Revision 1 incorrectly described this
    scenario as having `Legislature.NONE`, which is false (verified directly:
    `constitution.legislature: unicameral`), and designed a decree-route liberalization around that
    error. **No shipped scenario has `Legislature.NONE`**, so the decree route for constitutional
    amendments (§2.4) is structurally supported but not exercised by any of the three scenarios'
    calibration — `decree_state`'s liberalization goes through the **legislative** route, against a
    genuinely hostile, opposition-majority chamber, exactly like its existing Phase 3B1/3B2
    calibration already does for the budget. Nothing about `decree_state`'s existing legislature,
    seats, relationships, or prior calibration is touched.
11. **Election scheduling is `next_election_turn`, an explicit persisted turn number, not
    `turn % interval` — R4 correction.** §4.4 and §8 give the exact rules.
12. **Liberalization victory requires explicit transition provenance, not a snapshot check of the
    current constitution — R3 correction.** §5 gives the exact qualifying-transition definition and
    the new `pending_liberalization` state that carries it from the amendment turn to the next
    election.
13. **Popular unrest and impeachment are two-stage (attempt, then success), exactly like coups — R9
    correction.** Revision 1 gave coups an attempt+success split but let unrest/impeachment remove
    the government on a single "attempt" draw, which could not be calibrated to a low, fair
    background risk. §3.2/§3.3 now give both channels the same two-stage shape, and §11 reports
    the actual cumulative removal probability this produces at 20/40/100 turns for every scenario,
    computed against the real authored data, not assumed.
14. **Transition pressure is written in exactly one place, slot 12, from one combining formula — R6
    correction.** Revision 1 split the write across slot 2 (addition) and slot 12 (decay reading a
    value slot 2 had already mutated), while its own reconciliation group described a different
    order (`decay(opening) + added`). §4.3/§6 now specify the single identity used everywhere.

---

## 1. New types — `backend/app/core/politics.py`

```python
StrictInstitutionMetricBps = Annotated[int, Field(strict=True, ge=0, le=BPS_DENOMINATOR)]
"""An institution's loyalty/power/competence/corruption, in basis points. Replaces the Phase-1
float (0.0-100.0) fields on InstitutionState -- Phase 3C is the first phase to read these by any
formula."""

StrictPopulationMetricBps = Annotated[int, Field(strict=True, ge=0, le=BPS_DENOMINATOR)]
"""A population group's approval/trust/organization/radicalization/political_influence, in basis
points. Replaces the Phase-1 float (0.0-100.0) fields on PopulationGroupState -- Phase 3C is the
first phase to read these by any formula (R8: converted in the SAME commit as InstitutionState's
metrics, not bridged from floats)."""

StrictTermsHeld = Annotated[int, Field(strict=True, ge=1)]
"""How many consecutive terms the incumbent government has held, counting the term already
underway at scenario genesis as term 1."""

StrictTransitionPressureBps = Annotated[int, Field(strict=True, ge=0, le=BPS_DENOMINATOR)]
"""How much a recent constitutional amendment -- liberalizing OR consolidating; this field cannot
distinguish direction by construction, which is exactly what makes its COST symmetric between the
two -- is currently elevating coup risk."""

StrictRiskBps = Annotated[int, Field(strict=True, ge=0, le=BPS_DENOMINATOR)]
"""A per-turn attempt/success probability or election support level, in basis points."""

StrictSignedRiskContributionBps = Annotated[int, Field(strict=True, ge=-BPS_DENOMINATOR, le=BPS_DENOMINATOR)]
"""One named, signed contributing factor to a StrictRiskBps total, before the final clamp --
mirrors StrictRelationshipChangeBps's role in political_memory.py."""
```

---

## 2. New state — `backend/app/simulation/state.py`

### 2.1 `InstitutionState` and `PopulationGroupState` — modified (R8: both convert now)

```python
class InstitutionState(BaseModel):
    model_config = _STRICT_CONFIG
    id: str
    name: str
    loyalty: StrictInstitutionMetricBps
    power: StrictInstitutionMetricBps
    competence: StrictInstitutionMetricBps
    corruption: StrictInstitutionMetricBps

class PopulationGroupState(BaseModel):
    model_config = _STRICT_CONFIG
    id: str
    name: str
    population_share: float          # unchanged -- a fraction of the population, not a metric
    political_influence: StrictPopulationMetricBps
    approval: StrictPopulationMetricBps
    trust: StrictPopulationMetricBps
    organization: StrictPopulationMetricBps
    radicalization: StrictPopulationMetricBps
```

`population_share` stays a plain `float` in `[0, 1]` — it is a *proportion*, not one of the five
metrics this phase gives real formulas to, and converting it is out of scope (no formula in this
phase needs it in bps; `simulation.invariants`'s existing share-sums-to-1.0 check is unaffected).

New invariant (`simulation/invariants.py`): the player country must carry exactly one institution row
with `id == "military"` — `player_military_institution_required`, the coup formula's guaranteed
input. **`deficit_demo.yaml` is the scenario missing this row today** (verified directly: it authors
only an `id: executive` institution; `tiny_valid.yaml` and `decree_state.yaml` both already author
`id: executive`, `id: legislature`, and `id: military` rows) — `deficit_demo` gains a calibrated
`military` row as part of scenario calibration (§11). The redundant `id: "legislature"` row present
in `tiny_valid.yaml` and `decree_state.yaml` (POL-2's exact complaint — it duplicates
`LegislatureState`) is removed from both.

### 2.2 `PoliticalState` — five new fields (R3/R4/R6 add three beyond Revision 1's two)

```python
class PoliticalState(BaseModel):
    ...  # every existing field unchanged
    consecutive_terms_held: StrictTermsHeld
    """How many elections in a row (including the one already underway at genesis) the incumbent
    has won. Incremented on every electoral WIN that is not itself a liberalization victory (slot
    13). No "reset to 0" path exists: a loss or a term-limit exit both end the game."""

    next_election_turn: int | None
    """R4: the exact turn the next scheduled election falls on, replacing turn % interval ==
    0 arithmetic, which breaks the moment the interval changes mid-game. Required and authored at
    genesis (§2.2.1); None if and only if national_election_interval_turns is None. The sole
    writer after genesis is slot 13 (§4.4)."""

    regime_transition_pressure_bps: StrictTransitionPressureBps
    """Elevated coup risk from a recent constitutional amendment, direction-blind by construction.
    0 at genesis for every shipped scenario. Written in exactly one place, slot 12, from one
    combining formula (§4.3/§6 -- R6)."""

    pending_liberalization: PendingLiberalizationState | None = None
    """R3: explicit provenance for the liberalization-victory check. Set only when a
    ConstitutionalAmendmentDecision transitions the constitution from a qualifying noncompetitive
    shape to a qualifying competitive-elected shape (§5). A constitution that already shipped
    competitive-elected at genesis can NEVER win the liberalization victory, because this field is
    never set for it -- there is no transition to record. Cleared when the next scheduled election
    tests it (win or loss) or when a later amendment un-qualifies the constitution again."""

    terminal_outcome: TerminalOutcomeState | None = None
    """Set exactly once, by slot 12 or slot 13, and never cleared or altered afterward. None means
    the game is still being played. resolve_turn refuses to resolve any further turn once this is
    set (§6)."""
```

#### 2.2.1 Genesis authoring (all three scenarios)

| Scenario | `consecutive_terms_held` | `next_election_turn` | `regime_transition_pressure_bps` | `pending_liberalization` |
|---|---|---|---|---|
| `tiny_valid` (interval 16) | `1` | `16` | `0` | *(absent)* |
| `deficit_demo` (interval 20) | `1` | `20` | `0` | *(absent)* |
| `decree_state` (interval `None`) | `1` | `None` | `0` | *(absent)* |

`next_election_turn` is authored directly (not derived from `national_election_interval_turns` at
load time) so a future scenario is free to schedule a first election sooner or later than a full
interval after genesis (e.g. "this government's term is already three turns old") — the two fields
are validated to agree on nullness (`next_election_turn is None ⟺ national_election_interval_turns
is None`) by a new `PoliticalState` cross-validator, but not on value.

### 2.3 New enums and models

```python
class OutcomeBucket(StrEnum):
    VICTORY = "victory"
    DEFEAT = "defeat"

class RemovalReason(StrEnum):
    COUP = "coup"
    FORCED_ABDICATION = "forced_abdication"
    ASSASSINATION = "assassination"
    IMPEACHMENT = "impeachment"
    ELECTORAL_DEFEAT = "electoral_defeat"
    TERM_LIMIT_EXIT = "term_limit_exit"

class VictoryReason(StrEnum):
    PEACEFUL_LIBERALIZATION_COMPLETED = "peaceful_liberalization_completed"

class TerminalOutcomeState(BaseModel):
    model_config = _STRICT_CONFIG
    bucket: OutcomeBucket
    removal_reason: RemovalReason | None = None
    victory_reason: VictoryReason | None = None
    turn: int = Field(ge=0)

    @model_validator(mode="after")
    def _reason_matches_bucket(self) -> TerminalOutcomeState:
        if self.bucket is OutcomeBucket.VICTORY:
            if self.victory_reason is None or self.removal_reason is not None:
                raise ValueError("VICTORY requires victory_reason and forbids removal_reason")
        else:
            if self.removal_reason is None or self.victory_reason is not None:
                raise ValueError("DEFEAT requires removal_reason and forbids victory_reason")
        return self

class PendingLiberalizationState(BaseModel):
    """R3. Set by slot 2 exactly when a ConstitutionalAmendmentDecision's closing constitution
    satisfies §5's "competitive elected" shape while its OPENING constitution did not -- the
    qualifying transition. Both digests are stored (constitution_digest(), already exists) so
    reconciliation can prove the transition really happened, not merely that the field is set."""
    model_config = _STRICT_CONFIG
    set_at_turn: int = Field(ge=0)
    opening_constitution_digest: str
    closing_constitution_digest: str
```

---

### 2.4 New decision — `backend/app/simulation/decisions.py`

**R2 correction: `ConstitutionalAxisTarget` is a discriminated union of five single-purpose models,
not one model with sibling optional fields.** This makes "partially specified clearable values"
structurally impossible (each variant has exactly one `value` field, nothing to leave inconsistently
set) rather than something a validator has to police after the fact.

```python
class DecreeAuthorityTarget(BaseModel):
    model_config = _STRICT_CONFIG
    axis: Literal["decree_authority"] = "decree_authority"
    value: DecreeAuthority

class ExecutiveSystemTarget(BaseModel):
    model_config = _STRICT_CONFIG
    axis: Literal["executive_system"] = "executive_system"
    value: ExecutiveSystem

class ExecutiveSelectionTarget(BaseModel):
    model_config = _STRICT_CONFIG
    axis: Literal["executive_selection"] = "executive_selection"
    value: ExecutiveSelection

class ElectionIntervalTarget(BaseModel):
    model_config = _STRICT_CONFIG
    axis: Literal["national_election_interval_turns"] = "national_election_interval_turns"
    value: StrictTurnInterval | None
    """None explicitly means "abolish the scheduled interval" -- the field's own type already
    allows this (ConstitutionState.national_election_interval_turns is Optional), so no separate
    boolean is needed to distinguish "clear it" from "don't touch it": not including this target
    in `targets` at all IS "don't touch it"."""

class TermLimitTarget(BaseModel):
    model_config = _STRICT_CONFIG
    axis: Literal["executive_term_limit_terms"] = "executive_term_limit_terms"
    value: StrictTermCount | None   # None means "abolish the term limit", same reasoning as above

ConstitutionalAxisTarget = Annotated[
    DecreeAuthorityTarget | ExecutiveSystemTarget | ExecutiveSelectionTarget
    | ElectionIntervalTarget | TermLimitTarget,
    Field(discriminator="axis"),
]

class ConstitutionalAmendmentDecision(BaseModel):
    model_config = _STRICT_CONFIG
    kind: Literal["constitutional_amendment"] = "constitutional_amendment"
    targets: tuple[ConstitutionalAxisTarget, ...] = Field(min_length=1)
    route: ProposalRoute = ProposalRoute.LEGISLATIVE
    influence: tuple[InfluenceAllocation, ...] = ()
    """Added by the plan-only calibration below (was absent from the first draft of this model).
    `InfluenceAllocation` is reused byte-for-byte from `BudgetDecision.influence` -- same per-bloc
    `(party_id, bloc_id, political_capital)` shape, same `MAX_INFLUENCE_BPS`/
    `INFLUENCE_BPS_PER_CAPITAL` constants, same canonical-order/no-duplicate-bloc validators. See
    the FINDING below `required_amendment_yes_seats` for why this field is load-bearing, not
    optional decoration: without it, decree_state's own liberalizing amendment is mathematically
    unreachable at any legislature or capital level."""

    @model_validator(mode="after")
    def _no_duplicate_axes(self) -> ConstitutionalAmendmentDecision:
        axes = [t.axis for t in self.targets]
        if len(axes) != len(set(axes)):
            duplicates = sorted({a for a in axes if axes.count(a) > 1})
            raise ValueError(f"targets cannot name the same axis twice: {duplicates}")
        return self

    @model_validator(mode="after")
    def _targets_are_in_canonical_axis_order(self) -> ConstitutionalAmendmentDecision:
        """Reject-not-normalize, the same rule BudgetDecision.influence and
        BlocRelationshipInvestmentDecision.investments already follow. Canonical order is
        alphabetical by axis name: decree_authority < executive_selection < executive_system <
        executive_term_limit_terms < national_election_interval_turns."""
        axes = [t.axis for t in self.targets]
        if axes != sorted(axes):
            raise ValueError(f"targets must be sorted ascending by axis name, got {axes!r}")
        return self
```

`Decision: TypeAlias = Annotated[BudgetDecision | BlocRelationshipInvestmentDecision |
ConstitutionalAmendmentDecision, Field(discriminator="kind")]`. Canonical kind order
(`bloc_relationship_investment < budget < constitutional_amendment`) is already alphabetical.

**R5: `DecisionSet` gains a new cross-decision rule — at most one of `{BudgetDecision,
ConstitutionalAmendmentDecision}` per turn.** `BlocRelationshipInvestmentDecision` stays compatible
with either. This is what keeps the report design in §7 tractable: a turn's one "proposal slot" is
either a budget or an amendment, never both, so `PoliticalRelationshipReport`'s existing policy-
reaction formulas (which read `LegislativeReport`'s tax/spending direction) need no new case — a
turn spent on an amendment reports `LegislativeReport.outcome == NO_PROPOSAL` exactly like any other
no-budget turn, an outcome the engine already handles correctly today.

**Eligibility, routing, and the "changes nothing" / "final constitution invalid" checks are all
resolution-time (`phases.py` slot 1), never on the Pydantic model itself** — the decision model
cannot see `GameState`, so none of these can be construction-time checks:

- **Legislative route** requires `constitution.legislature is not Legislature.NONE`. Passage requires
  a supermajority sized by `amendment_difficulty`, via a new pure function in `legislative_voting.py`:
  `required_amendment_yes_seats(total_seats, difficulty)` — `SIMPLE_MAJORITY` reuses
  `required_yes_seats`; `SUPERMAJORITY` is `(total_seats * 2 + 2) // 3` (ceiling two-thirds);
  `ENTRENCHED` is `(total_seats * 3 + 3) // 4` (ceiling three-quarters). Bicameral passage is AND
  across chambers.
  **Bloc support formula — corrected by the plan-only calibration below.** An earlier draft of
  this plan scored amendment support on `government_relationship_bps`/`discipline_bps` alone, with
  no influence term, on the reasoning that an amendment carries no tax/spending content and
  therefore no policy-compatibility term either. That reasoning was checked by computing
  `decree_state`'s real ceiling under that literal formula: `ROLE_ANCHOR_BPS[OPPOSITION]` (2,000)
  plus the full `RELATIONSHIP_WEIGHT_BPS` swing (2,000) caps the opposition bloc's `baseline` at
  4,000 even at the maximum possible relationship (+10,000), and its authored `discipline_bps`
  (8,000) then whips a below-midpoint baseline *further down*, capping `effective_support_bps` at
  exactly **3,200** — no relationship value, however favorable, can move it past that ceiling. With
  the governing bloc already maxed at 10,000 (45 seats · 10,000 = 450,000) and the opposition
  capped at 3,200 (55 seats · 3,200 = 176,000), the reachable total is `626,000`, short of the
  `67 · 10,000 = 670,000` a `SUPERMAJORITY` passage on this 100-seat chamber requires — **strictly,
  provably unreachable**, confirmed by direct computation, not estimated. The honest fix is not a
  new mechanism: it restores the same `influence_bps`/`MAX_INFLUENCE_BPS`/`INFLUENCE_BPS_PER_CAPITAL`
  step `resolve_bloc_support` already applies for budgets, reusing every constant and function
  unchanged, and drops only `policy_compatibility_bps` (the one term with nothing to act on, since
  an amendment carries no tax/spending content). The corrected function,
  `resolve_amendment_support(role, relationship_bps, discipline_bps, allocated_political_capital)`
  in `legislative_voting.py`: `baseline = baseline_support_bps(role, relationship_bps)` (reused,
  unchanged) → `final = clamp_bps(baseline + influence_bps(allocated_political_capital))` (skips
  the `policy_compatibility_bps` term `resolve_bloc_support` would otherwise add) → `effective =
  clamp_bps(final + trunc_div_toward_zero((final - 5_000) * discipline_bps, 10_000))` (the same
  discipline step, unchanged). With this fix, 67/100 is reachable and affordable — see §11(b) for
  the complete, computed campaign.
- **Decree route** is legal only when `constitution.legislature is Legislature.NONE` *and*
  `decree_authority is UNLIMITED`. Cost: `CONSTITUTIONAL_AMENDMENT_DECREE_COST = 400` political
  capital. **No shipped scenario can exercise this route** (§0 item 10) — it exists for structural
  completeness and any future `Legislature.NONE` scenario, not for this phase's own calibration.
- A decree amendment is never legal when a legislature exists, even under `UNLIMITED` — deliberately
  out of scope (§0 item 3, §16).
- **"Targets that change nothing" are rejected atomically at resolution time**: for each target,
  compare `value` against the corresponding field on `opening_state`'s own `ConstitutionState`; if
  every target in the decision is a no-op, or if any single target is (the whole decision is
  rejected, matching `BudgetDecision`'s own "at least one target must do something" philosophy,
  applied per-target here since a partially-redundant amendment is more likely to be an authoring
  bug than a legitimate one-shot omnibus change).
- **The final constitution is validated as a whole, not axis-by-axis**: build the trial closing
  `ConstitutionState` by applying every target in the decision to the opening constitution
  simultaneously, then run the existing `first_constitutional_violation` against it. Any violation
  (C1–C10) rejects the whole decision atomically — a `DecisionSetError`, the turn aborts with no
  partial state, matching every other invalid-decision case in this codebase. This is what makes a
  five-axis, single-turn regime change (§11's `decree_state` liberalization) legal: intermediate
  single-axis states are never validated, only the final combination.
- New `CapitalExpenditureCategory` member: `CONSTITUTIONAL_AMENDMENT`, folded into the existing
  ledger's affordability guard exactly like the three existing categories.

---

## 3. The new pure module — `backend/app/simulation/government_survival.py`

Named to sit beside `political_memory.py`/`relationships.py`. **Deliberately not added to
`NEUTRAL_MODULES`.** Elections and coups are the opposite case from `NEUTRAL_MODULES`'s discipline by
design — a scheduled election only exists because of `national_election_interval_turns`, impeachment
eligibility genuinely depends on `judicial_review`/`executive_selection`. This module's own scoring
functions still accept only plain ints/enums it declares itself, never `ConstitutionState` — the
constitution is read in `phases.py`'s slot handlers, the same split `legislature.py`'s own routing
check already uses.

**R8: no float bridge of any kind.** `PopulationGroupState`'s metrics are strict bps by the time this
module ever sees them (§2.1); the population-weighted mean used by the unrest channel is plain
integer arithmetic (`trunc_div_toward_zero`) over already-bps inputs, with no rounding-mode question
to answer.

Every constant below was chosen and verified against the three shipped scenarios' real, authored
data (military institution rows, population groups, legislature seat/relationship composition,
legitimacy) by a scratch calibration script — not invented and left unverified. §11 records the
actual computed outputs.

### 3.1 Coup channel — two-stage, threshold-gated (R7: fully specified; R9: attempt+success split)

```python
BASE_COUP_ATTEMPT_RISK_BPS = 8
COUP_LOYALTY_THRESHOLD_BPS = 5_000
"""Below 50% loyalty, disloyalty starts contributing to attempt risk. At or above the threshold,
this term is exactly zero -- a threshold-gated design (not a pure linear weight) is what makes a
"stable, loyal" military (every shipped scenario authors loyalty >= 75%) contribute nothing from
this term, rather than requiring the weight itself to be hand-tuned to near-zero at 75%."""
COUP_LOYALTY_SHORTFALL_WEIGHT_BPS = 3_000
COUP_LEGITIMACY_THRESHOLD_BPS = 3_000
"""Below 30% legitimacy, a coup becomes easier to justify. At or above, zero contribution."""
COUP_LEGITIMACY_SHORTFALL_WEIGHT_BPS = 2_000
COUP_OPPOSITION_WEIGHT_BPS = 80
"""Linear, not threshold-gated -- a hostile legislature is meaningfully destabilizing at any
share, even a modest one, so there is no "safe" opposition level."""
COUP_TRANSITION_PRESSURE_WEIGHT_BPS = 1_000
MAX_COUP_ATTEMPT_RISK_BPS = 2_500

def coup_attempt_risk_bps(
    *, military_loyalty_bps: int, military_power_bps: int, legitimacy_bps: int,
    opposition_seat_share_bps: int | None, transition_pressure_bps: int,
) -> CoupAttemptRiskAssessment:
    loyalty_shortfall_bps = max(0, COUP_LOYALTY_THRESHOLD_BPS - military_loyalty_bps)
    loyalty_contribution_bps = trunc_div_toward_zero(
        trunc_div_toward_zero(loyalty_shortfall_bps * military_power_bps, BPS_DENOMINATOR)
        * COUP_LOYALTY_SHORTFALL_WEIGHT_BPS,
        BPS_DENOMINATOR,
    )
    legitimacy_shortfall_bps = max(0, COUP_LEGITIMACY_THRESHOLD_BPS - legitimacy_bps)
    legitimacy_contribution_bps = trunc_div_toward_zero(
        legitimacy_shortfall_bps * COUP_LEGITIMACY_SHORTFALL_WEIGHT_BPS, BPS_DENOMINATOR
    )
    opposition_contribution_bps = trunc_div_toward_zero(
        (opposition_seat_share_bps or 0) * COUP_OPPOSITION_WEIGHT_BPS, BPS_DENOMINATOR
    )
    pressure_contribution_bps = trunc_div_toward_zero(
        transition_pressure_bps * COUP_TRANSITION_PRESSURE_WEIGHT_BPS, BPS_DENOMINATOR
    )
    total_bps = (
        BASE_COUP_ATTEMPT_RISK_BPS + loyalty_contribution_bps + legitimacy_contribution_bps
        + opposition_contribution_bps + pressure_contribution_bps
    )
    return CoupAttemptRiskAssessment(
        loyalty_contribution_bps=loyalty_contribution_bps,
        legitimacy_contribution_bps=legitimacy_contribution_bps,
        opposition_contribution_bps=opposition_contribution_bps,
        transition_pressure_contribution_bps=pressure_contribution_bps,
        attempt_risk_bps=max(0, min(MAX_COUP_ATTEMPT_RISK_BPS, total_bps)),
    )
```

```python
COUP_SUCCESS_BASE_BPS = 500
COUP_SUCCESS_POWER_WEIGHT_BPS = 2_000
COUP_SUCCESS_COMPETENCE_WEIGHT_BPS = 1_000
COUP_SUCCESS_LEGITIMACY_DEFENSE_WEIGHT_BPS = 3_000
MAX_COUP_SUCCESS_PROBABILITY_BPS = 7_000

def coup_success_probability_bps(*, military_power_bps: int, military_competence_bps: int, legitimacy_bps: int) -> int:
    power_contribution_bps = trunc_div_toward_zero(military_power_bps * COUP_SUCCESS_POWER_WEIGHT_BPS, BPS_DENOMINATOR)
    competence_contribution_bps = trunc_div_toward_zero(military_competence_bps * COUP_SUCCESS_COMPETENCE_WEIGHT_BPS, BPS_DENOMINATOR)
    legitimacy_contribution_bps = -trunc_div_toward_zero(legitimacy_bps * COUP_SUCCESS_LEGITIMACY_DEFENSE_WEIGHT_BPS, BPS_DENOMINATOR)
    total_bps = COUP_SUCCESS_BASE_BPS + power_contribution_bps + competence_contribution_bps + legitimacy_contribution_bps
    return max(0, min(MAX_COUP_SUCCESS_PROBABILITY_BPS, total_bps))
```

Two independent RNG streams, each drawn only when reached: `ctx.rng("coup_attempt")` draws once
(`randint(1, 10_000) <= attempt_risk_bps`); only if that fires, `ctx.rng("coup_outcome")` draws once
more against `success_probability_bps`.

### 3.2 Popular-unrest channel — R9: now two-stage, matching the coup channel's shape

```python
BASE_UNREST_ATTEMPT_RISK_BPS = 15
UNREST_RADICALIZATION_THRESHOLD_BPS = 2_000    # above 20% population-weighted radicalization
UNREST_RADICALIZATION_WEIGHT_BPS = 2_500
UNREST_DISAPPROVAL_THRESHOLD_BPS = 5_500       # above 55% population-weighted disapproval
UNREST_DISAPPROVAL_WEIGHT_BPS = 1_500
MAX_UNREST_ATTEMPT_RISK_BPS = 1_500

def unrest_attempt_risk_bps(*, radicalization_bps: int, organization_bps: int, disapproval_bps: int) -> UnrestAttemptRiskAssessment:
    radicalization_excess_bps = max(0, radicalization_bps - UNREST_RADICALIZATION_THRESHOLD_BPS)
    radicalization_contribution_bps = trunc_div_toward_zero(
        trunc_div_toward_zero(radicalization_excess_bps * organization_bps, BPS_DENOMINATOR)
        * UNREST_RADICALIZATION_WEIGHT_BPS,
        BPS_DENOMINATOR,
    )
    disapproval_excess_bps = max(0, disapproval_bps - UNREST_DISAPPROVAL_THRESHOLD_BPS)
    disapproval_contribution_bps = trunc_div_toward_zero(disapproval_excess_bps * UNREST_DISAPPROVAL_WEIGHT_BPS, BPS_DENOMINATOR)
    total_bps = BASE_UNREST_ATTEMPT_RISK_BPS + radicalization_contribution_bps + disapproval_contribution_bps
    return UnrestAttemptRiskAssessment(
        radicalization_contribution_bps=radicalization_contribution_bps,
        disapproval_contribution_bps=disapproval_contribution_bps,
        attempt_risk_bps=max(0, min(MAX_UNREST_ATTEMPT_RISK_BPS, total_bps)),
    )
```

```python
UNREST_SUCCESS_BASE_BPS = 500
UNREST_SUCCESS_ORGANIZATION_WEIGHT_BPS = 3_000
UNREST_SUCCESS_LEGITIMACY_DEFENSE_WEIGHT_BPS = 3_000
MAX_UNREST_SUCCESS_PROBABILITY_BPS = 6_000
ASSASSINATION_SEVERITY_THRESHOLD_BPS = 1_500    # worst 15% of severity draws, GIVEN success

def unrest_success_probability_bps(*, organization_bps: int, legitimacy_bps: int) -> int:
    organization_contribution_bps = trunc_div_toward_zero(organization_bps * UNREST_SUCCESS_ORGANIZATION_WEIGHT_BPS, BPS_DENOMINATOR)
    legitimacy_contribution_bps = -trunc_div_toward_zero(legitimacy_bps * UNREST_SUCCESS_LEGITIMACY_DEFENSE_WEIGHT_BPS, BPS_DENOMINATOR)
    total_bps = UNREST_SUCCESS_BASE_BPS + organization_contribution_bps + legitimacy_contribution_bps
    return max(0, min(MAX_UNREST_SUCCESS_PROBABILITY_BPS, total_bps))
```

`radicalization_bps`/`organization_bps`/`disapproval_bps` are population-share-weighted means over
`opening_state`'s `PopulationGroupState` rows (already bps, R8), computed by a plain
`trunc_div_toward_zero(sum(share_i * metric_i), sum(share_i))`-shaped helper — no float involved
anywhere. `ctx.rng("unrest_attempt")` gates the attempt; if it fires, `ctx.rng("unrest_outcome")`
gates success against `unrest_success_probability_bps` — **failure means "unrest occurred but was
contained": reported, no removal.** Only on success does a third draw, `ctx.rng("unrest_severity")`,
label the outcome: `randint(1, 10_000) <= ASSASSINATION_SEVERITY_THRESHOLD_BPS` →
`RemovalReason.ASSASSINATION`; otherwise → `RemovalReason.FORCED_ABDICATION`.

### 3.3 Impeachment channel — R9: two-stage; R10: `attempted` now means "a motion was brought", not "completed"

```python
IMPEACHMENT_LEGITIMACY_THRESHOLD_BPS = 4_000    # below 40% legitimacy, impeachment becomes live
IMPEACHMENT_LEGITIMACY_SHORTFALL_WEIGHT_BPS = 2_000
IMPEACHMENT_OPPOSITION_THRESHOLD_BPS = 5_000    # opposition needs a real majority-adjacent bloc
IMPEACHMENT_OPPOSITION_WEIGHT_BPS = 1_500
IMPEACHMENT_JUDICIAL_REVIEW_SCALE_BPS = {
    JudicialReview.NONE: 0, JudicialReview.WEAK: 5_000, JudicialReview.STRONG: 10_000,
}
MAX_IMPEACHMENT_ATTEMPT_RISK_BPS = 1_200

def impeachment_attempt_risk_bps(*, opposition_seat_share_bps: int, legitimacy_bps: int, judicial_review: JudicialReview) -> ImpeachmentAttemptRiskAssessment:
    scale_bps = IMPEACHMENT_JUDICIAL_REVIEW_SCALE_BPS[judicial_review]
    legitimacy_shortfall_bps = max(0, IMPEACHMENT_LEGITIMACY_THRESHOLD_BPS - legitimacy_bps)
    legitimacy_contribution_bps = trunc_div_toward_zero(
        trunc_div_toward_zero(legitimacy_shortfall_bps * IMPEACHMENT_LEGITIMACY_SHORTFALL_WEIGHT_BPS, BPS_DENOMINATOR) * scale_bps,
        BPS_DENOMINATOR,
    )
    opposition_excess_bps = max(0, opposition_seat_share_bps - IMPEACHMENT_OPPOSITION_THRESHOLD_BPS)
    opposition_contribution_bps = trunc_div_toward_zero(
        trunc_div_toward_zero(opposition_excess_bps * IMPEACHMENT_OPPOSITION_WEIGHT_BPS, BPS_DENOMINATOR) * scale_bps,
        BPS_DENOMINATOR,
    )
    total_bps = legitimacy_contribution_bps + opposition_contribution_bps
    return ImpeachmentAttemptRiskAssessment(
        legitimacy_contribution_bps=legitimacy_contribution_bps,
        opposition_contribution_bps=opposition_contribution_bps,
        attempt_risk_bps=max(0, min(MAX_IMPEACHMENT_ATTEMPT_RISK_BPS, total_bps)),
    )
```

```python
IMPEACHMENT_SUCCESS_BASE_BPS = 500
IMPEACHMENT_SUCCESS_OPPOSITION_WEIGHT_BPS = 4_000
IMPEACHMENT_SUCCESS_LEGITIMACY_DEFENSE_WEIGHT_BPS = 3_000
MAX_IMPEACHMENT_SUCCESS_PROBABILITY_BPS = 6_000

def impeachment_success_probability_bps(*, opposition_seat_share_bps: int, legitimacy_bps: int) -> int:
    opposition_contribution_bps = trunc_div_toward_zero(opposition_seat_share_bps * IMPEACHMENT_SUCCESS_OPPOSITION_WEIGHT_BPS, BPS_DENOMINATOR)
    legitimacy_contribution_bps = -trunc_div_toward_zero(legitimacy_bps * IMPEACHMENT_SUCCESS_LEGITIMACY_DEFENSE_WEIGHT_BPS, BPS_DENOMINATOR)
    total_bps = IMPEACHMENT_SUCCESS_BASE_BPS + opposition_contribution_bps + legitimacy_contribution_bps
    return max(0, min(MAX_IMPEACHMENT_SUCCESS_PROBABILITY_BPS, total_bps))
```

**Eligibility** (checked in `phases.py`, not this module): `legislature is not Legislature.NONE` and
`judicial_review is not JudicialReview.NONE` and `executive_selection is not
ExecutiveSelection.HEREDITARY`. An ineligible turn skips the channel entirely; the report still
records `eligible=False`. `ctx.rng("impeachment_attempt")` gates the motion; if it fires,
`ctx.rng("impeachment_outcome")` gates `succeeded` against `impeachment_success_probability_bps` —
**a motion that fails is reported (`attempted=True, succeeded=False`) with no removal**, closing
R10's naming concern: `attempted` now means only "a motion was brought," never "completed removal."

### 3.4 Election channel — R7: fully specified; R10: exact seat counts, not independently-rounded shares

```python
REQUIRED_ELECTION_SUPPORT_BPS = 5_000
LEGISLATIVE_SUPPORT_WEIGHT_BPS = 5_000
POPULATION_APPROVAL_WEIGHT_BPS = 4_000
LEGITIMACY_WEIGHT_BPS = 1_000
MAX_POLLING_UNCERTAINTY_SWING_BPS = 1_000       # +/- 10 percentage points

def legislative_support_bps(*, bloc_seats_and_relationships: tuple[tuple[int, int], ...], total_seats: int) -> int:
    """(seats, government_relationship_bps) pairs across every bloc in every chamber -- reads
    exact seat counts, never a party's own already-rounded seat-share. Each bloc's relationship is
    rescaled from [-10,000, +10,000] to a [0, 10,000] support contribution
    ((relationship_bps + 10_000) // 2, truncating toward zero via trunc_div_toward_zero on the sum
    identity below, never per-bloc), then seat-weighted."""
    weighted_sum = sum(
        seats * trunc_div_toward_zero(relationship_bps + BPS_DENOMINATOR, 2)
        for seats, relationship_bps in bloc_seats_and_relationships
    )
    return trunc_div_toward_zero(weighted_sum, total_seats)

def election_baseline_support_bps(*, legislative_support_bps: int | None, population_approval_bps: int, legitimacy_bps: int) -> ElectionSupportAssessment:
    if legislative_support_bps is None:
        # renormalize over the two remaining signals -- never fabricates a legislature that
        # doesn't exist. No shipped scenario exercises this branch (all three have a legislature).
        weighted_sum = population_approval_bps * (POPULATION_APPROVAL_WEIGHT_BPS + LEGISLATIVE_SUPPORT_WEIGHT_BPS) \
            + legitimacy_bps * LEGITIMACY_WEIGHT_BPS
        denominator = POPULATION_APPROVAL_WEIGHT_BPS + LEGISLATIVE_SUPPORT_WEIGHT_BPS + LEGITIMACY_WEIGHT_BPS
    else:
        weighted_sum = (
            legislative_support_bps * LEGISLATIVE_SUPPORT_WEIGHT_BPS
            + population_approval_bps * POPULATION_APPROVAL_WEIGHT_BPS
            + legitimacy_bps * LEGITIMACY_WEIGHT_BPS
        )
        denominator = LEGISLATIVE_SUPPORT_WEIGHT_BPS + POPULATION_APPROVAL_WEIGHT_BPS + LEGITIMACY_WEIGHT_BPS
    baseline_bps = trunc_div_toward_zero(weighted_sum, denominator)
    return ElectionSupportAssessment(..., baseline_support_bps=baseline_bps)
```

`ctx.rng("election")` draws a signed swing uniformly in `[-MAX_POLLING_UNCERTAINTY_SWING_BPS,
+MAX_POLLING_UNCERTAINTY_SWING_BPS]`, applied once: `final_support_bps = clamp(baseline_support_bps +
swing, 0, 10_000)`. `WON` iff `final_support_bps >= REQUIRED_ELECTION_SUPPORT_BPS`.

### 3.5 Transition pressure — R6: one combining function, one identity, used everywhere

```python
TRANSITION_PRESSURE_DECAY_NUMERATOR = 1
TRANSITION_PRESSURE_DECAY_DENOMINATOR = 6
AMENDMENT_PRESSURE_PER_AXIS_BY_DIFFICULTY_BPS = {
    AmendmentDifficulty.SIMPLE_MAJORITY: 1_500,
    AmendmentDifficulty.SUPERMAJORITY: 2_500,
    AmendmentDifficulty.ENTRENCHED: 4_000,
}

def transition_pressure_added_bps(*, difficulty: AmendmentDifficulty, axes_changed: int) -> int:
    """axes_changed in [1, 5] (five amendable axes, §2.4/§0 item 9) scales the added pressure
    linearly. Direction-blind by construction: never reads which way any axis moved, only that it
    moved and by how much of the difficulty-scaled per-axis unit -- the literal mechanism making
    liberalization and consolidation cost-symmetric."""
    return min(BPS_DENOMINATOR, AMENDMENT_PRESSURE_PER_AXIS_BY_DIFFICULTY_BPS[difficulty] * axes_changed)

def resolve_transition_pressure_bps(*, opening_pressure_bps: int, amendment_added_bps: int) -> TransitionPressureResolution:
    """The ONE place regime_transition_pressure_bps is ever computed -- called once, from slot 12,
    reading the turn's OPENING pressure value and (if a ConstitutionalAmendmentDecision passed or
    was decreed this turn) its added-pressure amount. Never split across two phase steps."""
    decay_bps = _transition_pressure_decay_magnitude_bps(opening_pressure_bps)  # min-1-step, no-overshoot, toward zero
    uncapped_bps = opening_pressure_bps - decay_bps + amendment_added_bps
    closing_bps = max(0, min(BPS_DENOMINATOR, uncapped_bps))
    return TransitionPressureResolution(
        opening_bps=opening_pressure_bps, decayed_bps=decay_bps, added_bps=amendment_added_bps,
        uncapped_bps=uncapped_bps, closing_bps=closing_bps,
    )
```

`_transition_pressure_decay_magnitude_bps` has the identical shape to `political_memory.py`'s
`relationship_decay_bps` (proportional 1/6, minimum one-bps step so a small residual still
terminates, no overshoot) — deliberately faster than relationship decay's 1/8, since a constitutional
shock is meant to fade within about a year and a half of turns, not linger as long as a bloc's
personal grudge.

---

## 4. Phase-slot design — `backend/app/simulation/phases.py`

No 16th slot. Both reserved no-ops are replaced with real handlers, in their existing position.

**R7 ordering clarification (this is a real correction, not a restatement): slots 12 and 13 read
legitimacy and legislature/relationship data as they stand AFTER slots 10 and 11 have already run
this same turn — the CLOSING values for this turn, not a pre-turn opening snapshot.** There is no
structural reason for coup/unrest/impeachment/election risk to lag behind this turn's own legitimacy
change or this turn's own relationship decay; the one-turn-delay rule that genuinely exists elsewhere
(slot 1 scoring the budget vote against the *opening* relationship, so this turn's investment cannot
buy the vote it is used in) has no analogue here — nothing in slot 12/13 can retroactively "spend"
this turn's own legitimacy resolution to cheapen itself, so reading it live introduces no similar
loophole. Concretely: `ctx.state.politics.legitimacy_bps` and `ctx.state.politics.legislature` are
read as `ctx.state` stands when slot 12/13 execute, which is after slots 1–11 have already mutated it
this turn. `InstitutionState`/`PopulationGroupState` are untouched by every slot before 12 in this
phase, so reading them at slot 12/13 is equivalent to reading them from either the turn's opening or
closing state — reconciliation (§8) exploits this explicitly.

### 4.1 Slot 12 — `evaluate_protests_strikes_insurgency_coups_revolutions` → `_evaluate_unrest_and_coup_risk`

1. Defensive assertion: `politics.terminal_outcome is None` (structurally unreachable, since
   `resolve_turn` already refused at the top — kept explicit).
2. Read `ctx.state`'s *current* (post-slot-11) legitimacy, legislature/relationships, institutions,
   and population groups.
3. **Resolve `regime_transition_pressure_bps`** via `resolve_transition_pressure_bps`, reading this
   turn's *opening* pressure value (captured once, at the very start of `resolve_turn`, before any
   slot runs — the same `OpeningPoliticalSnapshot`-style capture every other opening-value read in
   this codebase already uses) and, if a `ConstitutionalAmendmentDecision` passed/was decreed this
   turn, `transition_pressure_added_bps(...)` computed from the real decision and the *opening*
   constitution's `amendment_difficulty`. This is the single write site R6 requires.
4. Compute all **three** channel risk assessments — pure, no RNG yet, always done, always reported.
5. Evaluate channels **in fixed priority order — coup, then popular unrest, then impeachment.** Every
   channel's RNG draw(s) always happen regardless of whether an earlier channel already produced a
   removal this turn — **a later channel's draw sequence must never depend on whether an earlier
   channel fired.** Only the first channel (in priority order) to produce a removal writes
   `politics.terminal_outcome`; later channels' outcomes are still computed and still reported.
6. If any channel produced a removal: write `politics.terminal_outcome` (bucket=DEFEAT, the matching
   `RemovalReason`, `turn=ctx.state.turn`).
7. Build the slot's scratch data, wrapped into `CoupUnrestReport` at slot 15.

### 4.2 Slot 13 — `evaluate_elections_and_constitutional_events` → `_evaluate_elections`

1. **First line: if `politics.terminal_outcome is not None` (set by slot 12 this same turn), build an
   all-`not_scheduled` inert `ElectionReport` and return immediately.**
2. Otherwise: `scheduled = (politics.next_election_turn == ctx.state.turn)` — replaces the old
   modulo check entirely (R4; §4.4 gives the exact scheduling-update rules).
3. If not scheduled: build an inert report, done.
4. If scheduled: check `consecutive_terms_held >= executive_term_limit_terms` (only when a limit is
   authored) → `RemovalReason.TERM_LIMIT_EXIT`, **no RNG consumed** — a term limit is a hard
   constitutional fact, checked using the value as of entering this election, before any win
   increment.
5. Otherwise: compute `election_baseline_support_bps` (reading this turn's *current*,
   post-slot-11 legislature and legitimacy, per the R7 ordering fix), draw the polling swing
   (`ctx.rng("election")`), compute `final_support_bps`, compare to `REQUIRED_ELECTION_SUPPORT_BPS`.
   - **Win:** `consecutive_terms_held += 1`; reschedule `next_election_turn = ctx.state.turn +
     national_election_interval_turns` (§4.4); check the liberalization-victory condition (§5) — if
     `politics.pending_liberalization is not None` and this win satisfies it, set `terminal_outcome`
     (VICTORY, `PEACEFUL_LIBERALIZATION_COMPLETED`) and clear `pending_liberalization`; otherwise the
     game continues (CONTINUING — `terminal_outcome` stays `None`, `pending_liberalization` stays
     whatever it was, which by construction can only be `None` here, since a set-and-untested pending
     state is always cleared by the very next scheduled election one way or the other).
   - **Loss:** `terminal_outcome` set (DEFEAT, `ELECTORAL_DEFEAT`); `pending_liberalization` cleared
     (moot — the game has ended, but cleared for a tidy closing state rather than left stale).
6. Build `ElectionReport` from the validated, already-computed values.

### 4.3 Where `ConstitutionalAmendmentDecision` is actually handled

Entirely in **slot 1** (routing, voting — via the new `resolve_amendment_support`/
`required_amendment_yes_seats`) and **slot 2** (commit) — never in slots 12/13, which only ever
*read* the constitution:

- Slot 2, on `PASSED_LEGISLATIVE`/decree success: writes the new `ConstitutionState` to
  `player.politics.constitution`; if the qualifying-transition test (§5) holds between the *opening*
  and this new closing constitution, sets `politics.pending_liberalization`; if a
  `pending_liberalization` was already set from an earlier turn and this new closing constitution no
  longer satisfies the "competitive elected" shape, clears it (a reversed liberalization must be
  re-earned by a fresh qualifying transition, not silently grandfathered in). **Slot 2 does *not*
  touch `regime_transition_pressure_bps` at all** (R6) — only slot 12 ever writes that field, reading
  whatever amendment happened this turn via the real `DecisionSet`, exactly as reconciliation will
  (§8).
- `ConstitutionalAmendmentReport` (§7.2) is assembled at slot 15 from slot 1's chamber-tally scratch
  and slot 2's commit outcome, mirroring `LegislativeReport`'s own assembly split.

### 4.4 `next_election_turn` — exact scheduling rules (R4)

| Event | Rule |
|---|---|
| Genesis | Authored directly (§2.2.1) — not derived. |
| An election resolves as a WIN (CONTINUING, not liberalization victory) | `next_election_turn = closing_turn + national_election_interval_turns`, using whichever interval is active in the closing constitution *this same turn* (normally unchanged, unless an amendment also landed this turn — see below). |
| An election resolves as a LOSS, TERM_LIMIT_EXIT, or a liberalization VICTORY | The game has ended; `next_election_turn` is left unchanged (frozen, like `regime_transition_pressure_bps` on removal) — never read again. |
| A `ConstitutionalAmendmentDecision` sets `national_election_interval_turns` to a new non-`None` value X (whether previously `None` or a different value) | `next_election_turn = closing_turn + X` — always exactly X turns from the moment of the change, discarding any prior schedule. Applies uniformly whether this is the first interval ever authored (`decree_state`'s liberalization) or a change to an already-scheduled one. |
| A `ConstitutionalAmendmentDecision` clears `national_election_interval_turns` to `None` | `next_election_turn = None` — no further elections are scheduled unless a future amendment re-establishes an interval. |
| No amendment touches the interval, and no election was scheduled this turn | `next_election_turn` unchanged. |

**Same-turn amendment/election collision is structurally impossible, not merely avoided by
convention**: `StrictTurnInterval` requires `> 0`, so `next_election_turn = closing_turn + X` is
always strictly greater than `closing_turn` whenever a reschedule happens — the turn an interval is
*set* can never simultaneously be the turn its first election falls on. (A *pre-existing* scheduled
election milestone happening to coincide with an unrelated amendment in the same turn is not a
collision at all — slot 1/2 run before slot 12/13, so the amendment's effects, if any, are already
committed by the time the pre-scheduled election evaluates.)

---

## 5. Victory condition — exact, checkable, with real provenance (R3)

**Step 1 — the qualifying transition (checked in slot 2, on every amendment that passes/is
decreed).** A constitution is **noncompetitive** if `executive_selection` is `HEREDITARY` or
`APPOINTED`, or `decree_authority` is not `NONE` (i.e., the executive is not genuinely competitively
chosen, or decree power still allows bypassing the legislature). A constitution is **competitive
elected** if `executive_selection` is `DIRECT_ELECTION` or `LEGISLATIVE_SELECTION`, *and*
`decree_authority is NONE`, *and* `national_election_interval_turns is not None`. The **qualifying
transition** is: the amendment's *opening* constitution was noncompetitive, and its *closing*
constitution is competitive elected. When it holds, slot 2 sets
`politics.pending_liberalization = PendingLiberalizationState(set_at_turn=ctx.state.turn,
opening_constitution_digest=constitution_digest(opening), closing_constitution_digest=
constitution_digest(closing))`.

**Step 2 — the test (checked in slot 13, at the next scheduled election).**
`PEACEFUL_LIBERALIZATION_COMPLETED` holds if and only if, at the close of a scheduled election:

1. `politics.pending_liberalization is not None` (set by step 1, at some earlier turn, and never
   cleared since — this is the provenance check itself: a constitution that shipped
   competitive-elected at genesis, or reached that shape by any path other than a qualifying
   in-play transition, can never have this field set, and therefore can never win).
2. The election just resolved is `WON` by the incumbent.

That is the entire condition — steps 1 and 2 together are strictly stronger than a snapshot-only
check would be, because step 1 can only ever become true from a real, resolved amendment turn,
never from a scenario's genesis authoring. **A starting democracy (any scenario whose constitution
ships already competitive-elected) can win ordinary elections forever — a CONTINUING outcome each
time — but can never win the *liberalization* victory, because `pending_liberalization` is never set
for it.** This is intentionally strict in the other direction too: liberalizing and then losing the
*very next* free election is `ELECTORAL_DEFEAT`, a normal DEFEAT, not a softened outcome — democracy
is not scored as safer, it is scored as surviving its own first real test, using the exact same
election-result formula that decides every other government's fate.

**Reversal**: if a later amendment (before the pending test is ever reached) moves the constitution
back out of "competitive elected" shape, `pending_liberalization` is cleared (§4.3) — a reversed
liberalization must be re-earned by a fresh qualifying transition, never grandfathered.

---

## 6. The removal mechanism

`PoliticalState.terminal_outcome: TerminalOutcomeState | None` lives in hash-chained `state_json` —
no `GameSave`-envelope change of any kind.

```python
def resolve_turn(state: GameState, decisions: DecisionSet) -> TurnResolution:
    player = state.world.countries[state.world.player_country_id]
    if player.politics is not None and player.politics.terminal_outcome is not None:
        raise GameAlreadyConcludedError(player.politics.terminal_outcome)
    ...  # existing body unchanged from here
```

```python
class GameAlreadyConcludedError(MandateError):
    def __init__(self, outcome: TerminalOutcomeState) -> None:
        self.outcome = outcome
        reason = (outcome.victory_reason or outcome.removal_reason).value
        super().__init__(
            f"the game concluded at turn {outcome.turn} ({outcome.bucket.value}: {reason}); "
            "no further turn can be resolved. Nothing was modified."
        )
```

**New `validate_history` guard**, closing the "hand-crafted save smuggling extra turns" gap
`resolve_turn`'s own refusal cannot reach:

```python
concluded_at: int | None = None
for index, entry in enumerate(save.entries):
    ...  # existing per-entry checks
    if concluded_at is not None:
        problems.append(
            f"turn {entry.turn}: entry exists after the game concluded at turn {concluded_at}; "
            "a concluded game cannot be advanced further, and a genuine save could never contain "
            "entries after that turn"
        )
    if state_model is not None:
        player = state_model.world.countries[state_model.world.player_country_id]
        if (player.politics is not None and player.politics.terminal_outcome is not None
                and concluded_at is None):
            concluded_at = entry.turn
```

Deliberately a *second*, independent guard from `resolve_turn`'s refusal: one prevents advancing a
concluded save through the CLI; this one catches a save hand-assembled with post-conclusion entries
present from the start.

**R10 — CLI multi-turn behavior, defined precisely** (§9 restates this at the CLI layer): if
`resolve --turns N` concludes the game partway through (turn K < N), the loop stops *after* turn K,
the save is written normally with the concluded state as its last entry, and the command **exits 0
(success)** with a message noting the game ended at turn K of the N requested — this is not an error,
it is the loop doing exactly what it should the moment `terminal_outcome` is set. A **separate,
subsequent** invocation of `resolve` against that already-concluded save is the atomic-refusal case:
`GameAlreadyConcludedError`, exit 1, no output file, input byte-identical before and after.

---

## 7. New reports — `backend/app/simulation/report.py`

### 7.1 `CoupUnrestReport` — `TurnReport`'s 10th report

```python
class CoupChannelReport(BaseModel):
    model_config = _STRICT_CONFIG
    military_loyalty_bps: StrictInstitutionMetricBps
    military_power_bps: StrictInstitutionMetricBps
    military_competence_bps: StrictInstitutionMetricBps
    loyalty_contribution_bps: StrictSignedRiskContributionBps
    legitimacy_contribution_bps: StrictSignedRiskContributionBps
    opposition_contribution_bps: StrictSignedRiskContributionBps
    transition_pressure_contribution_bps: StrictSignedRiskContributionBps
    attempt_risk_bps: StrictRiskBps
    attempted: bool
    success_probability_bps: StrictRiskBps | None = None
    succeeded: bool | None = None
    # self-validators: (1) attempt_risk_bps re-sums+clamps the four named contributions; (2)
    # success_probability_bps/succeeded both None iff attempted is False, both present otherwise --
    # R10: success_probability_bps is re-derived HERE from military_power/competence/legitimacy,
    # independently of whatever RNG draw succeeded/attempted represent, not merely assumed.

class PopularUnrestChannelReport(BaseModel):
    model_config = _STRICT_CONFIG
    radicalization_bps: StrictPopulationMetricBps
    organization_bps: StrictPopulationMetricBps
    disapproval_bps: StrictPopulationMetricBps
    radicalization_contribution_bps: StrictSignedRiskContributionBps
    disapproval_contribution_bps: StrictSignedRiskContributionBps
    attempt_risk_bps: StrictRiskBps
    attempted: bool
    success_probability_bps: StrictRiskBps | None = None
    succeeded: bool | None = None
    outcome: Literal["none", "contained", "forced_abdication", "assassination"]
    # "contained" = attempted, succeeded=False. "none" = not attempted at all.

class ImpeachmentChannelReport(BaseModel):
    model_config = _STRICT_CONFIG
    eligible: bool
    legitimacy_contribution_bps: StrictSignedRiskContributionBps | None = None
    opposition_contribution_bps: StrictSignedRiskContributionBps | None = None
    attempt_risk_bps: StrictRiskBps | None = None
    attempted: bool | None = None
    success_probability_bps: StrictRiskBps | None = None
    succeeded: bool | None = None
    # every Optional field is None together iff eligible is False.

class CoupUnrestReport(BaseModel):
    model_config = _STRICT_CONFIG
    coup: CoupChannelReport
    popular_unrest: PopularUnrestChannelReport
    impeachment: ImpeachmentChannelReport
    removal_triggered: RemovalReason | None
    opening_transition_pressure_bps: StrictTransitionPressureBps
    decayed_transition_pressure_bps: StrictTransitionPressureBps
    added_transition_pressure_bps: StrictTransitionPressureBps
    closing_transition_pressure_bps: StrictTransitionPressureBps
    # self-validators: removal_triggered matches the coup-then-unrest-then-impeachment priority
    # order (re-derived from the three channels' own succeeded fields, never trusted independently);
    # closing_transition_pressure_bps == opening - decayed + added, clamped (R6's one identity,
    # re-checked here as the report's own arithmetic guarantee, independent of reconciliation).
```

### 7.2 `ConstitutionalAmendmentReport` — `TurnReport`'s 11th report (R5)

```python
class ConstitutionalAmendmentTargetReport(BaseModel):
    model_config = _STRICT_CONFIG
    axis: str
    opening_value: str    # str() of whichever enum/int/None the axis held
    closing_value: str

class ConstitutionalAmendmentReport(BaseModel):
    model_config = _STRICT_CONFIG
    proposed: bool
    route: ProposalRoute | None = None
    targets: tuple[ConstitutionalAmendmentTargetReport, ...] = ()
    amendment_decision_digest: str | None = None
    chambers: tuple[ChamberVoteReport, ...] = ()    # reuses the existing model verbatim
    influence: tuple[InfluenceAllocation, ...] = ()  # mirrors LegislativeReport's own influence rows
    political_capital_committed: StrictPoliticalCapital = 0
    outcome: Literal["no_proposal", "passed_legislative", "failed_legislative", "enacted_by_decree"]
    opening_constitution_digest: str
    closing_constitution_digest: str
    transition_pressure_added_bps: StrictTransitionPressureBps
    qualifies_as_liberalization_transition: bool
    # self-validators: outcome derived from chamber tallies exactly like LegislativeReport's own
    # outcome validator; closing_constitution_digest == opening_constitution_digest UNLESS outcome
    # is passed_legislative or enacted_by_decree; transition_pressure_added_bps re-derived from
    # targets' own count and (implicitly) the route/outcome; qualifies_as_liberalization_transition
    # re-derived from §5's exact rule applied to the two stored digests' underlying axis values
    # (the report stores the axis-by-axis targets, which is enough to re-check the noncompetitive
    # -> competitive-elected shape without needing the full ConstitutionState);
    # political_capital_committed == sum(row.political_capital for row in influence) on the
    # legislative route (mirrors PoliticalCapitalReport's own expenditure-row identity), or the
    # flat CONSTITUTIONAL_AMENDMENT_DECREE_COST on the decree route with influence == ().
```

**Why Option B (a dedicated report), not Option A (generalizing `LegislativeReport` into a proposal
union):** `LegislativeReport` is deeply load-bearing for `PoliticalRelationshipReport`'s policy-
reaction cross-validators (tax/spending direction and intensity, read every turn regardless of
outcome). Generalizing it into a union would touch every one of those validators, plus every existing
test that constructs a `LegislativeReport` literal, for a proposal kind (constitutional amendments)
that carries no tax/spending content at all and therefore does not need any of that machinery. A
dedicated report keeps the two proposal kinds' reporting fully independent, at the cost of one more
top-level report — the same trade `PoliticalRelationshipReport` itself already made against
`PoliticalCapitalReport` in Phase 3B2B, for the same reason (a shared field that would mean two
different things is worse than two separate, single-purpose fields).

### 7.3 `TurnReport` changes

- Three new `X | None` fields — `coup_unrest`, `election`, `constitutional_amendment` — join the
  existing nine in the all-present-or-all-absent validator (9 → 12 booleans; message text and
  validator name updated to name all three).
- **No `TurnReport`-level cross-validator compares `ElectionReport.parties` against
  `LegislativeReport` (R10 correction).** `LegislativeReport.blocs`
  can be genuinely empty/absent on a `NO_PROPOSAL` turn, which is common (most turns carry no budget
  proposal at all), so cross-checking against it would spuriously fail on exactly those turns. Party
  election-stance data is instead reconciled directly against `closing_state.politics.legislature` by
  party/bloc identity — a **reconciliation** group (§8), not a report-internal cross-validator, since
  it needs `GameState`, which no report can see on its own.
- `ElectionReport.parties` itself (§7.4) now carries exact `seats`/`total_seats` integers, never an
  independently-rounded `seat_share_bps` (R10).

### 7.4 `ElectionReport` — `TurnReport`'s 12th report

```python
class PartyElectionStanceReport(BaseModel):
    model_config = _STRICT_CONFIG
    party_id: str
    government_role: GovernmentRole
    seats: int = Field(ge=0)
    total_seats: int = Field(gt=0)
    relationship_weighted_support_bps: StrictRiskBps

class ElectionReport(BaseModel):
    model_config = _STRICT_CONFIG
    scheduled: bool
    eligible_to_stand: bool
    consecutive_terms_held: StrictTermsHeld
    executive_term_limit_terms: StrictTermCount | None
    legislative_support_contribution_bps: StrictRiskBps | None
    population_approval_contribution_bps: StrictRiskBps
    legitimacy_contribution_bps: StrictRiskBps
    baseline_support_bps: StrictRiskBps
    polling_uncertainty_bps: int             # signed, [-MAX_SWING, +MAX_SWING]
    final_support_bps: StrictRiskBps
    required_support_bps: StrictRiskBps
    result: Literal["not_scheduled", "term_limit_exit", "won", "lost"]
    liberalization_completed: bool
    next_election_turn: int | None           # closing value, after this turn's reschedule (if any)
    parties: tuple[PartyElectionStanceReport, ...]
    # self-validators: final_support == clamp(baseline + swing); result matches support/term-limit
    # exactly; liberalization_completed implies result == "won"; parties nonempty only when
    # scheduled and a legislature exists, and sum(seats) == total_seats for every row consistently.
```

---

## 8. Reconciliation — new groups 24–39 (`backend/app/simulation/reconciliation.py`)

All added to the single reconciliation function (renamed, in this phase, to
`reconcile_political_legislative_and_survival_report` — every call site updated in its own isolated
step within the same commit). **R7 note applied throughout the table below**: any check that needs
"this turn's legitimacy" or "this turn's legislature/relationships" reads `closing_state` (since
nothing after slot 11 changes those two things, `closing_state`'s values are provably identical to
what slot 12/13 actually read at runtime); any check needing pre-turn data (the opening pressure value
transition-pressure decay is computed from) reads `opening_state`.

| Group | Proves |
|---|---|
| 24 | Coup channel's `attempt_risk_bps` and every named contribution re-derived from `closing_state`'s own military institution row, legislature (opposition seat share), legitimacy, and the report's own `opening_transition_pressure_bps` — compared field by field. |
| 25 | Coup `success_probability_bps` re-derived independently from `closing_state`'s military power/competence/legitimacy (R10 — not merely the RNG draw). |
| 26 | Coup RNG-draw recompute: `derive_rng(opening_state.seed, resolving_turn, "coup_attempt")` redrawn and compared to `attempted`; if attempted, `derive_rng(..., "coup_outcome")` redrawn and compared to `succeeded`. |
| 27 | Popular-unrest attempt-risk recompute (mirrors 24), reading `closing_state`'s population groups. |
| 28 | Popular-unrest `success_probability_bps` recompute (mirrors 25). |
| 29 | Popular-unrest RNG-draw recompute (mirrors 26), plus the severity draw when successful. |
| 30 | Impeachment eligibility recompute (`legislature != NONE`, `judicial_review != NONE`, `executive_selection != HEREDITARY`, from `closing_state.politics.constitution`); when eligible, attempt-risk recompute. |
| 31 | Impeachment `success_probability_bps` recompute (mirrors 25/28). |
| 32 | Impeachment RNG-draw recompute (mirrors 26/29). |
| 33 | `removal_triggered` (report) vs `closing_state.politics.terminal_outcome.removal_reason` (state) — exact match, including both-`None`. |
| 34 | Transition-pressure identity recompute (R6): `closing_transition_pressure_bps == max(0, min(10_000, opening - decay(opening) + added))`, where `added` is re-derived from the real `DecisionSet` (a `ConstitutionalAmendmentReport` with `outcome` in `{passed_legislative, enacted_by_decree}` this turn) and `opening_state`'s own `amendment_difficulty` — never from report prose. |
| 35 | Election-scheduling recompute: `scheduled` vs `opening_state.politics.next_election_turn == closing_state.turn`; `next_election_turn`'s new (or unchanged) value re-derived per §4.4's exact table. |
| 36 | Election term-limit recompute: `eligible_to_stand`/`result == "term_limit_exit"` vs `opening_state`'s own `consecutive_terms_held`/`executive_term_limit_terms`. |
| 37 | Election support-score recompute: `legislative_support_contribution_bps`/`population_approval_contribution_bps`/`legitimacy_contribution_bps` re-derived from `closing_state` (seat-and-relationship-weighted legislature, population-approval mean, legitimacy), matched against the report. |
| 38 | Election RNG-draw recompute: `derive_rng(opening_state.seed, resolving_turn, "election")` redrawn, compared to `polling_uncertainty_bps`. |
| 39 | Election result vs closing state: `result == "won"` implies `closing_state.consecutive_terms_held == opening_state.consecutive_terms_held + 1` (and either no `terminal_outcome`, or VICTORY if liberalization just completed); `result in ("lost", "term_limit_exit")` implies `closing_state.politics.terminal_outcome.removal_reason` matches exactly. |
| 40 | `ElectionReport.parties` vs `closing_state.politics.legislature` by `(party_id)` identity — exact seats/total_seats match, **read from state directly, never from `LegislativeReport`** (R10 — the bug an earlier draft's design would have introduced). |
| 41 | `pending_liberalization` state-to-state (R3): set only on a turn whose real `ConstitutionalAmendmentReport` shows a qualifying transition (§5 step 1, re-derived from the report's own stored targets against `opening_state`'s constitution); cleared only on a turn that either tests it via a scheduled election (win or loss) or un-qualifies it via a later amendment; otherwise unchanged. |
| 42 | Liberalization-victory provenance (R3's core guarantee): `election.liberalization_completed` implies `opening_state.politics.pending_liberalization is not None` — **the check that makes a starting-democracy exploit structurally impossible to fabricate**, since `opening_state` is real, persisted, hash-chained history, not a value a tampered report can assert about itself. |
| 43 | `ConstitutionalAmendmentReport`'s digest, chamber tallies, and political-capital commitment recomputed against the **real submitted `ConstitutionalAmendmentDecision`** (mirroring group 18's "against the actual decision, never report prose" discipline for the budget) and `opening_state`'s legislature. |
| 44 | Constitution-axis staticness, extended: the three never-amendable axes (`territorial_organization`, `judicial_review`, `amendment_difficulty`) are byte-identical opening/closing on every turn; the five amendable axes may differ only when a `ConstitutionalAmendmentDecision` was actually submitted, and its targets — matched by axis name against the real `DecisionSet` — exactly explain the observed diff. |
| 45 | Terminal-outcome non-retroactivity: `opening_state.politics.terminal_outcome` must be `None` on every turn reconciliation is asked to check at all — the redundant, independently-checkable backstop for the guarantee `resolve_turn`'s own top-of-function refusal already promises. |

### 8.1 New tamper-matrix cases (extending ADR 0012's §10.1 table)

| # | Tampered | Caught by |
|---|---|---|
| 19 | `CoupChannelReport.attempt_risk_bps`, internally consistent with its own named contributions | group 24 |
| 20 | Coup `success_probability_bps` recomputed to a different, still-internally-consistent value | group 25 |
| 21 | Coup RNG outcome (`attempted`/`succeeded`) flipped, contributions left untouched | group 26 |
| 22 | `removal_triggered` claimed absent while `closing_state.terminal_outcome` is actually set (or the reverse) | group 33 |
| 23 | `regime_transition_pressure_bps` left unchanged on a turn that actually amended the constitution | group 34 |
| 24 | `election.scheduled`/`next_election_turn` fabricated inconsistent with the real prior schedule | group 35 |
| 25 | `election.result == "won"` with `closing_state.consecutive_terms_held` left unincremented | group 39 |
| 26 | `election.parties` seat counts diverging from the real, untouched legislature | group 40 |
| 27 | **The starting-democracy exploit case R3 exists to close**: a fresh save whose constitution ships already competitive-elected, with a fabricated `election.liberalization_completed=True` and a fabricated `pending_liberalization` state, both internally self-consistent — caught only by group 42, which requires `opening_state.politics.pending_liberalization` to be real, persisted history, not merely a claim the current turn's report and state agree with each other on. |
| 28 | A `decree_authority`/`executive_system`/`executive_selection`/`national_election_interval_turns`/`executive_term_limit_terms` change in closing state with no matching target in the real submitted `ConstitutionalAmendmentDecision` | group 44 |
| 29 | A hand-assembled save with an entry appended after a `terminal_outcome`-carrying entry | `validate_history`'s tail-truncation guard (§6) |

---

## 9. CLI, reason IDs, and rendering (item 13)

**New reason IDs**:

| `reason_id` | category | emitted when |
|---|---|---|
| `coup_risk_assessed` | `politics` | every turn — all three channels' current risk scores and named contributing factors |
| `coup_attempt_occurred` | `politics` | coup `attempted` |
| `coup_succeeded` | `politics` | coup `succeeded` |
| `popular_unrest_occurred` | `politics` | unrest `outcome != "none"` (covers `contained` too) |
| `impeachment_motion_brought` | `politics` | impeachment `attempted` (R10: renamed from `impeachment_attempted` for clarity now that the channel has its own success stage) |
| `impeachment_succeeded` | `politics` | impeachment `succeeded` |
| `election_scheduled` | `politics` | `election.scheduled` |
| `election_result` | `politics` | `election.scheduled` (won/lost/term_limit_exit, one entry) |
| `constitutional_amendment_enacted` | `politics` | a `ConstitutionalAmendmentDecision` passed/was decreed, one entry per axis changed |
| `peaceful_liberalization_completed` | `politics` | `election.liberalization_completed` |
| `game_concluded` | `administration` | `politics.terminal_outcome` newly set this turn — emitted **before** `turn_resolved` (R10: `turn_resolved` stays the genuinely final entry on every turn, no exception carved out) |

**CLI additions** (`backend/app/cli.py`):
- `mandate inspect --institutions` — new flag, printing the strict-bps institution table directly
  from state.
- `_print_coup_unrest_report`/`_print_election_report`/`_print_constitutional_amendment_report` —
  three new shared leaf renderers, called identically from both `_cmd_resolve`'s live output and
  `_cmd_history --turn N`'s replay output.
- `inspect --politics` gains `terminal_outcome`, `next_election_turn`, and
  `regime_transition_pressure_bps` lines.
- `main()`'s existing `except MandateError` branch already handles `GameAlreadyConcludedError`
  (it is a `MandateError` subclass) with no new wiring.
- **R10: `_cmd_resolve`'s loop** stops immediately after a turn that sets `terminal_outcome`, writes
  the save normally, prints `f"game concluded at turn {N} of {requested} requested ({bucket}: 
  {reason})"`, and returns exit 0. A fresh `resolve` invocation against an already-concluded save
  hits `GameAlreadyConcludedError` at the top of `resolve_turn` before the loop's first iteration
  even begins, exit 1, no output file, input untouched.

---

## 10. Save/ruleset versioning (item 15)

**`RULESET_VERSION`: `"0.11.0" → "0.12.0"`.**

> Bumped for three reasons, any one alone sufficient. First, `InstitutionState`'s and
> `PopulationGroupState`'s metric fields change from float (0.0–100.0) to strict basis points
> (0–10,000) together, in this phase (R8) — a *scale* change with no honest migration. Second,
> `PoliticalState` gains five new fields, three of them (`consecutive_terms_held`,
> `next_election_turn`, `regime_transition_pressure_bps`) required and authored, with no data in a
> 0.11.0 save to backfill from — fabricating them would assert political history the save was never
> asked to record. Third, `TurnReport` grows from nine to twelve reports; a 0.11.0 save's historical
> `report_json` entries were built under, and only ever validated against, the nine-report shape, and
> re-parsing them under the twelve-report `TurnReport` would reject every historical entry outright.
> A 0.11.0 fixture is rejected with `UnsupportedRulesetVersionError` before any entry payload is
> parsed, exactly as every prior bump.

`SAVE_FORMAT_VERSION` stays `1`. `SUPPORTED_CONTENT_VERSIONS`: `"0.11.0" → "0.12.0"` in lockstep —
institution/population-group rows gain bps values and lose the redundant `legislature` row where
present; every scenario's `politics:` block gains the new authored lines (§2.2.1); `deficit_demo.yaml`
gains its previously-missing `military` institution row.

**Frozen fixture**: a genuine 0.11.0-ruleset save, produced by the pre-this-phase engine and
committed **before any schema change lands** — named `phase3b2b_save_ruleset_0.11.0.json` in
`backend/tests/fixtures/`, matching the established `phase<producing-phase>_save_ruleset_
<version>.json` convention. A new `test_compatibility.py` case asserts rejection with
`UnsupportedRulesetVersionError` specifically, before any entry payload is parsed.

---

## 11. Scenario calibration (item 16) — real numbers, computed against real authored data

All three scenarios need: institution rows' four metrics ×100 (float percent → bps); the redundant
`id: "legislature"` row removed from `tiny_valid`/`decree_state`; population-group rows' five metrics
×100; `deficit_demo` gains a calibrated `military` institution row; every `politics:` block gains
`consecutive_terms_held`, `next_election_turn`, `regime_transition_pressure_bps` (§2.2.1).

**The constants in §3 were tuned against a scratch calibration script driving these exact, real,
verified authored values — not invented and left unverified.** Computed outputs (all in bps unless
noted; "compound" = `attempt × success`, the actual per-turn removal probability from that channel):

| Scenario | Coup attempt / success / compound | Unrest attempt / success / compound | Impeachment attempt / success / compound | Total per-turn removal | Cumulative @ 20 / 40 / 100 turns |
|---|---|---|---|---|---|
| `tiny_valid` | 38 / 300 / 1 | 15 / 0 / 0 | 0 / — / 0 | 1 bps (0.01%) | 0.20% / 0.40% / 1.00% |
| `deficit_demo` | 48 / 250 / 1 | 15 / 0 / 0 | 0 / 700 / 0 | 1 bps (0.01%) | 0.20% / 0.40% / 1.00% |
| `decree_state` | 52 / 600 / 3 | 15 / 0 / 0 | 37 / 900 / 3 | 6 bps (0.06%) | 1.19% / 2.37% / 5.83% |

**All three stay well under any reasonable "meaningful cumulative game-over probability" bar over
100 turns** (R9's fairness requirement) — `decree_state`'s ~5.8% is real and higher than the other
two (its opposition holds an outright majority, 55/100, and `judicial_review: weak` scales
impeachment risk up), which is the honest, correct shape: a monarch facing a hostile legislative
majority genuinely carries more background risk than a comfortable coalition government, without
either government being in a "doomed" state. A deliberately low-loyalty military (military
`loyalty_bps` edited down to `2000`, everything else at `tiny_valid`'s baseline) drives coup attempt
risk to `623` bps (6.23%/turn) — a real, sharply visible jump, confirming the formula is genuinely
sensitive, not merely decorative.

**Testing discipline (R9): stability is proven across multiple seeds, and terminal and nonterminal
soaks are kept separate.** A "100-turn soak" that might legitimately terminate early is not a
100-turn soak — it is a terminal-path integration test, and is named and tested as one:

- **Nonterminal soaks (existing five + no new terminal risk introduced into them)**: re-verified,
  at the fixture seed, that none of the five existing 100-turn soaks terminate early under the new
  channels — this is itself a real assertion (not merely "unchanged"), since coup/unrest/impeachment
  risk is now live on every turn of every soak, including turns that submit budget/investment
  decisions unrelated to survival mechanics.
- **Multi-seed stability sweep**: a new, dedicated test resolves each scenario 100 turns with no
  survival-relevant decisions across a **declared, fixed seed range — `0` through `19` inclusive (20
  seeds), chosen before any run is observed, never selected or pruned after the fact** — and asserts
  termination did not occur for any seed in that range at the table above's calibrated constants —
  proving stability as a measured, swept claim, not a single-favorable-seed artifact.
- **Terminal-path integration tests, separate from any soak**: dedicated, short, single-seed tests
  for (a) a coup succeeding (via the deliberately-low-loyalty edit above), (b) `tiny_valid`'s
  natural term-limit exit at turn 32 (below), (c) `deficit_demo`'s natural contested election at
  turn 20 (below), (d) the `decree_state` liberalization walkthrough (below). None of these are
  called soaks.

**`tiny_valid`** (interval 16, term limit 2): `next_election_turn` reschedules to 32 after the turn-16
win (`16 + 16`); at turn 32, `consecutive_terms_held` has reached `2` (incremented once, at turn 16),
so `2 >= 2` fires `TERM_LIMIT_EXIT` — this is `tiny_valid`'s own natural, unforced proof of items 5
and 10, needing no synthetic fixture. A separate multi-seed sweep at the same baseline support level
(computed: `baseline_support_bps = 5487`, comfortably above the `5000` required — see the worked
election-support calculation below) confirms an unlucky `-487`-or-worse polling swing (within the
`±1000` range) can still cause a loss at some seed, proving the uncertainty is genuine.

**`deficit_demo`** (interval 20, no term limit): computed `baseline_support_bps = 4665`, **below**
the `5000` required — this scenario's authored weaker legitimacy/support genuinely puts its first
election in contested territory: only a swing of `+335` or better (out of the `±1000` range, i.e. a
`(1000-335)/2000 ≈ 33%` chance under a uniform swing) wins. The calibration test sweeps multiple
seeds at turn 20, confirms both `WON` and `LOST` are real, reachable outcomes, and pins the fixture
seed's own actual result as a literal assertion (not assumed). It is also the natural
"consolidation elevates coup risk, measurably and temporarily" proof (item 9): `deficit_demo`'s
`decree_authority` is `emergency_only` with a real legislature present (governing coalition 50/100,
opposition 50/100, required 51 for `SIMPLE_MAJORITY`) — a single-axis `ConstitutionalAmendmentDecision`
(`decree_authority → UNLIMITED`) goes through the legislative route via `resolve_amendment_support`,
needing to flip at least one seat exactly like this scenario's own existing budget calibration
already demonstrates is reachable-but-not-free. `transition_pressure_added_bps` for a one-axis,
`SIMPLE_MAJORITY` change is `1_500`; the test diffs `coup_attempt_risk_bps` turn-by-turn afterward
against a no-amendment control run on the same seed, confirming the diff is strictly positive
immediately after and decays to exactly zero within the predicted number of turns (per §3.5's 1/6
decay).

**`decree_state`** (monarchical/hereditary/unicameral/unlimited, no legislature-free path, interval
`None` at genesis): three proofs, none of them altering this scenario's existing legislature, seats,
relationships, or Phase 3B1/3B2 calibration (§0 item 10 — R1's correction).

- (a) The multi-seed nonterminal stability sweep (above) confirms `ElectionReport.scheduled == False`
  on all 100 turns of every unmodified run — elections structurally do not apply until this form is
  amended, the deliberate test case this scenario exists to cover.
- (b) **The canonical liberalization walkthrough — fully computed, not deferred.** The exact atomic
  five-target amendment that liberalizes this monarchy (verified by hand against every C1–C10 rule,
  §0 item 9): `executive_system → PRESIDENTIAL`, `executive_selection → DIRECT_ELECTION`,
  `decree_authority → NONE`, `national_election_interval_turns → 8`. This is a genuine regime-type
  change, not merely a procedural one — the executive stops being hereditary, which is the
  substantive fact that makes it a real qualifying transition (§5), not a cosmetic one. Because
  `decree_state` **has a real legislature** (45 governing / 55 opposition seats — R1), and the
  decree route is illegal whenever a legislature exists, **this amendment must pass through the
  legislative route**, at `SUPERMAJORITY` difficulty (67 of 100 seats), against an opposition bloc
  whose authored relationship is a maximally hostile `-8,000`.

  A dedicated scratch script (outside the repository, driving the real, unmodified
  `resolve_turn`/`relationship_gain_bps`/`relationship_decay_bps`/`resolve_political_capital`
  against `decree_state.yaml`'s real authored data, plus this plan's own corrected
  `resolve_amendment_support` and a bounded-knapsack DP identical in shape to
  `_exhaustive_cheapest_bargain`) computed the complete cheapest path, swept over both constant and
  asymmetric two-turn preparation splits (the same "sweep against real scenario data" methodology
  `relationships.py`'s own `RELATIONSHIP_HALF_GAP_CAPITAL` docstring uses — not a formally proven
  global optimum, but a reproducible, located minimum):

  | Turn | Action | Opening capital | Committed | Regeneration | Closing capital | Opening opp. relationship | Decay | Investment | Closing opp. relationship |
  |---|---|---|---|---|---|---|---|---|---|
  | 1 | Invest 85 PC in `opposition_party/main` | 500 | 85 | 383 | 798 | -8,000 | 0 | +2,615 | -5,385 |
  | 2 | Invest 118 PC in `opposition_party/main` | 798 | 118 | 385 | 1,000 (capacity-capped) | -5,385 | -326 | +2,937 | -2,774 |
  | 3 | Submit the amendment, `influence=(opposition_party/main: 300)` | 1,000 | 300 | 388 | 1,000 (capacity-capped) | -2,774 | (unused — vote reads opening) | — | — |

  **Total cumulative political capital committed: 503** (85 + 118 + 300). Every turn's commitment is
  proven `<= opening_political_capital` directly from the table above (85≤500, 118≤798, 300≤1,000) —
  the affordability guard holds by construction, not assumption. `governing_party/core` receives
  `0` capital throughout: at relationship `+6,000`/discipline `5,000`, its `effective_support_bps`
  is already `10,000` (the ceiling) with zero influence, so the DP finds no benefit in spending
  there — confirmed by the DP's own backtrace, not asserted.

  **Supporting-seat tally, submitting with zero capital at each turn's opening relationship** (the
  "is it even close" check): turn 1 (-8,000) → 45/100; turn 2 (-5,385) → 45/100; turn 3 (-2,774) →
  45/100 — flat at 45, because `resolve_amendment_support` with zero influence never lifts the
  opposition bloc's `effective_support_bps` off `0` at *any* of these relationship values (its
  `discipline_bps=8,000` whips a still-below-midpoint `baseline` all the way to the floor). This is
  the concrete demonstration that **relationship investment alone, without vote-turn influence
  capital, never suffices here** — the two levers are complementary, not substitutes: investment
  raises the `baseline` that influence is added to; only the combination crosses the discipline
  midpoint.

  **First turn the amendment can pass: turn 3.** At turn 3's opening relationship (-2,774) with the
  decisive `300`-capital allocation: `resolve_amendment_support` gives the opposition bloc
  `effective_support_bps = 4,003`, the governing bloc `10,000` (unchanged, zero capital); apportioned
  via the real, unmodified `apportion_supporting_seats` — `45·10,000 + 55·4,003 = 670,165`,
  `670,165 // 10,000 = 67` base seats before any remainder bonus — **exactly the 67 required.**

  **Boundary test — one fewer preparation turn: fails, unreachable, not merely unaffordable.**
  Attempting the amendment at turn 2 (after only turn 1's 85-PC investment, opposition relationship
  `-5,385`) returns `None` from the bargain DP even searching the full `[0, 300]` domain on *both*
  blocs — the combined maximum reachable total at that relationship (`450,000 + 55·2,120 =
  566,600`) falls short of `670,000` by a wide margin. This is a hard reachability failure, not a
  cost-threshold one.

  **Boundary test — one less capital on the decisive (turn 3) allocation: fails, exactly at the
  boundary.** At the opposition bloc's real turn-3 relationship (`-2,774`): capital `300` gives
  `effective_support_bps=4,003`, apportioning to `67/100` — **passes**. Capital `299` gives
  `effective_support_bps=3,985`, apportioning to `66/100` — **fails**, one seat short. The
  calibration is tight, not slack, at the swept minimum.

  Once the amendment passes (turn 3), `transition_pressure_added_bps` for this five-axis
  `SUPERMAJORITY` change is `min(10_000, 2_500 × 5) = 10_000` — the maximum, a full regime change
  being the largest shock this system can represent — and `next_election_turn = 3 + 8 = 11`.

  **The complete path from turn 3 to the election, at the fixture seed (77), computed turn by turn**
  (real `resolve_turn` for legitimacy/capital drift; this plan's own coup/unrest/impeachment/
  election formulas plus real `core.rng.derive_rng(77, turn, stream)` draws for every risk channel):
  coup attempt risk peaks at **1,052 bps (10.52%) on turn 3 itself** (driven almost entirely by the
  maxed transition-pressure contribution, `1,000` of the `1,052`), then decays turn over turn in
  step with the pressure's 1/6 decay (885 → 746 → 630 → 534 → 454 → 387 → 331 → 284 bps by turn 11).
  Popular-unrest risk stays flat at the scenario's calibrated `15` bps every turn (population data is
  static and never crosses either threshold). Impeachment becomes eligible from turn 3 onward (the
  amendment just replaced `HEREDITARY` selection), holding flat at `37` bps. **At seed 77, none of
  the three channels' attempt draws fire on any turn from 3 through 11** — a real, checked, negative
  result at a real risk level above 10% on the worst turn, not an assumed one. The scheduled election
  resolves at turn 11: opposition relationship has decayed back to `-6,426` by then (no further
  investment after turn 2), giving `legislative_support_bps=4,582`; population approval is the
  static `5,330`; legitimacy has drifted to `6,684`; `baseline_support_bps = (4,582·5,000 +
  5,330·4,000 + 6,684·1,000) / 10,000 = 5,091`; the seed's polling swing is `+615`; `final_support_bps
  = 5,706 >= 5,000` required — **WON**. Because `pending_liberalization` was set at turn 3 (the
  amendment's opening constitution was noncompetitive — hereditary selection, unlimited decree — and
  its closing constitution is competitive-elected), this win satisfies §5's test:
  `peaceful_liberalization_completed = True`. The walkthrough's own honesty requirement — that a
  coup might interrupt before the election, and the test must report whichever outcome the real
  formulas and real seed produce — is satisfied by running the actual numbers: at this seed,
  liberalization completes; the calibration test also asserts the coup-risk ceiling (1,052 bps at
  turn 3) directly, so a reader can see how close the risk came without it firing.

- (c) The multi-seed sweep (a) already establishes the "dictatorships may remain stable" baseline
  measurement honestly (5.83% cumulative over 100 turns, not asserted as zero).

**Worked election-support example** (item 3's "deterministic election results," computed from real
authored seat/relationship data):

`legislative_support_bps` for `tiny_valid`'s lower chamber (100 seats: mainstream 40 seats @
`+6,000` relationship, reform 12 @ `+3,000`, conservatives 30 @ `-7,000`, populists 8 @ `-3,000`,
farmers 10 @ `+2,000`) = `(40·8000 + 12·6500 + 30·1500 + 8·3500 + 10·6000) / 100 = 5,310`.
Population-weighted approval (three groups, shares 4000/3500/2500 bps, approvals 5200/5000/6000 bps)
= `5,330`. Legitimacy = `7,000`. `baseline_support_bps = (5310·5000 + 5330·4000 + 7000·1000) /
10000 = 5,487` — comfortably above the `5,000` required, matching the "reelection is the normal
case" calibration intent.

---

## 12. Requirement-to-test matrix

| # | Requirement | Primary coverage |
|---|---|---|
| T1 | Election scheduling / constitutional eligibility | `test_government_survival.py::test_next_election_turn_scheduling_rules` (all six rows of §4.4's table); `decree_state`'s multi-seed "never scheduled" sweep |
| T2 | Candidate/party participation | `test_election_report.py`: party-stance rows match the real legislature by identity; `sum(seats) == total_seats` |
| T3 | Deterministic election results | same-seed/turn/stream → identical swing; reconciliation group 38; the worked `tiny_valid` example (§11) reproduced exactly |
| T4 | Democratic transfer of power | `deficit_demo` multi-seed WON/LOST sweep, pinned fixture-seed result |
| T5 | Player reelection and electoral defeat | `tiny_valid` term-limit-exit-at-turn-32; `deficit_demo` pinned-seed contested result |
| T6 | Coup risk and coup attempts | `test_government_survival.py::test_coup_formulas`; two-stage RNG-draw determinism; reconciliation groups 24-26 |
| T7 | Institutional support inputs, no full military | schema test confirming no military/unit/combat type exists anywhere; `InstitutionState`/`PopulationGroupState` bps conversion tests |
| T8 | Dictatorship-to-democracy victory path | `decree_state` canonical liberalization walkthrough (§11b), fully computed (85/118/300 campaign, turn-11 WON result at seed 77) |
| T9 | Democracy-to-dictatorship route and consequences | `deficit_demo` consolidation-pressure diff test (§11) |
| T10 | Removal from office / campaign termination | `test_resolver.py::test_resolve_turn_refuses_after_terminal_outcome`; `GameAlreadyConcludedError` message/exit-code test; `_cmd_resolve` mid-loop-stop vs fresh-invocation-refusal tests (R10) |
| T11 | Clear victory/defeat/continuing taxonomy | `TerminalOutcomeState` validator tests; explicit test that CONTINUING has no representation beyond `None` |
| T12 | Interaction with legitimacy/capital/legislature/relationships | phase-isolation-style tests proving `legitimacy.py`/`political_memory.py`/`relationships.py` stay unmodified; R7 ordering test proving slot 12/13 read this-turn's closing legitimacy/relationships, not a stale opening snapshot |
| T13 | Reports, reason IDs, CLI | `test_reason_renderers.py` coverage extension (11 new IDs); `test_cli.py` new `--institutions` flag and shared-renderer parity check |
| T14 | Reconciliation and tamper resistance | `test_reconciliation.py` groups 24-45, one corruption case per field per group; `test_history.py` tamper-matrix cases 19-29, **including case 27, the starting-democracy liberalization-exploit case R3 exists to close** |
| T15 | Save-version compatibility | `test_compatibility.py` frozen-0.11.0-fixture rejection |
| T16 | Scenario calibration | `test_scenario_survival_calibration.py`, all three scenarios per §11, including the multi-seed stability sweep |
| T17 | This matrix itself | reviewed against the 22 numbered items directly at PR time |
| T18 | 100-turn soak / determinism | five existing soaks re-verified non-terminating under the new channels; multi-seed stability sweep (§11, distinct from "a soak"); terminal paths tested as separate, explicitly-named integration tests, never folded into soak framing (R9) |
| T19 | Manual CLI walkthrough | §13 below, transcript attached to the PR description |
| T20 | Files/commits | reviewed at PR time against §14 |
| T21 | Explicit exclusions | `test_legislative_neutrality.py` extended with a positive assertion that `government_survival.py` is deliberately excluded from `NEUTRAL_MODULES` |
| T22 | Engine freeze | §17 below — a documentation deliverable, confirmed by review |

---

## 13. Manual CLI walkthrough (14 steps, R4/R10 corrected; step 4's numbers now exact)

1. `mandate new --scenario data/scenarios/decree_state.yaml --out decree.json`
2. `mandate inspect --state decree.json --politics --institutions --legislature` — confirm
   `decree_authority: unlimited`, the real 45/55 unicameral legislature, `consecutive_terms_held: 1`,
   `next_election_turn: (none)`, `regime_transition_pressure_bps: 0`, `terminal_outcome: (none)`,
   military row shown in bps.
3. `mandate resolve --state decree.json --turns 1 --out decree.json` with no decisions —
   `mandate history --state decree.json --turn 1` shows `coup_risk_assessed` (low background
   numbers, named factors) and `election_scheduled: false`.
4. Author `invest_1.json` (`BlocRelationshipInvestmentDecision`, 85 PC into `opposition_party/main`);
   `mandate resolve --state decree.json --turns 1 --decisions-file invest_1.json --out decree.json`.
   Author `invest_2.json` (118 PC into `opposition_party/main`); `mandate resolve --state decree.json
   --turns 1 --decisions-file invest_2.json --out decree.json`. Author `amend.json` with the exact
   five-target `ConstitutionalAmendmentDecision` from §11b plus `influence=(opposition_party/main:
   300)`; `mandate resolve --state decree.json --turns 1 --decisions-file amend.json --out
   decree.json` — this is turn 3, the computed vote turn; §11(b)'s table gives the exact
   opening/closing capital and relationship values to check against at each of these three turns.
5. `mandate inspect --state decree.json --politics` — constitution changed (monarchical/hereditary
   → presidential/direct_election, decree_authority → none), `next_election_turn` now `11` (§11b:
   `3 + 8`), `regime_transition_pressure_bps` at `10,000` (the maximum, five-axis `SUPERMAJORITY`
   change), `pending_liberalization` set, capital spent (`503` cumulative — §11b), and
   `constitutional_amendment_enacted` present in the matching `history --turn 3`.
6. `mandate resolve --state decree.json --turns 8 --out decree.json` (no decisions) to reach the
   first scheduled election at turn 11. §11(b) computed this run at the fixture seed (77): coup
   attempt risk peaks at 1,052 bps on turn 3 itself and decays every turn after; none of the three
   removal channels fire on any turn from 3 through 11 at this seed — confirm the printed
   `coup_risk_assessed` figures on each intervening turn match §11(b)'s table.
7. `mandate history --state decree.json --turn 11` — `election_result: won` (baseline support
   5,091 bps, swing +615, final 5,706 — §11b), `peaceful_liberalization_completed` present.
8. `mandate inspect --state decree.json --politics` — `terminal_outcome: victory /
   peaceful_liberalization_completed / turn 11`.
9. `mandate resolve --state decree.json --turns 1` — refused with `GameAlreadyConcludedError`'s
   message, nonzero exit, `decree.json` byte-identical before/after.
10. `mandate new --scenario data/scenarios/tiny_valid.yaml --out tiny.json`; `mandate resolve --state
    tiny.json --turns 32 --out tiny.json` — the command exits 0 (R10: a concluded mid-loop stop is
    success, not an error); turn 16 shows an automatic won election (`next_election_turn` reschedules
    to 32); turn 32 shows `election_result: term_limit_exit`, and the CLI reports the game concluded
    at turn 32 of the 32 requested.
11. `mandate new --scenario data/scenarios/deficit_demo.yaml --out deficit.json`; `mandate resolve
    --state deficit.json --turns 20 --out deficit.json` — demonstrate the fixture seed's pinned
    won/lost result at turn 20 against the computed `4,665`-bps baseline support (§11).
12. `mandate history --state deficit.json --turn 20` vs the same block printed live during step 11's
    `resolve` — byte-for-byte identical rendering (shared-renderer discipline check).
13. **R10: begin from a fresh, deliberately-authored scenario, not a hand-edited mid-game save.**
    `mandate new --scenario data/scenarios/tiny_valid.yaml --out lowloyalty.json`, then a
    purpose-built scratch scenario file (or a `--seed`/decisions-file-driven fresh game, not a
    post-hoc edited save) with the military `loyalty` field authored at `2000` from genesis, so
    the save's hash chain is genuinely consistent from the start. `mandate resolve --turns 1` and
    confirm `coup_attempt_occurred` (and possibly `coup_succeeded`) appears with named contributing
    factors reflecting the low authored value — matching the `623`-bps computed example in §11,
    verifiable by eye against the printed contribution breakdown.
14. Hand-craft a save with an entry appended after a `terminal_outcome`-carrying entry (mirroring
    `test_history.py`'s own `_retamper_entry_with_consistent_hash` pattern — rehashed consistently,
    not a stale-hash tamper, so the walkthrough demonstrates the *new* guard, not merely the
    pre-existing hash check); `mandate inspect` on it and confirm `validate_history`'s new guard
    rejects it with the "entry exists after the game concluded" message.

---

## 14. Files and reviewable commit sequence — three internal gates (new, per the review)

**Structure**: one Phase 3C branch, one PR, but the work is organized into three internally-gated
groups. Each gate's own commits must be fully green (full suite, `ruff`, `mypy`) and its own slice of
calibration/tests must pass **before the next gate's commits begin** — a reviewer can evaluate gate
1 as a complete, load-bearing unit without needing gate 3 to exist yet. `pending_liberalization`
and the liberalization-specific tests are the one genuine cross-gate dependency (§5 needs both
election scheduling from gate 1 and amendments from gate 3) — gate 1's own tests cover only ordinary
election win/loss/term-limit outcomes (no liberalization victory test yet, since nothing can set
`pending_liberalization` until gate 3 lands); gate 3 adds the liberalization-specific tests once the
amendment mechanism exists.

**New files:**
- `backend/app/simulation/government_survival.py`
- `backend/tests/test_government_survival.py`
- `backend/tests/test_coup_unrest_report.py`
- `backend/tests/test_election_report.py`
- `backend/tests/test_constitutional_amendment_report.py`
- `backend/tests/test_scenario_survival_calibration.py`
- `backend/tests/test_terminal_outcome.py`
- `backend/tests/fixtures/phase3b2b_save_ruleset_0.11.0.json`
- `docs/adr/0013-government-survival.md`

**Modified files:** `app/core/errors.py`, `app/core/politics.py`, `app/simulation/state.py`,
`app/simulation/decisions.py`, `app/simulation/legislature.py`, `app/simulation/legislative_voting.py`,
`app/simulation/constitution.py` (no rule changes — read-only reference), `app/simulation/phases.py`,
`app/simulation/report.py`, `app/simulation/reconciliation.py`, `app/simulation/resolver.py`,
`app/simulation/history.py`, `app/simulation/save_format.py`, `app/simulation/invariants.py`,
`app/cli.py`, `data/scenarios/*.yaml` (all three), `docs/roadmap.md`, `docs/product_spec.md` (§41's
stale "Phase 3B2A" reference corrected), `backend/tests/test_soak.py`,
`backend/tests/test_no_forbidden_imports.py`, `backend/tests/test_legislative_neutrality.py`,
`backend/tests/test_compatibility.py`, and every existing test file constructing a
`TurnReport`/`PoliticalState`/`InstitutionState`/`PopulationGroupState` literal (a global sweep).

### Gate 3C1 — terminal state, scheduling, elections

1. **Freeze `phase3b2b_save_ruleset_0.11.0.json`**, isolated, before any model or constant change.
2. **Bps conversion**: `core/politics.py` new types; `InstitutionState`/`PopulationGroupState`
   float→bps (R8, both together); scenario updates (bps values, drop redundant `legislature` row,
   add `deficit_demo`'s missing `military` row); `player_military_institution_required` invariant.
3. **New state**: `TerminalOutcomeState`, `RemovalReason`, `VictoryReason`,
   `PendingLiberalizationState`; `PoliticalState`'s five new fields, including `next_election_turn`'s
   genesis-vs-derived cross-validator (§2.2.1); scenario `politics:` blocks gain the new authored
   lines.
4. **`resolve_turn` top-of-function guard, `GameAlreadyConcludedError`, `validate_history`
   tail-truncation guard** (§6).
5. **Election channel formulas** in `government_survival.py` (§3.4), pure, fully unit-tested in
   isolation (worked `tiny_valid` example from §11 pinned as a literal test).
6. **Slot 13**: `_evaluate_elections`, `next_election_turn` scheduling rules (§4.4, all six table
   rows tested), `ElectionReport` (without the liberalization-specific fields being exercisable
   yet — `pending_liberalization` always `None` at this gate), its self-validators.
7. **`TurnReport` grows to ten reports** (adds `election` only, at this gate).
8. **Reconciliation groups 35-40, 45** (election scheduling, term limit, support-score, RNG-draw,
   result-vs-state, party-identity match, terminal non-retroactivity).
9. **CLI**: `election_scheduled`/`election_result`/`game_concluded` reason IDs, shared election
   renderer on both print paths, `--politics`'s new lines, `_cmd_resolve`'s mid-loop-stop-vs-refusal
   split (R10).
10. **Gate 3C1 calibration**: `tiny_valid` term-limit-exit-at-turn-32 test; `deficit_demo` multi-seed
    contested-election sweep with the pinned fixture-seed result; `decree_state`'s "never scheduled"
    multi-seed sweep. Full suite green, gate reviewed as a complete unit.

### Gate 3C2 — coups, unrest, impeachment

11. **Coup/unrest/impeachment formulas** in `government_survival.py` (§3.1–3.3), pure, fully
    unit-tested in isolation, including the multi-seed cumulative-probability computation that
    produced §11's table.
12. **Slot 12**: `_evaluate_unrest_and_coup_risk`, the fixed coup→unrest→impeachment priority order,
    `resolve_transition_pressure_bps`'s single write site (§4.1/§4.3 — R6), `CoupUnrestReport`, its
    self-validators.
13. **`TurnReport` grows to eleven reports** (adds `coup_unrest`).
14. **Reconciliation groups 24-34** (coup/unrest/impeachment attempt-risk, success-probability,
    RNG-draw recomputes; transition-pressure identity).
15. **CLI**: the remaining coup/unrest/impeachment reason IDs, shared `CoupUnrestReport` renderer on
    both print paths, `--institutions` flag.
16. **History tamper-matrix cases 19-23** (`test_history.py`).
17. **Gate 3C2 calibration**: the multi-seed stability sweep across all three scenarios (§11's
    table, computed and pinned); the five existing soaks re-verified non-terminating under the new
    channels; the deliberately-low-loyalty terminal-path integration test (§13 step 13's scenario).
    Full suite green, gate reviewed as a complete unit.

### Gate 3C3 — constitutional transitions and victory

18. **`ConstitutionalAmendmentDecision`**, five-axis discriminated-union target shapes, the
    `influence` field (§2.4's plan-only correction), decision-set "at most one policy proposal"
    rule, `resolve_amendment_support`/`required_amendment_yes_seats`, new
    `CapitalExpenditureCategory` member.
19. **Slot 1/2 wiring**: amendment routing, voting, the "changes nothing"/"final constitution
    invalid" resolution-time checks, commit, `pending_liberalization` set/clear logic (§4.3/§5).
20. **`ConstitutionalAmendmentReport`**, its self-validators; `TurnReport` grows to its final twelve
    reports.
21. **Victory condition** (§5) fully wired: gate 3C1's `ElectionReport` liberalization check becomes
    live now that `pending_liberalization` can actually be set.
22. **Reconciliation groups 41-44** (pending-liberalization state-to-state, liberalization
    provenance — the group that closes the starting-democracy exploit — amendment digest/tally/
    capital recompute, five-axis staticness).
23. **History tamper-matrix cases 24-29**, including case 27, the starting-democracy exploit case.
24. **CLI**: `constitutional_amendment_enacted`/`peaceful_liberalization_completed` reason IDs,
    shared `ConstitutionalAmendmentReport` renderer on both print paths.
25. **Ruleset/content-version bump** (`0.11.0 → 0.12.0`), `test_compatibility.py` rejection case.
26. **Gate 3C3 calibration**: `deficit_demo`'s consolidation-pressure diff test; `decree_state`'s
    canonical liberalization walkthrough (§11b — the fully computed 85/118/300 campaign and its
    turn-11 WON result at seed 77), asserted as literal pinned values; the full 22-item requirement
    matrix reviewed against the finished engine. Performance remeasurement against the Phase 3B2B
    baseline (five existing soaks + the new multi-seed stability sweep's own timing), same
    1-warm-up-plus-3-sample protocol, 2.0x stop-and-report threshold.
27. **Docs**: `docs/adr/0013-government-survival.md`, `docs/roadmap.md` Phase 3C entry (converted to
    the checked/unchecked bullet format every completed phase uses), `docs/product_spec.md` §41
    correction, `README.md`, the §17 engine-freeze declaration.

Each commit gated individually with `ruff format`, `ruff check`, `mypy`, and the affected tests; the
full suite green before every commit from 2 onward (commit 1 is the isolated fixture freeze). No
amending.

---

## 15. Verification commands

```bash
cd backend && uv sync --locked --group dev && uv build
uv run ruff format --check . && uv run ruff check . && uv run mypy
uv run pytest -v
cd ../frontend && npm ci && npm run typecheck && npm run build && npm test
npm audit --audit-level=low                        # expect only the known FE-1 nanoid advisory
cd .. && docker compose config --quiet              # never started
```

Plus all five existing 100-turn soaks (re-verified non-terminating), the new multi-seed stability
sweep (§11 — declared seeds `0`–`19` × 3 scenarios × 100 turns, distinct from a soak), one discarded
warm-up per soak, three measured runs, median compared, reported before and after gate 3C3's commit 26.
If any post/pre median ratio exceeds 2.0x, stop and report exact measurements. Never assert wall-clock
timings in tests.

---

## 16. Explicit exclusions (item 21)

No `MilitaryState`, unit, province, or combat model of any kind. No war, no diplomacy, no sanctions,
no treaties, no nuclear weapons. No multiplayer, no GUI/frontend work (CLI only). No second proposal
kind beyond the budget and the new constitutional amendment; no confidence votes, no coalition
collapse, no conference committees, no per-proposal supermajorities for ordinary (non-constitutional)
law; no legislative seat realignment or defections; no AI-country politics. `judicial_review` gains
exactly one narrow read (impeachment eligibility and its risk scale) and no general courts/doctrine
system. `decree_authority: EMERGENCY_ONLY` remains, deliberately, mechanically identical to `NONE` —
no emergency-declaration mechanic is built. `territorial_organization` stays non-amendable and
mechanically inert. `PopulationGroupState.population_share` stays a float (it is a proportion, not
one of the five converted metrics).

**New tracked tickets this phase deliberately does not close:** `POL-5` (a genuine
emergency-declaration system giving `EMERGENCY_ONLY` real, distinct-from-`NONE` behavior), `POL-6`
(courts/judicial review as a general doctrine, illegal-decree consequences), `POL-7` (second proposal
kind beyond the amendment this phase adds, confidence votes, coalition collapse, conference
committees), `POL-8` (seat realignment/defections), `POL-9` (AI-country politics), `POL-10`
(character/cabinet system — see §17's final framing). `TEST-1`, `FIN-1`, `FE-1` remain open
and untouched, as instructed. `POL-2` (the `InstitutionState`/`LegislatureState` overlap) **closes
fully** in this phase (§0 item 4) — there is no remaining `POL-2b`.

---

## 17. Engine-freeze definition (item 22) — final correction: character question left open, not foreclosed

**Correction to this section (this section only — everything else in the plan is unaffected).** An
earlier draft chose "no character system, permanently" and called that a permanent Version 1
limitation. That overreached: it foreclosed a product decision this plan has no standing to make
permanently, and it isn't necessary to make the engine freeze coherent. The corrected position:

- **Phase 3C adds no character system.** Nothing in §1–§16 introduces a `PoliticalActor`, a named
  leader, or any per-person state. Every removal reason, election result, and coup outcome remains a
  fact about *the office*, never about a named individual.
- **Phase 4A (the graphical vertical slice) may attach presentation-only leader and political
  portraits to the stable identifiers this phase already ships** — `party_id`, `bloc_id`,
  `institution.id`, the government-role labels on `LegislativeBlocState`. A portrait or a name shown
  next to "governing coalition" or "opposition bloc" is pure rendering: it reads an existing,
  already-reconciled identifier and displays it, and cannot feed back into any formula in §3, because
  no formula in §3 or elsewhere in this phase accepts anything resembling a character as an input.
- **`POL-10` (a character/cabinet system) remains an explicit base-game candidate** — not filed as
  expansion-only, not filed as "if ever." It is undecided, not deferred-forever.
- **The actual decision — whether Version 1 needs a minimal `PoliticalActorState` (identity, office,
  party, loyalty, competence) — is made after the first graphical vertical-slice playtest**, with
  real evidence about whether office/bloc-level presentation is enough or whether players need a
  named person to track. This plan does not prejudge that outcome in either direction.
- **The engine freeze is written to permit that later module without reopening anything this phase
  builds.** If `POL-10` is later approved, it adds a new, independently versioned, optional state
  block and its own ruleset bump; it does not touch `PoliticalState`, `government_survival.py`'s
  formulas, or any of the twelve reports frozen by this phase. This is a structural property of the
  freeze below (new-additive, not payload-editing), not a promise about what a later phase will
  choose to do.
- **No Phase 3C formula may depend on an unbuilt character model.** Checked directly: every input to
  every formula in §3 is `InstitutionState`, `PopulationGroupState`, `LegislatureState`/
  `LegislativeBlocState`, `ConstitutionState`, or `PoliticalState` fields that exist today — none of
  the coup/unrest/impeachment/election formulas reads or infers anything about an individual.

**The freeze declared below is a claim about the deterministic simulation's mechanics, not a claim
about whether characters will ever exist.** Concretely:

- `GameState`'s domestic-government shape (`PoliticalState`, `LegislatureState`, `ConstitutionState`,
  `InstitutionState`, `PopulationGroupState`, `EconomyState`, `GovernmentFinanceState`) is final for
  this build — no further Phase-3-scope commit should add a required field to any of these types. A
  future `PoliticalActorState`, if approved, adds **new**, independently optional state, never edits
  these types in place.
- `DecisionSet`'s three-member union (`BudgetDecision | BlocRelationshipInvestmentDecision |
  ConstitutionalAmendmentDecision`) is the complete domestic-decision vocabulary for this build.
- `TurnReport`'s twelve reports are the complete domestic reporting vocabulary for this build — every
  one self-validating, reconciled against real state, CLI-visible on both live and replayed paths.
- `PHASE_ORDER`'s ten real slots (1–5, 10–13, 15) are domestically complete. The remaining five
  no-op slots (6 public services, 7 diplomacy/sanctions, 8 military movement/combat, 9 casualties/
  occupation, 14 narrative events) are honestly, permanently out of this freeze's scope.
- **A game can now legitimately end** — `resolve_turn`/`advance_game`/`validate_history` all
  correctly model a terminal state, which is the one piece of plumbing every later phase (an API's
  turn-resolution endpoint, a frontend's "game over" screen) needs to exist *before* it can be built
  against.
- **What "frozen" does NOT mean**: it does not mean balance is final; it does not mean the domestic
  engine can never grow again (the next structural change is a new, versioned ruleset bump, not a
  rewrite); and it does not mean the character/leaders question is settled — it is explicitly left
  open, to be decided with playtest evidence, not in this planning document. Phase 4A can render
  party/bloc/institution data (names, roles, relationships, loyalty) and presentation-only portraits
  against this freeze without waiting on that decision; Phase 4/5 work otherwise requires zero further
  `simulation/` *formula* changes to proceed.

---

## 18. Confirmation

### Six binding confirmations

1. **`decree_state`'s legislature remains byte-identical through scenario recalibration.** §11's
   scenario-calibration pass touches `decree_state.yaml` in exactly two ways: institution/population
   metric fields ×100 (float→bps, R8) and the `politics:` block's three new authored lines (§2.2.1).
   Neither touches the `legislature:` block. The 45-seat governing / 55-seat opposition unicameral
   legislature, its bloc names, discipline, and `government_relationship_bps`/
   `baseline_government_relationship_bps` values are untouched — confirmed by §0 item 10's explicit
   statement and unchanged by any later correction, since nothing after it alters scenario data.
2. **Its liberalizing amendment passes through the real legislative voting engine.** §11(b) states
   this amendment is proposed as a `ConstitutionalAmendmentDecision` at `route=LEGISLATIVE`
   (`decree_state` has a real legislature, so the decree route is illegal regardless of
   `decree_authority` — §2.4), scored by the corrected `resolve_amendment_support`/
   `required_amendment_yes_seats` functions against the real seat/relationship data, requiring 67 of
   100 seats (`SUPERMAJORITY`) against a bloc structurally opposed at `-8,000`. No shortcut or
   scripted outcome is assumed — §11(b) now reports the complete, computed campaign (85/118/300 PC
   across three turns, both boundary failures verified) produced by a scratch script driving the
   real engine plus the plan's own corrected formulas, not a deferred promise to verify later.
3. **The final five-axis constitution is valid under C1–C10.** The target combination —
   `executive_system: PRESIDENTIAL`, `executive_selection: DIRECT_ELECTION`, `decree_authority: NONE`,
   `national_election_interval_turns: 8`, legislature unchanged at `unicameral` — was checked by hand
   against every rule in `first_constitutional_violation()`: C1/C2 (parliamentary rules) don't apply,
   system is presidential; C3 (presidential forbids legislative selection) holds, selection is direct;
   C4 (semi-presidential) doesn't apply; C5 (legislative selection requires a legislature) doesn't
   apply, selection is direct; C6 (hereditary requires monarchical) doesn't apply, selection is no
   longer hereditary; C7 (monarchical requires hereditary/appointed) doesn't apply, system is no
   longer monarchical; C8 (term limit + hereditary) doesn't apply, no term limit is set by this
   amendment and selection isn't hereditary; C9 (election interval + no legislature + not direct
   election) doesn't fire, a legislature exists; C10 (no legislature + decree ≠ unlimited) doesn't
   fire, a legislature exists. All ten checks pass.
4. **Only one policy proposal is permitted per turn, and simultaneous reporting is not attempted.**
   §2.4/R5 states the `DecisionSet` rule directly: "at most one of `{BudgetDecision,
   ConstitutionalAmendmentDecision}` per turn." No provision anywhere in this plan supports both in
   one turn, so simultaneous budget-and-amendment reporting is never required to be specified —
   the constraint is enforced structurally (a `DecisionSetError` on violation), not by report design.
5. **All new top-level reports participate correctly in the completeness rule.** §7.3 states
   `TurnReport`'s all-present-or-all-absent validator grows from nine booleans to twelve, naming all
   three new reports (`coup_unrest`, `election`, `constitutional_amendment`) as joining it explicitly.
   §14's gate sequence confirms this incrementally: `TurnReport` reaches ten reports at the end of
   Gate 3C1 (adds `election`), eleven at the end of Gate 3C2 (adds `coup_unrest`), and its final
   twelve at the end of Gate 3C3 (adds `constitutional_amendment`) — the validator and its test
   coverage are updated in the same commit each report is added, never left inconsistent between
   gates.
6. **The cumulative survival calibration uses a declared seed range, not selected favorable seeds.**
   §11's per-turn/cumulative-probability table (the 1/6/38/48/52-bps-style figures and their
   20/40/100-turn cumulative values) is computed directly from the closed-form formulas in §3 against
   each scenario's authored data — arithmetic, not sampled, so there is no seed to select favorably in
   the first place. The stochastic claim that needs seed discipline is stability (no early
   termination): §11 specifies this as an explicit, declared, contiguous range, **seeds `0` through
   `19` inclusive**, fixed before any run is observed, for all three scenarios. If any seed in that
   declared range terminates early, that is a reportable finding requiring recalibration, not a seed
   to drop and re-roll past. The `decree_state` liberalization walkthrough's own fixture-seed (77)
   result is likewise reported as computed (turn-11 WON, coup risk peaking at 1,052 bps without
   firing), not assumed. The terminal-path integration tests (coup-succeeds, term-limit-exit,
   contested-election, liberalization walkthrough) remain separately, deliberately single-seed (the
   fixture seed) by design, since they exist to demonstrate a specific reachable outcome, not to
   measure stability.

**No repository mutation has occurred while writing this plan.** Working tree clean and unchanged; no
branch created; no repository file edited; nothing committed, pushed, merged, or opened as a PR. Every
claim about the existing codebase — slot names and count, `ctx.rng()`'s existence and zero call sites,
exact enum values and C1–C10 rule text, exact report count and validator name, exact ruleset/save-
format version constants, **`decree_state.yaml`'s real unicameral 45/55 legislature (R1)**,
**`deficit_demo.yaml`'s missing military institution row**, every scenario's exact constitutional
axes/institution/population-group values, the fixture-naming convention — was verified by direct
reading of the source files, not assumed. The formulas in §3 and the calibration figures in §11,
including the full `decree_state` amendment campaign, were computed by scratch scripts run against
these exact, verified values and the real, unmodified backend package (`resolve_turn`,
`relationship_gain_bps`, `relationship_decay_bps`, `resolve_political_capital`,
`apportion_supporting_seats`, `core.rng.derive_rng`), outside the repository, touching nothing. All
verification commands proposed in §15 are read-only or build/test-only; no Docker container or
Postgres instance would be started by following this plan as written.

### Critical files for implementation

- `backend/app/simulation/phases.py`
- `backend/app/simulation/state.py`
- `backend/app/simulation/report.py`
- `backend/app/simulation/reconciliation.py`
- `backend/app/simulation/resolver.py`
- `backend/app/simulation/history.py`
- `backend/app/simulation/constitution.py`
- `backend/app/simulation/legislature.py`
- `backend/app/simulation/legislative_voting.py`
- `backend/app/simulation/decisions.py`
- `backend/app/simulation/legitimacy.py`
- `backend/app/simulation/political_memory.py` (formula-shape precedent)
- `backend/app/core/politics.py`
- `backend/app/core/rng.py`
- `backend/app/simulation/save_format.py`
- `backend/app/cli.py`
- `data/scenarios/tiny_valid.yaml`, `deficit_demo.yaml`, `decree_state.yaml`
- `docs/adr/0011-*.md`, `docs/adr/0012-*.md` (structural precedent for this plan's own format)
