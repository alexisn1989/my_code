"""Fix-forward 6b: the global concurrency cap, `MAX_CONCURRENT_CONFLICTS` (frozen plan sec.10.1,
measured sec.10.5). Commit 6a's integration soak and the 6b checkpoint audit both surfaced that
no such cap existed in the engine despite being specified in the plan; this file proves the
guard `phases._resolve_foreign_conflict_outbreak` now applies (see that function's own updated
docstring for the exact mechanism) against a SYNTHETIC multi-dyad fixture -- no shipped scenario
authors more than one dyad (verified directly against the YAML content), so shipped content can
never exercise concurrency above 1 and this fixture is the only way to reach the cap at all.

Declared seeds for every test below, before any run: 42, 1337, 20260826, 7, 99991 -- the same
set the frozen plan's sec.21 calibration declares, reused here rather than a fresh set chosen
after observing results.
"""

from __future__ import annotations

from app.core.errors import GameAlreadyConcludedError
from app.simulation.decisions import DecisionSet
from app.simulation.foreign_conflict import MAX_CONCURRENT_CONFLICTS, ConflictStatus, WarAim
from app.simulation.history import advance_game, new_game
from app.simulation.resolver import resolve_turn
from app.simulation.save_format import SAVE_FORMAT_VERSION, dump_save_json, load_save_json
from app.simulation.state import ConflictDyadState, ForeignConflictState, ForeignProfileState
from tests.conftest import make_game_state

DECLARED_SEEDS = (42, 1337, 20260826, 7, 99991)

# Pressure per dyad, chosen so occurrence is frequent AND so all three dyads' weights can be
# simultaneously eligible without the outbreak report's own total_weight_bps (StrictBps, capped
# at 10,000) overflowing before any war has started and removed a dyad from candidacy: weight =
# clamp_bps(trunc_div(tension+grievance, 2)) = 3,000 per dyad, summing to 9,000 for all three.
_HIGH_PRESSURE = {"tension_bps": 3_000, "grievance_bps": 3_000}


def _profile(capability: int = 5_000) -> ForeignProfileState:
    return ForeignProfileState(display_name="Profile", war_capability_bps=capability)


def _dyad(country_a: str, country_b: str) -> ConflictDyadState:
    return ConflictDyadState(
        country_a=country_a,
        country_b=country_b,
        aggressor=country_a,
        defender=country_b,
        aim_a=WarAim.DETERRENCE,
        aim_b=WarAim.TERRITORIAL,
        eligible=True,
        player_security_exposure_bps=0,
        **_HIGH_PRESSURE,
    )


def _conflict(
    country_a: str, country_b: str, *, status: ConflictStatus, resolved_turn: int | None = None
) -> ForeignConflictState:
    return ForeignConflictState(
        conflict_id=f"{country_a}__{country_b}__t0",
        country_a=country_a,
        country_b=country_b,
        aggressor=country_a,
        defender=country_b,
        war_capability_a_bps=5_000,
        war_capability_b_bps=5_000,
        aim_a=WarAim.DETERRENCE,
        aim_b=WarAim.TERRITORIAL,
        opened_turn=0,
        intensity_bps=3_000,
        position_bps=0,
        exhaustion_a_bps=0,
        exhaustion_b_bps=0,
        negotiation_readiness_bps=0,
        status=status,
        resolved_turn=resolved_turn,
    )


_PAIR_A = ("alpha", "beta")
_PAIR_B = ("delta", "gamma")
_PAIR_C = ("epsilon", "zeta")
_ALL_COUNTRIES = ("alpha", "beta", "delta", "gamma", "epsilon", "zeta")
_PROFILES = {name: _profile() for name in _ALL_COUNTRIES}


def _empty_decisions(state):  # type: ignore[no-untyped-def]
    return DecisionSet(expected_turn=state.turn, expected_state_version=state.state_version)


def _fixture_state(*, seed: int, conflicts=(), dyads=()):  # type: ignore[no-untyped-def]
    return make_game_state(seed=seed, foreign_profiles=_PROFILES, dyads=dyads, conflicts=conflicts)


# --- items 1-2: candidate admission at and below the cap ------------------------------------


def test_live_count_one_permits_another_outbreak_candidate() -> None:
    """One live conflict on pair A, plus a fresh eligible dyad on pair B: with `live_count=1 <
    MAX_CONCURRENT_CONFLICTS`, dyad B must be admitted as a candidate."""
    state = _fixture_state(
        seed=DECLARED_SEEDS[0],
        conflicts=(_conflict(*_PAIR_A, status=ConflictStatus.ACTIVE),),
        dyads=(_dyad(*_PAIR_B),),
    )
    report = resolve_turn(state, _empty_decisions(state)).report
    assert report.foreign_affairs is not None
    candidate_pairs = {
        (row.country_a, row.country_b) for row in report.foreign_affairs.outbreak.candidates
    }
    assert _PAIR_B in candidate_pairs


def test_live_count_at_the_cap_produces_an_empty_candidate_tuple_and_zero_probability() -> None:
    """Two live conflicts (pairs A and B) at `MAX_CONCURRENT_CONFLICTS`, plus a fresh eligible
    dyad on pair C: dyad C must NOT be admitted -- the candidate tuple is empty and the clamped
    probability is exactly 0."""
    assert MAX_CONCURRENT_CONFLICTS == 2, "this test's two-pair setup assumes the current cap"
    state = _fixture_state(
        seed=DECLARED_SEEDS[0],
        conflicts=(
            _conflict(*_PAIR_A, status=ConflictStatus.ACTIVE),
            _conflict(*_PAIR_B, status=ConflictStatus.CEASEFIRE),
        ),
        dyads=(_dyad(*_PAIR_C),),
    )
    report = resolve_turn(state, _empty_decisions(state)).report
    assert report.foreign_affairs is not None
    outbreak = report.foreign_affairs.outbreak
    assert outbreak.candidates == ()
    assert outbreak.total_weight_bps == 0
    assert outbreak.clamped_probability_bps == 0


# --- items 3-4: the occurrence draw is unconditional, selection is not ----------------------


def test_the_occurrence_draw_is_still_made_and_stored_at_the_cap() -> None:
    state = _fixture_state(
        seed=DECLARED_SEEDS[0],
        conflicts=(
            _conflict(*_PAIR_A, status=ConflictStatus.ACTIVE),
            _conflict(*_PAIR_B, status=ConflictStatus.ACTIVE),
        ),
        dyads=(_dyad(*_PAIR_C),),
    )
    report = resolve_turn(state, _empty_decisions(state)).report
    assert report.foreign_affairs is not None
    outbreak = report.foreign_affairs.outbreak
    assert isinstance(outbreak.occurrence_draw, int)
    assert outbreak.occurred is False


def test_the_selection_draw_is_absent_at_the_cap() -> None:
    state = _fixture_state(
        seed=DECLARED_SEEDS[0],
        conflicts=(
            _conflict(*_PAIR_A, status=ConflictStatus.ACTIVE),
            _conflict(*_PAIR_B, status=ConflictStatus.ACTIVE),
        ),
        dyads=(_dyad(*_PAIR_C),),
    )
    report = resolve_turn(state, _empty_decisions(state)).report
    assert report.foreign_affairs is not None
    outbreak = report.foreign_affairs.outbreak
    assert outbreak.selection_draw is None
    assert outbreak.selected_country_a is None
    assert outbreak.conflict_id is None


# --- item 5: terminal conflicts consume no capacity -------------------------------------------


def test_terminal_conflicts_consume_no_capacity() -> None:
    """Two TERMINAL conflicts (one SETTLED, one DECIDED) on pairs A and B, plus a fresh eligible
    dyad on pair C: since `SETTLED`/`DECIDED` are permanent history, `live_count=0` and dyad C
    must be admitted -- the cap is not reached."""
    state = _fixture_state(
        seed=DECLARED_SEEDS[0],
        conflicts=(
            _conflict(*_PAIR_A, status=ConflictStatus.SETTLED, resolved_turn=0),
            _conflict(*_PAIR_B, status=ConflictStatus.DECIDED, resolved_turn=0),
        ),
        dyads=(_dyad(*_PAIR_C),),
    )
    report = resolve_turn(state, _empty_decisions(state)).report
    assert report.foreign_affairs is not None
    candidate_pairs = {
        (row.country_a, row.country_b) for row in report.foreign_affairs.outbreak.candidates
    }
    assert _PAIR_C in candidate_pairs


# --- item 6: many-turn witness, declared seeds, reaches 2 but never 3 -------------------------


def _drive(seed: int, turns: int):  # type: ignore[no-untyped-def]
    """All three dyads eligible from turn 0; resolves `turns` consecutive turns directly through
    `resolve_turn` (no decisions ever submitted), returning the live-conflict-count observed at
    the close of every turn."""
    state = _fixture_state(seed=seed, dyads=(_dyad(*_PAIR_A), _dyad(*_PAIR_B), _dyad(*_PAIR_C)))
    live_counts = []
    for _ in range(turns):
        resolution = resolve_turn(state, _empty_decisions(state))
        state = resolution.state
        live_counts.append(
            sum(
                1
                for c in state.world.conflicts
                if c.status in (ConflictStatus.ACTIVE, ConflictStatus.CEASEFIRE)
            )
        )
    return live_counts


def test_many_turn_witness_across_declared_seeds_reaches_two_but_never_three() -> None:
    per_seed_max = {}
    for seed in DECLARED_SEEDS:
        counts = _drive(seed, turns=400)
        assert all(c <= MAX_CONCURRENT_CONFLICTS for c in counts), (
            f"seed {seed}: live count exceeded {MAX_CONCURRENT_CONFLICTS} at some turn -- "
            f"observed counts include {max(counts)}"
        )
        per_seed_max[seed] = max(counts)
    assert max(per_seed_max.values()) == MAX_CONCURRENT_CONFLICTS, (
        f"sanity: no declared seed ever reached the cap of {MAX_CONCURRENT_CONFLICTS} within "
        f"200 turns across three high-pressure dyads -- per_seed_max={per_seed_max}"
    )


# --- item 7: determinism and save/reload on the fixture ---------------------------------------


def _play(seed: int, turns: int) -> str:
    state = make_game_state(
        seed=seed,
        foreign_profiles=_PROFILES,
        dyads=(_dyad(*_PAIR_A), _dyad(*_PAIR_B), _dyad(*_PAIR_C)),
    )
    save = new_game(state, save_format_version=SAVE_FORMAT_VERSION)
    for _ in range(turns):
        current = save.current_state()
        try:
            save = advance_game(save, _empty_decisions(current))
        except GameAlreadyConcludedError:
            break
    return dump_save_json(save)


def test_the_fixture_is_deterministic_under_independent_replay() -> None:
    for seed in DECLARED_SEEDS:
        assert _play(seed, turns=50) == _play(seed, turns=50)


def test_the_fixture_survives_save_reload_without_a_reroll() -> None:
    for seed in DECLARED_SEEDS:
        uninterrupted = _play(seed, turns=50)

        state = make_game_state(
            seed=seed,
            foreign_profiles=_PROFILES,
            dyads=(_dyad(*_PAIR_A), _dyad(*_PAIR_B), _dyad(*_PAIR_C)),
        )
        save = new_game(state, save_format_version=SAVE_FORMAT_VERSION)
        for _ in range(25):
            current = save.current_state()
            try:
                save = advance_game(save, _empty_decisions(current))
            except GameAlreadyConcludedError:
                break

        reloaded = load_save_json(dump_save_json(save))
        for _ in range(25, 50):
            current = reloaded.current_state()
            try:
                reloaded = advance_game(reloaded, _empty_decisions(current))
            except GameAlreadyConcludedError:
                break

        assert dump_save_json(reloaded) == uninterrupted
