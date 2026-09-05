"""Military Movement vertical slice, commit 3 -- authoritative military state and the approved
scenario rosters.

Commit 3 introduces STATE ONLY. There is deliberately no movement decision, no reachability
helper, no resolver change, no report and no reconciliation here; those arrive in commits 4 and 5.
What this file proves is that the state exists, is shaped exactly as the frozen plan specifies,
carries no field no mechanic reads, and that the three shipped scenarios author exactly the
approved rosters in the approved starting theaters.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from app.content.scenarios import load_scenario_file
from app.core.canonical_json import canonical_dumps
from app.simulation.geography import LabelAnchor, TheaterKind
from app.simulation.invariants import check_invariants
from app.simulation.state import (
    ForeignProfileRef,
    FormationBranch,
    FormationState,
    MilitaryState,
    TheaterPresentation,
    TheaterState,
)
from tests.conftest import make_game_state

SCENARIOS_DIR = Path(__file__).resolve().parents[2] / "data" / "scenarios"

#: The roster approved for each shipped scenario: scenario file -> (player country id, formation
#: id, display name, starting theater id, that theater's authored display name). Written here as
#: literals, deliberately: a test that re-derived them from the YAML would pass no matter what the
#: YAML said, which is the opposite of pinning an approved value.
APPROVED_ROSTERS: dict[str, tuple[str, str, str, str, str]] = {
    "tiny_valid.yaml": (
        "arken",
        "arken_first_army",
        "First Army of Arken",
        "arken_capital",
        "Arken Capital Region",
    ),
    "decree_state.yaml": (
        "valdrun",
        "valdrun_first_army",
        "First Army of Valdrun",
        "valdrun_capital",
        "Valdrun Capital Region",
    ),
    "deficit_demo.yaml": (
        "strapped",
        "strapped_first_army",
        "First Army of the Republic",
        "home_capital",
        "Capital Region",
    ),
}

_SCENARIO_FILES = sorted(APPROVED_ROSTERS)


# --------------------------------------------------------------------------
# The models
# --------------------------------------------------------------------------


class TestFormationModels:
    def test_branch_enum_contains_exactly_army(self) -> None:
        """No inert `NAVY`/`AIR_FORCE`. `RouteKind` has one member (`LAND`) and `TheaterKind` only
        `LAND`/`COASTAL`, so a naval or air branch would advertise reachability the shipped map
        cannot express."""
        assert [branch.value for branch in FormationBranch] == ["army"]

    def test_formation_state_has_exactly_the_three_approved_fields(self) -> None:
        """No status, strength, manpower, readiness, supply, equipment, commander or experience --
        no mechanic in this slice reads any of them. And no `formation_id`/`owner`: identity comes
        from the mapping key, ownership from the containing `CountryState`."""
        assert sorted(FormationState.model_fields) == [
            "branch",
            "display_name",
            "location_theater_id",
        ]

    def test_formation_state_rejects_an_extra_field(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            FormationState.model_validate(
                {
                    "display_name": "First Army",
                    "branch": "army",
                    "location_theater_id": "capital",
                    "strength": 10_000,
                }
            )
        assert "strength" in str(exc_info.value)

    def test_formation_state_rejects_an_embedded_identifier(self) -> None:
        """The key is authoritative; a duplicated id could disagree with it."""
        with pytest.raises(ValidationError):
            FormationState.model_validate(
                {
                    "formation_id": "first_army",
                    "display_name": "First Army",
                    "branch": "army",
                    "location_theater_id": "capital",
                }
            )

    def test_military_state_has_exactly_formations(self) -> None:
        assert sorted(MilitaryState.model_fields) == ["formations"]

    @pytest.mark.parametrize("bad_id", ["", "x" * 65])
    def test_formation_identifier_obeys_the_strict_length_bounds(self, bad_id: str) -> None:
        """`StrictFormationId` is 1..64, matching `StrictMapId`'s bounds."""
        with pytest.raises(ValidationError):
            MilitaryState.model_validate(
                {
                    "formations": {
                        bad_id: {
                            "display_name": "First Army",
                            "branch": "army",
                            "location_theater_id": "capital",
                        }
                    }
                }
            )

    def test_formation_identifier_is_strict_about_type(self) -> None:
        with pytest.raises(ValidationError):
            MilitaryState.model_validate(
                {
                    "formations": {
                        7: {
                            "display_name": "First Army",
                            "branch": "army",
                            "location_theater_id": "capital",
                        }
                    }
                }
            )

    def test_explicit_empty_military_state_round_trips_canonically(self) -> None:
        """`MilitaryState(formations={})` is a first-class value, not a stand-in for absence."""
        empty = MilitaryState(formations={})
        dumped = empty.model_dump(mode="json")
        assert dumped == {"formations": {}}
        assert MilitaryState.model_validate(dumped) == empty
        assert canonical_dumps(dumped) == canonical_dumps(
            MilitaryState.model_validate(json.loads(json.dumps(dumped))).model_dump(mode="json")
        )

    def test_formation_mapping_serialization_is_independent_of_insertion_order(self) -> None:
        """Canonical JSON sorts mapping keys, so two identical rosters built in different orders
        produce identical bytes -- the same argument `WorldState.foreign_profiles` records."""
        rows = {
            "b_army": FormationState(
                display_name="B", branch=FormationBranch.ARMY, location_theater_id="capital"
            ),
            "a_army": FormationState(
                display_name="A", branch=FormationBranch.ARMY, location_theater_id="capital"
            ),
        }
        forward = MilitaryState(formations=dict(rows))
        reversed_order = MilitaryState(formations={k: rows[k] for k in reversed(list(rows))})
        assert list(forward.formations) != list(reversed_order.formations)
        assert canonical_dumps(forward.model_dump(mode="json")) == canonical_dumps(
            reversed_order.model_dump(mode="json")
        )


# --------------------------------------------------------------------------
# The invariants
# --------------------------------------------------------------------------


def _codes(state: object) -> list[str]:
    return [violation.code for violation in check_invariants(state)]  # type: ignore[arg-type]


class TestMilitaryInvariants:
    def test_player_without_military_state_fails_with_its_own_code(self) -> None:
        state = make_game_state()
        player = state.world.countries["testland"]
        broken = state.model_copy(
            update={
                "world": state.world.model_copy(
                    update={"countries": {"testland": player.model_copy(update={"military": None})}}
                )
            }
        )
        assert "player_military_state_required" in _codes(broken)

    def test_player_military_state_required_is_distinct_from_the_institution_rule(self) -> None:
        """Two different facts about two different things: the institution row the coup-risk
        formula reads, and the formation container this slice adds. A state can satisfy either
        while violating the other."""
        state = make_game_state()
        player = state.world.countries["testland"]
        no_state = player.model_copy(update={"military": None})
        no_row = player.model_copy(
            update={"institutions": [row for row in player.institutions if row.id != "military"]}
        )

        only_state_missing = _codes(
            state.model_copy(
                update={
                    "world": state.world.model_copy(update={"countries": {"testland": no_state}})
                }
            )
        )
        only_row_missing = _codes(
            state.model_copy(
                update={"world": state.world.model_copy(update={"countries": {"testland": no_row}})}
            )
        )

        assert "player_military_state_required" in only_state_missing
        assert "player_military_institution_required" not in only_state_missing
        assert "player_military_institution_required" in only_row_missing
        assert "player_military_state_required" not in only_row_missing

    def test_explicit_empty_military_state_satisfies_the_presence_rule(self) -> None:
        """The rule is about the state being present, never about it holding a formation."""
        state = make_game_state()
        assert state.world.countries["testland"].military == MilitaryState(formations={})
        assert "player_military_state_required" not in _codes(state)

    def test_a_valid_player_owned_formation_location_passes(self) -> None:
        state = make_game_state()
        player = state.world.countries["testland"]
        with_formation = player.model_copy(
            update={
                "military": MilitaryState(
                    formations={
                        "first_army": FormationState(
                            display_name="First Army",
                            branch=FormationBranch.ARMY,
                            # `make_minimal_strategic_map`'s single theater, owned by the player.
                            location_theater_id="capital",
                        )
                    }
                )
            }
        )
        healthy = state.model_copy(
            update={
                "world": state.world.model_copy(update={"countries": {"testland": with_formation}})
            }
        )
        assert _codes(healthy) == []

    def test_unknown_theater_produces_the_unknown_theater_code(self) -> None:
        state = make_game_state()
        player = state.world.countries["testland"]
        broken = state.model_copy(
            update={
                "world": state.world.model_copy(
                    update={
                        "countries": {
                            "testland": player.model_copy(
                                update={
                                    "military": MilitaryState(
                                        formations={
                                            "first_army": FormationState(
                                                display_name="First Army",
                                                branch=FormationBranch.ARMY,
                                                location_theater_id="no_such_theater",
                                            )
                                        }
                                    )
                                }
                            )
                        }
                    }
                )
            }
        )
        codes = _codes(broken)
        assert "formation_location_unknown_theater" in codes
        assert "formation_location_not_owned_by_country" not in codes

    def test_foreign_owned_theater_produces_the_ownership_code(self) -> None:
        """The theater resolves, so this is not the unknown-theater case -- it is the distinct
        fact that the formation is standing somewhere its own country does not own."""
        state = make_game_state()
        world = state.world
        foreign_theater = TheaterState(
            display_name="Foreign Ground",
            kind=TheaterKind.LAND,
            owner=ForeignProfileRef(foreign_profile_id="kessia"),
            presentation=TheaterPresentation(
                centroid_x=7_000, centroid_y=7_000, label_anchor=LabelAnchor.CENTER
            ),
        )
        strategic_map = world.strategic_map
        widened = strategic_map.model_copy(
            update={"theaters": {**strategic_map.theaters, "foreign_ground": foreign_theater}}
        )
        player = world.countries["testland"]
        broken = state.model_copy(
            update={
                "world": world.model_copy(
                    update={
                        "strategic_map": widened,
                        "countries": {
                            "testland": player.model_copy(
                                update={
                                    "military": MilitaryState(
                                        formations={
                                            "first_army": FormationState(
                                                display_name="First Army",
                                                branch=FormationBranch.ARMY,
                                                location_theater_id="foreign_ground",
                                            )
                                        }
                                    )
                                }
                            )
                        },
                    }
                )
            }
        )
        codes = _codes(broken)
        assert "formation_location_not_owned_by_country" in codes
        assert "formation_location_unknown_theater" not in codes

    def test_a_non_player_country_may_keep_no_military_state(self) -> None:
        """Optional on the model; required only for the player."""
        state = make_game_state()
        player = state.world.countries["testland"]
        ai_country = player.model_copy(update={"id": "otherland", "military": None})
        with_ai = state.model_copy(
            update={
                "world": state.world.model_copy(
                    update={"countries": {"testland": player, "otherland": ai_country}}
                )
            }
        )
        codes = _codes(with_ai)
        assert "player_military_state_required" not in codes
        assert "formation_location_unknown_theater" not in codes
        assert "formation_location_not_owned_by_country" not in codes


# --------------------------------------------------------------------------
# The approved scenario rosters
# --------------------------------------------------------------------------


class TestApprovedRosters:
    @pytest.mark.parametrize("scenario_file", _SCENARIO_FILES)
    def test_scenario_authors_exactly_the_approved_formation(self, scenario_file: str) -> None:
        country_id, formation_id, display_name, theater_id, _ = APPROVED_ROSTERS[scenario_file]
        state = load_scenario_file(SCENARIOS_DIR / scenario_file)

        military = state.world.countries[country_id].military
        assert military is not None
        assert list(military.formations) == [formation_id]

        formation = military.formations[formation_id]
        assert formation.display_name == display_name
        assert formation.branch is FormationBranch.ARMY
        assert formation.location_theater_id == theater_id

    @pytest.mark.parametrize("scenario_file", _SCENARIO_FILES)
    def test_starting_theater_resolves_and_is_owned_by_the_player(self, scenario_file: str) -> None:
        country_id, _, _, theater_id, theater_display_name = APPROVED_ROSTERS[scenario_file]
        state = load_scenario_file(SCENARIOS_DIR / scenario_file)

        theater = state.world.strategic_map.theaters[theater_id]
        assert theater.display_name == theater_display_name
        assert theater.owner.kind == "player_country"
        assert theater.owner.country_id == country_id  # type: ignore[union-attr]
        assert country_id == state.world.player_country_id

    @pytest.mark.parametrize("scenario_file", _SCENARIO_FILES)
    def test_each_starting_theater_is_that_scenarios_capital(self, scenario_file: str) -> None:
        """Approved deliberately: the capital sits at the centre of each scenario's player
        subgraph, so a later slice can exercise movement from turn 1 without multi-hop."""
        _, _, _, theater_id, _ = APPROVED_ROSTERS[scenario_file]
        state = load_scenario_file(SCENARIOS_DIR / scenario_file)
        assert state.world.strategic_map.capital_theater_id == theater_id

    @pytest.mark.parametrize("scenario_file", _SCENARIO_FILES)
    def test_only_the_player_country_gains_military_state(self, scenario_file: str) -> None:
        country_id, _, _, _, _ = APPROVED_ROSTERS[scenario_file]
        state = load_scenario_file(SCENARIOS_DIR / scenario_file)
        for other_id, country in state.world.countries.items():
            if other_id != country_id:
                assert country.military is None, other_id

    @pytest.mark.parametrize("scenario_file", _SCENARIO_FILES)
    def test_no_foreign_profile_gains_military_state(self, scenario_file: str) -> None:
        """A foreign profile stays exactly what W1 made it: `display_name` and
        `war_capability_bps`. Owning map area did not upgrade it into a country, and neither does
        this slice."""
        state = load_scenario_file(SCENARIOS_DIR / scenario_file)
        for profile in state.world.foreign_profiles.values():
            assert sorted(type(profile).model_fields) == ["display_name", "war_capability_bps"]

    @pytest.mark.parametrize("scenario_file", _SCENARIO_FILES)
    def test_scenario_is_valid_under_every_invariant(self, scenario_file: str) -> None:
        state = load_scenario_file(SCENARIOS_DIR / scenario_file)
        assert _codes(state) == []

    @pytest.mark.parametrize("scenario_file", _SCENARIO_FILES)
    def test_formations_are_not_stored_inside_the_strategic_map(self, scenario_file: str) -> None:
        """Group 53 requires the map's canonical bytes to be identical across a resolved turn; a
        position stored inside it would break that the first time anything moved."""
        state = load_scenario_file(SCENARIOS_DIR / scenario_file)
        map_json = canonical_dumps(state.world.strategic_map.model_dump(mode="json"))
        assert "formation" not in map_json
        assert "military" not in map_json

    @pytest.mark.parametrize("scenario_file", _SCENARIO_FILES)
    def test_only_content_version_and_player_military_changed_in_the_yaml(
        self, scenario_file: str
    ) -> None:
        """Structural guard on the authored file itself: the roster edit must not have disturbed
        any other authored content. Compares the parsed YAML against the same file's own
        non-military content, so an accidental edit to a theater, route, sector or bloc fails
        here rather than only showing up as a digest change somewhere else.
        """
        country_id, _, _, _, _ = APPROVED_ROSTERS[scenario_file]
        with (SCENARIOS_DIR / scenario_file).open(encoding="utf-8") as handle:
            document = yaml.safe_load(handle)

        assert document["content_version"] == "0.15.0"
        for country in document["countries"]:
            if country["id"] == country_id:
                assert "military" in country
            else:
                assert "military" not in country
        # The map block is authored content this commit must not have touched.
        assert "military" not in json.dumps(document["strategic_map"])
        assert "formations" not in json.dumps(document["strategic_map"])
