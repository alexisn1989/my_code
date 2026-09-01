"""Thin HTTP verbs over the engine. No simulation logic lives here.

Every handler does the same three things: validate its input, call the engine or
a projection builder, and return a projection. Anything that decides what is
true in the game happens inside `app.simulation`.

**One mutation boundary guards the whole authoritative session, not just
`/resolve`.** `/game/new`, `/game/load`, `/game/save-as` and `/game/resolve` each
open `session.boundary.admit(...)` before touching `session.current_save` or the
save root, because any of the four can replace the active save or mutate
persisted save data. Without a shared boundary, a `/load` racing `/resolve`
could swap `session.current_save` between resolve's persist and its own swap,
silently discarding whichever write lost the race. `/preview` is the one
mutating-shaped request that deliberately stays OUTSIDE the boundary -- it never
writes anything, so admission would only block an unrelated resolve for no
reason -- but it still captures `session.current_save` exactly once, matching
the same one-complete-revision discipline the boundary enforces for everyone
else. See `test_api_concurrency.py` for the real-overlap proof across every
operation pair.
"""

from __future__ import annotations

import re
from contextlib import suppress
from pathlib import Path
from typing import Any

from anyio import to_thread
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.content.scenarios import load_scenario_file
from app.core.errors import (
    DecisionSetError,
    HistoryValidationError,
    ScenarioValidationError,
    SnapshotNotFoundError,
)
from app.simulation.decisions import DecisionSet
from app.simulation.history import GameSave, advance_game, new_game, validate_history
from app.simulation.save_format import SAVE_FORMAT_VERSION
from app.simulation.state import GameState

from .policy_cards import build_decision_options_with_policy_cards
from .preview import preview_decisions
from .projections import (
    DashboardProjection,
    DecisionOptionsProjection,
    HistoryDetailResponse,
    HistoryListEntry,
    PreviewProjection,
    ResolveResponse,
    SaveSummary,
    ScenarioSummary,
    StrategicMapProjection,
    build_dashboard,
    build_strategic_map,
    build_turn_result,
)
from .save_registry import (
    SaveRepository,
    new_save_id,
    validate_display_name,
    validate_save_id,
)
from .session import GameSession, PersistenceError, StaleRevisionError

#: A scenario id is a bare lowercase identifier -- the same reject-by-shape
#: discipline as save IDs, so no request can walk out of the scenario root.
SCENARIO_ID_PATTERN = re.compile(r"^[a-z0-9_]+$")

#: The one polished showcase scenario (frozen plan §6.2).
SHOWCASE_SCENARIO_ID = "decree_state"

#: The opaque revision token's only permitted shape.
REVISION_PATTERN = re.compile(r"^(\d+)\.(\d+)$")

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
        await session.wait_at_barrier()
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
        await session.wait_at_barrier()
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


@router.get("/game/map/strategic", response_model=StrategicMapProjection)
def get_strategic_map(request: Request) -> StrategicMapProjection:
    """The read-only strategic map: theaters, directed routes and authored political shapes.

    Read-only, like `/game/state` -- captures `session.current_save` once and never takes the
    mutation boundary. Presentation only: selecting a theater in the client queues nothing, and
    this endpoint never draws RNG, resolves a turn or writes state.
    """
    save = _session(request).current_save
    return build_strategic_map(save.current_state())


@router.get("/game/decision-options", response_model=DecisionOptionsProjection)
def get_decision_options(request: Request) -> DecisionOptionsProjection:
    """The legal-move envelope: what the client needs to build a decision.

    Read-only, like `/game/state` -- captures `session.current_save` once and
    never takes the mutation boundary. Every figure is a real engine constant
    or a real state fact (frozen plan Sec 4.6, Sec 10); this endpoint decides
    nothing about what is affordable or legal to SUBMIT -- `/preview` scores a
    draft and `/resolve`'s own validators are still the only authority.
    """
    save = _session(request).current_save
    return build_decision_options_with_policy_cards(save.current_state())


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


# --------------------------------------------------------------------------
# Resolve -- the one authoritative mutation
# --------------------------------------------------------------------------


class ResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: The opaque token most recently received, echoed back VERBATIM.
    revision: str
    #: Assembled in canonical order by the client. The server does not sort,
    #: deduplicate, normalize or repair -- noncanonical order is REJECTED by the
    #: engine's own validators, which is the contract the engine guarantees.
    decisions: tuple[dict[str, Any], ...] = ()


def _parse_revision(revision: str) -> tuple[int, int]:
    """Split the opaque token into the two integers the ENGINE will check.

    The server never substitutes its own current values here. Passing the
    client's claim through is what keeps `resolver.py`'s staleness check
    load-bearing instead of trivially satisfied (ADR 0014).
    """
    match = REVISION_PATTERN.fullmatch(revision)
    if match is None:
        raise DecisionSetError(f"malformed revision token {revision!r}")
    return int(match.group(1)), int(match.group(2))


@router.post("/game/resolve", response_model=ResolveResponse)
async def resolve(request: Request, body: ResolveRequest) -> ResolveResponse:
    """Resolve one turn.

    The order below is the authoritative one from ADR 0014, and the last two
    steps are the ones that are easy to get subtly wrong:

      1. Acquire mutation admission immediately, or reject `resolution_in_progress`.
      2. Parse the client-echoed revision.
      3. Compare it with the live state; reject a stale revision.
      4. Build `DecisionSet` from the CLIENT's claimed turn/version, unsorted.
      5. Call the engine.
      6. Capture the returned immutable save in `new_save`.
      7. Persist `new_save` atomically.
      8. Swap `session.current_save` only after persistence succeeds.
      9. Release the boundary -- on every path, success or failure.
     10. Build the response from the CAPTURED `new_save`, never by re-reading
         `session.current_save` after the boundary is released, which another
         request could by then have advanced.

    A persistence failure leaves both the in-memory save and the on-disk save
    exactly as they were.
    """
    session = _session(request)
    async with session.boundary.admit("resolution"):
        await session.wait_at_barrier()

        save = session.current_save
        claimed_turn, claimed_version = _parse_revision(body.revision)
        live = save.current_state()
        if (claimed_turn, claimed_version) != (live.turn, live.state_version):
            raise StaleRevisionError(
                expected=f"{live.turn}.{live.state_version}", actual=body.revision
            )

        try:
            decision_set = DecisionSet.model_validate(
                {
                    "expected_turn": claimed_turn,
                    "expected_state_version": claimed_version,
                    "decisions": list(body.decisions),
                }
            )
        except ValidationError as error:
            # Translate the schema rejection into the engine's own error type.
            # This is a change of exception CLASS only -- the payload is not
            # sorted, deduplicated, repaired or coerced on its way through, so a
            # noncanonical or malformed decision set stays rejected.
            raise DecisionSetError(str(error)) from error
        # The engine is synchronous and can take ~100ms on a long history, so it
        # runs off the event loop. The transaction stays single: the boundary is
        # still held for the whole of it.
        new_save = await to_thread.run_sync(advance_game, save, decision_set)
        try:
            session.repository.write_save(session.save_id, new_save)
        except OSError as error:
            # Nothing is swapped: the in-memory save and the on-disk bytes both
            # remain exactly as they were before this request.
            raise PersistenceError(f"could not persist the resolved turn: {error}") from error
        session.adopt(new_save, session.save_id)
        # Index refresh is best-effort convenience metadata. The turn is already
        # committed and authoritative, so a metadata failure must NOT turn a
        # successful resolve into a reported failure; the next listing repairs it.
        with suppress(OSError):
            session.repository.list_saves()

    entry = new_save.entries[-1]
    report = entry.report()
    assert report is not None, "a resolved turn always stores a report"
    state = entry.state()
    return ResolveResponse(
        turnResult=build_turn_result(state, report), dashboard=build_dashboard(state, report)
    )


# --------------------------------------------------------------------------
# Preview -- read-only, and deliberately NOT behind the mutation boundary
# --------------------------------------------------------------------------


class PreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: str
    decisions: tuple[dict[str, Any], ...] = ()


@router.post("/game/preview", response_model=PreviewProjection)
def preview_proposal(request: Request, body: PreviewRequest) -> PreviewProjection:
    """Score a drafted proposal without changing anything.

    Deliberately does NOT take the mutation boundary: the frozen plan states
    preview uses "never the session lock, never a write", and taking it would let
    a player drafting in one tab reject an unrelated resolve in another.

    Instead it captures `session.current_save` ONCE, at the top, and works
    entirely from that immutable reference -- so a concurrent resolve can never
    show preview a mixture of pre- and post-mutation state. It observes one
    complete revision or the other.
    """
    save = _session(request).current_save  # captured once; never re-read below
    state = save.current_state()
    claimed_turn, claimed_version = _parse_revision(body.revision)
    if (claimed_turn, claimed_version) != (state.turn, state.state_version):
        raise StaleRevisionError(
            expected=f"{state.turn}.{state.state_version}", actual=body.revision
        )

    try:
        decision_set = DecisionSet.model_validate(
            {
                "expected_turn": claimed_turn,
                "expected_state_version": claimed_version,
                "decisions": list(body.decisions),
            }
        )
    except ValidationError as error:
        # Same reject-not-normalize contract as /resolve: exception class is
        # translated, the payload is never sorted, repaired or coerced.
        raise DecisionSetError(str(error)) from error

    return preview_decisions(state, decision_set)
