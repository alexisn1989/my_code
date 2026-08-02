"""A deterministic soak test: many turns, full history revalidated every time.

Not part of `app.core`/`app.simulation` (this is a test module), so using
`time.monotonic()` here to measure wall-clock duration does not conflict with
the AST-based determinism guard — it never influences game state, only this
test's own reporting.

Uses `tiny_valid.yaml` (deliberately sustainable — see its header comment)
rather than the in-memory `make_game_state()` factory: a scenario with
government accounting active every turn is a materially more realistic soak
than one where 100 turns of no-op phases would run identically fast whether
or not the accounting engine existed at all.
"""

from __future__ import annotations

import time

from app.content.scenarios import load_scenario_file
from app.simulation.decisions import DecisionSet
from app.simulation.history import advance_game, new_game, validate_history
from app.simulation.save_format import SAVE_FORMAT_VERSION
from tests.conftest import SCENARIO_DIR, make_game_state

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
        f"\n{TURNS}-turn soak (in-memory factory state): {elapsed:.3f}s total, "
        f"{elapsed / TURNS * 1000:.2f}ms/turn (O(n^2) full-history revalidation)"
    )


def test_100_turn_soak_with_real_scenario_and_accounting_every_turn_stays_sustainable() -> None:
    """The Phase 2A counterpart to the test above: a real scenario, government
    accounting resolving every turn, and an explicit check that the
    deliberately-sustainable budget behaves as documented over a long run —
    cash grows, debt never does, and every turn still reconciles."""
    state = load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml")
    save = new_game(state, save_format_version=SAVE_FORMAT_VERSION)
    opening_debt = state.world.countries["arken"].treasury.debt

    started = time.monotonic()
    for _ in range(TURNS):
        current = save.current_state()
        decisions = DecisionSet(
            expected_turn=current.turn,
            expected_state_version=current.state_version,
            decisions=(),
        )
        save = advance_game(save, decisions)
    elapsed = time.monotonic() - started

    assert save.current_turn() == TURNS
    assert len(save.entries) == TURNS + 1
    assert validate_history(save) == []

    final_country = save.current_state().world.countries["arken"]
    assert final_country.treasury.debt == opening_debt, (
        "a sustainable budget with no repayment modeled should never accrue new debt"
    )
    assert final_country.treasury.cash_on_hand > 0

    for entry in save.entries[1:]:
        report = entry.report()
        assert report is not None
        assert report.finance is not None
        assert report.finance.reconciliation_status == "reconciled"
        assert report.finance.new_borrowing == 0

    print(
        f"\n{TURNS}-turn soak (real scenario, accounting every turn): "
        f"{elapsed:.3f}s total, {elapsed / TURNS * 1000:.2f}ms/turn"
    )
