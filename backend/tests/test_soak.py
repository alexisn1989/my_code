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
from app.simulation.resource_extraction import DepositStatus
from app.simulation.save_format import SAVE_FORMAT_VERSION
from app.simulation.state import ResourceCategory, SectorCategory
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
        assert report.labor_market is not None
        assert report.resources is not None
        assert report.production is not None
        assert report.tax_base_derivation is not None
        assert report.finance is not None
        assert report.finance.reconciliation_status == "reconciled"
        assert report.finance.new_borrowing == 0
        # Phase 2B3: labor allocation feeds production every turn, same-turn, no lag.
        allocated_by_category = {
            s.category: s.allocated_workers for s in report.labor_market.sectors
        }
        for row in report.production.sectors:
            assert row.employed_workers == allocated_by_category[row.category]
        # Phase 2C1: labor allocation feeds resource extraction every turn, same-turn, no lag;
        # no negative reserves; exact conservation, every deposit, every turn.
        assert (
            allocated_by_category[SectorCategory.EXTRACTION]
            == report.resources.extraction_sector_workers
        )
        for deposit in report.resources.deposits:
            assert deposit.closing_stock >= 0
            assert (
                deposit.opening_stock + deposit.regenerated
                == deposit.extracted + deposit.closing_stock
            )

    print(
        f"\n{TURNS}-turn soak (real scenario, labor+resources+production+derivation+finance "
        f"every turn): {elapsed:.3f}s total, {elapsed / TURNS * 1000:.2f}ms/turn"
    )


def test_100_turn_soak_with_deficit_demo_exercises_the_full_timber_trajectory() -> None:
    """The Phase 2C1 counterpart to the soak test above, using `deficit_demo.yaml` specifically
    because its timber deposit passes through all three regimes of its hand-worked trajectory
    (R4/R8) within a 100-turn horizon — resolutions 1-39 capacity-bound, resolution 40 the
    `STOCK_CONSTRAINED` boundary, resolutions 41-100 the steady state — none of which
    `tiny_valid.yaml`'s own calibration reaches (its own boundary sits around resolution 250).
    Also proves conservation/no-negative-reserves/labor-resource-agreement hold for the full 100
    turns of a scenario that (unlike `tiny_valid`) deliberately borrows every turn.
    """
    state = load_scenario_file(SCENARIO_DIR / "deficit_demo.yaml")
    save = new_game(state, save_format_version=SAVE_FORMAT_VERSION)

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
    assert validate_history(save) == []

    timber_by_turn = []
    for entry in save.entries[1:]:
        report = entry.report()
        assert report is not None
        assert report.labor_market is not None
        assert report.resources is not None
        allocated_by_category = {
            s.category: s.allocated_workers for s in report.labor_market.sectors
        }
        assert (
            allocated_by_category[SectorCategory.EXTRACTION]
            == report.resources.extraction_sector_workers
        )
        for deposit in report.resources.deposits:
            assert deposit.closing_stock >= 0
            assert (
                deposit.opening_stock + deposit.regenerated
                == deposit.extracted + deposit.closing_stock
            )
        timber_by_turn.append(
            next(d for d in report.resources.deposits if d.category == ResourceCategory.TIMBER)
        )

    for i, row in enumerate(timber_by_turn[:39], start=1):
        assert row.status == DepositStatus.CAPACITY_CONSTRAINED, f"resolution {i}"
    boundary = timber_by_turn[39]
    assert boundary.status == DepositStatus.STOCK_CONSTRAINED
    assert boundary.closing_stock == 0
    for i, row in enumerate(timber_by_turn[40:], start=41):
        assert row.status == DepositStatus.STOCK_CONSTRAINED, f"resolution {i}"
        assert row.extracted == 5_000, f"resolution {i}"
        assert row.closing_stock == 0, f"resolution {i}"

    print(
        f"\n{TURNS}-turn soak (deficit_demo, full three-regime timber trajectory): "
        f"{elapsed:.3f}s total, {elapsed / TURNS * 1000:.2f}ms/turn"
    )
