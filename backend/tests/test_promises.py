"""Commit 7 (characters slice): promises, and the independent oracle that proves them.

The centre of this module is `TestGroup60RejectsCoordinatedFalsehoods`. Every other tamper suite in
this repository perturbs ONE surface -- a report row, an entry, a state field -- and that is a real
but limited proof: it establishes that the four records of a turn must agree with each other. It
does not establish that reconciliation knows anything.

A COORDINATED tamper is the harder case. State, the governance row, the report entry and the trust
figures are all rewritten together, so every record agrees with every other record, and the only
thing wrong is the RULE they jointly claim was followed. Nothing about cross-record equality can
catch that. Only a check that carries its own transcribed copy of the lifecycle can -- which is
exactly what group 60 is for, and the only evidence that it is an oracle rather than a consistency
checker.

Each coordinated case below is therefore built by `_restate`, which DERIVES the rows, the entries
and the closing trust from the tampered state, so the forgery is internally perfect by construction
rather than by hand.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.content.scenarios import load_scenario_file
from app.simulation.decisions import (
    CabinetDecision,
    CabinetOrder,
    DecisionSet,
    PromiseDecision,
)
from app.simulation.promises import (
    ACHIEVEMENT_TERMS,
    LIVE_PROMISE_STATUSES,
    MAINTENANCE_TERMS,
    PROMISE_SETTLEMENT_REASON_IDS,
    TERMINAL_PROMISE_STATUSES,
    PromiseStatus,
    is_maintenance_term,
    trust_delta_bps,
)
from app.simulation.reconciliation import reconcile_political_legislative_and_survival_report
from app.simulation.report import PromiseReport, TurnReport, TurnReportEntry
from app.simulation.resolver import resolve_turn
from app.simulation.state import RULESET_VERSION, GameState, PromiseState
from tests.conftest import SCENARIO_DIR

_APP = Path(__file__).resolve().parents[1] / "app"
_RECONCILIATION_MODULE = _APP / "simulation" / "reconciliation.py"
_PHASES_MODULE = _APP / "simulation" / "phases.py"

_COS = "chief_of_staff"


def _scenario(name: str = "tiny_valid.yaml") -> GameState:
    return load_scenario_file(SCENARIO_DIR / name)


def _decisions(state: GameState, *decisions: Any) -> DecisionSet:
    return DecisionSet(
        expected_turn=state.turn,
        expected_state_version=state.state_version,
        decisions=tuple(decisions),
    )


def _chief_of_staff(state: GameState) -> str:
    player = state.world.countries[state.world.player_country_id]
    assert player.cabinet is not None
    return player.cabinet.offices[_COS].character_id


def _make(state: GameState, *, character_id: str, turns: int = 4) -> PromiseDecision:
    return PromiseDecision(
        action="make",
        character_id=character_id,
        term_kind="cabinet_tenure",
        subject_id=_COS,
        deadline_turn=state.turn + turns,
    )


def _group_60(
    opening: GameState, closing: GameState, report: TurnReport, decisions: DecisionSet | None
) -> list[str]:
    """Only group 60's problems, so a case cannot pass by tripping some other group."""
    return [
        problem
        for problem in reconcile_political_legislative_and_survival_report(
            opening_state=opening, closing_state=closing, report=report, decisions=decisions
        )
        if "(group 60)" in problem
    ]


def _restate(
    *,
    opening: GameState,
    closing: GameState,
    report: TurnReport,
    promises: dict[str, PromiseState],
) -> tuple[GameState, TurnReport]:
    """Rewrite the closing state, the governance rows, the entries AND the trust figures together,
    so all four records agree with each other and disagree only with the lifecycle.

    This is what makes the cases below coordinated rather than single-surface. Everything except
    `promises` is DERIVED from `promises`, using the same shape the engine uses, so there is no way
    for the forgery to be caught by one record contradicting another -- which is precisely the
    detection route being taken away.

    `model_construct` is used for the rows and the states, and only for that: several of these
    forgeries are shapes the real constructors refuse (an early fulfilment, a doubled delta). That
    the models refuse them is defence in depth and is asserted separately; the point here is that
    reconciliation must ALSO refuse them, since a corrupted save never went through a constructor.
    """
    turn = opening.turn
    world = closing.world
    opening_promises = opening.world.promises

    # Trust follows the restated rows, so the forgery pays itself.
    deltas: dict[str, int] = {}
    for key, promise in promises.items():
        opening_status = (
            PromiseStatus.PENDING if key not in opening_promises else opening_promises[key].status
        )
        if opening_status is not promise.status:
            deltas[promise.character_id] = deltas.get(promise.character_id, 0) + trust_delta_bps(
                promise.status
            )

    characters = dict(opening.world.characters)
    for character_id, delta in deltas.items():
        character = characters[character_id]
        characters[character_id] = character.model_copy(
            update={"personal_trust": max(0, min(10_000, character.personal_trust + delta))}
        )

    forged_state = closing.model_copy(
        update={"world": world.model_copy(update={"promises": promises, "characters": characters})}
    )

    governance = report.governance
    assert governance is not None
    pass_keys = {
        key for key, promise in opening_promises.items() if promise.status in LIVE_PROMISE_STATUSES
    } | {key for key, promise in promises.items() if promise.made_turn == turn}

    rows: list[PromiseReport] = []
    made_entries: list[TurnReportEntry] = []
    settlement_entries: list[TurnReportEntry] = []
    for key in sorted(pass_keys):
        promise = promises[key]
        character = characters[promise.character_id]
        opening_character = opening.world.characters[promise.character_id]
        opening_status = (
            PromiseStatus.PENDING if key not in opening_promises else opening_promises[key].status
        )
        moved = opening_status is not promise.status
        before = opening_character.personal_trust
        after = character.personal_trust
        params: dict[str, str | int] = {
            "promise_id": key,
            "character_id": promise.character_id,
            "character_display_name": character.display_name,
            "term_kind": promise.term_kind,
            "subject_id": promise.subject_id,
            "subject_display_name": _subject_display_name(forged_state, promise),
            "deadline_turn": promise.deadline_turn,
        }
        rows.append(
            PromiseReport.model_construct(
                promise_id=key,
                character_id=promise.character_id,
                character_display_name=character.display_name,
                term_kind=promise.term_kind,
                subject_id=promise.subject_id,
                subject_display_name=params["subject_display_name"],
                made_turn=promise.made_turn,
                deadline_turn=promise.deadline_turn,
                opening_status=opening_status,
                closing_status=promise.status,
                settled_turn=promise.settled_turn,
                qualifying_turn=promise.qualifying_turn,
                violated_turn=promise.violated_turn,
                trust_before_bps=before,
                trust_after_bps=after,
                trust_delta_bps=after - before,
            )
        )
        if promise.made_turn == turn:
            made_entries.append(
                TurnReportEntry(category="government", reason_id="promise_made", params=params)
            )
        # `.get`, not `[...]`: a forgery may assert a transition production cannot make --
        # a row "settling" INTO `PENDING` has no event to announce, which is why no reason id
        # exists for it. Omitting the entry keeps the forgery internally coherent, so the
        # transition itself is what gets rejected rather than a missing entry.
        reason_id = PROMISE_SETTLEMENT_REASON_IDS.get(promise.status)
        if moved and reason_id is not None:
            settlement_entries.append(
                TurnReportEntry(
                    category="government",
                    reason_id=reason_id,
                    params={**params, "trust_delta_bps": after - before},
                )
            )

    kept = [entry for entry in report.entries if not entry.reason_id.startswith("promise_")]
    forged_report = report.model_copy(
        update={
            "governance": governance.model_copy(update={"promises": tuple(rows)}),
            "entries": tuple(made_entries + settlement_entries + kept),
        }
    )
    return forged_state, forged_report


def _subject_display_name(state: GameState, promise: PromiseState) -> str:
    from app.simulation.state import (
        LEGISLATIVE_PROPOSAL_DISPLAY_NAMES,
        POST_DISPLAY_NAMES,
        CabinetPost,
    )

    if promise.term_kind == "cabinet_tenure":
        return POST_DISPLAY_NAMES[CabinetPost(promise.subject_id)]
    if promise.term_kind == "legislative_support":
        return LEGISLATIVE_PROPOSAL_DISPLAY_NAMES[promise.subject_id]
    return state.world.foreign_profiles[promise.subject_id].display_name


@pytest.fixture
def made() -> tuple[GameState, GameState, TurnReport, DecisionSet, str]:
    """A resolved turn carrying one live `cabinet_tenure` promise, deadline four turns out."""
    opening = _scenario()
    holder = _chief_of_staff(opening)
    decisions = _decisions(opening, _make(opening, character_id=holder))
    resolution = resolve_turn(opening, decisions)
    key = next(iter(resolution.state.world.promises))
    return opening, resolution.state, resolution.report, decisions, key


class TestGroup60RejectsCoordinatedFalsehoods:
    """State, rows, entries and trust all agree; only the RULE they claim is wrong.

    Each case asserts the clean resolution reconciles first, so a test cannot pass because the
    fixture was already broken -- the anti-vacuity discipline every tamper suite here follows.
    """

    def test_the_untampered_turn_reconciles(self, made: Any) -> None:
        opening, closing, report, decisions, _ = made
        assert _group_60(opening, closing, report, decisions) == []

    def test_an_early_fulfilment_is_rejected_though_every_record_agrees(self, made: Any) -> None:
        """The no-early-reward rule, which is the whole point of `MINIMUM_PROMISE_TURNS`.

        Closing state says FULFILLED, the character really is +1,000, the row states that
        transition, and the entry announces it. Nothing disagrees with anything. It is still a lie,
        because the promise was kept for one turn out of four.
        """
        opening, closing, report, decisions, key = made
        promise = closing.world.promises[key]
        forged = {
            key: promise.model_construct(
                **{
                    **dict(promise),
                    "status": PromiseStatus.FULFILLED,
                    "settled_turn": opening.turn,
                }
            )
        }
        state, tampered = _restate(opening=opening, closing=closing, report=report, promises=forged)
        problems = _group_60(opening, state, tampered, decisions)
        assert any("rather than on its deadline" in problem for problem in problems), problems

    def test_a_breach_dated_after_the_first_violation_is_rejected(self, made: Any) -> None:
        """A breach is dated to the FIRST violating turn. Postponing the date would let a player
        keep spending trust in bargains they had already forfeited."""
        opening, closing, report, decisions, key = made
        promise = closing.world.promises[key]
        forged = {
            key: promise.model_construct(
                **{
                    **dict(promise),
                    "status": PromiseStatus.BREACHED,
                    "violated_turn": opening.turn + 2,
                    "settled_turn": opening.turn + 2,
                }
            )
        }
        state, tampered = _restate(opening=opening, closing=closing, report=report, promises=forged)
        problems = _group_60(opening, state, tampered, decisions)
        assert any("dates its violation to" in problem for problem in problems), problems

    def test_a_forged_promise_id_is_rejected_though_it_keys_state_row_and_entry(
        self, made: Any
    ) -> None:
        """The id is a pure function of `(character_id, term_kind, made_turn)`. Renaming it
        consistently everywhere still fails, because group 60 recomputes the digest rather than
        reading the key -- which is what stops a build from inventing its own keying scheme."""
        opening, closing, report, decisions, key = made
        promise = closing.world.promises[key]
        forged_key = "pr_" + "b" * 64
        state, tampered = _restate(
            opening=opening, closing=closing, report=report, promises={forged_key: promise}
        )
        problems = _group_60(opening, state, tampered, decisions)
        assert any("closing_state carries no row under" in problem for problem in problems), (
            problems
        )

    def test_an_illegal_terminal_transition_is_rejected_everywhere_at_once(self) -> None:
        """`PENDING -> EXPIRED` is the penalty-free lapse the lifecycle refuses, and a terminal row
        may never move again. Both are stated as one allowlist of pairs, so a build that invented a
        transition fails even with every record telling the same story."""
        opening = _scenario()
        holder = _chief_of_staff(opening)
        decisions = _decisions(opening, _make(opening, character_id=holder))
        resolution = resolve_turn(opening, decisions)
        key = next(iter(resolution.state.world.promises))
        promise = resolution.state.world.promises[key]
        forged = {
            key: promise.model_construct(
                **{
                    **dict(promise),
                    "status": PromiseStatus.EXPIRED,
                    "settled_turn": promise.deadline_turn,
                    "released_turn": opening.turn,
                }
            )
        }
        state, tampered = _restate(
            opening=opening,
            closing=resolution.state,
            report=resolution.report,
            promises=forged,
        )
        problems = _group_60(opening, state, tampered, decisions)
        assert any("only a released promise may expire" in problem for problem in problems), (
            problems
        )

    def test_a_consistently_rebaselined_assistance_promise_is_rejected(self) -> None:
        """R14's immutability half, which is the only half a later turn can check.

        The attack it exists to stop: a promise not to draw aid, whose baseline is quietly raised to
        match what was actually drawn, so the pool looks untouched. Here the baseline is moved in
        state AND restated in the row, on a turn after creation -- internally perfect, and still
        rejected, because verified-once plus never-moved is the composition that stands in for a
        make-turn comparison group 60 cannot perform.
        """
        opening = _scenario()
        leader = next(
            character_id
            for character_id, character in sorted(opening.world.characters.items())
            if getattr(character.affiliation, "foreign_profile_id", None) == "kessia"
        )
        decisions = _decisions(
            opening,
            PromiseDecision(
                action="make",
                character_id=leader,
                term_kind="assistance_restraint",
                subject_id="kessia",
                deadline_turn=opening.turn + 4,
            ),
        )
        first = resolve_turn(opening, decisions)
        key = next(iter(first.state.world.promises))

        # The next turn is where "never moved" becomes checkable.
        quiet = _decisions(first.state)
        second = resolve_turn(first.state, quiet)
        promise = second.state.world.promises[key]
        forged = {
            key: promise.model_construct(**{**dict(promise), "baseline_assistance_drawn": 999_999})
        }
        state, tampered = _restate(
            opening=first.state, closing=second.state, report=second.report, promises=forged
        )
        problems = _group_60(first.state, state, tampered, quiet)
        assert any("re-baselined its assistance draw" in problem for problem in problems), problems

    @pytest.mark.parametrize(
        ("mutation", "expected"),
        [
            ("missing", "PROMISE_RELEASE row(s)"),
            ("extra", "PROMISE_RELEASE row(s)"),
            ("mispriced", "charges"),
        ],
    )
    def test_the_release_ledger_row_must_be_present_unique_and_exactly_priced(
        self, mutation: str, expected: str
    ) -> None:
        """A release is the one promise event that costs capital, so the ledger is the one surface
        a player can audit it on. Missing, doubled and mispriced are checked separately because
        they are three different lies about the same row."""
        opening = _scenario()
        holder = _chief_of_staff(opening)
        first = resolve_turn(opening, _decisions(opening, _make(opening, character_id=holder)))
        key = next(iter(first.state.world.promises))

        release = _decisions(
            first.state,
            PromiseDecision(action="release", character_id=holder, promise_id=key),
        )
        resolution = resolve_turn(first.state, release)
        assert _group_60(first.state, resolution.state, resolution.report, release) == []

        capital = resolution.report.political_capital
        assert capital is not None
        rows = list(capital.expenditures)
        promise_rows = [row for row in rows if row.category.value == "promise_release"]
        assert len(promise_rows) == 1, "the clean release pays exactly one row"
        others = [row for row in rows if row.category.value != "promise_release"]

        if mutation == "missing":
            forged_rows = tuple(others)
        elif mutation == "extra":
            forged_rows = tuple(others + promise_rows + promise_rows)
        else:
            forged_rows = tuple(
                others
                + [
                    promise_rows[0].model_construct(
                        **{**dict(promise_rows[0]), "political_capital": 1}
                    )
                ]
            )
        tampered = resolution.report.model_copy(
            update={
                "political_capital": capital.model_construct(
                    **{**dict(capital), "expenditures": forged_rows}
                )
            }
        )
        problems = _group_60(first.state, resolution.state, tampered, release)
        assert any(expected in problem for problem in problems), problems

    def test_qualification_claimed_for_a_decree_route_proposal_is_rejected(self) -> None:
        """R16, as a coordinated forgery rather than a matrix entry.

        A `legislative_support` promise is kept by putting the proposal to a CHAMBER. Governing by
        decree is the opposite of that -- it is the act of not asking -- so a decree turn qualifies
        nothing. Here the state claims a qualifying turn, the row restates it and the promise is
        marked fulfilled at its deadline; the records are consistent and the claim is false.
        """
        from app.simulation.decisions import BudgetDecision
        from app.simulation.legislature import ProposalRoute

        opening = _scenario("decree_state.yaml")
        leader = "leader_opposition_party"
        decisions = _decisions(
            opening,
            # Canonical kind order is REJECTED, not sorted (`decisions_json` is hash-covered), so
            # "budget" precedes "promise" here because that is the order the engine requires.
            BudgetDecision(personal_income_rate_bps=2500, route=ProposalRoute.DECREE),
            PromiseDecision(
                action="make",
                character_id=leader,
                term_kind="legislative_support",
                subject_id="budget",
                deadline_turn=opening.turn + 4,
            ),
        )
        resolution = resolve_turn(opening, decisions)
        key = next(iter(resolution.state.world.promises))

        # The real turn qualifies nothing: a decree never reached a chamber.
        assert resolution.state.world.promises[key].qualifying_turn is None
        assert _group_60(opening, resolution.state, resolution.report, decisions) == []

        promise = resolution.state.world.promises[key]
        forged = {
            key: promise.model_construct(**{**dict(promise), "qualifying_turn": opening.turn})
        }
        state, tampered = _restate(
            opening=opening, closing=resolution.state, report=resolution.report, promises=forged
        )
        problems = _group_60(opening, state, tampered, decisions)
        assert problems, "a decree route must not be able to qualify a legislative-support promise"

    def test_a_doubled_trust_delta_is_rejected_even_where_the_clamp_hides_it(self) -> None:
        """The clamp boundary is exactly where a double application becomes invisible in state.

        A character near zero who is breached once and breached twice closes on the same trust, so
        comparing closing trust against a plausible total proves nothing there. What gives it away
        is the DECLARED delta, which group 60 compares against the transcribed table rather than
        against the report's own arithmetic -- the reason that check exists at all.
        """
        opening = _scenario()
        holder = _chief_of_staff(opening)
        characters = dict(opening.world.characters)
        # Put the counterparty close enough to zero that -2,000 and -4,000 both clamp to 0.
        characters[holder] = characters[holder].model_copy(update={"personal_trust": 1_500})
        opening = opening.model_copy(
            update={"world": opening.world.model_copy(update={"characters": characters})}
        )

        decisions = _decisions(
            opening,
            CabinetDecision(orders=(CabinetOrder(post=_COS, character_id=None),)),
            _make(opening, character_id=holder),
        )
        resolution = resolve_turn(opening, decisions)
        key = next(iter(resolution.state.world.promises))
        assert resolution.state.world.promises[key].status is PromiseStatus.BREACHED
        assert resolution.state.world.characters[holder].personal_trust == 0
        assert _group_60(opening, resolution.state, resolution.report, decisions) == []

        governance = resolution.report.governance
        assert governance is not None
        row = governance.promises[0]
        # Applied twice. Closing trust is 0 either way, so ONLY the declared figure differs.
        doubled = row.model_construct(**{**dict(row), "trust_delta_bps": row.trust_delta_bps * 2})
        tampered = resolution.report.model_copy(
            update={"governance": governance.model_copy(update={"promises": (doubled,)})}
        )
        problems = _group_60(opening, resolution.state, tampered, decisions)
        assert any("licenses" in problem for problem in problems), problems

    def test_qualification_claimed_for_the_wrong_proposal_kind_is_rejected(self) -> None:
        """The other half of R16: a legislative-route BUDGET does not keep a promise about an
        AMENDMENT. Selecting the scratch by kind is what makes the two independent, and reading only
        the budget's route -- the draft plan's error -- would have made an amendment promise
        permanently unqualifiable in one direction and trivially forgeable in the other."""
        from app.simulation.decisions import BudgetDecision

        opening = _scenario("deficit_demo.yaml")
        leader = "leader_independents"
        decisions = _decisions(
            opening,
            BudgetDecision(personal_income_rate_bps=2000),
            PromiseDecision(
                action="make",
                character_id=leader,
                term_kind="legislative_support",
                subject_id="constitutional_amendment",
                deadline_turn=opening.turn + 4,
            ),
        )
        resolution = resolve_turn(opening, decisions)
        key = next(iter(resolution.state.world.promises))

        # A budget went to the chamber; the promise was about an amendment, so nothing qualified.
        assert resolution.state.world.promises[key].qualifying_turn is None
        assert _group_60(opening, resolution.state, resolution.report, decisions) == []

        promise = resolution.state.world.promises[key]
        forged = {
            key: promise.model_construct(**{**dict(promise), "qualifying_turn": opening.turn})
        }
        state, tampered = _restate(
            opening=opening, closing=resolution.state, report=resolution.report, promises=forged
        )
        problems = _group_60(opening, state, tampered, decisions)
        assert any("no legislative-route proposal of kind" in p for p in problems), problems

    def test_a_kept_promise_that_went_unrecorded_is_also_rejected(self) -> None:
        """The reverse direction, which matters just as much: a player who actually did the thing
        must not be denied the record of it. Asserted by stripping the qualifying turn from a turn
        that genuinely earned one."""
        from app.simulation.decisions import BudgetDecision

        opening = _scenario("deficit_demo.yaml")
        decisions = _decisions(
            opening,
            BudgetDecision(personal_income_rate_bps=2000),
            PromiseDecision(
                action="make",
                character_id="leader_independents",
                term_kind="legislative_support",
                subject_id="budget",
                deadline_turn=opening.turn + 4,
            ),
        )
        resolution = resolve_turn(opening, decisions)
        key = next(iter(resolution.state.world.promises))
        assert resolution.state.world.promises[key].qualifying_turn == opening.turn

        promise = resolution.state.world.promises[key]
        forged = {key: promise.model_construct(**{**dict(promise), "qualifying_turn": None})}
        state, tampered = _restate(
            opening=opening, closing=resolution.state, report=resolution.report, promises=forged
        )
        problems = _group_60(opening, state, tampered, decisions)
        assert any("records no qualifying turn" in p for p in problems), problems


_ALLOWED_PROMISE_IMPORTS = frozenset(
    {
        "MINIMUM_PROMISE_TURNS",
        "PROMISE_BREACHED_TRUST_LOSS_BPS",
        "PROMISE_EXPIRED_TRUST_BPS",
        "PROMISE_ID_LENGTH",
        "PROMISE_ID_PREFIX",
        "PROMISE_KEPT_TRUST_GAIN_BPS",
        "PROMISE_RELEASED_TRUST_BPS",
        "PROMISE_RELEASE_COST_CAPITAL",
        "PromiseStatus",
        "PromiseTermKind",
    }
)
"""What `reconciliation.py` may take from `promises`: the enums, the numeric calibration, and the
id's shape. Nothing else.

The line is CALIBRATION versus BEHAVIOUR, not constant versus function, and that distinction is the
whole of group 60's independence. A number both sides read is safe: a transcription error still
surfaces as a disagreement. A PARTITION both sides read is not -- if production files a term, a
status or an event on the wrong side, an importing reconciliation repeats the misclassification and
certifies it, and there is nothing left to disagree with.

So `MAINTENANCE_TERMS`, `ACHIEVEMENT_TERMS`, `LIVE_PROMISE_STATUSES`, `TERMINAL_PROMISE_STATUSES`
and `PROMISE_SETTLEMENT_REASON_IDS` are deliberately absent, though each looks like a constant.
Group 60 declares its own. An ALLOWLIST, not a denylist, so a newly added helper is refused by
default rather than reviewed for correctness later.
"""

_FORBIDDEN_PROMISE_CALLS = frozenset(
    {
        "promise_id",
        "trust_delta_bps",
        "is_maintenance_term",
        "earliest_legal_deadline",
        "validation_live_statuses",
        "_settle_promises",
        "_promise_qualifies",
        "_promise_violation_observed",
        "_promise_report_rows_and_entries",
    }
)
"""The production entry points group 60 must never call. `_promise_qualifies` is named explicitly
because R16 was caught there: a reconciliation re-using the production selector could not fail when
the selector picks the wrong scratch."""


class TestGroup60IsIndependent:
    def test_reconciliation_imports_only_calibration_and_vocabulary(self) -> None:
        tree = ast.parse(_RECONCILIATION_MODULE.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "app.simulation.promises":
                imported.update(alias.name for alias in node.names)
        assert imported, "reconciliation is expected to import the calibration constants"
        assert imported <= _ALLOWED_PROMISE_IMPORTS, sorted(imported - _ALLOWED_PROMISE_IMPORTS)

    def test_the_behavioural_partitions_are_never_imported(self) -> None:
        """Stated as its own test rather than left implicit in the allowlist, because these five
        are the ones a future edit would most plausibly reach for: each looks like a constant."""
        tree = ast.parse(_RECONCILIATION_MODULE.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "app.simulation.promises":
                imported.update(alias.name for alias in node.names)
        behavioural = {
            "ACHIEVEMENT_TERMS",
            "LIVE_PROMISE_STATUSES",
            "MAINTENANCE_TERMS",
            "PROMISE_SETTLEMENT_REASON_IDS",
            "TERMINAL_PROMISE_STATUSES",
        }
        assert not (imported & behavioural), sorted(imported & behavioural)

    def test_reconciliation_never_calls_the_production_promise_logic(self) -> None:
        tree = ast.parse(_RECONCILIATION_MODULE.read_text(encoding="utf-8"))
        called = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert not (called & _FORBIDDEN_PROMISE_CALLS), sorted(called & _FORBIDDEN_PROMISE_CALLS)

    def test_the_scan_detects_a_call_when_one_is_present(self) -> None:
        """Anti-vacuity: a scan that matched nothing would pass whatever the module did."""
        sample = ast.parse(
            "from app.simulation.promises import trust_delta_bps\nx = trust_delta_bps(status)\n"
        )
        called = {
            node.func.id
            for node in ast.walk(sample)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "trust_delta_bps" in called


class TestTheTranscriptionsAgreeWithTheEngine:
    """Independence must not become divergence. Two implementations, one answer -- a disagreement
    surfaces here rather than as a save that reconciles against a wrong rule."""

    def test_the_term_partition_agrees(self) -> None:
        from app.simulation.reconciliation import (
            _TRANSCRIBED_ACHIEVEMENT_TERMS,
            _TRANSCRIBED_MAINTENANCE_TERMS,
        )

        assert _TRANSCRIBED_MAINTENANCE_TERMS == MAINTENANCE_TERMS
        assert _TRANSCRIBED_ACHIEVEMENT_TERMS == ACHIEVEMENT_TERMS
        # ... and the two really do partition the type, so no term is filed twice or not at all.
        assert not (_TRANSCRIBED_MAINTENANCE_TERMS & _TRANSCRIBED_ACHIEVEMENT_TERMS)
        for term in MAINTENANCE_TERMS | ACHIEVEMENT_TERMS:
            assert is_maintenance_term(term) == (term in _TRANSCRIBED_MAINTENANCE_TERMS)

    def test_the_status_partition_agrees(self) -> None:
        from app.simulation.reconciliation import (
            _TRANSCRIBED_LIVE_PROMISE_STATUSES,
            _TRANSCRIBED_TERMINAL_PROMISE_STATUSES,
        )

        assert _TRANSCRIBED_LIVE_PROMISE_STATUSES == LIVE_PROMISE_STATUSES
        assert _TRANSCRIBED_TERMINAL_PROMISE_STATUSES == TERMINAL_PROMISE_STATUSES
        every_status = frozenset(PromiseStatus)
        assert every_status == (
            _TRANSCRIBED_LIVE_PROMISE_STATUSES | _TRANSCRIBED_TERMINAL_PROMISE_STATUSES
        )
        assert not (_TRANSCRIBED_LIVE_PROMISE_STATUSES & _TRANSCRIBED_TERMINAL_PROMISE_STATUSES)

    def test_the_trust_table_agrees_over_every_status(self) -> None:
        from app.simulation.reconciliation import _transcribed_promise_trust_delta_bps

        for status in PromiseStatus:
            assert _transcribed_promise_trust_delta_bps(status) == trust_delta_bps(status)

    def test_the_reason_mapping_agrees_over_every_status(self) -> None:
        from app.simulation.reconciliation import _transcribed_settlement_reason_id

        for status in PromiseStatus:
            assert _transcribed_settlement_reason_id(status) == PROMISE_SETTLEMENT_REASON_IDS.get(
                status
            )
        assert _transcribed_settlement_reason_id(PromiseStatus.PENDING) is None

    def test_the_id_transcription_agrees_across_a_sweep(self) -> None:
        from app.simulation.promises import promise_id
        from app.simulation.reconciliation import _transcribed_promise_id

        for character_id in ("a", "a__b", "__", "t1", "x" * 64):
            for term_kind in sorted(MAINTENANCE_TERMS | ACHIEVEMENT_TERMS):
                for made_turn in (0, 1, 7, 10**18):
                    assert _transcribed_promise_id(
                        character_id=character_id, term_kind=term_kind, made_turn=made_turn
                    ) == promise_id(
                        character_id=character_id, term_kind=term_kind, made_turn=made_turn
                    )


class TestPersonalTrustHasExactlyOneWriter:
    """`_commit_promise_settlements` is the ONLY thing in the repository that writes
    `personal_trust`, and this is the mechanical proof of it.

    That guarantee is what lets the bargain and the assistance modules keep READING trust without
    any of them gaining a write path -- the answer to "changed trust affects later assessments
    without writing trust anywhere else". A grep would not do: PD-1 and PD-2 were both logged for a
    search framed as call shapes rather than as symbols.
    """

    WRITER = "_commit_promise_settlements"

    COMPARISON_HELPERS = frozenset(
        {"_reconcile_promise_trust", "character_registry_moved_only_by_promise_trust"}
    )
    """The two reconciliation helpers that name `personal_trust` in a `model_copy` in order to
    COMPARE two characters field-by-field -- "equal except for trust" -- never to produce state.

    Named individually rather than waved through by module, because the allowance is what a future
    edit would hide behind. Both exist to prove the registry moved ONLY by trust, which is the
    opposite of writing it: they are how groups 58, 59 and 60 keep their byte-identity claims while
    permitting the one authorised mutation."""

    def _writers(self, module: Path) -> set[str]:
        """Every enclosing function that writes `personal_trust`, by assignment or `model_copy`."""
        tree = ast.parse(module.read_text(encoding="utf-8"))
        writers: set[str] = set()

        for function in ast.walk(tree):
            if not isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for node in ast.walk(function):
                # `x.personal_trust = ...`
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Attribute) and target.attr == "personal_trust":
                            writers.add(function.name)
                # `model_copy(update={"personal_trust": ...})`
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "model_copy"
                ):
                    for keyword in node.keywords:
                        if keyword.arg != "update" or not isinstance(keyword.value, ast.Dict):
                            continue
                        for key in keyword.value.keys:
                            if isinstance(key, ast.Constant) and key.value == "personal_trust":
                                writers.add(function.name)
        return writers

    def test_only_the_settlement_committer_writes_trust(self) -> None:
        for module in sorted(_APP.rglob("*.py")):
            writers = self._writers(module)
            if module == _PHASES_MODULE:
                assert writers == {self.WRITER}, sorted(writers)
            elif module == _RECONCILIATION_MODULE:
                assert not (writers - self.COMPARISON_HELPERS), (
                    f"{module.name}: {sorted(writers - self.COMPARISON_HELPERS)}"
                )
            else:
                # Every other module: not one write, of either shape. This is the half that matters
                # in practice -- a build that started nudging trust in a projection, a preview or a
                # CLI path would show up here rather than as a slow drift nobody could source.
                assert writers == set(), f"{module.name}: {sorted(writers)}"

    def test_the_scan_detects_both_write_shapes(self) -> None:
        """Anti-vacuity, for each shape separately: a scan that matched neither would pass a
        repository that wrote trust everywhere."""
        assignment = ast.parse("def f():\n    character.personal_trust = 0\n")
        copy = ast.parse("def g():\n    character.model_copy(update={'personal_trust': 0})\n")
        for tree, name in ((assignment, "f"), (copy, "g")):
            found: set[str] = set()
            for function in ast.walk(tree):
                if not isinstance(function, ast.FunctionDef):
                    continue
                for node in ast.walk(function):
                    if isinstance(node, ast.Assign):
                        for target in node.targets:
                            if (
                                isinstance(target, ast.Attribute)
                                and target.attr == "personal_trust"
                            ):
                                found.add(function.name)
                    if (
                        isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "model_copy"
                    ):
                        for keyword in node.keywords:
                            if keyword.arg == "update" and isinstance(keyword.value, ast.Dict):
                                for key in keyword.value.keys:
                                    if (
                                        isinstance(key, ast.Constant)
                                        and key.value == "personal_trust"
                                    ):
                                        found.add(function.name)
            assert name in found

    def test_a_fulfilment_at_the_trust_ceiling_records_the_licensed_gain(self) -> None:
        """The symmetric case to the breach floor, and it fails in the same way if the settlement
        records the realised movement instead of the licensed one.

        At 9,500 trust a kept promise is worth `+1,000`, of which only 500 can land. The row must
        say `+1,000` -- what keeping the promise was WORTH -- with the ceiling accounted for
        separately by `trust_after_bps`, exactly as the floor case records the full `-2,000` of a
        breach that could only take 1,500.

        Reachability, stated rather than implied: the highest authored `personal_trust` in any
        shipped scenario is 7,000, so no roster reaches the ceiling and this test lifts one
        character to 9,500 just as the floor case lowers one to 1,500. That is the calibration
        working -- trust is meant to be slow to build -- not a gap in the content.
        """
        opening = _scenario()
        holder = _chief_of_staff(opening)
        characters = dict(opening.world.characters)
        characters[holder] = characters[holder].model_copy(update={"personal_trust": 9_500})
        opening = opening.model_copy(
            update={"world": opening.world.model_copy(update={"characters": characters})}
        )

        state = opening
        decisions = _decisions(state, _make(state, character_id=holder))
        resolution = resolve_turn(state, decisions)
        state = resolution.state
        assert _group_60(opening, state, resolution.report, decisions) == []

        # Run the horizon out. The deadline turn is the only one that pays.
        for _ in range(4):
            previous = state
            quiet = _decisions(state)
            resolution = resolve_turn(state, quiet)
            state = resolution.state
            assert _group_60(previous, state, resolution.report, quiet) == []

        governance = resolution.report.governance
        assert governance is not None
        (row,) = governance.promises
        assert row.closing_status is PromiseStatus.FULFILLED
        assert row.trust_before_bps == 9_500
        assert row.trust_delta_bps == 1_000, (
            "the LICENSED gain, not the 500 that survived the clamp"
        )
        assert row.trust_after_bps == 10_000
        assert state.world.characters[holder].personal_trust == 10_000

    def test_a_doubled_gain_cannot_hide_behind_the_trust_ceiling(self) -> None:
        """The ceiling hides a double application exactly as the floor does: 9,500 + 1,000 and
        9,500 + 2,000 both close at 10,000, so comparing closing trust proves nothing there. Only
        the declared figure gives it away."""
        opening = _scenario()
        holder = _chief_of_staff(opening)
        characters = dict(opening.world.characters)
        characters[holder] = characters[holder].model_copy(update={"personal_trust": 9_500})
        opening = opening.model_copy(
            update={"world": opening.world.model_copy(update={"characters": characters})}
        )

        state = opening
        resolution = resolve_turn(state, _decisions(state, _make(state, character_id=holder)))
        state = resolution.state
        for _ in range(4):
            previous = state
            quiet = _decisions(state)
            resolution = resolve_turn(state, quiet)
            state = resolution.state

        governance = resolution.report.governance
        assert governance is not None
        (row,) = governance.promises
        assert row.trust_after_bps == 10_000

        doubled = row.model_construct(**{**dict(row), "trust_delta_bps": 2_000})
        tampered = resolution.report.model_copy(
            update={"governance": governance.model_copy(update={"promises": (doubled,)})}
        )
        problems = _group_60(previous, state, tampered, quiet)
        assert any("licenses" in problem for problem in problems), problems


class TestReleaseEligibilityHasOneDefinition:
    """`release_block_reason` is the single rule slot 1's code 7 and the projection both read.

    Building it found two releases the engine had been accepting, because code 7 was reusing code
    5's `validation_live_statuses` -- a predicate that answers a DIFFERENT question ("does this pair
    already have something live?"). Both are pinned below, and both are real: one charged the price
    twice for nothing, the other let a player duck a settlement that was already due.
    """

    def test_the_predicate_is_total_over_every_status_and_the_absent_case(self) -> None:
        """Code 7's domain is four cases, not two, so the helper must answer for all of them --
        otherwise "slot 1 raises code 7 exactly when this returns a reason" is simply false."""
        from app.simulation.promises import release_block_reason

        assert (
            release_block_reason(status=None, deadline_turn=None, resolving_turn=3)
            == "promise_missing"
        )
        for status in TERMINAL_PROMISE_STATUSES:
            assert (
                release_block_reason(status=status, deadline_turn=9, resolving_turn=3)
                == "promise_already_settled"
            )
        assert (
            release_block_reason(status=PromiseStatus.CANCELLED, deadline_turn=9, resolving_turn=3)
            == "promise_already_released"
        )
        assert (
            release_block_reason(status=PromiseStatus.PENDING, deadline_turn=3, resolving_turn=3)
            == "promise_past_releasing"
        )
        assert (
            release_block_reason(status=PromiseStatus.PENDING, deadline_turn=4, resolving_turn=3)
            is None
        )
        # Every status is answered: none falls through to an accidental `None`.
        for status in PromiseStatus:
            verdict = release_block_reason(status=status, deadline_turn=9, resolving_turn=3)
            assert verdict is not None or status is PromiseStatus.PENDING

    def test_an_already_released_promise_cannot_be_released_again(self) -> None:
        """Defect 1. It was accepted before the shared predicate landed: the price would have been
        charged a second time, `released_turn` reset, and nothing bought -- the horizon runs to the
        ORIGINAL deadline either way."""
        from app.core.errors import TurnResolutionError

        opening = _scenario()
        holder = _chief_of_staff(opening)
        first = resolve_turn(opening, _decisions(opening, _make(opening, character_id=holder)))
        key = next(iter(first.state.world.promises))
        released = resolve_turn(
            first.state,
            _decisions(
                first.state,
                PromiseDecision(action="release", character_id=holder, promise_id=key),
            ),
        )
        assert released.state.world.promises[key].status is PromiseStatus.CANCELLED

        with pytest.raises(TurnResolutionError) as exc_info:
            resolve_turn(
                released.state,
                _decisions(
                    released.state,
                    PromiseDecision(action="release", character_id=holder, promise_id=key),
                ),
            )
        message = str(exc_info.value)
        assert "promise_release_names_no_live_promise" in message
        assert "promise_already_released" in message

    def test_a_promise_due_this_turn_is_past_releasing(self) -> None:
        """Defect 2, and the sharper of the two: a promise whose deadline is THIS turn is about to
        settle on its merits. Releasing it would convert a breach or a fulfilment into a paid
        cancellation -- the settlement-ducking step 2 of the precedence exists to forbid."""
        from app.core.errors import TurnResolutionError

        opening = _scenario()
        holder = _chief_of_staff(opening)
        state = resolve_turn(
            opening, _decisions(opening, _make(opening, character_id=holder))
        ).state
        key = next(iter(state.world.promises))
        deadline = state.world.promises[key].deadline_turn

        # Walk to the turn BEFORE the deadline: still releasable.
        while state.turn < deadline - 1:
            state = resolve_turn(state, _decisions(state)).state
        assert state.turn == deadline - 1
        ok = resolve_turn(
            state,
            _decisions(
                state, PromiseDecision(action="release", character_id=holder, promise_id=key)
            ),
        )
        assert ok.state.world.promises[key].status is PromiseStatus.CANCELLED

        # ... and on the deadline turn itself it is not.
        due = resolve_turn(state, _decisions(state)).state
        assert due.turn == deadline
        with pytest.raises(TurnResolutionError) as exc_info:
            resolve_turn(
                due,
                _decisions(
                    due, PromiseDecision(action="release", character_id=holder, promise_id=key)
                ),
            )
        assert "promise_past_releasing" in str(exc_info.value)

    def test_every_terminal_status_is_reached_through_its_own_lifecycle(self) -> None:
        """`TERMINAL_PROMISE_STATUSES` has three members reached three different ways, and a matrix
        that ran one promise out to its deadline would prove only the first while appearing to cover
        all three. So each is built by the path that actually produces it -- and then a release of
        each is refused, which is the branch under test.
        """
        from app.api.decision_preflight import first_decision_problem
        from app.core.errors import TurnResolutionError
        from app.simulation.promises import release_block_reason

        reached: dict[PromiseStatus, tuple[GameState, str, str]] = {}

        # FULFILLED: keep a tenure promise to its deadline.
        opening = _scenario()
        holder = _chief_of_staff(opening)
        state = resolve_turn(
            opening, _decisions(opening, _make(opening, character_id=holder))
        ).state
        key = next(iter(state.world.promises))
        while state.world.promises[key].status is PromiseStatus.PENDING:
            state = resolve_turn(state, _decisions(state)).state
        assert state.world.promises[key].status is PromiseStatus.FULFILLED
        reached[PromiseStatus.FULFILLED] = (state, key, holder)

        # BREACHED: violate the same maintenance term in the promise's own set.
        opening = _scenario()
        state = resolve_turn(
            opening,
            _decisions(
                opening,
                CabinetDecision(orders=(CabinetOrder(post=_COS, character_id=None),)),
                _make(opening, character_id=holder),
            ),
        ).state
        key = next(iter(state.world.promises))
        assert state.world.promises[key].status is PromiseStatus.BREACHED
        reached[PromiseStatus.BREACHED] = (state, key, holder)

        # EXPIRED: release, then run the ORIGINAL horizon out.
        opening = _scenario()
        state = resolve_turn(
            opening, _decisions(opening, _make(opening, character_id=holder))
        ).state
        key = next(iter(state.world.promises))
        state = resolve_turn(
            state,
            _decisions(
                state, PromiseDecision(action="release", character_id=holder, promise_id=key)
            ),
        ).state
        assert state.world.promises[key].status is PromiseStatus.CANCELLED
        while state.world.promises[key].status is PromiseStatus.CANCELLED:
            state = resolve_turn(state, _decisions(state)).state
        assert state.world.promises[key].status is PromiseStatus.EXPIRED
        reached[PromiseStatus.EXPIRED] = (state, key, holder)

        # All three, by three different lifecycles -- and each refuses a release on BOTH surfaces.
        assert set(reached) == TERMINAL_PROMISE_STATUSES
        for status, (settled, promise_key, character_id) in sorted(reached.items()):
            assert settled.world.promises[promise_key].status is status
            decisions = _decisions(
                settled,
                PromiseDecision(
                    action="release", character_id=character_id, promise_id=promise_key
                ),
            )

            # The helper names the DETAILED branch reason...
            assert (
                release_block_reason(
                    status=status,
                    deadline_turn=settled.world.promises[promise_key].deadline_turn,
                    resolving_turn=settled.turn,
                )
                == "promise_already_settled"
            ), status

            # ... while both public surfaces report the one fixed CODE. Preflight is asserted here
            # and not only in the blocked-case test above, which covers absent, cancelled and
            # due-pending rows but never reaches a settled one.
            problem = first_decision_problem(settled, decisions)
            assert problem is not None, status
            assert problem.code == "promise_release_names_no_live_promise", status

            with pytest.raises(TurnResolutionError) as exc_info:
                resolve_turn(settled, decisions)
            message = str(exc_info.value)
            assert "promise_release_names_no_live_promise" in message
            assert "promise_already_settled" in message

    def test_resolver_and_preflight_agree_on_every_matrix_case(self) -> None:
        """Parity across the PUBLIC namespace, which is the one both surfaces owe the client.

        `release_block_reason` distinguishes four internal diagnostics, but `PROMISE_REJECTION_CODES`
        is a seven-code contract: every blocked release is `promise_release_names_no_live_promise` on
        both surfaces, with the diagnostic carried as explanatory text. A preflight that answered
        `promise_missing` as a CODE would be inventing an eighth, which is exactly the drift a single
        shared predicate is supposed to prevent -- so the predicate is shared and the code is fixed.
        """
        from app.api.decision_preflight import first_decision_problem
        from app.core.errors import TurnResolutionError

        opening = _scenario()
        holder = _chief_of_staff(opening)

        # Each case is BUILT: a fresh scenario carries no promises, so reading authored state would
        # prove these branches by never exercising them.
        live = resolve_turn(opening, _decisions(opening, _make(opening, character_id=holder))).state
        key = next(iter(live.world.promises))
        cancelled = resolve_turn(
            live,
            _decisions(
                live, PromiseDecision(action="release", character_id=holder, promise_id=key)
            ),
        ).state
        due = live
        while due.turn < live.world.promises[key].deadline_turn:
            due = resolve_turn(due, _decisions(due)).state

        blocked_cases: list[tuple[str, GameState, str]] = [
            ("absent id", live, "pr_" + "c" * 64),
            ("already released", cancelled, key),
            ("due this turn", due, key),
        ]
        for label, state, promise_key in blocked_cases:
            decisions = _decisions(
                state,
                PromiseDecision(action="release", character_id=holder, promise_id=promise_key),
            )
            problem = first_decision_problem(state, decisions)
            assert problem is not None, label
            assert problem.code == "promise_release_names_no_live_promise", label
            with pytest.raises(TurnResolutionError) as exc_info:
                resolve_turn(state, decisions)
            assert "promise_release_names_no_live_promise" in str(exc_info.value), label

        # ... and the one releasable case is accepted by both.
        ok_decisions = _decisions(
            live, PromiseDecision(action="release", character_id=holder, promise_id=key)
        )
        assert first_decision_problem(live, ok_decisions) is None
        assert (
            resolve_turn(live, ok_decisions).state.world.promises[key].status
            is PromiseStatus.CANCELLED
        )

    def test_preflight_and_resolver_agree_on_every_make_rejection_code(self) -> None:
        """One case per `make` code, asserting the two surfaces name the IDENTICAL literal.

        Code 6 is covered separately below, because reaching it needs a constructed state.
        """
        from app.api.decision_preflight import first_decision_problem
        from app.core.errors import TurnResolutionError

        opening = _scenario()
        holder = _chief_of_staff(opening)
        cases: list[tuple[str, PromiseDecision]] = [
            (
                "promise_character_unknown",
                PromiseDecision(
                    action="make",
                    character_id="nobody_at_all",
                    term_kind="cabinet_tenure",
                    subject_id=_COS,
                    deadline_turn=opening.turn + 4,
                ),
            ),
            (
                "promise_term_not_available_for_this_character",
                PromiseDecision(
                    action="make",
                    character_id=holder,
                    term_kind="legislative_support",
                    subject_id="budget",
                    deadline_turn=opening.turn + 4,
                ),
            ),
            (
                "promise_subject_unknown",
                PromiseDecision(
                    action="make",
                    character_id=holder,
                    term_kind="cabinet_tenure",
                    subject_id="minister_for_nothing",
                    deadline_turn=opening.turn + 4,
                ),
            ),
            (
                "promise_deadline_too_soon",
                PromiseDecision(
                    action="make",
                    character_id=holder,
                    term_kind="cabinet_tenure",
                    subject_id=_COS,
                    deadline_turn=opening.turn + 3,
                ),
            ),
        ]
        for code, decision in cases:
            decisions = _decisions(opening, decision)
            problem = first_decision_problem(opening, decisions)
            assert problem is not None, code
            assert problem.code == code, f"{code}: preflight said {problem.code}"
            with pytest.raises(TurnResolutionError) as exc_info:
                resolve_turn(opening, decisions)
            assert code in str(exc_info.value), code

        # Code 5 needs a live promise, so it is built rather than declared.
        live = resolve_turn(opening, _decisions(opening, _make(opening, character_id=holder))).state
        reissue = _decisions(live, _make(live, character_id=holder))
        problem = first_decision_problem(live, reissue)
        assert problem is not None
        assert problem.code == "promise_term_already_live_for_this_character"
        with pytest.raises(TurnResolutionError) as exc_info:
            resolve_turn(live, reissue)
        assert "promise_term_already_live_for_this_character" in str(exc_info.value)

    def _collision_row(self, *, character_id: str, made_turn: int) -> PromiseState:
        """A row occupying exactly the id a `make` on `made_turn` would derive, which is NOT
        validation-live -- so code 5 passes and code 6 is the check that fires.

        `BREACHED` rather than `FULFILLED`, and that choice is forced:
        `_terminal_settlement_lands_in_the_window` pins a fulfilment to its DEADLINE, which here
        would be four turns in the future, while it permits a breach anywhere in the window
        "including `made_turn` -- a player who promises and breaks the promise in the same decision
        set has really done that".

        **The ROW is engine-producible; the STATE is deliberately not.** No `model_construct` bypass
        is needed, because a promise made and breached on one turn is a real thing the settler
        produces. What no history can produce is this row sitting in the OPENING state of turn
        `made_turn` -- a promise made at `T` exists only once `T` has resolved. That is the point
        rather than a flaw: code 6 guards against a corrupted or hand-assembled save, so its fixture
        is a controlled structural-backstop state, not a reproducible campaign.
        """
        return PromiseState(
            character_id=character_id,
            term_kind="cabinet_tenure",
            subject_id=_COS,
            made_turn=made_turn,
            deadline_turn=made_turn + 4,
            status=PromiseStatus.BREACHED,
            violated_turn=made_turn,
            settled_turn=made_turn,
        )

    def _with_promises(self, state: GameState, promises: dict[str, PromiseState]) -> GameState:
        return state.model_copy(
            update={"world": state.world.model_copy(update={"promises": promises})}
        )

    def test_a_promise_id_collision_is_refused_by_both_surfaces(self) -> None:
        """Code 6 is a STRUCTURAL BACKSTOP, and the plan requires it asserted rather than excused.

        It is unreachable in ordinary play -- the id is a pure function of
        `(character_id, term_kind, made_turn)` and at most one promise decision may appear per turn
        -- but "unreachable" is a claim about inputs, not a reason to leave the branch unproven. A
        corrupted or hand-assembled save can present exactly this state, which is what the check
        exists for, and the id-collision defence explicitly covers terminal rows.

        The fixture is therefore a CONTROLLED STRUCTURAL-BACKSTOP STATE: every row in it is
        model-valid and of a shape the engine really produces, while the opening state as a whole is
        one no sequence of resolved turns could have reached. Both halves matter -- a fixture built
        by bypassing the constructors would prove nothing about the real models.
        """
        from app.api.decision_preflight import first_decision_problem
        from app.core.errors import TurnResolutionError
        from app.simulation.promises import promise_id

        opening = _scenario()
        holder = _chief_of_staff(opening)
        collision_id = promise_id(
            character_id=holder, term_kind="cabinet_tenure", made_turn=opening.turn
        )
        state = self._with_promises(
            opening,
            {collision_id: self._collision_row(character_id=holder, made_turn=opening.turn)},
        )
        decisions = _decisions(state, _make(state, character_id=holder))

        problem = first_decision_problem(state, decisions)
        assert problem is not None
        assert problem.code == "promise_id_collision"
        with pytest.raises(TurnResolutionError) as exc_info:
            resolve_turn(state, decisions)
        assert "promise_id_collision" in str(exc_info.value)

    def test_code_5_precedes_code_6_when_a_state_carries_both(self) -> None:
        """Precedence, asserted rather than assumed: a scheduling conflict is the more useful thing
        to tell a player, and the structural backstop is reported only when nothing else applies.

        Two rows for one `(character, term)` pair is not representable through ordinary play --
        cardinality is enforced at SUBMISSION, not at rest -- which is precisely why both checks
        exist and why this state has to be constructed to test their order. Like the collision
        fixture above, the rows are model-valid and the assembled state is deliberately outside any
        reachable history.
        """
        from app.api.decision_preflight import first_decision_problem
        from app.core.errors import TurnResolutionError
        from app.simulation.promises import promise_id

        opening = _scenario()
        holder = _chief_of_staff(opening)
        collision_id = promise_id(
            character_id=holder, term_kind="cabinet_tenure", made_turn=opening.turn
        )
        # A live row for the same pair, under a DIFFERENT id (an earlier made_turn), so code 5 and
        # code 6 are both satisfied by the same decision.
        live_id = promise_id(
            character_id=holder, term_kind="cabinet_tenure", made_turn=opening.turn + 1
        )
        live_row = PromiseState(
            character_id=holder,
            term_kind="cabinet_tenure",
            subject_id=_COS,
            made_turn=opening.turn,
            deadline_turn=opening.turn + 6,
            status=PromiseStatus.PENDING,
        )
        state = self._with_promises(
            opening,
            {
                collision_id: self._collision_row(character_id=holder, made_turn=opening.turn),
                live_id: live_row,
            },
        )
        decisions = _decisions(state, _make(state, character_id=holder))

        problem = first_decision_problem(state, decisions)
        assert problem is not None
        assert problem.code == "promise_term_already_live_for_this_character", (
            "code 5 precedes code 6"
        )
        with pytest.raises(TurnResolutionError) as exc_info:
            resolve_turn(state, decisions)
        message = str(exc_info.value)
        assert "promise_term_already_live_for_this_character" in message
        assert "promise_id_collision" not in message


class TestEveryPromiseReasonIsRegistered:
    """The gap that let five emitted reason ids reach a player as fallback text.

    `test_every_registered_reason_id_has_a_sample_and_renders_cleanly` runs over the REGISTRY, so it
    proves registered ids have samples and says nothing about ids the engine emits but never
    registered. Until this class existed, all five promise reasons were emitted by slot 15, rendered
    as fallback text in both CLI paths, and not one test failed.

    Two pins, catching opposite mistakes: the registry pin catches an id registered but never
    emitted, and the emission pin catches an id emitted but never registered. Neither subsumes the
    other.
    """

    EXPECTED = frozenset({"promise_made", *PROMISE_SETTLEMENT_REASON_IDS.values()})
    """DERIVED from the production mapping, never retyped -- so a sixth status cannot leave this pin
    behind. That is the opposite of group 60's discipline and deliberately so: group 60 is an ORACLE
    and must be able to disagree with production, while this asks "is everything the engine can emit
    actually registered", a question about the registries whose completeness depends on reading the
    real mapping."""

    def test_the_five_ids_are_exactly_what_the_engine_can_emit(self) -> None:
        assert {
            "promise_made",
            "promise_breached",
            "promise_expired",
            "promise_fulfilled",
            "promise_released",
        } == self.EXPECTED

    def test_every_promise_reason_has_an_api_label(self) -> None:
        from app.api.projections import REASON_LABELS

        assert set(REASON_LABELS) >= self.EXPECTED, sorted(self.EXPECTED - set(REASON_LABELS))

    def test_every_promise_reason_has_a_cli_renderer(self) -> None:
        from app.cli import REASON_RENDERERS

        assert set(REASON_RENDERERS) >= self.EXPECTED, sorted(self.EXPECTED - set(REASON_RENDERERS))

    def test_every_promise_reason_has_a_renderer_sample(self) -> None:
        from tests.test_reason_renderers import _SAMPLE_PARAMS

        assert set(_SAMPLE_PARAMS) >= self.EXPECTED, sorted(self.EXPECTED - set(_SAMPLE_PARAMS))

    def test_every_reason_a_real_campaign_emits_is_registered_and_renders(self) -> None:
        """The emission half, in the shape of the existing legislative umbrella test.

        This one depends on no mapping at all -- it reads what the engine ACTUALLY emitted -- so it
        still catches an id the mapping itself got wrong, which the three registry pins above
        cannot.
        """
        from app.cli import REASON_RENDERERS, render_entry
        from tests.test_reason_renderers import _SAMPLE_PARAMS

        emitted: set[str] = set()
        for report in _promise_campaign_reports():
            for entry in report.entries:
                if not entry.reason_id.startswith("promise_"):
                    continue
                emitted.add(entry.reason_id)
                assert entry.reason_id in REASON_RENDERERS, entry.reason_id
                assert entry.reason_id in _SAMPLE_PARAMS, entry.reason_id
                rendered = render_entry(entry)
                assert "unrendered" not in rendered, entry.reason_id
                assert "error rendering" not in rendered, entry.reason_id
                # No raw identifier reaches a player: the sentence is built from snapshotted display
                # names, so a post value or a character id appearing here is a defect.
                assert "chief_of_staff" not in rendered, rendered
                assert "cabinet_tenure" not in rendered, rendered

        # Anti-vacuity: the campaign really did exercise all five, so this cannot pass by emitting
        # nothing at all.
        assert emitted == TestEveryPromiseReasonIsRegistered.EXPECTED, sorted(emitted)


def _promise_campaign_reports() -> list[TurnReport]:
    """Resolve campaigns that between them emit every one of the five promise reasons.

    Three separate runs, because the lifecycles are mutually exclusive: a promise that is kept
    cannot also be breached, and one that is released cannot also be fulfilled.
    """
    reports: list[TurnReport] = []

    def _run(state: GameState, *decisions: Any) -> GameState:
        resolution = resolve_turn(state, _decisions(state, *decisions))
        reports.append(resolution.report)
        return resolution.state

    # made -> fulfilled
    opening = _scenario()
    holder = _chief_of_staff(opening)
    state = _run(opening, _make(opening, character_id=holder))
    key = next(iter(state.world.promises))
    while state.world.promises[key].status is PromiseStatus.PENDING:
        state = _run(state)

    # made -> breached, in one set
    opening = _scenario()
    _run(
        opening,
        CabinetDecision(orders=(CabinetOrder(post=_COS, character_id=None),)),
        _make(opening, character_id=holder),
    )

    # made -> released -> expired
    opening = _scenario()
    state = _run(opening, _make(opening, character_id=holder))
    key = next(iter(state.world.promises))
    state = _run(state, PromiseDecision(action="release", character_id=holder, promise_id=key))
    while state.world.promises[key].status is PromiseStatus.CANCELLED:
        state = _run(state)

    return reports


class TestThePromiseProjectionAndPreview:
    """What the interface is told, and that it agrees with what the engine will do."""

    def test_options_are_valid_triples_with_current_labels_and_the_engine_s_deadline(self) -> None:
        from app.api.projections import build_decision_options
        from app.simulation.promises import earliest_legal_deadline

        for scenario in ("tiny_valid.yaml", "decree_state.yaml", "deficit_demo.yaml"):
            state = _scenario(scenario)
            options = build_decision_options(state).promise_options
            assert options, scenario
            for option in options:
                # The triple is one the resolver would accept -- proved by submitting it.
                decisions = _decisions(
                    state,
                    PromiseDecision(
                        action="make",
                        character_id=option.character_id,
                        term_kind=option.term_kind,  # type: ignore[arg-type]
                        subject_id=option.subject_id,
                        deadline_turn=option.earliest_legal_deadline,
                    ),
                )
                resolve_turn(state, decisions)
                # The deadline is the engine's, not `turn + 4` recomputed here.
                assert option.earliest_legal_deadline == earliest_legal_deadline(
                    made_turn=state.turn
                )
                # Labels are CURRENT registry values, and no raw identifier is offered as prose.
                assert (
                    option.character_display_name
                    == state.world.characters[option.character_id].display_name
                )
                assert "_" not in option.subject_display_name

    def test_a_renamed_character_shows_renamed_here_unlike_a_report_row(self) -> None:
        """The distinction that makes "current, not snapshotted" a real rule rather than wording.

        A `PromiseReport` row keeps the name its turn was resolved under; this projection describes
        what exists to choose from NOW, so a rename must surface here immediately. Getting the two
        backwards would either rewrite history or offer stale names.
        """
        from app.api.projections import build_decision_options

        state = _scenario()
        holder = _chief_of_staff(state)
        characters = dict(state.world.characters)
        characters[holder] = characters[holder].model_copy(
            update={"display_name": "Renamed Person"}
        )
        renamed = state.model_copy(
            update={"world": state.world.model_copy(update={"characters": characters})}
        )
        options = build_decision_options(renamed).promise_options
        names = {
            option.character_display_name for option in options if option.character_id == holder
        }
        assert names == {"Renamed Person"}

    def test_make_option_visibility_follows_the_r11_boundary(self) -> None:
        """A reissue is legal at the original deadline and not before, so the OFFER must appear at
        exactly that turn. Offering at `d - 1` would propose a set the resolver rejects as code 5;
        hiding at `d` would conceal one that is legal."""
        from app.api.projections import build_decision_options

        opening = _scenario()
        holder = _chief_of_staff(opening)
        state = resolve_turn(
            opening, _decisions(opening, _make(opening, character_id=holder))
        ).state
        key = next(iter(state.world.promises))
        deadline = state.world.promises[key].deadline_turn
        state = resolve_turn(
            state,
            _decisions(
                state, PromiseDecision(action="release", character_id=holder, promise_id=key)
            ),
        ).state

        def offered(current: GameState) -> bool:
            return any(
                option.character_id == holder and option.term_kind == "cabinet_tenure"
                for option in build_decision_options(current).promise_options
            )

        while state.turn < deadline - 1:
            assert not offered(state), f"turn {state.turn}: the abandoned horizon still occupies it"
            state = resolve_turn(state, _decisions(state)).state
        assert state.turn == deadline - 1
        assert not offered(state), "at d - 1 the pair is still barred"
        state = resolve_turn(state, _decisions(state)).state
        assert state.turn == deadline
        assert offered(state), "at d the bar lifts and the reissue must be offered"

    def test_active_promises_carry_pending_and_cancelled_with_a_projected_verdict(self) -> None:
        from app.api.projections import build_decision_options

        opening = _scenario()
        holder = _chief_of_staff(opening)
        state = resolve_turn(
            opening, _decisions(opening, _make(opening, character_id=holder))
        ).state
        (pending,) = build_decision_options(state).active_promises
        assert pending.status == "pending"
        assert pending.releasable is True
        assert pending.release_blocked_reason is None

        key = next(iter(state.world.promises))
        released = resolve_turn(
            state,
            _decisions(
                state, PromiseDecision(action="release", character_id=holder, promise_id=key)
            ),
        ).state
        (cancelled,) = build_decision_options(released).active_promises
        assert cancelled.status == "cancelled"
        assert cancelled.releasable is False
        assert cancelled.release_blocked_reason == "promise_already_released"
        assert cancelled.released_turn == state.turn

    def test_a_settled_promise_leaves_the_view_but_stays_in_state(self) -> None:
        """The view answers "what can I still act on", so history belongs to the turn report."""
        from app.api.projections import build_decision_options

        opening = _scenario()
        holder = _chief_of_staff(opening)
        state = resolve_turn(
            opening, _decisions(opening, _make(opening, character_id=holder))
        ).state
        key = next(iter(state.world.promises))
        while state.world.promises[key].status is PromiseStatus.PENDING:
            state = resolve_turn(state, _decisions(state)).state
        assert state.world.promises[key].status is PromiseStatus.FULFILLED
        assert build_decision_options(state).active_promises == ()
        assert key in state.world.promises, "settled rows are never deleted"

    def test_the_narrowed_literal_is_unreachable_for_the_two_internal_reasons(self) -> None:
        """`ActivePromiseView`'s reason has two members while the helper has four. Asserted, not
        assumed: if a live row could ever yield `promise_missing` or `promise_already_settled`, the
        `Literal` would have to widen."""
        from app.api.projections import build_decision_options
        from app.simulation.promises import release_block_reason

        for scenario in ("tiny_valid.yaml", "decree_state.yaml", "deficit_demo.yaml"):
            state = _scenario(scenario)
            # Built from whatever THIS scenario actually offers rather than a hard-coded post:
            # `decree_state` holds its chief-of-staff chair vacant, so a fixed holder would make the
            # case unreachable there and quietly narrow a three-scenario sweep to two.
            option = build_decision_options(state).promise_options[0]
            state = resolve_turn(
                state,
                _decisions(
                    state,
                    PromiseDecision(
                        action="make",
                        character_id=option.character_id,
                        term_kind=option.term_kind,  # type: ignore[arg-type]
                        subject_id=option.subject_id,
                        deadline_turn=option.earliest_legal_deadline,
                    ),
                ),
            ).state
            assert state.world.promises, scenario
            for view in build_decision_options(state).active_promises:
                promise = state.world.promises[view.promise_id]
                assert release_block_reason(
                    status=promise.status,
                    deadline_turn=promise.deadline_turn,
                    resolving_turn=state.turn,
                ) in (None, "promise_already_released", "promise_past_releasing")

    def test_preview_prices_an_eligible_release_at_250_exactly_once(self) -> None:
        from app.api.preview import preview_decisions

        opening = _scenario()
        holder = _chief_of_staff(opening)
        state = resolve_turn(
            opening, _decisions(opening, _make(opening, character_id=holder))
        ).state
        key = next(iter(state.world.promises))
        decisions = _decisions(
            state, PromiseDecision(action="release", character_id=holder, promise_id=key)
        )
        projection = preview_decisions(state, decisions)
        assert projection.promise_release_capital == 250
        # Exactly once: the identity against the other five terms, so the term can be neither
        # dropped nor double-counted.
        assert projection.committed_capital == (
            projection.route_capital_cost
            + projection.influence_capital
            + projection.investment_capital
            + projection.cabinet_capital
            + projection.legislative_bargain_capital
            + projection.promise_release_capital
        )

    def test_public_preview_rejects_a_blocked_release_rather_than_pricing_it_at_zero(self) -> None:
        """`preview_decisions` runs the shared preflight BEFORE scoring, so a blocked release never
        reaches pricing: the whole set is rejected, exactly as `/resolve` rejects it."""
        from app.api.decision_preflight import first_decision_problem
        from app.api.preview import preview_decisions
        from app.core.errors import DecisionSetError

        opening = _scenario()
        holder = _chief_of_staff(opening)
        state = resolve_turn(
            opening, _decisions(opening, _make(opening, character_id=holder))
        ).state
        key = next(iter(state.world.promises))
        released = resolve_turn(
            state,
            _decisions(
                state, PromiseDecision(action="release", character_id=holder, promise_id=key)
            ),
        ).state
        decisions = _decisions(
            released, PromiseDecision(action="release", character_id=holder, promise_id=key)
        )
        problem = first_decision_problem(released, decisions)
        assert problem is not None
        assert problem.code == "promise_release_names_no_live_promise"
        with pytest.raises(DecisionSetError):
            preview_decisions(released, decisions)

    def test_the_private_pricing_helper_is_total_but_unreachable_for_blocked_input(self) -> None:
        """The zero branch is a guarantee about the HELPER, not behaviour a player can observe --
        it keeps a future caller that priced before validating from charging for a refused release.
        """
        from app.api.preview import _promise_release_cost

        opening = _scenario()
        holder = _chief_of_staff(opening)
        state = resolve_turn(
            opening, _decisions(opening, _make(opening, character_id=holder))
        ).state
        key = next(iter(state.world.promises))
        released = resolve_turn(
            state,
            _decisions(
                state, PromiseDecision(action="release", character_id=holder, promise_id=key)
            ),
        ).state
        blocked = _decisions(
            released, PromiseDecision(action="release", character_id=holder, promise_id=key)
        )
        assert _promise_release_cost(released, blocked) == 0


class TestTheSevenCaseR16QualificationSuite:
    """R16 in full: qualification is read from the RESOLVED scratch selected by proposal KIND.

    Seven cases, not six. The clean matrix is two promise kinds x three proposal situations, which
    is six on its own; the decree-route case is a seventh on top of it, and an earlier count that
    said "six" was conflating the two.

    | # | promise subject | what the turn did          | qualifies |
    |---|-----------------|----------------------------|-----------|
    | 1 | budget          | legislative-route budget   | YES       |
    | 2 | budget          | legislative-route amendment| no        |
    | 3 | budget          | no proposal                | no        |
    | 4 | amendment       | legislative-route amendment| YES       |
    | 5 | amendment       | legislative-route budget   | no        |
    | 6 | amendment       | no proposal                | no        |
    | 7 | budget          | DECREE-route budget        | no        |

    **Cases 4 and 5 are the ones the pre-R16 plan would have got wrong.** It named only
    `legislative_scratch`, which covers the budget alone, so an amendment promise could never have
    been qualified by anything -- permanently unfulfillable, and the defect this suite is the
    regression test for.

    **Case 7 is a separate claim**: governing by decree is the act of NOT asking the chamber, so it
    keeps no promise about putting something to one. Passage is still irrelevant throughout -- the
    player controls submission and route, never how the chamber votes.
    """

    @staticmethod
    def _amendment() -> Any:
        """A minimal real amendment for `tiny_valid`: its authored interval is 16, so 12 is a
        genuine change rather than a no-op the engine would refuse."""
        from app.simulation.decisions import ConstitutionalAmendmentDecision, ElectionIntervalTarget

        return ConstitutionalAmendmentDecision(targets=(ElectionIntervalTarget(value=12),))

    @staticmethod
    def _budget(**kwargs: Any) -> Any:
        from app.simulation.decisions import BudgetDecision

        return BudgetDecision(personal_income_rate_bps=2500, **kwargs)

    @staticmethod
    def _party_leader(state: GameState) -> str:
        return next(
            character_id
            for character_id, character in sorted(state.world.characters.items())
            if character.party_id is not None
        )

    def _qualifying_turn(
        self, scenario: str, *, subject_id: str, proposal: Any | None
    ) -> int | None:
        """Resolve one turn and report what the promise recorded, through the real resolver."""
        state = _scenario(scenario)
        leader = self._party_leader(state)
        promise = PromiseDecision(
            action="make",
            character_id=leader,
            term_kind="legislative_support",
            subject_id=subject_id,
            deadline_turn=state.turn + 4,
        )
        # Canonical kind order is REJECTED, never sorted, and both proposal kinds sort before
        # "promise", so the proposal leads.
        submitted = (promise,) if proposal is None else (proposal, promise)
        resolution = resolve_turn(state, _decisions(state, *submitted))
        key = next(iter(resolution.state.world.promises))
        # Whatever it recorded, group 60 agrees it was entitled to record it.
        assert (
            _group_60(state, resolution.state, resolution.report, _decisions(state, *submitted))
            == []
        )
        return resolution.state.world.promises[key].qualifying_turn

    def test_1_a_budget_promise_is_qualified_by_a_legislative_budget(self) -> None:
        assert (
            self._qualifying_turn("tiny_valid.yaml", subject_id="budget", proposal=self._budget())
            == 0
        )

    def test_2_a_budget_promise_is_not_qualified_by_an_amendment(self) -> None:
        assert (
            self._qualifying_turn(
                "tiny_valid.yaml", subject_id="budget", proposal=self._amendment()
            )
            is None
        )

    def test_3_a_budget_promise_is_not_qualified_by_no_proposal(self) -> None:
        assert self._qualifying_turn("tiny_valid.yaml", subject_id="budget", proposal=None) is None

    def test_4_an_amendment_promise_is_qualified_by_a_legislative_amendment(self) -> None:
        """The case the pre-R16 plan made impossible."""
        assert (
            self._qualifying_turn(
                "tiny_valid.yaml",
                subject_id="constitutional_amendment",
                proposal=self._amendment(),
            )
            == 0
        )

    def test_5_an_amendment_promise_is_not_qualified_by_a_budget(self) -> None:
        """The other half: reading only the budget's route would have qualified this wrongly."""
        assert (
            self._qualifying_turn(
                "tiny_valid.yaml",
                subject_id="constitutional_amendment",
                proposal=self._budget(),
            )
            is None
        )

    def test_6_an_amendment_promise_is_not_qualified_by_no_proposal(self) -> None:
        assert (
            self._qualifying_turn(
                "tiny_valid.yaml", subject_id="constitutional_amendment", proposal=None
            )
            is None
        )

    def test_7_a_decree_route_budget_qualifies_nothing(self) -> None:
        """`decree_state` is the one scenario that permits decrees, so the case is reachable from
        shipped content rather than constructed."""
        from app.simulation.legislature import ProposalRoute

        assert (
            self._qualifying_turn(
                "decree_state.yaml",
                subject_id="budget",
                proposal=self._budget(route=ProposalRoute.DECREE),
            )
            is None
        )

    def test_a_non_matching_turn_leaves_the_promise_pending_rather_than_breaching_it(self) -> None:
        """An achievement term is never broken early: turns remain in which the promised proposal
        can still be submitted, so an off-target turn is evidence of nothing."""
        state = _scenario()
        leader = self._party_leader(state)
        decisions = _decisions(
            state,
            self._amendment(),
            PromiseDecision(
                action="make",
                character_id=leader,
                term_kind="legislative_support",
                subject_id="budget",
                deadline_turn=state.turn + 4,
            ),
        )
        resolution = resolve_turn(state, decisions)
        key = next(iter(resolution.state.world.promises))
        promise = resolution.state.world.promises[key]
        assert promise.status is PromiseStatus.PENDING
        assert promise.qualifying_turn is None
        assert promise.violated_turn is None, "achievement terms carry no early violation"


class TestTheTransitionMatrixIsExhaustive:
    """T1-T6 pair by pair, INCLUDING every pair the lifecycle refuses.

    The six legal transitions are already exercised end to end elsewhere. What this adds is the
    complement: for every ordered pair of statuses OUTSIDE the legal set, group 60 rejects it. That
    is the half a positive suite cannot cover -- a build that quietly permitted `PENDING -> EXPIRED`
    would pass every test that only checks the transitions it does make.

    Driven from the enum rather than a written list, so a sixth status cannot slip past: the
    complement is computed, and 25 ordered pairs minus the 6 legal ones is 19 refusals.
    """

    def test_the_legal_set_is_exactly_the_six_of_the_lifecycle(self) -> None:
        from app.simulation.reconciliation import _LEGAL_PROMISE_TRANSITIONS

        assert {
            (PromiseStatus.PENDING, PromiseStatus.PENDING),
            (PromiseStatus.CANCELLED, PromiseStatus.CANCELLED),
            (PromiseStatus.PENDING, PromiseStatus.BREACHED),
            (PromiseStatus.PENDING, PromiseStatus.FULFILLED),
            (PromiseStatus.PENDING, PromiseStatus.CANCELLED),
            (PromiseStatus.CANCELLED, PromiseStatus.EXPIRED),
        } == _LEGAL_PROMISE_TRANSITIONS

    def test_the_two_absences_that_carry_the_design(self) -> None:
        """Stated as their own test because these are the two a future edit would most plausibly
        "fix": a pending achievement promise that reaches its deadline without evidence is a BREACH,
        never a free lapse, and nothing ever leaves a terminal status."""
        from app.simulation.reconciliation import _LEGAL_PROMISE_TRANSITIONS

        assert (PromiseStatus.PENDING, PromiseStatus.EXPIRED) not in _LEGAL_PROMISE_TRANSITIONS
        for terminal in TERMINAL_PROMISE_STATUSES:
            for target in PromiseStatus:
                if target is terminal:
                    continue
                assert (terminal, target) not in _LEGAL_PROMISE_TRANSITIONS, (terminal, target)

    def test_every_illegal_pair_is_refused_by_group_60(self) -> None:
        """The complement, exhaustively. 25 ordered pairs, 6 legal, so 19 must fail."""
        from app.simulation.reconciliation import _LEGAL_PROMISE_TRANSITIONS

        opening = _scenario()
        holder = _chief_of_staff(opening)
        decisions = _decisions(opening, _make(opening, character_id=holder))
        resolution = resolve_turn(opening, decisions)
        key = next(iter(resolution.state.world.promises))
        assert _group_60(opening, resolution.state, resolution.report, decisions) == []

        refused = 0
        for opening_status in PromiseStatus:
            for closing_status in PromiseStatus:
                if (opening_status, closing_status) in _LEGAL_PROMISE_TRANSITIONS:
                    continue
                refused += 1
                promise = resolution.state.world.promises[key]
                forged_opening = opening.model_copy(
                    update={
                        "world": opening.world.model_copy(
                            update={
                                "promises": {
                                    key: promise.model_construct(
                                        **{**dict(promise), "status": opening_status}
                                    )
                                }
                            }
                        )
                    }
                )
                forged = {
                    key: promise.model_construct(**{**dict(promise), "status": closing_status})
                }
                state, tampered = _restate(
                    opening=forged_opening,
                    closing=resolution.state,
                    report=resolution.report,
                    promises=forged,
                )
                problems = _group_60(forged_opening, state, tampered, None)
                # Asserted on the TRANSITION message specifically, so a case cannot pass
                # because the forgery happened to trip some unrelated check.
                assert any(
                    "not one of the six legal transitions" in problem
                    or "left the terminal status" in problem
                    for problem in problems
                ), (opening_status, closing_status, problems)
        assert refused == len(PromiseStatus) ** 2 - len(_LEGAL_PROMISE_TRANSITIONS) == 19


class TestBreachesCannotBeReversed:
    """The two anti-reversal properties, as CAMPAIGNS rather than assertions about a single turn.

    Both fall out of settling on OBSERVATION rather than at the deadline -- a maintenance promise is
    terminal the instant it is violated -- but "falls out of" is exactly the kind of claim that stops
    being true after a refactor, so each is played out over several turns.
    """

    def test_dismiss_then_reappoint_cannot_make_a_breach_look_kept(self) -> None:
        opening = _scenario()
        holder = _chief_of_staff(opening)
        state = resolve_turn(
            opening,
            _decisions(
                opening,
                CabinetDecision(orders=(CabinetOrder(post=_COS, character_id=None),)),
                _make(opening, character_id=holder),
            ),
        ).state
        key = next(iter(state.world.promises))
        assert state.world.promises[key].status is PromiseStatus.BREACHED
        violated_at = state.world.promises[key].violated_turn

        # Put them straight back, and run past the original deadline.
        state = resolve_turn(
            state,
            _decisions(
                state,
                CabinetDecision(orders=(CabinetOrder(post=_COS, character_id=holder),)),
            ),
        ).state
        deadline = state.world.promises[key].deadline_turn
        while state.turn <= deadline + 1:
            previous = state
            quiet = _decisions(state)
            resolution = resolve_turn(state, quiet)
            state = resolution.state
            assert _group_60(previous, state, resolution.report, quiet) == []

        promise = state.world.promises[key]
        assert promise.status is PromiseStatus.BREACHED, "terminal is terminal"
        assert promise.violated_turn == violated_at, "the date never moves"
        assert promise.settled_turn == violated_at

    def test_drawing_aid_then_waiting_cannot_restore_an_assistance_promise(self) -> None:
        """`assistance_drawn` is monotonically non-decreasing -- a pool only ever depletes -- so
        once it exceeds the promise-time baseline no amount of subsequent quiet brings it back.

        Measured against the stored baseline rather than the previous turn, which is precisely what
        makes draw-then-wait unable to recover.
        """
        from app.simulation.decisions import ForeignAssistanceDecision

        opening = _scenario()
        leader = next(
            character_id
            for character_id, character in sorted(opening.world.characters.items())
            if getattr(character.affiliation, "foreign_profile_id", None) == "kessia"
        )
        promise = PromiseDecision(
            action="make",
            character_id=leader,
            term_kind="assistance_restraint",
            subject_id="kessia",
            deadline_turn=opening.turn + 4,
        )
        # Promise restraint and draw from the very same counterpart in one set.
        state = resolve_turn(
            opening,
            _decisions(opening, ForeignAssistanceDecision(profile_id="kessia"), promise),
        ).state
        key = next(iter(state.world.promises))
        assert state.world.promises[key].status is PromiseStatus.BREACHED
        drawn = state.world.foreign_relationships["kessia"].assistance_drawn
        assert drawn > 0, "the draw really happened"

        deadline = state.world.promises[key].deadline_turn
        while state.turn <= deadline + 1:
            previous = state
            quiet = _decisions(state)
            resolution = resolve_turn(state, quiet)
            state = resolution.state
            assert _group_60(previous, state, resolution.report, quiet) == []
            assert state.world.foreign_relationships["kessia"].assistance_drawn >= drawn, (
                "a drawn pool never un-draws"
            )

        assert state.world.promises[key].status is PromiseStatus.BREACHED


class TestThePromiseIdIsOpaqueAndInjective:
    """The id is a KEY and nothing else. Nothing anywhere parses it.

    That rule is what dissolves the injectivity hazard rather than arguing around it:
    `StrictCharacterId` has no pattern, so a character id may legally contain `__`, end in a term
    name, or consist only of separators. Rather than reason about whether a composed id is
    decodable, the id is a fixed-length digest and no code decodes it -- every consumer reads the
    stored typed fields instead.
    """

    HOSTILE_IDS = (
        "a",
        "a__b",
        "a__cabinet_tenure",
        "a__cabinet_tenure__t1",
        "__",
        "t1",
        "__t1",
        "x" * 64,
        "y" * 62 + "__",
    )
    """Ids chosen to break a COMPOSED scheme: each one either contains the separator a composed id
    would use, imitates a term name, or imitates a turn suffix. Under the digest they are ordinary
    strings, which is the property being demonstrated."""

    def test_every_id_is_exactly_the_fixed_length(self) -> None:
        """EQUALITY, not `<=`. The previous design declared `MAX_PROMISE_ID_LENGTH = 128`, which was
        a guess dressed as a derivation: `made_turn` has no upper bound, so a composed id's length
        was unbounded. A digest is exactly 67 characters for any input at all."""
        from app.simulation.promises import PROMISE_ID_LENGTH, promise_id

        for character_id in self.HOSTILE_IDS:
            for term_kind in sorted(MAINTENANCE_TERMS | ACHIEVEMENT_TERMS):
                for made_turn in (0, 1, 7, 10**18):
                    derived = promise_id(
                        character_id=character_id, term_kind=term_kind, made_turn=made_turn
                    )
                    assert len(derived) == PROMISE_ID_LENGTH == 67
                    assert derived.startswith("pr_")

    def test_hostile_inputs_are_all_distinct(self) -> None:
        """Distinctness only -- deliberately NOT decodability. A test that round-tripped an id back
        to its triple would bless exactly the parsing this design forbids."""
        from app.simulation.promises import promise_id

        derived = {
            promise_id(character_id=character_id, term_kind=term_kind, made_turn=made_turn)
            for character_id in self.HOSTILE_IDS
            for term_kind in sorted(MAINTENANCE_TERMS | ACHIEVEMENT_TERMS)
            for made_turn in (0, 1, 7, 10**18)
        }
        expected = len(self.HOSTILE_IDS) * len(MAINTENANCE_TERMS | ACHIEVEMENT_TERMS) * 4
        assert len(derived) == expected, "a collision among hostile inputs"

    def test_one_literal_digest_is_pinned(self) -> None:
        """So a change to the tuple's SHAPE, or to `canonical_bytes`, fails loudly here rather than
        producing silently different ids across a save boundary."""
        from app.simulation.promises import promise_id

        assert (
            promise_id(character_id="hal_verrin", term_kind="cabinet_tenure", made_turn=0)
            == "pr_8c03d89d4c41c3ab6a735bdaa9235289fee3a1cc858d1862532aa7108d99e788"
        )

    def test_the_id_is_order_free_and_deterministic(self) -> None:
        """`canonical_bytes` sorts keys, so the literal spelled in `promise_id` and any reordering
        of it produce the same digest -- no dict-iteration or insertion-order dependence."""
        from app.core.canonical_json import canonical_digest
        from app.simulation.promises import PROMISE_ID_PREFIX, promise_id

        forward = canonical_digest(
            {"character_id": "a", "made_turn": 3, "term_kind": "cabinet_tenure"}
        )
        reordered = canonical_digest(
            {"term_kind": "cabinet_tenure", "character_id": "a", "made_turn": 3}
        )
        assert forward == reordered
        assert (
            promise_id(character_id="a", term_kind="cabinet_tenure", made_turn=3)
            == PROMISE_ID_PREFIX + forward
        )

    def test_the_promises_mapping_serialises_order_free(self) -> None:
        """Two insertion orders dump byte-identically, the proof
        `test_foreign_profiles_insertion_order_is_not_semantic` established for foreign profiles.
        `canonical_dumps` sorts keys, so a dict is order-free by construction; this pins it."""
        from app.core.canonical_json import canonical_dumps

        opening = _scenario()
        holder = _chief_of_staff(opening)
        state = resolve_turn(
            opening, _decisions(opening, _make(opening, character_id=holder))
        ).state
        promises = dict(state.world.promises)
        extra_key = "pr_" + "e" * 64
        promises[extra_key] = next(iter(promises.values()))

        forward = dict(sorted(promises.items()))
        backward = dict(sorted(promises.items(), reverse=True))
        assert list(forward) != list(backward), "the two orders really differ"
        assert canonical_dumps(
            state.world.model_copy(update={"promises": forward}).model_dump(mode="json")
        ) == canonical_dumps(
            state.world.model_copy(update={"promises": backward}).model_dump(mode="json")
        )

    def test_nothing_in_the_app_parses_a_promise_id(self) -> None:
        """The structural no-parse scan, in the shape of the `war_capability_bps` fence.

        A new decoder is refused BY DEFAULT rather than reviewed for correctness later -- which is
        the only way a rule like "nothing parses this" survives contact with future edits.
        """
        forbidden_methods = {
            "split",
            "rsplit",
            "partition",
            "rpartition",
            "removeprefix",
            "removesuffix",
            "startswith",
            "endswith",
        }
        offenders: list[str] = []
        for module in sorted(_APP.rglob("*.py")):
            tree = ast.parse(module.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                    continue
                if node.func.attr not in forbidden_methods:
                    continue
                target = node.func.value
                name = (
                    target.id
                    if isinstance(target, ast.Name)
                    else target.attr
                    if isinstance(target, ast.Attribute)
                    else ""
                )
                if "promise_id" in name:
                    offenders.append(f"{module.name}: {name}.{node.func.attr}")
        assert offenders == [], offenders

    def test_the_no_parse_scan_detects_a_decoder(self) -> None:
        """Anti-vacuity: a scan matching nothing would pass a repository full of decoders."""
        sample = ast.parse("parts = promise_id.split('__')\n")
        found = [
            node.func.attr
            for node in ast.walk(sample)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and "promise_id" in node.func.value.id
        ]
        assert found == ["split"]


class TestReleaseAndReissueCanNeverPayEarlier:
    """The anti-farming guarantee, as a TIMING proof and never an economic one.

    The withdrawn claim was that a release is "never cheaper than keeping". That comparison cannot
    be made honestly: cabinet flexibility, a proposal slot and forgone aid are three different
    resources with no common price, so any capital figure expressing "cheaper" would be a made-up
    exchange rate dressed as a proof. **It must not be restated.**

    What IS provable is that farming -- getting the reward sooner and more often -- is impossible:

    1. a promise made at `m` with deadline `d` pays only at `d`;
    2. releasing at `r` (`m <= r < d`) makes it `CANCELLED`, which is NOT terminal, so the
       `(character, term)` pair stays barred;
    3. the bar lifts only when the expiry fires, at the ORIGINAL `d`;
    4. any replacement obeys `deadline >= made + MINIMUM_PROMISE_TURNS`;
    5. so the earliest reissued reward is `d + 4 > d`. Strictly later, always, and it cost capital.
    """

    def test_no_schedule_pays_trust_before_the_original_deadline(self) -> None:
        """Swept over every release turn in the window, through the real resolver."""
        opening = _scenario()
        holder = _chief_of_staff(opening)
        base = resolve_turn(opening, _decisions(opening, _make(opening, character_id=holder))).state
        key = next(iter(base.world.promises))
        deadline = base.world.promises[key].deadline_turn
        opening_trust = opening.world.characters[holder].personal_trust

        for release_turn in range(base.turn, deadline):
            state = base
            while state.turn < release_turn:
                state = resolve_turn(state, _decisions(state)).state
            state = resolve_turn(
                state,
                _decisions(
                    state,
                    PromiseDecision(action="release", character_id=holder, promise_id=key),
                ),
            ).state
            # Run past the original deadline, checking every turn.
            while state.turn <= deadline + 1:
                assert state.world.characters[holder].personal_trust == opening_trust, (
                    f"released at {release_turn}: trust moved before the original deadline"
                )
                state = resolve_turn(state, _decisions(state)).state
            assert state.world.promises[key].status is PromiseStatus.EXPIRED

    def test_the_earliest_reissued_reward_is_strictly_later_than_keeping(self) -> None:
        """Step 5 of the proof, measured rather than argued."""
        opening = _scenario()
        holder = _chief_of_staff(opening)
        state = resolve_turn(
            opening, _decisions(opening, _make(opening, character_id=holder))
        ).state
        key = next(iter(state.world.promises))
        deadline = state.world.promises[key].deadline_turn

        state = resolve_turn(
            state,
            _decisions(
                state, PromiseDecision(action="release", character_id=holder, promise_id=key)
            ),
        ).state
        while state.turn < deadline:
            state = resolve_turn(state, _decisions(state)).state

        # The bar lifts at exactly `d`, and the replacement's own horizon starts there.
        reissue = _make(state, character_id=holder)
        assert reissue.deadline_turn is not None
        assert reissue.deadline_turn >= deadline + 4 > deadline
        state = resolve_turn(state, _decisions(state, reissue)).state
        replacement = next(
            promise for promise_key, promise in state.world.promises.items() if promise_key != key
        )
        assert replacement.deadline_turn > deadline, "strictly later, always"

    def test_no_pair_ever_holds_two_non_terminal_rows(self) -> None:
        """The cardinality half. Swept across a campaign that makes, releases, expires and reissues,
        so it is a property of the run rather than of one turn."""
        opening = _scenario()
        holder = _chief_of_staff(opening)
        state = resolve_turn(
            opening, _decisions(opening, _make(opening, character_id=holder))
        ).state
        key = next(iter(state.world.promises))
        deadline = state.world.promises[key].deadline_turn
        state = resolve_turn(
            state,
            _decisions(
                state, PromiseDecision(action="release", character_id=holder, promise_id=key)
            ),
        ).state

        def live_pairs(current: GameState) -> list[tuple[str, str]]:
            return [
                (promise.character_id, promise.term_kind)
                for promise in current.world.promises.values()
                if promise.status in LIVE_PROMISE_STATUSES
            ]

        for _ in range(8):
            pairs = live_pairs(state)
            assert len(pairs) == len(set(pairs)), pairs
            decisions = (
                _decisions(state, _make(state, character_id=holder))
                if state.turn == deadline
                else _decisions(state)
            )
            state = resolve_turn(state, decisions).state
        assert len(live_pairs(state)) == len(set(live_pairs(state)))


_PROMISE_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "promise_save_ruleset_0.21.0.json"


class TestCompatibility:
    """Two proofs, each falsifiable on its own.

    The version gate and the payload shape are SEPARATE claims, and a single test cannot establish
    both: a save rejected on its version never reaches the parser, so a passing version test says
    nothing about whether the payload would have failed. A shows the field is genuinely breaking;
    B shows the player never sees a parse failure for it. Either alone would be reassuring rather
    than probative.
    """

    def test_the_fixture_really_predates_this_ruleset(self) -> None:
        raw = json.loads(_PROMISE_FIXTURE.read_text(encoding="utf-8"))
        assert raw["ruleset_version"] == "0.21.0"
        assert raw["content_version"] == "0.18.0"
        assert RULESET_VERSION == "0.22.0"

    def _one_stored_governance_report(self) -> dict[str, object]:
        raw = json.loads(_PROMISE_FIXTURE.read_text(encoding="utf-8"))
        for entry in raw["entries"]:
            payload = entry.get("report_json")
            if not payload:
                continue
            document = json.loads(payload) if isinstance(payload, str) else payload
            if document.get("governance"):
                return dict(document["governance"])
        raise AssertionError("the fixture is expected to carry a real GovernanceReport")

    def test_proof_a_the_payload_fails_specifically_on_the_missing_field(self) -> None:
        """Bypasses the version gate entirely and parses one stored subtree under the NEW model.

        Asserts the SPECIFIC error -- type `missing` at exactly `promises` -- rather than "some
        ValidationError", because a test that accepted any failure would keep passing if the payload
        later broke for an unrelated reason, which is exactly the false green this proof exists to
        prevent.
        """
        from app.simulation.report import GovernanceReport

        stored = self._one_stored_governance_report()
        assert "promises" not in stored
        assert set(stored) == {"posts"}, "the 0.21.0 shape is `posts` alone"
        with pytest.raises(ValidationError) as exc_info:
            GovernanceReport.model_validate(stored)
        errors = exc_info.value.errors()
        assert [error["type"] for error in errors] == ["missing"]
        assert [error["loc"] for error in errors] == [("promises",)]

    def test_proof_a_anti_vacuity_the_single_field_is_the_whole_incompatibility(self) -> None:
        """A LOCAL COPY with `promises: []` injected parses cleanly, proving the one missing field
        is the whole of the break.

        The production model must NEVER gain a default -- that is the entire reason 0.21.0 is
        incompatible, and a default would silently assert that a turn resolved before this mechanic
        existed had "no promises", a claim about undertakings nobody could have given. The injection
        happens in the test's own copy only.
        """
        from app.simulation.report import GovernanceReport

        stored = self._one_stored_governance_report()
        report = GovernanceReport.model_validate(stored | {"promises": []})
        assert report.promises == ()
        assert GovernanceReport.model_fields["promises"].is_required()

    def test_proof_b_the_version_rejection_happens_before_any_parsing(self) -> None:
        """Every payload replaced with text that is not even valid JSON, envelope left at 0.21.0.

        A clean version rejection is only possible if the version check runs FIRST -- and because
        the payloads are unparseable, this cannot pass by accident on a build where the order is
        reversed.
        """
        from app.core.errors import UnsupportedRulesetVersionError
        from app.simulation.save_format import load_save_json

        raw = json.loads(_PROMISE_FIXTURE.read_text(encoding="utf-8"))
        for entry in raw["entries"]:
            if "state_json" in entry:
                entry["state_json"] = "{definitely not json"
            if entry.get("report_json") is not None:
                entry["report_json"] = "{definitely not json"
        with pytest.raises(UnsupportedRulesetVersionError) as exc_info:
            load_save_json(json.dumps(raw), source="corrupted-but-still-incompatible")
        message = str(exc_info.value)
        assert "0.21.0" in message and RULESET_VERSION in message

    def test_the_fixture_still_carries_both_pre_promise_shapes(self) -> None:
        """If either shape had been regenerated under the current engine, both proofs would be
        hollow -- A would have nothing to fail on and B would be rejecting a save that was already
        parseable."""
        raw = json.loads(_PROMISE_FIXTURE.read_text(encoding="utf-8"))
        world = json.loads(raw["entries"][-1]["state_json"])["world"]
        assert "promises" not in world
        for entry in raw["entries"]:
            payload = entry.get("report_json")
            if not payload:
                continue
            document = json.loads(payload) if isinstance(payload, str) else payload
            governance = document.get("governance")
            if governance is not None:
                assert set(governance) == {"posts"}


class TestTheTimingSweepOverRelativeOrderings:
    """The authorized sweep: schedules over the relative ordering of make, release, violation, the
    original deadline and reissue -- not one axis.

    An earlier version swept the RELEASE turn alone and so never exercised a violation at all. Three
    rules had no test between them: a release winning over a same-turn violation (§4.5 step 3), a
    violation after a release being ignored, and a reissued promise ever settling.
    """

    DEADLINE = 4
    VIOLATION_TURNS: tuple[int | None, ...] = (None, 1, 2, 3, 4)
    RELEASE_TURNS: tuple[int | None, ...] = (None, 1, 2, 3)
    """Neither domain includes 0, and that is structural rather than a trimmed corner.

    A `DecisionSet` carries at most one `PromiseDecision`, so turn 0 is the make and cannot also be
    the release -- `r = 0` is unconstructible. `v = 0` IS constructible (a cabinet order and a
    promise are different kinds and may share a set) and is covered by the make-and-breach test, so
    it lives there rather than being duplicated. `r` stops at 3 because a release is legal only
    while `deadline > turn`.
    """

    @staticmethod
    def _classify(v: int | None, r: int | None) -> str:
        """Exactly one class per `(v, r)`, asserted below before any schedule runs.

        `r is not None and v == r` rather than a bare `v == r`: `None == None` is true, so an
        unguarded comparison would also swallow the no-violation-no-release schedule and two classes
        would overlap. Likewise `v is None or v > r` rather than `v > r`, which would raise on
        `None`.
        """
        if v is not None and (r is None or v < r):
            return "breached"
        if r is not None and v == r:
            return "release_wins"
        if r is not None and (v is None or v > r):
            return "cancelled_then_expired"
        return "fulfilled"

    def test_the_four_classes_are_exhaustive_and_mutually_exclusive(self) -> None:
        """A schedule that fell through, or matched two, would make the sweep below silently
        incomplete -- so the classification is proved before it is used."""
        seen: dict[str, int] = {}
        for v in self.VIOLATION_TURNS:
            for r in self.RELEASE_TURNS:
                predicates = [
                    v is not None and (r is None or v < r),
                    r is not None and v == r,
                    r is not None and (v is None or v > r),
                    v is None and r is None,
                ]
                assert sum(predicates) == 1, (v, r, predicates)
                seen[self._classify(v, r)] = seen.get(self._classify(v, r), 0) + 1
        assert set(seen) == {"breached", "release_wins", "cancelled_then_expired", "fulfilled"}
        assert seen["fulfilled"] == 1, "exactly one schedule leaves the promise untouched"

    def _advance(self, state: GameState) -> GameState:
        """One accepted empty turn, reconciled."""
        quiet = _decisions(state)
        resolution = resolve_turn(state, quiet)
        assert _group_60(state, resolution.state, resolution.report, quiet) == []
        return resolution.state

    def _assert_rejected_and_unchanged(self, state: GameState, decisions: DecisionSet) -> None:
        """A refused resolution must leave the state byte-identical.

        Asserted rather than assumed, because a schedule that "advanced" on a turn the engine never
        resolved would drift off the ordering it claims to be running -- and then report a pass for
        a sequence it never played.
        """
        from app.core.canonical_json import canonical_dumps
        from app.core.errors import TurnResolutionError

        before = canonical_dumps(state.model_dump(mode="json"))
        with pytest.raises(TurnResolutionError):
            resolve_turn(state, decisions)
        assert canonical_dumps(state.model_dump(mode="json")) == before

    @pytest.mark.parametrize("violation_turn", VIOLATION_TURNS)
    @pytest.mark.parametrize("release_turn", RELEASE_TURNS)
    def test_the_schedule_settles_exactly_as_its_class_requires(
        self, violation_turn: int | None, release_turn: int | None
    ) -> None:
        expected = self._classify(violation_turn, release_turn)

        opening = _scenario()
        holder = _chief_of_staff(opening)
        opening_trust = opening.world.characters[holder].personal_trust

        state = resolve_turn(
            opening, _decisions(opening, _make(opening, character_id=holder))
        ).state
        key = next(iter(state.world.promises))
        assert state.world.promises[key].deadline_turn == self.DEADLINE

        released_already = False
        while state.turn <= self.DEADLINE + 2:
            turn = state.turn
            submitted: list[Any] = []
            if violation_turn == turn:
                submitted.append(
                    CabinetDecision(orders=(CabinetOrder(post=_COS, character_id=None),))
                )
            if release_turn == turn:
                decision = PromiseDecision(action="release", character_id=holder, promise_id=key)
                if state.world.promises[key].status is PromiseStatus.PENDING:
                    submitted.append(decision)
                    released_already = True
                else:
                    # Already breached: the release is refused, and must move nothing.
                    self._assert_rejected_and_unchanged(
                        state, _decisions(state, *submitted, decision)
                    )

            decisions = _decisions(state, *submitted)
            resolution = resolve_turn(state, decisions)
            assert _group_60(state, resolution.state, resolution.report, decisions) == []
            state = resolution.state

            promise = state.world.promises[key]
            trust = state.world.characters[holder].personal_trust
            # THE anti-farming invariant: no POSITIVE trust before the original deadline. Negative
            # may land early -- that asymmetry is the design, so the invariant is about the reward.
            if turn < self.DEADLINE:
                assert trust <= opening_trust, f"turn {turn}: trust rose before the deadline"
            live = [
                (row.character_id, row.term_kind)
                for row in state.world.promises.values()
                if row.status in LIVE_PROMISE_STATUSES
            ]
            assert len(live) == len(set(live)), live
            if promise.status in TERMINAL_PROMISE_STATUSES and turn >= self.DEADLINE:
                break

        promise = state.world.promises[key]
        trust = state.world.characters[holder].personal_trust

        if expected == "breached":
            assert promise.status is PromiseStatus.BREACHED
            assert promise.violated_turn == violation_turn
            assert trust == max(0, opening_trust - 2_000)
        elif expected == "release_wins":
            # §4.5 step 3: the paid release beats the same-turn violation, so NO breach is recorded.
            # Without this the mechanic would be worthless -- the player would pay capital AND lose
            # trust, and nobody would ever release.
            assert promise.status is PromiseStatus.EXPIRED, "cancelled, then expired at d"
            assert promise.violated_turn is None, "a paid release records no breach"
            assert promise.released_turn == release_turn
            assert trust == opening_trust
        elif expected == "cancelled_then_expired":
            assert promise.status is PromiseStatus.EXPIRED
            assert promise.violated_turn is None
            assert promise.released_turn == release_turn
            assert promise.settled_turn == self.DEADLINE, "the ORIGINAL horizon, not the release"
            assert trust == opening_trust
        else:
            assert promise.status is PromiseStatus.FULFILLED
            assert promise.settled_turn == self.DEADLINE
            assert trust == opening_trust + 1_000

        # A release was actually submitted iff the row was still PENDING when its turn came --
        # exactly the non-breached schedules. `promise.released_turn` above pins WHEN; this pins
        # that the breached schedules never got to release at all.
        assert released_already is (release_turn is not None and expected != "breached")

    def test_the_reissue_arm_is_refused_before_d_and_settles_at_its_own_deadline(self) -> None:
        """Run separately from the sweep above, and for a CONTENT reason rather than convenience.

        `cabinet_tenure` is available only to a SITTING officeholder, so after a dismissal the
        character is not promisable at all -- a reissue there fails as code 2, not code 5, and a
        sweep that mixed the two would silently test the wrong rule. This arm therefore uses a
        released-but-unviolated promise.
        """
        opening = _scenario()
        holder = _chief_of_staff(opening)
        opening_trust = opening.world.characters[holder].personal_trust
        state = resolve_turn(
            opening, _decisions(opening, _make(opening, character_id=holder))
        ).state
        key = next(iter(state.world.promises))
        deadline = state.world.promises[key].deadline_turn
        state = resolve_turn(
            state,
            _decisions(
                state, PromiseDecision(action="release", character_id=holder, promise_id=key)
            ),
        ).state

        # Refused every turn before the original deadline -- and each refusal moves nothing.
        while state.turn < deadline:
            self._assert_rejected_and_unchanged(
                state, _decisions(state, _make(state, character_id=holder))
            )
            state = self._advance(state)

        # At `d` the bar lifts, in the same turn the old row expires.
        assert state.turn == deadline
        reissue = _make(state, character_id=holder)
        assert reissue.deadline_turn is not None
        replacement_deadline = reissue.deadline_turn
        assert replacement_deadline >= deadline + 4 > deadline
        decisions = _decisions(state, reissue)
        resolution = resolve_turn(state, decisions)
        assert _group_60(state, resolution.state, resolution.report, decisions) == []
        state = resolution.state
        assert state.world.promises[key].status is PromiseStatus.EXPIRED

        replacement_key = next(k for k in state.world.promises if k != key)
        # The replacement settles at ITS OWN deadline, which is the half nothing proved before.
        while state.world.promises[replacement_key].status is PromiseStatus.PENDING:
            assert state.world.characters[holder].personal_trust == opening_trust
            state = self._advance(state)
        replacement = state.world.promises[replacement_key]
        assert replacement.status is PromiseStatus.FULFILLED
        assert replacement.settled_turn == replacement_deadline
        assert state.world.characters[holder].personal_trust == opening_trust + 1_000

    def test_a_dismissed_character_is_not_promisable_at_all(self) -> None:
        """Stated on its own rather than left as an accident of the sweep: after a dismissal the
        term is refused at code 2 (not available to this character), never code 5 (already live).
        The distinction matters because a test that expected code 5 here would pass for the wrong
        reason."""
        from app.api.decision_preflight import first_decision_problem
        from app.core.errors import TurnResolutionError

        opening = _scenario()
        holder = _chief_of_staff(opening)
        state = resolve_turn(
            opening,
            _decisions(
                opening, CabinetDecision(orders=(CabinetOrder(post=_COS, character_id=None),))
            ),
        ).state
        assert not state.world.promises, "no promise was ever made here"

        decisions = _decisions(state, _make(state, character_id=holder))
        problem = first_decision_problem(state, decisions)
        assert problem is not None
        assert problem.code == "promise_term_not_available_for_this_character"
        with pytest.raises(TurnResolutionError) as exc_info:
            resolve_turn(state, decisions)
        message = str(exc_info.value)
        assert "promise_term_not_available_for_this_character" in message
        assert "promise_term_already_live_for_this_character" not in message
