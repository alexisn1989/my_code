"""Gate 4A3 UX-3 (U1): the stakes line the interface shows a new player stays true.

`WIN_AND_LOSS_LINE` in `frontend/src/greybox/screens/GlossaryScreen.tsx` reads: "You win by turning
this into a competitive constitution and then winning the first election held under it. You lose if
you are removed by coup, forced abdication, ...". Two facts make it true, and each is pinned here:

* every way the engine can remove a government is named in it, by the phrase the API already uses
  for that reason (`REMOVAL_REASON_TEXT`), so a new removal reason cannot ship unnamed;
* every shipped scenario starts NONCOMPETITIVE -- the only condition under which "turning this into
  a competitive constitution" describes the player's country, since the victory requires a
  transition from a noncompetitive constitution (`phases.py`, the liberalization check).
"""

from __future__ import annotations

import pathlib
import re

import pytest

from app.api.outcome_labels import REMOVAL_REASON_TEXT
from app.content.scenarios import load_scenario_file
from app.simulation.government_survival import is_noncompetitive_constitution
from app.simulation.state import RemovalReason
from tests.test_api_preview_parity import SCENARIO_DIR

REPO = pathlib.Path(__file__).resolve().parents[2]
GLOSSARY_TSX = REPO / "frontend" / "src" / "greybox" / "screens" / "GlossaryScreen.tsx"
SHIPPED_SCENARIOS = sorted(path.stem for path in SCENARIO_DIR.glob("*.yaml"))


def _win_and_loss_line() -> str:
    """The line exactly as the browser builds it: the array's strings joined by single spaces."""
    source = GLOSSARY_TSX.read_text(encoding="utf-8")
    start = source.index("export const WIN_AND_LOSS_LINE = [")
    block = source[start : source.index('].join(" ");', start)]
    return " ".join(re.findall(r'^\s*"([^"]*)",\s*$', block, flags=re.MULTILINE))


def test_the_line_is_actually_parsed() -> None:
    """Anti-vacuity: the parse yields the whole sentence, not an empty or partial string."""
    line = _win_and_loss_line()
    assert line.startswith("You win by turning this into a competitive constitution")
    assert line.endswith("electoral defeat or term limit exit.")


@pytest.mark.parametrize("reason", list(RemovalReason), ids=lambda reason: reason.value)
def test_every_removal_reason_is_named_by_its_authored_phrase(reason: RemovalReason) -> None:
    assert REMOVAL_REASON_TEXT[reason].phrase in _win_and_loss_line()


def test_the_scenarios_are_the_three_shipped_ones() -> None:
    """Anti-vacuity for the next test: it must run over real scenarios, not an empty glob."""
    assert SHIPPED_SCENARIOS == ["decree_state", "deficit_demo", "tiny_valid"]


@pytest.mark.parametrize("scenario_id", SHIPPED_SCENARIOS)
def test_every_shipped_scenario_starts_noncompetitive(scenario_id: str) -> None:
    state = load_scenario_file(SCENARIO_DIR / f"{scenario_id}.yaml")
    politics = state.world.countries[state.world.player_country_id].politics
    assert politics is not None
    constitution = politics.constitution
    assert is_noncompetitive_constitution(
        executive_selection=constitution.executive_selection,
        decree_authority=constitution.decree_authority,
    ), f"{scenario_id} starts competitive: the stakes line would be false there"
