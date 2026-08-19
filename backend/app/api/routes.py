"""Thin HTTP verbs over the engine. No simulation logic lives here.

Every handler does the same three things: validate its input, call the engine or
a projection builder, and return a projection. Anything that decides what is
true in the game happens inside `app.simulation`.

Gate 4A1 commit 4 covers the read-only and lifecycle operations. `/preview` and
`/resolve` arrive in this gate's later commits and are registered there.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from app.content.scenarios import load_scenario_file
from app.core.errors import (
    HistoryValidationError,
    ScenarioValidationError,
    SnapshotNotFoundError,
)
from app.simulation.history import GameSave, new_game, validate_history
from app.simulation.save_format import SAVE_FORMAT_VERSION
from app.simulation.state import GameState

from .projections import (
    DashboardProjection,
    HistoryDetailResponse,
    HistoryListEntry,
    SaveSummary,
    ScenarioSummary,
    build_dashboard,
    build_turn_result,
)
from .save_registry import (
    SaveRepository,
    new_save_id,
    validate_display_name,
    validate_save_id,
)
from .session import GameSession

#: A scenario id is a bare lowercase identifier -- the same reject-by-shape
#: discipline as save IDs, so no request can walk out of the scenario root.
SCENARIO_ID_PATTERN = re.compile(r"^[a-z0-9_]+$")

#: The one polished showcase scenario (frozen plan §6.2).
SHOWCASE_SCENARIO_ID = "decree_state"

router = APIRouter()


class NewGameRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    seed: int | None = None


class LoadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    save_id: str


class SaveAsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1)


def _session(request: Request) -> GameSession:
    session: GameSession = request.app.state.session
    return session


def _repository(request: Request) -> SaveRepository:
    return _session(request).repository


def _scenario_root(request: Request) -> Path:
    root: Path = request.app.state.settings.scenario_root
    return root


def _scenario_path(root: Path, scenario_id: str) -> Path:
    """Resolve a scenario id to its file, rejecting anything that is not an id."""
    if not SCENARIO_ID_PATTERN.fullmatch(scenario_id):
        raise ScenarioValidationError(scenario_id, ["not a known scenario id"])
    candidate = root / f"{scenario_id}.yaml"
    if not candidate.is_file() or candidate.is_symlink():
        raise ScenarioValidationError(scenario_id, ["no such scenario file"])
    return candidate


def _election_interval_label(state: GameState) -> str:
    country = state.world.countries[state.world.player_country_id]
    politics = country.politics
    if politics is None:
        return "No election scheduled"
    interval = politics.constitution.national_election_interval_turns
    return "No election scheduled" if interval is None else f"Every {interval} turns"


def _current_report(save: GameSave) -> object:
    return save.entries[-1].report()


# --------------------------------------------------------------------------
# Scenarios
# --------------------------------------------------------------------------


@router.get("/scenarios", response_model=list[ScenarioSummary])
def list_scenarios(request: Request) -> list[ScenarioSummary]:
    """Scenario cards for the Title screen.

    Each file is actually loaded rather than described from a hand-written
    table, so the card can never claim a government form the scenario does not
    have.
    """
    root = _scenario_root(request)
    summaries: list[ScenarioSummary] = []
    if not root.is_dir():
        return summaries
    for path in sorted(root.glob("*.yaml")):
        scenario_id = path.stem
        if not SCENARIO_ID_PATTERN.fullmatch(scenario_id):
            continue
        state = load_scenario_file(path)
        dashboard = build_dashboard(state, None)
        summaries.append(
            ScenarioSummary(
                scenario_id=scenario_id,
                display_name=dashboard.country_name,
                government_form=dashboard.government_form,
                election_interval_label=_election_interval_label(state),
                starting_legitimacy_text=dashboard.concerns.legitimacy.headline,
                is_showcase=scenario_id == SHOWCASE_SCENARIO_ID,
            )
        )
    return summaries


# --------------------------------------------------------------------------
# Lifecycle
# --------------------------------------------------------------------------


@router.post("/game/new", response_model=DashboardProjection)
async def create_game(request: Request, body: NewGameRequest) -> DashboardProjection:
    """Start a campaign.

    Order (ADR 0014): build the save, allocate a UUID, write it atomically,
    update the index, and only then swap the active session -- so the in-memory
    pointer never moves ahead of the disk.
    """
    session = _session(request)
    async with session.boundary.admit("new game"):
        state = load_scenario_file(_scenario_path(_scenario_root(request), body.scenario_id))
        if body.seed is not None:
            # Exactly what the CLI does for `--seed`, so a GUI campaign and a CLI
            # campaign at the same seed are the same campaign.
            state = state.model_copy(update={"seed": body.seed})
        save = new_game(state, save_format_version=SAVE_FORMAT_VERSION)
        save_id = new_save_id()
        session.repository.write_save(save_id, save)
        session.repository.list_saves()
        session.adopt(save, save_id)
        return build_dashboard(save.current_state(), None)


@router.post("/game/load", response_model=DashboardProjection)
async def load_game(request: Request, body: LoadRequest) -> DashboardProjection:
    """Load a save by ID.

    The registry entry is never treated as proof of integrity: the save is read,
    parsed, version-checked and `validate_history`-checked, and only a save that
    passes all of that replaces the active session.
    """
    session = _session(request)
    async with session.boundary.admit("load"):
        save_id = validate_save_id(body.save_id)
        save = session.repository.read_save(save_id)
        problems = validate_history(save)
        if problems:
            raise HistoryValidationError(problems)
        session.adopt(save, save_id)
        return build_dashboard(save.current_state(), save.entries[-1].report())


@router.post("/game/save-as", response_model=SaveSummary)
async def save_as(request: Request, body: SaveAsRequest) -> SaveSummary:
    """Checkpoint the current state under a NEW save id.

    A branch, not a rename: the running session keeps autosaving under its
    original id, which is left untouched.
    """
    session = _session(request)
    async with session.boundary.admit("save"):
        display_name = validate_display_name(body.display_name)
        save = session.current_save
        checkpoint_id = new_save_id()
        session.repository.write_save(checkpoint_id, save)
        records = {record.save_id: record for record in session.repository.list_saves()}
        record = records[checkpoint_id]
        session.repository.write_index(
            tuple(
                (
                    row
                    if row.save_id != checkpoint_id
                    else type(row)(**{**row.__dict__, "display_name": display_name})
                )
                for row in records.values()
            )
        )
        return SaveSummary(
            save_id=checkpoint_id,
            display_name=display_name,
            scenario_id=record.scenario_id,
            current_turn=record.current_turn,
            updated_at=record.updated_at,
            terminal_outcome_summary=record.terminal_outcome_summary,
            loadable=record.loadable,
            integrity_problem=record.integrity_problem,
        )


# --------------------------------------------------------------------------
# Read-only views
# --------------------------------------------------------------------------


@router.get("/game/state", response_model=DashboardProjection)
def get_state(request: Request) -> DashboardProjection:
    """The bare dashboard shape -- never a narrative about what changed."""
    save = _session(request).current_save
    return build_dashboard(save.current_state(), save.entries[-1].report())


@router.get("/game/history", response_model=list[HistoryListEntry])
def list_history(request: Request) -> list[HistoryListEntry]:
    """The timeline: one rendered line per resolved turn, nothing heavier."""
    save = _session(request).current_save
    entries: list[HistoryListEntry] = []
    for entry in save.entries:
        report = entry.report()
        if report is None:
            continue  # genesis carries no report, so it is not a timeline row
        result = build_turn_result(entry.state(), report)
        entries.append(
            HistoryListEntry(
                turn=result.turn, outcome_line=result.outcome_headline, tone=result.outcome_tone
            )
        )
    return entries


@router.get("/game/history/{turn}", response_model=HistoryDetailResponse)
def get_history_detail(request: Request, turn: int) -> HistoryDetailResponse:
    """One historical turn, rendered from its OWN stored report and state.

    Nothing is recomputed from the current state: `entry_at(turn)` carries both
    the report written when that turn resolved and the state it produced, and
    `dashboardAsOfTurn` is built from the latter.
    """
    save = _session(request).current_save
    entry = save.entry_at(turn)
    report = entry.report()
    if report is None:
        raise SnapshotNotFoundError(turn, [row.turn for row in save.entries if row.turn > 0])
    state = entry.state()
    return HistoryDetailResponse(
        turnResult=build_turn_result(state, report),
        dashboardAsOfTurn=build_dashboard(state, report),
    )


@router.get("/saves", response_model=list[SaveSummary])
def list_saves(request: Request) -> list[SaveSummary]:
    """Safe metadata only. No filesystem path ever appears in the response."""
    return [
        SaveSummary(
            save_id=record.save_id,
            display_name=record.display_name,
            scenario_id=record.scenario_id,
            current_turn=record.current_turn,
            updated_at=record.updated_at,
            terminal_outcome_summary=record.terminal_outcome_summary,
            loadable=record.loadable,
            integrity_problem=record.integrity_problem,
        )
        for record in _repository(request).list_saves()
    ]
