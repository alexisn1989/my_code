"""Legislative vocabulary: chambers, party roles, proposal routes and outcomes (Phase 3B1, §5.1).

**This module names things; it decides nothing.** It exports no formula, no weight and no
threshold. Like `simulation.constitution`, that absence is deliberate: the enums below describe
*structure* — how a legislature is shaped, what relationship a party has to the government, which
lawmaking route a proposal took — and never how deserving any of it is.

The one place a constitutional type meets a legislative one is **routing** (`simulation.phases`,
§8): which chambers must approve a proposal, and whether a decree is legally available. That is
structure deciding *procedure*. Neither `simulation.apportionment` nor
`simulation.legislative_voting` accepts a constitutional type at all, which keeps Phase 3A's
neutrality guarantee intact through Phase 3B1 — see
`docs/adr/0010-legislature-parties-and-political-capital-bargaining.md`.

Targets Python 3.11, so this uses `StrEnum` (3.11+) exactly as `simulation.constitution` does.
"""

from __future__ import annotations

from enum import StrEnum


class LegislativeChamber(StrEnum):
    """Which chamber of a legislature a seat sits in.

    **Declaration order is canonical order**, the same rule `SectorCategory` and `ResourceCategory`
    already follow: every tuple keyed by this enum must appear in this order, and a noncanonical
    ordering is *rejected* rather than silently repaired (the R3 reject-not-normalize rule).

    `LOWER` is the sole chamber of a unicameral legislature. That is a naming choice, not a
    judgement: a unicameral body is neither "lower" nor "upper" in any real sense, but picking one
    consistently means `Legislature.UNICAMERAL` maps to exactly one representable shape instead of
    two indistinguishable ones. `simulation.invariants` enforces it
    (`unicameral_chamber_must_be_lower`).
    """

    LOWER = "lower"
    UPPER = "upper"


class GovernmentRole(StrEnum):
    """A party's **formal** relationship to the current government.

    This is an institutional fact — who is in the cabinet, who guarantees supply — not sentiment.
    Sentiment lives on the *bloc* as `government_relationship_bps`, because a party's formal role
    and its caucuses' actual loyalty are genuinely different things: a rebel faction inside a
    governing party is exactly the case a party-level-only model cannot represent.
    """

    COALITION = "coalition"
    CONFIDENCE_AND_SUPPLY = "confidence_and_supply"
    OPPOSITION = "opposition"


class ProposalRoute(StrEnum):
    """How the player asked for a proposal to become law.

    Chosen explicitly per proposal, never inferred. A government that *could* rule by decree still
    has to say so, because bypassing a chamber is a deliberate act that later phases will attach
    consequences to (courts, legitimacy cost, constitutional crisis -- Phase 3C).
    """

    LEGISLATIVE = "legislative"
    DECREE = "decree"


class ChangeDirection(StrEnum):
    """Which way a proposed policy quantity moves, kept **separate from how far** it moves.

    Direction and intensity are stored as two fields rather than one signed "percent change"
    because the ratio is genuinely undefined in one real case: raising spending from zero. A single
    relative-change field would have to record that as `0`, which reads as "nothing changed" when
    the truth is the opposite — creating a program where none existed is the *largest* spending
    change available, not the smallest. See `legislative_voting.spending_change` for all four
    branches.
    """

    DECREASE = "decrease"
    UNCHANGED = "unchanged"
    INCREASE = "increase"


class LegislativeOutcome(StrEnum):
    """What became of the turn's budget proposal.

    Every member describes a turn that genuinely **completed**. There is deliberately no
    `route_unavailable` member: asking for a decree the constitution does not authorise is an
    *invalid decision*, not an outcome, and it aborts the turn atomically via
    `core.errors.DecisionSetError` (§8.1). Recording it here would assert that a turn legitimately
    resolved in which the player attempted an extra-constitutional act and simply did not — which
    is a lie about the game state, and quietly normalises rule-breaking.

    Illegal or extra-constitutional decrees are a real feature for a later phase, and they need
    courts, judicial review and constitutional-crisis mechanics (`judicial_review` already exists
    as a constitutional axis and is read by nothing) -- not a quiet reinterpretation of an invalid
    command as a completed turn.
    """

    NO_PROPOSAL = "no_proposal"
    PASSED_LEGISLATIVE = "passed_legislative"
    FAILED_LEGISLATIVE = "failed_legislative"
    ENACTED_BY_DECREE = "enacted_by_decree"
