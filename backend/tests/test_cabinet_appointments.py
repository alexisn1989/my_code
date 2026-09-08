"""Appointing, replacing and dismissing a cabinet.

Commit 2 gave the player a cabinet they could not change. This is the commit that makes it a
decision, and four claims are worth proving about it.

* **Hiring is a tradeoff, not a purchase.** The price is what a person DEMANDS (`independence`),
  the willingness to serve at all is `loyalty` weighed against the government's legitimacy, and
  which chair they will take is `ambition`. Three traits, three distinct consumers, every branch
  reachable from content that already ships.
* **A decision is all-or-nothing, and judged on its RESULT.** One illegal order refuses the whole
  set and applies none of it; a same-turn transfer is legal precisely because the assembled cabinet
  is what gets checked, not the orders pairwise.
* **This turn belongs to whoever was already serving.** An appointment takes effect next turn, and
  -- the part that is easy to get wrong -- a REPLACEMENT or a DISMISSAL must not erase the outgoing
  holder's contribution to the turn they served in full.
* **Every change is visible and none of it can be forged.** The subtree, the ledger, the report
  entries and the state all describe one event, and reconciliation group 57 proves they agree.

The turn-`t` reads and the affordability boundary live in `test_characters_and_cabinet.py`
alongside the rest of the office-bonus proofs; this file covers the decision itself.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.api.decision_preflight import first_decision_problem
from app.api.preview import preview_decisions
from app.api.projections import build_decision_options, build_turn_result
from app.cli import REASON_RENDERERS, main
from app.content.scenarios import load_scenario_file
from app.core.errors import TurnResolutionError
from app.simulation.cabinet import (
    CABINET_APPOINTMENT_BASE_COST,
    CABINET_INDEPENDENCE_SURCHARGE_MAX,
    FOREIGN_MINISTRY_AMBITION_CEILING_BPS,
    GOVERNMENT_LEGITIMACY_FLOOR_BPS,
    MINIMUM_ACCEPTANCE_LOYALTY_BPS,
    CabinetRefusal,
    appointment_cost_capital,
    appointment_refusal,
    is_domestic_to,
)
from app.simulation.decisions import (
    CabinetDecision,
    CabinetOrder,
    DecisionSet,
    cabinet_decision_digest,
)
from app.simulation.history import advance_game, new_game, validate_history
from app.simulation.legislature import CapitalExpenditureCategory
from app.simulation.reconciliation import reconcile_political_legislative_and_survival_report
from app.simulation.report import CabinetChange
from app.simulation.resolver import resolve_turn
from app.simulation.save_format import SAVE_FORMAT_VERSION
from app.simulation.state import POST_DISPLAY_NAMES, CabinetPost, GameState
from tests.conftest import SCENARIO_DIR

_CoS = CabinetPost.CHIEF_OF_STAFF
_FM = CabinetPost.FOREIGN_MINISTER


def _load(scenario_file: str) -> GameState:
    return load_scenario_file(SCENARIO_DIR / scenario_file)


def _decide(state: GameState, *orders: CabinetOrder) -> DecisionSet:
    return DecisionSet(
        expected_turn=state.turn,
        expected_state_version=state.state_version,
        decisions=[CabinetDecision(orders=orders)],
    )


def _row(resolution, post: CabinetPost):  # type: ignore[no-untyped-def]
    assert resolution.report.governance is not None
    (row,) = [r for r in resolution.report.governance.posts if r.post is post]
    return row


def _offices(state: GameState) -> dict[str, str]:
    cabinet = state.world.countries[state.world.player_country_id].cabinet
    assert cabinet is not None
    return {post.value: appt.character_id for post, appt in cabinet.offices.items()}


# --- the price: exact integers, and what it is a price OF ---------------------------------------


@pytest.mark.parametrize(("independence_bps", "expected"), [(0, 120), (5_000, 210), (10_000, 300)])
def test_the_cost_formula_is_exact_at_its_named_points(
    independence_bps: int, expected: int
) -> None:
    """`120 + independence_bps * 180 // 10_000`. Pinned at the two ends and the midpoint, because
    a formula whose only test is "it returns something" is not calibrated."""
    assert appointment_cost_capital(independence_bps=independence_bps) == expected
    assert CABINET_APPOINTMENT_BASE_COST == 120
    assert CABINET_INDEPENDENCE_SURCHARGE_MAX == 180


def test_the_cost_truncates_and_never_uses_a_float() -> None:
    """Truncation toward zero at every step, so the price is reproducible on any machine. 4,300
    would be 77.4 in decimal and is 77 here -- checked as an exact identity rather than an
    approximation."""
    for independence_bps in range(0, 10_001, 7):
        cost = appointment_cost_capital(independence_bps=independence_bps)
        assert isinstance(cost, int)
        assert cost == 120 + independence_bps * 180 // 10_000
    assert appointment_cost_capital(independence_bps=4_300) == 197


def test_price_reads_independence_and_never_competence() -> None:
    """The mandate's shape: capable independent people demand more, but the price is what somebody
    DEMANDS, not what they are worth. If cost tracked competence it would be a second competence
    score wearing a currency sign, and a cheap effective hire would stop being representable.

    `tiny_valid`'s roster proves it is not: the professional is more competent than the ambitious
    expert (7,400 against 8,100 is close, but the loyal administrator at 3,200 is far below both)
    and costs LESS than either, because he demands less.
    """
    characters = _load("tiny_valid.yaml").world.characters
    by_cost = {
        character_id: appointment_cost_capital(independence_bps=character.independence)
        for character_id, character in characters.items()
        if character.party_id is None
    }
    assert by_cost["hal_verrin"] == 147
    assert by_cost["wren_hollis"] == 197
    assert by_cost["tomas_bekker"] == 231
    assert by_cost["ilse_marovec"] == 276
    # Cheaper than the ambitious expert despite being more loyal AND nearly as competent.
    assert by_cost["wren_hollis"] < by_cost["tomas_bekker"]
    assert characters["wren_hollis"].competence < characters["tomas_bekker"].competence


# --- willingness: three refusals, every branch reachable from shipped content --------------------


def test_the_thresholds_are_the_documented_ones() -> None:
    assert MINIMUM_ACCEPTANCE_LOYALTY_BPS == 5_000
    assert GOVERNMENT_LEGITIMACY_FLOOR_BPS == 6_500
    assert FOREIGN_MINISTRY_AMBITION_CEILING_BPS == 8_000


def test_the_same_candidate_accepts_a_legitimate_government_and_refuses_a_weak_one() -> None:
    """The gate is a fact about the PAIR, not about the person: `ilse_marovec` (loyalty 3,400)
    serves `tiny_valid` at legitimacy 7,000 and refuses `decree_state`'s equivalent at 6,000. A
    single-condition rule could not express that, and a low-loyalty candidate would be either
    always available or never."""
    strong = _load("tiny_valid.yaml").world.characters["ilse_marovec"]
    weak = _load("decree_state.yaml").world.characters["raul_kesten"]
    assert strong.loyalty == weak.loyalty == 3_400

    assert appointment_refusal(character=strong, post=_CoS, legitimacy_bps=7_000) is None
    assert (
        appointment_refusal(character=weak, post=_CoS, legitimacy_bps=6_000)
        is CabinetRefusal.LOW_LEGITIMACY
    )


def test_the_legitimacy_floor_is_a_boundary_not_a_slope() -> None:
    candidate = _load("tiny_valid.yaml").world.characters["ilse_marovec"]
    assert (
        appointment_refusal(
            character=candidate, post=_CoS, legitimacy_bps=GOVERNMENT_LEGITIMACY_FLOOR_BPS
        )
        is None
    )
    assert (
        appointment_refusal(
            character=candidate, post=_CoS, legitimacy_bps=GOVERNMENT_LEGITIMACY_FLOOR_BPS - 1
        )
        is CabinetRefusal.LOW_LEGITIMACY
    )


def test_loyal_candidates_serve_a_weak_government_too() -> None:
    """The anti-vacuity half: the gate is not "nobody serves a weak government". `deficit_demo` at
    legitimacy 6,000 still has two willing candidates, which is what makes its affordability
    boundary a real choice rather than an empty one."""
    characters = _load("deficit_demo.yaml").world.characters
    willing = [
        character_id
        for character_id, character in characters.items()
        if character.party_id is None
        and appointment_refusal(character=character, post=_CoS, legitimacy_bps=6_000) is None
    ]
    assert sorted(willing) == ["bela_ronsard", "freya_lund"]


def test_ambition_refuses_the_junior_chair_and_only_the_junior_chair() -> None:
    """POST-specific by construction, and provable in ISOLATION from the loyalty gate: at
    `tiny_valid`'s legitimacy 7,000 nobody refuses on legitimacy, so `tomas_bekker`'s refusal can
    only be the ambition rule."""
    tomas = _load("tiny_valid.yaml").world.characters["tomas_bekker"]
    assert tomas.ambition == 9_100
    assert appointment_refusal(character=tomas, post=_CoS, legitimacy_bps=7_000) is None
    assert (
        appointment_refusal(character=tomas, post=_FM, legitimacy_bps=7_000)
        is CabinetRefusal.THIS_POST
    )


def test_a_party_leader_is_not_appointable_at_all() -> None:
    """Their standing with the government is the legislative bloc layer's business. Two
    independent models of one person's relationship to the player is one too many."""
    leader = _load("tiny_valid.yaml").world.characters["leader_civic_union"]
    for post in CabinetPost:
        assert (
            appointment_refusal(character=leader, post=post, legitimacy_bps=10_000)
            is CabinetRefusal.LEADS_A_PARTY
        )


def test_a_sitting_holder_is_never_re_assessed() -> None:
    """The gate is asked when somebody is HIRED, never of somebody already serving -- otherwise a
    fall in legitimacy would silently empty the cabinet, which is a resignation mechanic this slice
    does not model. `decree_state` depends on it: its foreign minister would refuse a fresh
    appointment there, and keeps serving."""
    state = _load("decree_state.yaml")
    incumbent = state.world.characters["raul_kesten"]
    assert (
        appointment_refusal(character=incumbent, post=_FM, legitimacy_bps=6_000)
        is CabinetRefusal.LOW_LEGITIMACY
    )
    resolution = resolve_turn(
        state,
        DecisionSet(expected_turn=state.turn, expected_state_version=state.state_version),
    )
    assert _offices(resolution.state)["foreign_minister"] == "raul_kesten"
    assert _row(resolution, _FM).change is CabinetChange.UNCHANGED


# --- the three verbs, derived from the opening cabinet -------------------------------------------


def test_appoint_into_a_vacancy() -> None:
    state = _load("decree_state.yaml")
    assert "chief_of_staff" not in _offices(state)
    resolution = resolve_turn(
        state, _decide(state, CabinetOrder(post=_CoS, character_id="yannic_pell"))
    )
    row = _row(resolution, _CoS)
    assert row.change is CabinetChange.APPOINTED
    assert row.opening_holder_id is None and row.closing_holder_id == "yannic_pell"
    assert row.capital_committed == 197
    assert _offices(resolution.state)["chief_of_staff"] == "yannic_pell"


def test_replace_an_incumbent() -> None:
    state = _load("tiny_valid.yaml")
    resolution = resolve_turn(
        state, _decide(state, CabinetOrder(post=_CoS, character_id="wren_hollis"))
    )
    row = _row(resolution, _CoS)
    assert row.change is CabinetChange.REPLACED
    assert row.opening_holder_id == "hal_verrin"
    assert row.opening_holder_display_name == "Hal Verrin"
    assert row.closing_holder_id == "wren_hollis"
    assert row.capital_committed == 197


def test_dismiss_leaves_the_post_vacant_and_costs_nothing() -> None:
    """Sacking somebody is not an expenditure. Its price is the vacancy -- and, from commit 7, the
    trust consequence."""
    state = _load("tiny_valid.yaml")
    resolution = resolve_turn(state, _decide(state, CabinetOrder(post=_FM)))
    row = _row(resolution, _FM)
    assert row.change is CabinetChange.DISMISSED
    assert row.closing_holder_id is None and row.capital_committed == 0
    assert "foreign_minister" not in _offices(resolution.state)
    assert resolution.report.political_capital is not None
    assert not [
        expenditure
        for expenditure in resolution.report.political_capital.expenditures
        if expenditure.category is CapitalExpenditureCategory.CABINET_APPOINTMENT
    ]


def test_the_verb_is_read_from_state_and_cannot_be_authored() -> None:
    """`CabinetOrder` has no verb field at all: appoint, replace and dismiss are conclusions drawn
    from the opening cabinet. A client that believed it was appointing into a vacant post, when the
    post is occupied, gets a replacement -- correctly reported, and correctly charged."""
    assert set(CabinetOrder.model_fields) == {"post", "character_id"}
    occupied = _load("tiny_valid.yaml")
    vacant = _load("decree_state.yaml")
    order = CabinetOrder(post=_CoS, character_id="wren_hollis")
    assert (
        _row(resolve_turn(occupied, _decide(occupied, order)), _CoS).change
        is CabinetChange.REPLACED
    )
    order = CabinetOrder(post=_CoS, character_id="yannic_pell")
    assert (
        _row(resolve_turn(vacant, _decide(vacant, order)), _CoS).change is CabinetChange.APPOINTED
    )


# --- integrity: judged on the assembled result ---------------------------------------------------


@pytest.mark.parametrize(
    ("orders", "code"),
    [
        ((CabinetOrder(post=_CoS, character_id="nobody_at_all"),), "cabinet_character_unknown"),
        (
            (CabinetOrder(post=_CoS, character_id="leader_kessia"),),
            "cabinet_character_not_domestic",
        ),
        (
            (CabinetOrder(post=_CoS, character_id="leader_civic_union"),),
            "cabinet_character_leads_a_party",
        ),
        (
            (CabinetOrder(post=_CoS, character_id="hal_verrin"),),
            "cabinet_post_already_held_by_this_character",
        ),
        (
            (CabinetOrder(post=_FM, character_id="tomas_bekker"),),
            "cabinet_candidate_refuses_this_post",
        ),
        (
            (
                CabinetOrder(post=_CoS, character_id="wren_hollis"),
                CabinetOrder(post=_FM, character_id="wren_hollis"),
            ),
            "cabinet_character_would_hold_two_posts",
        ),
    ],
)
def test_every_integrity_rule_rejects_with_its_own_stable_code(
    orders: tuple[CabinetOrder, ...], code: str
) -> None:
    """The resolver and the preflight must name the SAME reason, or a draft could preview green and
    then be refused -- which is the failure `decision_preflight` exists to prevent."""
    state = _load("tiny_valid.yaml")
    decisions = _decide(state, *orders)

    with pytest.raises(TurnResolutionError) as exc_info:
        resolve_turn(state, decisions)
    assert code in str(exc_info.value)

    problem = first_decision_problem(state, decisions)
    assert problem is not None and problem.code == code


def test_dismissing_a_vacant_post_is_rejected() -> None:
    """Nothing to dismiss is not a smaller dismissal. Accepting it would let a client submit a set
    that means nothing and be told it succeeded."""
    state = _load("decree_state.yaml")
    assert "chief_of_staff" not in _offices(state)
    decisions = _decide(state, CabinetOrder(post=_CoS))
    with pytest.raises(TurnResolutionError) as exc_info:
        resolve_turn(state, decisions)
    assert "cabinet_dismissal_of_a_vacant_post" in str(exc_info.value)
    problem = first_decision_problem(state, decisions)
    assert problem is not None and problem.code == "cabinet_dismissal_of_a_vacant_post"


def test_a_same_turn_transfer_is_legal_and_charged_once() -> None:
    """The case a pairwise check over orders cannot get right: `ilse_marovec` holds the ministry,
    so appointing her chief of staff is legal exactly when the same decision also orders the post
    she is leaving. Charged once -- for the destination -- because the origin is being vacated,
    not staffed. Both posts move together at `t + 1`, so no turn sees her in two chairs or none.
    """
    state = _load("tiny_valid.yaml")
    resolution = resolve_turn(
        state,
        _decide(
            state,
            CabinetOrder(post=_CoS, character_id="ilse_marovec"),
            CabinetOrder(post=_FM, character_id="hal_verrin"),
        ),
    )
    assert _offices(resolution.state) == {
        "chief_of_staff": "ilse_marovec",
        "foreign_minister": "hal_verrin",
    }
    assert _row(resolution, _CoS).capital_committed == 276
    assert _row(resolution, _FM).capital_committed == 147
    for post in CabinetPost:
        assert _row(resolution, post).closing_effective_from_turn == resolution.state.turn


def test_a_lone_order_that_would_seat_one_person_twice_is_refused() -> None:
    """The same appointment WITHOUT the origin order. This is why the projection reports
    `requires_vacating_post` rather than marking the candidate ineligible: she is perfectly
    appointable -- `candidate_accepts_post` is true -- and it is this decision that is
    incomplete."""
    state = _load("tiny_valid.yaml")
    decisions = _decide(state, CabinetOrder(post=_CoS, character_id="ilse_marovec"))
    with pytest.raises(TurnResolutionError) as exc_info:
        resolve_turn(state, decisions)
    assert "cabinet_character_would_hold_two_posts" in str(exc_info.value)


def test_one_illegal_order_refuses_the_whole_decision_and_applies_none_of_it() -> None:
    """Atomicity, proved against the state rather than asserted: a set pairing a perfectly legal
    replacement with an illegal one leaves the cabinet byte-identical to how it opened."""
    state = _load("tiny_valid.yaml")
    with pytest.raises(TurnResolutionError):
        resolve_turn(
            state,
            _decide(
                state,
                CabinetOrder(post=_CoS, character_id="wren_hollis"),
                CabinetOrder(post=_FM, character_id="tomas_bekker"),
            ),
        )
    assert _offices(state) == {"chief_of_staff": "hal_verrin", "foreign_minister": "ilse_marovec"}


# --- decision shape ------------------------------------------------------------------------------


def test_orders_are_rejected_not_sorted_and_never_duplicated() -> None:
    """`decisions_json` is hash-covered, so two semantically identical sets listed in different
    orders would digest differently. Rejected, never normalized."""
    with pytest.raises(ValidationError, match="cabinet_orders_not_canonical"):
        CabinetDecision(
            orders=(
                CabinetOrder(post=_FM, character_id="a"),
                CabinetOrder(post=_CoS, character_id="b"),
            )
        )
    with pytest.raises(ValidationError, match="cabinet_duplicate_post"):
        CabinetDecision(
            orders=(
                CabinetOrder(post=_CoS, character_id="a"),
                CabinetOrder(post=_CoS, character_id="b"),
            )
        )
    with pytest.raises(ValidationError, match="cabinet_orders_empty"):
        CabinetDecision(orders=())


def test_at_most_one_cabinet_decision_per_set() -> None:
    one = CabinetDecision(orders=(CabinetOrder(post=_CoS, character_id="a"),))
    with pytest.raises(ValidationError, match="at most one cabinet decision"):
        DecisionSet(expected_turn=0, expected_state_version=0, decisions=[one, one])


def test_the_digest_covers_every_field_and_is_order_stable() -> None:
    """Computed from `model_dump(mode="json")`, so a new field is covered by construction rather
    than by remembering to add it here."""
    a = CabinetDecision(orders=(CabinetOrder(post=_CoS, character_id="x"),))
    b = CabinetDecision(orders=(CabinetOrder(post=_CoS, character_id="y"),))
    c = CabinetDecision(orders=(CabinetOrder(post=_CoS),))
    digests = {cabinet_decision_digest(d) for d in (a, b, c)}
    assert len(digests) == 3
    assert cabinet_decision_digest(a) == cabinet_decision_digest(
        CabinetDecision(orders=(CabinetOrder(post=_CoS, character_id="x"),))
    )


# --- the ledger, and what a dismissal deliberately does not produce ------------------------------


def test_two_paid_appointments_produce_exactly_one_aggregated_ledger_row() -> None:
    """`CABINET_APPOINTMENT` is untargeted, so two rows would share the sort key
    `(category, "", "")` exactly and their canonical order would fall back to insertion order.
    One aggregated row keeps the ledger's order a property of its own key -- the same shape
    `DECREE` has always had."""
    state = _load("decree_state.yaml")
    resolution = resolve_turn(
        state,
        _decide(
            state,
            CabinetOrder(post=_CoS, character_id="edda_thorne"),
            CabinetOrder(post=_FM, character_id="yannic_pell"),
        ),
    )
    assert _row(resolution, _CoS).capital_committed == 147
    assert _row(resolution, _FM).capital_committed == 197

    assert resolution.report.political_capital is not None
    rows = [
        row
        for row in resolution.report.political_capital.expenditures
        if row.category is CapitalExpenditureCategory.CABINET_APPOINTMENT
    ]
    assert len(rows) == 1
    assert rows[0].political_capital == 344
    assert rows[0].party_id is None and rows[0].bloc_id is None


def test_a_dismissal_only_turn_produces_no_ledger_row_at_all() -> None:
    state = _load("tiny_valid.yaml")
    resolution = resolve_turn(state, _decide(state, CabinetOrder(post=_FM)))
    assert resolution.report.political_capital is not None
    assert not [
        row
        for row in resolution.report.political_capital.expenditures
        if row.category is CapitalExpenditureCategory.CABINET_APPOINTMENT
    ]
    assert resolution.report.political_capital.total_committed == 0


# --- visibility: the entry is the only surface a dismissal reaches --------------------------------


def test_a_dismissal_is_visible_on_the_turn_result_and_in_history() -> None:
    """The reason cabinet changes emit report ENTRIES at all. `build_turn_result` derives its
    `drivers` from `report.entries` and its `ledger` from the expenditure rows, and a dismissal has
    no expenditure row -- so without an entry it would be invisible on every API surface. The same
    builder serves live resolution and history detail, so proving it once proves both."""
    state = _load("tiny_valid.yaml")
    resolution = resolve_turn(state, _decide(state, CabinetOrder(post=_FM)))
    projection = build_turn_result(resolution.state, resolution.report)

    (driver,) = [item for item in projection.drivers if item.reason_id == "cabinet_dismissed"]
    assert driver.params["outgoing_character_display_name"] == "Ilse Marovec"
    assert driver.label
    assert not [entry for entry in projection.ledger if "abinet" in entry.label]


def test_an_old_turn_renders_from_its_own_stored_names() -> None:
    """Snapshotted display names, checked the only way that means anything: emptying the character
    registry from the state the projection is built against. A person renamed or dropped from the
    roster must not be able to rewrite what a past turn said."""
    state = _load("tiny_valid.yaml")
    resolution = resolve_turn(
        state, _decide(state, CabinetOrder(post=_CoS, character_id="wren_hollis"))
    )
    forgotten = resolution.state.model_copy(
        update={"world": resolution.state.world.model_copy(update={"characters": {}})}
    )
    projection = build_turn_result(forgotten, resolution.report)
    (driver,) = [item for item in projection.drivers if item.reason_id == "cabinet_replaced"]
    assert driver.params["character_display_name"] == "Wren Hollis"
    assert driver.params["outgoing_character_display_name"] == "Hal Verrin"


# --- reconciliation: group 57 -------------------------------------------------------------------


def _resolved_replacement():  # type: ignore[no-untyped-def]
    state = _load("tiny_valid.yaml")
    decisions = _decide(state, CabinetOrder(post=_CoS, character_id="wren_hollis"))
    return state, decisions, resolve_turn(state, decisions)


def test_a_clean_cabinet_turn_reconciles() -> None:
    state, decisions, resolution = _resolved_replacement()
    assert (
        reconcile_political_legislative_and_survival_report(
            opening_state=state,
            closing_state=resolution.state,
            report=resolution.report,
            decisions=decisions,
        )
        == []
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("capital_committed", 300),
        ("opening_holder_competence_bps", 9_999),
        ("opening_holder_id", "tomas_bekker"),
        ("closing_holder_id", "tomas_bekker"),
        ("closing_effective_from_turn", 0),
    ],
)
def test_a_forged_row_field_is_caught_against_state(field: str, value: object) -> None:
    """Each of these leaves the row's OWN arithmetic untouched or repairs it; only a comparison
    against `opening_state`/`closing_state` catches them. `model_copy` bypasses the row validators
    deliberately -- the point is to make reconciliation reject it, not the constructor."""
    state, decisions, resolution = _resolved_replacement()
    assert resolution.report.governance is not None
    rows = list(resolution.report.governance.posts)
    rows[0] = rows[0].model_copy(update={field: value})
    forged = resolution.report.model_copy(
        update={
            "governance": resolution.report.governance.model_copy(update={"posts": tuple(rows)})
        }
    )
    problems = reconcile_political_legislative_and_survival_report(
        opening_state=state,
        closing_state=resolution.state,
        report=forged,
        decisions=decisions,
    )
    assert [problem for problem in problems if "group 57" in problem]


def test_a_change_reported_with_no_decision_submitted_is_caught() -> None:
    """Non-retroactivity: a turn that submitted no cabinet decision cannot report one."""
    state, _, resolution = _resolved_replacement()
    empty = DecisionSet(expected_turn=state.turn, expected_state_version=state.state_version)
    problems = reconcile_political_legislative_and_survival_report(
        opening_state=state,
        closing_state=resolution.state,
        report=resolution.report,
        decisions=empty,
    )
    assert [problem for problem in problems if "group 57" in problem]


def test_a_stripped_or_forged_entry_is_caught() -> None:
    state, decisions, resolution = _resolved_replacement()
    stripped = resolution.report.model_copy(
        update={
            "entries": tuple(e for e in resolution.report.entries if e.category != "government")
        }
    )
    assert [
        problem
        for problem in reconcile_political_legislative_and_survival_report(
            opening_state=state,
            closing_state=resolution.state,
            report=stripped,
            decisions=decisions,
        )
        if "group 57" in problem
    ]

    entries = [
        e.model_copy(update={"params": {**e.params, "character_display_name": "Someone Else"}})
        if e.category == "government"
        else e
        for e in resolution.report.entries
    ]
    renamed = resolution.report.model_copy(update={"entries": tuple(entries)})
    assert [
        problem
        for problem in reconcile_political_legislative_and_survival_report(
            opening_state=state,
            closing_state=resolution.state,
            report=renamed,
            decisions=decisions,
        )
        if "group 57" in problem
    ]


# --- the API surfaces ----------------------------------------------------------------------------


def test_a_transfer_candidate_accepts_the_post_and_names_the_one_to_vacate() -> None:
    """The correction this projection exists for, in one candidate.

    `ilse_marovec` is illegal as a LONE chief-of-staff appointment and perfectly legal when the
    same decision vacates her ministry, so a single per-candidate verdict could never be truthful
    about her. The field is therefore named `candidate_accepts_post` -- a statement about the
    PERSON -- and the two structural facts are given separately, as instructions rather than as
    refusals.
    """
    options = build_decision_options(_load("tiny_valid.yaml"))
    (chief,) = [post for post in options.cabinet_posts if post.post == "chief_of_staff"]
    (ilse,) = [c for c in chief.candidates if c.character_id == "ilse_marovec"]

    assert ilse.candidate_accepts_post is True
    assert ilse.currently_holds_post == "foreign_minister"
    assert ilse.requires_vacating_post == "foreign_minister"

    assert ilse.refusal_code is None
    assert ilse.verb == "replace"
    assert ilse.appointment_cost == 276


def test_no_foreign_character_ever_appears_as_a_candidate() -> None:
    """A government may only appoint its own people, so a foreign profile's leader is not a
    candidate anywhere -- not listed-and-refused, ABSENT. Offering somebody the resolver would
    reject with `cabinet_character_not_domestic` would be inviting a decision that cannot succeed.

    Checked against every scenario, and against the roster rather than a hand-written list: any
    character whose affiliation is not this player country must be missing from every candidate
    collection, whatever their traits.
    """
    for scenario in ("tiny_valid.yaml", "decree_state.yaml", "deficit_demo.yaml"):
        state = _load(scenario)
        player_id = state.world.player_country_id
        foreign = {
            character_id
            for character_id, character in state.world.characters.items()
            if not is_domestic_to(character=character, country_id=player_id)
        }
        assert foreign, scenario  # every scenario authors foreign leaders; else this proves nothing

        options = build_decision_options(state)
        assert options.cabinet_posts, scenario
        offered = {
            candidate.character_id
            for post in options.cabinet_posts
            for candidate in post.candidates
        }
        assert offered, scenario
        assert not (offered & foreign), (scenario, sorted(offered & foreign))
        # And the exclusion is by AFFILIATION, not by luck: every offered candidate is domestic.
        for character_id in offered:
            assert is_domestic_to(
                character=state.world.characters[character_id], country_id=player_id
            ), (scenario, character_id)


def test_the_incumbent_of_a_post_is_marked_rather_than_refused() -> None:
    options = build_decision_options(_load("tiny_valid.yaml"))
    (chief,) = [post for post in options.cabinet_posts if post.post == "chief_of_staff"]
    (hal,) = [c for c in chief.candidates if c.character_id == "hal_verrin"]
    assert hal.currently_holds_post == "chief_of_staff"
    assert hal.candidate_accepts_post is True
    assert hal.requires_vacating_post is None
    assert chief.holder_character_id == "hal_verrin"
    assert chief.can_dismiss is True


def test_no_candidate_ever_carries_a_whole_decision_failure() -> None:
    """Codes 8 and affordability are properties of a DRAFT, not of a person. Stating them here
    would make them unconditional refusals. Scanned across every post and candidate in all three
    scenarios so the guarantee is about the projection and not about one lucky case."""
    forbidden = {"cabinet_character_would_hold_two_posts", "cabinet_dismissal_of_a_vacant_post"}
    for scenario in ("tiny_valid.yaml", "decree_state.yaml", "deficit_demo.yaml"):
        options = build_decision_options(_load(scenario))
        assert options.cabinet_posts
        for post in options.cabinet_posts:
            for candidate in post.candidates:
                assert candidate.refusal_code not in forbidden, (scenario, candidate.character_id)
                assert (candidate.refusal_code is None) == candidate.candidate_accepts_post, (
                    scenario,
                    candidate.character_id,
                )


def test_preview_prices_the_draft_and_reports_unaffordability() -> None:
    """Where the whole-decision verdicts DO live. The cabinet term is priced through the engine's
    own `appointment_cost_capital`, so a preview cannot quote a price the resolver would not
    charge."""
    state = _load("deficit_demo.yaml")
    affordable = preview_decisions(
        state, _decide(state, CabinetOrder(post=_CoS, character_id="bela_ronsard"))
    )
    assert affordable.cabinet_capital == 147
    assert affordable.committed_capital == 147
    assert affordable.opening_capital == 300
    assert affordable.affordable is True

    both = preview_decisions(
        state,
        _decide(
            state,
            CabinetOrder(post=_CoS, character_id="bela_ronsard"),
            CabinetOrder(post=_FM, character_id="freya_lund"),
        ),
    )
    assert both.cabinet_capital == 344
    assert both.affordable is False


def test_a_weak_government_cannot_staff_a_whole_cabinet_at_once() -> None:
    """The authored affordability boundary, and a real statement about the game: at legitimacy
    6,000 only two of `deficit_demo`'s four candidates will serve, and filling both vacant posts
    with them costs 344 against an opening 300."""
    state = _load("deficit_demo.yaml")
    with pytest.raises(TurnResolutionError) as exc_info:
        resolve_turn(
            state,
            _decide(
                state,
                CabinetOrder(post=_CoS, character_id="bela_ronsard"),
                CabinetOrder(post=_FM, character_id="freya_lund"),
            ),
        )
    assert "344" in str(exc_info.value) and "300" in str(exc_info.value)
    assert _offices(state) == {}


# --- and it survives being written down and read back --------------------------------------------


def test_a_campaign_that_hires_replaces_and_dismisses_replays_cleanly() -> None:
    """`validate_history` re-runs reconciliation over every stored entry, so a cabinet change that
    did not survive serialization surfaces here as a group 57 problem rather than as a silently
    different cabinet."""
    save = new_game(_load("tiny_valid.yaml"), save_format_version=SAVE_FORMAT_VERSION)
    plan = (
        # Replace, then dismiss, then appoint into the vacancy that dismissal left -- all three
        # verbs across three consecutive turns of one campaign.
        (CabinetOrder(post=_CoS, character_id="wren_hollis"),),
        (CabinetOrder(post=_FM),),
        (CabinetOrder(post=_FM, character_id="hal_verrin"),),
    )
    for orders in plan:
        state = save.entries[-1].state()
        save = advance_game(save, _decide(state, *orders))
    assert validate_history(save) == []

    assert _offices(save.entries[-1].state()) == {
        "chief_of_staff": "wren_hollis",
        "foreign_minister": "hal_verrin",
    }
    changes = []
    for entry in save.entries[1:]:
        report = entry.report()
        assert report is not None and report.governance is not None
        changes.extend(
            row.change.value
            for row in report.governance.posts
            if row.change is not CabinetChange.UNCHANGED
        )
    assert changes == ["replaced", "dismissed", "appointed"]


# --- the post's own label is stored, and the quiet line is said exactly once ----------------------


def test_the_row_and_the_entry_both_store_the_posts_display_name() -> None:
    """Every word a rendered sentence uses comes from the report, not from a transformation of an
    identifier. That is what lets a post be relabelled without rewriting what past turns said."""
    state = _load("tiny_valid.yaml")
    resolution = resolve_turn(
        state, _decide(state, CabinetOrder(post=_CoS, character_id="wren_hollis"))
    )
    assert resolution.report.governance is not None
    labels = {row.post.value: row.post_display_name for row in resolution.report.governance.posts}
    assert labels == {"chief_of_staff": "chief of staff", "foreign_minister": "foreign minister"}
    assert labels == {post.value: name for post, name in POST_DISPLAY_NAMES.items()}

    (entry,) = [e for e in resolution.report.entries if e.category == "government"]
    assert entry.params["post"] == "chief_of_staff"
    assert entry.params["post_display_name"] == "chief of staff"


def test_an_old_turn_keeps_its_own_post_label_when_the_build_relabels_the_post() -> None:
    """The snapshot's whole purpose, checked the only way that means anything: render a stored
    entry through the real renderer with no access to `POST_DISPLAY_NAMES` at all."""
    params: dict[str, str | int] = {
        "post": "foreign_minister",
        "post_display_name": "minister for foreign affairs",
        "capital_committed": 0,
        "outgoing_character_id": "ilse_marovec",
        "outgoing_character_display_name": "Ilse Marovec",
    }
    sentence = REASON_RENDERERS["cabinet_dismissed"](params)
    assert "minister for foreign affairs" in sentence
    assert "foreign_minister" not in sentence


def test_a_quiet_turn_says_no_cabinet_changes_exactly_once_on_each_surface(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Once in the API's "what did not change" channel, once in the CLI -- and once only.

    The CLI count is the regression test for double-printing: both CLI paths render
    `report.entries` first and the per-report blocks second, so a block that also printed changes
    would say them twice. It prints only the quiet sentence, which is exactly why a QUIET turn is
    where "exactly once" is worth pinning.
    """
    state = _load("tiny_valid.yaml")
    quiet = resolve_turn(
        state, DecisionSet(expected_turn=state.turn, expected_state_version=state.state_version)
    )
    projection = build_turn_result(quiet.state, quiet.report)
    assert [line for line in projection.unchanged if line == "No cabinet changes."] == [
        "No cabinet changes."
    ]
    assert not [item for item in projection.drivers if item.reason_id.startswith("cabinet_")]

    save = tmp_path / "save0.json"
    assert (
        main(["new", "--scenario", str(SCENARIO_DIR / "tiny_valid.yaml"), "--out", str(save)]) == 0
    )
    resolved = tmp_path / "save1.json"
    capsys.readouterr()
    assert main(["resolve", "--state", str(save), "--turns", "1", "--out", str(resolved)]) == 0
    assert capsys.readouterr().out.count("No cabinet changes.") == 1

    assert main(["history", "--state", str(resolved), "--turn", "1"]) == 0
    assert capsys.readouterr().out.count("No cabinet changes.") == 1


def test_a_turn_with_changes_says_the_quiet_line_on_neither_surface() -> None:
    """The anti-vacuity half: "exactly once" must not be satisfied by a line that is always
    printed. A turn that DID change the cabinet says nothing of the kind, anywhere."""
    state = _load("tiny_valid.yaml")
    busy = resolve_turn(state, _decide(state, CabinetOrder(post=_FM)))
    projection = build_turn_result(busy.state, busy.report)
    assert "No cabinet changes." not in projection.unchanged
    assert [item for item in projection.drivers if item.reason_id == "cabinet_dismissed"]


def test_the_cli_prints_a_real_change_exactly_once_in_both_paths(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The other half of the double-print guarantee, on the loud path."""
    save = tmp_path / "save0.json"
    assert (
        main(["new", "--scenario", str(SCENARIO_DIR / "tiny_valid.yaml"), "--out", str(save)]) == 0
    )
    orders = tmp_path / "orders.json"
    orders.write_text(
        json.dumps(
            {
                "expected_turn": 0,
                "expected_state_version": 0,
                "decisions": [
                    {
                        "kind": "cabinet",
                        "orders": [{"post": "chief_of_staff", "character_id": "wren_hollis"}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    resolved = tmp_path / "save1.json"
    capsys.readouterr()
    assert (
        main(
            [
                "resolve",
                "--state",
                str(save),
                "--turns",
                "1",
                "--decisions-file",
                str(orders),
                "--out",
                str(resolved),
            ]
        )
        == 0
    )
    resolve_out = capsys.readouterr().out
    sentence = "Wren Hollis replaced Hal Verrin as chief of staff for 197 political capital."
    assert resolve_out.count(sentence) == 1
    assert resolve_out.count("No cabinet changes.") == 0

    assert main(["history", "--state", str(resolved), "--turn", "1"]) == 0
    assert capsys.readouterr().out.count(sentence) == 1


def test_the_projection_labels_every_post_from_the_authored_map() -> None:
    """No client ever has to rewrite `chief_of_staff` into prose -- the transformation the CLI had
    and lost. Checked against `POST_DISPLAY_NAMES` itself rather than against literals, so the map
    stays the single source of the words."""
    for scenario in ("tiny_valid.yaml", "decree_state.yaml", "deficit_demo.yaml"):
        options = build_decision_options(_load(scenario))
        labels = {post.post: post.post_display_name for post in options.cabinet_posts}
        assert labels == {post.value: name for post, name in POST_DISPLAY_NAMES.items()}, scenario


def test_every_post_a_candidate_references_resolves_to_a_projected_row() -> None:
    """`currently_holds_post` and `requires_vacating_post` are identifiers a client matches against
    `CabinetPostOption.post`. If one ever named a post the projection does not carry, the client
    would be forced to invent a label -- so the lookup is proved total here rather than defended by
    a fallback in the screen."""
    for scenario in ("tiny_valid.yaml", "decree_state.yaml", "deficit_demo.yaml"):
        options = build_decision_options(_load(scenario))
        known = {post.post for post in options.cabinet_posts}
        referenced = {
            value
            for post in options.cabinet_posts
            for candidate in post.candidates
            for value in (candidate.currently_holds_post, candidate.requires_vacating_post)
            if value is not None
        }
        assert referenced <= known, (scenario, sorted(referenced - known))
        # Anti-vacuity, where the content actually supports it: a scenario whose posts are all
        # vacant legitimately references none, so requiring a non-empty set everywhere would only
        # be asserting `deficit_demo`'s emptiness in a confusing place.
        if any(post.holder_character_id is not None for post in options.cabinet_posts):
            assert referenced, scenario


def test_a_resolved_save_stores_no_client_side_provenance() -> None:
    """The UI tracks WHY it added a companion dismissal (`origin`, `generatedBy`,
    `requiresVacatingPost`). None of that is a decision, and `CabinetOrder` is `extra="forbid"`, so
    none of it can reach the wire -- but `decisions_json` is hash-covered and permanent, so the
    absence is worth asserting against the stored bytes rather than trusting the model."""
    save = new_game(_load("tiny_valid.yaml"), save_format_version=SAVE_FORMAT_VERSION)
    state = save.entries[-1].state()
    save = advance_game(
        save,
        _decide(
            state,
            CabinetOrder(post=_CoS, character_id="ilse_marovec"),
            CabinetOrder(post=_FM),
        ),
    )
    stored = save.entries[-1].decisions_json
    assert stored is not None
    for ui_only in ("origin", "generatedBy", "requiresVacatingPost", "generated_by"):
        assert ui_only not in stored, ui_only
    assert "chief_of_staff" in stored and "ilse_marovec" in stored
