"""Named people, the cabinet they sit in, and the one thing an office is worth today.

This is the first named-actor layer in the engine: until now the player governed offices and
institutions, and every removal reason described a post, never a person. Four claims are worth
proving about the layer, and they are what this file is organised around.

* **A character is five distinct facts about a person, not one number wearing five hats.** The
  bounds are shared, the meanings are not, and the shipped rosters are authored so that no
  correlation between them can be inferred from the content -- in particular `loyalty` is nowhere
  `BPS_DENOMINATOR - competence`, and a genuinely competent AND loyal professional exists.
* **An office pays only while somebody is actually doing the job.** Vacancy, an unmodelled cabinet
  and an appointment that has not taken effect yet all contribute exactly nothing, and a state with
  no cabinet at all computes precisely the numbers it computed before this layer existed.
* **The chief of staff's competence changes an outcome that is visible in the report.** Not a
  displayed score: the same 100 capital buys a strictly larger relationship improvement, and the
  difference survives a save/replay.
* **A forged competence is caught.** The report row re-derives its own arithmetic, so a competence
  raised alone fails the row; a competence raised together with the gain it would buy leaves the row
  self-consistent, and only reconciliation's comparison against the opening cabinet (group 56)
  catches that.

The recruitment, bargaining and promise consumers of the other four traits are the later commits of
this slice; what is proven here is the shape they are authored in and the one consumer that exists.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.cli import main
from app.content.scenarios import load_scenario_file
from app.core.errors import TurnResolutionError
from app.core.politics import BPS_DENOMINATOR
from app.simulation.cabinet import effective_holder_id, holder_competence_bps
from app.simulation.constitution import DecreeAuthority, Legislature
from app.simulation.decisions import (
    BlocInvestment,
    BlocRelationshipInvestmentDecision,
    CabinetDecision,
    CabinetOrder,
    DecisionSet,
)
from app.simulation.history import advance_game, new_game, validate_history
from app.simulation.invariants import check_invariants
from app.simulation.reconciliation import reconcile_political_legislative_and_survival_report
from app.simulation.relationships import (
    CHIEF_OF_STAFF_MAX_BONUS_BPS,
    RELATIONSHIP_CEILING_BPS,
    RELATIONSHIP_HALF_GAP_CAPITAL,
    RELATIONSHIP_INVESTMENT_CAP,
    chief_of_staff_gain_bonus_bps,
    relationship_gain_bps,
)
from app.simulation.report import BlocRelationshipMemoryReport
from app.simulation.resolver import resolve_turn
from app.simulation.save_format import SAVE_FORMAT_VERSION
from app.simulation.state import (
    CabinetAppointment,
    CabinetPost,
    CabinetState,
    CharacterState,
    ForeignProfileRef,
    ForeignProfileState,
    GameState,
    PlayerCountryRef,
)
from tests.conftest import SCENARIO_DIR, make_country, make_game_state, make_politics

_SCENARIOS = ("tiny_valid.yaml", "decree_state.yaml", "deficit_demo.yaml")

# `tiny_valid`'s cheapest real bargaining target, and the pair every end-to-end test below invests
# in. Its chief of staff (`hal_verrin`) is deliberately the weak administrator: a small bonus that
# still has to show up is a harder test than a large one.
_TINY_TARGET = ("national_front", "conservatives")

#: One real foreign profile, so a character affiliated with it resolves. Tests that provoke a
#: PARTY or CABINET violation use it, leaving the affiliation itself beyond reproach.
_ONE_FOREIGN_PROFILE = {
    "kessia": ForeignProfileState(display_name="Kessia", war_capability_bps=5_000)
}


def _trait_kwargs(**overrides: int) -> dict[str, int]:
    base = {
        "competence": 5_000,
        "loyalty": 5_000,
        "independence": 5_000,
        "ambition": 5_000,
        "personal_trust": 5_000,
    }
    base.update(overrides)
    return base


def _character(**overrides: object) -> CharacterState:
    fields: dict[str, object] = {
        "display_name": "Somebody",
        "affiliation": PlayerCountryRef(kind="player_country", country_id="testland"),
        **_trait_kwargs(),
    }
    fields.update(overrides)
    return CharacterState(**fields)  # type: ignore[arg-type]


def _load(scenario_file: str) -> GameState:
    return load_scenario_file(SCENARIO_DIR / scenario_file)


def _invest(
    state: GameState,
    capital: int,
    target: tuple[str, str],
    *also: CabinetDecision,
) -> DecisionSet:
    """An investment, optionally alongside a cabinet decision, in canonical kind order.

    `"bloc_relationship_investment"` sorts before `"cabinet"`, and `DecisionSet` REJECTS a
    noncanonical tuple rather than sorting it, so the order here is part of building a legal set.
    """
    party_id, bloc_id = target
    investment = BlocRelationshipInvestmentDecision(
        investments=(BlocInvestment(party_id=party_id, bloc_id=bloc_id, political_capital=capital),)
    )
    return DecisionSet(
        expected_turn=state.turn,
        expected_state_version=state.state_version,
        decisions=sorted([investment, *also], key=lambda decision: decision.kind),
    )


def _with_cabinet(state: GameState, cabinet: CabinetState) -> GameState:
    """`state` with the player's cabinet replaced. Goes through real `model_copy`s, so the result
    is a state the engine accepts structurally -- the point is to change who is SERVING, not to
    build something malformed."""
    player = state.world.countries[state.world.player_country_id]
    countries = dict(state.world.countries)
    countries[player.id] = player.model_copy(update={"cabinet": cabinet})
    return state.model_copy(
        update={"world": state.world.model_copy(update={"countries": countries})}
    )


def _memory_row(report, target: tuple[str, str]) -> BlocRelationshipMemoryReport:  # type: ignore[no-untyped-def]
    assert report.political_relationship is not None
    party_id, bloc_id = target
    (row,) = [
        candidate
        for candidate in report.political_relationship.blocs
        if (candidate.party_id, candidate.bloc_id) == (party_id, bloc_id)
    ]
    return row


# --- the model: five facts, five bounded values, and a vacancy that is not an absence -----------


def test_only_the_two_posts_that_do_something_are_declared() -> None:
    """A post whose holder changes nothing is a promise the engine does not keep, so there are two
    -- and their declaration order is their alphabetical value order, which is what lets any
    collection keyed by post sort with no second convention."""
    assert [post.value for post in CabinetPost] == ["chief_of_staff", "foreign_minister"]
    assert [post.value for post in CabinetPost] == sorted(post.value for post in CabinetPost)


@pytest.mark.parametrize(
    "trait", ("competence", "loyalty", "independence", "ambition", "personal_trust")
)
def test_every_trait_is_a_strict_bounded_integer(trait: str) -> None:
    """All five share one alias and therefore one band, `0..BPS_DENOMINATOR` inclusive. Strict, so
    a float or a numeric string is a rejection rather than a coercion -- the whole engine's
    no-floating-point discipline starts at the schema."""
    assert _character(**{trait: 0}) is not None
    assert _character(**{trait: BPS_DENOMINATOR}) is not None
    for rejected in (-1, BPS_DENOMINATOR + 1, 5_000.0, "5000"):
        with pytest.raises(ValidationError):
            _character(**{trait: rejected})


def test_a_character_rejects_a_field_nobody_declared() -> None:
    with pytest.raises(ValidationError):
        _character(charisma=9_000)


def test_a_cabinet_with_both_posts_vacant_is_a_real_cabinet() -> None:
    """`offices={}` is a government that has both jobs and has filled neither -- deliberately a
    different state from `CountryState.cabinet is None`, which is a country that models no cabinet
    at all."""
    cabinet = CabinetState()
    assert cabinet.offices == {}
    assert CabinetState(offices={}) == cabinet


def test_an_appointment_cannot_take_effect_before_the_campaign_starts() -> None:
    assert CabinetAppointment(character_id="somebody", effective_from_turn=0) is not None
    with pytest.raises(ValidationError):
        CabinetAppointment(character_id="somebody", effective_from_turn=-1)
    with pytest.raises(ValidationError):
        CabinetAppointment(character_id="", effective_from_turn=0)


# --- simulation.cabinet: one timing rule, in one place ------------------------------------------


def test_an_unmodelled_cabinet_a_vacant_post_and_a_future_holder_all_mean_nobody() -> None:
    """Three genuinely different situations, one answer, because a bonus of nothing is a bonus of
    nothing. Anything needing the difference reads the cabinet directly."""
    future = CabinetState(
        offices={
            CabinetPost.CHIEF_OF_STAFF: CabinetAppointment(
                character_id="hired_today", effective_from_turn=6
            )
        }
    )
    for cabinet in (None, CabinetState(offices={}), future):
        assert (
            effective_holder_id(cabinet=cabinet, post=CabinetPost.CHIEF_OF_STAFF, resolving_turn=5)
            is None
        )


def test_a_holder_serves_from_their_effective_turn_onward_and_not_before() -> None:
    cabinet = CabinetState(
        offices={
            CabinetPost.CHIEF_OF_STAFF: CabinetAppointment(
                character_id="hired_on_turn_5", effective_from_turn=6
            )
        }
    )
    serving = [
        turn
        for turn in range(10)
        if effective_holder_id(
            cabinet=cabinet, post=CabinetPost.CHIEF_OF_STAFF, resolving_turn=turn
        )
        is not None
    ]
    assert serving == [6, 7, 8, 9]


def test_one_post_says_nothing_about_the_other() -> None:
    cabinet = CabinetState(
        offices={
            CabinetPost.FOREIGN_MINISTER: CabinetAppointment(
                character_id="diplomat", effective_from_turn=0
            )
        }
    )
    assert (
        effective_holder_id(cabinet=cabinet, post=CabinetPost.FOREIGN_MINISTER, resolving_turn=0)
        == "diplomat"
    )
    assert (
        effective_holder_id(cabinet=cabinet, post=CabinetPost.CHIEF_OF_STAFF, resolving_turn=0)
        is None
    )


def test_competence_is_zero_for_a_vacancy_and_for_a_holder_who_is_not_in_the_registry() -> None:
    """The unknown-holder branch is unreachable in a valid game (`cabinet_holder_unknown` rejects
    that state before and after every resolution) and is guarded anyway, because reconciliation
    reads a save that may be tampered and must return a problem string rather than raise."""
    cabinet = CabinetState(
        offices={
            CabinetPost.CHIEF_OF_STAFF: CabinetAppointment(
                character_id="ghost", effective_from_turn=0
            )
        }
    )
    assert (
        holder_competence_bps(
            cabinet=cabinet,
            characters={},
            post=CabinetPost.CHIEF_OF_STAFF,
            resolving_turn=0,
        )
        == 0
    )
    assert (
        holder_competence_bps(
            cabinet=CabinetState(offices={}),
            characters={"ghost": _character(competence=9_000)},
            post=CabinetPost.CHIEF_OF_STAFF,
            resolving_turn=0,
        )
        == 0
    )
    assert (
        holder_competence_bps(
            cabinet=cabinet,
            characters={"ghost": _character(competence=9_000)},
            post=CabinetPost.CHIEF_OF_STAFF,
            resolving_turn=0,
        )
        == 9_000
    )


# --- the bonus: additive, bounded, and never a rescue --------------------------------------------


@pytest.mark.parametrize("opening_relationship_bps", (-10_000, -2_500, 0, 2_500, 9_000))
@pytest.mark.parametrize("political_capital", (1, 17, 100, RELATIONSHIP_INVESTMENT_CAP))
def test_a_vacant_post_reproduces_the_pre_cabinet_gain_exactly(
    opening_relationship_bps: int, political_capital: int
) -> None:
    """The default argument is what keeps every existing caller, test and pinned calibration table
    meaning exactly what it meant: no chief of staff, no difference."""
    gap = RELATIONSHIP_CEILING_BPS - opening_relationship_bps
    before_this_layer = (gap * political_capital) // (
        RELATIONSHIP_HALF_GAP_CAPITAL + political_capital
    )
    assert (
        relationship_gain_bps(
            opening_relationship_bps=opening_relationship_bps,
            political_capital=political_capital,
        )
        == before_this_layer
    )
    assert (
        relationship_gain_bps(
            opening_relationship_bps=opening_relationship_bps,
            political_capital=political_capital,
            chief_of_staff_competence_bps=0,
        )
        == before_this_layer
    )


def test_the_bonus_is_a_quarter_of_the_base_gain_at_maximum_competence_and_scales_down() -> None:
    assert chief_of_staff_gain_bonus_bps(base_gain_bps=1_000, competence_bps=BPS_DENOMINATOR) == (
        1_000 * CHIEF_OF_STAFF_MAX_BONUS_BPS // BPS_DENOMINATOR
    )
    assert chief_of_staff_gain_bonus_bps(base_gain_bps=1_000, competence_bps=BPS_DENOMINATOR) == 250
    assert chief_of_staff_gain_bonus_bps(base_gain_bps=1_000, competence_bps=5_000) == 125
    assert chief_of_staff_gain_bonus_bps(base_gain_bps=1_000, competence_bps=0) == 0


def test_the_bonus_never_decreases_as_competence_rises() -> None:
    """Monotone in competence at a fixed base, which is the only ordering claim the office makes:
    a more competent chief of staff is never worse than a less competent one."""
    bonuses = [
        chief_of_staff_gain_bonus_bps(base_gain_bps=2_833, competence_bps=competence)
        for competence in range(0, BPS_DENOMINATOR + 1, 137)
    ]
    assert bonuses == sorted(bonuses)
    assert bonuses[0] == 0 and bonuses[-1] > bonuses[0]


def test_hiring_a_chief_of_staff_never_makes_a_rejected_investment_legal() -> None:
    """Slot 1 rejects an investment whose computed gain is `0`. A bonus is a fraction of the base
    gain, so a quarter of nothing is nothing -- the rejection cannot be bought around."""
    at_the_ceiling = relationship_gain_bps(
        opening_relationship_bps=RELATIONSHIP_CEILING_BPS,
        political_capital=RELATIONSHIP_INVESTMENT_CAP,
        chief_of_staff_competence_bps=BPS_DENOMINATOR,
    )
    assert at_the_ceiling == 0
    truncated_away = relationship_gain_bps(
        opening_relationship_bps=RELATIONSHIP_CEILING_BPS - 100,
        political_capital=1,
        chief_of_staff_competence_bps=BPS_DENOMINATOR,
    )
    assert truncated_away == 0


@pytest.mark.parametrize("opening_relationship_bps", (-10_000, -5_000, 0, 5_000, 9_999))
def test_the_closing_relationship_stays_strictly_below_the_ceiling_at_full_competence(
    opening_relationship_bps: int,
) -> None:
    """The module's standing guarantee, re-proven with the office in play. It holds because the
    bonus is a further fraction of the same gap rather than a multiplier on the result: the largest
    possible total is `1.25 * gap * 200 / 700`, comfortably under `gap`."""
    for political_capital in (1, 50, 100, RELATIONSHIP_INVESTMENT_CAP):
        gain = relationship_gain_bps(
            opening_relationship_bps=opening_relationship_bps,
            political_capital=political_capital,
            chief_of_staff_competence_bps=BPS_DENOMINATOR,
        )
        assert opening_relationship_bps + gain < RELATIONSHIP_CEILING_BPS


# --- invariants: every code reachable from a real state ------------------------------------------


def _codes(state: GameState) -> list[str]:
    """Every violation code, in emitted order. A LIST, not a set, so a test can assert that a
    constructed state raises exactly one problem and therefore that the code it names is the one
    being provoked rather than one of several."""
    return [violation.code for violation in check_invariants(state)]


def test_the_player_must_have_a_cabinet_even_when_it_is_empty() -> None:
    state = make_game_state(
        countries={"testland": make_country("testland", with_cabinet=False)},
        player_country_id="testland",
    )
    assert _codes(state) == ["player_cabinet_required"]
    assert _codes(make_game_state()) == []


def test_a_character_affiliated_with_nobody_is_rejected() -> None:
    state = make_game_state(
        characters={
            "drifter": _character(
                affiliation=PlayerCountryRef(kind="player_country", country_id="atlantis")
            )
        }
    )
    assert _codes(state) == ["character_affiliation_unresolved"]


def test_a_foreign_leader_may_not_claim_a_domestic_party() -> None:
    """A foreign profile's leader represents an abstract actor and sits in no domestic
    legislature. The profile is REAL here, so the affiliation resolves and this is the only
    violation raised -- the party claim is what is being rejected, not a dangling reference."""
    state = make_game_state(
        characters={
            "meddler": _character(
                affiliation=ForeignProfileRef(kind="foreign_profile", foreign_profile_id="kessia"),
                party_id="alpha",
            )
        },
        foreign_profiles=_ONE_FOREIGN_PROFILE,
    )
    assert _codes(state) == ["character_party_on_foreign_affiliation"]


def test_a_party_leader_must_lead_a_party_that_exists() -> None:
    state = make_game_state(
        characters={"pretender": _character(party_id="party_of_one")},
    )
    assert _codes(state) == ["character_party_unknown"]


def test_a_party_leader_outlives_the_abolition_of_the_legislature() -> None:
    """Abolishing the legislature is a legal constitutional amendment. If a leader's `party_id`
    became a violation the moment the chamber was dissolved, a legal player action would turn a
    valid state invalid -- so an unverifiable party claim is deliberately not a false one."""
    without_legislature = make_politics(
        legislature=Legislature.NONE, decree_authority=DecreeAuthority.UNLIMITED
    )
    state = make_game_state(
        countries={"testland": make_country("testland", politics=without_legislature)},
        player_country_id="testland",
        characters={"deposed": _character(party_id="a_party_that_no_longer_meets")},
    )
    assert state.world.countries["testland"].politics is not None
    assert state.world.countries["testland"].politics.legislature is None
    assert check_invariants(state) == []


def test_a_post_cannot_be_held_by_somebody_who_does_not_exist() -> None:
    cabinet = CabinetState(
        offices={
            CabinetPost.CHIEF_OF_STAFF: CabinetAppointment(
                character_id="ghost", effective_from_turn=0
            )
        }
    )
    state = make_game_state(
        countries={"testland": make_country("testland", cabinet=cabinet)},
        player_country_id="testland",
    )
    assert _codes(state) == ["cabinet_holder_unknown"]


def test_a_government_may_only_appoint_its_own_people() -> None:
    cabinet = CabinetState(
        offices={
            CabinetPost.FOREIGN_MINISTER: CabinetAppointment(
                character_id="outsider", effective_from_turn=0
            )
        }
    )
    state = make_game_state(
        countries={"testland": make_country("testland", cabinet=cabinet)},
        player_country_id="testland",
        characters={
            "outsider": _character(
                affiliation=ForeignProfileRef(kind="foreign_profile", foreign_profile_id="kessia")
            )
        },
        foreign_profiles=_ONE_FOREIGN_PROFILE,
    )
    assert _codes(state) == ["cabinet_holder_not_of_this_country"]


def test_one_person_holds_at_most_one_post() -> None:
    cabinet = CabinetState(
        offices={
            CabinetPost.CHIEF_OF_STAFF: CabinetAppointment(
                character_id="polymath", effective_from_turn=0
            ),
            CabinetPost.FOREIGN_MINISTER: CabinetAppointment(
                character_id="polymath", effective_from_turn=0
            ),
        }
    )
    state = make_game_state(
        countries={"testland": make_country("testland", cabinet=cabinet)},
        player_country_id="testland",
        characters={"polymath": _character()},
    )
    assert _codes(state) == ["cabinet_holder_holds_two_posts"]


def test_a_seated_cabinet_over_a_real_roster_is_clean() -> None:
    """The anti-vacuity half of the seven checks above: the same shapes, correctly authored, must
    produce no violation at all."""
    cabinet = CabinetState(
        offices={
            CabinetPost.CHIEF_OF_STAFF: CabinetAppointment(
                character_id="aide", effective_from_turn=0
            ),
            CabinetPost.FOREIGN_MINISTER: CabinetAppointment(
                character_id="envoy", effective_from_turn=0
            ),
        }
    )
    state = make_game_state(
        countries={"testland": make_country("testland", cabinet=cabinet)},
        player_country_id="testland",
        characters={"aide": _character(), "envoy": _character()},
    )
    assert check_invariants(state) == []


# --- content: three rosters, three cabinets, and no hidden single number -------------------------


@pytest.mark.parametrize("scenario_file", _SCENARIOS)
def test_every_scenario_authors_a_player_cabinet_and_a_roster_that_validates(
    scenario_file: str,
) -> None:
    state = _load(scenario_file)
    assert check_invariants(state) == []
    player = state.world.countries[state.world.player_country_id]
    assert player.cabinet is not None
    assert len(state.world.characters) >= 4
    for character_id, character in state.world.characters.items():
        assert character.display_name.strip(), character_id


@pytest.mark.parametrize("scenario_file", _SCENARIOS)
def test_no_shipped_character_is_one_number_wearing_five_hats(scenario_file: str) -> None:
    """The correlation the mandate forbids, checked against the content rather than the code: if
    `loyalty` were `BPS_DENOMINATOR - competence` anywhere, a player could read one trait off the
    other and the hiring tradeoff would collapse into a ranking."""
    characters = _load(scenario_file).world.characters
    for character_id, character in characters.items():
        assert character.loyalty != BPS_DENOMINATOR - character.competence, character_id
        traits = (
            character.competence,
            character.loyalty,
            character.independence,
            character.ambition,
            character.personal_trust,
        )
        assert len(set(traits)) >= 3, character_id


@pytest.mark.parametrize("scenario_file", _SCENARIOS)
def test_every_scenario_offers_all_four_hiring_archetypes(scenario_file: str) -> None:
    """A choice, not a ranking. The professional is the one that matters most: without somebody
    who is both capable and loyal, "competence costs loyalty" would be a law of the world rather
    than a tendency the player can beat by looking harder."""
    candidates = [
        character
        for character in _load(scenario_file).world.characters.values()
        if character.party_id is None and isinstance(character.affiliation, PlayerCountryRef)
    ]
    assert any(c.competence <= 4_000 and c.loyalty >= 8_000 for c in candidates), "loyal weak"
    assert any(
        c.competence >= 8_000 and c.independence >= 8_000 and c.loyalty <= 4_000 for c in candidates
    ), "independent expert"
    assert any(c.competence >= 8_000 and c.ambition >= 8_000 for c in candidates), "ambitious"
    assert any(c.competence >= 7_000 and c.loyalty >= 7_000 for c in candidates), "professional"


def test_the_three_scenarios_ship_three_different_cabinet_occupancies() -> None:
    """Both posts filled, one filled, none filled -- so every branch of the effectivity and bonus
    logic is exercised by real content and not only by constructed states."""
    occupancy = {}
    for scenario_file in _SCENARIOS:
        state = _load(scenario_file)
        cabinet = state.world.countries[state.world.player_country_id].cabinet
        assert cabinet is not None
        occupancy[scenario_file] = len(cabinet.offices)
    assert sorted(occupancy.values()) == [0, 1, 2], occupancy


# --- the office pays, visibly, and only to whoever is actually serving ---------------------------


def _resolve_investment(state: GameState, capital: int = 100):  # type: ignore[no-untyped-def]
    return resolve_turn(state, _invest(state, capital, _TINY_TARGET))


def test_a_serving_chief_of_staff_buys_a_strictly_larger_relationship_gain() -> None:
    """The whole point of the office, measured: identical state, identical decision, identical
    capital -- one has `hal_verrin` (competence 3,200) in post and one does not."""
    state = _load("tiny_valid.yaml")
    with_holder = _memory_row(_resolve_investment(state).report, _TINY_TARGET)
    without = _memory_row(
        _resolve_investment(_with_cabinet(state, CabinetState(offices={}))).report, _TINY_TARGET
    )

    assert with_holder.chief_of_staff_competence_bps == 3_200
    assert without.chief_of_staff_competence_bps == 0
    assert with_holder.investment_capital == without.investment_capital == 100
    assert with_holder.opening_relationship_bps == without.opening_relationship_bps
    assert with_holder.investment_component_bps > without.investment_component_bps
    assert with_holder.closing_relationship_bps > without.closing_relationship_bps
    assert with_holder.investment_component_bps == without.investment_component_bps + (
        without.investment_component_bps
        * 3_200
        * CHIEF_OF_STAFF_MAX_BONUS_BPS
        // BPS_DENOMINATOR
        // BPS_DENOMINATOR
    )


def test_an_appointment_made_this_turn_does_not_pay_for_the_turn_that_made_it() -> None:
    """The effectivity rule, proved through the REAL decision path.

    Until appointments existed this was asserted against a hand-built state carrying
    `effective_from_turn > state.turn` -- a state `cabinet_appointment_not_yet_effective` now
    forbids outright, precisely because no resolution can produce one. The property is unchanged
    and the proof is strictly stronger: submit a real appointment, and this turn's relationship
    investment is still scored against the OPENING holder.
    """
    state = _load("tiny_valid.yaml")
    hire = CabinetDecision(
        orders=(
            CabinetOrder(post=CabinetPost.CHIEF_OF_STAFF, character_id="ilse_marovec"),
            # Ilse holds the foreign ministry, so the transfer must vacate it in the same
            # decision; otherwise she would end up seated twice. Vacating it by DISMISSAL keeps
            # this turn to one paid appointment (276) plus the 100 investment, inside the
            # scenario's 500 opening capital.
            CabinetOrder(post=CabinetPost.FOREIGN_MINISTER),
        )
    )
    resolution = resolve_turn(state, _invest(state, 100, _TINY_TARGET, hire))
    row = _memory_row(resolution.report, _TINY_TARGET)

    # `hal_verrin`, the OPENING chief of staff, not `ilse_marovec` (8,600) who was hired today.
    assert row.chief_of_staff_competence_bps == 3_200
    assert (
        row.investment_component_bps
        == _memory_row(_resolve_investment(state).report, _TINY_TARGET).investment_component_bps
    )

    seated = resolution.state.world.countries["arken"].cabinet
    assert seated is not None
    assert seated.offices[CabinetPost.CHIEF_OF_STAFF].character_id == "ilse_marovec"
    assert seated.offices[CabinetPost.CHIEF_OF_STAFF].effective_from_turn == resolution.state.turn


def test_a_replacement_does_not_erase_the_outgoing_holders_turn() -> None:
    """The regression test for the defect this commit fixes.

    Slot 2 commits the closing cabinet mid-resolution, so a slot 11 that read `ctx.state` would see
    the outgoing holder GONE -- not "not yet effective", which is what an appointment into a
    vacancy looks like, but absent -- and would score this turn's investment at competence 0. The
    outgoing holder served the whole turn; the incoming one has not started. Both a replacement and
    a dismissal must therefore leave this turn's figures exactly as a quiet turn would.
    """
    state = _load("tiny_valid.yaml")
    quiet = _memory_row(_resolve_investment(state).report, _TINY_TARGET)
    replaced = _memory_row(
        resolve_turn(
            state,
            _invest(
                state,
                100,
                _TINY_TARGET,
                CabinetDecision(
                    orders=(
                        CabinetOrder(post=CabinetPost.CHIEF_OF_STAFF, character_id="wren_hollis"),
                    )
                ),
            ),
        ).report,
        _TINY_TARGET,
    )
    dismissed = _memory_row(
        resolve_turn(
            state,
            _invest(
                state,
                100,
                _TINY_TARGET,
                CabinetDecision(orders=(CabinetOrder(post=CabinetPost.CHIEF_OF_STAFF),)),
            ),
        ).report,
        _TINY_TARGET,
    )
    for name, row in (("replaced", replaced), ("dismissed", dismissed)):
        assert row.chief_of_staff_competence_bps == 3_200, name
        assert row.investment_component_bps == quiet.investment_component_bps, name


def test_a_better_chief_of_staff_is_worth_more_than_a_worse_one() -> None:
    """Competence is read as a quantity, not as a flag: `tiny_valid`'s four candidates produce four
    non-decreasing gains, strictly increasing wherever their competences differ enough to survive
    truncation."""
    state = _load("tiny_valid.yaml")
    by_competence = sorted(
        (character.competence, character_id)
        for character_id, character in state.world.characters.items()
        if character.party_id is None and isinstance(character.affiliation, PlayerCountryRef)
    )
    gains = []
    for _competence, character_id in by_competence:
        seated = CabinetState(
            offices={
                CabinetPost.CHIEF_OF_STAFF: CabinetAppointment(
                    character_id=character_id, effective_from_turn=0
                )
            }
        )
        gains.append(
            _memory_row(
                _resolve_investment(_with_cabinet(state, seated)).report, _TINY_TARGET
            ).investment_component_bps
        )
    assert gains == sorted(gains)
    assert gains[0] < gains[-1]


def test_the_foreign_minister_does_not_touch_relationship_investment() -> None:
    """One office, one consumer. `tiny_valid` seats its most competent candidate as foreign
    minister; SACKING her changes nothing about a domestic bargain -- if it did, the two posts
    would be one post."""
    state = _load("tiny_valid.yaml")
    player = state.world.countries[state.world.player_country_id]
    assert player.cabinet is not None
    assert CabinetPost.FOREIGN_MINISTER in player.cabinet.offices, "there is somebody to sack"
    without_minister = CabinetState(
        offices={
            post: appointment
            for post, appointment in player.cabinet.offices.items()
            if post is not CabinetPost.FOREIGN_MINISTER
        }
    )
    seated = _memory_row(_resolve_investment(state).report, _TINY_TARGET)
    sacked = _memory_row(
        _resolve_investment(_with_cabinet(state, without_minister)).report, _TINY_TARGET
    )
    assert sacked.investment_component_bps == seated.investment_component_bps
    assert sacked.chief_of_staff_competence_bps == seated.chief_of_staff_competence_bps


# --- a forged competence is caught twice, for two different reasons ------------------------------


def test_the_row_rejects_a_competence_its_own_arithmetic_does_not_support() -> None:
    """The row re-derives the gain formula from its OWN stored fields, so raising the competence
    alone no longer explains the investment component it carries."""
    row = _memory_row(_resolve_investment(_load("tiny_valid.yaml")).report, _TINY_TARGET)
    forged = {**row.model_dump(), "chief_of_staff_competence_bps": 0}
    with pytest.raises(ValidationError):
        BlocRelationshipMemoryReport.model_validate(forged)
    assert BlocRelationshipMemoryReport.model_validate(row.model_dump()) == row


def test_reconciliation_rejects_a_competence_the_opening_cabinet_never_had() -> None:
    """Group 56. A competence raised TOGETHER with the gain it would buy leaves the row perfectly
    self-consistent and buys a larger relationship out of nothing; only a comparison against the
    opening state catches it, which is why the check exists at all."""
    state = _load("tiny_valid.yaml")
    resolution = _resolve_investment(state)
    assert (
        reconcile_political_legislative_and_survival_report(
            opening_state=state,
            closing_state=resolution.state,
            report=resolution.report,
            decisions=None,
        )
        == []
    )

    assert resolution.report.political_relationship is not None
    rows = tuple(
        row.model_copy(
            update={"chief_of_staff_competence_bps": row.chief_of_staff_competence_bps + 1}
        )
        for row in resolution.report.political_relationship.blocs
    )
    forged_report = resolution.report.model_copy(
        update={
            "political_relationship": resolution.report.political_relationship.model_copy(
                update={"blocs": rows}
            )
        }
    )
    problems = reconcile_political_legislative_and_survival_report(
        opening_state=state,
        closing_state=resolution.state,
        report=forged_report,
        decisions=None,
    )
    assert any("group 56" in problem for problem in problems)


def test_reconciliation_scores_a_row_against_the_opening_cabinet_and_not_the_closing_one() -> None:
    """The same reason group 14 pins the vote's relationship to the opening value: a row scored
    against a mid-turn cabinet would be scored against somebody who was not yet doing the job."""
    state = _with_cabinet(_load("tiny_valid.yaml"), CabinetState(offices={}))
    resolution = _resolve_investment(state)
    seated_afterwards = _with_cabinet(
        resolution.state,
        CabinetState(
            offices={
                CabinetPost.CHIEF_OF_STAFF: CabinetAppointment(
                    character_id="ilse_marovec", effective_from_turn=resolution.state.turn
                )
            }
        ),
    )
    problems = reconcile_political_legislative_and_survival_report(
        opening_state=state,
        closing_state=seated_afterwards,
        report=resolution.report,
        decisions=None,
    )
    # Group 56 is satisfied -- the relationship rows were scored against the OPENING cabinet, which
    # is what this test is about, and a cabinet seated afterwards does not retroactively change
    # them. Group 57 legitimately objects, because the governance subtree really does disagree with
    # this hand-built closing state; that is a different claim and is proved on its own elsewhere.
    assert not [problem for problem in problems if "group 56" in problem]
    assert all("group 57" in problem for problem in problems)


# --- and it all survives being written down and read back ----------------------------------------


def test_a_campaign_with_a_serving_cabinet_replays_and_validates() -> None:
    """`validate_history` re-runs reconciliation over every stored entry, so a chief of staff whose
    contribution did not survive serialization would surface here as a group 56 problem rather than
    as a silently different number."""
    save = new_game(_load("tiny_valid.yaml"), save_format_version=SAVE_FORMAT_VERSION)
    for _ in range(3):
        state = save.entries[-1].state()
        save = advance_game(save, _invest(state, 100, _TINY_TARGET))
    assert validate_history(save) == []

    genesis = save.entries[0].state()
    assert genesis.world.characters["hal_verrin"].competence == 3_200
    latest_report = save.entries[-1].report()
    assert latest_report is not None
    assert _memory_row(latest_report, _TINY_TARGET).chief_of_staff_competence_bps == 3_200


# --- and the player can actually see it ----------------------------------------------------------


def _inspect_cabinet(tmp_path, capsys, scenario_file: str, *flags: str) -> str:  # type: ignore[no-untyped-def]
    save = tmp_path / "save0.json"
    assert main(["new", "--scenario", str(SCENARIO_DIR / scenario_file), "--out", str(save)]) == 0
    capsys.readouterr()
    assert main(["inspect", "--state", str(save), *flags]) == 0
    return capsys.readouterr().out


def test_inspect_cabinet_names_the_holder_and_shows_what_the_post_is_worth(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An office whose holder the player cannot see would be exactly the decorative score this
    layer is not: the traits print because they are what the appointment is FOR."""
    out = _inspect_cabinet(tmp_path, capsys, "tiny_valid.yaml", "--cabinet")
    assert "cabinet:" in out
    assert "chief_of_staff: Hal Verrin (hal_verrin) -- in post since turn 0" in out
    assert "competence=32%" in out
    assert "loyalty=88%" in out
    assert "personal_trust=65%" in out
    # The independent expert in the other chair, so the two rows cannot be the same person's
    # traits printed twice.
    assert "competence=86%" in out
    assert "loyalty=34%" in out


def test_inspect_cabinet_prints_a_vacancy_rather_than_omitting_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A vacancy is a costly condition, not an absence of news. `decree_state` has one empty post
    and `deficit_demo` has two -- a player who cannot see the empty chair cannot see the
    decision."""
    decree = _inspect_cabinet(tmp_path, capsys, "decree_state.yaml", "--cabinet")
    assert "chief_of_staff: vacant" in decree
    assert "foreign_minister: Raul Kesten (raul_kesten) -- in post since turn 0" in decree
    deficit = _inspect_cabinet(tmp_path, capsys, "deficit_demo.yaml", "--cabinet")
    assert "chief_of_staff: vacant" in deficit
    assert "foreign_minister: vacant" in deficit


def test_inspect_cabinet_shows_both_holders_when_both_posts_are_filled(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = _inspect_cabinet(tmp_path, capsys, "tiny_valid.yaml", "--cabinet")
    assert "chief_of_staff: Hal Verrin (hal_verrin) -- in post since turn 0" in out
    assert "foreign_minister: Ilse Marovec (ilse_marovec) -- in post since turn 0" in out


def test_the_cabinet_section_is_opt_in(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Matching every other `inspect` detail flag: a plain `inspect` stays the short summary it
    has always been."""
    assert "cabinet:" not in _inspect_cabinet(tmp_path, capsys, "tiny_valid.yaml")


def test_the_affordability_guard_counts_appointments_with_every_other_sink() -> None:
    """One guard, four terms, against OPENING capital -- and its message names all four.

    The boundary is authored, not contrived: moving `ilse_marovec` (276) to chief of staff while
    putting `hal_verrin` (147) in the ministry she leaves costs 423, which `tiny_valid` can afford
    on its own; add a 100-capital investment and the total is 523 against an opening 500, so the
    whole set is refused. Nothing is partially applied -- the closing state is never reached.
    """
    state = _load("tiny_valid.yaml")
    transfer = CabinetDecision(
        orders=(
            CabinetOrder(post=CabinetPost.CHIEF_OF_STAFF, character_id="ilse_marovec"),
            CabinetOrder(post=CabinetPost.FOREIGN_MINISTER, character_id="hal_verrin"),
        )
    )
    affordable = resolve_turn(
        state,
        DecisionSet(
            expected_turn=state.turn,
            expected_state_version=state.state_version,
            decisions=[transfer],
        ),
    )
    seated = affordable.state.world.countries["arken"].cabinet
    assert seated is not None
    assert seated.offices[CabinetPost.CHIEF_OF_STAFF].character_id == "ilse_marovec"
    assert seated.offices[CabinetPost.FOREIGN_MINISTER].character_id == "hal_verrin"
    assert sum(post.capital_committed for post in affordable.report.governance.posts) == 423

    with pytest.raises(TurnResolutionError) as exc_info:
        resolve_turn(state, _invest(state, 100, _TINY_TARGET, transfer))
    message = str(exc_info.value)
    for term in (
        "route commitment",
        "relationship investment",
        "constitutional amendment",
        "cabinet appointment 423",
    ):
        assert term in message, term
    assert "523" in message and "500" in message
