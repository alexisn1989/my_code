"""Composable constitutional structure: how authority is legally organised (Phase 3A, §9).

**This module describes legal structure and nothing else.** It exports no legitimacy function, no
scoring table, and no per-axis weights of any kind. That absence is deliberate and load-bearing:
Phase 3A's central rule is that the *form* of a government must never determine how *accepted* it
is. Acceptance is `PoliticalState.constitutional_order_support_bps` — scenario-authored, sitting
beside the constitution rather than derived from it — and legitimacy moves from that plus economic
performance (`simulation.legitimacy`, which cannot even take a constitutional argument). See
`docs/adr/0009-constitutional-foundation-legitimacy-political-capital.md`.

**Validity means internally coherent, not publicly legitimate.** The rules below (C1-C7) reject
constitutions describing an institutionally impossible arrangement — a parliamentary executive with
no parliament, a term limit on a hereditary monarch. They say nothing about whether an order is
good, popular, stable, or deserving of acceptance, and every combination they permit must remain
reachable: a stable democracy, a democracy backsliding into rule by decree, a one-party state, a
personal dictatorship, a monarchy, and a dictatorship that introduces competitive elections are all
valid constitutions here, and all equally capable of being widely accepted or widely rejected.

Rather than one flattened `democracy | dictatorship` enum, authority is described by seven
independent axes plus two optional scalars, so a government can change one dimension at a time —
which is what makes gradual constitutional change representable at all in later phases.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.canonical_json import canonical_digest

_STRICT_CONFIG = ConfigDict(extra="forbid", validate_assignment=True)

StrictTermCount: TypeAlias = Annotated[int, Field(strict=True, gt=0)]
"""A count of executive terms. Strictly positive: "no term limit" is expressed by `None`, never by
zero, so an absent limit and a nonsensical zero-term limit can never be confused."""

StrictTurnInterval: TypeAlias = Annotated[int, Field(strict=True, gt=0)]
"""A number of turns between constitutionally required national elections. Strictly positive for
the same reason: "no required election" is `None`, not `0`."""


class ExecutiveSystem(StrEnum):
    """How the executive relates to the legislature.

    **(R8)** `MONARCHICAL` exists because `PRESIDENTIAL + HEREDITARY` is incoherent: a presidential
    executive's defining feature is a separate origin from, and accountability distinct from, the
    legislature — a mandate or an appointment, never an inheritance. `MONARCHICAL` is the value that
    makes a hereditary (or elective) head of state honest, bound by C6/C7 below.
    """

    PRESIDENTIAL = "presidential"
    PARLIAMENTARY = "parliamentary"
    SEMI_PRESIDENTIAL = "semi_presidential"
    MONARCHICAL = "monarchical"


class ExecutiveSelection(StrEnum):
    """How the executive comes to hold office."""

    DIRECT_ELECTION = "direct_election"
    LEGISLATIVE_SELECTION = "legislative_selection"
    HEREDITARY = "hereditary"
    APPOINTED = "appointed"


class Legislature(StrEnum):
    """Whether a standing deliberative body exists, and how many chambers it has.

    Phase 3A models the *existence and shape* of a legislature only. Chambers with members, seat
    counts, parties and law passage are Phase 3B — deliberately absent rather than stubbed empty.
    """

    NONE = "none"
    UNICAMERAL = "unicameral"
    BICAMERAL = "bicameral"


class TerritorialOrganization(StrEnum):
    """Whether authority is constitutionally dispersed to subnational tiers.

    **Mechanically inert in Phase 3A** — it has no economic, legitimacy, political-capital or
    provincial effect, and a dedicated isolation test pins that (changing `UNITARY` to `FEDERAL`
    changes the constitutional state and its digest and nothing else). It is declared now because
    it is a foundational schema fact that later phases must not have to retrofit into every
    existing save, and because federal behavior needs Phase 6's map to mean anything. Deferred, not
    implemented — stated plainly rather than disguised as an effect.
    """

    UNITARY = "unitary"
    FEDERAL = "federal"


class JudicialReview(StrEnum):
    """How far courts may constrain the other branches."""

    NONE = "none"
    WEAK = "weak"
    STRONG = "strong"


class AmendmentDifficulty(StrEnum):
    """How hard the constitution itself is to change.

    Phase 3A stores this; amendment *decisions* are Phase 3B/3C.
    """

    SIMPLE_MAJORITY = "simple_majority"
    SUPERMAJORITY = "supermajority"
    ENTRENCHED = "entrenched"


class DecreeAuthority(StrEnum):
    """Whether the executive may legislate unilaterally."""

    NONE = "none"
    EMERGENCY_ONLY = "emergency_only"
    UNLIMITED = "unlimited"


class ConstitutionState(BaseModel):
    """One country's constitutional order: seven independent axes plus two optional scalars.

    `executive_term_limit_terms is None` means there is no term limit, and
    `national_election_interval_turns is None` means no constitutionally required national
    election — genuinely absent, never a sentinel zero, matching
    `ResourceDepositState.stock_ceiling`'s established `| None` precedent.

    **(R8)** `national_election_interval_turns`, not `executive_election_interval_turns`: a
    parliamentary national election selects a *legislature*, which then selects the executive — the
    electorate never votes for the executive directly in that arrangement, so a name built around
    "executive election" would misdescribe it. The new name states what is actually scheduled.

    The validator below applies C1-C10 so an incoherent constitution can never be constructed on any
    path — fresh build, scenario load, or `model_validate_json` history replay.
    `simulation.invariants` re-checks the same rules independently against state, to catch a
    bypassed construction (`model_construct`).
    """

    model_config = _STRICT_CONFIG

    executive_system: ExecutiveSystem
    executive_selection: ExecutiveSelection
    legislature: Legislature
    territorial_organization: TerritorialOrganization
    judicial_review: JudicialReview
    amendment_difficulty: AmendmentDifficulty
    decree_authority: DecreeAuthority
    executive_term_limit_terms: StrictTermCount | None = None
    national_election_interval_turns: StrictTurnInterval | None = None

    @model_validator(mode="after")
    def _combination_is_internally_coherent(self) -> ConstitutionState:
        problem = first_constitutional_violation(self)
        if problem is not None:
            code, message = problem
            raise ValueError(f"{code}: {message}")
        return self


def first_constitutional_violation(
    constitution: ConstitutionState,
) -> tuple[str, str] | None:
    """Return `(code, message)` for the first violated rule C1-C10, or `None` if coherent.

    Shared by `ConstitutionState`'s own validator and by `simulation.invariants`'s bypassed-
    construction backstop, so the two can never disagree about what "valid" means. Both callers
    need the *code*, not just a boolean, so a violation is always attributable to a named rule.

    Checked top-down; exactly one code is reported per invalid constitution.
    """
    system = constitution.executive_system
    selection = constitution.executive_selection
    legislature = constitution.legislature

    # C1/C2: a parliamentary executive is, by definition, made and unmade by a parliament.
    if system is ExecutiveSystem.PARLIAMENTARY:
        if legislature is Legislature.NONE:
            return (
                "parliamentary_requires_legislature",
                "a parliamentary executive requires a legislature, but legislature is 'none'",
            )
        if selection is not ExecutiveSelection.LEGISLATIVE_SELECTION:
            return (
                "parliamentary_requires_legislative_selection",
                "a parliamentary executive must be selected by the legislature, but "
                f"executive_selection is {selection.value!r}",
            )

    # C3: a presidential executive has a separate origin from the legislature, so not
    # LEGISLATIVE_SELECTION. (It also cannot inherit office -- not HEREDITARY -- but that half of
    # the same logical constraint is enforced by C6 below, which fires first for that sub-case; see
    # C6's comment. APPOINTED stays legal here: an appointed presidency is exactly how many
    # authoritarian republics are constituted.)
    if (
        system is ExecutiveSystem.PRESIDENTIAL
        and selection is ExecutiveSelection.LEGISLATIVE_SELECTION
    ):
        return (
            "presidential_forbids_legislative_selection",
            "a presidential executive cannot be selected by the legislature; that is a "
            "parliamentary arrangement",
        )

    # C4: semi-presidentialism is a directly-elected president PLUS a legislature.
    if system is ExecutiveSystem.SEMI_PRESIDENTIAL:
        if selection is not ExecutiveSelection.DIRECT_ELECTION:
            return (
                "semi_presidential_requires_direct_election_and_legislature",
                "a semi-presidential executive must be directly elected, but executive_selection "
                f"is {selection.value!r}",
            )
        if legislature is Legislature.NONE:
            return (
                "semi_presidential_requires_direct_election_and_legislature",
                "a semi-presidential system requires a legislature, but legislature is 'none'",
            )

    # C5: nothing can select the executive if no legislature exists. Independently reachable when
    # the executive_system is PRESIDENTIAL-rejected-earlier or SEMI_PRESIDENTIAL cases do not apply.
    if selection is ExecutiveSelection.LEGISLATIVE_SELECTION and legislature is Legislature.NONE:
        return (
            "legislative_selection_requires_legislature",
            "executive_selection is 'legislative_selection' but there is no legislature to "
            "perform the selection",
        )

    # C6 (R8, new): a hereditary executive is a monarchical arrangement -- not presidential,
    # parliamentary or semi-presidential. This is the rule that makes the previously-incoherent
    # PRESIDENTIAL + HEREDITARY impossible. (PARLIAMENTARY + HEREDITARY and SEMI_PRESIDENTIAL +
    # HEREDITARY are already caught above by C1/C2 and C4 respectively -- this is what makes THOSE
    # combinations impossible too, just reported under their own more specific codes. C6 is the
    # first rule to fire only for the PRESIDENTIAL + HEREDITARY combination, which no earlier rule
    # addresses.)
    if selection is ExecutiveSelection.HEREDITARY and system is not ExecutiveSystem.MONARCHICAL:
        return (
            "hereditary_requires_monarchical_system",
            "executive_selection is 'hereditary' but executive_system is "
            f"{system.value!r}, not 'monarchical'",
        )

    # C7 (R8, new): a monarch inherits, or is chosen by a restricted body (APPOINTED covers
    # elective monarchy) -- never directly elected by the nation, nor selected by a legislature it
    # does not answer to.
    if system is ExecutiveSystem.MONARCHICAL and selection not in (
        ExecutiveSelection.HEREDITARY,
        ExecutiveSelection.APPOINTED,
    ):
        return (
            "monarchical_requires_hereditary_or_appointed",
            "executive_system is 'monarchical' but executive_selection is "
            f"{selection.value!r}, which is neither 'hereditary' nor 'appointed'",
        )

    # C8: a hereditary executive serves for life; "terms" is not a coherent unit for it.
    if (
        constitution.executive_term_limit_terms is not None
        and selection is ExecutiveSelection.HEREDITARY
    ):
        return (
            "term_limit_requires_non_hereditary_executive",
            "a hereditary executive cannot have a term limit; terms are not a unit of a "
            "lifetime office",
        )

    # C9 (R8, rewritten): a scheduled national election must have something nationally elected --
    # either a legislature (which the electorate elects even under a parliamentary executive), or a
    # directly-elected executive. This correctly admits the parliamentary case the old executive-
    # only rule wrongly rejected.
    if (
        constitution.national_election_interval_turns is not None
        and legislature is Legislature.NONE
        and selection is not ExecutiveSelection.DIRECT_ELECTION
    ):
        return (
            "national_election_requires_something_elected",
            "national_election_interval_turns is set but there is no legislature and "
            f"executive_selection is {selection.value!r}, not 'direct_election'",
        )

    # C10 (Phase 3B1): an order in which no organ can make law is not a constrained government;
    # it is the absence of one. With no legislature, the executive must be able to legislate --
    # otherwise the constitution describes a state that cannot change its own laws by any route,
    # which is not a hard government to play, it is an unplayable one.
    if legislature is Legislature.NONE and (
        constitution.decree_authority is not DecreeAuthority.UNLIMITED
    ):
        return (
            "legislature_absent_requires_unlimited_decree",
            f"legislature is 'none' but decree_authority is {constitution.decree_authority.value!r}, "
            "so no organ can make law",
        )

    return None


def constitution_digest(constitution: ConstitutionState) -> str:
    """A deterministic structural version marker over the constitution's nine fields.

    Changes if and only if the legal structure changes, which makes it a stable "amendment
    version" identifier for Phase 3B/3C and lets `simulation.reconciliation` prove in one
    comparison that Phase 3A never mutates a constitution.

    Carries **no** legitimacy meaning. It is a hash of structure, not a rating of it. Uses the same
    `core.canonical_json.canonical_digest` that backs `HistoryEntry.entry_hash`, so ordering and
    formatting can never make two identical constitutions digest differently.
    """
    return canonical_digest(constitution.model_dump(mode="json"))
