"""`GET /api/game/military` -- current positions and destination options (commit 6).

This endpoint adds no legality logic. Every verdict it serves comes from `classify_destinations`,
the same function `/preview` explains with and `/resolve` decides submissions with, so the three
cannot disagree about what is legal or about why. The equality test below is what keeps that true:
if a second implementation ever appeared here, it would have to agree row-for-row with the first
across every theater of every shipped scenario, and any divergence fails.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.main import ApiSettings, create_app
from app.api.projections import build_military
from app.content.scenarios import load_scenario_file
from app.core.canonical_json import canonical_dumps
from app.simulation.military import classify_destinations

REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_DIR = REPO_ROOT / "data" / "scenarios"

#: Per scenario: player country, formation id, capital, the two player flanks, the two foreign
#: theaters. Literals, so a test cannot pass by re-deriving whatever the YAML happens to say.
SCENARIO_SHAPE: dict[str, tuple[str, str, str, tuple[str, str], tuple[str, str]]] = {
    "tiny_valid": (
        "arken",
        "arken_first_army",
        "arken_capital",
        ("arken_coast", "arken_north"),
        ("kessia_south", "vetruska_frontier"),
    ),
    "decree_state": (
        "valdrun",
        "valdrun_first_army",
        "valdrun_capital",
        ("valdrun_east", "valdrun_highlands"),
        ("marnil_border", "sorrend_plain"),
    ),
    "deficit_demo": (
        "strapped",
        "strapped_first_army",
        "home_capital",
        ("home_lowlands", "home_port"),
        ("marnil_march", "tolvane_isle"),
    ),
}

ALL_SCENARIOS = sorted(SCENARIO_SHAPE)


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(
        ApiSettings(save_root=tmp_path / "saves", scenario_root=SCENARIO_DIR, serve_spa=False)
    )
    with TestClient(app, base_url="http://127.0.0.1:8420") as test_client:
        yield test_client


def _new(client: TestClient, scenario_id: str = "tiny_valid") -> dict:
    response = client.post("/api/game/new", json={"scenario_id": scenario_id})
    assert response.status_code == 200, response.text
    return response.json()


def _military(client: TestClient) -> dict:
    response = client.get("/api/game/military")
    assert response.status_code == 200, response.text
    return response.json()


class TestTheProjectionNeverRederivesLegality:
    """§8.0: one classifier, one source of legality. The projection may present, never decide."""

    @pytest.mark.parametrize("scenario_id", ALL_SCENARIOS)
    def test_every_verdict_equals_the_classifier_directly(self, scenario_id: str) -> None:
        country_id, formation_id, *_ = SCENARIO_SHAPE[scenario_id]
        state = load_scenario_file(SCENARIO_DIR / f"{scenario_id}.yaml")
        military = state.world.countries[country_id].military
        assert military is not None

        projected = build_military(state)

        for row in projected.formations:
            expected = classify_destinations(
                formation=military.formations[row.formation_id],
                player_country_id=country_id,
                map_state=state.world.strategic_map,
            )
            assert [
                (o.theater_id, o.eligible, o.ineligible_reason_code)
                for o in row.destination_options
            ] == [(c.theater_id, c.eligible, c.ineligible_reason_code) for c in expected], (
                row.formation_id
            )
        assert [row.formation_id for row in projected.formations] == [formation_id]

    @pytest.mark.parametrize("scenario_id", ALL_SCENARIOS)
    def test_foreign_theaters_report_ownership_never_unreachability(self, scenario_id: str) -> None:
        """The precedence that must survive the trip through presentation: a foreign theater is
        refused for WHOSE it is, whether or not a route reaches it. Reporting the routed one as
        unreachable would imply that authoring a route would authorize entry."""
        _, _, _, _, foreign = SCENARIO_SHAPE[scenario_id]
        state = load_scenario_file(SCENARIO_DIR / f"{scenario_id}.yaml")

        options = {o.theater_id: o for o in build_military(state).formations[0].destination_options}

        for theater_id in foreign:
            assert options[theater_id].eligible is False
            assert options[theater_id].ineligible_reason_code == "destination_not_player_owned"


class TestTheShapeItServes:
    def test_it_carries_every_theater_with_a_reason_for_each_refusal(
        self, client: TestClient
    ) -> None:
        """Ineligible theaters are included, not filtered out: the interface has to explain an
        unavailable destination, and it cannot explain what it was never given."""
        _new(client)
        body = _military(client)

        options = body["formations"][0]["destination_options"]
        assert len(options) == 5, "every theater on the map, eligible or not"
        for option in options:
            assert (option["ineligible_reason_code"] is None) is option["eligible"]

    def test_it_names_the_current_location_and_every_option(self, client: TestClient) -> None:
        """Display names travel with ids everywhere, so no surface resolves one from the other and
        a raw id never becomes player-facing text."""
        _new(client)
        formation = _military(client)["formations"][0]

        assert formation["formation_id"] == "arken_first_army"
        assert formation["display_name"] == "First Army of Arken"
        assert formation["branch"] == "army"
        assert formation["location_theater_id"] == "arken_capital"
        assert formation["location_display_name"] == "Arken Capital Region"
        assert all(option["display_name"] for option in formation["destination_options"])
        by_id = {o["theater_id"]: o for o in formation["destination_options"]}
        assert by_id["arken_north"]["display_name"] == "Northern March"
        assert by_id["arken_north"]["eligible"] is True

    def test_the_revision_matches_the_dashboard(self, client: TestClient) -> None:
        """Revision-keyed, like decision options -- so the client can tell when it is stale."""
        dashboard = _new(client)
        assert _military(client)["revision"] == dashboard["revision"]

    def test_it_carries_no_history_and_no_draft(self, client: TestClient) -> None:
        """Current state only. What moved is reported by the resolve response and the Turn Result
        / History surfaces, from the report written when it happened; a history-derived field here
        would duplicate that record and could disagree with it."""
        _new(client)
        body = _military(client)

        assert set(body) == {"revision", "formations"}
        assert set(body["formations"][0]) == {
            "formation_id",
            "display_name",
            "branch",
            "location_theater_id",
            "location_display_name",
            "destination_options",
        }


class TestItTracksResolutionAndStaysReadOnly:
    def test_positions_follow_an_applied_movement(self, client: TestClient) -> None:
        dashboard = _new(client)
        before = _military(client)["formations"][0]
        assert before["location_theater_id"] == "arken_capital"

        resolved = client.post(
            "/api/game/resolve",
            json={
                "revision": dashboard["revision"],
                "campaign_id": dashboard["campaign_id"],
                "decisions": [
                    {
                        "kind": "military_movement",
                        "orders": [
                            {
                                "formation_id": "arken_first_army",
                                "destination_theater_id": "arken_north",
                            }
                        ],
                    }
                ],
            },
        )
        assert resolved.status_code == 200, resolved.text

        after = _military(client)
        assert after["formations"][0]["location_theater_id"] == "arken_north"
        assert after["formations"][0]["location_display_name"] == "Northern March"
        assert after["revision"] != before.get("revision")
        # The options moved with it: from the northern flank the capital is one hop and the other
        # flank is two, which is a real constraint of the shipped star map, not a defect.
        by_id = {o["theater_id"]: o for o in after["formations"][0]["destination_options"]}
        assert by_id["arken_capital"]["eligible"] is True
        assert by_id["arken_coast"]["eligible"] is False
        assert (
            by_id["arken_coast"]["ineligible_reason_code"] == "destination_not_directly_reachable"
        )

    def test_requesting_it_changes_nothing(self, client: TestClient) -> None:
        """Asking for the options is not submitting one."""
        dashboard = _new(client)
        state = load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml")
        before = canonical_dumps(state.model_dump(mode="json"))

        _military(client)
        _military(client)

        assert client.get("/api/game/state").json()["revision"] == dashboard["revision"]
        assert canonical_dumps(state.model_dump(mode="json")) == before

    def test_it_needs_an_active_session(self, client: TestClient) -> None:
        response = client.get("/api/game/military")

        assert response.status_code == 404
        assert response.json()["type"] == "no_active_session"
