"""The campaign objective: where the player stands on the road to victory (Gate 4A3 victory path).

Everything here is DERIVED from engine state and classified ONLY by the engine's own two
predicates, `is_noncompetitive_constitution` and `is_competitive_elected_constitution`
(`app/simulation/government_survival.py`). Nothing restates which executive selections or decree
authorities count: each of the three conditions is read by asking the competitive-elected
predicate about one axis with the other two held at a value that satisfies it.

The engine's victory rule, which this module reports and never re-decides:

* an ENACTED amendment whose opening constitution is non-competitive and whose proposed one is
  competitive-elected records `pending_liberalization` (`phases.py`, slot 1 and slot 2);
* a later enacted amendment that leaves the constitution NOT competitive-elected clears it;
* a national election won on a later turn than the marker is victory; ANY lost election is defeat.

The two predicates are mutually exclusive but not exhaustive, so a constitution is in exactly one
of three classes. The third, `neither` -- an elected executive and no decree authority, but no
election schedule -- is coherent while a legislature sits, and from it (or from a competitive
constitution reached without a marker) no reform can qualify until the constitution first returns
to non-competitive rule. The objective says so rather than presenting it as progress.
"""

from __future__ import annotations

from functools import cache
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.simulation.constitution import (
    ConstitutionState,
    DecreeAuthority,
    ExecutiveSelection,
    ExecutiveSystem,
    first_constitutional_violation,
)
from app.simulation.decisions import (
    ConstitutionalAmendmentDecision,
    ConstitutionalAxisTarget,
    DecreeAuthorityTarget,
    ElectionIntervalTarget,
    ExecutiveSelectionTarget,
    ExecutiveSystemTarget,
)
from app.simulation.government_survival import (
    is_competitive_elected_constitution,
    is_noncompetitive_constitution,
)
from app.simulation.report import TurnReport
from app.simulation.state import (
    GameState,
    OutcomeBucket,
    PoliticalState,
    RemovalReason,
    VictoryReason,
)

from .constitution_labels import (
    DECREE_AUTHORITY_LABELS,
    EXECUTIVE_SELECTION_LABELS,
    election_interval_label,
)

_STRICT = ConfigDict(extra="forbid", frozen=True)

ConstitutionClass = Literal["noncompetitive", "competitive", "neither"]
ObjectiveStage = Literal["reform", "cannot_qualify", "qualifying_election", "concluded"]
CannotQualifyReason = Literal["missing_interval", "already_competitive"]
ConditionId = Literal["elected_executive", "no_decree_authority", "election_interval"]
AmendmentEffect = Literal[
    "qualifies",
    "reform_continues",
    "reopens_route",
    "cannot_qualify",
    "keeps_transition",
    "ends_transition",
]

#: The election schedule the objective's links propose: the shortest preset the catalog offers
#: (`policy_cards._ELECTION_INTERVAL_PRESETS`, pinned by a test), and the interval of the audited
#: winning Valdrun route.
QUALIFYING_INTERVAL_TURNS = 4

#: The catalog id of the one-amendment reform that completes two or more unmet conditions at once.
QUALIFYING_REFORM_CARD_ID = "constitution_qualifying_reform"

ORDERING_NOTE = (
    "Only a reform that takes the constitution from non-competitive rule to meeting all three "
    "conditions counts. Set the election schedule before, or together with, the last of the other "
    "changes. The simplest way is to make every change in one amendment."
)
VICTORY_NOTE = "Meeting every condition is not victory: you must then win the election."

_CONDITION_LABELS: dict[ConditionId, str] = {
    "elected_executive": "An elected executive",
    "no_decree_authority": "No decree authority",
    "election_interval": "A national election schedule",
}
_CONDITION_ORDER: tuple[ConditionId, ...] = (
    "elected_executive",
    "no_decree_authority",
    "election_interval",
)

_WAY_BACK = (
    "To qualify, the constitution must first return to non-competitive rule (for example, by "
    "restoring emergency decree authority) and then be reformed in one amendment that meets all "
    "three conditions. Until then, no election can complete the objective."
)


# --------------------------------------------------------------------------
# Classification -- the engine's predicates, and nothing else
# --------------------------------------------------------------------------


def constitution_class(constitution: ConstitutionState) -> ConstitutionClass:
    """Which of the engine's classes `constitution` is in. Exactly one holds (tested)."""
    if is_noncompetitive_constitution(
        executive_selection=constitution.executive_selection,
        decree_authority=constitution.decree_authority,
    ):
        return "noncompetitive"
    if is_competitive_elected_constitution(
        executive_selection=constitution.executive_selection,
        decree_authority=constitution.decree_authority,
        national_election_interval_turns=constitution.national_election_interval_turns,
    ):
        return "competitive"
    return "neither"


@cache
def _satisfying_selection() -> ExecutiveSelection:
    return next(
        selection
        for selection in ExecutiveSelection
        if is_competitive_elected_constitution(
            executive_selection=selection,
            decree_authority=_satisfying_decree(),
            national_election_interval_turns=QUALIFYING_INTERVAL_TURNS,
        )
    )


@cache
def _satisfying_decree() -> DecreeAuthority:
    for decree in DecreeAuthority:
        if any(
            is_competitive_elected_constitution(
                executive_selection=selection,
                decree_authority=decree,
                national_election_interval_turns=QUALIFYING_INTERVAL_TURNS,
            )
            for selection in ExecutiveSelection
        ):
            return decree
    raise AssertionError("the competitive-elected predicate admits no decree authority")


def condition_met(constitution: ConstitutionState, condition: ConditionId) -> bool:
    """One of the predicate's three conjuncts, asked of the predicate itself: the other two axes
    are held at values that satisfy it, so the answer turns on this axis alone."""
    selection = constitution.executive_selection
    decree = constitution.decree_authority
    interval = constitution.national_election_interval_turns
    if condition == "elected_executive":
        decree, interval = _satisfying_decree(), QUALIFYING_INTERVAL_TURNS
    elif condition == "no_decree_authority":
        selection, interval = _satisfying_selection(), QUALIFYING_INTERVAL_TURNS
    else:
        selection, decree = _satisfying_selection(), _satisfying_decree()
    return is_competitive_elected_constitution(
        executive_selection=selection,
        decree_authority=decree,
        national_election_interval_turns=interval,
    )


def _unmet(constitution: ConstitutionState) -> tuple[ConditionId, ...]:
    return tuple(c for c in _CONDITION_ORDER if not condition_met(constitution, c))


def _names(conditions: tuple[ConditionId, ...]) -> str:
    words = [_CONDITION_LABELS[c][0].lower() + _CONDITION_LABELS[c][1:] for c in conditions]
    if len(words) <= 1:
        return "".join(words)
    return ", ".join(words[:-1]) + " and " + words[-1]


def _met_count(constitution: ConstitutionState) -> int:
    return len(_CONDITION_ORDER) - len(_unmet(constitution))


# --------------------------------------------------------------------------
# Trial constitutions -- built the way decision_preflight builds them
# --------------------------------------------------------------------------


def trial_constitution(
    opening: ConstitutionState, targets: tuple[ConstitutionalAxisTarget, ...]
) -> ConstitutionState | None:
    """The constitution `targets` would produce if enacted, or `None` when the amendment would be
    refused structurally (a target that changes nothing, or an incoherent result under C1-C10).

    All targets are applied at once and then checked, exactly as `decision_preflight` and the
    resolver build the trial -- never one axis at a time."""
    payload = opening.model_dump(mode="python")
    for target in targets:
        if getattr(opening, target.axis) == target.value:
            return None
        payload[target.axis] = target.value
    if first_constitutional_violation(ConstitutionState.model_construct(**payload)) is not None:
        return None
    return ConstitutionState.model_validate(payload)


def amendment_effect_if_enacted(
    politics: PoliticalState, proposed: ConstitutionState
) -> AmendmentEffect:
    """What ENACTING an amendment producing `proposed` would do to the objective.

    Strictly conditional: whether the amendment is enacted at all (the vote, affordability) is not
    this function's business. The qualifying test is the resolver's: opening non-competitive and
    proposed competitive-elected; the marker rule is slot 2's."""
    opening_class = constitution_class(politics.constitution)
    proposed_class = constitution_class(proposed)
    if opening_class == "noncompetitive" and proposed_class == "competitive":
        return "qualifies"
    if politics.pending_liberalization is not None:
        return "keeps_transition" if proposed_class == "competitive" else "ends_transition"
    if proposed_class == "noncompetitive":
        return "reform_continues" if opening_class == "noncompetitive" else "reopens_route"
    return "cannot_qualify"


class ObjectiveEffectProjection(BaseModel):
    """`PreviewProjection.objective_effect_if_enacted`: the staged amendment's effect IF ENACTED.

    It never says the amendment will be enacted -- `would_pass` and `affordable` on the same
    preview say whether resolving the draft would enact it."""

    model_config = _STRICT

    effect: AmendmentEffect
    conditions_met: int
    still_needed: tuple[str, ...] = ()
    deciding_election_turn: int | None = None
    election_this_turn_too_soon: bool = False


def preview_effect(
    state: GameState, politics: PoliticalState, amendment: ConstitutionalAmendmentDecision
) -> ObjectiveEffectProjection | None:
    proposed = trial_constitution(politics.constitution, amendment.targets)
    if proposed is None:  # pragma: no cover - preview's structural preflight rejects these first
        return None
    effect = amendment_effect_if_enacted(politics, proposed)
    deciding: int | None = None
    too_soon = False
    if effect in ("qualifies", "keeps_transition"):
        # Resolution runs on the turn it PRODUCES (`state.turn + 1`): slot 2 records the marker and
        # reschedules an interval target from it, and slot 13 holds an election scheduled for it.
        produced = state.turn + 1
        interval_target = next(
            (t for t in amendment.targets if t.axis == "national_election_interval_turns"), None
        )
        scheduled = (
            produced + interval_target.value
            if interval_target is not None and interval_target.value is not None
            else politics.next_election_turn
        )
        deciding = scheduled
        if effect == "qualifies" and scheduled == produced:
            # That election resolves in this same turn, after the amendment: too soon to count.
            too_soon = True
            interval = proposed.national_election_interval_turns
            deciding = None if interval is None else produced + interval
    unmet = _unmet(proposed)
    return ObjectiveEffectProjection(
        effect=effect,
        conditions_met=len(_CONDITION_ORDER) - len(unmet),
        still_needed=tuple(_CONDITION_LABELS[c] for c in unmet),
        deciding_election_turn=deciding,
        election_this_turn_too_soon=too_soon,
    )


# --------------------------------------------------------------------------
# The reform each link proposes
# --------------------------------------------------------------------------


def _executive_choice(
    opening: ConstitutionState, companions: tuple[ConstitutionalAxisTarget, ...]
) -> tuple[ExecutiveSystem, ExecutiveSelection] | None:
    """The government form a link proposes for an elected executive: an elected selection that
    keeps the current system if the C-rules allow it, otherwise the first coherent one in the
    engine's enum order (for a monarchy: presidential, direct election). `companions` are the other
    targets the same amendment carries, so coherence is judged on the whole trial."""
    candidates = [
        (system, selection)
        for system in ExecutiveSystem
        for selection in ExecutiveSelection
        if selection is not opening.executive_selection
        and condition_met(
            opening.model_copy(update={"executive_selection": selection}), "elected_executive"
        )
    ]
    candidates.sort(key=lambda pair: pair[0] is not opening.executive_system)
    for system, selection in candidates:
        targets = _sorted(companions + _form_targets(opening, system, selection))
        if trial_constitution(opening, targets) is not None:
            return system, selection
    return None


def _form_targets(
    opening: ConstitutionState, system: ExecutiveSystem, selection: ExecutiveSelection
) -> tuple[ConstitutionalAxisTarget, ...]:
    targets: list[ConstitutionalAxisTarget] = [ExecutiveSelectionTarget(value=selection)]
    if system is not opening.executive_system:
        targets.append(ExecutiveSystemTarget(value=system))
    return tuple(targets)


def _sorted(targets: tuple[ConstitutionalAxisTarget, ...]) -> tuple[ConstitutionalAxisTarget, ...]:
    return tuple(sorted(targets, key=lambda target: target.axis))


def _single_condition_targets(
    opening: ConstitutionState, condition: ConditionId
) -> tuple[str, tuple[ConstitutionalAxisTarget, ...]] | None:
    """`(card_id, targets)` of the existing catalog card that meets `condition` on its own."""
    if condition == "no_decree_authority":
        value = _satisfying_decree()
        return f"constitution_decree_authority_to_{value.value}", (
            DecreeAuthorityTarget(value=value),
        )
    if condition == "election_interval":
        return (
            f"constitution_election_interval_to_{QUALIFYING_INTERVAL_TURNS}",
            (ElectionIntervalTarget(value=QUALIFYING_INTERVAL_TURNS),),
        )
    choice = _executive_choice(opening, ())
    if choice is None:
        return None
    system, selection = choice
    return (
        f"constitution_government_form_{system.value}_{selection.value}",
        _sorted(_form_targets(opening, system, selection)),
    )


def qualifying_reform_targets(
    constitution: ConstitutionState,
) -> tuple[ConstitutionalAxisTarget, ...] | None:
    """The ONE amendment completing every unmet condition, with any companion change the C-rules
    require -- or `None` when no such amendment would qualify (the constitution is not
    non-competitive, or no coherent combination exists)."""
    if constitution_class(constitution) != "noncompetitive":
        return None
    unmet = _unmet(constitution)
    targets: list[ConstitutionalAxisTarget] = []
    if "no_decree_authority" in unmet:
        targets.append(DecreeAuthorityTarget(value=_satisfying_decree()))
    if "election_interval" in unmet:
        targets.append(ElectionIntervalTarget(value=QUALIFYING_INTERVAL_TURNS))
    if "elected_executive" in unmet:
        choice = _executive_choice(constitution, tuple(targets))
        if choice is None:
            return None
        targets.extend(_form_targets(constitution, *choice))
    combined = _sorted(tuple(targets))
    proposed = trial_constitution(constitution, combined)
    if proposed is None or constitution_class(proposed) != "competitive":
        return None
    return combined


# --------------------------------------------------------------------------
# The dashboard's objective
# --------------------------------------------------------------------------


class ObjectiveCondition(BaseModel):
    model_config = _STRICT

    id: ConditionId
    label: str
    current_text: str
    met: bool
    link_card_id: str | None = None
    """The existing catalog card that meets this condition on its own, when a link is offered.
    `None` when the condition is met, when no coherent card exists, or when enacting it alone would
    leave the constitution unable to qualify (`note` then says why)."""
    if_enacted_alone: AmendmentEffect | None = None
    note: str | None = None


class ObjectiveProjection(BaseModel):
    """`DashboardProjection.objective`: the stage, from the engine's eligibility and marker."""

    model_config = _STRICT

    stage: ObjectiveStage
    cannot_qualify_reason: CannotQualifyReason | None = None
    headline: str
    detail: str | None = None
    conditions_met: int
    conditions_text: str
    transition_text: str
    conditions: tuple[ObjectiveCondition, ...]
    transition_turn: int | None = None
    election_turn: int | None = None
    election_note: str | None = None
    qualifying_card_id: str | None = None
    """The card "Draft the qualifying reform" selects: the existing single card when one condition
    is unmet, `constitution_qualifying_reform` when more are. Only in the `reform` stage."""
    ordering_note: str | None = None


def _current_text(constitution: ConstitutionState, condition: ConditionId) -> str:
    if condition == "elected_executive":
        return EXECUTIVE_SELECTION_LABELS[constitution.executive_selection]
    if condition == "no_decree_authority":
        return DECREE_AUTHORITY_LABELS[constitution.decree_authority]
    return election_interval_label(constitution.national_election_interval_turns)


_ALONE_CANNOT_QUALIFY_NOTE = (
    "Not on its own: with an elected executive and no decree authority, but no election schedule, "
    "the constitution could no longer qualify. Set the election schedule first, or use Draft the "
    "qualifying reform."
)


def _conditions(politics: PoliticalState, *, offer_links: bool) -> tuple[ObjectiveCondition, ...]:
    constitution = politics.constitution
    rows: list[ObjectiveCondition] = []
    for condition in _CONDITION_ORDER:
        met = condition_met(constitution, condition)
        link: str | None = None
        effect: AmendmentEffect | None = None
        note: str | None = None
        if not met and offer_links:
            single = _single_condition_targets(constitution, condition)
            if single is not None:
                card_id, targets = single
                proposed = trial_constitution(constitution, targets)
                if proposed is not None:
                    effect = amendment_effect_if_enacted(politics, proposed)
                    if effect == "cannot_qualify":
                        note = _ALONE_CANNOT_QUALIFY_NOTE
                    else:
                        link = card_id
        rows.append(
            ObjectiveCondition(
                id=condition,
                label=_CONDITION_LABELS[condition],
                current_text=_current_text(constitution, condition),
                met=met,
                link_card_id=link,
                if_enacted_alone=effect,
                note=note,
            )
        )
    return tuple(rows)


def qualifying_card_id(politics: PoliticalState) -> str | None:
    targets = qualifying_reform_targets(politics.constitution)
    if targets is None or politics.terminal_outcome is not None:
        return None
    unmet = _unmet(politics.constitution)
    if len(unmet) == 1:
        single = _single_condition_targets(politics.constitution, unmet[0])
        return None if single is None else single[0]
    return QUALIFYING_REFORM_CARD_ID


def build_objective(politics: PoliticalState) -> ObjectiveProjection:
    constitution = politics.constitution
    met = _met_count(constitution)
    conditions_text = f"Constitutional conditions: {met} of 3 met"
    marker = politics.pending_liberalization
    transition_text = (
        f"Qualifying transition: recorded on turn {marker.set_at_turn}"
        if marker is not None
        else "Qualifying transition: not recorded"
    )
    election = politics.next_election_turn

    def make(
        stage: ObjectiveStage,
        headline: str,
        *,
        detail: str | None = None,
        cannot_qualify_reason: CannotQualifyReason | None = None,
        offer_links: bool = False,
        election_note: str | None = None,
        qualifying: str | None = None,
        ordering_note: str | None = None,
    ) -> ObjectiveProjection:
        return ObjectiveProjection(
            stage=stage,
            cannot_qualify_reason=cannot_qualify_reason,
            headline=headline,
            detail=detail,
            conditions_met=met,
            conditions_text=conditions_text,
            transition_text=transition_text,
            conditions=_conditions(politics, offer_links=offer_links),
            transition_turn=None if marker is None else marker.set_at_turn,
            election_turn=election,
            election_note=election_note,
            qualifying_card_id=qualifying,
            ordering_note=ordering_note,
        )

    outcome = politics.terminal_outcome
    if outcome is not None:
        victory = (
            outcome.bucket is OutcomeBucket.VICTORY
            and outcome.victory_reason is VictoryReason.PEACEFUL_LIBERALIZATION_COMPLETED
        )
        return make(
            "concluded",
            (
                "Objective complete: the qualifying election was won."
                if victory
                else "The campaign has ended."
            ),
        )

    if marker is not None:
        return make(
            "qualifying_election",
            (
                f"Win the qualifying election: turn {election}."
                if election is not None
                else "Win the next national election."
            ),
            detail=f"Transition recorded on turn {marker.set_at_turn}. Losing it ends the campaign.",
        )

    klass = constitution_class(constitution)
    if klass == "noncompetitive":
        unmet = _unmet(constitution)
        return make(
            "reform",
            f"Reform the constitution: {met} of 3 conditions met.",
            detail=f"Still needed: {_names(unmet)}.",
            offer_links=True,
            election_note=(
                f"An election on turn {election} before a qualifying reform won't complete the "
                "objective, and losing any election ends the campaign."
                if election is not None
                else None
            ),
            qualifying=qualifying_card_id(politics),
            ordering_note=ORDERING_NOTE,
        )

    if klass == "neither":
        return make(
            "cannot_qualify",
            "Your constitution can't qualify as it stands.",
            cannot_qualify_reason="missing_interval",
            detail=(
                "It has an elected executive and no decree authority, but no election schedule, so "
                "it is no longer under non-competitive rule, and only a reform from "
                f"non-competitive rule counts. {_WAY_BACK}"
            ),
        )

    return make(
        "cannot_qualify",
        "All three conditions are met, but no qualifying transition is recorded.",
        cannot_qualify_reason="already_competitive",
        detail=(
            "Only a reform from non-competitive rule counts, and this constitution reached its "
            f"present form without one. {_WAY_BACK}"
        ),
    )


# --------------------------------------------------------------------------
# The turn result's objective line
# --------------------------------------------------------------------------

_ENACTED_OUTCOMES = ("passed_legislative", "enacted_by_decree")


def objective_line(
    opening: PoliticalState | None, closing: PoliticalState, report: TurnReport
) -> str | None:
    """One sentence on what this turn did to the objective, from the stored report, the CLOSING
    state and the OPENING state's marker. `None` when nothing touched it, or when the opening
    state is unknown (a caller that cannot supply it gets no line rather than a guessed one).

    Terminal outcomes take precedence, then an enacted amendment by closing stage, then a failed
    amendment, then an election won without a transition."""
    if opening is None:
        return None
    opening_marker = opening.pending_liberalization
    closing_marker = closing.pending_liberalization
    outcome = closing.terminal_outcome
    if outcome is not None:
        if outcome.bucket is OutcomeBucket.VICTORY:
            return "Objective complete: you won the qualifying election."
        if outcome.removal_reason is RemovalReason.ELECTORAL_DEFEAT and opening_marker is not None:
            return "The qualifying election was lost; the campaign is over."
        return "The campaign ended before the objective was completed."

    amendment = report.constitutional_amendment
    election = report.election
    election_held = election is not None and election.result in ("won", "lost")
    if amendment is not None and amendment.proposed:
        if amendment.outcome.value not in _ENACTED_OUTCOMES:
            return "The amendment failed; the constitution and checklist are unchanged."
        if amendment.qualifies_as_liberalization_transition:
            line = (
                "The constitution now qualifies, and the transition is recorded. Win the election "
                f"on turn {closing.next_election_turn} to complete it."
            )
            if election_held:
                line += " This turn's election came too soon to count."
            return line
        if opening_marker is not None and closing_marker is not None:
            return (
                "The constitution still qualifies; the transition recorded on turn "
                f"{closing_marker.set_at_turn} stands. Election: turn {closing.next_election_turn}."
            )
        objective = build_objective(closing)
        if opening_marker is not None:
            return (
                "This amendment ended the qualifying transition: "
                f"{_names(_unmet(closing.constitution))} no longer met. {objective.headline}"
            )
        if objective.stage == "reform":
            return (
                f"{objective.conditions_met} of 3 constitutional conditions met. "
                f"Still needed: {_names(_unmet(closing.constitution))}."
            )
        if objective.cannot_qualify_reason == "missing_interval":
            return (
                f"{_met_count(closing.constitution)} of 3 conditions are met, but the constitution "
                "can no longer qualify: it is no longer under non-competitive rule, and only a "
                "reform from non-competitive rule counts."
            )
        return (
            "All three conditions are met, but this did not count as the qualifying reform: the "
            "constitution was not under non-competitive rule before it."
        )

    if election is not None and election.result == "won":
        return (
            "Election won, but no qualifying transition was recorded, so the objective is not "
            f"complete. Next election: turn {closing.next_election_turn}."
        )
    return None
