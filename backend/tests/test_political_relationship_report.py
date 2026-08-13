"""Validation-hardening audit for `BlocRelationshipMemoryReport`/`PoliticalRelationshipReport`'s
self-validation (Phase 3B2B), mirroring `test_political_capital_report.py`'s own audit pattern.

`BlocRelationshipMemoryReport` (the row) declares 5 self-validators; `PoliticalRelationshipReport`
(the ninth top-level report) declares 5 more. The two genuinely cross-report checks that involve
this report -- the relocated investment/ledger correspondence and the proposal-vs-`LegislativeReport`
match -- are `TurnReport` cross-validators and are audited in `test_political_capital_report.py`
alongside the other `TurnReport` cross-validators, not here.

Every real report used below comes from the actual `resolve_turn` resolver against
`deficit_demo.yaml`/`decree_state.yaml` -- nothing is hand-built except where a real turn cannot
reach the case cleanly (isolating one row's arithmetic without a whole turn's other fields moving
too).
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.content.scenarios import load_scenario_file
from app.simulation.decisions import (
    BlocInvestment,
    BlocRelationshipInvestmentDecision,
    BudgetDecision,
    DecisionSet,
)
from app.simulation.legislature import ChangeDirection, LegislativeOutcome, ProposalRoute
from app.simulation.political_memory import (
    combine_relationship_components,
    enacted_policy_reaction_bps,
    relationship_decay_bps,
)
from app.simulation.relationships import relationship_gain_bps
from app.simulation.report import BlocRelationshipMemoryReport, PoliticalRelationshipReport
from app.simulation.resolver import resolve_turn
from tests.conftest import SCENARIO_DIR, make_game_state

_PRR_LOADERS = pytest.mark.parametrize(
    "load",
    [
        pytest.param(PoliticalRelationshipReport.model_validate, id="model_validate"),
        pytest.param(
            lambda data: PoliticalRelationshipReport.model_validate_json(json.dumps(data)),
            id="model_validate_json",
        ),
    ],
)


def _decisions_for(state, *decision_objs) -> DecisionSet:  # type: ignore[no-untyped-def]
    ordered = sorted(decision_objs, key=lambda d: d.kind)
    return DecisionSet(
        expected_turn=state.turn,
        expected_state_version=state.state_version,
        decisions=tuple(ordered),
    )


def _no_proposal_report_dict() -> dict:
    """A fresh scenario, no decisions at all: every bloc opens exactly at its authored baseline
    (deviation 0), so no row qualifies for §8's row-coverage rule -- an empty `blocs` tuple."""
    state = make_game_state(turn=0, state_version=0)
    resolution = resolve_turn(state, _decisions_for(state))
    report = resolution.report.political_relationship
    assert report is not None
    assert report.blocs == ()
    return report.model_dump(mode="json")


def _investment_only_report_dict() -> dict:
    """`deficit_demo`, an investment with no budget decision at all -- `NO_PROPOSAL` with exactly
    one nonzero-investment row (every scenario opens each bloc exactly at its authored baseline,
    so decay is 0 on this first turn; §8's row-coverage rule still gives this bloc a row purely
    because it received an investment)."""
    state = load_scenario_file(SCENARIO_DIR / "deficit_demo.yaml")
    investment = BlocRelationshipInvestmentDecision(
        investments=(
            BlocInvestment(party_id="citizens_bloc", bloc_id="moderates", political_capital=100),
        )
    )
    resolution = resolve_turn(state, _decisions_for(state, investment))
    assert resolution.report.legislative is not None
    assert resolution.report.legislative.outcome is LegislativeOutcome.NO_PROPOSAL
    report = resolution.report.political_relationship
    assert report is not None
    row = next(
        r for r in report.blocs if r.party_id == "citizens_bloc" and r.bloc_id == "moderates"
    )
    assert row.investment_capital == 100
    return report.model_dump(mode="json")


def _genuine_legislative_report_dict() -> dict:
    """`tiny_valid`, a genuine +500bps tax rise, passed legislatively unaided (regime A) -- every
    authored bloc gets a row (§8's row-coverage rule: policy enacted), several with a nonzero
    policy reaction."""
    state = load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml")
    current = state.world.countries["arken"].finance.tax_policy.personal_income_rate_bps
    decision = BudgetDecision(personal_income_rate_bps=current + 500)
    resolution = resolve_turn(state, _decisions_for(state, decision))
    assert resolution.report.legislative is not None
    assert resolution.report.legislative.outcome is LegislativeOutcome.PASSED_LEGISLATIVE
    report = resolution.report.political_relationship
    assert report is not None
    assert any(row.policy_reaction_component_bps != 0 for row in report.blocs)
    return report.model_dump(mode="json")


def _genuine_decree_report_dict() -> dict:
    """`decree_state`, a genuine +500bps tax rise enacted by decree -- every seated bloc gets a
    nonzero decree-bypass component alongside its policy reaction."""
    state = load_scenario_file(SCENARIO_DIR / "decree_state.yaml")
    decision = BudgetDecision(personal_income_rate_bps=2_500, route=ProposalRoute.DECREE)
    resolution = resolve_turn(state, _decisions_for(state, decision))
    assert resolution.report.legislative is not None
    assert resolution.report.legislative.outcome is LegislativeOutcome.ENACTED_BY_DECREE
    report = resolution.report.political_relationship
    assert report is not None
    assert all(row.decree_bypass_component_bps == -200 for row in report.blocs)
    assert any(row.policy_reaction_component_bps != 0 for row in report.blocs)
    return report.model_dump(mode="json")


def _unchanged_decree_report_dict() -> dict:
    """`decree_state`, re-decreeing the currently-active rate -- `UNCHANGED`, so every row's policy
    component is exactly 0 while the decree-bypass component is still applied every seated bloc."""
    state = load_scenario_file(SCENARIO_DIR / "decree_state.yaml")
    current = state.world.countries["valdrun"].finance.tax_policy.personal_income_rate_bps
    decision = BudgetDecision(personal_income_rate_bps=current, route=ProposalRoute.DECREE)
    resolution = resolve_turn(state, _decisions_for(state, decision))
    assert resolution.report.legislative is not None
    assert resolution.report.legislative.outcome is LegislativeOutcome.ENACTED_BY_DECREE
    report = resolution.report.political_relationship
    assert report is not None
    assert all(row.policy_reaction_component_bps == 0 for row in report.blocs)
    assert all(row.decree_bypass_component_bps == -200 for row in report.blocs)
    return report.model_dump(mode="json")


@_PRR_LOADERS
@pytest.mark.parametrize(
    "builder",
    [
        _no_proposal_report_dict,
        _investment_only_report_dict,
        _genuine_legislative_report_dict,
        _genuine_decree_report_dict,
        _unchanged_decree_report_dict,
    ],
)
def test_a_valid_report_round_trips(load, builder) -> None:
    load(builder())


# =============================================================================
# Row validator 1: opening_deviation_bps matches baseline and opening
# =============================================================================


def _consistent_row(
    *,
    baseline_relationship_bps: int = -2_000,
    opening_relationship_bps: int = 0,
    investment_capital: int = 0,
    tax_preference_bps: int = -2_000,
    spending_preference_bps: int = 0,
    tax_direction: ChangeDirection = ChangeDirection.UNCHANGED,
    tax_intensity_bps: int = 0,
    spending_direction: ChangeDirection = ChangeDirection.UNCHANGED,
    spending_intensity_bps: int = 0,
    decree_bypass_component_bps: int = 0,
) -> BlocRelationshipMemoryReport:
    """Hand-built, but every field independently re-derived from the SAME formulas the row's own
    validators check -- so a genuinely valid row, not a fixture that happens to pass."""
    opening_deviation_bps = opening_relationship_bps - baseline_relationship_bps
    decay_component_bps = relationship_decay_bps(
        opening_relationship_bps=opening_relationship_bps,
        baseline_relationship_bps=baseline_relationship_bps,
    )
    investment_component_bps = (
        relationship_gain_bps(
            opening_relationship_bps=opening_relationship_bps,
            political_capital=investment_capital,
        )
        if investment_capital > 0
        else 0
    )
    policy_reaction_component_bps = enacted_policy_reaction_bps(
        tax_preference_bps=tax_preference_bps,
        tax_direction=tax_direction,
        tax_intensity_bps=tax_intensity_bps,
        spending_preference_bps=spending_preference_bps,
        spending_direction=spending_direction,
        spending_intensity_bps=spending_intensity_bps,
    )
    uncapped, applied, closing = combine_relationship_components(
        opening_relationship_bps=opening_relationship_bps,
        decay_component_bps=decay_component_bps,
        investment_component_bps=investment_component_bps,
        policy_reaction_component_bps=policy_reaction_component_bps,
        decree_bypass_component_bps=decree_bypass_component_bps,
    )
    return BlocRelationshipMemoryReport(
        party_id="citizens_bloc",
        bloc_id="moderates",
        baseline_relationship_bps=baseline_relationship_bps,
        opening_relationship_bps=opening_relationship_bps,
        opening_deviation_bps=opening_deviation_bps,
        decay_component_bps=decay_component_bps,
        investment_component_bps=investment_component_bps,
        investment_capital=investment_capital,
        tax_preference_bps=tax_preference_bps,
        spending_preference_bps=spending_preference_bps,
        policy_reaction_component_bps=policy_reaction_component_bps,
        decree_bypass_component_bps=decree_bypass_component_bps,
        uncapped_total_change_bps=uncapped,
        applied_total_change_bps=applied,
        closing_relationship_bps=closing,
    )


def test_a_genuinely_consistent_row_constructs() -> None:
    row = _consistent_row()
    assert row.opening_deviation_bps == 2_000
    assert row.decay_component_bps == -250
    assert row.closing_relationship_bps == -250


def test_row_1_corrupted_opening_deviation_is_rejected() -> None:
    data = _consistent_row().model_dump(mode="json")
    data["opening_deviation_bps"] += 1
    with pytest.raises(ValidationError, match="opening_deviation_bps=.* does not match"):
        BlocRelationshipMemoryReport.model_validate(data)


def test_row_2_corrupted_decay_component_is_rejected() -> None:
    data = _consistent_row().model_dump(mode="json")
    data["decay_component_bps"] += 1
    with pytest.raises(ValidationError, match="decay_component_bps=.* does not match"):
        BlocRelationshipMemoryReport.model_validate(data)


def test_row_2_zero_deviation_gives_zero_decay() -> None:
    row = _consistent_row(baseline_relationship_bps=0, opening_relationship_bps=0)
    assert row.decay_component_bps == 0


def test_row_3_corrupted_investment_component_is_rejected() -> None:
    data = _consistent_row(investment_capital=100).model_dump(mode="json")
    data["investment_component_bps"] += 1
    with pytest.raises(ValidationError, match="investment_component_bps=.* does not match"):
        BlocRelationshipMemoryReport.model_validate(data)


def test_row_3_a_truncated_to_zero_gain_with_positive_capital_is_rejected() -> None:
    """A tiny `investment_capital` against a near-ceiling opening relationship truncates
    `relationship_gain_bps` to exactly 0 -- the formula-match check (validator 3's first half)
    would happily accept `investment_component_bps=0` here, since 0 IS what the formula returns.
    The coincidence check (validator 3's second half) is what actually rejects this: a report row
    may never claim capital was committed to an investment that provably bought nothing -- the
    resolver's own slot-1 gate refuses this decision before a report is ever built (R13), and this
    is the report-level backstop for the same rule."""
    with pytest.raises(ValidationError, match="investment_capital == 0 must exactly coincide"):
        _consistent_row(
            opening_relationship_bps=9_999, baseline_relationship_bps=0, investment_capital=1
        )


def test_row_4_corrupted_uncapped_total_is_rejected() -> None:
    data = _consistent_row().model_dump(mode="json")
    data["uncapped_total_change_bps"] += 1
    with pytest.raises(ValidationError, match="uncapped_total_change_bps=.* does not match"):
        BlocRelationshipMemoryReport.model_validate(data)


def test_row_5_corrupted_closing_relationship_is_rejected() -> None:
    data = _consistent_row().model_dump(mode="json")
    data["closing_relationship_bps"] += 1
    with pytest.raises(ValidationError, match="closing_relationship_bps=.* does not match"):
        BlocRelationshipMemoryReport.model_validate(data)


def test_row_5_corrupted_applied_change_is_rejected() -> None:
    data = _consistent_row().model_dump(mode="json")
    data["applied_total_change_bps"] += 1
    with pytest.raises(ValidationError, match="applied_total_change_bps=.* does not match"):
        BlocRelationshipMemoryReport.model_validate(data)


def test_row_5_boundary_truncation_is_visible_not_absorbed() -> None:
    """At the +10,000 ceiling, `uncapped_total_change_bps` and `applied_total_change_bps`
    genuinely differ -- the clamp truncates, and neither is silently adjusted to hide it. Decay
    alone (deviation 0) and investment alone (strictly less than the remaining gap, by 3B2A's own
    diminishing-returns guarantee) can never reach the ceiling on their own, so this combines a
    small remaining gap with the maximum possible investment AND a maximal positive policy
    reaction to genuinely cross it."""
    row = _consistent_row(
        baseline_relationship_bps=9_950,
        opening_relationship_bps=9_950,
        investment_capital=200,
        tax_preference_bps=10_000,
        tax_direction=ChangeDirection.INCREASE,
        tax_intensity_bps=10_000,
    )
    assert row.uncapped_total_change_bps != row.applied_total_change_bps
    assert row.closing_relationship_bps == 10_000


# =============================================================================
# Report validators 1-2: canonical order, no duplicate targets
# =============================================================================


@_PRR_LOADERS
def test_report_1_reversed_bloc_row_order_is_rejected(load) -> None:
    data = _genuine_legislative_report_dict()
    assert len(data["blocs"]) >= 2
    data["blocs"] = list(reversed(data["blocs"]))
    with pytest.raises(ValidationError, match="blocs must be sorted ascending"):
        load(data)


@_PRR_LOADERS
def test_report_2_duplicate_bloc_target_is_rejected(load) -> None:
    data = _genuine_legislative_report_dict()
    first = data["blocs"][0]
    data["blocs"] = [first, dict(first)]
    with pytest.raises(ValidationError, match="contains a duplicate"):
        load(data)


# =============================================================================
# Report validator 3: policy/decree components match the outcome (existence)
# =============================================================================


@_PRR_LOADERS
def test_report_3_policy_component_on_failed_legislative_is_rejected(load) -> None:
    data = _genuine_legislative_report_dict()
    data["outcome"] = LegislativeOutcome.FAILED_LEGISLATIVE.value
    with pytest.raises(ValidationError, match="cannot produce a policy reaction"):
        load(data)


@_PRR_LOADERS
def test_report_3_decree_component_without_legislature_present_is_rejected(load) -> None:
    data = _genuine_decree_report_dict()
    data["legislature_present"] = False
    with pytest.raises(ValidationError, match="cannot produce a decree-bypass penalty"):
        load(data)


# =============================================================================
# Report validator 4 (R4): policy reaction re-derived from THIS report's own fields
# =============================================================================


@_PRR_LOADERS
def test_report_4_corrupted_policy_reaction_component_is_rejected(load) -> None:
    """The sum/closing fields are bumped by the same +1 so the ROW's own validators (4 and 5)
    stay satisfied -- isolating the report-level re-derivation from the proposal/preferences."""
    data = _genuine_legislative_report_dict()
    row = next(r for r in data["blocs"] if r["policy_reaction_component_bps"] != 0)
    row["policy_reaction_component_bps"] += 1
    row["uncapped_total_change_bps"] += 1
    row["applied_total_change_bps"] += 1
    row["closing_relationship_bps"] += 1
    with pytest.raises(ValidationError, match="policy_reaction_component_bps=.* does not match"):
        load(data)


@_PRR_LOADERS
def test_report_4_unchanged_direction_forces_zero_reaction_regardless_of_preference(load) -> None:
    """(R12/R18) On an `UNCHANGED` re-decree, the axis short-circuits to 0 no matter what
    preference a row claims -- injecting a nonzero policy reaction is rejected purely from this
    report's own `tax_direction`/`spending_direction`, no cross-report or state check needed."""
    data = _unchanged_decree_report_dict()
    assert data["tax_direction"] == "unchanged"
    row = data["blocs"][0]
    row["policy_reaction_component_bps"] = 5
    row["uncapped_total_change_bps"] += 5
    row["applied_total_change_bps"] += 5
    row["closing_relationship_bps"] += 5
    with pytest.raises(ValidationError, match="policy_reaction_component_bps=.* does not match"):
        load(data)


# =============================================================================
# Report validator 5 (R4): decree bypass re-derived from outcome/legislature_present
# =============================================================================


@_PRR_LOADERS
def test_report_5_corrupted_decree_bypass_component_is_rejected(load) -> None:
    data = _genuine_decree_report_dict()
    row = data["blocs"][0]
    assert row["decree_bypass_component_bps"] == -200
    row["decree_bypass_component_bps"] = -150
    row["uncapped_total_change_bps"] += 50
    row["applied_total_change_bps"] += 50
    row["closing_relationship_bps"] += 50
    with pytest.raises(ValidationError, match="decree_bypass_component_bps=.* does not match"):
        load(data)
