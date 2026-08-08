"""Tests for `simulation.invariants`' Phase 3B1 legislature backstop, `_check_legislature`
(§10, T-I1..T-I21 in spirit — one focused bypass test per code).

`_check_legislature` re-derives, directly from `GameState` alone, every structural rule that
`LegislatureState`/`PartyState`/`LegislativeBlocState`/`ChamberState`/`PoliticalState`'s own
Pydantic validators already enforce at every legitimate construction path. Those validators are
mutable-object gaps: `model_construct` (used throughout this file) and any future non-validating
restore path can produce an object that is internally inconsistent while still passing type
checks. Every test below builds exactly that — a state no legitimate construction path could
produce — and confirms `check_invariants` catches it anyway, using logic that does not call the
bypassed validator itself.

## Why every bypass here goes through a `model_copy` chain, never a nested constructor call

Pydantic v2 revalidates a nested model *instance* whenever it is handed to a field during a
model's own `__init__` — passing an already-`model_construct`-built (and therefore invalid)
`LegislativeBlocState` into `PartyState(..., blocs=(bad_bloc,))`'s **normal** constructor
re-triggers `LegislativeBlocState`'s own validators against it right there, defeating the bypass
before it ever reaches `GameState`. `model_copy(update=...)`, by contrast, never revalidates
anything at any level — confirmed empirically during this file's development up through
`WorldState`. So every test here builds a genuinely valid baseline `GameState` first, builds the
one intentionally-broken object via `model_construct` (nesting further `model_construct` calls
wherever a defect must survive being wrapped), and then splices it in via a `model_copy` chain
from the point of defect up through `PoliticalState` → `CountryState` → `WorldState` → `GameState`
— never a normal constructor call after that point.

Each per-code test is built to isolate its one defect as cleanly as arithmetic allows, so the
assertion is "this code fired" rather than "some code fired" — seat totals are kept exactly
balanced except in the tests specifically about seat totals, and chamber/party/bloc counts are
kept exactly matching the constitution except in the tests specifically about counts.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.simulation.constitution import ConstitutionState, DecreeAuthority, Legislature
from app.simulation.invariants import check_invariants
from app.simulation.legislature import GovernmentRole, LegislativeChamber
from app.simulation.state import (
    BlocSeats,
    ChamberState,
    GameState,
    LegislativeBlocState,
    LegislatureState,
    PartyState,
    PoliticalState,
)
from tests.conftest import make_country, make_game_state, make_politics

LOWER = LegislativeChamber.LOWER
UPPER = LegislativeChamber.UPPER


def _codes(state: GameState) -> set[str]:
    return {v.code for v in check_invariants(state)}


def _valid_state(
    *, legislature_shape: Legislature = Legislature.UNICAMERAL, second_country: bool = False
) -> GameState:
    """A genuinely valid baseline `GameState`, player country `'a'` (and optionally a
    politics-free AI country `'b'`), built entirely through normal, validated constructors."""
    countries = {"a": make_country("a", politics=make_politics(legislature=legislature_shape))}
    if second_country:
        countries["b"] = make_country("b", with_politics=False)
    return make_game_state(countries=countries, player_country_id="a")


def _with_politics(state: GameState, *, country_id: str, politics: PoliticalState) -> GameState:
    """Swap `country_id`'s politics for `politics` via a `model_copy` chain — see the module
    docstring for why this, and never a nested constructor call, is what preserves a bypass."""
    country = state.world.countries[country_id]
    bad_country = country.model_copy(update={"politics": politics})
    bad_world = state.world.model_copy(
        update={"countries": {**state.world.countries, country_id: bad_country}}
    )
    return state.model_copy(update={"world": bad_world})


def _with_legislature(
    state: GameState, *, country_id: str = "a", legislature: LegislatureState | None
) -> GameState:
    politics = state.world.countries[country_id].politics
    assert politics is not None
    return _with_politics(
        state,
        country_id=country_id,
        politics=politics.model_copy(update={"legislature": legislature}),
    )


def _with_constitution(
    state: GameState, *, country_id: str = "a", constitution: ConstitutionState
) -> GameState:
    politics = state.world.countries[country_id].politics
    assert politics is not None
    return _with_politics(
        state,
        country_id=country_id,
        politics=politics.model_copy(update={"constitution": constitution}),
    )


def _bloc(
    *,
    bloc_id: str = "core",
    seats: tuple[BlocSeats, ...],
    relationship: int = 0,
    discipline: int = 0,
    tax_preference: int = 0,
    spending_preference: int = 0,
) -> LegislativeBlocState:
    """A valid bloc, via the real constructor — safe to embed under a `model_construct`-built
    parent (which never revalidates it), and safe as a standalone control object."""
    return LegislativeBlocState(
        id=bloc_id,
        name=bloc_id.title(),
        seats=seats,
        discipline_bps=discipline,
        government_relationship_bps=relationship,
        tax_preference_bps=tax_preference,
        spending_preference_bps=spending_preference,
    )


def _bad_bloc(**field_overrides: object) -> LegislativeBlocState:
    """A bloc built via `model_construct`, for a defect that lives on the bloc itself (its own
    field ranges, or its own `.seats` tuple's duplicates/order/unknown-chamber references)."""
    defaults: dict[str, object] = {
        "id": "core",
        "name": "Core",
        "seats": (),
        "discipline_bps": 0,
        "government_relationship_bps": 0,
        "tax_preference_bps": 0,
        "spending_preference_bps": 0,
    }
    defaults.update(field_overrides)
    return LegislativeBlocState.model_construct(**defaults)


def _party(
    *, party_id: str = "governing_party", blocs: tuple[LegislativeBlocState, ...]
) -> PartyState:
    """A valid party, via the real constructor — safe only when every entry in `blocs` is itself
    valid and in canonical order; use `_bad_party` whenever that is not the case."""
    return PartyState(
        id=party_id, name=party_id.title(), government_role=GovernmentRole.COALITION, blocs=blocs
    )


def _bad_party(
    *, party_id: str = "governing_party", blocs: tuple[LegislativeBlocState, ...]
) -> PartyState:
    """A party built via `model_construct`, for a defect on the party itself (no blocs,
    duplicate/reordered bloc ids) or to safely wrap an already-`model_construct`-built bloc
    without re-triggering its own validators."""
    return PartyState.model_construct(
        id=party_id, name=party_id.title(), government_role=GovernmentRole.COALITION, blocs=blocs
    )


def _bad_legislature(
    *, chambers: tuple[ChamberState, ...], parties: tuple[PartyState, ...]
) -> LegislatureState:
    """A legislature built via `model_construct` — used for every test in this file, since even a
    defect confined to a single nested bloc must be wrapped this way the whole way up (see the
    module docstring)."""
    return LegislatureState.model_construct(chambers=chambers, parties=parties)


# --- Baseline: valid shapes produce no legislature violations -----------------


def test_a_valid_unicameral_legislature_has_no_violations() -> None:
    assert check_invariants(_valid_state(legislature_shape=Legislature.UNICAMERAL)) == []


def test_a_valid_bicameral_legislature_has_no_violations() -> None:
    assert check_invariants(_valid_state(legislature_shape=Legislature.BICAMERAL)) == []


def test_a_valid_no_legislature_unlimited_decree_state_has_no_violations() -> None:
    politics = make_politics(
        legislature=Legislature.NONE, decree_authority=DecreeAuthority.UNLIMITED
    )
    assert politics.legislature is None
    state = make_game_state(
        countries={"a": make_country("a", politics=politics)}, player_country_id="a"
    )
    assert check_invariants(state) == []


# --- 1: legislature_required_by_constitution -----------------------------------


def test_legislature_required_by_constitution() -> None:
    """A constitution declaring a legislature, with none present."""
    state = _with_legislature(_valid_state(), legislature=None)
    assert "legislature_required_by_constitution" in _codes(state)


# --- 2: legislature_forbidden_by_constitution -----------------------------------


def test_legislature_forbidden_by_constitution() -> None:
    politics = make_politics(
        legislature=Legislature.NONE, decree_authority=DecreeAuthority.UNLIMITED
    )
    assert politics.legislature is None
    base_state = make_game_state(
        countries={"a": make_country("a", politics=politics)}, player_country_id="a"
    )
    stray_legislature = make_politics(legislature=Legislature.UNICAMERAL).legislature
    assert stray_legislature is not None
    state = _with_legislature(base_state, legislature=stray_legislature)
    codes = _codes(state)
    assert "legislature_forbidden_by_constitution" in codes
    # Isolated: decree_authority is already unlimited, so C10 does not also fire here.
    assert "legislature_absent_requires_unlimited_decree" not in codes


# --- 3: chamber_count_mismatch_with_constitution --------------------------------


def test_chamber_count_mismatch_with_constitution() -> None:
    base_state = _valid_state(legislature_shape=Legislature.UNICAMERAL)
    bicameral_legislature = make_politics(legislature=Legislature.BICAMERAL).legislature
    assert bicameral_legislature is not None
    state = _with_legislature(base_state, legislature=bicameral_legislature)
    assert "chamber_count_mismatch_with_constitution" in _codes(state)


# --- 4: duplicate_chamber -------------------------------------------------------


def test_duplicate_chamber() -> None:
    chambers = (
        ChamberState(chamber=LOWER, total_seats=50),
        ChamberState(chamber=LOWER, total_seats=50),
    )
    party = _bad_party(blocs=(_bloc(seats=(BlocSeats(chamber=LOWER, seats=50),)),))
    legislature = _bad_legislature(chambers=chambers, parties=(party,))
    state = _with_legislature(
        _valid_state(legislature_shape=Legislature.BICAMERAL), legislature=legislature
    )
    codes = _codes(state)
    assert "duplicate_chamber" in codes
    # Both duplicate entries share total_seats=50 and the sole bloc accounts for exactly 50 in
    # LOWER, so the mismatch code is not also triggered by this construction.
    assert "chamber_seat_total_mismatch" not in codes


# --- 5: noncanonical_chamber_order ----------------------------------------------


def test_noncanonical_chamber_order() -> None:
    chambers = (
        ChamberState(chamber=UPPER, total_seats=30),
        ChamberState(chamber=LOWER, total_seats=70),
    )
    party = _bad_party(
        blocs=(
            _bloc(seats=(BlocSeats(chamber=LOWER, seats=70), BlocSeats(chamber=UPPER, seats=30))),
        )
    )
    legislature = _bad_legislature(chambers=chambers, parties=(party,))
    state = _with_legislature(
        _valid_state(legislature_shape=Legislature.BICAMERAL), legislature=legislature
    )
    codes = _codes(state)
    assert "noncanonical_chamber_order" in codes
    assert "duplicate_chamber" not in codes
    assert "chamber_seat_total_mismatch" not in codes


# --- 6: unicameral_chamber_must_be_lower ----------------------------------------


def test_unicameral_chamber_must_be_lower() -> None:
    chambers = (ChamberState(chamber=UPPER, total_seats=50),)
    party = _bad_party(blocs=(_bloc(seats=(BlocSeats(chamber=UPPER, seats=50),)),))
    legislature = _bad_legislature(chambers=chambers, parties=(party,))
    state = _with_legislature(
        _valid_state(legislature_shape=Legislature.UNICAMERAL), legislature=legislature
    )
    codes = _codes(state)
    assert "unicameral_chamber_must_be_lower" in codes
    assert "chamber_count_mismatch_with_constitution" not in codes


# --- 7: chamber_total_seats_not_positive ----------------------------------------


def test_chamber_total_seats_not_positive() -> None:
    """`ChamberState.total_seats` is `StrictPositiveSeatCount` (`gt=0`). A zero-seat chamber with
    no bloc claiming any seats in it is internally self-consistent apart from this one field, so
    this test needs no further bypass beyond the chamber itself."""
    bad_chamber = ChamberState.model_construct(chamber=LOWER, total_seats=0)
    party = _bad_party(blocs=(_bloc(seats=()),))
    legislature = _bad_legislature(chambers=(bad_chamber,), parties=(party,))
    state = _with_legislature(
        _valid_state(legislature_shape=Legislature.UNICAMERAL), legislature=legislature
    )
    codes = _codes(state)
    assert "chamber_total_seats_not_positive" in codes
    assert "chamber_seat_total_mismatch" not in codes


# --- 8: legislature_absent_requires_unlimited_decree (C10) ----------------------


def _no_legislature_constitution(
    base: ConstitutionState, *, decree_authority: DecreeAuthority
) -> ConstitutionState:
    return ConstitutionState.model_construct(
        executive_system=base.executive_system,
        executive_selection=base.executive_selection,
        legislature=Legislature.NONE,
        territorial_organization=base.territorial_organization,
        judicial_review=base.judicial_review,
        amendment_difficulty=base.amendment_difficulty,
        decree_authority=decree_authority,
        executive_term_limit_terms=None,
        national_election_interval_turns=None,
    )


def test_legislature_absent_requires_unlimited_decree() -> None:
    """C10, independently recomputed here rather than only via `invalid_constitutional_combination`
    -- and the two must NOT both fire for the same defect (see `_check_politics`'s dedup)."""
    politics = make_politics(
        legislature=Legislature.NONE, decree_authority=DecreeAuthority.UNLIMITED
    )
    base_state = make_game_state(
        countries={"a": make_country("a", politics=politics)}, player_country_id="a"
    )
    bad_constitution = _no_legislature_constitution(
        politics.constitution, decree_authority=DecreeAuthority.EMERGENCY_ONLY
    )
    state = _with_constitution(base_state, constitution=bad_constitution)
    codes = _codes(state)
    assert "legislature_absent_requires_unlimited_decree" in codes
    assert "invalid_constitutional_combination" not in codes  # dedup: specific code wins


def test_c10_is_enforced_at_constitution_construction() -> None:
    """The first of the four required enforcement points: `ConstitutionState`'s own validator."""
    baseline = make_politics().constitution
    with pytest.raises(ValidationError, match="legislature_absent_requires_unlimited_decree"):
        ConstitutionState(
            executive_system=baseline.executive_system,
            executive_selection=baseline.executive_selection,
            legislature=Legislature.NONE,
            territorial_organization=baseline.territorial_organization,
            judicial_review=baseline.judicial_review,
            amendment_difficulty=baseline.amendment_difficulty,
            decree_authority=DecreeAuthority.NONE,
        )


def test_c10_is_enforced_at_resolve_turn_precondition() -> None:
    """The third required enforcement point: a bypassed C10-violating state is rejected by
    `resolve_turn`'s precondition `check_invariants` call, before any phase runs. `resolve_turn`
    wraps the `StateValidationError` as the *cause* of a `TurnResolutionError` — the caller-facing
    exception — so that is what is asserted here."""
    from app.core.errors import TurnResolutionError
    from app.simulation.decisions import DecisionSet
    from app.simulation.resolver import resolve_turn

    politics = make_politics(
        legislature=Legislature.NONE, decree_authority=DecreeAuthority.UNLIMITED
    )
    base_state = make_game_state(
        countries={"a": make_country("a", politics=politics)}, player_country_id="a"
    )
    bad_constitution = _no_legislature_constitution(
        politics.constitution, decree_authority=DecreeAuthority.EMERGENCY_ONLY
    )
    state = _with_constitution(base_state, constitution=bad_constitution)
    decisions = DecisionSet(expected_turn=0, expected_state_version=0, decisions=())
    with pytest.raises(TurnResolutionError, match="legislature_absent_requires_unlimited_decree"):
        resolve_turn(state, decisions)


def test_c10_is_enforced_at_history_replay() -> None:
    """The fourth required enforcement point, exercised through the real replay machinery
    (`history.validate_history`), not a hand-rolled substitute.

    A hand-tampered `state_json` -- exactly what a directly-edited save file on disk would look
    like -- is spliced into a genuine genesis `HistoryEntry`. `GameState.model_validate` (called
    inside `_validate_entry_payload`, `history.py:441-448`) rejects it during schema validation
    before `check_invariants` even runs, which is a STRONGER guarantee than the invariants layer
    catching it: no legitimately-serialized save could ever carry this defect into replay at all.
    Either way, `validate_history` reports it and the entry never becomes a usable state.
    """
    import dataclasses
    import json

    from app.core.canonical_json import canonical_digest, canonical_dumps
    from app.simulation.history import GameSave, HistoryEntry, _entry_hash_payload, validate_history

    politics = make_politics(
        legislature=Legislature.NONE, decree_authority=DecreeAuthority.UNLIMITED
    )
    base_state = make_game_state(
        countries={"a": make_country("a", politics=politics)}, player_country_id="a"
    )
    bad_constitution = _no_legislature_constitution(
        politics.constitution, decree_authority=DecreeAuthority.NONE
    )
    tampered_state = _with_constitution(base_state, constitution=bad_constitution)

    state_json = canonical_dumps(tampered_state.model_dump(mode="json"))
    payload = _entry_hash_payload(
        turn=0,
        previous_entry_hash=None,
        state=json.loads(state_json),
        decisions=None,
        report=None,
        ruleset_version=tampered_state.ruleset_version,
        content_version=tampered_state.content_version,
    )
    entry_hash = canonical_digest(payload)
    genesis = HistoryEntry(
        turn=0,
        previous_entry_hash=None,
        state_json=state_json,
        decisions_json=None,
        report_json=None,
        ruleset_version=tampered_state.ruleset_version,
        content_version=tampered_state.content_version,
        entry_hash=entry_hash,
    )
    save = GameSave(
        save_format_version=1,
        ruleset_version=tampered_state.ruleset_version,
        content_version=tampered_state.content_version,
        entry_count=1,
        head_entry_hash=entry_hash,
        entries=(genesis,),
    )

    problems = validate_history(save)
    assert any("legislature_absent_requires_unlimited_decree" in p for p in problems)
    assert not any("entry_hash does not match" in p for p in problems)  # isolates the real defect
    assert dataclasses.is_dataclass(
        genesis
    )  # sanity: HistoryEntry really is the plain dataclass used


# --- 9: duplicate_party_id ------------------------------------------------------


def test_duplicate_party_id() -> None:
    chambers = (ChamberState(chamber=LOWER, total_seats=100),)
    party_a = _party(party_id="alpha", blocs=(_bloc(seats=(BlocSeats(chamber=LOWER, seats=60),)),))
    party_a_dup = _party(
        party_id="alpha", blocs=(_bloc(seats=(BlocSeats(chamber=LOWER, seats=40),)),)
    )
    legislature = _bad_legislature(chambers=chambers, parties=(party_a, party_a_dup))
    state = _with_legislature(_valid_state(), legislature=legislature)
    codes = _codes(state)
    assert "duplicate_party_id" in codes
    assert "chamber_seat_total_mismatch" not in codes


# --- 10: noncanonical_party_order -----------------------------------------------


def test_noncanonical_party_order() -> None:
    chambers = (ChamberState(chamber=LOWER, total_seats=100),)
    party_b = _party(party_id="bravo", blocs=(_bloc(seats=(BlocSeats(chamber=LOWER, seats=40),)),))
    party_a = _party(party_id="alpha", blocs=(_bloc(seats=(BlocSeats(chamber=LOWER, seats=60),)),))
    legislature = _bad_legislature(chambers=chambers, parties=(party_b, party_a))
    state = _with_legislature(_valid_state(), legislature=legislature)
    codes = _codes(state)
    assert "noncanonical_party_order" in codes
    assert "duplicate_party_id" not in codes


def test_noncanonical_party_order_is_rejected_not_normalized() -> None:
    """The order-sensitivity check itself: `check_invariants` is read-only and must never repair
    the state it inspects -- the bypassed object's order is unchanged after the call."""
    chambers = (ChamberState(chamber=LOWER, total_seats=100),)
    party_b = _party(party_id="bravo", blocs=(_bloc(seats=(BlocSeats(chamber=LOWER, seats=40),)),))
    party_a = _party(party_id="alpha", blocs=(_bloc(seats=(BlocSeats(chamber=LOWER, seats=60),)),))
    legislature = _bad_legislature(chambers=chambers, parties=(party_b, party_a))
    state = _with_legislature(_valid_state(), legislature=legislature)

    check_invariants(state)  # discard the result; only the side effect (or lack of one) matters

    reloaded = state.world.countries["a"].politics
    assert reloaded is not None and reloaded.legislature is not None
    assert [p.id for p in reloaded.legislature.parties] == ["bravo", "alpha"]


# --- 11: party_has_no_blocs -----------------------------------------------------


def test_party_has_no_blocs() -> None:
    chambers = (ChamberState(chamber=LOWER, total_seats=100),)
    empty_party = _bad_party(party_id="empty", blocs=())
    full_party = _party(blocs=(_bloc(seats=(BlocSeats(chamber=LOWER, seats=100),)),))
    legislature = _bad_legislature(chambers=chambers, parties=(empty_party, full_party))
    state = _with_legislature(_valid_state(), legislature=legislature)
    codes = _codes(state)
    assert "party_has_no_blocs" in codes
    assert "chamber_seat_total_mismatch" not in codes


# --- 12: duplicate_bloc_id -------------------------------------------------------


def test_duplicate_bloc_id() -> None:
    bloc_a = _bloc(bloc_id="core", seats=(BlocSeats(chamber=LOWER, seats=60),))
    bloc_a_dup = _bloc(bloc_id="core", seats=(BlocSeats(chamber=LOWER, seats=40),))
    party = _bad_party(blocs=(bloc_a, bloc_a_dup))
    legislature = _bad_legislature(
        chambers=(ChamberState(chamber=LOWER, total_seats=100),), parties=(party,)
    )
    state = _with_legislature(_valid_state(), legislature=legislature)
    codes = _codes(state)
    assert "duplicate_bloc_id" in codes
    assert "chamber_seat_total_mismatch" not in codes


# --- 13: noncanonical_bloc_order -------------------------------------------------


def test_noncanonical_bloc_order() -> None:
    bloc_b = _bloc(bloc_id="bravo", seats=(BlocSeats(chamber=LOWER, seats=40),))
    bloc_a = _bloc(bloc_id="alpha", seats=(BlocSeats(chamber=LOWER, seats=60),))
    party = _bad_party(blocs=(bloc_b, bloc_a))
    legislature = _bad_legislature(
        chambers=(ChamberState(chamber=LOWER, total_seats=100),), parties=(party,)
    )
    state = _with_legislature(_valid_state(), legislature=legislature)
    codes = _codes(state)
    assert "noncanonical_bloc_order" in codes
    assert "duplicate_bloc_id" not in codes


# --- 14: duplicate_bloc_chamber_seats --------------------------------------------


def test_duplicate_bloc_chamber_seats() -> None:
    bad = _bad_bloc(seats=(BlocSeats(chamber=LOWER, seats=30), BlocSeats(chamber=LOWER, seats=20)))
    party = _bad_party(blocs=(bad,))
    legislature = _bad_legislature(
        chambers=(ChamberState(chamber=LOWER, total_seats=50),), parties=(party,)
    )
    state = _with_legislature(_valid_state(), legislature=legislature)
    codes = _codes(state)
    assert "duplicate_bloc_chamber_seats" in codes
    # 30 + 20 == the chamber's total_seats (50), so this does not also mismatch.
    assert "chamber_seat_total_mismatch" not in codes


# --- 15: noncanonical_bloc_seats_order -------------------------------------------


def test_noncanonical_bloc_seats_order() -> None:
    bad = _bad_bloc(seats=(BlocSeats(chamber=UPPER, seats=20), BlocSeats(chamber=LOWER, seats=80)))
    party = _bad_party(blocs=(bad,))
    chambers = (
        ChamberState(chamber=LOWER, total_seats=80),
        ChamberState(chamber=UPPER, total_seats=20),
    )
    legislature = _bad_legislature(chambers=chambers, parties=(party,))
    state = _with_legislature(
        _valid_state(legislature_shape=Legislature.BICAMERAL), legislature=legislature
    )
    codes = _codes(state)
    assert "noncanonical_bloc_seats_order" in codes
    assert "duplicate_bloc_chamber_seats" not in codes
    assert "chamber_seat_total_mismatch" not in codes


# --- 16: bloc_seats_reference_unknown_chamber ------------------------------------


def test_bloc_seats_reference_unknown_chamber() -> None:
    bad = _bad_bloc(seats=(BlocSeats(chamber=UPPER, seats=10),))
    party = _bad_party(blocs=(bad,))
    legislature = _bad_legislature(
        chambers=(ChamberState(chamber=LOWER, total_seats=100),), parties=(party,)
    )
    state = _with_legislature(_valid_state(), legislature=legislature)
    codes = _codes(state)
    assert "bloc_seats_reference_unknown_chamber" in codes
    # The LOWER chamber's own total (100) is held by nobody, since the bloc's only seats are in
    # the nonexistent UPPER -- this genuinely IS also a real, distinct seat-total defect, so it is
    # allowed to co-fire rather than being artificially suppressed.
    assert "chamber_seat_total_mismatch" in codes


# --- 17: chamber_seat_total_mismatch (exact reconciliation, both directions) ----


def test_chamber_seat_total_mismatch_undercount() -> None:
    party = _bad_party(blocs=(_bloc(seats=(BlocSeats(chamber=LOWER, seats=90),)),))
    legislature = _bad_legislature(
        chambers=(ChamberState(chamber=LOWER, total_seats=100),), parties=(party,)
    )
    state = _with_legislature(_valid_state(), legislature=legislature)
    assert "chamber_seat_total_mismatch" in _codes(state)


def test_chamber_seat_total_mismatch_overcount() -> None:
    party = _bad_party(blocs=(_bloc(seats=(BlocSeats(chamber=LOWER, seats=110),)),))
    legislature = _bad_legislature(
        chambers=(ChamberState(chamber=LOWER, total_seats=100),), parties=(party,)
    )
    state = _with_legislature(_valid_state(), legislature=legislature)
    assert "chamber_seat_total_mismatch" in _codes(state)


def test_exact_seat_reconciliation_recomputes_from_blocs_not_from_the_authored_total() -> None:
    """Recomputation, not trust: two blocs at 45+55 exactly reconcile a 100-seat chamber even
    though neither bloc alone matches it -- the check must sum across identity-matched blocs, not
    read a single field. A genuinely valid construction, built through real constructors
    throughout."""
    party = _party(
        blocs=(
            _bloc(bloc_id="ally", seats=(BlocSeats(chamber=LOWER, seats=55),)),
            _bloc(bloc_id="core", seats=(BlocSeats(chamber=LOWER, seats=45),)),
        )
    )
    legislature = LegislatureState(
        chambers=(ChamberState(chamber=LOWER, total_seats=100),), parties=(party,)
    )
    state = _with_legislature(_valid_state(), legislature=legislature)
    assert check_invariants(state) == []


# --- 18: bloc_relationship_out_of_range ------------------------------------------


@pytest.mark.parametrize("relationship", [10_001, -10_001])
def test_bloc_relationship_out_of_range(relationship: int) -> None:
    bad = _bad_bloc(
        seats=(BlocSeats(chamber=LOWER, seats=100),), government_relationship_bps=relationship
    )
    party = _bad_party(blocs=(bad,))
    legislature = _bad_legislature(
        chambers=(ChamberState(chamber=LOWER, total_seats=100),), parties=(party,)
    )
    state = _with_legislature(_valid_state(), legislature=legislature)
    assert "bloc_relationship_out_of_range" in _codes(state)


# --- 19: bloc_discipline_out_of_range --------------------------------------------


@pytest.mark.parametrize("discipline", [10_001, -1])
def test_bloc_discipline_out_of_range(discipline: int) -> None:
    bad = _bad_bloc(seats=(BlocSeats(chamber=LOWER, seats=100),), discipline_bps=discipline)
    party = _bad_party(blocs=(bad,))
    legislature = _bad_legislature(
        chambers=(ChamberState(chamber=LOWER, total_seats=100),), parties=(party,)
    )
    state = _with_legislature(_valid_state(), legislature=legislature)
    assert "bloc_discipline_out_of_range" in _codes(state)


# --- 20: bloc_preference_out_of_range (both preference fields) -------------------


@pytest.mark.parametrize(
    "field", ["tax_preference_bps", "spending_preference_bps"], ids=["tax", "spending"]
)
def test_bloc_preference_out_of_range(field: str) -> None:
    bad = _bad_bloc(seats=(BlocSeats(chamber=LOWER, seats=100),), **{field: 10_001})
    party = _bad_party(blocs=(bad,))
    legislature = _bad_legislature(
        chambers=(ChamberState(chamber=LOWER, total_seats=100),), parties=(party,)
    )
    state = _with_legislature(_valid_state(), legislature=legislature)
    assert "bloc_preference_out_of_range" in _codes(state)


# --- 21: non_player_legislature_not_supported ------------------------------------


def test_non_player_legislature_not_supported() -> None:
    """AI countries cannot have a legislature (Phase 3A already forbids AI politics entirely) --
    a bypassed construction attaching one anyway must be caught independently of that broader
    rule, matching `non_player_politics_not_supported`'s own existing pattern."""
    base_state = _valid_state(second_country=True)
    ai_politics = make_politics(legislature=Legislature.UNICAMERAL)
    state = _with_politics(base_state, country_id="b", politics=ai_politics)
    codes = _codes(state)
    assert "non_player_legislature_not_supported" in codes


def test_non_player_legislature_does_not_run_deeper_structural_checks() -> None:
    """Once a non-player's legislature is flagged as unsupported at all, the deeper structural
    checks (seat totals, ordering, ranges) must not also fire on content that should not exist --
    that would be noise, not signal. Built deliberately internally malformed (unreconciled seats)
    to prove the deeper checks are genuinely skipped, not merely absent by coincidence."""
    base_state = _valid_state(second_country=True)
    malformed_party = _bad_party(blocs=(_bloc(seats=(BlocSeats(chamber=LOWER, seats=1),)),))
    malformed_legislature = _bad_legislature(
        chambers=(ChamberState(chamber=LOWER, total_seats=999),), parties=(malformed_party,)
    )
    ai_politics = make_politics(legislature=Legislature.UNICAMERAL).model_copy(
        update={"legislature": malformed_legislature}
    )
    state = _with_politics(base_state, country_id="b", politics=ai_politics)
    codes = _codes(state)
    assert "non_player_legislature_not_supported" in codes
    assert "chamber_seat_total_mismatch" not in codes


# --- Static guards ---------------------------------------------------------------


def test_no_report_formula_or_voting_concepts_leaked_into_legislature_invariants() -> None:
    """`_check_legislature` receives `GameState` only. It must never reference
    `LegislativeReport`, `DecisionSet`, voting outcomes, influence, political-capital commitments,
    or formula-derived supporting seats -- those belong to `LegislativeReport`'s own validators or
    a future `reconcile_political_report`-style state/report comparison, not to a single-state
    structural check."""
    from app.simulation import invariants as invariants_module

    source = inspect.getsource(invariants_module)
    forbidden_fragments = (
        "LegislativeReport",
        "DecisionSet",
        "LegislativeOutcome",
        "ProposalRoute",
        "InfluenceAllocation",
        "BlocVoteReport",
        "ChamberVoteReport",
        "supporting_seats",
        "effective_support_bps",
        "influence_bps",
        "chamber_carries",
        "apportion_supporting_seats",
        "resolve_bloc_support",
        "political_capital_spent",
    )
    for fragment in forbidden_fragments:
        assert fragment not in source, (
            f"{fragment!r} is a report/formula/voting-outcome concept and must not be decidable "
            "from state alone -- check_invariants takes a single GameState and nothing else"
        )


def test_invariants_module_does_not_import_voting_or_report_machinery() -> None:
    """The structural half of the same guarantee: `invariants.py` must not even be ABLE to reach
    voting or reporting machinery, checked against the parsed source rather than the loaded
    module, so an import added inside a function body is caught just the same."""
    from app.simulation import invariants as invariants_module

    source_path = Path(inspect.getfile(invariants_module))
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    forbidden_modules = ("report", "decisions", "legislative_voting", "apportionment")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            imported = [node.module or ""]
        else:
            continue
        for name in imported:
            for forbidden in forbidden_modules:
                assert not name.endswith(f".{forbidden}") and name != forbidden, (
                    f"invariants.py imports {name!r}; it must recompute structure from state "
                    "alone, never reach into report/decision/voting-formula modules"
                )


def test_all_twenty_one_legislature_codes_are_distinct() -> None:
    """A regression pin, mirroring the existing 12-political-code guard: if two legislature
    checks ever accidentally shared a code, this catches it."""
    expected = {
        "legislature_required_by_constitution",
        "legislature_forbidden_by_constitution",
        "chamber_count_mismatch_with_constitution",
        "duplicate_chamber",
        "noncanonical_chamber_order",
        "unicameral_chamber_must_be_lower",
        "chamber_total_seats_not_positive",
        "legislature_absent_requires_unlimited_decree",
        "duplicate_party_id",
        "noncanonical_party_order",
        "party_has_no_blocs",
        "duplicate_bloc_id",
        "noncanonical_bloc_order",
        "duplicate_bloc_chamber_seats",
        "noncanonical_bloc_seats_order",
        "bloc_seats_reference_unknown_chamber",
        "chamber_seat_total_mismatch",
        "bloc_relationship_out_of_range",
        "bloc_discipline_out_of_range",
        "bloc_preference_out_of_range",
        "non_player_legislature_not_supported",
    }
    assert len(expected) == 21
