"""Validation-hardening audit for `LegislativeReport`/`ChamberVoteReport`/`BlocVoteReport`'s
self-validation and `TurnReport`'s three legislative cross-validators (Phase 3B1 follow-up).

Every one of the 13 `LegislativeReport`-family validators (report.py's own numbering, restated in
the module-level `# --- N. ...` section headers below) gets at least one dedicated corruption
test, exercised through **both** `model_validate` (dict) and `model_validate_json` (equivalent
JSON string) via the `_LEGISLATIVE_LOADERS`/`_TURN_LOADERS` parametrize decorators -- so each
corruption case is actually two separately-collected pytest items, not one loop hiding two
assertions.

Two sourcing strategies, chosen per case:

- **Real resolver, then corrupt one field at a time** (preferred, "where practical"): a genuinely
  valid report comes out of `resolve_turn` against `tiny_valid.yaml`/`deficit_demo.yaml` or a
  small custom `PoliticalState`, dumped to a dict, then exactly one claim is mutated.
- **Direct construction** for cases no real scenario reaches cleanly (the four spending-change
  branches with a zero opening/proposed total; isolating one cross-row check without a real
  bloc's influence perturbing five other fields at once). Every such report is still built by
  calling the real Pydantic constructors -- nothing is `model_construct`-bypassed or mocked -- so
  it is still the real validator chain being exercised, just against hand-picked, independently
  verified inputs instead of the resolver's output. `_bloc_row`/`_minimal_legislative_report`
  deliberately use a **saturating** relationship (`+/-10_000`) so `effective_support_bps` pins at
  10,000 or 0 regardless of influence spent -- the one trick that lets political-capital fields be
  varied freely without perturbing the five other fields a real (non-saturating) bloc's row would
  couple them to.

No test calls `simulation.legislative_voting`/`simulation.apportionment` to *produce* a report
(that would defeat the point -- report.py's validators must never call them either); the constants
imported from `legislative_voting` below (`MAX_INFLUENCE_BPS` etc.) are used only to compute what
a **hand-built** row's fields must independently say, exactly as `test_legislative_voting.py`
computes hand-worked figures against the same constants.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.content.scenarios import load_scenario_file
from app.simulation.constitution import DecreeAuthority, Legislature
from app.simulation.decisions import BudgetDecision, DecisionSet, InfluenceAllocation
from app.simulation.legislative_voting import (
    DECREE_POLITICAL_CAPITAL_COST,
    INFLUENCE_BPS_PER_CAPITAL,
    MAX_INFLUENCE_BPS,
)
from app.simulation.legislature import (
    ChangeDirection,
    GovernmentRole,
    LegislativeChamber,
    LegislativeOutcome,
    ProposalRoute,
)
from app.simulation.report import BlocVoteReport, ChamberVoteReport, LegislativeReport, TurnReport
from app.simulation.resolver import resolve_turn
from tests.conftest import SCENARIO_DIR, make_country, make_game_state, make_politics

_LEGISLATIVE_LOADERS = pytest.mark.parametrize(
    "load",
    [
        pytest.param(LegislativeReport.model_validate, id="model_validate"),
        pytest.param(
            lambda data: LegislativeReport.model_validate_json(json.dumps(data)),
            id="model_validate_json",
        ),
    ],
)

_TURN_LOADERS = pytest.mark.parametrize(
    "load",
    [
        pytest.param(TurnReport.model_validate, id="model_validate"),
        pytest.param(
            lambda data: TurnReport.model_validate_json(json.dumps(data)), id="model_validate_json"
        ),
    ],
)


# =============================================================================
# Builders
# =============================================================================


def _bloc_row(
    *,
    party_id: str = "gov",
    bloc_id: str = "core",
    chamber: LegislativeChamber = LegislativeChamber.LOWER,
    seats: int = 100,
    allocated: int = 0,
    role: GovernmentRole = GovernmentRole.COALITION,
    relationship_bps: int = 10_000,
) -> BlocVoteReport:
    """A single, fully self-consistent bloc row with a **saturating** relationship: baseline
    support is already clamped to 10,000 (coalition) or 0 (opposition, via `-10_000`) purely from
    role + relationship, with `tax_preference_bps=spending_preference_bps=0` so policy content
    never contributes and `discipline_bps=0` so amplification is a no-op. Consequently `influence`
    (driven by `allocated`) can be varied freely across the whole legal range without perturbing
    `final_support_bps`/`effective_support_bps`/`numerator`/`base_seats`/`remainder`/
    `supporting_seats` at all -- the property every commitment-focused test below relies on to
    isolate its one claim under test.
    """
    saturated = relationship_bps >= 0
    baseline = 10_000 if saturated else 0
    influence = min(MAX_INFLUENCE_BPS, allocated * INFLUENCE_BPS_PER_CAPITAL)
    effective = 10_000 if saturated else 0
    numerator = seats * effective
    base = numerator // 10_000
    return BlocVoteReport(
        party_id=party_id,
        bloc_id=bloc_id,
        chamber=chamber,
        seats=seats,
        government_role=role,
        government_relationship_bps=relationship_bps,
        discipline_bps=0,
        tax_preference_bps=0,
        spending_preference_bps=0,
        baseline_support_bps=baseline,
        policy_compatibility_bps=0,
        raw_support_bps=baseline,
        political_capital_allocated=allocated,
        influence_bps=influence,
        final_support_bps=baseline,
        effective_support_bps=effective,
        numerator=numerator,
        base_seats=base,
        remainder=numerator % 10_000,
        bonus_seat=False,
        supporting_seats=base,
    )


def _chamber_row(
    *,
    chamber: LegislativeChamber = LegislativeChamber.LOWER,
    total_seats: int,
    supporting_seats: int,
) -> ChamberVoteReport:
    required = total_seats // 2 + 1
    return ChamberVoteReport(
        chamber=chamber,
        total_seats=total_seats,
        supporting_seats=supporting_seats,
        required_yes_seats=required,
        shortfall_seats=max(0, required - supporting_seats),
        target_total=supporting_seats,
        extras_awarded=0,
        passed=supporting_seats >= required,
    )


def _minimal_legislative_report(
    *,
    outcome: LegislativeOutcome = LegislativeOutcome.PASSED_LEGISLATIVE,
    route: ProposalRoute | None = ProposalRoute.LEGISLATIVE,
    legislature_present: bool = True,
    allocated: int = 0,
    political_capital_committed: int | None = None,
    opening_political_capital: int = 1_000,
    chambers: tuple[ChamberVoteReport, ...] | None = None,
    blocs: tuple[BlocVoteReport, ...] | None = None,
    opening_total_program_spending: int = 1_000_000,
    proposed_total_program_spending: int = 1_000_000,
    spending_direction: ChangeDirection = ChangeDirection.UNCHANGED,
    spending_intensity_bps: int = 0,
    tax_delta_bps: int = 0,
    tax_direction: ChangeDirection = ChangeDirection.UNCHANGED,
    tax_intensity_bps: int = 0,
    budget_decision_digest: str | None = None,
) -> LegislativeReport:
    """A minimal, single-chamber, single-(saturating)-bloc `PASSED_LEGISLATIVE` report by default;
    every keyword lets a test steer exactly one axis (route/outcome/capital/spending/tax) while
    the rest stays trivially self-consistent.

    `budget_decision_digest` defaults to a properly-shaped placeholder digest for every outcome
    except `NO_PROPOSAL` (which requires `None`) — these tests exercise report-level syntax, never
    `simulation.reconciliation`'s semantic check against a real `DecisionSet`, so the digest's
    exact value never matters here, only its shape.
    """
    if blocs is None:
        blocs = (_bloc_row(seats=100, allocated=allocated),)
    if chambers is None:
        total = blocs[0].seats if blocs else 100
        chambers = (_chamber_row(total_seats=total, supporting_seats=total),)
    if political_capital_committed is None:
        political_capital_committed = allocated
    if budget_decision_digest is None and outcome is not LegislativeOutcome.NO_PROPOSAL:
        budget_decision_digest = "a" * 64
    return LegislativeReport(
        outcome=outcome,
        route=route,
        legislature_present=legislature_present,
        tax_delta_bps=tax_delta_bps,
        tax_direction=tax_direction,
        tax_intensity_bps=tax_intensity_bps,
        opening_total_program_spending=opening_total_program_spending,
        proposed_total_program_spending=proposed_total_program_spending,
        spending_direction=spending_direction,
        spending_intensity_bps=spending_intensity_bps,
        chambers=chambers,
        blocs=blocs,
        opening_political_capital=opening_political_capital,
        political_capital_committed=political_capital_committed,
        budget_decision_digest=budget_decision_digest,
    )


def _minimal_bicameral_report(*, lower_allocated: int, upper_allocated: int) -> LegislativeReport:
    """One bloc seated in both chambers (60 lower / 40 upper, both passing), each row's influence
    independently controllable without perturbing anything else (see `_bloc_row`)."""
    lower = _bloc_row(chamber=LegislativeChamber.LOWER, seats=60, allocated=lower_allocated)
    upper = _bloc_row(chamber=LegislativeChamber.UPPER, seats=40, allocated=upper_allocated)
    return _minimal_legislative_report(
        allocated=lower_allocated,
        political_capital_committed=lower_allocated,
        chambers=(
            _chamber_row(chamber=LegislativeChamber.LOWER, total_seats=60, supporting_seats=60),
            _chamber_row(chamber=LegislativeChamber.UPPER, total_seats=40, supporting_seats=40),
        ),
        blocs=(lower, upper),
    )


def _tied_50_100_report() -> LegislativeReport:
    """An exact 50/100 tie (required 51): fails, matching R1's "a tie fails" rule."""
    supportive = _bloc_row(
        party_id="gov",
        bloc_id="core",
        seats=50,
        role=GovernmentRole.COALITION,
        relationship_bps=10_000,
    )
    hostile = _bloc_row(
        party_id="opp",
        bloc_id="main",
        seats=50,
        role=GovernmentRole.OPPOSITION,
        relationship_bps=-10_000,
    )
    return _minimal_legislative_report(
        outcome=LegislativeOutcome.FAILED_LEGISLATIVE,
        blocs=(supportive, hostile),
        chambers=(_chamber_row(total_seats=100, supporting_seats=50),),
    )


def _row_index(data: dict, *, party_id: str, bloc_id: str, chamber: str) -> int:
    return next(
        i
        for i, row in enumerate(data["blocs"])
        if row["party_id"] == party_id and row["bloc_id"] == bloc_id and row["chamber"] == chamber
    )


# --- Real-resolver dict builders ---------------------------------------------


def _valid_legislative_report_dict() -> dict:
    """`tiny_valid`'s bicameral coalition passing the walkthrough proposal unaided in both
    chambers (58/100, 33/60) -- at least one chamber has a nonzero `extras_awarded`."""
    state = load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml")
    current = state.world.countries["arken"].finance.tax_policy.personal_income_rate_bps
    decision = BudgetDecision(personal_income_rate_bps=current + 500)
    decisions = DecisionSet(
        expected_turn=state.turn, expected_state_version=state.state_version, decisions=(decision,)
    )
    legislative = resolve_turn(state, decisions).report.legislative
    assert legislative is not None
    return legislative.model_dump(mode="json")


def _valid_failed_legislative_report_dict() -> dict:
    """`deficit_demo` fails the walkthrough proposal unaided: 47/100 against a required 51."""
    state = load_scenario_file(SCENARIO_DIR / "deficit_demo.yaml")
    current = state.world.countries["strapped"].finance.tax_policy.personal_income_rate_bps
    decision = BudgetDecision(personal_income_rate_bps=current + 500)
    decisions = DecisionSet(
        expected_turn=state.turn, expected_state_version=state.state_version, decisions=(decision,)
    )
    legislative = resolve_turn(state, decisions).report.legislative
    assert legislative is not None
    assert legislative.outcome is LegislativeOutcome.FAILED_LEGISLATIVE
    return legislative.model_dump(mode="json")


def _valid_bicameral_influence_report_dict(*, political_capital: int = 50) -> dict:
    """`civic_union/mainstream` is seated in both `tiny_valid` chambers and receives one real
    allocation -- the genuine (non-hand-built) bicameral-influence case."""
    state = load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml")
    current = state.world.countries["arken"].finance.tax_policy.personal_income_rate_bps
    decision = BudgetDecision(
        personal_income_rate_bps=current + 500,
        influence=(
            InfluenceAllocation(
                party_id="civic_union", bloc_id="mainstream", political_capital=political_capital
            ),
        ),
    )
    decisions = DecisionSet(
        expected_turn=state.turn, expected_state_version=state.state_version, decisions=(decision,)
    )
    legislative = resolve_turn(state, decisions).report.legislative
    assert legislative is not None
    return legislative.model_dump(mode="json")


def _valid_no_proposal_report_dict() -> dict:
    state = make_game_state(turn=0, state_version=0)
    decisions = DecisionSet(
        expected_turn=state.turn, expected_state_version=state.state_version, decisions=()
    )
    legislative = resolve_turn(state, decisions).report.legislative
    assert legislative is not None
    assert legislative.outcome is LegislativeOutcome.NO_PROPOSAL
    return legislative.model_dump(mode="json")


def _valid_decree_report_dict() -> dict:
    politics = make_politics(
        legislature=Legislature.NONE,
        decree_authority=DecreeAuthority.UNLIMITED,
        political_capital=500,
    )
    country = make_country("testland", politics=politics)
    state = make_game_state(countries={"testland": country}, player_country_id="testland")
    decision = BudgetDecision(personal_income_rate_bps=2_500, route=ProposalRoute.DECREE)
    decisions = DecisionSet(
        expected_turn=state.turn, expected_state_version=state.state_version, decisions=(decision,)
    )
    legislative = resolve_turn(state, decisions).report.legislative
    assert legislative is not None
    assert legislative.outcome is LegislativeOutcome.ENACTED_BY_DECREE
    return legislative.model_dump(mode="json")


def _injectable_chamber_and_bloc() -> tuple[dict, dict]:
    """A single, internally-valid `(chamber, bloc)` pair -- safe to splice into an otherwise
    chamber/bloc-free dict (`NO_PROPOSAL`/`ENACTED_BY_DECREE`) to prove the matrix validator
    rejects their mere *presence*, independent of whether the pair is itself well-formed."""
    report = _minimal_legislative_report()
    data = report.model_dump(mode="json")
    return data["chambers"][0], data["blocs"][0]


# =============================================================================
# 1. baseline support
# =============================================================================


@_LEGISLATIVE_LOADERS
def test_1_corrupted_baseline_support_is_rejected(load) -> None:
    data = _valid_legislative_report_dict()
    data["blocs"][0]["baseline_support_bps"] += 1
    with pytest.raises(ValidationError, match="baseline_support_bps"):
        load(data)


# =============================================================================
# 2. policy compatibility, including all four spending branches
# =============================================================================


@_LEGISLATIVE_LOADERS
def test_2_corrupted_policy_compatibility_is_rejected(load) -> None:
    data = _valid_legislative_report_dict()
    data["blocs"][0]["policy_compatibility_bps"] += 1
    with pytest.raises(ValidationError, match="policy_compatibility_bps"):
        load(data)


@pytest.mark.parametrize(
    "opening,proposed,direction,intensity",
    [
        pytest.param(0, 0, ChangeDirection.UNCHANGED, 0, id="zero_to_zero"),
        pytest.param(0, 500_000, ChangeDirection.INCREASE, 10_000, id="zero_to_positive_maxed"),
        pytest.param(500_000, 0, ChangeDirection.DECREASE, 10_000, id="positive_to_zero_maxed"),
        pytest.param(
            1_000_000, 1_050_000, ChangeDirection.INCREASE, 5_000, id="positive_to_positive"
        ),
    ],
)
def test_2_all_four_spending_branches_are_individually_valid(
    opening: int, proposed: int, direction: ChangeDirection, intensity: int
) -> None:
    """The four exhaustive branches of `_spending_change_representation_matches_totals` (R7),
    each independently constructed and shown to validate on its own -- proving the formula is
    genuinely branch-complete, not merely "the one branch a real scenario happens to reach"."""
    report = _minimal_legislative_report(
        opening_total_program_spending=opening,
        proposed_total_program_spending=proposed,
        spending_direction=direction,
        spending_intensity_bps=intensity,
    )
    assert report.spending_direction is direction
    assert report.spending_intensity_bps == intensity


@pytest.mark.parametrize(
    "opening,proposed,direction,intensity",
    [
        pytest.param(0, 0, ChangeDirection.UNCHANGED, 0, id="zero_to_zero"),
        pytest.param(0, 500_000, ChangeDirection.INCREASE, 10_000, id="zero_to_positive_maxed"),
        pytest.param(500_000, 0, ChangeDirection.DECREASE, 10_000, id="positive_to_zero_maxed"),
        pytest.param(
            1_000_000, 1_050_000, ChangeDirection.INCREASE, 5_000, id="positive_to_positive"
        ),
    ],
)
@_LEGISLATIVE_LOADERS
def test_2_each_spending_branch_rejects_a_corrupted_intensity(
    load, opening: int, proposed: int, direction: ChangeDirection, intensity: int
) -> None:
    data = _minimal_legislative_report(
        opening_total_program_spending=opening,
        proposed_total_program_spending=proposed,
        spending_direction=direction,
        spending_intensity_bps=intensity,
    ).model_dump(mode="json")
    data["spending_intensity_bps"] += 1
    with pytest.raises(ValidationError, match="spending_intensity_bps"):
        load(data)


@_LEGISLATIVE_LOADERS
def test_2_spending_direction_disagreeing_with_totals_is_rejected(load) -> None:
    """`opening == proposed` demands `UNCHANGED`; claiming `INCREASE` over an identical total
    must be rejected even though the (saturated, moot) intensity could coincidentally match."""
    data = _minimal_legislative_report(
        opening_total_program_spending=1_000_000,
        proposed_total_program_spending=1_000_000,
        spending_direction=ChangeDirection.UNCHANGED,
        spending_intensity_bps=0,
    ).model_dump(mode="json")
    data["spending_direction"] = "increase"
    with pytest.raises(ValidationError, match="spending_direction"):
        load(data)


# =============================================================================
# 3. raw support
# =============================================================================


@_LEGISLATIVE_LOADERS
def test_3_corrupted_raw_support_is_rejected(load) -> None:
    data = _valid_legislative_report_dict()
    data["blocs"][0]["raw_support_bps"] += 1
    with pytest.raises(ValidationError, match="raw_support_bps"):
        load(data)


# =============================================================================
# 4. influence
# =============================================================================


@_LEGISLATIVE_LOADERS
def test_4_corrupted_influence_is_rejected(load) -> None:
    data = _valid_bicameral_influence_report_dict(political_capital=50)
    idx = _row_index(data, party_id="civic_union", bloc_id="mainstream", chamber="lower")
    data["blocs"][idx]["influence_bps"] += 1
    with pytest.raises(ValidationError, match="influence_bps"):
        load(data)


@_LEGISLATIVE_LOADERS
def test_4_repeated_bloc_rows_with_inconsistent_allocation_is_rejected(load) -> None:
    """Report corrections §3, special case: the same `(party_id, bloc_id)` seated in two chambers
    must show identical `political_capital_allocated`/`influence_bps` on both rows."""
    data = _minimal_bicameral_report(lower_allocated=50, upper_allocated=50).model_dump(mode="json")
    upper_idx = _row_index(data, party_id="gov", bloc_id="core", chamber="upper")
    data["blocs"][upper_idx]["political_capital_allocated"] = 60
    data["blocs"][upper_idx]["influence_bps"] = 600
    with pytest.raises(ValidationError, match="inconsistent political_capital_allocated"):
        load(data)


def test_4_repeated_bloc_rows_with_inconsistent_influence_is_rejected() -> None:
    """Same shape as the allocation case above, but `influence_bps` alone disagrees while
    `political_capital_allocated` matches -- the second half of `_bicameral_allocation_is_
    consistent_per_bloc_identity`.

    Unlike every other case in this file, this branch is **not** reachable through
    `model_validate`/`model_validate_json`: `_influence_matches_allocation` (validator #4 on
    `BlocVoteReport` itself) already forces `influence_bps` to be a deterministic function of
    `political_capital_allocated`, so two rows with matching allocations can never independently
    arrive with differing influence through any normally-constructed input -- the allocation-
    mismatch check above always fires first in practice. Isolated the same way
    `test_political_report.py::test_baseline_lifecycle_none_opening_with_nonzero_change_is_
    rejected` isolates its own otherwise-unreachable branch: build every row through the real
    constructor, `model_construct` only to splice in the one otherwise-unreachable combination,
    then invoke the target validator method directly."""
    row1 = _bloc_row(chamber=LegislativeChamber.LOWER, seats=60, allocated=50)
    row2_valid = _bloc_row(chamber=LegislativeChamber.UPPER, seats=40, allocated=50)
    row2 = BlocVoteReport.model_construct(**{**dict(row2_valid), "influence_bps": 501})
    report = _minimal_bicameral_report(lower_allocated=50, upper_allocated=50)
    bypassed = LegislativeReport.model_construct(**{**dict(report), "blocs": (row1, row2)})
    with pytest.raises(ValueError, match="inconsistent influence_bps"):
        LegislativeReport._bicameral_allocation_is_consistent_per_bloc_identity(bypassed)


# =============================================================================
# 5. final support
# =============================================================================


@_LEGISLATIVE_LOADERS
def test_5_corrupted_final_support_is_rejected(load) -> None:
    data = _valid_legislative_report_dict()
    data["blocs"][0]["final_support_bps"] += 1
    with pytest.raises(ValidationError, match="final_support_bps"):
        load(data)


# =============================================================================
# 6. discipline amplification
# =============================================================================


@_LEGISLATIVE_LOADERS
def test_6_corrupted_effective_support_is_rejected(load) -> None:
    data = _valid_legislative_report_dict()
    # A row with nonzero discipline, so the amplification term is genuinely nonzero -- proving
    # the check exercises the discipline arithmetic, not merely a discipline=0 identity.
    row = next(r for r in data["blocs"] if r["discipline_bps"] > 0)
    row["effective_support_bps"] += 1
    with pytest.raises(ValidationError, match="effective_support_bps"):
        load(data)


# =============================================================================
# 7. numerator / base / remainder / supporting-seat arithmetic
# =============================================================================


@pytest.mark.parametrize("field", ["numerator", "base_seats", "remainder", "supporting_seats"])
@_LEGISLATIVE_LOADERS
def test_7_corrupted_apportionment_arithmetic_field_is_rejected(load, field: str) -> None:
    data = _valid_legislative_report_dict()
    # A full-support row (mainstream, effective 10,000 -> base==seats, remainder==0) is corrupted
    # *upward* by one: `remainder`/`base_seats` are already at their floor (0 / seats respectively
    # is base_seats' ceiling, not floor -- remainder=0 specifically can't go below its own
    # StrictBps(ge=0) field bound), and the mismatch is caught by the validator's own "does not
    # match" message either way, so +1 is the direction that never trips an unrelated field-level
    # bound first.
    row = next(
        r for r in data["blocs"] if r["party_id"] == "civic_union" and r["bloc_id"] == "mainstream"
    )
    row[field] += 1
    with pytest.raises(ValidationError, match="does not match"):
        load(data)


# =============================================================================
# 8. chamber-level largest-remainder bonus allocation
# =============================================================================


@_LEGISLATIVE_LOADERS
def test_8_corrupted_bonus_seat_ordering_is_rejected(load) -> None:
    """(R4) A bonus seat moved from the row with the largest remainder to a row with a smaller
    one, while every individual row stays locally self-consistent -- the corruption class only
    `_chamber_apportionment_is_correct`'s cross-row replay can catch."""
    data = _valid_legislative_report_dict()
    chamber_report = next(c for c in data["chambers"] if c["extras_awarded"] >= 1)
    chamber_name = chamber_report["chamber"]
    rows = [row for row in data["blocs"] if row["chamber"] == chamber_name]

    bonus_row = next(row for row in rows if row["bonus_seat"])
    false_rows = sorted(
        (row for row in rows if not row["bonus_seat"] and row["base_seats"] < row["seats"]),
        key=lambda r: r["remainder"],
    )
    assert false_rows, "need at least one bonus-eligible non-bonus row to move the bonus to"
    target_row = false_rows[0]
    assert target_row["remainder"] < bonus_row["remainder"]

    bonus_idx = _row_index(
        data, party_id=bonus_row["party_id"], bloc_id=bonus_row["bloc_id"], chamber=chamber_name
    )
    target_idx = _row_index(
        data, party_id=target_row["party_id"], bloc_id=target_row["bloc_id"], chamber=chamber_name
    )
    data["blocs"][bonus_idx]["bonus_seat"] = False
    data["blocs"][bonus_idx]["supporting_seats"] = data["blocs"][bonus_idx]["base_seats"]
    data["blocs"][target_idx]["bonus_seat"] = True
    data["blocs"][target_idx]["supporting_seats"] = data["blocs"][target_idx]["base_seats"] + 1

    with pytest.raises(ValidationError, match="largest-remainder ordering"):
        load(data)


@_LEGISLATIVE_LOADERS
def test_8_corrupted_chamber_aggregate_target_total_is_rejected(load) -> None:
    """The chamber-level aggregate (`target_total`/`extras_awarded`) is independently replayed
    from every bloc row -- corrupting it alone, with no per-row change, must still be caught."""
    data = _valid_legislative_report_dict()
    data["chambers"][0]["target_total"] += 1
    data["chambers"][0]["supporting_seats"] += 1
    with pytest.raises(ValidationError, match="does not match"):
        load(data)


@_LEGISLATIVE_LOADERS
def test_8_corrupted_extras_awarded_is_rejected(load) -> None:
    data = _valid_legislative_report_dict()
    data["chambers"][0]["extras_awarded"] += 1
    with pytest.raises(ValidationError, match="extras_awarded"):
        load(data)


# =============================================================================
# 9. strict required majority
# =============================================================================


@_LEGISLATIVE_LOADERS
def test_9_corrupted_required_yes_seats_is_rejected(load) -> None:
    data = _valid_legislative_report_dict()
    data["chambers"][0]["required_yes_seats"] += 1
    with pytest.raises(ValidationError, match="required_yes_seats"):
        load(data)


@_LEGISLATIVE_LOADERS
def test_9_required_majority_lowered_by_one_to_smuggle_tie_passage_is_rejected(load) -> None:
    """Special case: taking a genuine 50/100 tie (fails, required 51) and lowering the required
    majority to 50 so it reads as a pass. `_required_yes_seats_is_strict_majority` independently
    re-derives `total_seats // 2 + 1`, so the lowered bar is rejected on its own terms --
    regardless of what `passed`/`outcome` claim alongside it."""
    data = _tied_50_100_report().model_dump(mode="json")
    data["chambers"][0]["required_yes_seats"] = 50
    data["chambers"][0]["passed"] = True
    data["chambers"][0]["shortfall_seats"] = 0
    data["outcome"] = "passed_legislative"
    with pytest.raises(ValidationError, match="required_yes_seats"):
        load(data)


# =============================================================================
# 10. passed status and shortfall
# =============================================================================


@_LEGISLATIVE_LOADERS
def test_10_corrupted_passed_status_is_rejected(load) -> None:
    data = _valid_failed_legislative_report_dict()
    chamber = data["chambers"][0]
    assert chamber["passed"] is False
    chamber["passed"] = True
    with pytest.raises(ValidationError, match="passed"):
        load(data)


@_LEGISLATIVE_LOADERS
def test_10_corrupted_shortfall_seats_is_rejected(load) -> None:
    data = _valid_failed_legislative_report_dict()
    data["chambers"][0]["shortfall_seats"] += 1
    with pytest.raises(ValidationError, match="shortfall_seats"):
        load(data)


# =============================================================================
# 11. complete route/outcome/chamber matrix
# =============================================================================


@_LEGISLATIVE_LOADERS
def test_11_passed_legislative_with_zero_chambers_is_rejected(load) -> None:
    """`all([])` regression: a legislative outcome must never validate on an empty chamber list."""
    data = _valid_legislative_report_dict()
    assert data["outcome"] == "passed_legislative"
    data["chambers"] = []
    data["blocs"] = []
    with pytest.raises(ValidationError, match="zero chambers"):
        load(data)


@_LEGISLATIVE_LOADERS
def test_11_failed_legislative_with_every_chamber_passing_is_rejected(load) -> None:
    data = _valid_legislative_report_dict()
    assert data["outcome"] == "passed_legislative"
    assert all(c["passed"] for c in data["chambers"])
    data["outcome"] = "failed_legislative"
    with pytest.raises(ValidationError, match="FAILED_LEGISLATIVE requires at least one chamber"):
        load(data)


@_LEGISLATIVE_LOADERS
def test_11_no_proposal_with_non_none_route_is_rejected(load) -> None:
    data = _valid_no_proposal_report_dict()
    assert data["route"] is None
    data["route"] = "legislative"
    with pytest.raises(ValidationError, match="route=None"):
        load(data)


@_LEGISLATIVE_LOADERS
def test_11_no_proposal_with_chamber_and_bloc_rows_is_rejected(load) -> None:
    data = _valid_no_proposal_report_dict()
    assert data["chambers"] == [] and data["blocs"] == []
    chamber, bloc = _injectable_chamber_and_bloc()
    data["chambers"] = [chamber]
    data["blocs"] = [bloc]
    with pytest.raises(ValidationError, match="no chamber or bloc rows"):
        load(data)


@_LEGISLATIVE_LOADERS
def test_11_no_proposal_with_nonzero_commitment_is_rejected(load) -> None:
    data = _valid_no_proposal_report_dict()
    assert data["political_capital_committed"] == 0
    data["political_capital_committed"] = 1
    with pytest.raises(ValidationError, match="commit zero political capital"):
        load(data)


@_LEGISLATIVE_LOADERS
def test_11_decree_with_chamber_and_bloc_rows_is_rejected(load) -> None:
    data = _valid_decree_report_dict()
    assert data["chambers"] == [] and data["blocs"] == []
    chamber, bloc = _injectable_chamber_and_bloc()
    data["chambers"] = [chamber]
    data["blocs"] = [bloc]
    with pytest.raises(ValidationError, match="no chamber or bloc rows"):
        load(data)


# =============================================================================
# 12. unique-target political-capital commitment
# =============================================================================


@_LEGISLATIVE_LOADERS
def test_12_bicameral_commitment_is_reconstructed_from_unique_targets_not_summed_rows(load) -> None:
    """Report corrections §3, special case: `civic_union/mainstream` is seated in both `tiny_valid`
    chambers and receives one allocation. The real commitment is that single allocation, not the
    allocation summed once per chamber row it happens to appear in ("bicameral influence counted
    twice")."""
    data = _valid_bicameral_influence_report_dict(political_capital=50)
    assert data["political_capital_committed"] == 50
    mainstream_rows = [
        row
        for row in data["blocs"]
        if (row["party_id"], row["bloc_id"]) == ("civic_union", "mainstream")
    ]
    assert len(mainstream_rows) == 2
    assert all(row["political_capital_allocated"] == 50 for row in mainstream_rows)

    data["political_capital_committed"] = 100  # the double-counted bug this guards against
    with pytest.raises(ValidationError, match="political_capital_committed"):
        load(data)


@_LEGISLATIVE_LOADERS
def test_12_decree_commitment_disagreeing_with_the_fixed_cost_is_rejected(load) -> None:
    data = _valid_decree_report_dict()
    assert data["political_capital_committed"] == DECREE_POLITICAL_CAPITAL_COST
    data["political_capital_committed"] = DECREE_POLITICAL_CAPITAL_COST + 1
    with pytest.raises(ValidationError, match="political_capital_committed"):
        load(data)


# =============================================================================
# 13. commitment bounded by opening capital
# =============================================================================


def test_13_commitment_exactly_at_opening_capital_is_accepted() -> None:
    report = _minimal_legislative_report(allocated=300, opening_political_capital=300)
    assert report.political_capital_committed == 300


@_LEGISLATIVE_LOADERS
def test_13_commitment_one_point_above_opening_capital_is_rejected(load) -> None:
    """Special case: 301 committed against an opening of 300. A 301-committed report can never be
    *constructed* successfully at all (validator #13 runs at construction time same as any other
    -- there's no "valid, then corrupted" object to dump), so the dict is built from a genuinely
    valid 300/300 boundary report and then patched directly: `allocated`/`influence_bps` move to
    301 together (keeping validator #12's unique-target reconstruction satisfied, so #13 is the
    only thing left to reject it on)."""
    data = _minimal_legislative_report(allocated=300, opening_political_capital=300).model_dump(
        mode="json"
    )
    data["political_capital_committed"] = 301
    data["blocs"][0]["political_capital_allocated"] = 301
    data["blocs"][0]["influence_bps"] = min(MAX_INFLUENCE_BPS, 301 * INFLUENCE_BPS_PER_CAPITAL)
    with pytest.raises(ValidationError, match="exceeds opening_political_capital"):
        load(data)


# =============================================================================
# General round trip
# =============================================================================


@_LEGISLATIVE_LOADERS
def test_a_valid_legislative_report_round_trips(load) -> None:
    data = _valid_legislative_report_dict()
    load(data)


# =============================================================================
# TurnReport integration boundary: legislative <-> political/finance cross-checks
# =============================================================================


def _turn_report_dict_with_mainstream_allocation(political_capital: int) -> dict:
    state = load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml")
    current = state.world.countries["arken"].finance.tax_policy.personal_income_rate_bps
    decision = BudgetDecision(
        personal_income_rate_bps=current + 500,
        influence=(
            InfluenceAllocation(
                party_id="civic_union", bloc_id="mainstream", political_capital=political_capital
            ),
        ),
    )
    decisions = DecisionSet(
        expected_turn=state.turn, expected_state_version=state.state_version, decisions=(decision,)
    )
    return resolve_turn(state, decisions).report.model_dump(mode="json")


def _no_proposal_turn_report_dict(*, political_capital: int) -> dict:
    politics = make_politics(political_capital=political_capital)
    country = make_country("testland", politics=politics)
    state = make_game_state(countries={"testland": country}, player_country_id="testland")
    decisions = DecisionSet(
        expected_turn=state.turn, expected_state_version=state.state_version, decisions=()
    )
    return resolve_turn(state, decisions).report.model_dump(mode="json")


def _bump_political_spent(data: dict, *, new_spent: int) -> None:
    political = data["political"]
    political["political_capital_spent"] = new_spent
    political["closing_political_capital"] = min(
        political["political_capital_capacity"],
        political["opening_political_capital"]
        + political["political_capital_regeneration"]
        - new_spent,
    )


def _bump_political_opening_capital(data: dict, *, new_opening: int) -> None:
    political = data["political"]
    political["opening_political_capital"] = new_opening
    political["closing_political_capital"] = min(
        political["political_capital_capacity"],
        new_opening
        + political["political_capital_regeneration"]
        - political["political_capital_spent"],
    )


@_TURN_LOADERS
def test_matched_legislative_and_political_commitment_constructs(load) -> None:
    data = _turn_report_dict_with_mainstream_allocation(50)
    assert data["legislative"]["political_capital_committed"] == 50
    assert data["political"]["political_capital_spent"] == 50
    load(data)  # must not raise


@_TURN_LOADERS
def test_commitment_mismatch_rejected_when_legislative_side_changes(load) -> None:
    """The `legislative` sub-report is swapped for a real, independently-valid resolution of the
    *same* starting state with a different (but still real) influence spend -- both nested models
    are individually self-consistent; only the two reports' agreement with each other is broken."""
    baseline = _turn_report_dict_with_mainstream_allocation(50)
    other = _turn_report_dict_with_mainstream_allocation(51)
    assert other["legislative"]["political_capital_committed"] == 51
    data = dict(baseline)
    data["legislative"] = other["legislative"]
    with pytest.raises(ValidationError, match="political_capital_committed"):
        load(data)


@_TURN_LOADERS
def test_commitment_mismatch_rejected_when_political_side_changes(load) -> None:
    data = _turn_report_dict_with_mainstream_allocation(50)
    _bump_political_spent(data, new_spent=51)
    with pytest.raises(ValidationError, match="political_capital_committed"):
        load(data)


@_TURN_LOADERS
def test_opening_capital_mismatch_rejected_when_legislative_side_changes(load) -> None:
    baseline = _no_proposal_turn_report_dict(political_capital=500)
    other = _no_proposal_turn_report_dict(political_capital=501)
    assert other["legislative"]["opening_political_capital"] == 501
    data = dict(baseline)
    data["legislative"] = other["legislative"]
    with pytest.raises(ValidationError, match="opening_political_capital"):
        load(data)


@_TURN_LOADERS
def test_opening_capital_mismatch_rejected_when_political_side_changes(load) -> None:
    data = _no_proposal_turn_report_dict(political_capital=500)
    _bump_political_opening_capital(data, new_opening=501)
    with pytest.raises(ValidationError, match="opening_political_capital"):
        load(data)


@_TURN_LOADERS
def test_opening_spending_mismatch_rejected_when_legislative_side_changes(load) -> None:
    data = _no_proposal_turn_report_dict(political_capital=500)
    legislative = data["legislative"]
    assert (
        legislative["opening_total_program_spending"]
        == legislative["proposed_total_program_spending"]
    )
    legislative["opening_total_program_spending"] += 100
    legislative["proposed_total_program_spending"] += 100  # keep NO_PROPOSAL's own equality intact
    with pytest.raises(ValidationError, match="opening_total_program_spending"):
        load(data)
