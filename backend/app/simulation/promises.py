"""Undertakings the player gives a counterparty, and what keeping or breaking one is worth.

Pure formulas and pure identity over plain values: no I/O, no randomness, no state mutation, no
clock, no floating point -- the `government_survival.py` / `legislative_bargaining.py` /
`foreign_assistance.py` shape. Every function takes values it declares itself and never a state
model; the promises, the cabinet, the vote and the drawn pool are read out of state in `phases.py`'s
slot handlers.

**This is the trust layer the three negotiations were built to consume.** Commits 3-6 gave the
engine a bargain gate that refuses outright below 5,000 `personal_trust`, a bargain price that
discounts by `trust * 60 // 10_000`, and an assistance share that adds `trust * 1_200 // 10_000` --
and then left `personal_trust` a frozen authored constant that nothing could move. Promises are what
move it, and they move it on EVENTS ONLY: a kept promise and a broken one. There is no per-turn
drift, which is what keeps a character's trust a discrete, auditable record of what the player
actually did rather than a number that ages.

**Two term SHAPES, and the distinction is the whole design.**

* MAINTENANCE terms (`cabinet_tenure`, `assistance_restraint`) promise that a state will HOLD. They
  can be broken at any moment and can only be kept by running out the clock, so the first violating
  turn breaches them immediately and irreversibly.
* The ACHIEVEMENT term (`legislative_support`) promises that an act will HAPPEN by a deadline. It
  cannot be broken early -- a different proposal, or no proposal, still leaves turns in which the
  promised one can be submitted -- so an off-target turn is evidence of nothing and only the
  deadline can breach it.

Collapsing the two would make one of them wrong: a maintenance promise that waited for the deadline
could be violated and then quietly restored, and an achievement promise that breached early would
punish a player for not having acted yet.

**Trust timing is asymmetric on purpose.** Positive trust is deferred to the deadline always, so no
action however early can pay early -- that is what makes `MINIMUM_PROMISE_TURNS` control the REWARD
rather than merely constrain a field in a decision. Negative trust lands the moment a violation is
observed, so a player can never keep spending trust in bargains they have already forfeited, and a
deferred debit can never go unpaid because a campaign ended first. Rewards are earned by lasting;
penalties are incurred by acting.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, TypeAlias

from app.core.canonical_json import canonical_digest

PromiseTermKind: TypeAlias = Literal[
    "assistance_restraint", "cabinet_tenure", "legislative_support"
]
"""What was promised. Declared once here and shared by the decision, the state row and the report.

Typing any of those three as a bare `str` would let a report name a term the decision could never
carry; the alias makes them the same type by construction rather than by agreement -- the discipline
`LegislativeProposalKind` already established for the bargain.

Values are alphabetical, which is also their canonical order. `MAINTENANCE_TERMS` and
`ACHIEVEMENT_TERMS` below partition them, and a test asserts the partition is total, so a fourth
term cannot be added without deciding which shape it has.
"""

MAINTENANCE_TERMS: frozenset[PromiseTermKind] = frozenset(
    {"assistance_restraint", "cabinet_tenure"}
)
"""Terms promising that a state will HOLD: breached on the first violating turn, kept by lasting."""

ACHIEVEMENT_TERMS: frozenset[PromiseTermKind] = frozenset({"legislative_support"})
"""Terms promising that an act will HAPPEN: never breached early, settled only at the deadline."""


class PromiseStatus(StrEnum):
    """Where one promise stands.

    Values are alphabetical, so declaration order is canonical order -- and that matters here for
    the same reason it matters on `CapitalExpenditureCategory`: these values are serialised into
    `report_json` and covered by the entry hash, so renaming or reordering one after the fact is a
    save-format change rather than a refactor.

    **`CANCELLED` is NOT terminal.** It is the "released, but still inside the horizon you
    abandoned" state, and it decays to `EXPIRED` at the original deadline. That single choice is
    what makes `EXPIRED` reachable at all, and what makes the re-promise bar a property of this
    state machine instead of a rule bolted on beside it.
    """

    BREACHED = "breached"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    FULFILLED = "fulfilled"
    PENDING = "pending"


TERMINAL_PROMISE_STATUSES: frozenset[PromiseStatus] = frozenset(
    {PromiseStatus.BREACHED, PromiseStatus.EXPIRED, PromiseStatus.FULFILLED}
)
"""Reached at most once, never left. The settler skips these rows forever after, which is what makes
"exactly once" a property of the traversal rather than of a counter somebody has to maintain."""

LIVE_PROMISE_STATUSES: frozenset[PromiseStatus] = frozenset(
    {PromiseStatus.CANCELLED, PromiseStatus.PENDING}
)
"""The two states a promise can still move out of. A test asserts these two sets partition
`PromiseStatus` exactly, so a sixth status cannot be added without classifying it."""

PROMISE_KEPT_TRUST_GAIN_BPS = 1_000
"""What a kept promise adds to the counterparty's `personal_trust`.

MEASURED, not chosen. Swept against the three shipped scenarios: the opposition leaders who refuse
every bargain need +2,600 (Gustav Reiner), +2,900 (Nadia Brekke) and +2,400 (Petra Almas) of trust
to clear the 5,000 override. At 1,000 per kept promise, TWO kept promises flip nobody (4,400 / 4,100
/ 4,600 are all still below 5,000) and the THIRD flips all three (5,400 / 5,100 / 5,600). The
demonstration is therefore discriminating rather than approximate, identical in every scenario, and
spans a campaign instead of a turn.

Applied only at `deadline_turn` -- see the module docstring on asymmetric timing.
"""

PROMISE_BREACHED_TRUST_LOSS_BPS = 2_000
"""What a broken promise costs. Twice the gain, deliberately: a breach undoes two kept promises, so
trust is slow to build and quick to lose. Applied the moment a violation is observed."""

PROMISE_EXPIRED_TRUST_BPS = 0
"""An expired promise moves no trust. It was released and paid for in capital; the counterparty was
told, so there is nothing further to settle."""

PROMISE_RELEASED_TRUST_BPS = 0
"""Releasing moves no trust either -- the price is political capital (`PROMISE_RELEASE_COST_CAPITAL`)
and the horizon the release does not shorten."""

MINIMUM_PROMISE_TURNS = 4
"""The shortest legal window, `deadline_turn >= made_turn + MINIMUM_PROMISE_TURNS`.

A GAME-BALANCE CHOICE, not a measurement, in the same wording `CABINET_APPOINTMENT_BASE_COST` uses.

It is not merely a constraint on a field. Because no transition grants trust before `deadline_turn`,
this floor controls the REWARD: a promise satisfied on the turn after it was made still pays four
turns later, or not at all. Without the deferral the floor would constrain nothing -- a player could
promise a vote, hold it immediately, and collect. That is the appoint-then-fire hole the mandate
names, closed for all three terms by one constant rather than three special cases.
"""

PROMISE_RELEASE_COST_CAPITAL = 250
"""What it costs to be let out of a pending promise.

A GAME-BALANCE CHOICE, not a measurement. It deliberately equals
`legislative_voting.CONSTITUTIONAL_AMENDMENT_DECREE_COST`, the existing price for acting by fiat,
because going back on your word to a counterparty is that same kind of act. Against the landscape it
sits above the bargain (105-165) and the cheapest appointment (120), and below amendment-by-decree
(400) and `RELATIONSHIP_HALF_GAP_CAPITAL` (500).

**Reachability is the one property this number must actually satisfy.** Opening capital is 500 /
500 / 300 across the shipped scenarios. At 250 a release is payable in every one of them including
`deficit_demo`, where it consumes 250 of 300 and therefore costs roughly a whole turn's discretion
-- weighty, not impossible. The zero-capital actions the precedence rules need remain affordable
alongside it (a dismissal costs nothing, making a promise costs nothing), so release-plus-violation
and reissue-at-the-deadline are both reachable from shipped content. A price of 400 would have made
the release branch unaffordable in `deficit_demo` and left `CANCELLED` and `EXPIRED` untestable
there, which is why it was rejected.

It carries NO proof. An earlier design tried to prove a release price "never cheaper than keeping";
that claim was withdrawn, because cabinet flexibility, a proposal slot and forgone aid are three
different resources with no honest common price and any such number would be a made-up exchange rate
dressed as a proof. The anti-farming guarantee is the TIMING property instead: release-and-reissue
can never produce trust earlier than keeping the original. If play shows this number wrong it is a
one-line change with no invariant behind it.
"""

PROMISE_ID_PREFIX = "pr_"
"""Marks a promise id at a glance in a log, a report or a save, and keeps the namespace distinct
from the history-chain digests and the `{a}__{b}__t{n}` conflict ids that already exist."""

PROMISE_ID_LENGTH = 67
"""EXACT length of every promise id: `len("pr_")` + 64 hex characters of BLAKE2b-256.

Exact, not a maximum, and that is the point. An earlier design composed the id as
`f"{character_id}__{term_kind}__t{made_turn}"` and declared a maximum of 128, which was not formally
derivable: `made_turn` has no upper bound in the engine, so the composed id's length had none
either. A digest is the same length for every input, so the bound is a fact rather than a guess, and
it is asserted by EQUALITY.
"""


def promise_id(*, character_id: str, term_kind: PromiseTermKind, made_turn: int) -> str:
    """The stable, opaque identity of one promise.

    A pure function of three typed values: no UUID, no RNG, no clock, no insertion-order or
    dict-iteration dependence. `canonical_bytes` sorts keys, so the literal spelled below and any
    reordering of it produce the same digest, and a replayed campaign reproduces byte-identical ids.

    **THE ID IS OPAQUE. Nothing ever parses it.** Every consumer that needs the counterparty, the
    term or the turn reads `PromiseState.character_id`, `.term_kind` or `.made_turn` -- the stored
    typed fields, which are authoritative. This id is a key and nothing else.

    That rule is what makes the identity safe rather than merely tidy. `StrictCharacterId` is a
    free-form 1..64 character string with NO pattern, so a character id may legally contain any
    separator one might choose, and an earlier composed form had to argue that the result was still
    decodable. A digest removes the argument: there is nothing to decode, so a character id
    containing `__`, ending in a term-kind name, or consisting only of separators all hash like any
    other string. `tests/test_promises.py` enforces the no-parse rule with an AST scan rather than
    trusting this paragraph.

    `made_turn` enters as a JSON integer through `canonical_bytes`, so its encoding is the
    canonical-JSON one the whole engine already depends on -- there is no `str(int)` call here to
    get wrong and no zero-padded variant to forbid.
    """
    return PROMISE_ID_PREFIX + canonical_digest(
        {"character_id": character_id, "made_turn": made_turn, "term_kind": term_kind}
    )


def is_maintenance_term(term_kind: PromiseTermKind) -> bool:
    """Whether this term promises a state that must HOLD (as opposed to an act that must HAPPEN).

    The single place the shape distinction is decided, so the settler, the reporter and
    reconciliation cannot disagree about which transitions a term can reach: a maintenance term can
    breach before its deadline and an achievement term cannot.
    """
    return term_kind in MAINTENANCE_TERMS


def earliest_legal_deadline(*, made_turn: int) -> int:
    """The soonest deadline a promise made on `made_turn` may carry.

    Absolute, never relative, so a stored promise means the same thing regardless of when it is
    read. Shared by the decision validator and by the rejection code, so the boundary has exactly
    one definition.
    """
    return made_turn + MINIMUM_PROMISE_TURNS


def trust_delta_bps(status: PromiseStatus) -> int:
    """What reaching `status` does to the counterparty's `personal_trust`.

    The single source of truth for the trust column of the transition table, so the settler and the
    report validator read one function rather than two copies of a table. Reconciliation group 60
    deliberately does NOT call this -- it transcribes the same constants -- because a check that
    calls the function which produced the report cannot fail when that function is wrong.

    `PENDING` returns 0 because a promise that has not moved has not settled anything; the settler
    never applies a delta for a row whose status did not change.
    """
    if status is PromiseStatus.FULFILLED:
        return PROMISE_KEPT_TRUST_GAIN_BPS
    if status is PromiseStatus.BREACHED:
        return -PROMISE_BREACHED_TRUST_LOSS_BPS
    if status is PromiseStatus.EXPIRED:
        return PROMISE_EXPIRED_TRUST_BPS
    if status is PromiseStatus.CANCELLED:
        return PROMISE_RELEASED_TRUST_BPS
    return 0


PROMISE_REJECTION_CODES: tuple[str, ...] = (
    "promise_character_unknown",  # 1
    "promise_term_not_available_for_this_character",  # 2
    "promise_subject_unknown",  # 3
    "promise_deadline_too_soon",  # 4
    "promise_term_already_live_for_this_character",  # 5
    "promise_id_collision",  # 6
    "promise_release_names_no_live_promise",  # 7
)
"""Every reason a promise decision is refused at SUBMISSION, in evaluation precedence.

ONE tuple, drawn from by both surfaces that can refuse a promise -- slot 1's `DecisionSetError` and
`api.decision_preflight`'s `DecisionProblem.code` -- so the two can never drift into naming the same
failure differently. A test pins these exact contents in this exact order, so a code cannot be added
silently and the precedence cannot be reshuffled without the reshuffle being deliberate.

Precedence, recorded so it is not re-derived later: 1 before 2 because an unknown character has no
role to test; 2 before 3 because a subject is only meaningful once the term is available to that
person; 4 before 5 because a malformed horizon should be reported before a scheduling conflict; 6
last among the `make` codes because it is a structural backstop rather than a user error; and 7 is
the only `release` code, unreachable from a `make`.

**What is deliberately NOT here.** There is no `promise_make_and_release_in_one_set`. A
`DecisionSet` carries at most one `PromiseDecision` and its `action` is exclusively `"make"` or
`"release"`, so a set containing both for one promise cannot be constructed -- a code for it would
be a branch no input can reach, and would need a fabricated test to cover. The rule is satisfied by
the type system, and `tests/test_promises.py` asserts that impossibility directly instead.

Nor is there a separate "barred by an earlier release" code: that bar is code 5, because `CANCELLED`
is non-terminal until its original deadline, so an abandoned horizon is still LIVE for validation.
See `validation_live_statuses` below.
"""


PROMISE_SETTLEMENT_REASON_IDS: dict[PromiseStatus, str] = {
    PromiseStatus.BREACHED: "promise_breached",
    PromiseStatus.CANCELLED: "promise_released",
    PromiseStatus.EXPIRED: "promise_expired",
    PromiseStatus.FULFILLED: "promise_fulfilled",
}
"""The report-entry reason id each SETTLEMENT announces, keyed by the status it reached.

Authored here, beside the statuses themselves, so the engine, the CLI renderers and the API labels
all read one mapping instead of three copies of the same correspondence.

`PENDING` is deliberately absent: it is not a settlement. A promise entering `PENDING` is a
*creation*, which emits `promise_made` -- a separate event on a separate test (`made_turn ==
resolving_turn`), which is why a promise made this turn and left pending still announces itself, and
a promise created and breached in one decision set announces both.

`CANCELLED` maps to `promise_released` rather than to its own value, because the player-facing event
is the release they paid for; "cancelled" is the state that release produces, and the expiry that
follows it at the original deadline is the separately-announced `promise_expired`.
"""


def validation_live_statuses(
    *, deadline_turn: int, resolving_turn: int
) -> frozenset[PromiseStatus]:
    """Which statuses count as "already live" when code 5 is evaluated, for a promise with this
    deadline on this turn.

    Validation runs BEFORE the settler, so a naive "non-terminal in the opening state" test would
    see a `CANCELLED` row whose deadline is *this* turn -- a row the settler's first step is about
    to expire -- and would reject the very reissue the lifecycle exists to permit. The bar would
    then lift one turn late.

    So a `CANCELLED` row is live only while its ORIGINAL deadline is still ahead:

        validation_live(p) := p.status is PENDING
                           or (p.status is CANCELLED and p.deadline_turn > resolving_turn)

    which makes "reissue at the original deadline, never earlier" a property of one predicate rather
    than of an ordering between two phases.
    """
    if deadline_turn > resolving_turn:
        return LIVE_PROMISE_STATUSES
    return frozenset({PromiseStatus.PENDING})


PromiseReleaseBlockReason: TypeAlias = Literal[
    "promise_missing",
    "promise_already_settled",
    "promise_already_released",
    "promise_past_releasing",
]
"""Every reason a release is refused, as an exact shared contract rather than a bare `str`.

Typed so the two surfaces that consume it -- slot 1's code 7 and the decision-options projection --
are checked against the same four spellings, and a typo in a reason is a type error rather than a
silent mismatch between what the engine refuses and what the interface says it refuses.
"""


def release_block_reason(
    *,
    status: PromiseStatus | None,
    deadline_turn: int | None,
    resolving_turn: int,
) -> PromiseReleaseBlockReason | None:
    """Why this promise cannot be released now, or `None` when it can be.

    ONE definition, drawn from by both surfaces that decide releasability -- slot 1 raises
    `promise_release_names_no_live_promise` (code 7) exactly when this returns non-`None`, and the
    projection sets `releasable = reason is None`. So the interface cannot offer a release the
    resolver will refuse, nor hide one it would accept.

    **Total over code 7's whole domain**, which is why `status` is nullable. An earlier draft took
    only a status and a deadline and so answered for `PENDING` and `CANCELLED` alone -- but code 7
    also refuses an id naming no row at all, and one naming a row that has already settled, so
    "exactly when this returns a reason" would have been false for half its cases.

    **Primitives, never a `PromiseState`.** `state.py` imports `PromiseStatus`, `PromiseTermKind`,
    `MINIMUM_PROMISE_TURNS`, `TERMINAL_PROMISE_STATUSES` and `is_maintenance_term` from this module,
    so the dependency runs state -> promises; taking a `PromiseState` here would close that cycle.
    This module is the pure vocabulary layer and imports nothing but `canonical_digest`. Callers
    pull the two fields off their row before calling.

    `status is None` represents an absent promise.
    """
    if status is None:
        return "promise_missing"
    if status in TERMINAL_PROMISE_STATUSES:
        return "promise_already_settled"
    if status is PromiseStatus.CANCELLED:
        # Already paid for, and still running out its ORIGINAL horizon: releasing again would buy
        # nothing, and the pair stays barred until that deadline expires it.
        return "promise_already_released"
    assert deadline_turn is not None, "a PENDING promise always carries its deadline"
    if deadline_turn <= resolving_turn:
        # Past releasing: this promise settles on its merits this turn (the seven-step precedence,
        # step 2). Allowing it would let a player duck a settlement already due.
        return "promise_past_releasing"
    return None
