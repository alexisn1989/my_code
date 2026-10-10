"""Gate 4A3 W-2: the explanations of what investments and cabinet posts do -- checked against the
ENGINE, never against the explanation's own arithmetic.

* The preview's per-investment gain must equal what resolution records for that bloc
  (`PoliticalRelationshipReport.blocs[].investment_component_bps`), with and without a serving chief
  of staff, and with a chief of staff appointed in the same draft (who must not count yet).
* A zero-gain investment is flagged by the preview and refused by resolution.
* Each cabinet post's stated effect comes from the engine function that applies it.
"""

from __future__ import annotations

import pytest

from app.api.preview import preview_decisions
from app.api.projections import (
    POST_EFFECT_TEXT,
    build_decision_options,
    candidate_effect_text,
    format_bps_percent,
    post_effect_for_competence,
)
from app.core.errors import TurnResolutionError
from app.simulation.decisions import (
    BlocInvestment,
    BlocRelationshipInvestmentDecision,
    CabinetDecision,
    CabinetOrder,
)
from app.simulation.foreign_assistance import (
    FOREIGN_MINISTER_ASSISTANCE_SHARE_MAX_BPS,
    assistance_share_bps,
)
from app.simulation.invariants import check_invariants
from app.simulation.relationships import (
    CHIEF_OF_STAFF_MAX_BONUS_BPS,
    chief_of_staff_gain_bonus_bps,
    relationship_gain_bps,
)
from app.simulation.state import CabinetPost, GameState
from tests.test_campaign_objective import _load, _politics, _resolve, _set, _set_politics


def _invest_everywhere(state: GameState, capital: int) -> BlocRelationshipInvestmentDecision:
    legislature = _politics(state).legislature
    assert legislature is not None
    rows = sorted(
        (
            BlocInvestment(party_id=party.id, bloc_id=bloc.id, political_capital=capital)
            for party in legislature.parties
            for bloc in party.blocs
        ),
        key=lambda row: (row.party_id, row.bloc_id),
    )
    return BlocRelationshipInvestmentDecision(investments=tuple(rows))


def _resolved_components(resolution: object) -> dict[tuple[str, str], int]:
    report = resolution.report.political_relationship  # type: ignore[attr-defined]
    assert report is not None
    return {(row.party_id, row.bloc_id): row.investment_component_bps for row in report.blocs}


@pytest.mark.parametrize(
    ("scenario", "capital"), [("tiny_valid", 50), ("decree_state", 120), ("deficit_demo", 60)]
)
def test_preview_gain_equals_the_resolved_investment_component(scenario: str, capital: int) -> None:
    state = _load(scenario)
    decision = _invest_everywhere(state, capital)
    preview = preview_decisions(state, _set(state, decision))
    assert preview.affordable, "the fixture spends within opening capital"
    resolved = _resolved_components(_resolve(state, decision))
    assert preview.investment_effects, "every drafted investment is reported"
    for row in preview.investment_effects:
        assert row.gain_bps == resolved[(row.party_id, row.bloc_id)], row.bloc_display_name
        assert not row.no_effect
    if scenario == "tiny_valid":
        # A serving chief of staff: the bonus is the engine's own share of the base gain.
        assert all(row.chief_of_staff_bonus_bps > 0 for row in preview.investment_effects)
    else:
        assert all(row.chief_of_staff_bonus_bps == 0 for row in preview.investment_effects)


def test_a_chief_of_staff_appointed_in_the_same_draft_does_not_count_yet() -> None:
    state = _load("decree_state")
    options = build_decision_options(state)
    chief = next(post for post in options.cabinet_posts if post.post == "chief_of_staff")
    candidate = next(
        c for c in chief.candidates if c.candidate_accepts_post and c.requires_vacating_post is None
    )
    appoint = CabinetDecision(
        orders=(CabinetOrder(post=CabinetPost.CHIEF_OF_STAFF, character_id=candidate.character_id),)
    )
    investment = _invest_everywhere(state, 50)
    preview = preview_decisions(state, _set(state, appoint, investment))
    assert all(row.chief_of_staff_bonus_bps == 0 for row in preview.investment_effects)
    resolved = _resolved_components(_resolve(state, appoint, investment))
    for row in preview.investment_effects:
        assert row.gain_bps == resolved[(row.party_id, row.bloc_id)]


def test_an_investment_that_would_change_nothing_is_flagged_and_refused() -> None:
    state = _load("decree_state")
    legislature = _politics(state).legislature
    assert legislature is not None
    parties = tuple(
        party.model_copy(
            update={
                "blocs": tuple(
                    bloc.model_copy(update={"government_relationship_bps": 10_000})
                    for bloc in party.blocs
                )
            }
        )
        for party in legislature.parties
    )
    state = _set_politics(state, legislature=legislature.model_copy(update={"parties": parties}))
    decision = _invest_everywhere(state, 50)
    preview = preview_decisions(state, _set(state, decision))
    assert preview.investment_effects
    assert all(row.no_effect and row.gain_bps == 0 for row in preview.investment_effects)
    with pytest.raises(TurnResolutionError, match="would have no effect"):
        _resolve(state, decision)


def test_every_cabinet_post_has_an_explanation_built_from_its_engine_maximum() -> None:
    assert set(POST_EFFECT_TEXT) == set(CabinetPost)
    assert (
        format_bps_percent(CHIEF_OF_STAFF_MAX_BONUS_BPS)
        in POST_EFFECT_TEXT[CabinetPost.CHIEF_OF_STAFF]
    )
    whole, frac = divmod(FOREIGN_MINISTER_ASSISTANCE_SHARE_MAX_BPS, 100)
    assert f"{whole}.{frac:02d} percentage points" in POST_EFFECT_TEXT[CabinetPost.FOREIGN_MINISTER]


@pytest.mark.parametrize("competence", [0, 3200, 8600, 10_000])
def test_candidate_effects_are_the_engine_functions(competence: int) -> None:
    # Chief of staff: the bonus the engine adds to a gain of exactly 10,000 bps.
    assert post_effect_for_competence(CabinetPost.CHIEF_OF_STAFF, competence) == (
        chief_of_staff_gain_bonus_bps(base_gain_bps=10_000, competence_bps=competence)
    )
    # ...and that is the share a real investment's gain grows by, within integer truncation.
    base = relationship_gain_bps(opening_relationship_bps=-8_000, political_capital=200)
    with_chief = relationship_gain_bps(
        opening_relationship_bps=-8_000,
        political_capital=200,
        chief_of_staff_competence_bps=competence,
    )
    stated = post_effect_for_competence(CabinetPost.CHIEF_OF_STAFF, competence)
    assert abs((with_chief - base) * 10_000 - base * stated) <= 10_000
    # Foreign minister: the difference the engine's share function makes. Never more than stated,
    # and exactly the stated amount wherever the engine's 1-bps floor does not clip the share.
    stated_fm = post_effect_for_competence(CabinetPost.FOREIGN_MINISTER, competence)
    for trust, standing, independence in [
        (0, 0, 0),
        (5_000, 2_000, 3_000),
        (-2_000, -3_000, 9_000),
    ]:
        terms = {
            "personal_trust_bps": trust,
            "standing_bps": standing,
            "independence_bps": independence,
        }
        with_minister = assistance_share_bps(foreign_minister_competence_bps=competence, **terms)
        without = assistance_share_bps(foreign_minister_competence_bps=0, **terms)
        assert 0 <= with_minister - without <= stated_fm
        if without > 1:
            assert with_minister - without == stated_fm
    assert candidate_effect_text(CabinetPost.CHIEF_OF_STAFF, competence).startswith(
        f"With competence {format_bps_percent(competence)}: investments would gain about "
    )
    # The foreign minister's sentence is an upper bound, because of that floor: it must say so.
    whole, frac = divmod(stated_fm, 100)
    assert candidate_effect_text(CabinetPost.FOREIGN_MINISTER, competence) == (
        f"With competence {format_bps_percent(competence)}: a counterpart would grant up to "
        f"{whole}.{frac:02d} percentage points more of its remaining pool."
    )


def test_options_carry_the_explanations() -> None:
    options = build_decision_options(_load("tiny_valid"))
    for post in options.cabinet_posts:
        assert post.post_effect_text == POST_EFFECT_TEXT[CabinetPost(post.post)]
        for candidate in post.candidates:
            assert candidate.effect_text == candidate_effect_text(
                CabinetPost(post.post), candidate.competence_bps
            )


def test_a_future_start_appointment_is_rejected_by_the_engine() -> None:
    """Why the preview may read the opening chief of staff at `state.turn` (W-2 record, mutation
    M3): no valid state holds an appointment that starts after the state's own turn, so reading it
    at `state.turn + 1` selects the same holder on every valid state. This proves that rejection
    directly, on a real scenario, rather than leaving it to the engine's source."""
    state = _load("tiny_valid")
    assert check_invariants(state) == []
    player = state.world.countries[state.world.player_country_id]
    assert player.cabinet is not None
    chief = player.cabinet.offices[CabinetPost.CHIEF_OF_STAFF]
    assert chief.effective_from_turn <= state.turn, "the opening chief already serves"
    future = chief.model_copy(update={"effective_from_turn": state.turn + 1})
    player.cabinet = player.cabinet.model_copy(
        update={"offices": {**player.cabinet.offices, CabinetPost.CHIEF_OF_STAFF: future}}
    )
    assert [v.code for v in check_invariants(state)] == ["cabinet_appointment_not_yet_effective"]
