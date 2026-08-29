"""External Wars W1 fix-forward 7a: aggregate outbreak pressure above 10,000.

`ForeignConflictOutbreakReport.total_weight_bps` was typed `StrictBps` (<=10,000), which
contradicts the frozen plan sec.6.2, R4 point 5: only each dyad's OWN weight is bps-bounded
(R4 point 4, `clamp_bps(trunc_div(tension+grievance, 2))`); their SUM is deliberately unclamped,
and only the derived occurrence PROBABILITY is clamped, by an explicit `min(10_000, ...)`, "at
saturation a war is certain among eligible dyads, and the weighted pick still decides which."

The defect was invisible to shipped content because no shipped scenario authors more than one
dyad, so no shipped total can reach 10,000 at all. These tests exercise the multi-dyad regime the
type made unrepresentable.

Declared seeds, before any run: 42, 1337, 20260826, 7, 99991 -- the frozen plan's own sec.21
calibration set, reused rather than a fresh set chosen after observing results.
"""

from __future__ import annotations

from app.core.errors import GameAlreadyConcludedError
from app.core.money import BPS_DENOMINATOR
from app.simulation.decisions import DecisionSet
from app.simulation.foreign_conflict import (
    MAX_CONCURRENT_CONFLICTS,
    MIN_OUTBREAK_WEIGHT_BPS,
    OUTBREAK_SCALE_BPS,
    ConflictStatus,
    WarAim,
    dyad_weight_bps,
    initial_intensity_bps,
    outbreak_probability_bps,
    passes_pressure_floor,
    select_candidate_index,
)
from app.simulation.reconciliation import reconcile_foreign_affairs_report
from app.simulation.report import (
    ForeignConflictOutbreakCandidateRow,
    ForeignConflictOutbreakReport,
)
from app.simulation.resolver import resolve_turn
from app.simulation.state import ConflictDyadState, ForeignProfileState, GameState
from tests.conftest import make_game_state

DECLARED_SEEDS = (42, 1337, 20260826, 7, 99991)

# Two dyads at the maximum authorable pressure short of saturation: weight 9,500 each.
_PAIR_A = ("alpha", "beta")
_PAIR_B = ("delta", "gamma")


def _profile() -> ForeignProfileState:
    return ForeignProfileState(display_name="Profile", war_capability_bps=5_000)


def _dyad(country_a: str, country_b: str, *, tension: int, grievance: int) -> ConflictDyadState:
    return ConflictDyadState(
        country_a=country_a,
        country_b=country_b,
        aggressor=country_a,
        defender=country_b,
        aim_a=WarAim.DETERRENCE,
        aim_b=WarAim.TERRITORIAL,
        eligible=True,
        player_security_exposure_bps=0,
        tension_bps=tension,
        grievance_bps=grievance,
    )


def _candidate(
    country_a: str, country_b: str, *, tension: int, grievance: int
) -> ForeignConflictOutbreakCandidateRow:
    weight = dyad_weight_bps(tension_bps=tension, grievance_bps=grievance)
    return ForeignConflictOutbreakCandidateRow(
        country_a=country_a,
        country_b=country_b,
        aggressor=country_a,
        defender=country_b,
        tension_bps=tension,
        grievance_bps=grievance,
        raw_dyad_weight_bps=weight,
        passed_pressure_floor=passes_pressure_floor(raw_weight_bps=weight),
    )


def _outbreak_report(
    candidates: tuple[ForeignConflictOutbreakCandidateRow, ...], **overrides: object
) -> ForeignConflictOutbreakReport:
    """A self-consistent, non-occurring outbreak report over `candidates`, so each test below
    alters exactly the one fact it is about."""
    total = sum(row.raw_dyad_weight_bps for row in candidates if row.passed_pressure_floor)
    probability = outbreak_probability_bps(total_weight_bps=total)
    fields: dict[str, object] = {
        "turn": 0,
        "candidates": candidates,
        "minimum_outbreak_weight_bps": MIN_OUTBREAK_WEIGHT_BPS,
        "total_weight_bps": total,
        "outbreak_scale_bps": OUTBREAK_SCALE_BPS,
        "clamped_probability_bps": probability,
        # a draw at exactly the probability never fires, whatever the probability is
        "occurrence_draw": min(probability, BPS_DENOMINATOR - 1),
        "occurred": False,
        "initial_intensity_constant_bps": 2_000,
        "tension_intensity_weight_bps": 3_000,
    }
    fields.update(overrides)
    return ForeignConflictOutbreakReport(**fields)  # type: ignore[arg-type]


# --- items 1-3: two legal 9,500 candidates total 19,000, validate, and drive probability -------


def test_two_maximal_candidates_total_nineteen_thousand() -> None:
    rows = (
        _candidate(*_PAIR_A, tension=9_500, grievance=9_500),
        _candidate(*_PAIR_B, tension=9_500, grievance=9_500),
    )
    assert [row.raw_dyad_weight_bps for row in rows] == [9_500, 9_500], (
        "each dyad's own weight stays bps-bounded (frozen plan sec.6.2 R4 point 4)"
    )
    assert sum(row.raw_dyad_weight_bps for row in rows) == 19_000


def test_a_report_whose_total_is_nineteen_thousand_validates() -> None:
    rows = (
        _candidate(*_PAIR_A, tension=9_500, grievance=9_500),
        _candidate(*_PAIR_B, tension=9_500, grievance=9_500),
    )
    report = _outbreak_report(rows)
    assert report.total_weight_bps == 19_000, (
        "the aggregate must survive construction unclamped -- this is the exact assertion the "
        "pre-7a StrictBps ceiling made impossible"
    )


def test_probability_is_computed_from_the_full_unclamped_total() -> None:
    """19,000 * 700 / 10,000 = 1,330 -- more than twice the 700 a total wrongly clamped to
    10,000 would have produced, so this genuinely distinguishes the two."""
    rows = (
        _candidate(*_PAIR_A, tension=9_500, grievance=9_500),
        _candidate(*_PAIR_B, tension=9_500, grievance=9_500),
    )
    report = _outbreak_report(rows)
    assert report.clamped_probability_bps == outbreak_probability_bps(total_weight_bps=19_000)
    assert report.clamped_probability_bps == 1_330
    assert report.clamped_probability_bps != outbreak_probability_bps(
        total_weight_bps=BPS_DENOMINATOR
    ), "a clamped total would have produced a different, smaller probability"


# --- items 4-5: a selection draw above 10,000, and the walk that consumes it -------------------


def test_a_selection_draw_above_ten_thousand_is_valid_below_the_full_total() -> None:
    rows = (
        _candidate(*_PAIR_A, tension=9_500, grievance=9_500),
        _candidate(*_PAIR_B, tension=9_500, grievance=9_500),
    )
    report = _outbreak_report(
        rows,
        occurrence_draw=0,
        occurred=True,
        selection_draw=15_000,
        selected_country_a=_PAIR_B[0],
        selected_country_b=_PAIR_B[1],
        conflict_id=f"{_PAIR_B[0]}__{_PAIR_B[1]}__t0",
        opened_turn=0,
        initial_intensity_bps=initial_intensity_bps(tension_bps=9_500),
        initial_position_bps=0,
        initial_exhaustion_a_bps=0,
        initial_exhaustion_b_bps=0,
        initial_readiness_bps=0,
    )
    assert report.selection_draw == 15_000
    assert (report.selected_country_a, report.selected_country_b) == _PAIR_B


def test_the_cumulative_walk_uses_the_full_total_across_the_ten_thousand_boundary() -> None:
    """Weights (9_500, 9_500): draws 0-9,499 land on the first candidate and 9,500-18,999 on the
    second. A walk over a total clamped to 10,000 could not even represent the second half."""
    weights = (9_500, 9_500)
    assert select_candidate_index(selection_draw=0, weights_bps=weights) == 0
    assert select_candidate_index(selection_draw=9_499, weights_bps=weights) == 0
    assert select_candidate_index(selection_draw=9_500, weights_bps=weights) == 1
    assert select_candidate_index(selection_draw=10_000, weights_bps=weights) == 1
    assert select_candidate_index(selection_draw=18_999, weights_bps=weights) == 1


# --- item 6: reconciliation accepts a genuine turn whose total exceeds 10,000 -----------------


def _two_dyad_state(seed: int) -> GameState:
    return make_game_state(
        seed=seed,
        foreign_profiles={name: _profile() for name in (*_PAIR_A, *_PAIR_B)},
        dyads=(
            _dyad(*_PAIR_A, tension=9_500, grievance=9_500),
            _dyad(*_PAIR_B, tension=9_500, grievance=9_500),
        ),
    )


def _empty_decisions(state: GameState) -> DecisionSet:
    return DecisionSet(expected_turn=state.turn, expected_state_version=state.state_version)


def test_reconciliation_accepts_a_real_turn_whose_total_exceeds_ten_thousand() -> None:
    for seed in DECLARED_SEEDS:
        state = _two_dyad_state(seed)
        resolution = resolve_turn(state, _empty_decisions(state))
        assert resolution.report.foreign_affairs is not None
        assert resolution.report.foreign_affairs.outbreak.total_weight_bps == 19_000, (
            "sanity: this turn must actually be in the above-10,000 regime under test"
        )
        problems = reconcile_foreign_affairs_report(
            opening_state=state, closing_state=resolution.state, report=resolution.report
        )
        assert problems == [], f"seed {seed}: {problems!r}"


# --- item 7: tampering the total, the probability or the draw is still detected ---------------


def _resolve_until_outbreak() -> tuple[GameState, GameState, object]:
    """The first turn, across the declared seeds, on which the two-dyad state actually opens a
    war -- so the selection-draw tamper below has a real draw to corrupt."""
    for seed in DECLARED_SEEDS:
        state = _two_dyad_state(seed)
        for _ in range(40):
            resolution = resolve_turn(state, _empty_decisions(state))
            assert resolution.report.foreign_affairs is not None
            if resolution.report.foreign_affairs.outbreak.occurred:
                return state, resolution.state, resolution
            state = resolution.state
    raise AssertionError("no outbreak within 40 turns on any declared seed")


def test_tampering_the_total_the_probability_or_the_draw_is_detected() -> None:
    opening, closing, resolution = _resolve_until_outbreak()
    report = resolution.report  # type: ignore[attr-defined]
    assert report.foreign_affairs is not None
    outbreak = report.foreign_affairs.outbreak
    assert outbreak.total_weight_bps > BPS_DENOMINATOR

    def _reconcile_with(**outbreak_overrides: object) -> list[str]:
        forged = report.model_copy(
            update={
                "foreign_affairs": report.foreign_affairs.model_copy(
                    update={"outbreak": outbreak.model_copy(update=outbreak_overrides)}
                )
            }
        )
        return reconcile_foreign_affairs_report(
            opening_state=opening, closing_state=closing, report=forged
        )

    # the total silently clamped back to 10,000 -- the exact corruption the old type would force
    problems = _reconcile_with(total_weight_bps=BPS_DENOMINATOR)
    assert any("total_weight_bps" in p for p in problems), problems

    problems = _reconcile_with(clamped_probability_bps=outbreak.clamped_probability_bps + 1)
    assert any("clamped_probability_bps" in p for p in problems), problems

    assert outbreak.selection_draw is not None
    problems = _reconcile_with(selection_draw=outbreak.selection_draw + 1)
    assert any("selection_draw" in p for p in problems), problems


# --- item 8: saturation -- the total stays unclamped while the probability pins at 10,000 -----

# 700 bps of scale means probability saturates at total >= ceil(10_000 * 10_000 / 700) = 142,858.
# Fifteen maximal (10,000-weight) dyads total 150,000, clearing it; fourteen would not.
_SATURATING_DYAD_COUNT = 15


def _saturating_pairs() -> tuple[tuple[str, str], ...]:
    return tuple((f"c{i:02d}a", f"c{i:02d}b") for i in range(_SATURATING_DYAD_COUNT))


def _saturating_state(seed: int) -> GameState:
    pairs = _saturating_pairs()
    return make_game_state(
        seed=seed,
        foreign_profiles={name: _profile() for pair in pairs for name in pair},
        dyads=tuple(
            _dyad(a, b, tension=BPS_DENOMINATOR, grievance=BPS_DENOMINATOR) for a, b in pairs
        ),
    )


def test_at_saturation_the_total_stays_unclamped_and_the_probability_pins_at_certainty() -> None:
    state = _saturating_state(DECLARED_SEEDS[0])
    resolution = resolve_turn(state, _empty_decisions(state))
    assert resolution.report.foreign_affairs is not None
    outbreak = resolution.report.foreign_affairs.outbreak

    assert len(outbreak.candidates) == _SATURATING_DYAD_COUNT
    assert outbreak.total_weight_bps == _SATURATING_DYAD_COUNT * BPS_DENOMINATOR == 150_000
    assert outbreak.total_weight_bps > 142_857, "sanity: this must be past the saturation point"
    assert outbreak.clamped_probability_bps == BPS_DENOMINATOR
    assert outbreak.occurred, "at certainty a war must start whatever the occurrence draw was"

    # the weighted pick still ran over the FULL total, not a clamped one
    assert outbreak.selection_draw is not None
    assert 0 <= outbreak.selection_draw < outbreak.total_weight_bps
    weights = tuple(
        row.raw_dyad_weight_bps for row in outbreak.candidates if row.passed_pressure_floor
    )
    expected_index = select_candidate_index(
        selection_draw=outbreak.selection_draw, weights_bps=weights
    )
    expected_row = [row for row in outbreak.candidates if row.passed_pressure_floor][expected_index]
    assert (outbreak.selected_country_a, outbreak.selected_country_b) == (
        expected_row.country_a,
        expected_row.country_b,
    )

    problems = reconcile_foreign_affairs_report(
        opening_state=state, closing_state=resolution.state, report=resolution.report
    )
    assert problems == []


# --- item 9: the live-conflict cap is independent of the candidate count ----------------------


def test_the_concurrency_cap_is_independent_of_how_many_candidates_there_are() -> None:
    """Fifteen saturating dyads means a war opens every single turn it is permitted to -- yet the
    global cap still holds at two. Candidate count drives WHICH war starts, never HOW MANY may
    run at once."""
    for seed in DECLARED_SEEDS:
        state = _saturating_state(seed)
        max_live = 0
        max_candidates = 0
        for _ in range(60):
            resolution = resolve_turn(state, _empty_decisions(state))
            assert resolution.report.foreign_affairs is not None
            max_candidates = max(
                max_candidates, len(resolution.report.foreign_affairs.outbreak.candidates)
            )
            state = resolution.state
            live = sum(
                1
                for conflict in state.world.conflicts
                if conflict.status in (ConflictStatus.ACTIVE, ConflictStatus.CEASEFIRE)
            )
            assert live <= MAX_CONCURRENT_CONFLICTS, f"seed {seed}: {live} live conflicts"
            max_live = max(max_live, live)
        assert max_live == MAX_CONCURRENT_CONFLICTS, (
            f"seed {seed}: sanity -- saturating pressure never even reached the cap "
            f"(max_live={max_live})"
        )
        assert max_candidates > MAX_CONCURRENT_CONFLICTS, (
            f"seed {seed}: sanity -- the candidate count must exceed the cap for this test to "
            f"say anything (max_candidates={max_candidates})"
        )


# --- item 10: shipped content is provably untouched by the widening ---------------------------


def test_no_shipped_scenario_can_reach_the_widened_regime() -> None:
    """The widening cannot alter shipped behaviour: every shipped scenario authors at most one
    dyad, so its total can never exceed a single clamped weight of 10,000 and every value the old
    `StrictBps` domain admitted is still admitted identically. Byte-identical shipped histories
    are pinned separately by `test_foreign_conflict_integration_soak.py`."""
    from app.content.scenarios import load_scenario_file
    from tests.conftest import SCENARIO_DIR

    for scenario in ("tiny_valid.yaml", "decree_state.yaml", "deficit_demo.yaml"):
        state = load_scenario_file(SCENARIO_DIR / scenario)
        assert len(state.world.dyads) <= 1, (
            f"{scenario} authors {len(state.world.dyads)} dyads; this test's premise -- and the "
            "claim that the widening is inert for shipped content -- would need re-checking"
        )
        turns_checked = 0
        for _ in range(40):
            try:
                resolution = resolve_turn(state, _empty_decisions(state))
            except GameAlreadyConcludedError:
                break  # a shipped campaign may end on term limits well before turn 40
            assert resolution.report.foreign_affairs is not None
            assert resolution.report.foreign_affairs.outbreak.total_weight_bps <= BPS_DENOMINATOR, (
                f"{scenario} reached the widened regime; shipped byte-identity is not guaranteed"
            )
            state = resolution.state
            turns_checked += 1
        assert turns_checked > 0, f"{scenario} resolved no turns at all"
