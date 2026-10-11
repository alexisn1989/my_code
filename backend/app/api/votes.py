"""(Gate 4A3 M-0) Recorded chamber votes, read from stored turn reports and nothing else.

Two questions the redesigned Legislature and result screens ask, answered without recomputing
anything:

* **What did the chambers vote, on a turn that held a vote?** `recorded_vote` reads the stored
  `LegislativeReport` (a budget) or `ConstitutionalAmendmentReport` (an amendment). The tallies are
  the stored ones -- never re-derived against today's seats. Budgets store a row per bloc and
  chamber (`BlocVoteReport`); amendments store chamber totals only, so `blocs_recorded` is false
  and no bloc rows are invented for them.
* **Why was no vote held?** `no_vote_reason` names the stored reason. Only two exist: no proposal
  was put forward, or the proposal was enacted by decree. A legislative-route proposal with no
  sitting legislature is refused before a turn exists (`phases.py`, the `requires a legislature`
  refusals), so "no legislature" is not a reason any stored turn can carry. Any other stored
  combination is a projection error, raised rather than guessed.

`last_recorded_vote` walks a save's stored history from newest to oldest and returns the first turn
that actually held a chamber vote, filed under the same turn number History uses, so an
appointment-only or decree turn never hides the last real vote.
"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.simulation.history import GameSave
from app.simulation.legislature import LegislativeOutcome
from app.simulation.report import TurnReport
from app.simulation.state import GameState

_STRICT = ConfigDict(extra="forbid", frozen=True)

NoVoteReason = Literal["no_proposal", "enacted_by_decree"]


class RecordedBlocVote(BaseModel):
    """One bloc's recorded support in one chamber (budgets only)."""

    model_config = _STRICT

    party_id: str
    bloc_id: str
    bloc_display_name: str
    seats: int
    supporting_seats: int


class RecordedChamberVote(BaseModel):
    """One chamber's recorded tally, exactly as stored."""

    model_config = _STRICT

    chamber: str
    total_seats: int
    supporting_seats: int
    required_seats: int
    passed: bool
    blocs: tuple[RecordedBlocVote, ...] = ()


class RecordedBudgetChange(BaseModel):
    """What the voted budget proposed, from the stored report (directions and totals; the stored
    report keeps no per-rate targets for a budget that failed)."""

    model_config = _STRICT

    tax_direction: str
    tax_delta_bps: int
    spending_direction: str
    opening_total_program_spending: int
    proposed_total_program_spending: int


class RecordedAmendmentTarget(BaseModel):
    """One axis the voted amendment proposed to change, from the stored report."""

    model_config = _STRICT

    axis: str
    opening_value: str
    proposed_value: str


class RecordedVote(BaseModel):
    """A chamber vote that was actually held on one turn."""

    model_config = _STRICT

    proposal_kind: Literal["budget", "constitutional_amendment"]
    outcome: Literal["passed_legislative", "failed_legislative"]
    chambers: tuple[RecordedChamberVote, ...]
    blocs_recorded: bool
    """True for budgets (bloc rows are stored); false for amendments, whose report stores chamber
    totals only."""
    budget: RecordedBudgetChange | None = None
    amendment_targets: tuple[RecordedAmendmentTarget, ...] = ()


class LastRecordedVote(BaseModel):
    """The most recent turn that held a chamber vote."""

    model_config = _STRICT

    turn: int
    """The turn number History files that turn under (the turn it produced)."""
    vote: RecordedVote


def _bloc_names(state: GameState) -> dict[tuple[str, str], str]:
    politics = state.world.countries[state.world.player_country_id].politics
    legislature = None if politics is None else politics.legislature
    if legislature is None:
        return {}
    return {(party.id, bloc.id): bloc.name for party in legislature.parties for bloc in party.blocs}


def recorded_vote(state: GameState, report: TurnReport) -> RecordedVote | None:
    """The chamber vote this turn held, or `None` when it held none. `state` is the state the turn
    produced (used only for bloc display names)."""
    legislative = report.legislative
    amendment = report.constitutional_amendment
    if legislative is not None and legislative.chambers:
        names = _bloc_names(state)
        return RecordedVote(
            proposal_kind="budget",
            outcome=legislative.outcome.value,  # type: ignore[arg-type]
            chambers=tuple(
                RecordedChamberVote(
                    chamber=chamber.chamber.value,
                    total_seats=chamber.total_seats,
                    supporting_seats=chamber.supporting_seats,
                    required_seats=chamber.required_yes_seats,
                    passed=chamber.passed,
                    blocs=tuple(
                        RecordedBlocVote(
                            party_id=row.party_id,
                            bloc_id=row.bloc_id,
                            bloc_display_name=names.get((row.party_id, row.bloc_id), row.bloc_id),
                            seats=row.seats,
                            supporting_seats=row.supporting_seats,
                        )
                        for row in legislative.blocs
                        if row.chamber is chamber.chamber
                    ),
                )
                for chamber in legislative.chambers
            ),
            blocs_recorded=True,
            budget=RecordedBudgetChange(
                tax_direction=legislative.tax_direction.value,
                tax_delta_bps=legislative.tax_delta_bps,
                spending_direction=legislative.spending_direction.value,
                opening_total_program_spending=legislative.opening_total_program_spending,
                proposed_total_program_spending=legislative.proposed_total_program_spending,
            ),
        )
    if amendment is not None and amendment.chambers:
        return RecordedVote(
            proposal_kind="constitutional_amendment",
            outcome=amendment.outcome.value,  # type: ignore[arg-type]
            chambers=tuple(
                RecordedChamberVote(
                    chamber=chamber.chamber.value,
                    total_seats=chamber.total_seats,
                    supporting_seats=chamber.supporting_seats,
                    required_seats=chamber.required_yes_seats,
                    passed=chamber.passed,
                )
                for chamber in amendment.chambers
            ),
            blocs_recorded=False,
            amendment_targets=tuple(
                RecordedAmendmentTarget(
                    axis=str(target.axis),
                    opening_value=target.opening_value,
                    proposed_value=target.proposed_value,
                )
                for target in amendment.targets
            ),
        )
    return None


def no_vote_reason(report: TurnReport) -> NoVoteReason:
    """Why a turn that held no chamber vote held none, from the stored outcomes only.

    Call only when `recorded_vote` is `None`. Raises `ValueError` for any stored combination this
    does not recognise, so a new outcome cannot be silently mislabelled."""
    legislative = report.legislative
    amendment = report.constitutional_amendment
    if legislative is None:
        raise ValueError("a resolved turn without a legislative report: no reason can be stated")
    if legislative.chambers or (amendment is not None and amendment.chambers):
        raise ValueError("this turn held a chamber vote; it has no no-vote reason")
    if legislative.outcome is LegislativeOutcome.ENACTED_BY_DECREE:
        return "enacted_by_decree"
    if amendment is not None and amendment.proposed:
        if amendment.outcome is LegislativeOutcome.ENACTED_BY_DECREE:
            return "enacted_by_decree"
        raise ValueError(
            f"an amendment was proposed with outcome {amendment.outcome.value!r} "
            "but no chamber vote is recorded"
        )
    if legislative.outcome is LegislativeOutcome.NO_PROPOSAL:
        return "no_proposal"
    raise ValueError(f"budget outcome {legislative.outcome.value!r} with no recorded chamber vote")


def held_a_vote(report_json: str) -> bool:
    """Whether a stored report records a chamber vote, read from its canonical JSON WITHOUT model
    validation -- the cheap pre-check `last_recorded_vote` runs on every turn it walks past.

    Full validation of every stored report on every options read cost about 33 ms over 40 turns, so
    only the turn that held a vote is parsed into a `TurnReport`. A test pins that this agrees with
    `recorded_vote` on every entry of real saves."""
    raw = json.loads(report_json)
    legislative = raw.get("legislative") or {}
    amendment = raw.get("constitutional_amendment") or {}
    return bool(legislative.get("chambers")) or bool(amendment.get("chambers"))


def last_recorded_vote(save: GameSave) -> LastRecordedVote | None:
    """The newest turn in `save` that held a chamber vote, or `None` if none ever has."""
    for entry in reversed(save.entries):
        if entry.report_json is None or not held_a_vote(entry.report_json):
            continue  # genesis, or a turn that held no vote
        report = entry.report()
        assert report is not None
        state = entry.state()
        vote = recorded_vote(state, report)
        assert vote is not None, "held_a_vote and recorded_vote disagree"
        return LastRecordedVote(turn=state.turn, vote=vote)
    return None
