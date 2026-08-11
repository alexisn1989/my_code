"""Tests for `simulation.constitution` (Phase 3A, T-C1..T-C10; Phase 3B1 adds C10 itself).

Two things this file exists to pin:

1. **Validity rules C1-C10 are total and exact** — every one of the 10,368 reachable configurations
   is accepted or rejected exactly as the rules predict, so "valid" is a closed, enumerable set
   rather than whatever the validator happens to do.
2. **Validity is not legitimacy** — the arrangements a reader might expect to be penalised
   (unlimited decree authority alongside elections, an entrenched constitution, a federal
   dictatorship, strong courts with no legislature) are all explicitly *legal*, because Phase 3A
   must not encode an opinion about which forms of government deserve acceptance. The numeric
   half of that guarantee lives in `test_legitimacy_neutrality.py`.
"""

from __future__ import annotations

import itertools

import pytest
from pydantic import ValidationError

from app.simulation.constitution import (
    AmendmentDifficulty,
    ConstitutionState,
    DecreeAuthority,
    ExecutiveSelection,
    ExecutiveSystem,
    JudicialReview,
    Legislature,
    TerritorialOrganization,
    constitution_digest,
    first_constitutional_violation,
)


def _constitution(**overrides: object) -> ConstitutionState:
    """A coherent presidential baseline; override one axis at a time."""
    base: dict[str, object] = {
        "executive_system": ExecutiveSystem.PRESIDENTIAL,
        "executive_selection": ExecutiveSelection.DIRECT_ELECTION,
        "legislature": Legislature.UNICAMERAL,
        "territorial_organization": TerritorialOrganization.UNITARY,
        "judicial_review": JudicialReview.WEAK,
        "amendment_difficulty": AmendmentDifficulty.SUPERMAJORITY,
        "decree_authority": DecreeAuthority.EMERGENCY_ONLY,
    }
    base.update(overrides)
    return ConstitutionState(**base)  # type: ignore[arg-type]


# --- T-C1: every rule C1-C10 rejects, with its own code ----------------------


def test_c1_parliamentary_requires_legislature() -> None:
    with pytest.raises(ValidationError, match="parliamentary_requires_legislature"):
        _constitution(
            executive_system=ExecutiveSystem.PARLIAMENTARY,
            executive_selection=ExecutiveSelection.LEGISLATIVE_SELECTION,
            legislature=Legislature.NONE,
        )


def test_c2_parliamentary_requires_legislative_selection() -> None:
    with pytest.raises(ValidationError, match="parliamentary_requires_legislative_selection"):
        _constitution(
            executive_system=ExecutiveSystem.PARLIAMENTARY,
            executive_selection=ExecutiveSelection.DIRECT_ELECTION,
            legislature=Legislature.UNICAMERAL,
        )


def test_c3_presidential_forbids_legislative_selection() -> None:
    with pytest.raises(ValidationError, match="presidential_forbids_legislative_selection"):
        _constitution(
            executive_system=ExecutiveSystem.PRESIDENTIAL,
            executive_selection=ExecutiveSelection.LEGISLATIVE_SELECTION,
            legislature=Legislature.UNICAMERAL,
        )


def test_c4_semi_presidential_requires_direct_election() -> None:
    with pytest.raises(
        ValidationError, match="semi_presidential_requires_direct_election_and_legislature"
    ):
        _constitution(
            executive_system=ExecutiveSystem.SEMI_PRESIDENTIAL,
            executive_selection=ExecutiveSelection.APPOINTED,
            legislature=Legislature.UNICAMERAL,
        )


def test_c4_semi_presidential_requires_legislature() -> None:
    with pytest.raises(
        ValidationError, match="semi_presidential_requires_direct_election_and_legislature"
    ):
        _constitution(
            executive_system=ExecutiveSystem.SEMI_PRESIDENTIAL,
            executive_selection=ExecutiveSelection.DIRECT_ELECTION,
            legislature=Legislature.NONE,
        )


def test_c5_legislative_selection_requires_legislature() -> None:
    """Reachable independently of C1/C2/C3/C4/C6: neither a parliamentary, presidential, semi-
    presidential nor hereditary/monarchical combination applies, so this fires for the remaining
    combination — a monarchy that tries to be selected by a nonexistent legislature."""
    violation = first_constitutional_violation(
        ConstitutionState.model_construct(
            executive_system=ExecutiveSystem.PARLIAMENTARY,
            executive_selection=ExecutiveSelection.LEGISLATIVE_SELECTION,
            legislature=Legislature.UNICAMERAL,
            territorial_organization=TerritorialOrganization.UNITARY,
            judicial_review=JudicialReview.NONE,
            amendment_difficulty=AmendmentDifficulty.SUPERMAJORITY,
            decree_authority=DecreeAuthority.NONE,
            executive_term_limit_terms=None,
            national_election_interval_turns=None,
        )
    )
    assert violation is None  # sanity: the coherent case really is coherent

    bypassed = ConstitutionState.model_construct(
        executive_system=ExecutiveSystem.MONARCHICAL,
        executive_selection=ExecutiveSelection.LEGISLATIVE_SELECTION,
        legislature=Legislature.NONE,
        territorial_organization=TerritorialOrganization.UNITARY,
        judicial_review=JudicialReview.NONE,
        amendment_difficulty=AmendmentDifficulty.SUPERMAJORITY,
        decree_authority=DecreeAuthority.NONE,
        executive_term_limit_terms=None,
        national_election_interval_turns=None,
    )
    code, _ = first_constitutional_violation(bypassed)  # type: ignore[misc]
    assert code == "legislative_selection_requires_legislature"


def test_c6_hereditary_requires_monarchical_system() -> None:
    """The rule that makes the previously-incoherent PRESIDENTIAL + HEREDITARY impossible."""
    with pytest.raises(ValidationError, match="hereditary_requires_monarchical_system"):
        _constitution(
            executive_system=ExecutiveSystem.PRESIDENTIAL,
            executive_selection=ExecutiveSelection.HEREDITARY,
            legislature=Legislature.NONE,
        )


def test_c7_monarchical_requires_hereditary_or_appointed() -> None:
    with pytest.raises(ValidationError, match="monarchical_requires_hereditary_or_appointed"):
        _constitution(
            executive_system=ExecutiveSystem.MONARCHICAL,
            executive_selection=ExecutiveSelection.DIRECT_ELECTION,
            legislature=Legislature.UNICAMERAL,
        )


def test_c8_term_limit_requires_non_hereditary_executive() -> None:
    with pytest.raises(ValidationError, match="term_limit_requires_non_hereditary_executive"):
        _constitution(
            executive_system=ExecutiveSystem.MONARCHICAL,
            executive_selection=ExecutiveSelection.HEREDITARY,
            legislature=Legislature.NONE,
            executive_term_limit_terms=2,
        )


def test_c9_national_election_requires_something_elected() -> None:
    with pytest.raises(ValidationError, match="national_election_requires_something_elected"):
        _constitution(
            executive_system=ExecutiveSystem.MONARCHICAL,
            executive_selection=ExecutiveSelection.APPOINTED,
            legislature=Legislature.NONE,
            national_election_interval_turns=16,
        )


@pytest.mark.parametrize(
    "decree_authority",
    [
        pytest.param(DecreeAuthority.NONE, id="no-decree-power"),
        pytest.param(DecreeAuthority.EMERGENCY_ONLY, id="emergency-decree-only"),
    ],
)
def test_c10_legislature_absent_requires_unlimited_decree(
    decree_authority: DecreeAuthority,
) -> None:
    """(Phase 3B1) An order in which no organ can make law is not a constrained government; it is
    the absence of one.

    `EMERGENCY_ONLY` fails alongside `NONE` because Phase 3B1 has no emergency state, trigger,
    threshold or duration to read — so an emergency-only executive with no legislature has no
    route to legislate at all, whatever the label suggests.
    """
    with pytest.raises(ValidationError, match="legislature_absent_requires_unlimited_decree"):
        _constitution(
            executive_selection=ExecutiveSelection.APPOINTED,
            legislature=Legislature.NONE,
            decree_authority=decree_authority,
        )


def test_c10_is_independently_reachable_as_the_first_violation() -> None:
    """C10 is placed last, so it only fires where no earlier rule does — which means it could in
    principle be unreachable, masked entirely by C1-C9. It is not. The smallest witness:

    C1/C2 need a parliamentary executive; C3 needs legislative selection; C4 needs
    semi-presidential; C5 needs legislative selection; C6/C7 concern hereditary and monarchical;
    C8 needs a term limit; C9 needs an election interval. None applies here, and C10 fires.
    """
    bypassed = ConstitutionState.model_construct(
        executive_system=ExecutiveSystem.PRESIDENTIAL,
        executive_selection=ExecutiveSelection.DIRECT_ELECTION,
        legislature=Legislature.NONE,
        territorial_organization=TerritorialOrganization.UNITARY,
        judicial_review=JudicialReview.NONE,
        amendment_difficulty=AmendmentDifficulty.SUPERMAJORITY,
        decree_authority=DecreeAuthority.NONE,
        executive_term_limit_terms=None,
        national_election_interval_turns=None,
    )
    code, _ = first_constitutional_violation(bypassed)  # type: ignore[misc]
    assert code == "legislature_absent_requires_unlimited_decree"


def test_c10_counts_exactly_the_configurations_it_should() -> None:
    """C10 is the first violation on exactly 324 of the 10,368 configurations — enough to matter,
    and far from the whole space. A rule that rejected nothing, or nearly everything, would be
    evidence it had been written wrong."""
    fires = sum(
        1
        for combo in itertools.product(
            ExecutiveSystem,
            ExecutiveSelection,
            Legislature,
            TerritorialOrganization,
            JudicialReview,
            AmendmentDifficulty,
            DecreeAuthority,
            (None, 2),
            (None, 16),
        )
        if _expected_violation_code(
            combo[0], combo[1], combo[2], combo[7] is not None, combo[8] is not None, combo[6]
        )
        == "legislature_absent_requires_unlimited_decree"
    )
    assert fires == 324


def test_c10_leaves_the_absolute_executive_routes_open() -> None:
    """C10 must not close the dictatorship and absolute-monarchy archetypes Phase 3A deliberately
    left reachable — it only requires that such an order can actually legislate."""
    assert _constitution(
        executive_selection=ExecutiveSelection.APPOINTED,
        legislature=Legislature.NONE,
        decree_authority=DecreeAuthority.UNLIMITED,
    )
    assert _constitution(
        executive_system=ExecutiveSystem.MONARCHICAL,
        executive_selection=ExecutiveSelection.HEREDITARY,
        legislature=Legislature.NONE,
        decree_authority=DecreeAuthority.UNLIMITED,
    )


def test_c10_does_not_constrain_a_government_that_has_a_legislature() -> None:
    """With a chamber to pass laws, every decree setting stays legal — including none at all,
    which is the ordinary democratic case."""
    for legislature in (Legislature.UNICAMERAL, Legislature.BICAMERAL):
        for decree_authority in DecreeAuthority:
            assert _constitution(legislature=legislature, decree_authority=decree_authority)


# --- T-C2: every required archetype is constructible -------------------------


def test_all_required_archetypes_construct_cleanly() -> None:
    """The routes Phase 3A must leave open — including a dictatorship that introduces competitive
    elections, and both hereditary and elective monarchy. None is privileged or penalised here;
    that is what `test_legitimacy_neutrality.py` proves numerically."""
    archetypes = {
        "stable parliamentary democracy": dict(
            executive_system=ExecutiveSystem.PARLIAMENTARY,
            executive_selection=ExecutiveSelection.LEGISLATIVE_SELECTION,
            legislature=Legislature.BICAMERAL,
            judicial_review=JudicialReview.STRONG,
            executive_term_limit_terms=2,
            national_election_interval_turns=16,
        ),
        "presidential democracy": dict(
            executive_system=ExecutiveSystem.PRESIDENTIAL,
            executive_selection=ExecutiveSelection.DIRECT_ELECTION,
            legislature=Legislature.UNICAMERAL,
            territorial_organization=TerritorialOrganization.FEDERAL,
            executive_term_limit_terms=2,
            national_election_interval_turns=16,
        ),
        "backsliding democracy": dict(
            executive_system=ExecutiveSystem.PRESIDENTIAL,
            executive_selection=ExecutiveSelection.DIRECT_ELECTION,
            legislature=Legislature.UNICAMERAL,
            judicial_review=JudicialReview.NONE,
            amendment_difficulty=AmendmentDifficulty.SIMPLE_MAJORITY,
            decree_authority=DecreeAuthority.UNLIMITED,
            national_election_interval_turns=20,
        ),
        "one-party government": dict(
            executive_system=ExecutiveSystem.PARLIAMENTARY,
            executive_selection=ExecutiveSelection.LEGISLATIVE_SELECTION,
            legislature=Legislature.UNICAMERAL,
            judicial_review=JudicialReview.NONE,
            amendment_difficulty=AmendmentDifficulty.ENTRENCHED,
            decree_authority=DecreeAuthority.UNLIMITED,
        ),
        "personal dictatorship": dict(
            executive_system=ExecutiveSystem.PRESIDENTIAL,
            executive_selection=ExecutiveSelection.APPOINTED,
            legislature=Legislature.NONE,
            judicial_review=JudicialReview.NONE,
            amendment_difficulty=AmendmentDifficulty.ENTRENCHED,
            decree_authority=DecreeAuthority.UNLIMITED,
        ),
        "hereditary monarchy": dict(
            executive_system=ExecutiveSystem.MONARCHICAL,
            executive_selection=ExecutiveSelection.HEREDITARY,
            legislature=Legislature.NONE,
            judicial_review=JudicialReview.NONE,
            amendment_difficulty=AmendmentDifficulty.ENTRENCHED,
            decree_authority=DecreeAuthority.UNLIMITED,
        ),
        # (Phase 3B1) UNLIMITED, not EMERGENCY_ONLY: C10 rejects an order with no legislature
        # and no unlimited decree, because no organ in it could make law at all. The archetype
        # this test guards is "elective monarchy", which survives the change intact.
        "elective monarchy": dict(
            executive_system=ExecutiveSystem.MONARCHICAL,
            executive_selection=ExecutiveSelection.APPOINTED,
            legislature=Legislature.NONE,
            judicial_review=JudicialReview.WEAK,
            amendment_difficulty=AmendmentDifficulty.ENTRENCHED,
            decree_authority=DecreeAuthority.UNLIMITED,
        ),
        "constitutional monarchy": dict(
            executive_system=ExecutiveSystem.MONARCHICAL,
            executive_selection=ExecutiveSelection.HEREDITARY,
            legislature=Legislature.BICAMERAL,
            judicial_review=JudicialReview.STRONG,
            decree_authority=DecreeAuthority.NONE,
        ),
        "dictatorship that introduced elections": dict(
            executive_system=ExecutiveSystem.PRESIDENTIAL,
            executive_selection=ExecutiveSelection.DIRECT_ELECTION,
            legislature=Legislature.UNICAMERAL,
            judicial_review=JudicialReview.WEAK,
            executive_term_limit_terms=2,
            national_election_interval_turns=16,
        ),
        "semi-presidential republic": dict(
            executive_system=ExecutiveSystem.SEMI_PRESIDENTIAL,
            executive_selection=ExecutiveSelection.DIRECT_ELECTION,
            legislature=Legislature.BICAMERAL,
            national_election_interval_turns=20,
        ),
    }
    for label, axes in archetypes.items():
        assert _constitution(**axes) is not None, label


# --- T-C3: deliberate non-rules stay legal -----------------------------------


def test_strong_judicial_review_without_a_legislature_is_legal() -> None:
    """Courts can review executive decrees; this is a real arrangement, not a contradiction."""
    assert _constitution(
        executive_selection=ExecutiveSelection.APPOINTED,
        legislature=Legislature.NONE,
        judicial_review=JudicialReview.STRONG,
        decree_authority=DecreeAuthority.UNLIMITED,  # C10: something must be able to make law
    )


def test_unlimited_decree_with_elections_and_term_limits_is_legal() -> None:
    """Precisely the democratic-backsliding configuration; rejecting it would hard-code a route."""
    assert _constitution(
        decree_authority=DecreeAuthority.UNLIMITED,
        executive_term_limit_terms=2,
        national_election_interval_turns=16,
    )


def test_entrenched_amendment_difficulty_is_legal_with_any_other_axis() -> None:
    for legislature in Legislature:
        assert _constitution(
            legislature=legislature,
            executive_selection=ExecutiveSelection.DIRECT_ELECTION,
            amendment_difficulty=AmendmentDifficulty.ENTRENCHED,
            decree_authority=DecreeAuthority.UNLIMITED,  # C10: legal for every legislature value
        )


def test_federal_organization_without_a_legislature_is_legal() -> None:
    """Federal dictatorships exist."""
    assert _constitution(
        executive_selection=ExecutiveSelection.APPOINTED,
        legislature=Legislature.NONE,
        territorial_organization=TerritorialOrganization.FEDERAL,
        decree_authority=DecreeAuthority.UNLIMITED,  # C10: something must be able to make law
    )


def test_monarchical_with_legislature_judicial_review_and_election_is_legal() -> None:
    """Constitutional monarchies exist and must not be forced into absolutism: a legislature,
    strong courts and a scheduled national election are all legal alongside MONARCHICAL."""
    assert _constitution(
        executive_system=ExecutiveSystem.MONARCHICAL,
        executive_selection=ExecutiveSelection.HEREDITARY,
        legislature=Legislature.BICAMERAL,
        judicial_review=JudicialReview.STRONG,
        national_election_interval_turns=16,
    )


# --- T-C8: total rule coverage over every reachable configuration ------------


def _expected_violation_code(
    system: ExecutiveSystem,
    selection: ExecutiveSelection,
    legislature: Legislature,
    has_term_limit: bool,
    has_election_interval: bool,
    decree_authority: DecreeAuthority,
) -> str | None:
    """An independent re-statement of C1-C10, written from the rule table rather than from the
    implementation, so the two must agree for all 10,368 configurations.

    `decree_authority` became a parameter in Phase 3B1: C10 makes it validity-affecting for the
    first time, so it can no longer be treated as one of the purely descriptive axes.
    """
    if system is ExecutiveSystem.PARLIAMENTARY:
        if legislature is Legislature.NONE:
            return "parliamentary_requires_legislature"
        if selection is not ExecutiveSelection.LEGISLATIVE_SELECTION:
            return "parliamentary_requires_legislative_selection"
    if (
        system is ExecutiveSystem.PRESIDENTIAL
        and selection is ExecutiveSelection.LEGISLATIVE_SELECTION
    ):
        return "presidential_forbids_legislative_selection"
    if system is ExecutiveSystem.SEMI_PRESIDENTIAL and (
        selection is not ExecutiveSelection.DIRECT_ELECTION or legislature is Legislature.NONE
    ):
        return "semi_presidential_requires_direct_election_and_legislature"
    if selection is ExecutiveSelection.LEGISLATIVE_SELECTION and legislature is Legislature.NONE:
        return "legislative_selection_requires_legislature"
    if selection is ExecutiveSelection.HEREDITARY and system is not ExecutiveSystem.MONARCHICAL:
        return "hereditary_requires_monarchical_system"
    if system is ExecutiveSystem.MONARCHICAL and selection not in (
        ExecutiveSelection.HEREDITARY,
        ExecutiveSelection.APPOINTED,
    ):
        return "monarchical_requires_hereditary_or_appointed"
    if has_term_limit and selection is ExecutiveSelection.HEREDITARY:
        return "term_limit_requires_non_hereditary_executive"
    if (
        has_election_interval
        and legislature is Legislature.NONE
        and selection is not (ExecutiveSelection.DIRECT_ELECTION)
    ):
        return "national_election_requires_something_elected"
    if legislature is Legislature.NONE and decree_authority is not DecreeAuthority.UNLIMITED:
        return "legislature_absent_requires_unlimited_decree"
    return None


def test_every_reachable_configuration_matches_the_rule_table() -> None:
    """All 4 x 4 x 3 x 2 x 3 x 3 x 3 = 2,592 axis combinations, times term-limit present/absent
    times election-interval present/absent = 10,368 configurations."""
    checked = 0
    for (
        system,
        selection,
        legislature,
        territorial,
        judicial,
        amendment,
        decree,
        term_limit,
        interval,
    ) in itertools.product(
        ExecutiveSystem,
        ExecutiveSelection,
        Legislature,
        TerritorialOrganization,
        JudicialReview,
        AmendmentDifficulty,
        DecreeAuthority,
        (None, 2),
        (None, 16),
    ):
        checked += 1
        expected = _expected_violation_code(
            system, selection, legislature, term_limit is not None, interval is not None, decree
        )
        bypassed = ConstitutionState.model_construct(
            executive_system=system,
            executive_selection=selection,
            legislature=legislature,
            territorial_organization=territorial,
            judicial_review=judicial,
            amendment_difficulty=amendment,
            decree_authority=decree,
            executive_term_limit_terms=term_limit,
            national_election_interval_turns=interval,
        )
        actual = first_constitutional_violation(bypassed)
        actual_code = None if actual is None else actual[0]
        assert actual_code == expected, (
            f"{system.value}/{selection.value}/{legislature.value}/{decree.value} "
            f"term_limit={term_limit} interval={interval}: "
            f"expected {expected!r}, got {actual_code!r}"
        )
    assert checked == 10_368


def test_the_valid_configuration_count_is_stable() -> None:
    """A regression pin: if a future change alters how many configurations are coherent, that is a
    ruleset-affecting decision that must be made deliberately, not noticed later."""
    # Three purely-descriptive axes remain: territorial (2) x judicial (3) x amendment (3) = 18
    # multiplications that cannot affect validity. `decree_authority` is NO LONGER among them --
    # C10 (Phase 3B1) makes it validity-affecting, so the old single `x 54` factorization is wrong
    # and is replaced by a split one. A 5-tuple with a legislature admits all three decree values
    # (18 x 3 = 54); one without a legislature admits only UNLIMITED (18 x 1 = 18).
    with_legislature = 0
    without_legislature = 0
    for system, selection, legislature, term_limit, interval in itertools.product(
        ExecutiveSystem, ExecutiveSelection, Legislature, (None, 2), (None, 16)
    ):
        if (
            _expected_violation_code(
                system,
                selection,
                legislature,
                term_limit is not None,
                interval is not None,
                DecreeAuthority.UNLIMITED,
            )
            is not None
        ):
            continue
        if legislature is Legislature.NONE:
            without_legislature += 1
        else:
            with_legislature += 1

    total_valid = sum(
        1
        for combo in itertools.product(
            ExecutiveSystem,
            ExecutiveSelection,
            Legislature,
            TerritorialOrganization,
            JudicialReview,
            AmendmentDifficulty,
            DecreeAuthority,
            (None, 2),
            (None, 16),
        )
        if _expected_violation_code(
            combo[0], combo[1], combo[2], combo[7] is not None, combo[8] is not None, combo[6]
        )
        is None
    )
    assert (with_legislature, without_legislature) == (44, 9)
    assert with_legislature * 54 + without_legislature * 18 == total_valid
    assert total_valid == 2_538


# --- T-C9: R8 — the incoherent pairing is gone --------------------------------


def test_c9_presidential_hereditary_is_rejected_by_c6() -> None:
    with pytest.raises(ValidationError, match="hereditary_requires_monarchical_system"):
        _constitution(
            executive_system=ExecutiveSystem.PRESIDENTIAL,
            executive_selection=ExecutiveSelection.HEREDITARY,
            legislature=Legislature.NONE,
        )


def test_c9_monarchical_direct_election_and_legislative_selection_are_rejected_by_c7() -> None:
    with pytest.raises(ValidationError, match="monarchical_requires_hereditary_or_appointed"):
        _constitution(
            executive_system=ExecutiveSystem.MONARCHICAL,
            executive_selection=ExecutiveSelection.DIRECT_ELECTION,
            legislature=Legislature.UNICAMERAL,
        )
    with pytest.raises(ValidationError, match="monarchical_requires_hereditary_or_appointed"):
        _constitution(
            executive_system=ExecutiveSystem.MONARCHICAL,
            executive_selection=ExecutiveSelection.LEGISLATIVE_SELECTION,
            legislature=Legislature.UNICAMERAL,
        )


def test_c9_both_hereditary_and_elective_monarchy_construct() -> None:
    assert _constitution(
        executive_system=ExecutiveSystem.MONARCHICAL,
        executive_selection=ExecutiveSelection.HEREDITARY,
        legislature=Legislature.NONE,
        decree_authority=DecreeAuthority.UNLIMITED,  # C10: an absolute monarch legislates
    )
    assert _constitution(
        executive_system=ExecutiveSystem.MONARCHICAL,
        executive_selection=ExecutiveSelection.APPOINTED,
        legislature=Legislature.NONE,
        decree_authority=DecreeAuthority.UNLIMITED,
    )


# --- T-C10: R8 — the renamed election field -----------------------------------


def test_c10_parliamentary_national_election_with_legislative_selection_is_legal() -> None:
    """The old executive-only rule wrongly rejected this: a parliamentary national election elects
    a legislature, which then selects the executive."""
    assert _constitution(
        executive_system=ExecutiveSystem.PARLIAMENTARY,
        executive_selection=ExecutiveSelection.LEGISLATIVE_SELECTION,
        legislature=Legislature.UNICAMERAL,
        national_election_interval_turns=16,
    )


def test_c10_no_legislature_and_non_direct_election_rejects_a_scheduled_national_election() -> None:
    with pytest.raises(ValidationError, match="national_election_requires_something_elected"):
        _constitution(
            executive_system=ExecutiveSystem.MONARCHICAL,
            executive_selection=ExecutiveSelection.APPOINTED,
            legislature=Legislature.NONE,
            national_election_interval_turns=16,
        )


# --- T-C6/T-C7: digest stability and enum value stability --------------------


def test_identical_axes_produce_identical_digests() -> None:
    assert constitution_digest(_constitution()) == constitution_digest(_constitution())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        pytest.param("legislature", Legislature.BICAMERAL, id="legislature"),
        pytest.param("territorial_organization", TerritorialOrganization.FEDERAL, id="territorial"),
        pytest.param("judicial_review", JudicialReview.STRONG, id="judicial"),
        pytest.param("amendment_difficulty", AmendmentDifficulty.ENTRENCHED, id="amendment"),
        pytest.param("decree_authority", DecreeAuthority.UNLIMITED, id="decree"),
        pytest.param("executive_term_limit_terms", 2, id="term-limit"),
        pytest.param("national_election_interval_turns", 16, id="election-interval"),
    ],
)
def test_changing_any_single_axis_changes_the_digest(field: str, value: object) -> None:
    assert constitution_digest(_constitution()) != constitution_digest(
        _constitution(**{field: value})
    )


def test_enum_values_are_stable_strings() -> None:
    """Canonical JSON — and therefore every `entry_hash` — depends on these literals; renaming one
    is a ruleset-affecting change, not a refactor."""
    assert [m.value for m in ExecutiveSystem] == [
        "presidential",
        "parliamentary",
        "semi_presidential",
        "monarchical",
    ]
    assert [m.value for m in ExecutiveSelection] == [
        "direct_election",
        "legislative_selection",
        "hereditary",
        "appointed",
    ]
    assert [m.value for m in Legislature] == ["none", "unicameral", "bicameral"]
    assert [m.value for m in TerritorialOrganization] == ["unitary", "federal"]
    assert [m.value for m in JudicialReview] == ["none", "weak", "strong"]
    assert [m.value for m in AmendmentDifficulty] == [
        "simple_majority",
        "supermajority",
        "entrenched",
    ]
    assert [m.value for m in DecreeAuthority] == ["none", "emergency_only", "unlimited"]


# --- the module exports no legitimacy surface (R1, structural half) ----------


def test_constitution_module_exports_no_legitimacy_or_scoring_surface() -> None:
    """R1: constitutional form must not be able to influence legitimacy. The strongest structural
    guarantee is that this module has nothing to offer such a calculation — no score, no weight, no
    anchor, no rating."""
    import app.simulation.constitution as constitution_module

    forbidden = ("anchor", "score", "weight", "rating", "legitimacy", "support")
    offenders = [
        name
        for name in dir(constitution_module)
        if not name.startswith("_") and any(word in name.lower() for word in forbidden)
    ]
    assert offenders == []


def test_term_limit_and_election_interval_reject_zero() -> None:
    """`None` means absent; zero would be a nonsensical limit masquerading as one."""
    with pytest.raises(ValidationError):
        _constitution(executive_term_limit_terms=0)
    with pytest.raises(ValidationError):
        _constitution(national_election_interval_turns=0)
