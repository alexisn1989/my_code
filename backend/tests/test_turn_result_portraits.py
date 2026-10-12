"""Gate 4A3 M-4: the turn result's people carry the likeness they had ON THAT TURN.

The bargain, cabinet, assistance and promise entries store a character id and display name, but no
portrait. `build_turn_result` adds `*_portrait_ref` from the state the recorded turn PRODUCED --
the same `state` argument it already reads bloc names from -- so:

* History depicts a turn exactly as live did, whatever later turns change;
* a character absent from that turn's state gets no key (the name stands alone); there is no
  fallback to any other state;
* the stored report is untouched.
"""

from __future__ import annotations

import inspect

from app.api import projections
from app.api.projections import build_turn_result
from app.content.scenarios import load_scenario_file
from app.simulation.decisions import (
    BudgetDecision,
    CabinetDecision,
    CabinetOrder,
    DecisionSet,
    LegislativeBargainDecision,
)
from app.simulation.history import GameSave, advance_game, new_game
from app.simulation.legislature import ProposalRoute
from app.simulation.save_format import SAVE_FORMAT_VERSION
from app.simulation.state import CabinetPost, GameState
from tests.conftest import SCENARIO_DIR

_CoS = CabinetPost.CHIEF_OF_STAFF
_LEADER = "leader_rural_alliance"


def _advance(save: GameSave, *decisions: object) -> GameSave:
    state = save.current_state()
    return advance_game(
        save,
        DecisionSet(
            expected_turn=state.turn,
            expected_state_version=state.state_version,
            decisions=sorted(decisions, key=lambda d: d.kind),  # type: ignore[attr-defined]
        ),
    )


def _bargain_and_cabinet_turn() -> GameSave:
    save = new_game(
        load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml"),
        save_format_version=SAVE_FORMAT_VERSION,
    )
    return _advance(
        save,
        BudgetDecision(personal_income_rate_bps=1_800, route=ProposalRoute.LEGISLATIVE),
        LegislativeBargainDecision(character_id=_LEADER, proposal_kind="budget"),
        CabinetDecision(orders=(CabinetOrder(post=_CoS, character_id="wren_hollis"),)),
    )


def _people(result) -> dict[str, dict[str, str | int]]:  # type: ignore[no-untyped-def]
    return {d.reason_id: dict(d.params) for d in result.drivers if "character_id" in d.params}


def _without_character(state: GameState, character_id: str) -> GameState:
    world = state.world.model_copy(
        update={
            "characters": {k: v for k, v in state.world.characters.items() if k != character_id}
        }
    )
    return state.model_copy(update={"world": world})


def test_people_carry_their_portrait_from_the_turns_own_state() -> None:
    save = _bargain_and_cabinet_turn()
    entry = save.entries[-1]
    report = entry.report()
    assert report is not None
    state = entry.state()
    people = _people(build_turn_result(state, report))
    assert "legislative_bargain_accepted" in people, "anti-vacuity: the bargain was struck"
    assert "cabinet_replaced" in people, "anti-vacuity: the post changed hands"
    bargain = people["legislative_bargain_accepted"]
    assert bargain["character_portrait_ref"] == state.world.characters[_LEADER].portrait_ref
    replaced = people["cabinet_replaced"]
    assert replaced["character_portrait_ref"] == state.world.characters["wren_hollis"].portrait_ref
    outgoing = str(replaced["outgoing_character_id"])
    assert (
        replaced["outgoing_character_portrait_ref"] == state.world.characters[outgoing].portrait_ref
    )
    # Presentation only: the stored entries carry no portrait.
    assert not any(key.endswith("portrait_ref") for e in report.entries for key in e.params)


def test_history_after_later_turns_depicts_the_turn_exactly_as_live_did() -> None:
    save = _bargain_and_cabinet_turn()
    live_entry = save.entries[-1]
    live_report = live_entry.report()
    assert live_report is not None
    live = build_turn_result(live_entry.state(), live_report)
    turn = live_entry.state().turn

    # Later turns change the cabinet again: wren_hollis is dismissed, then hal_verrin returns.
    later = _advance(save, CabinetDecision(orders=(CabinetOrder(post=_CoS),)))
    later = _advance(
        later, CabinetDecision(orders=(CabinetOrder(post=_CoS, character_id="hal_verrin"),))
    )
    historical = later.entry_at(turn)
    history_report = historical.report()
    assert history_report is not None
    again = build_turn_result(historical.state(), history_report)
    assert again.model_dump_json() == live.model_dump_json()
    assert _people(again)["cabinet_replaced"]["character_portrait_ref"] == (
        historical.state().world.characters["wren_hollis"].portrait_ref
    )


def test_a_character_absent_from_that_turns_state_gets_no_portrait_and_no_fallback() -> None:
    save = _bargain_and_cabinet_turn()
    entry = save.entries[-1]
    report = entry.report()
    assert report is not None
    state = entry.state()
    baseline = build_turn_result(state, report)

    # Deleting the leader from ANOTHER state (today's, say) changes nothing: it is never consulted.
    today = _without_character(save.current_state(), _LEADER)
    assert today.world.characters.get(_LEADER) is None
    assert build_turn_result(state, report).model_dump_json() == baseline.model_dump_json()

    # Deleting the leader from the turn's OWN state removes the key -- no fallback is attempted.
    bargain = _people(build_turn_result(_without_character(state, _LEADER), report))[
        "legislative_bargain_accepted"
    ]
    assert "character_portrait_ref" not in bargain
    assert bargain["character_display_name"]  # the name still stands


def test_the_enrichment_reads_only_the_state_it_is_given() -> None:
    assert list(inspect.signature(projections._portrait_refs).parameters) == ["state"]
    source = inspect.getsource(projections._portrait_refs)
    assert "state.world.characters" in source
    for forbidden in ("session", "current_state", "decision_options", "build_decision_options"):
        assert forbidden not in source
    assert list(inspect.signature(projections._with_portrait_refs).parameters) == [
        "params",
        "portraits",
    ]
