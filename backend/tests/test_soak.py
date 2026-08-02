"""A deterministic soak test: many turns, full history revalidated every time.

Not part of `app.core`/`app.simulation` (this is a test module), so using
`time.monotonic()` here to measure wall-clock duration does not conflict with
the AST-based determinism guard — it never influences game state, only this
test's own reporting.
"""

from __future__ import annotations

import time

from app.simulation.decisions import DecisionSet
from app.simulation.history import advance_game, new_game, validate_history
from app.simulation.save_format import SAVE_FORMAT_VERSION
from tests.conftest import make_game_state

TURNS = 100


def test_100_turn_soak_completes_without_invariant_violations() -> None:
    save = new_game(
        make_game_state(turn=0, state_version=0), save_format_version=SAVE_FORMAT_VERSION
    )

    started = time.monotonic()
    for _ in range(TURNS):
        current = save.current_state()
        decisions = DecisionSet(
            expected_turn=current.turn,
            expected_state_version=current.state_version,
            decisions=[],
        )
        save = advance_game(save, decisions)
    elapsed = time.monotonic() - started

    assert save.current_turn() == TURNS
    assert len(save.entries) == TURNS + 1
    assert save.entry_count == TURNS + 1
    assert validate_history(save) == []

    # Reported for the record, not asserted against — Phase 1 favors
    # correctness (full history revalidation on every advance_game call)
    # over performance; see docs/architecture.md, "Performance boundary."
    print(
        f"\n{TURNS}-turn soak: {elapsed:.3f}s total, "
        f"{elapsed / TURNS * 1000:.2f}ms/turn (O(n^2) full-history revalidation)"
    )
