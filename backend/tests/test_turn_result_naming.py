"""Gate 4A3 UX-4e (DR1): the turn result names what it reports.

* Relationship drivers store only `party_id`/`bloc_id`. The projection adds `bloc_display_name` from
  the same state the result is built from, so the browser can say WHICH bloc -- without touching the
  stored report, and identically live and in history.
* The browser's `TAX_FIELD_LABEL` and `SPENDING_LABEL` (frontend/src/format/format.ts) must cover
  exactly the engine's tax fields and `SpendingCategory`, or a policy line silently falls back to
  "A tax rate changed." -- the same drift guard the sector labels have.
"""

from __future__ import annotations

import pathlib
import re

from app.api.projections import build_turn_result
from app.cli import _TAX_FIELD_LABELS
from app.content.scenarios import load_scenario_file
from app.simulation.decisions import BudgetDecision, DecisionSet
from app.simulation.history import GameSave, advance_game, new_game
from app.simulation.legislature import ProposalRoute
from app.simulation.save_format import SAVE_FORMAT_VERSION
from app.simulation.state import SpendingCategory
from tests.test_api_preview_parity import SCENARIO_DIR

FORMAT_TS = (
    pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src" / "format" / "format.ts"
)


def _decree_turn(save: GameSave) -> GameSave:
    """One turn whose budget is enacted by decree, so every seated bloc reacts and the turn records
    relationship drivers (an empty turn records none)."""
    state = save.current_state()
    return advance_game(
        save,
        DecisionSet(
            expected_turn=state.turn,
            expected_state_version=state.state_version,
            decisions=(BudgetDecision(personal_income_rate_bps=2_500, route=ProposalRoute.DECREE),),
        ),
    )


def _one_turn(scenario: str) -> GameSave:
    save = new_game(
        load_scenario_file(SCENARIO_DIR / f"{scenario}.yaml"),
        save_format_version=SAVE_FORMAT_VERSION,
    )
    return _decree_turn(save)


def test_relationship_drivers_name_their_bloc_from_the_turns_own_state() -> None:
    save = _one_turn("decree_state")
    entry = save.entries[-1]
    report = entry.report()
    assert report is not None
    politics = entry.state().world.countries[entry.state().world.player_country_id].politics
    assert politics is not None and politics.legislature is not None
    names = {(p.id, b.id): b.name for p in politics.legislature.parties for b in p.blocs}

    result = build_turn_result(entry.state(), report)
    bloc_drivers = [d for d in result.drivers if "bloc_id" in d.params and "party_id" in d.params]
    assert bloc_drivers, "anti-vacuity: the turn records relationship drivers"
    for driver in bloc_drivers:
        key = (str(driver.params["party_id"]), str(driver.params["bloc_id"]))
        assert driver.params["bloc_display_name"] == names[key], driver.reason_id

    # Presentation only: the stored report entries are exactly as they were written.
    assert not any("bloc_display_name" in e.params for e in report.entries)


def test_history_names_blocs_exactly_as_live_does() -> None:
    save = _decree_turn(_one_turn("decree_state"))
    live_entry = save.entries[-1]
    historical = save.entry_at(2)
    live_report, history_report = live_entry.report(), historical.report()
    assert live_report is not None and history_report is not None
    live = build_turn_result(live_entry.state(), live_report)
    again = build_turn_result(historical.state(), history_report)
    assert live.model_dump_json() == again.model_dump_json()


def _label_keys(name: str) -> set[str]:
    source = FORMAT_TS.read_text(encoding="utf-8")
    start = source.index(f"export const {name}")
    block = source[start : source.index("};", start)]
    return set(re.findall(r'^\s*([a-z_]+):\s*"[^"]+",\s*$', block, flags=re.MULTILINE))


def test_tax_field_labels_equal_the_engines_tax_fields() -> None:
    assert (
        _label_keys("TAX_FIELD_LABEL")
        == set(_TAX_FIELD_LABELS)
        == {
            "personal_income_rate_bps",
            "corporate_rate_bps",
            "consumption_rate_bps",
        }
    )


def test_spending_labels_equal_the_engines_spending_categories() -> None:
    keys = _label_keys("SPENDING_LABEL")
    assert len(keys) == 7, "anti-vacuity: all seven entries were parsed"
    assert keys == {category.value for category in SpendingCategory}
