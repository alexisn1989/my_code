"""External Wars W1 commit 9: durable calibration regression tests.

Pins the CORRECTED, production-native calibration measurements described in
`docs/plans/external-wars-w1-calibration-erratum.md` -- NOT the frozen plan's original §10
literals, which that erratum documents as measured by a driver with a 1-based turn-indexing
defect (against the turn-keyed `derive_rng`) and a floor-run counter that never reset across
ceasefire excursions. Constants, formulas, scenario content and schemas are unchanged; only the
measurement basis differs (turns 0..H-1, not 1..H; a floor run resets on every non-floor closing
state, including `CEASEFIRE`).

Every measurement here is reproduced with `foreign_conflict_calibration_helpers.run_calibration`,
an isolated harness that performs turn iteration and per-conflict status dispatch only -- every
arithmetic step calls a real production function, never a reimplemented formula.
`TestCalibrationHarnessParity` proves that harness reproduces `resolve_turn`'s own foreign-affairs
output byte-for-byte before anything else in this file relies on it.

Raw integer facts only: never a rounded percentage or a binary-float equality. Completed and
right-censored (still `ACTIVE`/`CEASEFIRE` at the horizon) conflicts are kept strictly separate --
an unresolved conflict is never counted as completed.
"""

from __future__ import annotations

import statistics
import time

import pytest

from app.content.scenarios import load_scenario_file
from app.core.errors import GameAlreadyConcludedError
from app.simulation import foreign_conflict as fc
from app.simulation.decisions import DecisionSet
from app.simulation.legitimacy import MAX_SECURITY_CONTRIBUTION_BPS
from app.simulation.resolver import resolve_turn
from app.simulation.state import ConflictDyadState, ForeignProfileState
from tests.conftest import SCENARIO_DIR, make_game_state
from tests.foreign_conflict_calibration_helpers import run_calibration

CALIBRATION_SEEDS = (42, 1337, 20260826, 7, 99991)
SCENARIO_FILES = ("tiny_valid.yaml", "decree_state.yaml", "deficit_demo.yaml")
LIVE_STATUSES = (fc.ConflictStatus.ACTIVE, fc.ConflictStatus.CEASEFIRE)


def _empty_decisions_for(state) -> DecisionSet:  # type: ignore[no-untyped-def]
    return DecisionSet(
        expected_turn=state.turn, expected_state_version=state.state_version, decisions=[]
    )


def _conflict_key(c):  # type: ignore[no-untyped-def]
    return (
        c.conflict_id,
        c.country_a,
        c.country_b,
        c.status.value,
        c.intensity_bps,
        c.position_bps,
        c.exhaustion_a_bps,
        c.exhaustion_b_bps,
        c.negotiation_readiness_bps,
        c.ceasefire_run_turns,
        c.resolved_turn,
        c.opened_turn,
        c.war_capability_a_bps,
        c.war_capability_b_bps,
    )


class TestCalibrationHarnessParity:
    """Proves the isolated harness (`run_calibration`) matches `resolve_turn`'s own foreign-affairs
    output exactly, on every turn available before an unrelated campaign-terminal outcome ends the
    real resolver early. Every other test in this file trusts the harness only because this test
    passes."""

    def test_harness_matches_resolve_turn_on_every_reachable_turn(self) -> None:
        for scenario in SCENARIO_FILES:
            for seed in CALIBRATION_SEEDS:
                base = load_scenario_file(SCENARIO_DIR / scenario).model_copy(update={"seed": seed})
                real: list[dict[str, object]] = []
                state = base
                for _ in range(80):
                    try:
                        res = resolve_turn(state, _empty_decisions_for(state))
                    except GameAlreadyConcludedError:
                        break
                    fa = res.report.foreign_affairs
                    assert fa is not None
                    pol = res.report.political
                    real.append(
                        {
                            "turn": state.turn,
                            "occurrence_draw": fa.outbreak.occurrence_draw,
                            "occurred": fa.outbreak.occurred,
                            "selection_draw": fa.outbreak.selection_draw,
                            "conflict_id": fa.outbreak.conflict_id,
                            "security": pol.security_contribution_bps if pol else 0,
                            "conflicts": tuple(_conflict_key(c) for c in res.state.world.conflicts),
                            "progressions": tuple(
                                (
                                    r.conflict_id,
                                    r.opening_status.value,
                                    r.closing_status.value,
                                    r.closing_intensity_bps,
                                    r.active_intensity_floor_applied,
                                )
                                for r in fa.progressions
                            ),
                        }
                    )
                    state = res.state

                assert real, f"{scenario} seed={seed}: real resolver produced zero turns"
                traces = run_calibration(base, turns=len(real))
                for i, (expected, trace) in enumerate(zip(real, traces, strict=True)):
                    got = {
                        "turn": trace.turn,
                        "occurrence_draw": trace.occurrence_draw,
                        "occurred": trace.occurred,
                        "selection_draw": trace.selection_draw,
                        "conflict_id": trace.opened_conflict_id,
                        "security": trace.security_contribution_bps,
                        "conflicts": tuple(_conflict_key(c) for c in trace.conflicts),
                        "progressions": trace.progressions,
                    }
                    assert got == expected, (
                        f"{scenario} seed={seed} turn_idx={i}: harness diverges from resolve_turn"
                    )


def _measure(*, horizon: int, start_turn: int = 0) -> dict[str, object]:
    """Corrected production-native measurement across all scenarios/seeds at one horizon.
    Continuous-floor-run definition (erratum §1, defect 2): increments only while closing status
    is ACTIVE and closing intensity equals MIN_ACTIVE_INTENSITY_BPS exactly; resets otherwise."""
    runs = total = quiet = 0
    completed: list[int] = []
    censored: list[int] = []
    status_counts = {"decided": 0, "settled": 0, "active": 0, "ceasefire": 0}
    breakdowns = maturations = 0
    intensities: list[int] = []
    floor_binds = 0
    floor_run_max = 0
    max_concurrency = 0
    below_floor_active_closes = 0

    for scenario in SCENARIO_FILES:
        for seed in CALIBRATION_SEEDS:
            runs += 1
            base = load_scenario_file(SCENARIO_DIR / scenario).model_copy(
                update={"seed": seed, "turn": start_turn}
            )
            traces = run_calibration(base, turns=horizon)
            seen: dict[str, object] = {}
            floor_run: dict[str, int] = {}
            last_turn = traces[-1].turn
            for trace in traces:
                max_concurrency = max(
                    max_concurrency,
                    sum(1 for c in trace.conflicts if c.status in LIVE_STATUSES),
                )
                for conflict_id, opening, closing, intensity, floor_applied in trace.progressions:
                    intensities.append(intensity)
                    if floor_applied:
                        floor_binds += 1
                    if closing == "active" and intensity < fc.MIN_ACTIVE_INTENSITY_BPS:
                        below_floor_active_closes += 1
                    if closing == "active" and intensity == fc.MIN_ACTIVE_INTENSITY_BPS:
                        floor_run[conflict_id] = floor_run.get(conflict_id, 0) + 1
                        floor_run_max = max(floor_run_max, floor_run[conflict_id])
                    else:
                        floor_run[conflict_id] = 0
                    if opening == "ceasefire" and closing == "active":
                        breakdowns += 1
                    if opening == "ceasefire" and closing == "settled":
                        maturations += 1
                for c in trace.conflicts:
                    seen[c.conflict_id] = c
            if not seen:
                quiet += 1
            total += len(seen)
            for c in seen.values():  # type: ignore[assignment]
                if c.status in LIVE_STATUSES:  # type: ignore[attr-defined]
                    censored.append(last_turn - c.opened_turn + 1)  # type: ignore[attr-defined]
                else:
                    completed.append(c.resolved_turn - c.opened_turn + 1)  # type: ignore[attr-defined]
                status_counts[c.status.value] += 1  # type: ignore[attr-defined]

    completed.sort()
    censored.sort()
    return dict(
        runs=runs,
        total=total,
        quiet=quiet,
        completed=completed,
        censored=censored,
        status_counts=status_counts,
        breakdowns=breakdowns,
        maturations=maturations,
        intensity_min=min(intensities),
        intensity_max=max(intensities),
        intensity_median=int(statistics.median(intensities)),
        floor_binds=floor_binds,
        floor_run_max=floor_run_max,
        max_concurrency=max_concurrency,
        below_floor_active_closes=below_floor_active_closes,
    )


class TestCorrectedCalibrationMeasurements:
    """Pins the corrected §10.2-§10.4 measurements (erratum §3) at both horizons."""

    def test_horizon_40_outbreak_frequency_and_campaign_shape(self) -> None:
        m = _measure(horizon=40)
        assert m["runs"] == 15
        assert m["total"] == 16
        assert m["quiet"] == 2

    def test_horizon_80_outbreak_frequency_and_campaign_shape(self) -> None:
        m = _measure(horizon=80)
        assert m["runs"] == 15
        assert m["total"] == 26
        assert m["quiet"] == 0

    def test_horizon_40_durations_completed_vs_right_censored(self) -> None:
        m = _measure(horizon=40)
        completed = m["completed"]
        censored = m["censored"]
        assert len(completed) == 5
        assert (completed[0], completed[len(completed) // 2], completed[-1]) == (14, 15, 37)
        assert len(censored) == 11
        assert (censored[0], censored[-1]) == (1, 40)

    def test_horizon_80_durations_completed_vs_right_censored(self) -> None:
        m = _measure(horizon=80)
        completed = m["completed"]
        censored = m["censored"]
        assert len(completed) == 15
        assert (completed[0], completed[len(completed) // 2], completed[-1]) == (14, 15, 68)
        assert len(censored) == 11
        assert (censored[0], censored[-1]) == (4, 80)

    def test_opened_by_40_terminal_by_80_cohort(self) -> None:
        opened_by_40 = terminal_by_80 = 0
        for scenario in SCENARIO_FILES:
            for seed in CALIBRATION_SEEDS:
                base = load_scenario_file(SCENARIO_DIR / scenario).model_copy(
                    update={"seed": seed, "turn": 0}
                )
                seen: dict[str, object] = {}
                for trace in run_calibration(base, turns=80):
                    for c in trace.conflicts:
                        seen[c.conflict_id] = c
                for c in seen.values():
                    if c.opened_turn < 40:  # type: ignore[attr-defined]
                        opened_by_40 += 1
                        if c.status not in LIVE_STATUSES:  # type: ignore[attr-defined]
                            terminal_by_80 += 1
        assert opened_by_40 == 16
        assert terminal_by_80 == 11
        # raw-integer form of the >=50% acceptance requirement, no float equality
        assert terminal_by_80 * 100 >= 50 * opened_by_40

    def test_horizon_40_status_ceasefire_and_intensity(self) -> None:
        m = _measure(horizon=40)
        sc = m["status_counts"]
        assert (sc["decided"], sc["settled"], sc["active"], sc["ceasefire"]) == (1, 4, 10, 1)
        assert m["breakdowns"] == 8
        assert m["maturations"] == 4
        assert (m["intensity_min"], m["intensity_median"], m["intensity_max"]) == (58, 2895, 6215)
        assert m["floor_binds"] == 93
        assert m["floor_run_max"] == 23
        assert m["below_floor_active_closes"] == 0
        assert m["max_concurrency"] == 1

    def test_horizon_80_status_ceasefire_and_intensity(self) -> None:
        m = _measure(horizon=80)
        sc = m["status_counts"]
        assert (sc["decided"], sc["settled"], sc["active"], sc["ceasefire"]) == (4, 11, 10, 1)
        assert m["breakdowns"] == 21
        assert m["maturations"] == 11
        assert (m["intensity_min"], m["intensity_median"], m["intensity_max"]) == (7, 547, 6215)
        assert m["floor_binds"] == 337
        assert m["floor_run_max"] == 31
        assert m["below_floor_active_closes"] == 0
        assert m["max_concurrency"] == 1

    def test_floor_run_is_disclosed_not_absorbing(self) -> None:
        """§10.8: exhaustion still accrues at the floor, so the long floor run is not the removed
        absorbing state. trunc_div(500 * 1200 / 10_000) = 60 bps/turn."""
        from app.core.politics import trunc_div_toward_zero

        gain = trunc_div_toward_zero(fc.MIN_ACTIVE_INTENSITY_BPS * fc.EXHAUSTION_RATE_BPS, 10_000)
        assert gain == 60
        assert gain > 0


class TestUnchangedCalibrationCategories:
    """Categories the corrected measurement re-confirms unchanged from frozen §10.5-§10.6."""

    def test_security_anxiety_distribution(self) -> None:
        expected = {
            "tiny_valid.yaml": (2000, -71, -63, -6),
            "decree_state.yaml": (3000, -111, -9, -9),
            "deficit_demo.yaml": (2000, -72, -6, -6),
        }
        for scenario, (exposure, exp_min, exp_med, exp_max) in expected.items():
            values: list[int] = []
            for seed in CALIBRATION_SEEDS:
                base = load_scenario_file(SCENARIO_DIR / scenario).model_copy(
                    update={"seed": seed, "turn": 0}
                )
                for trace in run_calibration(base, turns=80):
                    if trace.security_contribution_bps != 0:
                        values.append(trace.security_contribution_bps)
            assert values, scenario
            assert all(v <= 0 for v in values)
            assert min(values) == exp_min
            assert int(statistics.median(values)) == exp_med
            assert max(values) == exp_max
            caps = sum(1 for v in values if v == -MAX_SECURITY_CONTRIBUTION_BPS)
            assert caps == 0
            # sanity: the exposure this table is keyed by is the scenario's shipped exposure
            world = base.world
            exposures = {d.player_security_exposure_bps for d in world.dyads}
            assert exposures == {exposure}

    def test_zero_exposure_control_is_always_exactly_zero(self) -> None:
        base = load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml")
        zeroed = base.model_copy(
            update={
                "world": base.world.model_copy(
                    update={
                        "dyads": tuple(
                            d.model_copy(update={"player_security_exposure_bps": 0})
                            for d in base.world.dyads
                        )
                    }
                )
            }
        )
        values = [
            trace.security_contribution_bps
            for seed in CALIBRATION_SEEDS
            for trace in run_calibration(
                zeroed.model_copy(update={"seed": seed, "turn": 0}), turns=80
            )
        ]
        assert values
        assert set(values) == {0}

    def test_low_pressure_control_yields_zero_conflicts_structurally(self) -> None:
        base = load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml")
        control = base.model_copy(
            update={
                "world": base.world.model_copy(
                    update={
                        "dyads": tuple(
                            d.model_copy(update={"tension_bps": 200, "grievance_bps": 0})
                            for d in base.world.dyads
                        )
                    }
                )
            }
        )
        weight = fc.dyad_weight_bps(tension_bps=200, grievance_bps=0)
        assert weight == 100
        assert weight < fc.MIN_OUTBREAK_WEIGHT_BPS
        for horizon in (40, 80):
            total = 0
            for seed in CALIBRATION_SEEDS:
                seen: set[str] = set()
                for trace in run_calibration(
                    control.model_copy(update={"seed": seed, "turn": 0}), turns=horizon
                ):
                    for c in trace.conflicts:
                        seen.add(c.conflict_id)
                total += len(seen)
            assert total == 0

    def test_pressure_floor_boundary_499_500(self) -> None:
        assert fc.passes_pressure_floor(raw_weight_bps=499) is False
        assert fc.passes_pressure_floor(raw_weight_bps=500) is True

    def test_shipped_scenario_weights_and_concurrency(self) -> None:
        weights = {
            "tiny_valid.yaml": 8000,
            "decree_state.yaml": 9000,
            "deficit_demo.yaml": 8000,
        }
        for scenario, expected_weight in weights.items():
            base = load_scenario_file(SCENARIO_DIR / scenario)
            (dyad,) = base.world.dyads
            weight = fc.dyad_weight_bps(
                tension_bps=dyad.tension_bps, grievance_bps=dyad.grievance_bps
            )
            assert weight == expected_weight
        for scenario in SCENARIO_FILES:
            max_concurrent = 0
            for seed in CALIBRATION_SEEDS:
                base = load_scenario_file(SCENARIO_DIR / scenario).model_copy(
                    update={"seed": seed, "turn": 0}
                )
                for trace in run_calibration(base, turns=80):
                    max_concurrent = max(
                        max_concurrent,
                        sum(1 for c in trace.conflicts if c.status in LIVE_STATUSES),
                    )
            assert max_concurrent == 1

    def test_synthetic_multi_dyad_concurrency_never_exceeds_the_cap(self) -> None:
        profiles = {
            name: ForeignProfileState(display_name=name, war_capability_bps=5000)
            for name in ("kessia", "vetruska", "marnil", "sorrend", "tolvane")
        }

        def dyad(a: str, b: str, tension: int, grievance: int, exposure: int) -> ConflictDyadState:
            return ConflictDyadState(
                country_a=a,
                country_b=b,
                aggressor=b,
                defender=a,
                aim_a=fc.WarAim.DETERRENCE,
                aim_b=fc.WarAim.TERRITORIAL,
                eligible=True,
                player_security_exposure_bps=exposure,
                tension_bps=tension,
                grievance_bps=grievance,
            )

        synthetic_dyads = (
            dyad("kessia", "vetruska", 8500, 7500, 2000),
            dyad("marnil", "sorrend", 9500, 8500, 3000),
            dyad("marnil", "tolvane", 9000, 7000, 2000),
        )
        max_concurrent = 0
        total = 0
        for seed in CALIBRATION_SEEDS:
            state = make_game_state(seed=seed, foreign_profiles=profiles, dyads=synthetic_dyads)
            seen: set[str] = set()
            for trace in run_calibration(state, turns=80):
                max_concurrent = max(
                    max_concurrent, sum(1 for c in trace.conflicts if c.status in LIVE_STATUSES)
                )
                for c in trace.conflicts:
                    seen.add(c.conflict_id)
            total += len(seen)
        assert total == 29
        assert max_concurrent == 2
        assert max_concurrent <= fc.MAX_CONCURRENT_CONFLICTS

    def test_determinism_rerun_is_byte_identical(self) -> None:
        def trace_key(base, seed: int, horizon: int, start_turn: int = 0):  # type: ignore[no-untyped-def]
            b = base.model_copy(update={"seed": seed, "turn": start_turn})
            return [
                (
                    t.turn,
                    t.occurrence_draw,
                    t.occurred,
                    t.selection_draw,
                    t.opened_conflict_id,
                    t.security_contribution_bps,
                    tuple(
                        sorted(
                            (
                                c.conflict_id,
                                c.status.value,
                                c.intensity_bps,
                                c.position_bps,
                                c.exhaustion_a_bps,
                                c.negotiation_readiness_bps,
                                c.ceasefire_run_turns,
                                c.resolved_turn,
                            )
                            for c in t.conflicts
                        )
                    ),
                )
                for t in run_calibration(b, turns=horizon)
            ]

        for scenario in SCENARIO_FILES:
            base = load_scenario_file(SCENARIO_DIR / scenario)
            for seed in CALIBRATION_SEEDS:
                first = trace_key(base, seed, 80)
                second = trace_key(base, seed, 80)
                assert first == second

    def test_save_reload_at_turn_40_matches_uninterrupted_run(self) -> None:
        for scenario in SCENARIO_FILES:
            base = load_scenario_file(SCENARIO_DIR / scenario)
            for seed in CALIBRATION_SEEDS:
                seeded = base.model_copy(update={"seed": seed, "turn": 0})

                def summarize(traces):  # type: ignore[no-untyped-def]
                    return [
                        (
                            t.turn,
                            t.occurrence_draw,
                            t.occurred,
                            t.selection_draw,
                            t.opened_conflict_id,
                            t.security_contribution_bps,
                            tuple(
                                sorted(
                                    (
                                        c.conflict_id,
                                        c.status.value,
                                        c.intensity_bps,
                                        c.position_bps,
                                        c.exhaustion_a_bps,
                                        c.negotiation_readiness_bps,
                                        c.ceasefire_run_turns,
                                        c.resolved_turn,
                                    )
                                    for c in t.conflicts
                                )
                            ),
                        )
                        for t in traces
                    ]

                uninterrupted = summarize(run_calibration(seeded, turns=80))

                first_half = run_calibration(seeded, turns=40)
                mid_conflicts = first_half[-1].conflicts
                continued_state = seeded.model_copy(
                    update={
                        "turn": 40,
                        "world": seeded.world.model_copy(update={"conflicts": mid_conflicts}),
                    }
                )
                split = summarize(first_half) + summarize(
                    run_calibration(continued_state, turns=40)
                )
                assert split == uninterrupted


# The four constants the frozen plan's grid sweeps. None is a parameter of any production
# function -- each is read as a module global inside the function body -- so sweeping them
# requires the narrow, explicitly authorized `pytest.MonkeyPatch.context()` exception below,
# restored after every one of the 240 cells.
_GRID_FLOORS = (250, 500, 750, 1000, 1250)
_GRID_RECOVERIES = (200, 300, 400, 500)
_GRID_BREAKDOWNS = (3500, 4000, 4500, 5000)
_GRID_DURABILITIES = (3, 4, 5)


def _evaluate_grid_cell(floor: int) -> tuple[bool, dict[str, bool]]:
    """One grid cell. Constants are already patched by the caller. Horizon 80, turns 0-79,
    corrected floor-run definition is not needed here (the grid's own criteria don't use it)."""
    cf_to_active = cf_to_settled = decided = settled = active = ceasefire = 0
    below_floor = stalled = ge_10_turns = 0
    opened_by_40 = terminal_by_80 = 0
    for scenario in SCENARIO_FILES:
        for seed in CALIBRATION_SEEDS:
            base = load_scenario_file(SCENARIO_DIR / scenario).model_copy(
                update={"seed": seed, "turn": 0}
            )
            traces = run_calibration(base, turns=80)
            seen: dict[str, object] = {}
            prev_exhaustion: dict[str, tuple[int, int]] = {}
            last_turn = traces[-1].turn
            for trace in traces:
                for _conflict_id, opening, closing, intensity, _floor_applied in trace.progressions:
                    if closing == "active" and intensity < floor:
                        below_floor += 1
                    if opening == "ceasefire" and closing == "active":
                        cf_to_active += 1
                    if opening == "ceasefire" and closing == "settled":
                        cf_to_settled += 1
                for c in trace.conflicts:
                    if c.status is fc.ConflictStatus.ACTIVE and c.conflict_id in prev_exhaustion:
                        pa, _pb = prev_exhaustion[c.conflict_id]
                        if c.exhaustion_a_bps == pa and pa < 10000:
                            stalled += 1
                    prev_exhaustion[c.conflict_id] = (c.exhaustion_a_bps, c.exhaustion_b_bps)
                    seen[c.conflict_id] = c
            for c in seen.values():  # type: ignore[assignment]
                if c.status in LIVE_STATUSES:  # type: ignore[attr-defined]
                    duration = last_turn - c.opened_turn + 1  # type: ignore[attr-defined]
                    if c.status is fc.ConflictStatus.ACTIVE:  # type: ignore[attr-defined]
                        active += 1
                    else:
                        ceasefire += 1
                else:
                    duration = c.resolved_turn - c.opened_turn + 1  # type: ignore[attr-defined]
                    if c.status is fc.ConflictStatus.DECIDED:  # type: ignore[attr-defined]
                        decided += 1
                    else:
                        settled += 1
                if duration >= 10:
                    ge_10_turns += 1
                if c.opened_turn < 40:  # type: ignore[attr-defined]
                    opened_by_40 += 1
                    if c.status not in LIVE_STATUSES:  # type: ignore[attr-defined]
                        terminal_by_80 += 1
    criteria = {
        "no_indefinite_ceasefire": ceasefire == 0,
        "cf_to_settled_witness": cf_to_settled >= 1,
        "settled_reachable": settled >= 1,
        "terminal_ge_50pct": terminal_by_80 * 100 >= 50 * opened_by_40 if opened_by_40 else False,
        "decided_reachable": decided >= 1,
        "cf_to_active_witness": cf_to_active >= 1,
        "zero_below_floor": below_floor == 0,
        "zero_stalled": stalled == 0,
        "ten_turn_witness": ge_10_turns >= 1,
    }
    return all(criteria.values()), criteria


class TestCalibrationGrid:
    """The corrected 240-configuration grid (erratum §5): production-native turns 0-79. Pins the
    corrected passing set exactly, and separately pins the shipped configuration's own criteria
    as a documented-exception regression guard, so any future drift -- it starts passing, or a
    second criterion starts failing -- is caught rather than silently absorbed."""

    def test_240_cells_evaluated_and_the_corrected_passing_set_is_exact(self) -> None:
        cells_evaluated = 0
        passing: list[tuple[int, int, int, int]] = []
        for floor in _GRID_FLOORS:
            for recovery in _GRID_RECOVERIES:
                for breakdown in _GRID_BREAKDOWNS:
                    for durability in _GRID_DURABILITIES:
                        with pytest.MonkeyPatch.context() as mp:
                            mp.setattr(fc, "MIN_ACTIVE_INTENSITY_BPS", floor)
                            mp.setattr(fc, "CEASEFIRE_RECOVERY_BPS", recovery)
                            mp.setattr(fc, "CEASEFIRE_BREAKDOWN_BPS", breakdown)
                            mp.setattr(fc, "CEASEFIRE_DURABILITY_TURNS", durability)
                            ok, _criteria = _evaluate_grid_cell(floor)
                        cells_evaluated += 1
                        if ok:
                            passing.append((floor, recovery, breakdown, durability))

        assert cells_evaluated == 240
        # constants must be restored to the shipped values after every cell
        assert fc.MIN_ACTIVE_INTENSITY_BPS == 500
        assert fc.CEASEFIRE_RECOVERY_BPS == 300
        assert fc.CEASEFIRE_BREAKDOWN_BPS == 4000
        assert fc.CEASEFIRE_DURABILITY_TURNS == 4

        assert passing == [
            (250, 300, 4000, 4),
            (250, 400, 3500, 4),
            (500, 400, 3500, 4),
            (750, 400, 3500, 4),
            (1000, 400, 3500, 4),
            (1250, 300, 4000, 4),
            (1250, 400, 4000, 3),
        ]
        assert (500, 300, 4000, 4) not in passing

    def test_shipped_configuration_is_a_documented_exception(self) -> None:
        """(500, 300, 4000, 4) is the constants shipped in production today (unchanged by this
        erratum). Under the corrected measurement it fails exactly one criterion --
        `no_indefinite_ceasefire` -- and passes every other one, including both floor-safety
        criteria. Ship it anyway, disclosed: this test guards that exact, narrow shape of failure
        so any change to it (it starts passing, or a second criterion starts failing) is caught."""
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(fc, "MIN_ACTIVE_INTENSITY_BPS", 500)
            mp.setattr(fc, "CEASEFIRE_RECOVERY_BPS", 300)
            mp.setattr(fc, "CEASEFIRE_BREAKDOWN_BPS", 4000)
            mp.setattr(fc, "CEASEFIRE_DURABILITY_TURNS", 4)
            ok, criteria = _evaluate_grid_cell(500)

        assert fc.MIN_ACTIVE_INTENSITY_BPS == 500
        assert fc.CEASEFIRE_RECOVERY_BPS == 300
        assert fc.CEASEFIRE_BREAKDOWN_BPS == 4000
        assert fc.CEASEFIRE_DURABILITY_TURNS == 4

        assert ok is False
        assert criteria["no_indefinite_ceasefire"] is False
        for name, passed in criteria.items():
            if name == "no_indefinite_ceasefire":
                continue
            assert passed is True, f"unexpected additional failure: {name}"

    def test_zero_below_floor_and_zero_stalled_across_all_240(self) -> None:
        """Restated from the previous test's own per-cell criteria for a focused, independently
        readable regression: across every one of the 240 cells, no closing-ACTIVE conflict ever
        closes below that cell's own floor, and no ACTIVE conflict below full exhaustion ever
        stops progressing."""
        for floor in _GRID_FLOORS:
            for recovery in _GRID_RECOVERIES:
                for breakdown in _GRID_BREAKDOWNS:
                    for durability in _GRID_DURABILITIES:
                        with pytest.MonkeyPatch.context() as mp:
                            mp.setattr(fc, "MIN_ACTIVE_INTENSITY_BPS", floor)
                            mp.setattr(fc, "CEASEFIRE_RECOVERY_BPS", recovery)
                            mp.setattr(fc, "CEASEFIRE_BREAKDOWN_BPS", breakdown)
                            mp.setattr(fc, "CEASEFIRE_DURABILITY_TURNS", durability)
                            _ok, criteria = _evaluate_grid_cell(floor)
                        assert criteria["zero_below_floor"] is True
                        assert criteria["zero_stalled"] is True


class TestCalibrationPerformance:
    """Measured and reported, not pinned as a brittle timing equality (frozen plan sec.13)."""

    def test_full_calibration_completes_within_a_generous_budget(self) -> None:
        start = time.time()
        for scenario in SCENARIO_FILES:
            for seed in CALIBRATION_SEEDS:
                base = load_scenario_file(SCENARIO_DIR / scenario).model_copy(
                    update={"seed": seed, "turn": 0}
                )
                run_calibration(base, turns=80)
        elapsed = time.time() - start
        assert elapsed < 30.0, f"15-run 80-turn calibration took {elapsed:.2f}s, expected < 30s"
