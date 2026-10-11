"""Gate 4A3 M-0: the projections the redesigned Legislature and result screens read, checked
against the ENGINE and the stored reports -- never against their own arithmetic.

* `chamber_details` thresholds equal the engine's threshold functions and every card's own
  `PolicyCardChamberRequirement`.
* `BlocOption`'s relationship, role and preferences equal state.
* `ChamberPreview.blocs` sums to each chamber's total, and for a legislative budget each bloc's
  projected seats equal the resolved `BlocVoteReport.supporting_seats`.
* `recorded_vote` / `no_vote_reason` come from the stored report; exactly one is set; every stored
  outcome is classified (a new one fails); "no legislature" is unreachable.
* `last_recorded_vote` finds the last turn that HELD a vote, skipping decree and no-proposal turns,
  with that turn's own tallies, filed under History's turn number; the API serves it, and a reload
  from the save serves the same.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.main import ApiSettings, create_app
from app.api.policy_cards import build_decision_options_with_policy_cards
from app.api.preview import preview_decisions
from app.api.projections import build_decision_options, build_turn_result
from app.api.votes import held_a_vote, last_recorded_vote, no_vote_reason, recorded_vote
from app.core.errors import TurnResolutionError
from app.simulation.constitution import DecreeAuthority, Legislature
from app.simulation.decisions import (
    BudgetDecision,
    CabinetDecision,
    CabinetOrder,
    InfluenceAllocation,
    LegislativeBargainDecision,
)
from app.simulation.history import advance_game, new_game
from app.simulation.legislative_voting import (
    required_amendment_yes_seats,
    required_yes_seats,
)
from app.simulation.legislature import AmendmentThreshold, LegislativeOutcome, ProposalRoute
from app.simulation.resolver import resolve_turn
from app.simulation.save_format import SAVE_FORMAT_VERSION
from app.simulation.state import CabinetPost, GameState
from tests.conftest import SCENARIO_DIR, make_country, make_game_state, make_politics
from tests.test_campaign_objective import (
    DECREE_NONE,
    FOUR_AXIS,
    INTERVAL,
    _amend,
    _load,
    _politics,
    _resolve,
    _set,
)
from tests.test_effect_explanations import _invest_everywhere

SCENARIOS = ("decree_state", "tiny_valid", "deficit_demo")


def _cut(route: ProposalRoute = ProposalRoute.LEGISLATIVE, **kw: object) -> BudgetDecision:
    return BudgetDecision(personal_income_rate_bps=1800, route=route, **kw)  # type: ignore[arg-type]


# ---------------------------------------------------------------- decision options


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_chamber_details_are_the_engine_thresholds_and_agree_with_every_card(scenario: str) -> None:
    state = _load(scenario)
    legislature = _politics(state).legislature
    assert legislature is not None
    options = build_decision_options_with_policy_cards(state)
    difficulty = AmendmentThreshold(_politics(state).constitution.amendment_difficulty.value)
    assert [d.chamber for d in options.chamber_details] == list(options.chambers)
    for detail, chamber in zip(options.chamber_details, legislature.chambers, strict=True):
        assert detail.total_seats == chamber.total_seats
        assert detail.budget_required_seats == required_yes_seats(total_seats=chamber.total_seats)
        assert detail.amendment_required_seats == required_amendment_yes_seats(
            total_seats=chamber.total_seats, difficulty=difficulty
        )
    by_chamber = {d.chamber: d for d in options.chamber_details}
    checked = 0
    for card in options.policy_cards:
        for route in card.routes:
            for requirement in route.chambers:
                detail = by_chamber[requirement.chamber]
                expected = (
                    detail.amendment_required_seats
                    if card.category == "constitution"
                    else detail.budget_required_seats
                )
                assert requirement.required_seats == expected, card.card_id
                assert requirement.total_seats == detail.total_seats
                checked += 1
    assert checked > 0, "the comparison must not be vacuous"


@pytest.mark.parametrize("scenario", SCENARIOS)
@pytest.mark.parametrize("after_a_turn", [False, True])
def test_bloc_options_carry_the_blocs_state(scenario: str, after_a_turn: bool) -> None:
    state = _load(scenario)
    if after_a_turn:
        # A resolved relationship investment in every bloc moves relationships off their
        # baselines, so the CURRENT relationship is distinguishable from the authored baseline.
        state = _resolve(state, _invest_everywhere(state, 50)).state
    legislature = _politics(state).legislature
    assert legislature is not None
    parties = {party.id: party for party in legislature.parties}
    moved = 0
    for option in build_decision_options(state).blocs:
        party = parties[option.party_id]
        bloc = next(b for b in party.blocs if b.id == option.bloc_id)
        assert option.government_relationship_bps == bloc.government_relationship_bps
        assert option.government_role == party.government_role.value
        assert option.tax_preference_bps == bloc.tax_preference_bps
        assert option.spending_preference_bps == bloc.spending_preference_bps
        moved += bloc.government_relationship_bps != bloc.baseline_government_relationship_bps
    if after_a_turn:
        assert moved > 0, "the check must see a relationship that differs from its baseline"


# ---------------------------------------------------------------- preview bloc rows


def _bargain_with_dealing_leader(state: GameState) -> LegislativeBargainDecision | None:
    options = build_decision_options(state)
    dealer = next((c for c in options.legislative_bargain_counterparties if c.will_deal), None)
    if dealer is None:
        return None
    return LegislativeBargainDecision(character_id=dealer.character_id, proposal_kind="budget")


@pytest.mark.parametrize("scenario", SCENARIOS)
@pytest.mark.parametrize("with_bargain", [False, True])
def test_preview_bloc_rows_equal_the_resolved_bloc_votes(scenario: str, with_bargain: bool) -> None:
    state = _load(scenario)
    decisions: list[object] = [_cut()]
    if with_bargain:
        bargain = _bargain_with_dealing_leader(state)
        if bargain is None:
            pytest.skip(f"{scenario} has no leader who will deal")
        decisions.append(bargain)
    preview = preview_decisions(state, _set(state, *decisions))
    resolved = _resolve(state, *decisions).report.legislative
    assert resolved is not None and resolved.chambers
    recorded = {
        (b.chamber.value, b.party_id, b.bloc_id): b.supporting_seats for b in resolved.blocs
    }
    for chamber in preview.chambers:
        assert chamber.blocs, "every legislative chamber preview carries its bloc rows"
        assert sum(row.supporting_seats for row in chamber.blocs) == chamber.supporting_seats
        for row in chamber.blocs:
            assert row.supporting_seats == recorded[(chamber.chamber, row.party_id, row.bloc_id)]


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_amendment_preview_bloc_rows_sum_to_each_chamber(scenario: str) -> None:
    state = _load(scenario)
    # A legal amendment in each scenario: Valdrun needs all four axes; the others only decree.
    targets = FOUR_AXIS if scenario == "decree_state" else DECREE_NONE
    preview = preview_decisions(state, _set(state, _amend(*targets)))
    assert preview.chambers
    for chamber in preview.chambers:
        assert sum(row.supporting_seats for row in chamber.blocs) == chamber.supporting_seats


def test_a_decree_preview_has_no_chambers_and_so_no_bloc_rows() -> None:
    state = _load("decree_state")
    preview = preview_decisions(state, _set(state, _cut(ProposalRoute.DECREE)))
    assert preview.chambers == ()


# ---------------------------------------------------------------- recorded votes, per turn


def _turn_result(state: GameState, *decisions: object):  # noqa: ANN202
    resolution = _resolve(state, *decisions)
    return resolution, build_turn_result(resolution.state, resolution.report, opening_state=state)


def test_a_passed_legislative_budget_records_both_chambers_with_bloc_rows() -> None:
    state = _load("tiny_valid")
    resolution, result = _turn_result(state, _cut())
    assert result.no_vote_reason is None
    vote = result.recorded_vote
    assert (
        vote is not None and vote.proposal_kind == "budget" and vote.outcome == "passed_legislative"
    )
    assert vote.blocs_recorded
    stored = resolution.report.legislative
    assert stored is not None
    assert [(c.chamber, c.supporting_seats, c.required_seats, c.passed) for c in vote.chambers] == [
        (c.chamber.value, c.supporting_seats, c.required_yes_seats, c.passed)
        for c in stored.chambers
    ]
    for chamber in vote.chambers:
        assert sum(b.supporting_seats for b in chamber.blocs) == chamber.supporting_seats
        assert all(b.bloc_display_name and b.bloc_display_name != b.bloc_id for b in chamber.blocs)
    assert vote.budget is not None and vote.budget.tax_direction == stored.tax_direction.value


def test_a_failed_legislative_budget_records_the_shortfall() -> None:
    state = _load("decree_state")
    _, result = _turn_result(state, _cut())
    vote = result.recorded_vote
    assert vote is not None and vote.outcome == "failed_legislative"
    assert [(c.supporting_seats, c.required_seats, c.passed) for c in vote.chambers] == [
        (45, 51, False)
    ]


def test_an_amendment_vote_records_chamber_totals_and_no_bloc_rows() -> None:
    state = _load("decree_state")
    resolution, result = _turn_result(state, _amend(*FOUR_AXIS, influence=300))
    vote = result.recorded_vote
    assert vote is not None and vote.proposal_kind == "constitutional_amendment"
    assert not vote.blocs_recorded
    assert all(chamber.blocs == () for chamber in vote.chambers)
    stored = resolution.report.constitutional_amendment
    assert stored is not None
    assert [(c.supporting_seats, c.required_seats) for c in vote.chambers] == [
        (c.supporting_seats, c.required_yes_seats) for c in stored.chambers
    ]
    assert {t.axis for t in vote.amendment_targets} == {str(t.axis) for t in stored.targets}


def test_a_decree_budget_says_enacted_by_decree_and_records_no_vote() -> None:
    state = _load("decree_state")
    resolution, result = _turn_result(state, _cut(ProposalRoute.DECREE))
    assert resolution.report.legislative is not None
    assert resolution.report.legislative.outcome is LegislativeOutcome.ENACTED_BY_DECREE
    assert result.recorded_vote is None
    assert result.no_vote_reason == "enacted_by_decree"


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_a_turn_with_no_proposal_says_so(scenario: str) -> None:
    state = _load(scenario)
    _, result = _turn_result(state)
    assert result.recorded_vote is None and result.no_vote_reason == "no_proposal"


def test_an_appointment_only_turn_says_no_proposal() -> None:
    state = _load("decree_state")
    chief = next(
        p for p in build_decision_options(state).cabinet_posts if p.post == "chief_of_staff"
    )
    candidate = next(
        c for c in chief.candidates if c.candidate_accepts_post and c.requires_vacating_post is None
    )
    appoint = CabinetDecision(
        orders=(CabinetOrder(post=CabinetPost.CHIEF_OF_STAFF, character_id=candidate.character_id),)
    )
    _, result = _turn_result(state, appoint)
    assert result.no_vote_reason == "no_proposal"


def test_every_stored_outcome_is_classified_and_nothing_else_is_guessed() -> None:
    """Walks every `LegislativeOutcome` through `no_vote_reason` on a real stored report with its
    chambers emptied: the two no-vote outcomes are named, the two vote outcomes cannot occur without
    chambers and are refused, and a new outcome would fail this test until classified."""
    state = _load("decree_state")
    report = _resolve(state).report
    assert report.legislative is not None
    assert set(LegislativeOutcome) == {
        LegislativeOutcome.NO_PROPOSAL,
        LegislativeOutcome.PASSED_LEGISLATIVE,
        LegislativeOutcome.FAILED_LEGISLATIVE,
        LegislativeOutcome.ENACTED_BY_DECREE,
    }
    expected = {
        LegislativeOutcome.NO_PROPOSAL: "no_proposal",
        LegislativeOutcome.ENACTED_BY_DECREE: "enacted_by_decree",
    }
    for outcome in LegislativeOutcome:
        legislative = report.legislative.model_copy(update={"outcome": outcome, "chambers": ()})
        changed = report.model_copy(update={"legislative": legislative})
        if outcome in expected:
            assert no_vote_reason(changed) == expected[outcome]
        else:
            with pytest.raises(ValueError, match="no recorded chamber vote"):
                no_vote_reason(changed)
    amendment = report.constitutional_amendment
    assert amendment is not None
    for outcome in (LegislativeOutcome.PASSED_LEGISLATIVE, LegislativeOutcome.FAILED_LEGISLATIVE):
        odd = report.model_copy(
            update={
                "constitutional_amendment": amendment.model_copy(
                    update={"proposed": True, "outcome": outcome, "chambers": ()}
                )
            }
        )
        with pytest.raises(ValueError, match="no chamber vote is recorded"):
            no_vote_reason(odd)
    decreed = report.model_copy(
        update={
            "constitutional_amendment": amendment.model_copy(
                update={"proposed": True, "outcome": LegislativeOutcome.ENACTED_BY_DECREE}
            )
        }
    )
    assert no_vote_reason(decreed) == "enacted_by_decree"
    with pytest.raises(ValueError, match="without a legislative report"):
        no_vote_reason(report.model_copy(update={"legislative": None}))


def test_no_legislature_is_not_a_reason_any_turn_can_carry() -> None:
    """A legislative-route proposal with no sitting legislature is refused before a turn exists,
    so `no_vote_reason` needs no such value."""
    politics = make_politics(
        legislature=Legislature.NONE, decree_authority=DecreeAuthority.UNLIMITED
    )
    state = make_game_state(
        countries={"testland": make_country("testland", politics=politics)},
        player_country_id="testland",
    )
    with pytest.raises(TurnResolutionError, match="no legislature"):
        resolve_turn(state, _set(state, _cut()))
    with pytest.raises(TurnResolutionError, match="requires a legislature"):
        resolve_turn(state, _set(state, _amend(*INTERVAL)))


def test_the_turn_result_requires_exactly_one_of_vote_and_reason() -> None:
    state = _load("tiny_valid")
    _, result = _turn_result(state, _cut())
    with pytest.raises(ValueError, match="exactly one"):
        result.model_validate({**result.model_dump(), "no_vote_reason": "no_proposal"})
    with pytest.raises(ValueError, match="exactly one"):
        result.model_validate({**result.model_dump(), "recorded_vote": None})


# ---------------------------------------------------------------- the last vote actually held


def _advance(save, *decisions: object):  # noqa: ANN001, ANN202
    state = save.current_state()
    return advance_game(save, _set(state, *decisions))


def test_the_last_recorded_vote_skips_decree_and_no_proposal_turns() -> None:
    save = new_game(_load("decree_state"), save_format_version=SAVE_FORMAT_VERSION)
    assert last_recorded_vote(save) is None, "a fresh campaign has held no vote"
    save = _advance(save, _cut())  # turn 1: a legislative budget vote (fails 45 / 51)
    voted_turn = save.current_state().turn
    save = _advance(save, _cut(ProposalRoute.DECREE))  # a decree: no vote
    save = _advance(save)  # no proposal: no vote
    last = last_recorded_vote(save)
    assert last is not None
    assert last.turn == voted_turn
    assert last.vote.proposal_kind == "budget"
    assert [(c.supporting_seats, c.required_seats, c.passed) for c in last.vote.chambers] == [
        (45, 51, False)
    ], "the stored tallies of that turn, not today's"
    # A later amendment vote becomes the last one, with no bloc rows.
    influence = InfluenceAllocation(
        party_id="opposition_party", bloc_id="main", political_capital=300
    )
    amendment = _amend(*FOUR_AXIS).model_copy(update={"influence": (influence,)})
    save = _advance(save, amendment)
    last = last_recorded_vote(save)
    assert last is not None and last.turn == save.current_state().turn
    assert last.vote.proposal_kind == "constitutional_amendment" and not last.vote.blocs_recorded
    # The walk's cheap JSON pre-check agrees with the full parse on every stored turn.
    seen = set()
    for entry in save.entries[1:]:
        assert entry.report_json is not None
        report = entry.report()
        assert report is not None
        held = recorded_vote(entry.state(), report) is not None
        assert held_a_vote(entry.report_json) == held, entry.turn
        seen.add(held)
    assert seen == {True, False}, "both kinds of turn were checked"


def _client(root) -> TestClient:  # noqa: ANN001
    app = create_app(ApiSettings(save_root=root, scenario_root=SCENARIO_DIR, serve_spa=False))
    return TestClient(app, base_url="http://127.0.0.1:8420")


def test_the_api_serves_the_last_vote_under_historys_turn_number_and_a_reload_agrees(
    tmp_path,  # noqa: ANN001
) -> None:
    client = _client(tmp_path / "saves")
    started = client.post("/api/game/new", json={"scenario_id": "decree_state"})
    assert started.status_code == 200
    options = client.get("/api/game/decision-options").json()
    assert options["last_recorded_vote"] is None
    assert [d["budget_required_seats"] for d in options["chamber_details"]] == [51]

    def resolve(decisions: list[dict]) -> None:
        state = client.get("/api/game/state").json()
        response = client.post(
            "/api/game/resolve",
            json={
                "revision": state["revision"],
                "campaign_id": state["campaign_id"],
                "decisions": decisions,
            },
        )
        assert response.status_code == 200, response.text

    resolve([_cut().model_dump(mode="json")])
    resolve([_cut(ProposalRoute.DECREE).model_dump(mode="json")])
    options = client.get("/api/game/decision-options").json()
    last = options["last_recorded_vote"]
    history = client.get("/api/game/history").json()
    assert last["turn"] == history[0]["turn"], "filed under History's own turn number"
    assert last["vote"]["chambers"][0]["supporting_seats"] == 45
    detail = client.get(f"/api/game/history/{history[1]['turn']}").json()["turnResult"]
    assert detail["recorded_vote"] is None and detail["no_vote_reason"] == "enacted_by_decree"

    saved = client.post("/api/game/save-as", json={"display_name": "m0"})
    assert saved.status_code == 200, saved.text
    reloaded = _client(tmp_path / "saves")
    save_id = reloaded.get("/api/saves").json()[0]["save_id"]
    assert reloaded.post("/api/game/load", json={"save_id": save_id}).status_code == 200
    assert reloaded.get("/api/game/decision-options").json()["last_recorded_vote"] == last
