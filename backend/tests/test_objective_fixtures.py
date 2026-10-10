"""Gate 4A3 victory path (V-2): the browser fixtures for objective stages a winning replay cannot
reach are BACKEND OUTPUT, pinned here.

`frontend/e2e/victory.spec.ts` serves these dashboards in place of `/api/game/state` to render, in a
real browser, the `cannot_qualify` stages and a withheld link. Each file must equal what
`build_dashboard` produces for a state reached by real resolved turns (`resolve_turn`, legislature
made to carry the votes). Regenerate with `MANDATE_REGENERATE_OBJECTIVE_FIXTURES=1`.

The D-V1 drift guard lives here too: `format.ts`'s amendment axis and value labels must cover the
engine's amendable axes and enum values exactly.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Annotated, get_args, get_origin

import pytest

from app.api.objective import QUALIFYING_REFORM_CARD_ID, build_objective
from app.api.policy_cards import build_decision_options_with_policy_cards
from app.api.preview import preview_decisions
from app.api.projections import build_dashboard, build_turn_result
from app.simulation.constitution import DecreeAuthority, ExecutiveSelection, ExecutiveSystem
from app.simulation.decisions import (
    BlocInvestment,
    BlocRelationshipInvestmentDecision,
    ConstitutionalAmendmentDecision,
    ConstitutionalAxisTarget,
    InfluenceAllocation,
    TermLimitTarget,
)
from app.simulation.state import GameState
from tests.test_campaign_objective import (
    DECREE_NONE,
    FOUR_AXIS,
    INTERVAL,
    _amend,
    _election_next,
    _enact,
    _hostile,
    _load,
    _politics,
    _resolve,
    _set,
    _set_politics,
    _supportive,
    _valdrun_stuck,
    _valdrun_with_marker,
)

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "frontend" / "e2e" / "fixtures"
FORMAT_TS = REPO / "frontend" / "src" / "format" / "format.ts"
STAGES_JSON = REPO / "frontend" / "src" / "test" / "objective-stages.json"
OPTIONS_JSON = REPO / "frontend" / "src" / "test" / "decision-options-valdrun.json"
RESULTS_JSON = REPO / "frontend" / "src" / "test" / "objective-results.json"
GROUPING_TS = REPO / "frontend" / "src" / "greybox" / "policy" / "groupPolicyCards.ts"
REGENERATE = os.environ.get("MANDATE_REGENERATE_OBJECTIVE_FIXTURES") == "1"


def _after_decree_none() -> GameState:
    return _enact(_load("decree_state"), _amend(*DECREE_NONE))


def _already_competitive() -> GameState:
    return _enact(_valdrun_stuck(), _amend(*INTERVAL))


def _concluded_electoral_defeat() -> GameState:
    """Gate 4A3 W-1: the qualifying election LOST -- the transition was not completed."""
    marked = _election_next(_set_politics(_hostile(_valdrun_with_marker()), legitimacy_bps=0))
    return _resolve(marked).state


def _concluded_term_limit_exit() -> GameState:
    """Gate 4A3 W-1: a term-limit exit with the marker still stored -- also not completed."""
    marked = _enact(_valdrun_with_marker(), _amend(TermLimitTarget(value=1)))
    return _resolve(_election_next(_set_politics(marked, consecutive_terms_held=1))).state


CASES = {
    "objective-after-decree-none": _after_decree_none,
    "objective-concluded-electoral-defeat": _concluded_electoral_defeat,
    "objective-cannot-qualify-missing-interval": _valdrun_stuck,
    "objective-cannot-qualify-already-competitive": _already_competitive,
}


def _dashboard_json(state: GameState) -> str:
    projection = build_dashboard(state, None, campaign_id="fixture-campaign")
    return json.dumps(projection.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"


@pytest.mark.parametrize("name", sorted(CASES))
def test_objective_fixture_is_backend_output(name: str) -> None:
    expected = _dashboard_json(CASES[name]())
    path = FIXTURES / f"{name}.json"
    if REGENERATE:
        path.write_text(expected, encoding="utf-8")
    assert path.read_text(encoding="utf-8") == expected


def test_fixture_stages_are_the_ones_the_browser_test_expects() -> None:
    stages = {
        name: json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))["objective"]
        for name in CASES
    }
    assert stages["objective-after-decree-none"]["stage"] == "reform"
    executive = next(
        row
        for row in stages["objective-after-decree-none"]["conditions"]
        if row["id"] == "elected_executive"
    )
    assert executive["link_card_id"] is None
    assert executive["note"].startswith("Not on its own:")
    assert stages["objective-cannot-qualify-missing-interval"]["cannot_qualify_reason"] == (
        "missing_interval"
    )
    assert stages["objective-cannot-qualify-already-competitive"]["cannot_qualify_reason"] == (
        "already_competitive"
    )


def _stage_states() -> dict[str, GameState]:
    return {
        "reform": _load("decree_state"),
        "reformDeficitDemo": _load("deficit_demo"),
        "afterDecreeNone": _after_decree_none(),
        "qualifyingElection": _valdrun_with_marker(),
        "concludedVictory": _resolve(_election_next(_supportive(_valdrun_with_marker()))).state,
        "cannotQualifyMissingInterval": _valdrun_stuck(),
        "cannotQualifyAlreadyCompetitive": _already_competitive(),
        "concludedElectoralDefeat": _concluded_electoral_defeat(),
        "concludedTermLimitExit": _concluded_term_limit_exit(),
    }


def test_unit_test_stage_objectives_are_backend_output() -> None:
    """`frontend/src/test/objective-stages.json` -- the objectives the component tests render --
    equals `build_objective` on states reached by real resolved turns."""
    expected = {
        name: build_objective(_politics(state)).model_dump(mode="json")
        for name, state in _stage_states().items()
    }
    if REGENERATE:
        STAGES_JSON.write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")
    assert json.loads(STAGES_JSON.read_text(encoding="utf-8")) == expected
    assert expected["concludedVictory"]["stage"] == "concluded"


def test_unit_test_decision_options_are_backend_output() -> None:
    """The real decision options (with the policy-card catalog) for Valdrun's opening state, which
    the Decisions link tests select cards from."""
    options = build_decision_options_with_policy_cards(
        _load("decree_state"), campaign_id="campaign-1"
    )
    expected = options.model_dump(mode="json")
    if REGENERATE:
        OPTIONS_JSON.write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")
    assert json.loads(OPTIONS_JSON.read_text(encoding="utf-8")) == expected


def _invest_all(state: GameState, capital: int) -> BlocRelationshipInvestmentDecision:
    legislature = _politics(state).legislature
    assert legislature is not None
    rows = sorted(
        (
            BlocInvestment(party_id=party.id, bloc_id=bloc.id, political_capital=capital)
            for party in legislature.parties
            for bloc in party.blocs
        ),
        key=lambda row: (row.party_id, row.bloc_id),
    )
    return BlocRelationshipInvestmentDecision(investments=tuple(rows))


def _at_ceiling(state: GameState) -> GameState:
    legislature = _politics(state).legislature
    assert legislature is not None
    parties = tuple(
        party.model_copy(
            update={
                "blocs": tuple(
                    bloc.model_copy(update={"government_relationship_bps": 10_000})
                    for bloc in party.blocs
                )
            }
        )
        for party in legislature.parties
    )
    return _set_politics(state, legislature=legislature.model_copy(update={"parties": parties}))


def _results_and_previews() -> dict[str, object]:
    tiny = _load("tiny_valid")
    ceiling = _at_ceiling(_load("decree_state"))
    valdrun = _load("decree_state")
    four_axis = _amend(*FOUR_AXIS)
    reform = _resolve(_supportive(valdrun.model_copy(deep=True)), four_axis)
    deficit = _load("deficit_demo")
    passing = ConstitutionalAmendmentDecision(
        targets=DECREE_NONE,
        influence=(
            InfluenceAllocation(
                party_id="citizens_bloc", bloc_id="hardliners", political_capital=300
            ),
        ),
    )
    investment = BlocRelationshipInvestmentDecision(
        investments=(
            BlocInvestment(party_id="opposition_party", bloc_id="main", political_capital=200),
        )
    )
    return {
        "reformResult": build_turn_result(
            reform.state, reform.report, opening_state=_supportive(valdrun.model_copy(deep=True))
        ).model_dump(mode="json"),
        "previewPasses": preview_decisions(deficit, _set(deficit, passing)).model_dump(mode="json"),
        "previewFails": preview_decisions(valdrun, _set(valdrun, four_axis)).model_dump(
            mode="json"
        ),
        # Gate 4A3 W-2: investments with a serving chief of staff (tiny_valid), and one that would
        # change nothing (a bloc already at the ceiling).
        "previewInvestments": preview_decisions(tiny, _set(tiny, _invest_all(tiny, 50))).model_dump(
            mode="json"
        ),
        "previewInvestmentNoEffect": preview_decisions(
            ceiling, _set(ceiling, _invest_all(ceiling, 50))
        ).model_dump(mode="json"),
        "previewUnaffordable": preview_decisions(
            valdrun, _set(valdrun, _amend(*FOUR_AXIS, influence=400), investment)
        ).model_dump(mode="json"),
    }


def test_unit_test_results_and_previews_are_backend_output() -> None:
    expected = _results_and_previews()
    if REGENERATE:
        RESULTS_JSON.write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")
    assert json.loads(RESULTS_JSON.read_text(encoding="utf-8")) == expected
    passes, fails, unaffordable = (
        expected["previewPasses"],
        expected["previewFails"],
        expected["previewUnaffordable"],
    )
    assert passes["would_pass"] and passes["affordable"]  # type: ignore[index]
    assert not fails["would_pass"] and fails["affordable"]  # type: ignore[index]
    assert not unaffordable["affordable"]  # type: ignore[index]


def test_frontend_names_the_same_qualifying_card_id() -> None:
    source = GROUPING_TS.read_text(encoding="utf-8")
    assert f'export const QUALIFYING_REFORM_CARD_ID = "{QUALIFYING_REFORM_CARD_ID}";' in source


def _ts_record_keys(name: str) -> set[str]:
    source = FORMAT_TS.read_text(encoding="utf-8")
    match = re.search(
        rf"export const {name}: Record<string, string> = \{{(.*?)\n\}};", source, re.S
    )
    assert match is not None, name
    return set(re.findall(r"^\s+([a-z_]+):", match.group(1), re.M))


def _amendable_axes() -> set[str]:
    """Every axis an amendment target can name, read from the engine's own target union."""
    union = ConstitutionalAxisTarget
    while get_origin(union) is Annotated:
        union = get_args(union)[0]
    return {member.model_fields["axis"].default for member in get_args(union)}


def test_amendment_axis_labels_cover_every_amendable_axis() -> None:
    axes = _amendable_axes()
    assert len(axes) == 5
    assert _ts_record_keys("CONSTITUTION_AXIS_LABEL") == axes


def test_amendment_value_labels_cover_every_enum_value() -> None:
    values = {
        member.value
        for enum in (DecreeAuthority, ExecutiveSystem, ExecutiveSelection)
        for member in enum
    }
    assert _ts_record_keys("CONSTITUTION_VALUE_LABEL") == values
