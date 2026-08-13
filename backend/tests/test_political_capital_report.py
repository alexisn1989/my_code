"""Validation-hardening audit for `PoliticalCapitalReport`/`CapitalExpenditureReport`'s
self-validation and `TurnReport`'s Phase 3B2A/3B2B capital-ledger cross-validators, mirroring
`test_legislative_report.py`'s own audit exactly.

Each responsibility declared directly on `PoliticalCapitalReport` gets at least one dedicated
corruption test, exercised through **both** `model_validate` (dict) and `model_validate_json`
(equivalent JSON string) via the `_PCR_LOADERS`/`_TURN_LOADERS` parametrize decorators — so each
corruption case is actually two separately-collected pytest items, not one loop hiding two
assertions. Two responsibilities that live on the row models rather than on `PoliticalCapitalReport`
itself (`CapitalExpenditureReport._target_identity_matches_category_shape` and
`._decision_digest_is_a_well_formed_hex_digest`) are covered the same way, through the parent
report's own round trip.

**Phase 3B2B, §8:** `PoliticalCapitalReport.relationship_changes` and its two validators (former
responsibilities 7-10) are REMOVED — that detail moved to the new ninth report,
`PoliticalRelationshipReport`, whose own self-validators are audited in
`test_political_relationship_report.py`, and whose relocated capital-ledger correspondence is
audited below as a `TurnReport` cross-validator.

Two sourcing strategies, chosen per case, exactly as `test_legislative_report.py` documents:

- **Real resolver, then corrupt one field at a time** (preferred, used wherever a real scenario
  reaches the case cleanly): a genuinely valid report comes out of `resolve_turn` against
  `tiny_valid.yaml`/`deficit_demo.yaml`/`decree_state.yaml`, dumped to a dict, then exactly one
  claim is mutated.
- **Direct construction** for cases no real scenario reaches cleanly (the `model_construct` bypass
  for the positive-commitment backstop, which `StrictPoliticalCapitalCommitment`'s own `ge=1` bound
  already makes unreachable through ordinary validation). Every such report is still built by
  calling the real Pydantic constructors — nothing is mocked — so it is still the real validator
  chain being exercised, just against hand-picked, independently verified inputs instead of the
  resolver's output.

`_expenditure_categories_are_route_consistent` is deliberately **not** tested as a
`PoliticalCapitalReport` responsibility here — Revision 3 assigns it to `TurnReport` because it
needs `LegislativeReport.outcome`/`.route`, which `PoliticalCapitalReport` cannot see. It is
audited in the `TurnReport` integration section below, alongside the other Phase 3B2A/3B2B
cross-validators.
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
    InfluenceAllocation,
)
from app.simulation.legislature import CapitalExpenditureCategory, LegislativeOutcome, ProposalRoute
from app.simulation.relationships import relationship_gain_bps
from app.simulation.report import (
    CapitalExpenditureReport,
    PoliticalCapitalReport,
    TurnReport,
)
from app.simulation.resolver import resolve_turn
from tests.conftest import SCENARIO_DIR, make_game_state

_PCR_LOADERS = pytest.mark.parametrize(
    "load",
    [
        pytest.param(PoliticalCapitalReport.model_validate, id="model_validate"),
        pytest.param(
            lambda data: PoliticalCapitalReport.model_validate_json(json.dumps(data)),
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
# Real-resolver dict builders
# =============================================================================


def _decisions_for(state, *decision_objs) -> DecisionSet:  # type: ignore[no-untyped-def]
    ordered = sorted(decision_objs, key=lambda d: d.kind)
    return DecisionSet(
        expected_turn=state.turn,
        expected_state_version=state.state_version,
        decisions=tuple(ordered),
    )


def _valid_no_proposal_report_dict() -> dict:
    """No decisions at all -- an empty ledger, `NO_PROPOSAL`."""
    state = make_game_state(turn=0, state_version=0)
    resolution = resolve_turn(state, _decisions_for(state))
    ledger = resolution.report.political_capital
    assert ledger is not None
    assert ledger.expenditures == ()
    return ledger.model_dump(mode="json")


def _valid_legislative_report_dict() -> dict:
    """`tiny_valid` passes the walkthrough proposal unaided -- an EMPTY ledger (zero expenditure
    rows, since no capital was spent) and an empty `relationship_changes`. The "legislative route,
    zero commitment" baseline."""
    state = load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml")
    current = state.world.countries["arken"].finance.tax_policy.personal_income_rate_bps
    decision = BudgetDecision(personal_income_rate_bps=current + 500)
    resolution = resolve_turn(state, _decisions_for(state, decision))
    assert resolution.report.legislative is not None
    assert resolution.report.legislative.outcome is LegislativeOutcome.PASSED_LEGISLATIVE
    ledger = resolution.report.political_capital
    assert ledger is not None
    return ledger.model_dump(mode="json")


def _valid_legislative_report_dict_with_influence() -> dict:
    """`deficit_demo`'s cheapest passing bargain (162 on `citizens_bloc/moderates`) -- a nonempty
    ledger with exactly one `LEGISLATIVE_INFLUENCE` row and `total_committed == 162`, no
    relationship investment."""
    state = load_scenario_file(SCENARIO_DIR / "deficit_demo.yaml")
    current = state.world.countries["strapped"].finance.tax_policy.personal_income_rate_bps
    decision = BudgetDecision(
        personal_income_rate_bps=current + 500,
        influence=(
            InfluenceAllocation(
                party_id="citizens_bloc", bloc_id="moderates", political_capital=162
            ),
        ),
    )
    resolution = resolve_turn(state, _decisions_for(state, decision))
    assert resolution.report.legislative is not None
    assert resolution.report.legislative.outcome is LegislativeOutcome.PASSED_LEGISLATIVE
    ledger = resolution.report.political_capital
    assert ledger is not None
    assert ledger.total_committed == 162
    return ledger.model_dump(mode="json")


def _valid_decree_report_dict() -> dict:
    """`decree_state`, `route=DECREE` -- exactly one `DECREE` row, no influence rows, no
    relationship changes."""
    state = load_scenario_file(SCENARIO_DIR / "decree_state.yaml")
    decision = BudgetDecision(personal_income_rate_bps=2_500, route=ProposalRoute.DECREE)
    resolution = resolve_turn(state, _decisions_for(state, decision))
    assert resolution.report.legislative is not None
    assert resolution.report.legislative.outcome is LegislativeOutcome.ENACTED_BY_DECREE
    ledger = resolution.report.political_capital
    assert ledger is not None
    return ledger.model_dump(mode="json")


def _valid_relationship_only_report_dict() -> dict:
    """`deficit_demo`, an investment with no budget decision at all -- `NO_PROPOSAL` carrying a
    nonempty ledger, mirroring
    `test_relationship_investment_paths.py::test_a_relationship_only_turn_is_a_valid_no_proposal_with_a_nonempty_ledger`."""
    state = load_scenario_file(SCENARIO_DIR / "deficit_demo.yaml")
    investment = BlocRelationshipInvestmentDecision(
        investments=(
            BlocInvestment(party_id="citizens_bloc", bloc_id="moderates", political_capital=100),
        )
    )
    resolution = resolve_turn(state, _decisions_for(state, investment))
    assert resolution.report.legislative is not None
    assert resolution.report.legislative.outcome is LegislativeOutcome.NO_PROPOSAL
    ledger = resolution.report.political_capital
    assert ledger is not None
    assert ledger.total_committed == 100
    return ledger.model_dump(mode="json")


def _valid_mixed_report_dict() -> dict:
    """`deficit_demo`, investment 100 + influence 162 in the same turn -- a nonempty ledger with
    BOTH a `LEGISLATIVE_INFLUENCE` row and a `BLOC_RELATIONSHIP_INVESTMENT` row, `PASSED_LEGISLATIVE`,
    mirroring `test_relationship_investment_paths.py::test_a_turn_with_both_a_legislative_vote_and_an_investment_reconciles_clean`."""
    state = load_scenario_file(SCENARIO_DIR / "deficit_demo.yaml")
    current = state.world.countries["strapped"].finance.tax_policy.personal_income_rate_bps
    investment = BlocRelationshipInvestmentDecision(
        investments=(
            BlocInvestment(party_id="citizens_bloc", bloc_id="moderates", political_capital=100),
        )
    )
    budget = BudgetDecision(
        personal_income_rate_bps=current + 500,
        influence=(
            InfluenceAllocation(
                party_id="citizens_bloc", bloc_id="moderates", political_capital=162
            ),
        ),
    )
    resolution = resolve_turn(state, _decisions_for(state, investment, budget))
    assert resolution.report.legislative is not None
    assert resolution.report.legislative.outcome is LegislativeOutcome.PASSED_LEGISLATIVE
    ledger = resolution.report.political_capital
    assert ledger is not None
    assert ledger.total_committed == 262
    return ledger.model_dump(mode="json")


@_PCR_LOADERS
@pytest.mark.parametrize(
    "builder",
    [
        _valid_no_proposal_report_dict,
        _valid_legislative_report_dict,
        _valid_legislative_report_dict_with_influence,
        _valid_decree_report_dict,
        _valid_relationship_only_report_dict,
        _valid_mixed_report_dict,
    ],
)
def test_a_valid_report_round_trips(load, builder) -> None:
    load(builder())


# =============================================================================
# 1. total_committed matches expenditure rows
# =============================================================================


@_PCR_LOADERS
def test_1_corrupted_total_committed_is_rejected(load) -> None:
    data = _valid_legislative_report_dict_with_influence()
    data["total_committed"] += 1
    with pytest.raises(ValidationError, match="does not match sum\\(expenditures"):
        load(data)


# =============================================================================
# 2. total_committed bounded by opening capital
# =============================================================================


def test_2_commitment_exactly_at_opening_capital_is_accepted() -> None:
    state = load_scenario_file(SCENARIO_DIR / "deficit_demo.yaml")
    opening = state.world.countries["strapped"].politics.political_capital
    assert opening == 300
    current = state.world.countries["strapped"].finance.tax_policy.personal_income_rate_bps
    decision = BudgetDecision(
        personal_income_rate_bps=current + 500,
        influence=(
            InfluenceAllocation(
                party_id="citizens_bloc", bloc_id="moderates", political_capital=300
            ),
        ),
    )
    resolution = resolve_turn(state, _decisions_for(state, decision))
    ledger = resolution.report.political_capital
    assert ledger is not None
    assert ledger.total_committed == 300 == ledger.opening_political_capital


@_PCR_LOADERS
def test_2_corrupted_total_committed_above_opening_capital_is_rejected(load) -> None:
    """`total_committed` can never legitimately exceed opening capital at construction time (the
    real resolver enforces the guard before the report is ever built), so the boundary is reached
    the same way `test_legislative_report.py`'s 301-of-300 case is: patch a genuinely valid
    300-of-300 report's row and total together, so validator 1's own check stays satisfied and
    validator 2 is the only thing left to reject it."""
    data = _valid_legislative_report_dict_with_influence()
    row = next(
        r
        for r in data["expenditures"]
        if r["category"] == CapitalExpenditureCategory.LEGISLATIVE_INFLUENCE.value
    )
    row["political_capital"] = data["opening_political_capital"] + 1
    data["total_committed"] = data["opening_political_capital"] + 1
    with pytest.raises(ValidationError, match="exceeds opening_political_capital"):
        load(data)


# =============================================================================
# 3. closing capital matches the clamped identity
# =============================================================================


@_PCR_LOADERS
def test_3_corrupted_closing_capital_is_rejected(load) -> None:
    data = _valid_legislative_report_dict_with_influence()
    data["closing_political_capital"] += 1
    with pytest.raises(
        ValidationError, match="does not match min\\(capacity, opening - total_committed"
    ):
        load(data)


# =============================================================================
# 4. expenditure rows in canonical order
# =============================================================================


@_PCR_LOADERS
def test_4_reversed_expenditure_row_order_is_rejected(load) -> None:
    data = _valid_mixed_report_dict()
    assert len(data["expenditures"]) == 2
    data["expenditures"] = list(reversed(data["expenditures"]))
    with pytest.raises(ValidationError, match="expenditures must be sorted ascending"):
        load(data)


# =============================================================================
# 5. (row) decree target/category shape
# =============================================================================


@_PCR_LOADERS
def test_5_decree_row_carrying_a_target_is_rejected(load) -> None:
    data = _valid_decree_report_dict()
    decree_row = next(
        r for r in data["expenditures"] if r["category"] == CapitalExpenditureCategory.DECREE.value
    )
    decree_row["party_id"] = "citizens_bloc"
    decree_row["bloc_id"] = "moderates"
    with pytest.raises(ValidationError, match="category=DECREE must carry no party_id/bloc_id"):
        load(data)


@_PCR_LOADERS
def test_5_non_decree_row_missing_a_target_is_rejected(load) -> None:
    data = _valid_legislative_report_dict_with_influence()
    row = data["expenditures"][0]
    assert row["category"] != CapitalExpenditureCategory.DECREE.value
    row["party_id"] = None
    row["bloc_id"] = None
    with pytest.raises(ValidationError, match="must carry both party_id and bloc_id"):
        load(data)


# =============================================================================
# 6. at most one decree row
# =============================================================================


@_PCR_LOADERS
def test_6_two_decree_rows_is_rejected(load) -> None:
    data = _valid_decree_report_dict()
    decree_row = next(
        r for r in data["expenditures"] if r["category"] == CapitalExpenditureCategory.DECREE.value
    )
    duplicated = dict(decree_row)
    data["expenditures"] = [decree_row, duplicated]
    new_total = decree_row["political_capital"] * 2
    data["total_committed"] = new_total
    data["closing_political_capital"] = min(
        data["political_capital_capacity"],
        data["opening_political_capital"] - new_total + data["political_capital_regeneration"],
    )
    with pytest.raises(ValidationError, match="at most one DECREE expenditure row is valid"):
        load(data)


# =============================================================================
# 11. every expenditure row is a genuinely positive commitment
# =============================================================================


def test_11_zero_capital_row_is_unconstructible_through_ordinary_validation() -> None:
    """`StrictPoliticalCapitalCommitment` (`ge=1`) already rejects this at the ROW level, before
    `PoliticalCapitalReport`'s own backstop validator is ever reached -- proven here so the
    `model_construct` test below is understood as covering a genuinely different, otherwise
    unreachable path, not duplicating this one."""
    with pytest.raises(ValidationError, match="greater than or equal to 1"):
        CapitalExpenditureReport(
            category=CapitalExpenditureCategory.LEGISLATIVE_INFLUENCE,
            party_id="citizens_bloc",
            bloc_id="moderates",
            political_capital=0,
            decision_digest="0" * 64,
        )


def test_11_positive_commitment_backstop_rejects_a_model_construct_bypass() -> None:
    """`_expenditure_rows_are_positive_commitments` exists specifically as defence-in-depth against
    a bypassed construction -- reached here the same way `test_finance_report.py`'s
    `test_cash_flow_equation_validator_detects_a_direct_violation` reaches its own backstop: build a
    real, valid report, then use `model_construct` to hold a row whose `political_capital` was
    forced below 1 (impossible through the strict type), and call the validator method directly."""
    data = _valid_legislative_report_dict_with_influence()
    valid_report = PoliticalCapitalReport.model_validate(data)

    bad_row = CapitalExpenditureReport.model_construct(
        **{**valid_report.expenditures[0].__dict__, "political_capital": 0}
    )
    unvalidated = PoliticalCapitalReport.model_construct(
        **{**valid_report.__dict__, "expenditures": (bad_row, *valid_report.expenditures[1:])}
    )

    with pytest.raises(ValueError, match="non-positive political_capital"):
        PoliticalCapitalReport._expenditure_rows_are_positive_commitments(unvalidated)


# =============================================================================
# 12. (row) decision_digest is a well-formed hex digest
# =============================================================================


@_PCR_LOADERS
def test_12_malformed_decision_digest_is_rejected(load) -> None:
    data = _valid_legislative_report_dict_with_influence()
    data["expenditures"][0]["decision_digest"] = "not-a-hex-digest"
    with pytest.raises(ValidationError, match="not a lowercase 64-character hexadecimal digest"):
        load(data)


@_PCR_LOADERS
def test_12_uppercase_decision_digest_is_rejected(load) -> None:
    data = _valid_legislative_report_dict_with_influence()
    data["expenditures"][0]["decision_digest"] = data["expenditures"][0]["decision_digest"].upper()
    with pytest.raises(ValidationError, match="not a lowercase 64-character hexadecimal digest"):
        load(data)


# =============================================================================
# TurnReport integration boundary: the three Phase 3B2A capital-ledger cross-validators
# =============================================================================
#
# `_political_capital_ledger_reconciles_across_reports`'s FIRST check (total_committed vs
# political.political_capital_spent) is already covered by
# `test_legislative_report.py::test_commitment_mismatch_rejected_when_political_side_changes` --
# not duplicated here. Everything below is genuinely new coverage.


def _mixed_turn_report_dict() -> dict:
    state = load_scenario_file(SCENARIO_DIR / "deficit_demo.yaml")
    current = state.world.countries["strapped"].finance.tax_policy.personal_income_rate_bps
    investment = BlocRelationshipInvestmentDecision(
        investments=(
            BlocInvestment(party_id="citizens_bloc", bloc_id="moderates", political_capital=100),
        )
    )
    budget = BudgetDecision(
        personal_income_rate_bps=current + 500,
        influence=(
            InfluenceAllocation(
                party_id="citizens_bloc", bloc_id="moderates", political_capital=162
            ),
        ),
    )
    resolution = resolve_turn(state, _decisions_for(state, investment, budget))
    return resolution.report.model_dump(mode="json")


def _decree_turn_report_dict() -> dict:
    state = load_scenario_file(SCENARIO_DIR / "decree_state.yaml")
    decision = BudgetDecision(personal_income_rate_bps=2_500, route=ProposalRoute.DECREE)
    resolution = resolve_turn(state, _decisions_for(state, decision))
    return resolution.report.model_dump(mode="json")


def _no_proposal_turn_report_dict() -> dict:
    state = make_game_state(turn=0, state_version=0)
    resolution = resolve_turn(state, _decisions_for(state))
    return resolution.report.model_dump(mode="json")


@_TURN_LOADERS
def test_ledger_reconciles_legislative_share_mismatch_is_rejected(load) -> None:
    """`_political_capital_ledger_reconciles_across_reports`'s SECOND check: the ledger's own
    LEGISLATIVE_INFLUENCE/DECREE share must equal `legislative.political_capital_committed`.

    `legislative.political_capital_committed` cannot be corrupted directly -- `LegislativeReport`
    derives it internally from its own influence rows and rejects a mismatch itself, before this
    turn-level cross-check is ever reached. Instead, the LEDGER's influence row is bumped by 1
    (leaving the legislative sub-report untouched, so its own internal rule and the FIRST
    ledger/political check both stay satisfied), with `total_committed`/`political_capital_spent`/
    both sides' `closing_political_capital` kept internally consistent -- isolating the
    legislative-share disagreement specifically."""
    data = _mixed_turn_report_dict()
    assert data["legislative"]["political_capital_committed"] == 162
    influence_row = next(
        r
        for r in data["political_capital"]["expenditures"]
        if r["category"] == CapitalExpenditureCategory.LEGISLATIVE_INFLUENCE.value
    )
    influence_row["political_capital"] += 1
    new_total = data["political_capital"]["total_committed"] + 1
    new_closing = min(
        data["political_capital"]["political_capital_capacity"],
        data["political_capital"]["opening_political_capital"]
        - new_total
        + data["political_capital"]["political_capital_regeneration"],
    )
    data["political_capital"]["total_committed"] = new_total
    data["political_capital"]["closing_political_capital"] = new_closing
    data["political"]["political_capital_spent"] = new_total
    data["political"]["closing_political_capital"] = new_closing
    with pytest.raises(
        ValidationError, match="does not match the LEGISLATIVE_INFLUENCE/DECREE share"
    ):
        load(data)


@pytest.mark.parametrize(
    "field_name",
    ["opening_political_capital", "political_capital_regeneration", "political_capital_capacity"],
)
@_TURN_LOADERS
def test_ledger_and_political_report_capital_figures_must_agree(load, field_name: str) -> None:
    """Bumping one input field alone on the ledger side would ALSO break `PoliticalCapitalReport`'s
    own closing-capital identity (validator 3) first, since that identity is a function of exactly
    these inputs -- so the ledger's `closing_political_capital` is recomputed from the corrupted
    inputs to keep the ledger internally self-consistent, leaving only its disagreement with
    (unchanged) `political.*` for THIS cross-validator to catch."""
    data = _no_proposal_turn_report_dict()
    ledger = data["political_capital"]
    ledger[field_name] += 1
    ledger["closing_political_capital"] = min(
        ledger["political_capital_capacity"],
        ledger["opening_political_capital"]
        - ledger["total_committed"]
        + ledger["political_capital_regeneration"],
    )
    with pytest.raises(ValidationError, match=f"political_capital.{field_name}=.* does not match"):
        load(data)


def test_ledger_and_political_report_closing_capital_mismatch_is_unreachable_through_ordinary_validation() -> (
    None
):
    """The fourth pair (`closing_political_capital`) is checked only after opening/regeneration/
    capacity have ALL already been proven equal, and cross-validator 1 (declared earlier) already
    proves `total_committed == political.political_capital_spent`. With all four shared inputs
    equal, `PoliticalCapitalReport`'s own closing-identity (validator 3) and `PoliticalReport`'s own
    closing guard compute the IDENTICAL clamp formula from the IDENTICAL inputs -- so the closing
    values cannot legitimately disagree once every earlier check has passed; this branch is real
    defense-in-depth, unreachable via ordinary corruption, exactly like validator 11's backstop.
    Reached the same way: `model_construct` holds a `TurnReport` whose ledger closing value was
    forced to disagree, and the validator method is called directly."""
    data = _no_proposal_turn_report_dict()
    valid_report = TurnReport.model_validate(data)
    assert valid_report.political_capital is not None

    bad_ledger = valid_report.political_capital.model_construct(
        **{
            **valid_report.political_capital.__dict__,
            "closing_political_capital": valid_report.political_capital.closing_political_capital
            + 1,
        }
    )
    unvalidated = TurnReport.model_construct(
        **{**valid_report.__dict__, "political_capital": bad_ledger}
    )

    with pytest.raises(
        ValueError, match="political_capital.closing_political_capital=.* does not match"
    ):
        TurnReport._capital_ledger_opening_and_capacity_match_political_report(unvalidated)


@_TURN_LOADERS
def test_decree_outcome_with_an_extra_influence_row_is_rejected(load) -> None:
    """Route-consistency's DECREE branch (exactly one DECREE row, zero LEGISLATIVE_INFLUENCE rows)
    is checked only after the ledger/legislative-share cross-check (declared earlier) already
    agrees -- so an injected influence row must be OFFSET by shrinking the decree row's own amount
    by the same number, keeping the ledger's total LEGISLATIVE_INFLUENCE+DECREE share (and
    therefore `legislative.political_capital_committed`, `total_committed`, and every capital
    figure) completely unchanged. Only the ROW SHAPE changed -- exactly what this validator, and
    only this validator, polices."""
    data = _decree_turn_report_dict()
    decree_row = next(
        r
        for r in data["political_capital"]["expenditures"]
        if r["category"] == CapitalExpenditureCategory.DECREE.value
    )
    assert decree_row["political_capital"] >= 50
    decree_row["political_capital"] -= 50
    injected = dict(decree_row)
    injected["category"] = CapitalExpenditureCategory.LEGISLATIVE_INFLUENCE.value
    injected["party_id"], injected["bloc_id"] = "governing_party", "core"
    injected["political_capital"] = 50
    data["political_capital"]["expenditures"] = sorted(
        [decree_row, injected],
        key=lambda r: (r["category"], r["party_id"] or "", r["bloc_id"] or ""),
    )
    with pytest.raises(
        ValidationError, match="ENACTED_BY_DECREE requires exactly one DECREE expenditure row"
    ):
        load(data)


@_TURN_LOADERS
def test_passed_legislative_outcome_with_a_decree_row_is_rejected(load) -> None:
    """Same offsetting technique: a DECREE row is added and the existing influence row's amount is
    shrunk by the same number, so the LEGISLATIVE_INFLUENCE+DECREE share (and everything derived
    from it) stays exactly what it was -- only the shape (a DECREE row present at all, on a
    legislative-route outcome) is now wrong."""
    data = _mixed_turn_report_dict()
    assert data["legislative"]["outcome"] == LegislativeOutcome.PASSED_LEGISLATIVE.value
    influence_row = next(
        r
        for r in data["political_capital"]["expenditures"]
        if r["category"] == CapitalExpenditureCategory.LEGISLATIVE_INFLUENCE.value
    )
    assert influence_row["political_capital"] >= 50
    influence_row["political_capital"] -= 50
    injected = dict(influence_row)
    injected["category"] = CapitalExpenditureCategory.DECREE.value
    injected["party_id"], injected["bloc_id"] = None, None
    injected["political_capital"] = 50
    data["political_capital"]["expenditures"] = sorted(
        [*data["political_capital"]["expenditures"], injected],
        key=lambda r: (r["category"], r["party_id"] or "", r["bloc_id"] or ""),
    )
    with pytest.raises(ValidationError, match="requires zero DECREE expenditure rows"):
        load(data)


def test_no_proposal_outcome_with_a_decree_row_is_unreachable_through_ordinary_validation() -> None:
    """`LegislativeReport` itself forces `political_capital_committed == 0` for `NO_PROPOSAL`
    (its own rule, checked before this turn ever reaches TurnReport's cross-validators), so ANY
    nonzero ledger row -- decree or influence -- makes the legislative-share cross-check (declared
    BEFORE route-consistency) disagree first; there is no offsetting trick available the way there
    is for the decree/legislative-route cases above, because 0 admits no nonzero split. This
    NO_PROPOSAL branch of route-consistency is real defense-in-depth, unreachable via ordinary
    corruption -- reached directly via `model_construct`, mirroring the closing-capital test above."""
    data = _no_proposal_turn_report_dict()
    valid_report = TurnReport.model_validate(data)
    assert valid_report.political_capital is not None

    bad_row = CapitalExpenditureReport(
        category=CapitalExpenditureCategory.DECREE,
        party_id=None,
        bloc_id=None,
        political_capital=250,
        decision_digest="0" * 64,
    )
    bad_ledger = valid_report.political_capital.model_construct(
        **{
            **valid_report.political_capital.__dict__,
            "expenditures": (bad_row,),
            "total_committed": 250,
        }
    )
    unvalidated = TurnReport.model_construct(
        **{**valid_report.__dict__, "political_capital": bad_ledger}
    )

    with pytest.raises(
        ValueError, match="NO_PROPOSAL requires zero DECREE and zero LEGISLATIVE_INFLUENCE"
    ):
        TurnReport._expenditure_categories_are_route_consistent(unvalidated)


# =============================================================================
# Phase 3B2B: the relocated investment<->relationship-memory correspondence
# (`TurnReport._relationship_investment_components_match_the_capital_ledger`, formerly
# `PoliticalCapitalReport` validator 10)
# =============================================================================


@_TURN_LOADERS
def test_relationship_memory_row_with_no_matching_expenditure_row_is_rejected(load) -> None:
    """A `political_relationship` row claiming a DIFFERENT `investment_capital` than the ledger's
    real `BLOC_RELATIONSHIP_INVESTMENT` row -- with every one of the row's OWN dependent fields
    (`investment_component_bps`, the sum, the closing value) recomputed to stay genuinely
    self-consistent under the new capital figure, isolating the cross-report correspondence
    check specifically, rather than tripping the row's own formula validator first."""
    data = _mixed_turn_report_dict()
    investment_row = next(
        r
        for r in data["political_capital"]["expenditures"]
        if r["category"] == CapitalExpenditureCategory.BLOC_RELATIONSHIP_INVESTMENT.value
    )
    assert investment_row["political_capital"] == 100
    relationship_row = next(
        r
        for r in data["political_relationship"]["blocs"]
        if r["party_id"] == investment_row["party_id"] and r["bloc_id"] == investment_row["bloc_id"]
    )
    assert relationship_row["investment_capital"] == 100
    new_capital = 150
    new_investment_component = relationship_gain_bps(
        opening_relationship_bps=relationship_row["opening_relationship_bps"],
        political_capital=new_capital,
    )
    delta = new_investment_component - relationship_row["investment_component_bps"]
    relationship_row["investment_capital"] = new_capital
    relationship_row["investment_component_bps"] = new_investment_component
    relationship_row["uncapped_total_change_bps"] += delta
    relationship_row["applied_total_change_bps"] += delta
    relationship_row["closing_relationship_bps"] += delta
    with pytest.raises(ValidationError, match="does not correspond exactly"):
        load(data)


@_TURN_LOADERS
def test_investment_expenditure_row_with_no_matching_relationship_memory_row_is_rejected(
    load,
) -> None:
    data = _mixed_turn_report_dict()
    investment_row = next(
        r
        for r in data["political_capital"]["expenditures"]
        if r["category"] == CapitalExpenditureCategory.BLOC_RELATIONSHIP_INVESTMENT.value
    )
    data["political_relationship"]["blocs"] = [
        row
        for row in data["political_relationship"]["blocs"]
        if not (
            row["party_id"] == investment_row["party_id"]
            and row["bloc_id"] == investment_row["bloc_id"]
        )
    ]
    with pytest.raises(ValidationError, match="does not correspond exactly"):
        load(data)


@_TURN_LOADERS
def test_relationship_report_proposal_mismatch_with_legislative_report_is_rejected(load) -> None:
    """(R4) `political_relationship`'s own copy of the proposal's shape must equal
    `LegislativeReport`'s independently-stored fields. `_mixed_turn_report_dict`'s decision only
    moves the tax axis, so `spending_direction` is `UNCHANGED` and the axis formula
    (`_legislative_axis_component_bps`) short-circuits to `0` for EVERY row regardless of
    `spending_intensity_bps`'s value -- corrupting `spending_intensity_bps` alone therefore leaves
    `political_relationship`'s own self-validators fully satisfied (every row's
    `policy_reaction_component_bps` is unaffected), so only this cross-report check can catch it."""
    data = _mixed_turn_report_dict()
    assert data["political_relationship"]["spending_direction"] == "unchanged"
    data["political_relationship"]["spending_intensity_bps"] += 1
    with pytest.raises(ValidationError, match="does not match legislative.spending_intensity_bps"):
        load(data)
