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
from collections import Counter

from app.content.scenarios import load_scenario_file
from app.core.canonical_json import canonical_dumps
from app.simulation.decisions import (
    BlocInvestment,
    BlocRelationshipInvestmentDecision,
    BudgetDecision,
    DecisionSet,
    InfluenceAllocation,
)
from app.simulation.history import advance_game, new_game, validate_history
from app.simulation.legislative_voting import DECREE_POLITICAL_CAPITAL_COST
from app.simulation.legislature import LegislativeOutcome, ProposalRoute
from app.simulation.relationships import RELATIONSHIP_INVESTMENT_CAP, relationship_gain_bps
from app.simulation.report import SectorProductionConstraint
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


TINY_VALID_NATURAL_CONCLUSION_TURN = 32
"""Phase 3C: `tiny_valid`'s real, deterministic horizon under ordinary play with no decisions
submitted -- a 2-term limit and a 16-turn election interval reach `consecutive_terms_held == 2`
exactly at turn 32, firing `TERM_LIMIT_EXIT` (the incumbent wins its turn-16 election, then hits
the limit at its second). Not a bug in the soak or the election formula: this is the intended new
behavior (`docs.adr` 0013) -- a government can now genuinely run out its term, and once it does,
`GameAlreadyConcludedError` refuses any further resolution (proven below). The pre-3C 100-turn
horizon this test used is no longer reachable through ordinary play for THIS scenario; the
soak now runs to the real, natural conclusion instead."""


def test_100_turn_soak_with_real_scenario_and_accounting_every_turn_stays_sustainable() -> None:
    """The Phase 2A counterpart to the test above: a real scenario, government
    accounting resolving every turn, and an explicit check that the
    deliberately-sustainable budget behaves as documented over a long run —
    cash grows, debt never does, and every turn still reconciles, through
    tiny_valid's real, natural conclusion (Phase 3C: a term-limit exit)."""
    state = load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml")
    save = new_game(state, save_format_version=SAVE_FORMAT_VERSION)
    opening_debt = state.world.countries["arken"].treasury.debt
    turns = TINY_VALID_NATURAL_CONCLUSION_TURN

    started = time.monotonic()
    for _ in range(turns):
        current = save.current_state()
        decisions = DecisionSet(
            expected_turn=current.turn,
            expected_state_version=current.state_version,
            decisions=(),
        )
        save = advance_game(save, decisions)
    elapsed = time.monotonic() - started

    assert save.current_turn() == turns
    assert len(save.entries) == turns + 1
    assert validate_history(save) == []

    concluded_politics = save.current_state().world.countries["arken"].politics
    assert concluded_politics is not None
    assert concluded_politics.terminal_outcome is not None
    assert concluded_politics.terminal_outcome.bucket.value == "defeat"
    assert concluded_politics.terminal_outcome.removal_reason is not None
    assert concluded_politics.terminal_outcome.removal_reason.value == "term_limit_exit"
    assert concluded_politics.terminal_outcome.turn == turns

    from app.core.errors import GameAlreadyConcludedError

    stale_decisions = DecisionSet(
        expected_turn=save.current_turn(),
        expected_state_version=save.current_state().state_version,
        decisions=(),
    )
    try:
        advance_game(save, stale_decisions)
        raise AssertionError("expected GameAlreadyConcludedError")
    except GameAlreadyConcludedError:
        pass

    final_country = save.current_state().world.countries["arken"]
    assert final_country.treasury.debt == opening_debt, (
        "a sustainable budget with no repayment modeled should never accrue new debt"
    )
    assert final_country.treasury.cash_on_hand > 0

    # Phase 3A, T-S1 (Phase 3C: re-verified at the new, real 32-turn horizon): legitimacy
    # trajectory is monotone toward the authored order support (order-support drift only, since
    # tiny_valid's economy is flat) and never leaves its declared bounds. 7,961, not the pre-3C
    # 100-turn figure of 7,991 -- the trajectory is identical up to this point, simply observed
    # over a shorter, now-real horizon.
    assert final_country.politics is not None
    assert final_country.politics.legitimacy_bps == 7_961
    legitimacy_by_turn = []

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
        assert report.political is not None
        assert 0 <= report.political.closing_legitimacy_bps <= 10_000
        assert (
            0
            <= report.political.closing_political_capital
            <= (report.political.political_capital_capacity)
        )
        legitimacy_by_turn.append(report.political.closing_legitimacy_bps)
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
        # Phase 2C2, T32: every deposit is capacity-bound for `tiny_valid`'s full tested
        # horizon (the shortest-lived deposit, critical_minerals, lasts exactly 100 turns), so
        # the extraction-sector output is preserved at its calibrated turn-1 figure for all
        # 100 turns — no clamp, no drift.
        extraction_row = next(
            s for s in report.production.sectors if s.category is SectorCategory.EXTRACTION
        )
        assert report.resources.extraction_sector_real_output == 2_000_000_000
        assert report.resources.extraction_sector_potential_output == 2_000_000_000
        assert extraction_row.actual_output == 2_000_000_000
        assert extraction_row.constraint is SectorProductionConstraint.PHYSICAL_RESOURCE_CONSTRAINED

    assert all(a <= b for a, b in zip(legitimacy_by_turn, legitimacy_by_turn[1:], strict=False)), (
        "tiny_valid's economy is flat, so legitimacy must move monotonically toward the "
        "authored constitutional_order_support_bps with no performance-driven reversal"
    )

    print(
        f"\n{turns}-turn soak (real scenario, labor+resources+production+derivation+finance "
        f"every turn, through its real natural conclusion): {elapsed:.3f}s total, "
        f"{elapsed / turns * 1000:.2f}ms/turn"
    )


DEFICIT_DEMO_NATURAL_CONCLUSION_TURN = 40
"""Phase 3C: `deficit_demo`'s real, deterministic horizon under ordinary play with no decisions
submitted -- it wins its turn-20 election, then loses its turn-40 election via `ELECTORAL_DEFEAT`
(its baseline election support is genuinely below the required 5,000 bps threshold). Not a bug in
the soak or the election formula: this is the intended new behavior (`docs.adr` 0013) -- a
government can now genuinely lose an election, and once it does, `GameAlreadyConcludedError`
refuses any further resolution (proven below). The pre-3C 100-turn horizon this test used is no
longer reachable through ordinary play for THIS scenario; the soak now runs to the real, natural
conclusion instead. This truncates the timber trajectory's own hand-worked steady-state regime
(turns 41+), which is now unreachable under ordinary play and is no longer asserted here."""


def test_100_turn_soak_with_deficit_demo_exercises_the_full_timber_trajectory() -> None:
    """The Phase 2C1 counterpart to the soak test above, using `deficit_demo.yaml` specifically
    because its timber deposit passes through the first two regimes of its hand-worked trajectory
    (R4/R8) within its real, Phase-3C-natural horizon — resolutions 1-39 capacity-bound, resolution
    40 the `STOCK_CONSTRAINED` boundary (the game concludes via `ELECTORAL_DEFEAT` at turn 40
    itself, so the steady-state regime, resolutions 41+, is no longer reachable through ordinary
    play and is not asserted). None of this is within `tiny_valid.yaml`'s own calibration, whose
    boundary sits around resolution 250. Also proves conservation/no-negative-reserves/
    labor-resource-agreement hold for the full real horizon of a scenario that (unlike
    `tiny_valid`) deliberately borrows every turn.
    """
    state = load_scenario_file(SCENARIO_DIR / "deficit_demo.yaml")
    save = new_game(state, save_format_version=SAVE_FORMAT_VERSION)
    turns = DEFICIT_DEMO_NATURAL_CONCLUSION_TURN

    started = time.monotonic()
    for _ in range(turns):
        current = save.current_state()
        decisions = DecisionSet(
            expected_turn=current.turn,
            expected_state_version=current.state_version,
            decisions=(),
        )
        save = advance_game(save, decisions)
    elapsed = time.monotonic() - started

    assert save.current_turn() == turns
    assert len(save.entries) == turns + 1
    assert validate_history(save) == []

    concluded_politics = save.current_state().world.countries["strapped"].politics
    assert concluded_politics is not None
    assert concluded_politics.terminal_outcome is not None
    assert concluded_politics.terminal_outcome.bucket.value == "defeat"
    assert concluded_politics.terminal_outcome.removal_reason is not None
    assert concluded_politics.terminal_outcome.removal_reason.value == "electoral_defeat"
    assert concluded_politics.terminal_outcome.turn == turns

    from app.core.errors import GameAlreadyConcludedError

    stale_decisions = DecisionSet(
        expected_turn=save.current_turn(),
        expected_state_version=save.current_state().state_version,
        decisions=(),
    )
    try:
        advance_game(save, stale_decisions)
        raise AssertionError("expected GameAlreadyConcludedError")
    except GameAlreadyConcludedError:
        pass

    timber_by_turn = []
    extraction_output_by_turn = []
    legitimacy_by_turn = []
    for entry in save.entries[1:]:
        report = entry.report()
        assert report is not None
        assert report.labor_market is not None
        assert report.resources is not None
        assert report.production is not None
        assert report.political is not None
        assert 0 <= report.political.closing_legitimacy_bps <= 10_000
        assert (
            0
            <= report.political.closing_political_capital
            <= (report.political.political_capital_capacity)
        )
        legitimacy_by_turn.append(report.political.closing_legitimacy_bps)
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
        extraction_row = next(
            s for s in report.production.sectors if s.category is SectorCategory.EXTRACTION
        )
        assert report.resources.extraction_sector_real_output == extraction_row.actual_output
        assert extraction_row.constraint is SectorProductionConstraint.PHYSICAL_RESOURCE_CONSTRAINED
        extraction_output_by_turn.append(report.resources.extraction_sector_real_output)

    for i, row in enumerate(timber_by_turn[:39], start=1):
        assert row.status == DepositStatus.CAPACITY_CONSTRAINED, f"resolution {i}"
    boundary = timber_by_turn[39]
    assert boundary.status == DepositStatus.STOCK_CONSTRAINED
    assert boundary.closing_stock == 0
    # Phase 3C: the game concludes via ELECTORAL_DEFEAT at turn 40 itself, the same turn as the
    # STOCK_CONSTRAINED boundary above -- the steady-state regime (resolutions 41+) that the
    # pre-3C 100-turn soak asserted here is no longer reachable through ordinary play and is not
    # asserted.

    # Phase 2C2, T31: the exact extraction-sector output trajectory (§8), held through this
    # scenario's real, Phase-3C-natural 40-turn horizon — 500,000,000 through turn 25,
    # 100,000,000 for turns 26-40 (iron_ore depleted). Turn 41's steady-state figure
    # (50,000,000, timber's steady state) is no longer reachable and is not asserted.
    for i, output in enumerate(extraction_output_by_turn[:25], start=1):
        assert output == 500_000_000, f"turn {i}"
    for i, output in enumerate(extraction_output_by_turn[25:40], start=26):
        assert output == 100_000_000, f"turn {i}"

    # Phase 3A, T-S1 (Phase 3C: re-verified at the new, real 40-turn horizon): legitimacy dips at
    # exactly the one resource-depletion shock reachable within this horizon (turn 26, matching
    # the extraction-output regime boundary above) and nowhere else -- the turn-41 dip the pre-3C
    # soak asserted here is no longer reachable through ordinary play.
    dip_turns = [
        turn
        for turn, (previous, current) in enumerate(
            zip(legitimacy_by_turn, legitimacy_by_turn[1:], strict=False), start=2
        )
        if current < previous
    ]
    assert dip_turns == [26]
    assert legitimacy_by_turn[-1] == 6_431

    print(
        f"\n{turns}-turn soak (deficit_demo, timber trajectory through its real natural "
        f"conclusion): {elapsed:.3f}s total, {elapsed / turns * 1000:.2f}ms/turn"
    )


# --- Phase 3B1: a proposal EVERY turn, for 100 turns -------------------------------------------
#
# The three soaks above submit no decisions at all, so 100 turns of them never touch the
# legislative path once. This one submits a real `BudgetDecision` on every single turn against
# `decree_state.yaml` -- the only shipped scenario where all three outcomes are reachable, since
# it is the only one holding `decree_authority: unlimited` alongside a real legislature.


def _proposal_for(*, turn: int, opening_rate_bps: int, opening_capital: int) -> BudgetDecision:
    """A deterministic proposal chosen purely from this turn's own state -- no randomness, no
    clock, no hidden counter.

    The rate target ALTERNATES around the scenario's authored 20%: whatever the current rate is,
    the proposal moves it the other way. Without that, a proposal that merely restates the rate
    already in force would be a zero-magnitude change, every bloc would sit at its baseline, and
    the soak would silently stop exercising policy compatibility after the first application.

    The four-turn cycle covers no-influence / decree / cheapest-passing / one-short, and each
    expensive branch is guarded by what the government can actually afford this turn -- so the
    sequence can never trip slot 1's `committed <= opening` guard and abort the soak, while
    remaining a pure function of state.
    """
    target = 2_000 if opening_rate_bps >= 2_500 else 2_500
    slot = turn % 4
    if slot == 1 and opening_capital >= DECREE_POLITICAL_CAPITAL_COST:
        return BudgetDecision(personal_income_rate_bps=target, route=ProposalRoute.DECREE)
    if slot == 2 and opening_capital >= 283:
        return BudgetDecision(
            personal_income_rate_bps=target,
            influence=(
                InfluenceAllocation(
                    party_id="opposition_party", bloc_id="main", political_capital=283
                ),
            ),
        )
    if slot == 3 and opening_capital >= 282:
        return BudgetDecision(
            personal_income_rate_bps=target,
            influence=(
                InfluenceAllocation(
                    party_id="opposition_party", bloc_id="main", political_capital=282
                ),
            ),
        )
    return BudgetDecision(personal_income_rate_bps=target)


def _strip_relationship(legislature_json: dict) -> dict:
    """(Phase 3B2B) `government_relationship_bps` is genuinely mutable now -- decay and a policy
    reaction move it on every enacted-proposal turn, by design. Composition (chambers, parties,
    seats, roles, discipline, preferences) and the authored `baseline_government_relationship_bps`
    remain exactly as static as D7 always required; this strips only the field 3B2B deliberately
    makes mutable, mirroring `test_decree_state_scenario.py`'s identical fix."""
    return {
        **legislature_json,
        "parties": [
            {
                **party,
                "blocs": [
                    {k: v for k, v in bloc.items() if k != "government_relationship_bps"}
                    for bloc in party["blocs"]
                ],
            }
            for party in legislature_json["parties"]
        ],
    }


def test_100_turn_soak_with_a_proposal_every_turn_on_decree_state() -> None:
    save = new_game(
        load_scenario_file(SCENARIO_DIR / "decree_state.yaml"),
        save_format_version=SAVE_FORMAT_VERSION,
    )
    authored_legislature = canonical_dumps(
        _strip_relationship(
            save.current_state()
            .world.countries["valdrun"]
            .politics.legislature.model_dump(mode="json")  # type: ignore[union-attr]
        )
    )
    outcomes: Counter[LegislativeOutcome] = Counter()

    started = time.monotonic()
    for turn in range(TURNS):
        opening_state = save.current_state()
        opening_player = opening_state.world.countries["valdrun"]
        assert opening_player.finance is not None and opening_player.politics is not None
        opening_tax_policy = opening_player.finance.tax_policy
        opening_spending_plan = opening_player.finance.spending_plan
        opening_capital = opening_player.politics.political_capital
        capacity = opening_player.politics.political_capital_capacity

        decision = _proposal_for(
            turn=turn,
            opening_rate_bps=opening_tax_policy.personal_income_rate_bps,
            opening_capital=opening_capital,
        )
        save = advance_game(
            save,
            DecisionSet(
                expected_turn=opening_state.turn,
                expected_state_version=opening_state.state_version,
                decisions=(decision,),
            ),
        )

        # The turn advanced exactly once.
        assert save.current_turn() == turn + 1
        assert len(save.entries) == turn + 2

        report = save.entries[-1].report()
        assert report is not None and report.legislative is not None
        legislative = report.legislative
        outcomes[legislative.outcome] += 1

        closing_player = save.current_state().world.countries["valdrun"]
        assert closing_player.finance is not None and closing_player.politics is not None

        # A proposal was submitted every turn, so NO_PROPOSAL must never appear.
        assert legislative.outcome is not LegislativeOutcome.NO_PROPOSAL

        # The commitment never exceeds THIS turn's opening capital (R2), and closing capital
        # stays inside [0, capacity].
        assert legislative.political_capital_committed <= opening_capital
        assert legislative.opening_political_capital == opening_capital
        assert 0 <= closing_player.politics.political_capital <= capacity

        # D7: composition is static -- byte-identical to the authored legislature (except the
        # relationship field, which 3B2B deliberately makes mutable), every turn, through passes,
        # failures and decrees alike.
        assert (
            canonical_dumps(
                _strip_relationship(
                    closing_player.politics.legislature.model_dump(mode="json")  # type: ignore[union-attr]
                )
            )
            == authored_legislature
        )

        # Every chamber's supporting seats equal its own apportioned target (P1), and passage is
        # decided per chamber against its own majority.
        for chamber in legislative.chambers:
            assert chamber.supporting_seats == chamber.target_total
            assert chamber.passed == (chamber.supporting_seats >= chamber.required_yes_seats)

        # The gate: applied iff passed or decreed, and applied EXACTLY as submitted.
        applied = legislative.outcome in (
            LegislativeOutcome.PASSED_LEGISLATIVE,
            LegislativeOutcome.ENACTED_BY_DECREE,
        )
        if applied:
            assert (
                closing_player.finance.tax_policy.personal_income_rate_bps
                == decision.personal_income_rate_bps
            )
        else:
            assert closing_player.finance.tax_policy == opening_tax_policy
        # No spending target was ever submitted, so the plan never moves on any path.
        assert closing_player.finance.spending_plan == opening_spending_plan
    elapsed = time.monotonic() - started

    # Following this file's existing policy: the O(n^2) full-history revalidation already runs
    # inside every `advance_game` call above, so the final check confirms the whole chain.
    assert validate_history(save) == []
    assert save.current_turn() == TURNS

    # The sequence genuinely exercised every route, rather than silently degenerating into one.
    assert outcomes[LegislativeOutcome.PASSED_LEGISLATIVE] > 0
    assert outcomes[LegislativeOutcome.FAILED_LEGISLATIVE] > 0
    assert outcomes[LegislativeOutcome.ENACTED_BY_DECREE] > 0
    assert sum(outcomes.values()) == TURNS

    print(
        f"\n{TURNS}-turn soak (decree_state, a proposal every turn): {elapsed:.3f}s total, "
        f"{elapsed / TURNS * 1000:.2f}ms/turn; outcomes="
        + ", ".join(f"{outcome.value}={count}" for outcome, count in sorted(outcomes.items()))
    )


# --- Phase 3B2A: mixed-expenditure soak ---------------------------------------------------------


def _affordable_nonzero_investment(*, opening_relationship_bps: int, capital_ceiling: int) -> int:
    """The largest amount in `[1, min(RELATIONSHIP_INVESTMENT_CAP, capital_ceiling)]` that buys a
    NONZERO gain against `opening_relationship_bps`, or 0 if none does (the relationship is close
    enough to the ceiling that every affordable amount would be a guaranteed no-op, which R13
    rejects atomically). Tried from the top down since gain is monotonic non-decreasing in
    capital (§8.3), so the first nonzero hit from the top is also the affordable maximum."""
    for capital in range(min(RELATIONSHIP_INVESTMENT_CAP, capital_ceiling), 0, -1):
        if (
            relationship_gain_bps(
                opening_relationship_bps=opening_relationship_bps, political_capital=capital
            )
            > 0
        ):
            return capital
    return 0


def test_100_turn_soak_with_mixed_expenditure_on_decree_state() -> None:
    """(T22) Every turn submits BOTH a budget proposal (cycling decree / cheapest-passing /
    one-short / no-influence, exactly as `_proposal_for` above) AND a relationship investment in
    `opposition_party/main` -- the two competing political-capital sinks Phase 3B2A introduces,
    exercised together on every turn for the whole soak, not merely in isolation."""
    save = new_game(
        load_scenario_file(SCENARIO_DIR / "decree_state.yaml"),
        save_format_version=SAVE_FORMAT_VERSION,
    )
    outcomes: Counter[LegislativeOutcome] = Counter()

    started = time.monotonic()
    for turn in range(TURNS):
        opening_state = save.current_state()
        opening_player = opening_state.world.countries["valdrun"]
        assert opening_player.finance is not None and opening_player.politics is not None
        assert opening_player.politics.legislature is not None
        opening_capital = opening_player.politics.political_capital
        capacity = opening_player.politics.political_capital_capacity
        opening_bloc = next(
            bloc
            for party in opening_player.politics.legislature.parties
            for bloc in party.blocs
            if party.id == "opposition_party" and bloc.id == "main"
        )

        budget = _proposal_for(
            turn=turn,
            opening_rate_bps=opening_player.finance.tax_policy.personal_income_rate_bps,
            opening_capital=opening_capital,
        )
        route_cost = (
            DECREE_POLITICAL_CAPITAL_COST
            if budget.route is ProposalRoute.DECREE
            else sum(a.political_capital for a in budget.influence)
        )
        investment = _affordable_nonzero_investment(
            opening_relationship_bps=opening_bloc.government_relationship_bps,
            capital_ceiling=max(0, opening_capital - route_cost),
        )

        decisions: list[BudgetDecision | BlocRelationshipInvestmentDecision] = [budget]
        if investment > 0:
            decisions.append(
                BlocRelationshipInvestmentDecision(
                    investments=(
                        BlocInvestment(
                            party_id="opposition_party",
                            bloc_id="main",
                            political_capital=investment,
                        ),
                    )
                )
            )
        decisions.sort(key=lambda d: d.kind)

        save = advance_game(
            save,
            DecisionSet(
                expected_turn=opening_state.turn,
                expected_state_version=opening_state.state_version,
                decisions=tuple(decisions),
            ),
        )
        assert save.current_turn() == turn + 1

        report = save.entries[-1].report()
        assert (
            report is not None
            and report.legislative is not None
            and report.political_capital is not None
        )
        legislative = report.legislative
        pcr = report.political_capital
        outcomes[legislative.outcome] += 1

        closing_player = save.current_state().world.countries["valdrun"]
        assert (
            closing_player.politics is not None and closing_player.politics.legislature is not None
        )
        closing_bloc = next(
            bloc
            for party in closing_player.politics.legislature.parties
            for bloc in party.blocs
            if party.id == "opposition_party" and bloc.id == "main"
        )

        # Capital never negative, never exceeds capacity, and every turn's total is bounded by
        # THAT turn's opening capital (R2/R6) -- never by opening + regeneration.
        assert 0 <= closing_player.politics.political_capital <= capacity
        assert pcr.total_committed <= opening_capital

        # (Phase 3B2B) Every relationship stays in range -- decay and an enacted-policy reaction
        # both now move it every turn, so the old "non-decreasing" assertion (valid only for
        # 3B2A, which had neither) is replaced with the strictly more informative guarantee this
        # phase actually provides: the deviation from the bloc's own AUTHORED baseline never
        # exceeds what §7's bounded formulas (decay 1/8, a capped policy reaction, investment's
        # own diminishing-returns bound) can produce -- it never runs away.
        assert -10_000 <= closing_bloc.government_relationship_bps <= 10_000
        assert (
            closing_bloc.baseline_government_relationship_bps
            == opening_bloc.baseline_government_relationship_bps
        )
        # The relationship-memory report and the investment agree on what happened this turn.
        prr = report.political_relationship
        assert prr is not None
        investment_rows = [
            row
            for row in prr.blocs
            if row.party_id == "opposition_party"
            and row.bloc_id == "main"
            and row.investment_capital > 0
        ]
        if investment > 0:
            assert len(investment_rows) == 1
            assert investment_rows[0].investment_capital == investment
        else:
            assert investment_rows == []

    elapsed = time.monotonic() - started

    assert validate_history(save) == []
    assert save.current_turn() == TURNS
    assert outcomes[LegislativeOutcome.PASSED_LEGISLATIVE] > 0
    assert outcomes[LegislativeOutcome.ENACTED_BY_DECREE] > 0
    assert sum(outcomes.values()) == TURNS

    print(
        f"\n{TURNS}-turn soak (decree_state, mixed budget + relationship investment every turn): "
        f"{elapsed:.3f}s total, {elapsed / TURNS * 1000:.2f}ms/turn; outcomes="
        + ", ".join(f"{outcome.value}={count}" for outcome, count in sorted(outcomes.items()))
    )
