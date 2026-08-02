"""Disk-facing scenario loading.

This is the I/O boundary: `app.simulation.scenario.load_scenario_text` is
pure (text in, `GameState` out); this module reads a file from `data/scenarios/`
(or any path) and hands its text to that pure function. Callers that already
have scenario text in memory (e.g. an API request body, in Phase 4+) should
call `simulation.scenario.load_scenario_text` directly rather than going
through here.
"""

from __future__ import annotations

from pathlib import Path

from app.core.errors import ScenarioValidationError
from app.simulation.scenario import load_scenario_text
from app.simulation.state import GameState


def load_scenario_file(path: str | Path) -> GameState:
    """Read, parse, and validate a scenario YAML file into an initial `GameState`."""
    path = Path(path)
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ScenarioValidationError(str(path), [f"could not read file: {exc}"]) from exc
    return load_scenario_text(raw_text, source=str(path))
