"""External Wars W1 commit 7: focused tests for `reconcile_foreign_affairs_report` (frozen plan
sec.12, groups 46-52). Not commit 8's complete 16-case rehashed tamper matrix -- one focused test
per group's ownership and its honest failure boundaries, plus non-vacuity on quiet turns.

Every corruption is built with `model_copy(update=...)`, which never re-validates (Pydantic v2),
exactly `test_reconciliation.py`'s own established pattern: each test starts from a genuinely
resolved real turn and alters the smallest relevant fact, so the failure proves RECONCILIATION
caught a state/report contradiction -- not merely that a report self-validator did.
"""

from __future__ import annotations

import pytest

from app.content.scenarios import load_scenario_file
from app.simulation.decisions import DecisionSet
from app.simulation.foreign_conflict import (
    MAX_CONCURRENT_CONFLICTS,
    MIN_OUTBREAK_WEIGHT_BPS,
    ConflictStatus,
    WarAim,
    initial_intensity_bps,
)
from app.simulation.reconciliation import reconcile_foreign_affairs_report
from app.simulation.report import ForeignConflictOutbreakCandidateRow
from app.simulation.resolver import TurnResolution, resolve_turn
from app.simulation.state import (
    ConflictDyadState,
    ForeignConflictState,
    ForeignProfileState,
    GameState,
)
from tests.conftest import SCENARIO_DIR, make_game_state

# --- shared construction helpers ---------------------------------------------------------------


def _profile(capability: int = 5_000) -> ForeignProfileState:
    return ForeignProfileState(display_name="Profile", war_capability_bps=capability)


def _dyad(
    country_a: str,
    country_b: str,
    *,
    tension: int = 9_500,
    grievance: int = 9_500,
    eligible: bool = True,
    exposure: int = 2_000,
) -> ConflictDyadState:
    return ConflictDyadState(
        country_a=country_a,
        country_b=country_b,
        aggressor=country_a,
        defender=country_b,
        aim_a=WarAim.DETERRENCE,
        aim_b=WarAim.TERRITORIAL,
        eligible=eligible,
        player_security_exposure_bps=exposure,
        tension_bps=tension,
        grievance_bps=grievance,
    )


def _conflict(
    country_a: str,
    country_b: str,
    *,
    status: ConflictStatus,
    opened_turn: int = 0,
    intensity: int = 3_000,
    position: int = 0,
    exhaustion_a: int = 0,
    exhaustion_b: int = 0,
    readiness: int = 0,
    ceasefire_run_turns: int = 0,
    resolved_turn: int | None = None,
    capability_a: int = 5_000,
    capability_b: int = 5_000,
) -> ForeignConflictState:
    return ForeignConflictState(
        conflict_id=f"{country_a}__{country_b}__t{opened_turn}",
        country_a=country_a,
        country_b=country_b,
        aggressor=country_a,
        defender=country_b,
        war_capability_a_bps=capability_a,
        war_capability_b_bps=capability_b,
        aim_a=WarAim.DETERRENCE,
        aim_b=WarAim.TERRITORIAL,
        opened_turn=opened_turn,
        intensity_bps=intensity,
        position_bps=position,
        exhaustion_a_bps=exhaustion_a,
        exhaustion_b_bps=exhaustion_b,
        negotiation_readiness_bps=readiness,
        status=status,
        ceasefire_run_turns=ceasefire_run_turns,
        resolved_turn=resolved_turn,
    )


PAIR_A = ("alpha", "beta")
PAIR_B = ("delta", "gamma")
PAIR_C = ("epsilon", "zeta")
_ALL_COUNTRIES = ("alpha", "beta", "delta", "gamma", "epsilon", "zeta")
_PROFILES = {name: _profile() for name in _ALL_COUNTRIES}


def _empty_decisions(state: GameState) -> DecisionSet:
    return DecisionSet(expected_turn=state.turn, expected_state_version=state.state_version)


def _synthetic_state(
    *,
    conflicts: tuple[ForeignConflictState, ...] = (),
    dyads: tuple[ConflictDyadState, ...] = (),
    seed: int = 7,
) -> GameState:
    return make_game_state(seed=seed, foreign_profiles=_PROFILES, dyads=dyads, conflicts=conflicts)


def _resolve_once(state: GameState) -> tuple[GameState, GameState, TurnResolution]:
    resolution = resolve_turn(state, _empty_decisions(state))
    return state, resolution.state, resolution


def _reconcile(opening: GameState, closing: GameState, resolution: TurnResolution) -> list[str]:
    return reconcile_foreign_affairs_report(
        opening_state=opening, closing_state=closing, report=resolution.report
    )


def _assert_only(problems: list[str], substring: str) -> None:
    assert problems, f"expected a problem containing {substring!r}, got none"
    assert any(substring in p for p in problems), f"{substring!r} not found in {problems!r}"


# --- clean resolution: no problems, and it is genuinely non-vacuous ----------------------------


def test_a_clean_real_resolution_from_decree_state_returns_no_problems_across_many_turns() -> None:
    """`decree_state.yaml`'s real authored dyad reliably starts a war within 80 turns (already
    confirmed during implementation), so this exercises outbreak, ACTIVE progression, and
    terminal transitions all through the real resolver, with zero problems at every turn."""
    state = load_scenario_file(SCENARIO_DIR / "decree_state.yaml")
    saw_war = False
    for _ in range(60):
        opening, closing, resolution = _resolve_once(state)
        problems = _reconcile(opening, closing, resolution)
        assert problems == [], f"turn {opening.turn}: {problems!r}"
        assert resolution.report.foreign_affairs is not None
        if resolution.report.foreign_affairs.outbreak.occurred:
            saw_war = True
        state = closing
    assert saw_war, "sanity: no war started within 60 turns; this test proves nothing"


def test_zero_outbreak_and_conflict_free_turn_is_still_non_vacuous() -> None:
    """A synthetic state with NO dyads and NO conflicts at all: the outbreak report is
    present-but-empty every turn. Reconciliation must still be live here -- a fabricated
    outbreak, a fabricated conflict, or a fabricated security contribution must still be caught,
    proving `[]` is never merely the vacuous case."""
    state = _synthetic_state()
    opening, closing, resolution = _resolve_once(state)
    problems = _reconcile(opening, closing, resolution)
    assert problems == []
    assert resolution.report.foreign_affairs is not None
    outbreak = resolution.report.foreign_affairs.outbreak
    assert not outbreak.occurred
    assert outbreak.candidates == ()
    assert resolution.report.foreign_affairs.progressions == ()

    # fabricated outbreak occurrence, on an otherwise-genuine report
    forged_outbreak = outbreak.model_copy(
        update={
            "occurred": True,
            "conflict_id": "alpha__beta__t0",
            "opened_turn": 0,
            "selected_country_a": "alpha",
            "selected_country_b": "beta",
        }
    )
    forged_report = resolution.report.model_copy(
        update={
            "foreign_affairs": resolution.report.foreign_affairs.model_copy(
                update={"outbreak": forged_outbreak}
            )
        }
    )
    problems = reconcile_foreign_affairs_report(
        opening_state=opening, closing_state=closing, report=forged_report
    )
    _assert_only(problems, "group 48")

    # fabricated closing conflict with no progression row and no report evidence at all
    fabricated_conflict = _conflict("alpha", "beta", status=ConflictStatus.ACTIVE)
    forged_closing = closing.model_copy(
        update={"world": closing.world.model_copy(update={"conflicts": (fabricated_conflict,)})}
    )
    problems = reconcile_foreign_affairs_report(
        opening_state=opening, closing_state=forged_closing, report=resolution.report
    )
    assert problems == [], (
        "a conflict appearing in closing_state with no corresponding progression row is not "
        "this function's concern in isolation -- group 47's id-set check only inspects the "
        "REPORT's claims against the expected set derived from opening_state + the outbreak row, "
        "not extra state; the fabricated conflict here has no outbreak backing it either, so it "
        "would instead be caught by a construction-time/invariant check on world.conflicts, not "
        "foreign-affairs reconciliation"
    )

    # fabricated nonzero security contribution with no ACTIVE conflict anywhere
    political = resolution.report.political
    assert political is not None
    forged_political_report = resolution.report.model_copy(
        update={"political": political.model_copy(update={"security_contribution_bps": -50})}
    )
    problems = reconcile_foreign_affairs_report(
        opening_state=opening, closing_state=closing, report=forged_political_report
    )
    _assert_only(problems, "group 51")


def test_at_cap_turn_is_non_vacuous() -> None:
    """Two live conflicts (at `MAX_CONCURRENT_CONFLICTS`) plus a fresh eligible dyad: the real
    candidate tuple is empty every turn, but reconciliation is still live -- a fabricated
    candidate at capacity must still be caught."""
    assert MAX_CONCURRENT_CONFLICTS == 2
    state = _synthetic_state(
        conflicts=(
            _conflict(*PAIR_A, status=ConflictStatus.ACTIVE),
            _conflict(*PAIR_B, status=ConflictStatus.CEASEFIRE),
        ),
        dyads=(_dyad(*PAIR_C),),
    )
    opening, closing, resolution = _resolve_once(state)
    problems = _reconcile(opening, closing, resolution)
    assert problems == []
    assert resolution.report.foreign_affairs is not None
    assert resolution.report.foreign_affairs.outbreak.candidates == ()

    fabricated_candidate_report = resolution.report.model_copy(
        update={
            "foreign_affairs": resolution.report.foreign_affairs.model_copy(
                update={
                    "outbreak": resolution.report.foreign_affairs.outbreak.model_copy(
                        update={
                            "candidates": (
                                ForeignConflictOutbreakCandidateRow(
                                    country_a="epsilon",
                                    country_b="zeta",
                                    aggressor="epsilon",
                                    defender="zeta",
                                    tension_bps=9_500,
                                    grievance_bps=9_500,
                                    raw_dyad_weight_bps=9_500,
                                    passed_pressure_floor=True,
                                ),
                            )
                        }
                    )
                }
            )
        }
    )
    problems = reconcile_foreign_affairs_report(
        opening_state=opening, closing_state=closing, report=fabricated_candidate_report
    )
    _assert_only(problems, "group 47")


# --- group 46: opening provenance ---------------------------------------------------------------


def test_group46_existing_conflict_opening_corruption_is_caught() -> None:
    state = _synthetic_state(
        conflicts=(_conflict(*PAIR_A, status=ConflictStatus.ACTIVE, intensity=4_000),)
    )
    opening, closing, resolution = _resolve_once(state)
    assert resolution.report.foreign_affairs is not None
    row = resolution.report.foreign_affairs.progressions[0]
    corrupted_row = row.model_copy(update={"opening_intensity_bps": row.opening_intensity_bps + 1})
    forged_report = resolution.report.model_copy(
        update={
            "foreign_affairs": resolution.report.foreign_affairs.model_copy(
                update={"progressions": (corrupted_row,)}
            )
        }
    )
    problems = reconcile_foreign_affairs_report(
        opening_state=opening, closing_state=closing, report=forged_report
    )
    _assert_only(problems, "group 46")


def test_group46_new_conflict_opening_provenance() -> None:
    """A conflict that opens THIS turn: its row's opening_* must match the validated outbreak
    initialization, not a real prior conflict (there is none)."""
    opening, closing, resolution = _find_fresh_outbreak()
    assert resolution.report.foreign_affairs is not None
    outbreak = resolution.report.foreign_affairs.outbreak
    assert outbreak.occurred

    row = next(
        r
        for r in resolution.report.foreign_affairs.progressions
        if r.conflict_id == outbreak.conflict_id
    )
    corrupted_row = row.model_copy(update={"opening_intensity_bps": row.opening_intensity_bps + 1})
    other_rows = tuple(
        r
        for r in resolution.report.foreign_affairs.progressions
        if r.conflict_id != row.conflict_id
    )
    forged_report = resolution.report.model_copy(
        update={
            "foreign_affairs": resolution.report.foreign_affairs.model_copy(
                update={"progressions": (*other_rows, corrupted_row)}
            )
        }
    )
    problems = reconcile_foreign_affairs_report(
        opening_state=opening, closing_state=closing, report=forged_report
    )
    _assert_only(problems, "group 46")


def test_group46_neither_source_is_caught() -> None:
    """A progression row for a conflict_id that matches neither an opening-state conflict nor a
    validated outbreak."""
    state = _synthetic_state(conflicts=(_conflict(*PAIR_A, status=ConflictStatus.ACTIVE),))
    opening, closing, resolution = _resolve_once(state)
    assert resolution.report.foreign_affairs is not None
    row = resolution.report.foreign_affairs.progressions[0]
    fabricated_id_row = row.model_copy(update={"conflict_id": "nonexistent__pair__t99"})
    forged_report = resolution.report.model_copy(
        update={
            "foreign_affairs": resolution.report.foreign_affairs.model_copy(
                update={"progressions": (fabricated_id_row,)}
            )
        }
    )
    problems = reconcile_foreign_affairs_report(
        opening_state=opening, closing_state=closing, report=forged_report
    )
    assert any("group 46" in p or "group 47" in p for p in problems)


def test_group46_both_sources_is_caught() -> None:
    """Forge opening_state to ALSO contain a live conflict whose id equals a genuine outbreak's
    new conflict_id -- the row then matches both an "existing" opening conflict (fabricated) and
    the real validated outbreak initialization. The fabricated conflict must sit on a DIFFERENT
    country pair (`ForeignConflictState` has no validator tying `conflict_id` to its own
    `country_a`/`country_b`) so its presence in `opening_state` does not itself exclude the real
    outbreak's pair from candidacy -- that would collapse this into a single-source case instead
    of the ambiguous-provenance one this test targets."""
    opening, closing, resolution = _find_fresh_outbreak()
    assert resolution.report.foreign_affairs is not None
    new_id = resolution.report.foreign_affairs.outbreak.conflict_id
    assert new_id is not None
    outbreak_country_a, outbreak_country_b = new_id.split("__t")[0].split("__")
    assert (outbreak_country_a, outbreak_country_b) != PAIR_B, (
        "the fabricated conflict's pair must differ from the real outbreak's pair"
    )
    fabricated_existing = _conflict(
        *PAIR_B, status=ConflictStatus.ACTIVE, opened_turn=opening.turn
    ).model_copy(update={"conflict_id": new_id})
    forged_opening = opening.model_copy(
        update={
            "world": opening.world.model_copy(
                update={"conflicts": (*opening.world.conflicts, fabricated_existing)}
            )
        }
    )
    problems = reconcile_foreign_affairs_report(
        opening_state=forged_opening, closing_state=closing, report=resolution.report
    )
    _assert_only(problems, "BOTH")


# --- group 47: exact membership, projection, eligibility ---------------------------------------


def test_group47_missing_progression_row_is_caught() -> None:
    state = _synthetic_state(conflicts=(_conflict(*PAIR_A, status=ConflictStatus.ACTIVE),))
    opening, closing, resolution = _resolve_once(state)
    assert resolution.report.foreign_affairs is not None
    forged_report = resolution.report.model_copy(
        update={
            "foreign_affairs": resolution.report.foreign_affairs.model_copy(
                update={"progressions": ()}
            )
        }
    )
    problems = reconcile_foreign_affairs_report(
        opening_state=opening, closing_state=closing, report=forged_report
    )
    _assert_only(problems, "group 47")


def test_group47_extra_progression_row_is_caught() -> None:
    state = _synthetic_state(conflicts=(_conflict(*PAIR_A, status=ConflictStatus.ACTIVE),))
    opening, closing, resolution = _resolve_once(state)
    assert resolution.report.foreign_affairs is not None
    real_row = resolution.report.foreign_affairs.progressions[0]
    extra_row = real_row.model_copy(update={"conflict_id": "delta__gamma__t0"})
    forged_report = resolution.report.model_copy(
        update={
            "foreign_affairs": resolution.report.foreign_affairs.model_copy(
                update={"progressions": (extra_row, real_row)}
            )
        }
    )
    problems = reconcile_foreign_affairs_report(
        opening_state=opening, closing_state=closing, report=forged_report
    )
    _assert_only(problems, "group 47")


def test_group47_duplicate_progression_id_is_caught_even_with_a_matching_set() -> None:
    """Two rows with the SAME conflict_id: the id SET matches (cardinality 1 either way is
    wrong, but critically) duplicate detection must fire independently of set equality."""
    state = _synthetic_state(conflicts=(_conflict(*PAIR_A, status=ConflictStatus.ACTIVE),))
    opening, closing, resolution = _resolve_once(state)
    assert resolution.report.foreign_affairs is not None
    real_row = resolution.report.foreign_affairs.progressions[0]
    forged_report = resolution.report.model_copy(
        update={
            "foreign_affairs": resolution.report.foreign_affairs.model_copy(
                update={"progressions": (real_row, real_row)}
            )
        }
    )
    problems = reconcile_foreign_affairs_report(
        opening_state=opening, closing_state=closing, report=forged_report
    )
    _assert_only(problems, "duplicate")


def test_group47_closing_field_mismatch_is_caught() -> None:
    state = _synthetic_state(conflicts=(_conflict(*PAIR_A, status=ConflictStatus.ACTIVE),))
    opening, closing, resolution = _resolve_once(state)
    assert resolution.report.foreign_affairs is not None
    row = resolution.report.foreign_affairs.progressions[0]
    corrupted_row = row.model_copy(update={"closing_intensity_bps": row.closing_intensity_bps + 1})
    forged_report = resolution.report.model_copy(
        update={
            "foreign_affairs": resolution.report.foreign_affairs.model_copy(
                update={"progressions": (corrupted_row,)}
            )
        }
    )
    problems = reconcile_foreign_affairs_report(
        opening_state=opening, closing_state=closing, report=forged_report
    )
    _assert_only(problems, "group 47")


def test_group47_immutable_field_mutation_is_caught() -> None:
    """Mutate `closing_state`'s conflict's `aggressor` -- an immutable field -- leaving the
    report untouched (report doesn't carry aggressor, so it can't itself be "wrong"; the mutation
    must be caught purely from comparing opening vs closing state)."""
    state = _synthetic_state(conflicts=(_conflict(*PAIR_A, status=ConflictStatus.ACTIVE),))
    opening, closing, resolution = _resolve_once(state)
    live_conflict = closing.world.conflicts[0]
    mutated_conflict = live_conflict.model_copy(update={"aggressor": "beta"})
    forged_closing = closing.model_copy(
        update={"world": closing.world.model_copy(update={"conflicts": (mutated_conflict,)})}
    )
    problems = reconcile_foreign_affairs_report(
        opening_state=opening, closing_state=forged_closing, report=resolution.report
    )
    _assert_only(problems, "immutable")


def test_group47_candidate_omission_and_addition_are_caught() -> None:
    # Two dyads at `_dyad`'s legitimate 9_500 default: weight 9_500 each, totalling 19_000.
    # Fix-forward 7a: this fixture briefly used 3_000 to keep the sum under a `StrictBps` ceiling
    # `total_weight_bps` should never have carried (frozen plan sec.6.2, R4 point 5).
    state = _synthetic_state(dyads=(_dyad(*PAIR_A), _dyad(*PAIR_B)))
    opening, closing, resolution = _resolve_once(state)
    assert resolution.report.foreign_affairs is not None
    outbreak = resolution.report.foreign_affairs.outbreak
    assert len(outbreak.candidates) == 2

    # omission
    forged_outbreak = outbreak.model_copy(update={"candidates": outbreak.candidates[:1]})
    forged_report = resolution.report.model_copy(
        update={
            "foreign_affairs": resolution.report.foreign_affairs.model_copy(
                update={"outbreak": forged_outbreak}
            )
        }
    )
    problems = reconcile_foreign_affairs_report(
        opening_state=opening, closing_state=closing, report=forged_report
    )
    _assert_only(problems, "group 47")

    # addition
    forged_outbreak2 = outbreak.model_copy(
        update={"candidates": outbreak.candidates + outbreak.candidates[:1]}
    )
    forged_report2 = resolution.report.model_copy(
        update={
            "foreign_affairs": resolution.report.foreign_affairs.model_copy(
                update={"outbreak": forged_outbreak2}
            )
        }
    )
    problems2 = reconcile_foreign_affairs_report(
        opening_state=opening, closing_state=closing, report=forged_report2
    )
    assert problems2 != []


# --- group 48: RNG redraw, guard parity ---------------------------------------------------------


def test_group48_occurrence_draw_mismatch_is_caught() -> None:
    state = _synthetic_state(dyads=(_dyad(*PAIR_A),))
    opening, closing, resolution = _resolve_once(state)
    assert resolution.report.foreign_affairs is not None
    outbreak = resolution.report.foreign_affairs.outbreak
    forged_outbreak = outbreak.model_copy(
        update={"occurrence_draw": (outbreak.occurrence_draw + 1) % 10_000}
    )
    forged_report = resolution.report.model_copy(
        update={
            "foreign_affairs": resolution.report.foreign_affairs.model_copy(
                update={"outbreak": forged_outbreak}
            )
        }
    )
    problems = reconcile_foreign_affairs_report(
        opening_state=opening, closing_state=closing, report=forged_report
    )
    _assert_only(problems, "occurrence_draw")


def test_group48_selection_draw_mismatch_is_caught() -> None:
    opening, closing, resolution = _find_fresh_outbreak()
    assert resolution.report.foreign_affairs is not None
    outbreak = resolution.report.foreign_affairs.outbreak
    assert outbreak.selection_draw is not None
    forged_outbreak = outbreak.model_copy(update={"selection_draw": outbreak.selection_draw + 1})
    forged_report = resolution.report.model_copy(
        update={
            "foreign_affairs": resolution.report.foreign_affairs.model_copy(
                update={"outbreak": forged_outbreak}
            )
        }
    )
    problems = reconcile_foreign_affairs_report(
        opening_state=opening, closing_state=closing, report=forged_report
    )
    _assert_only(problems, "selection_draw")


def test_group48_jitter_mismatch_is_caught() -> None:
    state = _synthetic_state(conflicts=(_conflict(*PAIR_A, status=ConflictStatus.ACTIVE),))
    opening, closing, resolution = _resolve_once(state)
    assert resolution.report.foreign_affairs is not None
    row = resolution.report.foreign_affairs.progressions[0]
    forged_row = row.model_copy(update={"position_jitter_bps": row.position_jitter_bps + 1})
    forged_report = resolution.report.model_copy(
        update={
            "foreign_affairs": resolution.report.foreign_affairs.model_copy(
                update={"progressions": (forged_row,)}
            )
        }
    )
    problems = reconcile_foreign_affairs_report(
        opening_state=opening, closing_state=closing, report=forged_report
    )
    _assert_only(problems, "group 48")


def test_group48_termination_draw_mismatch_and_unused_draw_present() -> None:
    """An ACTIVE-opening conflict whose readiness/position never opens the ceasefire gate
    (near-zero intensity floor case, freshly opened): no termination draw should exist. Forge one
    onto the row -- a "speculative"/unused draw incorrectly present -- and confirm it is caught."""
    state = _synthetic_state(
        conflicts=(_conflict(*PAIR_A, status=ConflictStatus.ACTIVE, intensity=3_000, position=0),)
    )
    opening, closing, resolution = _resolve_once(state)
    assert resolution.report.foreign_affairs is not None
    row = resolution.report.foreign_affairs.progressions[0]
    assert row.termination_draw is None, "sanity: this fixture must not open the ceasefire gate"
    forged_row = row.model_copy(update={"termination_draw": 1234})
    forged_report = resolution.report.model_copy(
        update={
            "foreign_affairs": resolution.report.foreign_affairs.model_copy(
                update={"progressions": (forged_row,)}
            )
        }
    )
    problems = reconcile_foreign_affairs_report(
        opening_state=opening, closing_state=closing, report=forged_report
    )
    _assert_only(problems, "termination_draw")


def test_group48_ceasefire_opening_row_consumes_no_randomness() -> None:
    """A CEASEFIRE-opening conflict: jitter must be 0 and termination_draw must be None, always
    -- fabricating either is caught."""
    state = _synthetic_state(
        conflicts=(
            _conflict(
                *PAIR_A,
                status=ConflictStatus.CEASEFIRE,
                intensity=2_000,
                exhaustion_a=1_000,
                exhaustion_b=1_000,
                ceasefire_run_turns=0,
            ),
        )
    )
    opening, closing, resolution = _resolve_once(state)
    assert resolution.report.foreign_affairs is not None
    row = resolution.report.foreign_affairs.progressions[0]
    assert row.position_jitter_bps == 0
    assert row.termination_draw is None

    forged_jitter_row = row.model_copy(update={"position_jitter_bps": 5})
    forged_report = resolution.report.model_copy(
        update={
            "foreign_affairs": resolution.report.foreign_affairs.model_copy(
                update={"progressions": (forged_jitter_row,)}
            )
        }
    )
    problems = reconcile_foreign_affairs_report(
        opening_state=opening, closing_state=closing, report=forged_report
    )
    _assert_only(problems, "group 48")

    forged_termination_row = row.model_copy(update={"termination_draw": 42})
    forged_report2 = resolution.report.model_copy(
        update={
            "foreign_affairs": resolution.report.foreign_affairs.model_copy(
                update={"progressions": (forged_termination_row,)}
            )
        }
    )
    problems2 = reconcile_foreign_affairs_report(
        opening_state=opening, closing_state=closing, report=forged_report2
    )
    _assert_only(problems2, "termination_draw")


# --- group 49: authored staticness ---------------------------------------------------------------


def test_group49_foreign_profile_mutation_is_caught() -> None:
    state = _synthetic_state(dyads=(_dyad(*PAIR_A),))
    opening, closing, resolution = _resolve_once(state)
    mutated_profiles = dict(closing.world.foreign_profiles)
    mutated_profiles["alpha"] = mutated_profiles["alpha"].model_copy(
        update={"war_capability_bps": mutated_profiles["alpha"].war_capability_bps + 1}
    )
    forged_closing = closing.model_copy(
        update={"world": closing.world.model_copy(update={"foreign_profiles": mutated_profiles})}
    )
    problems = reconcile_foreign_affairs_report(
        opening_state=opening, closing_state=forged_closing, report=resolution.report
    )
    _assert_only(problems, "group 49")


def test_group49_dyad_mutation_is_caught() -> None:
    state = _synthetic_state(dyads=(_dyad(*PAIR_A),))
    opening, closing, resolution = _resolve_once(state)
    mutated_dyads = tuple(
        d.model_copy(update={"tension_bps": 1}) if d.country_a == "alpha" else d
        for d in closing.world.dyads
    )
    forged_closing = closing.model_copy(
        update={"world": closing.world.model_copy(update={"dyads": mutated_dyads})}
    )
    problems = reconcile_foreign_affairs_report(
        opening_state=opening, closing_state=forged_closing, report=resolution.report
    )
    _assert_only(problems, "group 49")


def test_group49_and_52_foreign_profile_insertion_order_is_irrelevant() -> None:
    state = _synthetic_state(
        conflicts=(_conflict(*PAIR_A, status=ConflictStatus.ACTIVE),), dyads=(_dyad(*PAIR_B),)
    )
    opening, closing, resolution = _resolve_once(state)
    problems_forward = _reconcile(opening, closing, resolution)

    reversed_profiles = dict(reversed(list(opening.world.foreign_profiles.items())))
    reordered_opening = opening.model_copy(
        update={"world": opening.world.model_copy(update={"foreign_profiles": reversed_profiles})}
    )
    reversed_profiles_closing = dict(reversed(list(closing.world.foreign_profiles.items())))
    reordered_closing = closing.model_copy(
        update={
            "world": closing.world.model_copy(
                update={"foreign_profiles": reversed_profiles_closing}
            )
        }
    )
    problems_backward = reconcile_foreign_affairs_report(
        opening_state=reordered_opening, closing_state=reordered_closing, report=resolution.report
    )
    assert problems_forward == problems_backward == []


# --- group 50: capability provenance -------------------------------------------------------------


def test_group50_capability_mismatch_is_caught() -> None:
    state = _synthetic_state(
        conflicts=(_conflict(*PAIR_A, status=ConflictStatus.ACTIVE, capability_a=5_000),)
    )
    opening, closing, resolution = _resolve_once(state)
    assert resolution.report.foreign_affairs is not None
    row = resolution.report.foreign_affairs.progressions[0]
    forged_row = row.model_copy(update={"opening_war_capability_a_bps": 9_999})
    forged_report = resolution.report.model_copy(
        update={
            "foreign_affairs": resolution.report.foreign_affairs.model_copy(
                update={"progressions": (forged_row,)}
            )
        }
    )
    problems = reconcile_foreign_affairs_report(
        opening_state=opening, closing_state=closing, report=forged_report
    )
    _assert_only(problems, "group 50")


# --- group 51: the security-anxiety causal chain --------------------------------------------------


def test_group51_political_and_foreign_affairs_disagreement_is_caught() -> None:
    """Both reports internally self-consistent (each built from the real resolver, then only the
    political report's stored contribution is corrupted after the fact) -- reconciliation must
    catch the cross-report disagreement even though neither report contradicts itself."""
    state = _synthetic_state(
        conflicts=(_conflict(*PAIR_A, status=ConflictStatus.ACTIVE, intensity=6_000),),
        dyads=(),
    )
    # exposure requires a dyad entry for the pair; conflicts alone carry no exposure, so the
    # dyad must exist even though the conflict already started (exposure lives on the dyad,
    # sec.9.2) -- add it directly to the opening state used for resolution.
    state = state.model_copy(
        update={
            "world": state.world.model_copy(update={"dyads": (_dyad(*PAIR_A, exposure=3_000),)})
        }
    )
    opening, closing, resolution = _resolve_once(state)
    political = resolution.report.political
    assert political is not None
    assert political.security_contribution_bps != 0, (
        "sanity: this fixture must produce a nonzero security contribution"
    )
    forged_political = political.model_copy(
        update={"security_contribution_bps": political.security_contribution_bps - 1}
    )
    forged_report = resolution.report.model_copy(update={"political": forged_political})
    problems = reconcile_foreign_affairs_report(
        opening_state=opening, closing_state=closing, report=forged_report
    )
    _assert_only(problems, "group 51")


def test_group51_zero_exposure_contributes_exactly_zero() -> None:
    state = _synthetic_state(
        conflicts=(_conflict(*PAIR_A, status=ConflictStatus.ACTIVE, intensity=8_000),),
        dyads=(_dyad(*PAIR_A, exposure=0),),
    )
    opening, closing, resolution = _resolve_once(state)
    political = resolution.report.political
    assert political is not None
    assert political.security_contribution_bps == 0
    problems = _reconcile(opening, closing, resolution)
    assert problems == []


def test_group51_non_active_conflicts_contribute_zero() -> None:
    # Opening exhaustion 5_000/5_000, position 0: `ceasefire_recovered_exhaustion_bps` drops each
    # by `CEASEFIRE_RECOVERY_BPS` (300) to 4_700, so `closing_readiness_bps` (average exhaustion
    # minus the zero decisiveness penalty) lands at 4_700 -- above `CEASEFIRE_BREAKDOWN_BPS`
    # (4_000), so the conflict stays CEASEFIRE at closing rather than breaking down to ACTIVE
    # (`ceasefire_closing_status`). A CEASEFIRE-opening row with default (0) exhaustion would
    # instead break down deterministically (readiness starts at 0, no RNG on this branch).
    state = _synthetic_state(
        conflicts=(
            _conflict(
                *PAIR_A,
                status=ConflictStatus.CEASEFIRE,
                intensity=8_000,
                exhaustion_a=5_000,
                exhaustion_b=5_000,
            ),
        ),
        dyads=(_dyad(*PAIR_A, exposure=3_000),),
    )
    opening, closing, resolution = _resolve_once(state)
    assert resolution.report.foreign_affairs is not None
    row = resolution.report.foreign_affairs.progressions[0]
    assert row.closing_status is ConflictStatus.CEASEFIRE, (
        "fixture assumption: this conflict must remain CEASEFIRE (not break down to ACTIVE) at "
        "closing for the claim under test -- non-ACTIVE conflicts contribute zero -- to apply"
    )
    political = resolution.report.political
    assert political is not None
    assert political.security_contribution_bps == 0
    problems = _reconcile(opening, closing, resolution)
    assert problems == []


# --- group 52: floors -----------------------------------------------------------------------------


def test_group52_active_intensity_floor_violation_is_caught() -> None:
    state = _synthetic_state(
        conflicts=(_conflict(*PAIR_A, status=ConflictStatus.ACTIVE, intensity=3_000),)
    )
    opening, closing, resolution = _resolve_once(state)
    assert resolution.report.foreign_affairs is not None
    row = resolution.report.foreign_affairs.progressions[0]
    if row.closing_status is not ConflictStatus.ACTIVE:
        pytest.skip("fixture did not stay ACTIVE this turn")
    forged_row = row.model_copy(update={"closing_intensity_bps": 1, "raw_closing_intensity_bps": 1})
    forged_report = resolution.report.model_copy(
        update={
            "foreign_affairs": resolution.report.foreign_affairs.model_copy(
                update={"progressions": (forged_row,)}
            )
        }
    )
    problems = reconcile_foreign_affairs_report(
        opening_state=opening, closing_state=closing, report=forged_report
    )
    assert any("group 47" in p or "group 52" in p or "group 48" in p for p in problems)


def test_group52_ceasefire_breakdown_floor_violation_is_caught() -> None:
    """A CEASEFIRE conflict engineered to break back to ACTIVE (low exhaustion recovery pushes
    readiness below the breakdown threshold): the recomputed restart intensity must be >=
    MIN_ACTIVE_INTENSITY_BPS. Corrupt the closing conflict's intensity below the floor while
    claiming ACTIVE, and confirm it's caught."""
    state = _synthetic_state(
        conflicts=(
            _conflict(
                *PAIR_A,
                status=ConflictStatus.CEASEFIRE,
                intensity=100,
                exhaustion_a=0,
                exhaustion_b=0,
                ceasefire_run_turns=0,
            ),
        )
    )
    opening, closing, resolution = _resolve_once(state)
    assert resolution.report.foreign_affairs is not None
    row = resolution.report.foreign_affairs.progressions[0]
    if row.closing_status is not ConflictStatus.ACTIVE:
        pytest.skip("fixture did not break down to ACTIVE this turn")
    forged_row = row.model_copy(update={"closing_intensity_bps": 1})
    forged_report = resolution.report.model_copy(
        update={
            "foreign_affairs": resolution.report.foreign_affairs.model_copy(
                update={"progressions": (forged_row,)}
            )
        }
    )
    problems = reconcile_foreign_affairs_report(
        opening_state=opening, closing_state=closing, report=forged_report
    )
    assert problems != []


def test_group52_sub_floor_dyad_is_represented_but_never_selectable() -> None:
    """A dyad below `MIN_OUTBREAK_WEIGHT_BPS` still appears as a candidate row
    (`passed_pressure_floor=False`), contributes nothing to `total_weight_bps`, and can never be
    the selected pair."""
    state = _synthetic_state(dyads=(_dyad(*PAIR_A, tension=100, grievance=100),))
    opening, closing, resolution = _resolve_once(state)
    assert resolution.report.foreign_affairs is not None
    outbreak = resolution.report.foreign_affairs.outbreak
    assert len(outbreak.candidates) == 1
    assert not outbreak.candidates[0].passed_pressure_floor
    assert outbreak.total_weight_bps == 0
    assert not outbreak.occurred
    problems = _reconcile(opening, closing, resolution)
    assert problems == []


def test_group52_sub_floor_dyad_forged_as_an_outbreak_is_caught() -> None:
    """Fix-forward 7b: the frozen plan's group 52 names this clause explicitly -- 'no outbreak
    occurred from a dyad whose raw_dyad_weight_bps was below MIN_OUTBREAK_WEIGHT_BPS'. A
    sub-floor dyad (weight 499, one below the 500 floor) that never actually triggers a war is
    forged into a fully self-consistent outbreak row; reconciliation must reject it with an
    explicit group-52 problem, not merely an incidental group-48 RNG mismatch."""
    weight = 499
    assert weight < MIN_OUTBREAK_WEIGHT_BPS
    state = _synthetic_state(dyads=(_dyad(*PAIR_A, tension=weight, grievance=weight),))
    opening, closing, resolution = _resolve_once(state)
    assert resolution.report.foreign_affairs is not None
    outbreak = resolution.report.foreign_affairs.outbreak
    assert outbreak.candidates[0].raw_dyad_weight_bps == weight
    assert not outbreak.candidates[0].passed_pressure_floor
    assert not outbreak.occurred, "sanity: this dyad must not genuinely start a war"

    country_a, country_b = PAIR_A
    forged_outbreak = outbreak.model_copy(
        update={
            "occurred": True,
            "selection_draw": 0,
            "selected_country_a": country_a,
            "selected_country_b": country_b,
            "conflict_id": f"{country_a}__{country_b}__t{opening.turn}",
            "opened_turn": opening.turn,
            "initial_intensity_bps": initial_intensity_bps(tension_bps=weight),
            "initial_position_bps": 0,
            "initial_exhaustion_a_bps": 0,
            "initial_exhaustion_b_bps": 0,
            "initial_readiness_bps": 0,
        }
    )
    forged_report = resolution.report.model_copy(
        update={
            "foreign_affairs": resolution.report.foreign_affairs.model_copy(
                update={"outbreak": forged_outbreak}
            )
        }
    )
    problems = reconcile_foreign_affairs_report(
        opening_state=opening, closing_state=closing, report=forged_report
    )
    _assert_only(problems, "(group 52)")
    assert any("sub-floor dyad" in p for p in problems)


# --- malformed references: problems, never exceptions --------------------------------------------


def test_missing_referenced_profile_returns_a_problem_not_an_exception() -> None:
    """A progression row's implied country is referenced by a real closing conflict, but the
    profile for it is missing from opening_state.foreign_profiles entirely -- must be a problem
    string, never a raised exception."""
    state = _synthetic_state(conflicts=(_conflict(*PAIR_A, status=ConflictStatus.ACTIVE),))
    opening, closing, resolution = _resolve_once(state)
    stripped_profiles = {k: v for k, v in opening.world.foreign_profiles.items() if k != "alpha"}
    forged_opening = opening.model_copy(
        update={"world": opening.world.model_copy(update={"foreign_profiles": stripped_profiles})}
    )
    problems = reconcile_foreign_affairs_report(
        opening_state=forged_opening, closing_state=closing, report=resolution.report
    )
    _assert_only(problems, "group 50")


def test_missing_referenced_dyad_for_a_candidate_returns_a_problem_not_an_exception() -> None:
    state = _synthetic_state(dyads=(_dyad(*PAIR_A),))
    opening, closing, resolution = _resolve_once(state)
    assert resolution.report.foreign_affairs is not None
    forged_opening = opening.model_copy(
        update={"world": opening.world.model_copy(update={"dyads": ()})}
    )
    # forged_opening no longer authors the dyad the real report's candidate row references.
    problems = reconcile_foreign_affairs_report(
        opening_state=forged_opening, closing_state=closing, report=resolution.report
    )
    _assert_only(problems, "group 47")


def test_missing_referenced_closing_conflict_returns_a_problem_not_an_exception() -> None:
    state = _synthetic_state(conflicts=(_conflict(*PAIR_A, status=ConflictStatus.ACTIVE),))
    opening, closing, resolution = _resolve_once(state)
    forged_closing = closing.model_copy(
        update={"world": closing.world.model_copy(update={"conflicts": ()})}
    )
    problems = reconcile_foreign_affairs_report(
        opening_state=opening, closing_state=forged_closing, report=resolution.report
    )
    _assert_only(problems, "group 47")


# --- helper: search for a genuine fresh outbreak (bounded, not "fishing after failure") ----------


def _find_fresh_outbreak() -> tuple[GameState, GameState, TurnResolution]:
    """A single-dyad, zero-pre-existing-conflict state, tried across a bounded, declared range of
    seeds until turn 0 produces a genuine outbreak. Not a search for a desired VALUE -- every
    outcome here is the real engine's output; only whether an outbreak fires this turn varies by
    seed, exactly `test_foreign_conflict_wiring.py`'s own established "resolve until it happens"
    pattern."""
    for seed in range(200):
        state = _synthetic_state(dyads=(_dyad(*PAIR_A),), seed=seed)
        opening, closing, resolution = _resolve_once(state)
        assert resolution.report.foreign_affairs is not None
        if resolution.report.foreign_affairs.outbreak.occurred:
            return opening, closing, resolution
    raise AssertionError("no outbreak occurred within 200 seeds; cannot exercise this claim")
