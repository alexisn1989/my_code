"""Gate 4A1: endpoint shapes for the read-only and lifecycle operations.

Assertions target schema, identities and meaningful political figures rather
than whole-response snapshots, so a copy change does not produce a wall of
diffs while a shape regression still fails.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.main import ApiSettings, create_app

REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_DIR = REPO_ROOT / "data" / "scenarios"
ALL_SCENARIO_IDS = ("decree_state", "deficit_demo", "tiny_valid")


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """A fresh app per test, with an isolated save root.

    The session is process-wide by design, so tests must not share one app
    instance or they would share a game.
    """
    app = create_app(
        ApiSettings(save_root=tmp_path / "saves", scenario_root=SCENARIO_DIR, serve_spa=False)
    )
    with TestClient(app, base_url="http://127.0.0.1:8420") as test_client:
        yield test_client


def _new_game(client: TestClient, scenario_id: str = "decree_state") -> dict:
    response = client.post("/api/game/new", json={"scenario_id": scenario_id})
    assert response.status_code == 200, response.text
    return response.json()


# --------------------------------------------------------------------------
# Scenarios
# --------------------------------------------------------------------------


def test_scenarios_lists_all_three_and_marks_the_showcase(client: TestClient) -> None:
    response = client.get("/api/scenarios")

    assert response.status_code == 200
    body = response.json()
    assert {row["scenario_id"] for row in body} == set(ALL_SCENARIO_IDS)
    showcase = [row for row in body if row["is_showcase"]]
    assert [row["scenario_id"] for row in showcase] == ["decree_state"]


def test_scenario_cards_describe_the_real_scenario(client: TestClient) -> None:
    body = {row["scenario_id"]: row for row in client.get("/api/scenarios").json()}

    decree = body["decree_state"]
    assert "unlimited decree authority" in decree["government_form"]
    assert decree["election_interval_label"] == "No election scheduled"
    assert decree["starting_legitimacy_text"].endswith("%")


# --------------------------------------------------------------------------
# New game
# --------------------------------------------------------------------------


@pytest.mark.parametrize("scenario_id", ALL_SCENARIO_IDS)
def test_every_shipped_scenario_starts_through_the_api(
    client: TestClient, scenario_id: str
) -> None:
    body = _new_game(client, scenario_id)

    assert body["turn"] == 0
    assert body["revision"] == "0.0"
    assert set(body["concerns"]) == {
        "money",
        "legitimacy",
        "legislature",
        "constitution",
        "survival",
    }
    assert body["map"]["presentation_only"] is True


def test_new_game_accepts_a_seed_override(client: TestClient) -> None:
    response = client.post("/api/game/new", json={"scenario_id": "decree_state", "seed": 0})

    assert response.status_code == 200


def test_new_game_rejects_an_unknown_scenario(client: TestClient) -> None:
    response = client.post("/api/game/new", json={"scenario_id": "no_such_scenario"})

    assert response.status_code == 400
    assert response.json()["type"] == "scenario_invalid"


@pytest.mark.parametrize("attempt", ["../../etc/passwd", "/etc/passwd", "..", "Decree_State"])
def test_new_game_refuses_a_scenario_id_that_is_not_an_identifier(
    client: TestClient, attempt: str
) -> None:
    response = client.post("/api/game/new", json={"scenario_id": attempt})

    assert response.status_code == 400
    assert response.json()["type"] == "scenario_invalid"


def test_new_game_rejects_unknown_fields(client: TestClient) -> None:
    response = client.post("/api/game/new", json={"scenario_id": "decree_state", "cheat": "please"})

    assert response.status_code == 422


# --------------------------------------------------------------------------
# State and no-active-session
# --------------------------------------------------------------------------


def test_state_before_any_game_is_a_distinct_404(client: TestClient) -> None:
    """A restarted server must say 'no active game', not crash."""
    response = client.get("/api/game/state")

    assert response.status_code == 404
    assert response.json()["type"] == "no_active_session"


def test_state_returns_the_bare_dashboard_shape(client: TestClient) -> None:
    _new_game(client)

    body = client.get("/api/game/state").json()

    # Deliberately NOT an envelope: no turnResult, no dashboard wrapper.
    assert "turnResult" not in body
    assert "dashboard" not in body
    assert body["revision"] == "0.0"
    assert body["political_capital"]["display"] == "500 / 1000"


def test_state_exposes_no_raw_engine_payload(client: TestClient) -> None:
    _new_game(client)

    raw = client.get("/api/game/state").text

    for forbidden in ("state_json", "report_json", "decisions_json", "entry_hash"):
        assert forbidden not in raw


# --------------------------------------------------------------------------
# Strategic map -- read-only (Strategic Military Map, Gate M0 commit 6)
# --------------------------------------------------------------------------


def test_strategic_map_before_any_game_is_a_distinct_404(client: TestClient) -> None:
    """Same shape as `/game/state`'s no-active-session behaviour -- there is deliberately no
    `present: false` flag, because a loaded game can never lack a map (frozen plan sec.11.3)."""
    response = client.get("/api/game/map/strategic")

    assert response.status_code == 404
    assert response.json()["type"] == "no_active_session"


def test_strategic_map_matches_the_authored_tiny_valid_scenario(client: TestClient) -> None:
    _new_game(client, scenario_id="tiny_valid")

    body = client.get("/api/game/map/strategic").json()

    assert body["map_id"] == "arken_basin"
    assert body["capital_theater_id"] == "arken_capital"
    assert len(body["theaters"]) == 5
    # Four, not three, since the fictional-geography revision: `shape_arken_isles` was authored
    # into `tiny_valid` as an approved decorative shape (revision sec.3 item 1, and the shape-count
    # table in sec.4 records tiny_valid 3 -> 4). It creates no theater, route or mechanic, which is
    # why the theater count above is unmoved.
    assert len(body["shapes"]) == 4
    theater_ids = [t["theater_id"] for t in body["theaters"]]
    assert theater_ids == sorted(theater_ids)
    capital = next(t for t in body["theaters"] if t["theater_id"] == "arken_capital")
    assert capital["is_capital"] is True
    assert capital["owner_display_name"] == "Republic of Arken"


def test_strategic_map_exposes_no_raw_engine_payload(client: TestClient) -> None:
    _new_game(client, scenario_id="tiny_valid")

    raw = client.get("/api/game/map/strategic").text

    for forbidden in ("state_json", "report_json", "decisions_json", "entry_hash"):
        assert forbidden not in raw


def test_strategic_map_does_not_change_after_resolving_a_turn(client: TestClient) -> None:
    _new_game(client, scenario_id="tiny_valid")
    before = client.get("/api/game/map/strategic").json()

    resolve_response = client.post("/api/game/resolve", json={"revision": "0.0", "decisions": []})
    assert resolve_response.status_code == 200, resolve_response.text

    after = client.get("/api/game/map/strategic").json()
    assert after == before


# --------------------------------------------------------------------------
# Decision options -- the legal-move envelope (frozen plan Sec 4.6)
# --------------------------------------------------------------------------


def test_decision_options_before_any_game_is_a_distinct_404(client: TestClient) -> None:
    response = client.get("/api/game/decision-options")

    assert response.status_code == 404
    assert response.json()["type"] == "no_active_session"


def test_decision_options_reports_the_real_engine_constants(client: TestClient) -> None:
    """Bounds and costs must be the engine's own numbers -- never invented ones."""
    _new_game(client)

    body = client.get("/api/game/decision-options").json()

    assert body["revision"] == "0.0"
    assert body["tax_rate_bps_minimum"] == 0
    assert body["tax_rate_bps_maximum"] == 10_000
    assert body["relationship_investment_minimum"] == 1
    assert body["relationship_investment_maximum"] == 200
    assert body["decree_legislative_capital_cost"] == 250
    assert body["decree_amendment_capital_cost"] == 400


@pytest.mark.parametrize(
    ("scenario_id", "expected"),
    [("decree_state", True), ("deficit_demo", False), ("tiny_valid", False)],
)
def test_decree_availability_reflects_the_real_constitution(
    client: TestClient, scenario_id: str, expected: bool
) -> None:
    _new_game(client, scenario_id)

    body = client.get("/api/game/decision-options").json()

    assert body["decree_available"] is expected
    axis = next(row for row in body["constitutional_axes"] if row["axis"] == "decree_authority")
    assert axis["current_value"] in {"none", "emergency_only", "unlimited"}
    assert (axis["current_value"] == "unlimited") is expected


@pytest.mark.parametrize("scenario_id", ("decree_state", "deficit_demo"))
def test_unicameral_scenarios_report_exactly_one_chamber_of_options(
    client: TestClient, scenario_id: str
) -> None:
    _new_game(client, scenario_id)

    body = client.get("/api/game/decision-options").json()

    assert len(body["chambers"]) == 1
    assert all(row["chamber"] == body["chambers"][0] for row in body["blocs"])


def test_bicameral_scenario_reports_both_chambers_of_options(client: TestClient) -> None:
    _new_game(client, "tiny_valid")

    body = client.get("/api/game/decision-options").json()

    assert len(body["chambers"]) == 2
    assert {row["chamber"] for row in body["blocs"]} == set(body["chambers"])


def test_decision_options_spending_categories_match_the_seven_real_categories(
    client: TestClient,
) -> None:
    _new_game(client)

    body = client.get("/api/game/decision-options").json()

    assert {row["category"] for row in body["spending_categories"]} == {
        "health",
        "education",
        "welfare",
        "infrastructure",
        "defense",
        "security",
        "administration",
    }
    for row in body["spending_categories"]:
        assert row["current_amount"] > 0


def test_decision_options_lists_all_five_constitutional_axes(client: TestClient) -> None:
    _new_game(client)

    body = client.get("/api/game/decision-options").json()

    axes = {row["axis"] for row in body["constitutional_axes"]}
    assert axes == {
        "decree_authority",
        "executive_system",
        "executive_selection",
        "national_election_interval_turns",
        "executive_term_limit_terms",
    }
    for row in body["constitutional_axes"]:
        if row["nullable"]:
            assert row["allowed_values"] is None
        else:
            assert row["current_value"] in row["allowed_values"]


def test_decision_options_exposes_no_raw_engine_payload(client: TestClient) -> None:
    _new_game(client)

    raw = client.get("/api/game/decision-options").text

    for forbidden in ("state_json", "report_json", "entry_hash", "constitution_json"):
        assert forbidden not in raw


def test_decision_options_opening_capital_matches_the_dashboard(client: TestClient) -> None:
    _new_game(client)

    options = client.get("/api/game/decision-options").json()
    dashboard = client.get("/api/game/state").json()

    assert options["opening_capital"] == dashboard["political_capital"]["current"]


# --------------------------------------------------------------------------
# History
# --------------------------------------------------------------------------


def test_history_is_empty_before_any_turn_resolves(client: TestClient) -> None:
    _new_game(client)

    assert client.get("/api/game/history").json() == []


def test_unknown_history_turn_reports_the_available_range(client: TestClient) -> None:
    _new_game(client)

    response = client.get("/api/game/history/9")

    assert response.status_code == 404
    assert response.json()["type"] == "snapshot_not_found"


# --------------------------------------------------------------------------
# Saves and checkpoints
# --------------------------------------------------------------------------


def test_new_game_registers_exactly_one_save(client: TestClient) -> None:
    _new_game(client)

    saves = client.get("/api/saves").json()

    assert len(saves) == 1
    assert saves[0]["loadable"] is True
    assert saves[0]["current_turn"] == 0


def test_save_listing_never_exposes_a_filesystem_path(client: TestClient) -> None:
    _new_game(client)

    raw = client.get("/api/saves").text

    assert "/" not in raw.replace("\\/", "") or "save_root" not in raw
    for row in client.get("/api/saves").json():
        assert set(row) == {
            "save_id",
            "display_name",
            "scenario_id",
            "current_turn",
            "updated_at",
            "terminal_outcome_summary",
            "loadable",
            "integrity_problem",
        }


def test_save_as_creates_a_new_checkpoint_and_leaves_the_active_id_alone(
    client: TestClient,
) -> None:
    _new_game(client)
    original = client.get("/api/saves").json()[0]["save_id"]

    response = client.post("/api/game/save-as", json={"display_name": "Before the amendment"})

    assert response.status_code == 200
    checkpoint = response.json()
    assert checkpoint["save_id"] != original
    assert checkpoint["display_name"] == "Before the amendment"
    assert {row["save_id"] for row in client.get("/api/saves").json()} == {
        original,
        checkpoint["save_id"],
    }


@pytest.mark.parametrize("name", ["", "   ", "x" * 81])
def test_save_as_rejects_an_unusable_display_name(client: TestClient, name: str) -> None:
    _new_game(client)

    response = client.post("/api/game/save-as", json={"display_name": name})

    assert response.status_code == 422


# --------------------------------------------------------------------------
# Load
# --------------------------------------------------------------------------


def test_load_restores_a_previously_saved_game(client: TestClient) -> None:
    _new_game(client)
    save_id = client.get("/api/saves").json()[0]["save_id"]

    response = client.post("/api/game/load", json={"save_id": save_id})

    assert response.status_code == 200
    assert response.json()["revision"] == "0.0"


@pytest.mark.parametrize(
    "attempt", ["../../etc/passwd", "/etc/passwd", "not-a-uuid", "a/b", "..", ""]
)
def test_load_refuses_anything_that_is_not_a_uuid(client: TestClient, attempt: str) -> None:
    """Rejected on shape, before any Path is built -- and never echoed back."""
    response = client.post("/api/game/load", json={"save_id": attempt})

    assert response.status_code == 400
    assert response.json()["type"] == "save_not_found"
    assert attempt not in response.text or attempt == ""


def test_load_of_a_well_formed_but_absent_save_is_404(client: TestClient) -> None:
    response = client.post(
        "/api/game/load", json={"save_id": "550e8400-e29b-41d4-a716-446655440000"}
    )

    assert response.status_code == 404
    assert response.json()["type"] == "save_not_found"


def test_a_tampered_save_is_refused_and_does_not_replace_the_session(
    client: TestClient, tmp_path: Path
) -> None:
    import json

    _new_game(client)
    save_id = client.get("/api/saves").json()[0]["save_id"]
    path = tmp_path / "saves" / f"{save_id}.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["entries"][-1]["entry_hash"] = "0" * len(raw["entries"][-1]["entry_hash"])
    path.write_text(json.dumps(raw), encoding="utf-8")

    response = client.post("/api/game/load", json={"save_id": save_id})

    assert response.status_code == 409
    assert response.json()["type"] == "history_invalid"
    # The previously active session is untouched by the failed load.
    assert client.get("/api/game/state").status_code == 200
