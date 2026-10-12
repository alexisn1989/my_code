"""Gate 4A3 M-4: the turn results the result-view unit tests render are BACKEND OUTPUT, pinned here.

Each entry of `frontend/src/test/turn-results.json` is `build_turn_result` over a turn really
resolved by `resolve_turn`, covering every state the proposal card has: a passed bicameral budget
with a bargain and a cabinet change, a failed budget, a decree, an amendment vote that failed and one
that passed, and a turn with no proposal. Regenerate with `MANDATE_REGENERATE_RESULT_FIXTURES=1`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from app.api.projections import build_turn_result
from app.simulation.decisions import (
    BudgetDecision,
    CabinetDecision,
    CabinetOrder,
    LegislativeBargainDecision,
)
from app.simulation.legislature import ProposalRoute
from app.simulation.state import CabinetPost, GameState
from tests.test_campaign_objective import FOUR_AXIS, _amend, _load, _resolve, _supportive

REPO = Path(__file__).resolve().parents[2]
RESULTS_JSON = REPO / "frontend" / "src" / "test" / "turn-results.json"
REGENERATE = os.environ.get("MANDATE_REGENERATE_RESULT_FIXTURES") == "1"


def _result(state: GameState, *decisions: object) -> dict[str, object]:
    opening = state.model_copy(deep=True)
    resolution = _resolve(state, *decisions)
    return build_turn_result(resolution.state, resolution.report, opening_state=opening).model_dump(
        mode="json"
    )


def _fixtures() -> dict[str, dict[str, object]]:
    return {
        "arkenBargainBudget": _result(
            _load("tiny_valid"),
            BudgetDecision(personal_income_rate_bps=1_800, route=ProposalRoute.LEGISLATIVE),
            LegislativeBargainDecision(
                character_id="leader_rural_alliance", proposal_kind="budget"
            ),
            CabinetDecision(
                orders=(CabinetOrder(post=CabinetPost.CHIEF_OF_STAFF, character_id="wren_hollis"),)
            ),
        ),
        "valdrunFailedBudget": _result(
            _load("decree_state"),
            BudgetDecision(personal_income_rate_bps=1_800, route=ProposalRoute.LEGISLATIVE),
        ),
        "valdrunDecreeBudget": _result(
            _load("decree_state"),
            BudgetDecision(personal_income_rate_bps=2_500, route=ProposalRoute.DECREE),
        ),
        "valdrunAmendmentFailed": _result(_load("decree_state"), _amend(*FOUR_AXIS)),
        "valdrunAmendmentPassed": _result(_supportive(_load("decree_state")), _amend(*FOUR_AXIS)),
        "valdrunNoProposal": _result(_load("decree_state")),
    }


def test_result_fixtures_are_backend_output() -> None:
    expected = _fixtures()
    if REGENERATE:
        RESULTS_JSON.write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")
    assert json.loads(RESULTS_JSON.read_text(encoding="utf-8")) == expected


def test_the_fixtures_cover_every_proposal_card_state() -> None:
    f = _fixtures()

    def vote(name: str) -> dict[str, object]:
        v = f[name]["recorded_vote"]
        assert isinstance(v, dict), name
        return v

    budget = vote("arkenBargainBudget")
    assert budget["proposal_kind"] == "budget" and budget["outcome"] == "passed_legislative"
    assert len(budget["chambers"]) == 2  # type: ignore[arg-type]
    assert vote("valdrunFailedBudget")["outcome"] == "failed_legislative"
    assert f["valdrunDecreeBudget"]["no_vote_reason"] == "enacted_by_decree"
    failed = vote("valdrunAmendmentFailed")
    assert failed["proposal_kind"] == "constitutional_amendment"
    assert failed["outcome"] == "failed_legislative" and failed["blocs_recorded"] is False
    assert vote("valdrunAmendmentPassed")["outcome"] == "passed_legislative"
    assert f["valdrunNoProposal"]["no_vote_reason"] == "no_proposal"

    people = {
        d["reason_id"]: d["params"]  # type: ignore[index]
        for d in f["arkenBargainBudget"]["drivers"]  # type: ignore[attr-defined]
        if "character_id" in d["params"]  # type: ignore[index]
    }
    assert people["legislative_bargain_accepted"]["character_portrait_ref"]
    assert people["cabinet_replaced"]["outgoing_character_portrait_ref"]
