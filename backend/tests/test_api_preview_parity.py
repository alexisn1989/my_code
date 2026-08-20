"""Gate 4A1: preview parity with real resolution, and preview purity.

Parity is the safety net that makes composing the engine's primitives (rather
than calling one shared scoring function, which does not exist) safe: from an
identical opening save, preview and a real `/resolve` must agree exactly on every
deterministic field. Purity is what makes preview free to call at any time.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.main import ApiSettings, create_app
from app.content.scenarios import load_scenario_file
from app.simulation.save_format import dump_save_json

REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_DIR = REPO_ROOT / "data" / "scenarios"
ALL_SCENARIO_IDS = ("decree_state", "deficit_demo", "tiny_valid")

#: `tiny_valid` is the only bicameral scenario; the other two are unicameral.
BICAMERAL = "tiny_valid"


def _make_client(tmp_path: Path, name: str = "saves") -> TestClient:
    app = create_app(
        ApiSettings(save_root=tmp_path / name, scenario_root=SCENARIO_DIR, serve_spa=False)
    )
    return TestClient(app, base_url="http://127.0.0.1:8420")


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with _make_client(tmp_path) as test_client:
        yield test_client


def _new(client: TestClient, scenario_id: str = "decree_state") -> str:
    response = client.post("/api/game/new", json={"scenario_id": scenario_id})
    assert response.status_code == 200, response.text
    revision: str = response.json()["revision"]
    return revision


def _budget(rate_bps: int = 2_500, route: str = "legislative", **extra: Any) -> dict[str, Any]:
    return {"kind": "budget", "personal_income_rate_bps": rate_bps, "route": route, **extra}


def _preview(client: TestClient, revision: str, decisions: list[dict[str, Any]]) -> Any:
    return client.post("/api/game/preview", json={"revision": revision, "decisions": decisions})


def _resolve(client: TestClient, revision: str, decisions: list[dict[str, Any]]) -> Any:
    return client.post("/api/game/resolve", json={"revision": revision, "decisions": decisions})


def _chamber_tallies_from_trace(turn_result: dict[str, Any]) -> dict[str, str]:
    """Pull the per-chamber figures the turn result records in its trace layer."""
    return {row["label"]: row["value_text"] for row in turn_result["trace"]}


# --------------------------------------------------------------------------
# Parity: identical opening saves, preview vs. real resolution
# --------------------------------------------------------------------------


@pytest.mark.parametrize("scenario_id", ALL_SCENARIO_IDS)
def test_preview_matches_real_resolution_for_a_legislative_budget(
    tmp_path: Path, scenario_id: str
) -> None:
    """Every scenario, unicameral and bicameral alike, from the same opening save."""
    decisions = [_budget()]
    with _make_client(tmp_path, "preview") as previewer:
        revision = _new(previewer, scenario_id)
        previewed = _preview(previewer, revision, decisions)
        assert previewed.status_code == 200, previewed.text
        preview_body = previewed.json()

    with _make_client(tmp_path, "resolve") as resolver:
        revision = _new(resolver, scenario_id)
        resolved = _resolve(resolver, revision, decisions)
        assert resolved.status_code == 200, resolved.text
        trace = _chamber_tallies_from_trace(resolved.json()["turnResult"])

    for chamber in preview_body["chambers"]:
        name = chamber["chamber"]
        assert trace[f"{name}: supporting seats"] == str(chamber["supporting_seats"])
        assert trace[f"{name}: required seats"] == str(chamber["required_seats"])


def test_bicameral_chambers_are_reported_separately_with_their_own_thresholds(
    tmp_path: Path,
) -> None:
    with _make_client(tmp_path) as client:
        revision = _new(client, BICAMERAL)
        body = _preview(client, revision, [_budget()]).json()

    assert len(body["chambers"]) == 2, "tiny_valid is bicameral"
    identities = [row["chamber"] for row in body["chambers"]]
    assert len(set(identities)) == 2, "chamber identities are distinct, never pooled"
    for row in body["chambers"]:
        # Each chamber carries its own requirement derived from its own size.
        assert row["required_seats"] == row["total_seats"] // 2 + 1


@pytest.mark.parametrize("scenario_id", ("deficit_demo", "decree_state"))
def test_unicameral_scenarios_report_exactly_one_chamber(tmp_path: Path, scenario_id: str) -> None:
    with _make_client(tmp_path) as client:
        revision = _new(client, scenario_id)
        body = _preview(client, revision, [_budget()]).json()

    assert len(body["chambers"]) == 1


def test_a_passing_and_a_failing_proposal_are_both_predicted_correctly(
    tmp_path: Path,
) -> None:
    """`tiny_valid` passes unaided; `decree_state` does not."""
    with _make_client(tmp_path, "a") as client:
        passing = _preview(client, _new(client, BICAMERAL), [_budget()]).json()
    with _make_client(tmp_path, "b") as client:
        failing = _preview(client, _new(client, "decree_state"), [_budget()]).json()

    assert passing["would_pass"] is True
    assert failing["would_pass"] is False

    # And the prediction agrees with what really happens.
    with _make_client(tmp_path, "c") as client:
        revision = _new(client, BICAMERAL)
        assert _resolve(client, revision, [_budget()]).status_code == 200
    with _make_client(tmp_path, "d") as client:
        revision = _new(client, "decree_state")
        blocked = _resolve(client, revision, [_budget()]).json()
        assert "blocked" in blocked["turnResult"]["outcome_headline"].lower()


def test_a_permitted_decree_previews_its_flat_route_cost(tmp_path: Path) -> None:
    with _make_client(tmp_path) as client:
        revision = _new(client, "decree_state")
        body = _preview(client, revision, [_budget(route="decree")]).json()

    assert body["route"] == "decree"
    assert body["route_capital_cost"] == 250
    assert body["committed_capital"] == 250


def test_an_unavailable_decree_is_rejected_by_preview_and_resolve_alike(
    tmp_path: Path,
) -> None:
    """`deficit_demo` grants no unlimited decree authority. Both must refuse."""
    decisions = [_budget(route="decree")]
    with _make_client(tmp_path, "p") as previewer:
        revision = _new(previewer, "deficit_demo")
        previewed = _preview(previewer, revision, decisions)
    with _make_client(tmp_path, "r") as resolver:
        revision = _new(resolver, "deficit_demo")
        resolved = _resolve(resolver, revision, decisions)

    assert previewed.status_code == 422
    assert resolved.status_code == 422
    assert previewed.json()["type"] == resolved.json()["type"] == "decision_rejected"


def test_amendment_preview_matches_real_resolution(tmp_path: Path) -> None:
    amendment = [
        {
            "kind": "constitutional_amendment",
            "targets": [{"axis": "decree_authority", "value": "none"}],
            "route": "legislative",
        }
    ]
    with _make_client(tmp_path, "p") as previewer:
        revision = _new(previewer, "decree_state")
        previewed = _preview(previewer, revision, amendment)
        assert previewed.status_code == 200, previewed.text
        preview_body = previewed.json()

    with _make_client(tmp_path, "r") as resolver:
        revision = _new(resolver, "decree_state")
        resolved = _resolve(resolver, revision, amendment)
        assert resolved.status_code == 200, resolved.text
        trace = _chamber_tallies_from_trace(resolved.json()["turnResult"])

    row = preview_body["chambers"][0]
    key = f"Amendment {row['chamber']}: supporting of required"
    assert trace[key] == f"{row['supporting_seats']} of {row['required_seats']}"


def test_299_vs_300_budget_influence_is_not_a_knife_edge_on_decree_state(
    tmp_path: Path,
) -> None:
    """This scenario/route/pair is NOT a boundary -- both sides already pass.

    A prior closeout report described "the real 299-vs-300 seat boundary" for
    this exact allocation. Investigated for THIS closeout: `decree_state`'s
    own committed calibration comment documents the budget bargain's real
    knife-edge as 282 (fails) -> 283 (passes) -- see the scenario file's
    header. 299 and 300 both sit above that threshold, so both already carry,
    with IDENTICAL seat counts at both points (52 of 100, against 51
    required). The previous test here asserted only `tallies[300] >=
    tallies[299]` -- true, but true even with zero seats moved, so it never
    actually exercised a boundary. This test asserts the real, unglamorous
    fact instead: no seat changes hands between 299 and 300 here. The genuine
    knife-edge test is `test_the_real_amendment_knife_edge_on_tiny_valid`
    below, on the route/scenario where one actually exists at a legislative
    amendment's threshold.
    """
    tallies: dict[int, int] = {}
    for allocated in (299, 300):
        with _make_client(tmp_path, f"budget-{allocated}") as client:
            revision = _new(client, "decree_state")
            body = _preview(
                client,
                revision,
                [
                    _budget(
                        influence=[
                            {
                                "party_id": "opposition_party",
                                "bloc_id": "main",
                                "political_capital": allocated,
                            }
                        ]
                    )
                ],
            ).json()
            tallies[allocated] = body["chambers"][0]["supporting_seats"]
            assert body["chambers"][0]["carries"] is True, "both 299 and 300 already carry"
            assert body["committed_capital"] == allocated

    assert tallies[299] == tallies[300] == 52, (
        "299 and 300 are identical here -- 52 of 100 seats, both above the real "
        "283-seat budget threshold this scenario documents"
    )


def test_the_real_amendment_knife_edge_on_tiny_valid(tmp_path: Path) -> None:
    """The real, verified, pinned knife-edge -- found this closeout by binary
    search against the live preview endpoint, never by editing the scenario.

    `decree_state`'s legislative amendment route has NO reachable knife-edge
    at all: with the opposition bloc's influence taken to unbounded (and
    unaffordable) amounts, `supporting_seats` saturates at 56 of the 100
    required 67 -- discipline_bps=8000 caps how far capital alone can move
    that bloc, so a supermajority amendment can never pass there by
    legislative vote (only by decree, a separate, unconditional route).

    `tiny_valid` (bicameral: 100-seat lower needing 67, 60-seat upper needing
    40) DOES have a reachable one. Fixing `national_front/conservatives` at
    300 (its own saturation point, where the lower chamber alone already
    carries at 67 of 67) and varying `national_front/populists` alone finds
    the exact seat where the UPPER chamber -- the one still short -- flips:
    166 fails (39 of 40), 167 passes (40 of 40). Both allocations are
    affordable (466/467 of a 500 opening capital, no extra turns needed).
    """
    failing_populist_capital = 166
    passing_populist_capital = 167
    conservative_capital = 300

    def _amendment(populist_capital: int) -> dict[str, Any]:
        return {
            "kind": "constitutional_amendment",
            "targets": [{"axis": "decree_authority", "value": "none"}],
            "route": "legislative",
            "influence": [
                {
                    "party_id": "national_front",
                    "bloc_id": "conservatives",
                    "political_capital": conservative_capital,
                },
                {
                    "party_id": "national_front",
                    "bloc_id": "populists",
                    "political_capital": populist_capital,
                },
            ],
        }

    expectations = {
        failing_populist_capital: (False, 39, 40),
        passing_populist_capital: (True, 40, 40),
    }

    for populist_capital, (would_pass, upper_supporting, upper_required) in expectations.items():
        # Preview.
        with _make_client(tmp_path, f"amend-preview-{populist_capital}") as client:
            revision = _new(client, BICAMERAL)
            body = _preview(client, revision, [_amendment(populist_capital)]).json()
        assert body["would_pass"] is would_pass
        by_chamber = {row["chamber"]: row for row in body["chambers"]}
        assert by_chamber["lower"]["carries"] is True, "lower already carries at conservatives=300"
        assert by_chamber["lower"]["supporting_seats"] == 67
        assert by_chamber["upper"]["supporting_seats"] == upper_supporting
        assert by_chamber["upper"]["required_seats"] == upper_required
        assert by_chamber["upper"]["carries"] is would_pass

        # The real resolver agrees, at the same knife-edge.
        with _make_client(tmp_path, f"amend-resolve-{populist_capital}") as client:
            revision = _new(client, BICAMERAL)
            resolved = _resolve(client, revision, [_amendment(populist_capital)])
        assert resolved.status_code == 200, resolved.text
        turn_result = resolved.json()["turnResult"]
        trace = _chamber_tallies_from_trace(turn_result)
        assert (
            trace["Amendment upper: supporting of required"]
            == f"{upper_supporting} of {upper_required}"
        )
        assert ("passed" in turn_result["outcome_headline"].lower()) is would_pass


def test_affordability_totals_match_the_engines_own_three_components(
    tmp_path: Path,
) -> None:
    """Route cost + influence + investment, compared against opening capital."""
    with _make_client(tmp_path) as client:
        revision = _new(client, "decree_state")
        body = _preview(
            client,
            revision,
            [
                {
                    "kind": "bloc_relationship_investment",
                    "investments": [
                        {
                            "party_id": "opposition_party",
                            "bloc_id": "main",
                            "political_capital": 85,
                        }
                    ],
                },
                _budget(route="decree"),
            ],
        ).json()

    assert body["route_capital_cost"] == 250
    assert body["investment_capital"] == 85
    assert body["committed_capital"] == 335
    assert body["opening_capital"] == 500
    assert body["affordable"] is True


def test_an_unaffordable_draft_is_reported_as_unaffordable(tmp_path: Path) -> None:
    with _make_client(tmp_path) as client:
        revision = _new(client, "decree_state")
        body = _preview(
            client,
            revision,
            [
                _budget(
                    influence=[
                        {
                            "party_id": "opposition_party",
                            "bloc_id": "main",
                            "political_capital": 600,
                        }
                    ]
                )
            ],
        ).json()

    assert body["committed_capital"] == 600
    assert body["opening_capital"] == 500
    assert body["affordable"] is False


def test_noncanonical_ordering_is_rejected_not_reordered(client: TestClient) -> None:
    """Preview honours reject-not-normalize exactly as resolve does."""
    revision = _new(client)
    noncanonical = [
        _budget(
            influence=[
                {"party_id": "opposition_party", "bloc_id": "main", "political_capital": 10},
                {"party_id": "governing_party", "bloc_id": "core", "political_capital": 10},
            ]
        )
    ]

    response = _preview(client, revision, noncanonical)

    assert response.status_code == 422
    assert response.json()["type"] == "decision_rejected"


def test_preview_rejects_a_stale_revision(client: TestClient) -> None:
    revision = _new(client)
    assert _resolve(client, revision, []).status_code == 200

    response = _preview(client, revision, [_budget()])

    assert response.status_code == 409
    assert response.json()["type"] == "stale_revision"


def test_preview_labels_itself_an_estimate_and_names_what_it_excludes(
    client: TestClient,
) -> None:
    revision = _new(client)

    body = _preview(client, revision, [_budget()]).json()

    assert body["estimate"] is True
    excluded = " ".join(body["excludes_stochastic_channels"]).lower()
    for channel in ("election", "coup", "unrest", "impeachment"):
        assert channel in excluded


# --------------------------------------------------------------------------
# Purity
# --------------------------------------------------------------------------


def test_preview_changes_nothing_observable(client: TestClient, tmp_path: Path) -> None:
    revision = _new(client)
    session = client.app.state.session  # type: ignore[attr-defined]
    before_save = session.current_save
    before_bytes = dump_save_json(before_save)
    before_files = {
        path.name: (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted((tmp_path / "saves").iterdir())
    }

    assert _preview(client, revision, [_budget()]).status_code == 200

    after_save = session.current_save
    assert after_save is before_save, "the session object itself is unchanged"
    assert dump_save_json(after_save) == before_bytes, "canonical save bytes unchanged"
    assert len(after_save.entries) == len(before_save.entries), "history length unchanged"
    assert after_save.head_entry_hash == before_save.head_entry_hash, "head hash unchanged"
    after_files = {
        path.name: (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted((tmp_path / "saves").iterdir())
    }
    assert after_files == before_files, "no file created, modified or touched"


def test_preview_requests_no_rng_stream(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A runtime guard, not just a source scan: `derive_rng` must never be reached."""
    revision = _new(client)

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("preview must not consume an RNG stream")

    monkeypatch.setattr("app.core.rng.derive_rng", forbidden)
    monkeypatch.setattr("app.simulation.phases.derive_rng", forbidden)

    assert _preview(client, revision, [_budget()]).status_code == 200


def test_preview_module_imports_nothing_from_core_rng() -> None:
    """The frozen plan's T-preview-rng source scan."""
    source = (Path(__file__).resolve().parents[1] / "app" / "api" / "preview.py").read_text()
    # Scan import STATEMENTS, not prose: the module docstring legitimately
    # explains why it never reaches `derive_rng`, and a naive substring scan
    # would fail on its own documentation.
    import_lines = [
        line
        for line in source.splitlines()
        if line.startswith(("import ", "from ")) or line.lstrip().startswith(("import ", "from "))
    ]
    joined = "\n".join(import_lines)

    assert "core.rng" not in joined
    assert "derive_rng" not in joined
    assert "derive_seed" not in joined


def test_repeated_previews_are_byte_identical(client: TestClient) -> None:
    revision = _new(client)
    decisions = [_budget()]

    first = _preview(client, revision, decisions).text
    second = _preview(client, revision, decisions).text
    third = _preview(client, revision, decisions).text

    assert first == second == third


def test_previewing_does_not_change_a_later_real_resolution(tmp_path: Path) -> None:
    """A previewed game and a never-previewed control must resolve identically.

    This is the strongest purity statement available: not merely that preview
    writes nothing, but that its having happened is undetectable downstream.
    """
    decisions = [_budget()]

    with _make_client(tmp_path, "previewed") as previewed:
        revision = _new(previewed, "decree_state")
        assert _preview(previewed, revision, decisions).status_code == 200
        assert _preview(previewed, revision, decisions).status_code == 200
        assert _resolve(previewed, revision, decisions).status_code == 200
        previewed_bytes = dump_save_json(
            previewed.app.state.session.current_save  # type: ignore[attr-defined]
        )

    with _make_client(tmp_path, "control") as control:
        revision = _new(control, "decree_state")
        assert _resolve(control, revision, decisions).status_code == 200
        control_bytes = dump_save_json(
            control.app.state.session.current_save  # type: ignore[attr-defined]
        )

    assert json.loads(previewed_bytes) == json.loads(control_bytes)


def test_preview_does_not_take_the_mutation_boundary(client: TestClient) -> None:
    """A draft in one tab must not 409 an unrelated resolve in another."""
    revision = _new(client)
    session = client.app.state.session  # type: ignore[attr-defined]

    assert _preview(client, revision, [_budget()]).status_code == 200

    assert session.boundary.busy is False
    assert _resolve(client, revision, []).status_code == 200


def test_preview_needs_an_active_session(client: TestClient) -> None:
    response = _preview(client, "0.0", [])

    assert response.status_code == 404
    assert response.json()["type"] == "no_active_session"


def test_a_scenario_state_is_loadable_for_every_shipped_scenario() -> None:
    """Sanity: the parity fixtures above really do cover all three."""
    for scenario_id in ALL_SCENARIO_IDS:
        assert load_scenario_file(SCENARIO_DIR / f"{scenario_id}.yaml") is not None
