"""Tests for `simulation.invariants`' External Wars Gate W1 backstop, `_check_foreign_conflicts`
(frozen plan sec.6), plus scenario-content isolation and save compatibility -- commit 5c.

`_check_foreign_conflicts` re-derives, directly from `WorldState` alone, every structural rule
`ForeignProfileState`/`ConflictDyadState`/`ForeignConflictState`/`WorldState`'s own Pydantic
validators already enforce at every legitimate construction path. Those validators are
mutable-object gaps: a `model_copy(update=...)` chain (which never revalidates anything at any
level -- confirmed empirically in `test_legislature_invariants.py`, and reused here) and any
future non-validating restore path can produce a `WorldState` that is internally inconsistent
while still passing type checks. Codes with no per-model validator at all -- the
`foreign_profiles` dict-key rules and the dyad/conflict cross-reference rules, which no
standalone model could ever check because they need `WorldState.countries`/`foreign_profiles` to
judge -- are reachable through plain, normal construction and are tested that way. Codes a model
already guards at construction time (tuple-level duplicate/order, and `ForeignConflictState`'s
own `resolved_turn`/status coherence) require the same `model_copy`-chain bypass
`test_legislature_invariants.py` established, so `check_invariants` is proven to catch them
independently of the validator being bypassed -- never through a normal constructor call after
the point of defect, since Pydantic v2 revalidates a nested model instance whenever it is handed
to a field through a normal `__init__`.

## Dictionary-order clarification (narrow implementation correction, not a frozen-plan edit)

The frozen plan's sec.6.1 names a `foreign_profiles_not_canonically_ordered` invariant code
alongside an explicit requirement that `WorldState.foreign_profiles` insertion order carry no
semantic weight (sec.6.1: "Order independence is explicit... a test constructs the same world
twice with the mapping built in two different insertion orders and asserts byte-identical
canonical JSON"). Those two statements conflict: a `dict` has no canonical "sorted" state to
violate short of imposing one, and rejecting a semantically identical mapping for its insertion
order would be exactly the kind of insertion-order dependence the same section forbids.
`canonical_json.canonical_dumps` already serializes with `sort_keys=True` (see
`WorldState.foreign_profiles`'s own docstring), so byte-identical canonical output was never
actually at risk. This file resolves the conflict in favor of the higher-level requirement:
`_check_foreign_conflicts` no longer emits `foreign_profiles_not_canonically_ordered`, and
`test_foreign_profiles_insertion_order_is_not_semantic` below proves two different insertion
orders are both valid and serialize identically, in place of a negative test for a code that no
longer exists.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from app.core.canonical_json import canonical_digest, canonical_dumps
from app.core.errors import UnsupportedRulesetVersionError
from app.saves import read_save_file
from app.simulation.foreign_conflict import MAX_CONCURRENT_CONFLICTS, ConflictStatus, WarAim
from app.simulation.invariants import check_invariants
from app.simulation.save_format import (
    SAVE_FORMAT_VERSION,
    SUPPORTED_RULESET_VERSIONS,
    load_save_json,
)
from app.simulation.state import (
    RULESET_VERSION,
    ConflictDyadState,
    ForeignConflictState,
    ForeignProfileState,
    GameState,
    WorldState,
)
from tests.conftest import make_country, make_game_state

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
PHASE4A_SAVE_PATH = FIXTURES_DIR / "phase4a_save_ruleset_0.12.0.json"

SCENARIOS_DIR = Path(__file__).resolve().parents[2] / "data" / "scenarios"

# Stable canonical baseline digests: `canonical_dumps` of the c47fc82 (pre-W1) scenario YAML with
# no keys stripped, computed once during authoring and recorded here as a repository-owned
# literal -- NOT recomputed via git at test time (§ commit 5c requires no runtime git
# invocation). A test below recomputes today's digest of the current YAML with exactly
# {"content_version", "foreign_profiles", "dyads"} stripped and compares it against this literal.
_PRE_W1_SCENARIO_DIGEST_BLAKE2B: dict[str, str] = {
    "tiny_valid.yaml": "8f23104a86cc0d455e510bd6e8cee548668cb4d8b67a372abb4ad4da027611a3",
    "decree_state.yaml": "54726c39e3e7c58c1b852d55bdc45fccacd5de75b70dda99b680cc2f104156c6",
    "deficit_demo.yaml": "6e7eb0c3bc24e47db34bb591e8af0b2374c04774a022c37c6df74503d4b1dbc4",
}


def _codes(state: GameState) -> set[str]:
    return {v.code for v in check_invariants(state)}


# --- valid building blocks, via real constructors -----------------------------


def _profile(display_name: str = "Kessia", capability: int = 5_000) -> ForeignProfileState:
    return ForeignProfileState(display_name=display_name, war_capability_bps=capability)


def _dyad(
    *,
    country_a: str = "kessia",
    country_b: str = "vetruska",
    aggressor: str = "vetruska",
    defender: str = "kessia",
    tension: int = 8_500,
    grievance: int = 7_500,
    exposure: int = 2_000,
    eligible: bool = True,
) -> ConflictDyadState:
    return ConflictDyadState(
        country_a=country_a,
        country_b=country_b,
        tension_bps=tension,
        grievance_bps=grievance,
        eligible=eligible,
        aggressor=aggressor,
        defender=defender,
        aim_a=WarAim.DETERRENCE,
        aim_b=WarAim.TERRITORIAL,
        player_security_exposure_bps=exposure,
    )


def _conflict(
    *,
    conflict_id: str = "kessia__vetruska__t0",
    country_a: str = "kessia",
    country_b: str = "vetruska",
    aggressor: str = "vetruska",
    defender: str = "kessia",
    status: ConflictStatus = ConflictStatus.ACTIVE,
    resolved_turn: int | None = None,
) -> ForeignConflictState:
    return ForeignConflictState(
        conflict_id=conflict_id,
        country_a=country_a,
        country_b=country_b,
        aggressor=aggressor,
        defender=defender,
        war_capability_a_bps=5_000,
        war_capability_b_bps=5_600,
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


def _valid_state() -> GameState:
    """A genuinely valid baseline `GameState`, player country `'testland'` (the `make_game_state`
    default), with two foreign profiles and one eligible dyad between them -- built entirely
    through normal, validated constructors."""
    return make_game_state(
        foreign_profiles={
            "kessia": _profile("Kessia", 5_000),
            "vetruska": _profile("Vetruska", 5_600),
        },
        dyads=(_dyad(),),
    )


# --- bypass helper, mirroring test_legislature_invariants.py's `_with_*` pattern ----


def _with_dyads_bypassed(state: GameState, dyads: tuple[ConflictDyadState, ...]) -> GameState:
    """Splice `dyads` into `state.world` via a `model_copy` chain, which never revalidates
    anything at any level -- unlike a normal constructor call, which would re-run
    `WorldState`'s own tuple-level validator and defeat the bypass before `check_invariants`
    is ever reached."""
    bad_world = state.world.model_copy(update={"dyads": dyads})
    return state.model_copy(update={"world": bad_world})


def _with_conflicts_bypassed(
    state: GameState, conflicts: tuple[ForeignConflictState, ...]
) -> GameState:
    bad_world = state.world.model_copy(update={"conflicts": conflicts})
    return state.model_copy(update={"world": bad_world})


# --- sanity: the baseline itself is valid --------------------------------------


def test_the_valid_baseline_has_no_violations() -> None:
    assert _codes(_valid_state()) == set()


# --- foreign-profile dict-key rules: no per-model validator exists, so plain --
# --- construction already reaches check_invariants; no bypass needed ----------


def test_foreign_profile_id_empty_is_reachable_by_plain_construction() -> None:
    state = make_game_state(foreign_profiles={"": _profile()})
    assert "foreign_profile_id_empty" in _codes(state)


def test_foreign_profile_id_collides_with_country_is_reachable_by_plain_construction() -> None:
    # make_game_state's default player_country_id is "testland"; a foreign_profiles key equal
    # to it collides with a world.countries id without needing a second country.
    state = make_game_state(foreign_profiles={"testland": _profile()})
    assert "foreign_profile_id_collides_with_country" in _codes(state)


def test_foreign_profiles_insertion_order_is_not_semantic() -> None:
    """Resolves the dictionary-order clarification (module docstring): the same two profiles,
    constructed in two different insertion orders, are both valid and serialize byte-identically
    -- canonical JSON already sorts keys, so insertion order carries no semantic weight and no
    invariant may reject one order over the other."""
    forward = make_game_state(
        foreign_profiles={
            "kessia": _profile("Kessia", 5_000),
            "vetruska": _profile("Vetruska", 5_600),
        },
        dyads=(_dyad(),),
    )
    reversed_order = make_game_state(
        foreign_profiles={
            "vetruska": _profile("Vetruska", 5_600),
            "kessia": _profile("Kessia", 5_000),
        },
        dyads=(_dyad(),),
    )
    assert _codes(forward) == set()
    assert _codes(reversed_order) == set()
    assert canonical_dumps(forward.world.model_dump(mode="json")) == canonical_dumps(
        reversed_order.world.model_dump(mode="json")
    )


# --- dyad cross-reference rules: ConflictDyadState cannot see WorldState, so ---
# --- these too are reachable by plain construction -----------------------------


def test_dyad_country_is_player_is_reachable_by_plain_construction() -> None:
    state = make_game_state(
        foreign_profiles={"kessia": _profile()},
        dyads=(
            _dyad(
                country_a="kessia", country_b="testland", aggressor="testland", defender="kessia"
            ),
        ),
    )
    assert "dyad_country_is_player" in _codes(state)


def test_dyad_country_unknown_is_reachable_by_plain_construction() -> None:
    state = make_game_state(
        foreign_profiles={"kessia": _profile()},
        dyads=(
            _dyad(country_a="kessia", country_b="nowhere", aggressor="nowhere", defender="kessia"),
        ),
    )
    assert "dyad_country_unknown" in _codes(state)


def test_foreign_profile_required_for_dyad_member_is_reachable_by_plain_construction() -> None:
    # "testneighbor" is a world.countries id (via the explicit countries= override below) but
    # never a foreign_profiles key -- the exact "known country, wrong namespace" case.
    state = make_game_state(
        countries={
            "testland": make_country("testland"),
            "testneighbor": make_country("testneighbor", with_politics=False),
        },
        foreign_profiles={"kessia": _profile()},
        dyads=(
            _dyad(
                country_a="kessia",
                country_b="testneighbor",
                aggressor="testneighbor",
                defender="kessia",
            ),
        ),
    )
    assert "foreign_profile_required_for_dyad_member" in _codes(state)


# --- conflict cross-reference rules: same reasoning as dyads -------------------


def test_conflict_country_is_player_is_reachable_by_plain_construction() -> None:
    state = make_game_state(
        foreign_profiles={"kessia": _profile()},
        conflicts=(
            _conflict(
                conflict_id="kessia__testland__t0",
                country_a="kessia",
                country_b="testland",
                aggressor="testland",
                defender="kessia",
            ),
        ),
    )
    assert "conflict_country_is_player" in _codes(state)


def test_conflict_country_unknown_is_reachable_by_plain_construction() -> None:
    state = make_game_state(
        foreign_profiles={"kessia": _profile()},
        conflicts=(
            _conflict(
                conflict_id="kessia__nowhere__t0",
                country_a="kessia",
                country_b="nowhere",
                aggressor="nowhere",
                defender="kessia",
            ),
        ),
    )
    assert "conflict_country_unknown" in _codes(state)


# --- tuple-level duplicate/order rules: guarded at construction time, so ------
# --- reaching check_invariants requires the model_copy bypass ------------------


def test_dyad_duplicate_pair_is_caught_by_check_invariants_when_construction_is_bypassed() -> None:
    base = _valid_state()
    # First, confirm the SAME defect is normally rejected at construction time (the validator
    # this backstop mirrors), so the bypass below is proven to be doing something real.
    with pytest.raises(ValidationError):
        WorldState(
            countries=base.world.countries,
            player_country_id=base.world.player_country_id,
            foreign_profiles=base.world.foreign_profiles,
            dyads=(_dyad(), _dyad()),
        )
    bypassed = _with_dyads_bypassed(base, (_dyad(), _dyad()))
    assert "dyad_duplicate_pair" in _codes(bypassed)


def test_dyad_pair_not_canonical_tuple_level_is_caught_by_check_invariants_when_bypassed() -> None:
    base = make_game_state(
        foreign_profiles={
            "kessia": _profile("Kessia"),
            "marnil": _profile("Marnil"),
            "zzz": _profile("Zzz"),
        },
    )
    # Two individually-valid, individually-canonical dyads (each satisfies its own
    # country_a < country_b) whose TUPLE order is descending -- only the tuple-level check can
    # catch this, since neither dyad's own field-level ordering validator sees the other.
    out_of_order = (
        _dyad(country_a="marnil", country_b="zzz", aggressor="marnil", defender="zzz"),
        _dyad(country_a="kessia", country_b="marnil", aggressor="marnil", defender="kessia"),
    )
    bypassed = _with_dyads_bypassed(base, out_of_order)
    assert "dyad_pair_not_canonical" in _codes(bypassed)


def test_conflict_duplicate_id_is_caught_by_check_invariants_when_bypassed() -> None:
    base = _valid_state()
    duplicate = (_conflict(), _conflict())
    bypassed = _with_conflicts_bypassed(base, duplicate)
    assert "conflict_duplicate_id" in _codes(bypassed)


def test_conflict_ids_not_canonical_tuple_level_is_caught_by_check_invariants_when_bypassed() -> (
    None
):
    base = make_game_state(
        foreign_profiles={
            "kessia": _profile("Kessia"),
            "marnil": _profile("Marnil"),
            "zzz": _profile("Zzz"),
        },
    )
    out_of_order = (
        _conflict(
            conflict_id="marnil__zzz__t0",
            country_a="marnil",
            country_b="zzz",
            aggressor="marnil",
            defender="zzz",
        ),
        _conflict(
            conflict_id="kessia__marnil__t0",
            country_a="kessia",
            country_b="marnil",
            aggressor="marnil",
            defender="kessia",
        ),
    )
    bypassed = _with_conflicts_bypassed(base, out_of_order)
    assert "conflict_ids_not_canonical" in _codes(bypassed)


# --- resolved_turn/status coherence: ForeignConflictState's own validator ------
# --- already guards this at construction time; check_invariants mirrors it ----


def test_conflict_terminal_status_requires_resolved_turn_is_caught_when_bypassed() -> None:
    """`ForeignConflictState`'s own `_resolved_turn_matches_terminal_status` validator rejects
    `status=SETTLED, resolved_turn=None` at construction time -- proven first, then the same
    defect is spliced past that validator via `model_copy(update=...)` (which never revalidates,
    per the module docstring) and shown to be caught independently by `check_invariants`."""
    with pytest.raises(ValidationError):
        _conflict(status=ConflictStatus.SETTLED, resolved_turn=None)

    bad = _conflict().model_copy(update={"status": ConflictStatus.SETTLED})
    bypassed = _with_conflicts_bypassed(_valid_state(), (bad,))
    assert "conflict_terminal_status_requires_resolved_turn" in _codes(bypassed)


def test_conflict_resolved_turn_requires_terminal_status_is_caught_when_bypassed() -> None:
    with pytest.raises(ValidationError):
        _conflict(status=ConflictStatus.ACTIVE, resolved_turn=5)

    bad = _conflict().model_copy(update={"resolved_turn": 5})
    bypassed = _with_conflicts_bypassed(_valid_state(), (bad,))
    assert "conflict_resolved_turn_requires_terminal_status" in _codes(bypassed)


# --- fix-forward 6b: the global concurrency cap, MAX_CONCURRENT_CONFLICTS -------
# --- slot 7's own guard stops a legitimate campaign from ever REACHING three; ---
# --- this is the backstop against a save that already CONTAINS three -----------


def _concurrency_state(
    profiles: dict[str, ForeignProfileState], conflicts: tuple[ForeignConflictState, ...]
) -> GameState:
    """A state with three independent foreign-profile pairs available, so up to three distinct
    conflicts can be constructed without colliding on `conflict_id` or canonical pair order.
    `conflicts` is passed straight through `WorldState`'s own real constructor, so every
    conflict-level construction-time invariant (canonical id order, no duplicate ids, resolved
    turn/status coherence) is already satisfied here -- only the concurrency count is new."""
    return make_game_state(foreign_profiles=profiles, dyads=(), conflicts=conflicts)


_CONCURRENCY_PROFILES = {
    "alpha": _profile("Alpha", 5_000),
    "beta": _profile("Beta", 5_000),
    "gamma": _profile("Gamma", 5_000),
    "delta": _profile("Delta", 5_000),
    "epsilon": _profile("Epsilon", 5_000),
    "zeta": _profile("Zeta", 5_000),
}


def _live_conflict(pair: tuple[str, str], *, status: ConflictStatus = ConflictStatus.ACTIVE):  # type: ignore[no-untyped-def]
    country_a, country_b = pair
    return _conflict(
        conflict_id=f"{country_a}__{country_b}__t0",
        country_a=country_a,
        country_b=country_b,
        aggressor=country_a,
        defender=country_b,
        status=status,
    )


def _terminal_conflict(pair: tuple[str, str]):  # type: ignore[no-untyped-def]
    country_a, country_b = pair
    return _conflict(
        conflict_id=f"{country_a}__{country_b}__t0",
        country_a=country_a,
        country_b=country_b,
        aggressor=country_a,
        defender=country_b,
        status=ConflictStatus.DECIDED,
        resolved_turn=0,
    )


_PAIR_1 = ("alpha", "beta")
_PAIR_2 = ("delta", "gamma")
_PAIR_3 = ("epsilon", "zeta")


@pytest.mark.parametrize("live_count", [0, 1, MAX_CONCURRENT_CONFLICTS])
def test_up_to_the_cap_live_conflicts_are_accepted(live_count: int) -> None:
    pairs = (_PAIR_1, _PAIR_2, _PAIR_3)[:live_count]
    conflicts = tuple(_live_conflict(pair) for pair in pairs)
    state = _concurrency_state(_CONCURRENCY_PROFILES, conflicts)
    assert "foreign_conflict_concurrency_exceeded" not in _codes(state)


def test_one_more_than_the_cap_live_conflicts_is_rejected() -> None:
    """Uses `MAX_CONCURRENT_CONFLICTS` directly rather than a hardcoded `3`, so the test tracks
    the shared constant instead of duplicating its value."""
    pairs = (_PAIR_1, _PAIR_2, _PAIR_3)[: MAX_CONCURRENT_CONFLICTS + 1]
    conflicts = tuple(_live_conflict(pair) for pair in pairs)
    state = _concurrency_state(_CONCURRENCY_PROFILES, conflicts)
    assert "foreign_conflict_concurrency_exceeded" in _codes(state)


def test_any_number_of_settled_and_decided_conflicts_consumes_no_capacity() -> None:
    conflicts = tuple(_terminal_conflict(pair) for pair in (_PAIR_1, _PAIR_2, _PAIR_3))
    state = _concurrency_state(_CONCURRENCY_PROFILES, conflicts)
    assert "foreign_conflict_concurrency_exceeded" not in _codes(state)


def test_the_cap_plus_terminal_history_is_accepted() -> None:
    """Two live conflicts (`MAX_CONCURRENT_CONFLICTS` at its current value of 2) plus a third,
    unrelated pair's terminal history must not trip the cap -- only ACTIVE/CEASEFIRE count."""
    assert MAX_CONCURRENT_CONFLICTS == 2, "this test's pair split assumes the current cap value"
    live = (_live_conflict(_PAIR_1), _live_conflict(_PAIR_2))
    terminal = (_terminal_conflict(_PAIR_3),)
    state = _concurrency_state(_CONCURRENCY_PROFILES, live + terminal)
    assert "foreign_conflict_concurrency_exceeded" not in _codes(state)


def test_concurrency_check_is_insensitive_to_foreign_profiles_insertion_order() -> None:
    pairs = (_PAIR_1, _PAIR_2, _PAIR_3)[: MAX_CONCURRENT_CONFLICTS + 1]
    conflicts = tuple(_live_conflict(pair) for pair in pairs)
    forward = _concurrency_state(_CONCURRENCY_PROFILES, conflicts)
    reversed_profiles = dict(reversed(list(_CONCURRENCY_PROFILES.items())))
    backward = _concurrency_state(reversed_profiles, conflicts)
    assert _codes(forward) == _codes(backward)
    assert "foreign_conflict_concurrency_exceeded" in _codes(forward)


# --- scenario-content isolation: relative to c47fc82, only content_version, ---
# --- foreign_profiles and dyads may have changed -------------------------------


@pytest.mark.parametrize(
    "scenario_file", ["tiny_valid.yaml", "decree_state.yaml", "deficit_demo.yaml"]
)
def test_scenario_content_is_isolated_to_the_w1_paths(scenario_file: str) -> None:
    """Everything else in the scenario -- countries (including `neighbor`), and every economic,
    fiscal, political, constitutional and calibration field -- is byte-identical to the
    pre-W1 (`c47fc82`) authored content once `content_version`/`foreign_profiles`/`dyads` are
    removed from both sides. The pre-W1 side is a stable literal recorded at authoring time
    (module-level `_PRE_W1_SCENARIO_DIGEST_BLAKE2B`); this test performs no git invocation."""
    with (SCENARIOS_DIR / scenario_file).open(encoding="utf-8") as handle:
        current = yaml.safe_load(handle)
    stripped = {
        key: value
        for key, value in current.items()
        if key not in ("content_version", "foreign_profiles", "dyads")
    }
    assert canonical_digest(stripped) == _PRE_W1_SCENARIO_DIGEST_BLAKE2B[scenario_file]


@pytest.mark.parametrize(
    "scenario_file", ["tiny_valid.yaml", "decree_state.yaml", "deficit_demo.yaml"]
)
def test_every_scenario_has_exactly_the_w1_paths_present(scenario_file: str) -> None:
    with (SCENARIOS_DIR / scenario_file).open(encoding="utf-8") as handle:
        current = yaml.safe_load(handle)
    assert current["content_version"] == "0.13.0"
    assert isinstance(current["foreign_profiles"], dict) and len(current["foreign_profiles"]) == 2
    assert isinstance(current["dyads"], list) and len(current["dyads"]) == 1


# --- save compatibility: the authentic commit-2 fixture must be rejected ------
# --- before any entry payload is parsed -----------------------------------------


def test_frozen_phase4a_save_fixture_declares_the_old_ruleset_version() -> None:
    raw = json.loads(PHASE4A_SAVE_PATH.read_text(encoding="utf-8"))
    assert raw["ruleset_version"] == "0.12.0"
    assert raw["content_version"] == "0.12.0"
    assert raw["ruleset_version"] != RULESET_VERSION


def test_phase4a_save_is_rejected_with_an_actionable_ruleset_version_error() -> None:
    raw_text = read_save_file(PHASE4A_SAVE_PATH)
    with pytest.raises(UnsupportedRulesetVersionError) as exc_info:
        load_save_json(raw_text, source=str(PHASE4A_SAVE_PATH))

    message = str(exc_info.value)
    assert "0.12.0" in message
    assert RULESET_VERSION in message
    assert "not loaded" in message


def test_phase4a_save_compatibility_is_checked_before_any_entry_payload_is_parsed() -> None:
    """Poison a deep entry payload (invalid JSON inside `state_json`) while preserving the
    fixture's unsupported `0.12.0` ruleset metadata untouched. The same
    `UnsupportedRulesetVersionError` must fire regardless -- proving the version gate runs
    before any entry payload is ever parsed."""
    raw = json.loads(read_save_file(PHASE4A_SAVE_PATH))
    raw["entries"][0]["state_json"] = "{not even valid json"

    with pytest.raises(UnsupportedRulesetVersionError):
        load_save_json(json.dumps(raw), source="corrupted-and-incompatible-w1")


def test_ruleset_and_save_format_versions_are_current() -> None:
    assert RULESET_VERSION == "0.13.0"
    assert SAVE_FORMAT_VERSION == 1


def test_no_migration_path_exists_for_the_pre_w1_ruleset() -> None:
    """`SUPPORTED_RULESET_VERSIONS` names exactly one version -- the current one. A migration
    path would need a second, older version present in this set; there is none, and no
    foreign-conflict state is ever synthesized for a save that predates it."""
    assert frozenset({"0.13.0"}) == SUPPORTED_RULESET_VERSIONS
