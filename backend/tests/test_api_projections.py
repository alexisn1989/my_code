"""Gate 4A1: the purpose-built projections, and the ONE turn-result builder.

The load-bearing test here is `test_live_and_history_turn_result_are_identical`:
`TurnResultProjection` has a single implementation path, so live resolution and
historical detail cannot drift apart. Everything else checks that projections
read stored values rather than recomputing them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.api.projections import (
    REASON_LABELS,
    DashboardProjection,
    TurnResultProjection,
    build_dashboard,
    build_turn_result,
    format_bps_percent,
    format_signed_bps_points,
    label_for,
    revision_token,
)
from app.cli import REASON_RENDERERS
from app.content.scenarios import load_scenario_file
from app.simulation.decisions import DecisionSet
from app.simulation.history import GameSave, advance_game, new_game
from app.simulation.save_format import SAVE_FORMAT_VERSION

REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_DIR = REPO_ROOT / "data" / "scenarios"
ALL_SCENARIOS = ("tiny_valid.yaml", "deficit_demo.yaml", "decree_state.yaml")


def _fresh_save(scenario: str) -> GameSave:
    return new_game(
        load_scenario_file(SCENARIO_DIR / scenario), save_format_version=SAVE_FORMAT_VERSION
    )


def _advance(save: GameSave) -> GameSave:
    state = save.current_state()
    return advance_game(
        save,
        DecisionSet(expected_turn=state.turn, expected_state_version=state.state_version),
    )


# --------------------------------------------------------------------------
# Reason-ID coverage
# --------------------------------------------------------------------------


def test_api_labels_cover_exactly_the_engine_reason_ids() -> None:
    """The API's own label table must not drift from the emitted vocabulary.

    Keys are compared, not rendered text: the API deliberately does not import
    the CLI's renderers, so a wording change in the CLI cannot reshape an API
    payload -- but a NEW reason id must never reach a client unlabelled.
    """
    assert set(REASON_LABELS) == set(REASON_RENDERERS)


def test_unmapped_reason_id_degrades_visibly_rather_than_crashing() -> None:
    assert label_for("no_such_reason_id") == "[no_such_reason_id]"


# --------------------------------------------------------------------------
# Display conversion -- integer only, no float rounding
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value_bps", "expected"),
    [(0, "0.00%"), (6_000, "60.00%"), (4_822, "48.22%"), (10_000, "100.00%"), (-8_000, "-80.00%")],
)
def test_bps_render_as_exact_percentages(value_bps: int, expected: str) -> None:
    assert format_bps_percent(value_bps) == expected


@pytest.mark.parametrize(
    ("value_bps", "expected"), [(269, "+2.69pp"), (-269, "-2.69pp"), (0, "+0.00pp")]
)
def test_signed_point_deltas(value_bps: int, expected: str) -> None:
    assert format_signed_bps_points(value_bps) == expected


# --------------------------------------------------------------------------
# Dashboard
# --------------------------------------------------------------------------


@pytest.mark.parametrize("scenario", ALL_SCENARIOS)
def test_dashboard_builds_for_every_shipped_scenario(scenario: str) -> None:
    save = _fresh_save(scenario)
    state = save.current_state()

    dashboard = build_dashboard(state, save.entries[-1].report())

    assert isinstance(dashboard, DashboardProjection)
    assert dashboard.turn == 0
    assert dashboard.revision == "0.0"
    assert dashboard.country_name
    assert dashboard.government_form
    # All five player-facing concerns are always present.
    assert dashboard.concerns.money.label == "Money"
    assert dashboard.concerns.legitimacy.label == "Legitimacy"
    assert dashboard.concerns.legislature.label == "Legislature"
    assert dashboard.concerns.constitution.label == "Constitution"
    assert dashboard.concerns.survival.label == "Survival"
    assert dashboard.map.presentation_only is True
    assert "No province-level mechanics exist." in dashboard.map.note


def test_turn_zero_reports_risk_as_unassessed_rather_than_inventing_one() -> None:
    """The genesis entry has no report, and risk lives only in a report.

    Recomputing a coup risk from current state would present a forward-looking
    estimate as if it were a resolved fact.
    """
    save = _fresh_save("decree_state.yaml")

    dashboard = build_dashboard(save.current_state(), save.entries[-1].report())

    assert save.entries[-1].report() is None
    assert dashboard.concerns.survival.headline == "Not yet assessed"


def test_decree_state_opens_with_no_scheduled_election() -> None:
    save = _fresh_save("decree_state.yaml")

    dashboard = build_dashboard(save.current_state(), None)

    assert dashboard.next_election_label == "None scheduled"
    assert "unlimited decree authority" in dashboard.government_form


def test_dashboard_reports_capital_as_current_over_capacity() -> None:
    save = _fresh_save("decree_state.yaml")

    dashboard = build_dashboard(save.current_state(), None)

    assert dashboard.political_capital.display == "500 / 1000"
    assert dashboard.political_capital.current == 500
    assert dashboard.political_capital.capacity == 1000


def test_goal_card_traces_to_a_real_alert_or_says_nothing_is_pressing() -> None:
    save = _advance(_fresh_save("decree_state.yaml"))
    state = save.current_state()

    dashboard = build_dashboard(state, save.entries[-1].report())

    if dashboard.alerts:
        assert dashboard.goal.headline == f"Your priority: {dashboard.alerts[0].headline}"
    else:
        assert "Nothing is pressing" in dashboard.goal.headline


# --------------------------------------------------------------------------
# The one shared turn-result builder
# --------------------------------------------------------------------------


@pytest.mark.parametrize("scenario", ALL_SCENARIOS)
def test_turn_result_builds_from_a_stored_report(scenario: str) -> None:
    save = _advance(_fresh_save(scenario))
    entry = save.entries[-1]
    report = entry.report()
    assert report is not None

    result = build_turn_result(entry.state(), report)

    assert isinstance(result, TurnResultProjection)
    assert result.turn == 1
    assert result.revision == "1.1"
    assert result.outcome_headline
    assert result.drivers, "a resolved turn always emits at least one reason id"
    assert all(driver.label for driver in result.drivers)


def test_live_and_history_turn_result_are_identical() -> None:
    """One builder, one result -- whatever path reaches it.

    A live resolution renders the entry it just produced; history renders the
    same entry fetched by turn number. Both must be byte-identical, because both
    call `build_turn_result` over the same stored report.
    """
    save = _advance(_advance(_fresh_save("decree_state.yaml")))

    live_entry = save.entries[-1]
    live_report = live_entry.report()
    assert live_report is not None
    live = build_turn_result(live_entry.state(), live_report)

    historical_entry = save.entry_at(2)
    historical_report = historical_entry.report()
    assert historical_report is not None
    historical = build_turn_result(historical_entry.state(), historical_report)

    assert live == historical
    assert live.model_dump_json() == historical.model_dump_json()


def test_historical_dashboard_reflects_that_turn_not_the_current_one() -> None:
    """`dashboardAsOfTurn` must be reconstructed from the stored entry's state."""
    save = _advance(_advance(_advance(_fresh_save("decree_state.yaml"))))

    as_of_turn_one = build_dashboard(save.entry_at(1).state(), save.entry_at(1).report())
    current = build_dashboard(save.current_state(), save.entries[-1].report())

    assert as_of_turn_one.turn == 1
    assert as_of_turn_one.revision == "1.1"
    assert current.turn == 3
    assert as_of_turn_one != current


def test_revision_token_is_turn_dot_state_version() -> None:
    save = _advance(_fresh_save("tiny_valid.yaml"))
    state = save.current_state()

    assert revision_token(state) == f"{state.turn}.{state.state_version}"
    assert revision_token(state) == "1.1"


# --------------------------------------------------------------------------
# No raw engine models leak
# --------------------------------------------------------------------------


def test_projections_expose_no_raw_engine_payloads() -> None:
    """Projection JSON must not carry state_json/report_json/entry_hash/digests."""
    save = _advance(_fresh_save("decree_state.yaml"))
    entry = save.entries[-1]
    report = entry.report()
    assert report is not None

    payloads = (
        build_dashboard(entry.state(), report).model_dump_json(),
        build_turn_result(entry.state(), report).model_dump_json(),
    )

    for payload in payloads:
        for forbidden in ("state_json", "report_json", "decisions_json", "entry_hash", "dev"):
            assert forbidden not in payload, f"{forbidden} leaked into a projection"
