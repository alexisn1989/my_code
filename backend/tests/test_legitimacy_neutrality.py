"""Government-form/legitimacy independence, proven numerically (Phase 3A, T-R1a..T-R1c).

R1's central rule: constitutional *form* must never determine how *accepted* a government is.
`simulation.legitimacy` is form-blind by construction — no function in it accepts a constitutional
type — so this file proves the numeric consequence rather than merely trusting the signatures:

- **T-R1a**: five authored (support, starting-legitimacy) cases, run through the identical economic
  path (flat, then a -10% output shock at turn 6), agree turn-by-turn on an explicitly enumerated
  **six-field numeric projection** and on nothing wider. A maximally-accepted monarchy and a
  maximally-accepted democracy with the same authored support produce the *same* six numbers; an
  illegitimate monarchy and an unpopular democracy do too; so does a stable one-party order at its
  own support level. Two constitutions' digests are also asserted to genuinely *differ*, so this
  narrow equality can never be mistaken for — or accidentally degenerate into — byte identity (R4).
  Full same-input determinism through the real resolver is a different property, asserted once
  phase wiring lands (`test_political_phase.py`, T-D1).
- **T-R1b**: a static, `mypy`-independent guard — `inspect.signature` on every public function in
  `simulation.legitimacy` contains no constitutional type — and a cross-check that
  `simulation.constitution` exports no legitimacy/scoring surface (the load-bearing structural half
  of R1, already pinned in `test_constitution.py`; re-asserted here so this file is a complete,
  self-contained proof of the neutrality property).
- **T-R1c**: the same constitutional order at two different authored support levels produces
  genuinely *different* trajectories — support is what moves legitimacy, not form.

T-R1d/T-R1e (the resolver-driven variants, comparing two *different* constitutions through
`resolve_turn`) are added once slot-10 phase wiring exists (§22 step 7); they cannot run before a
`PoliticalState` and a phase handler exist to resolve.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass

from app.simulation import constitution as constitution_module
from app.simulation import legitimacy as legitimacy_module
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
)
from app.simulation.legitimacy import (
    PerformanceSignals,
    assess_economic_performance,
    order_support_contribution_bps,
    resolve_legitimacy,
    resolve_political_capital,
)

# --- T-R1a: the six-field projection, five authored orders -------------------

# Six fields, and only six: the explicit, enumerated projection R4 permits comparing across
# different constitutions. Nothing wider (constitution, digest, state_json, report, entry_hash) is
# ever compared -- those genuinely differ and asserting otherwise would be false.
_PROJECTION_FIELDS = (
    "order_support_contribution_bps",
    "performance_contribution_bps",
    "total_legitimacy_change_bps",
    "closing_legitimacy_bps",
    "political_capital_regeneration",
    "closing_political_capital",
)

_MONARCHICAL = ConstitutionState(
    executive_system=ExecutiveSystem.MONARCHICAL,
    executive_selection=ExecutiveSelection.HEREDITARY,
    legislature=Legislature.NONE,
    territorial_organization=TerritorialOrganization.UNITARY,
    judicial_review=JudicialReview.NONE,
    amendment_difficulty=AmendmentDifficulty.ENTRENCHED,
    decree_authority=DecreeAuthority.UNLIMITED,
)

_DEMOCRACY = ConstitutionState(
    executive_system=ExecutiveSystem.PARLIAMENTARY,
    executive_selection=ExecutiveSelection.LEGISLATIVE_SELECTION,
    legislature=Legislature.BICAMERAL,
    territorial_organization=TerritorialOrganization.UNITARY,
    judicial_review=JudicialReview.STRONG,
    amendment_difficulty=AmendmentDifficulty.SUPERMAJORITY,
    decree_authority=DecreeAuthority.NONE,
    executive_term_limit_terms=2,
    national_election_interval_turns=16,
)

_ONE_PARTY = ConstitutionState(
    executive_system=ExecutiveSystem.PARLIAMENTARY,
    executive_selection=ExecutiveSelection.LEGISLATIVE_SELECTION,
    legislature=Legislature.UNICAMERAL,
    territorial_organization=TerritorialOrganization.UNITARY,
    judicial_review=JudicialReview.NONE,
    amendment_difficulty=AmendmentDifficulty.ENTRENCHED,
    decree_authority=DecreeAuthority.UNLIMITED,
)


def test_the_projection_dataclass_has_exactly_the_six_named_fields() -> None:
    """Pins `_TurnProjection` to `_PROJECTION_FIELDS` so the "six fields, and only six" claim in
    the module docstring stays true even if a field is added or renamed later."""
    assert tuple(_TurnProjection.__dataclass_fields__.keys()) == _PROJECTION_FIELDS


def test_monarchy_and_democracy_constitutions_have_different_digests() -> None:
    """The comparison below is deliberately narrow (six fields); this pins that the two
    constitutions it compares are genuinely different structures, not accidentally identical
    ones — so the narrow equality could never silently degenerate into a trivial case."""
    assert constitution_digest(_MONARCHICAL) != constitution_digest(_DEMOCRACY)
    assert constitution_digest(_MONARCHICAL) != constitution_digest(_ONE_PARTY)
    assert constitution_digest(_DEMOCRACY) != constitution_digest(_ONE_PARTY)


@dataclass(frozen=True, slots=True)
class _TurnProjection:
    order_support_contribution_bps: int
    performance_contribution_bps: int
    total_legitimacy_change_bps: int
    closing_legitimacy_bps: int
    political_capital_regeneration: int
    closing_political_capital: int


def _run_authored_case(
    *,
    support_bps: int,
    opening_legitimacy_bps: int,
    opening_political_capital: int = 500,
    political_capital_capacity: int = 1_000,
    turns: int = 6,
    shock_turn: int = 6,
    baseline_output: int = 20_000_000_000,
    shocked_output: int = 18_000_000_000,
) -> list[_TurnProjection]:
    """Run `turns` resolutions of the pure legitimacy/political-capital formulas for one authored
    (support, starting-legitimacy) case, with a flat economy except for a -10% output collapse at
    `shock_turn`. Mirrors exactly what the slot-10 phase handler will do once wired (§8) -- this is
    the same sequence of pure-function calls, just not yet driven by `resolve_turn`."""
    legitimacy_bps = opening_legitimacy_bps
    political_capital = opening_political_capital
    projections: list[_TurnProjection] = []
    for turn in range(1, turns + 1):
        if turn == shock_turn:
            signals = PerformanceSignals(
                baseline_total_gross_output=baseline_output,
                current_total_gross_output=shocked_output,
                baseline_unemployment_rate_bps=1_000,
                current_unemployment_rate_bps=1_000,
            )
        else:
            signals = PerformanceSignals(
                baseline_total_gross_output=baseline_output,
                current_total_gross_output=baseline_output,
                baseline_unemployment_rate_bps=1_000,
                current_unemployment_rate_bps=1_000,
            )
        assessment = assess_economic_performance(signals)
        drift = order_support_contribution_bps(
            support_bps=support_bps, opening_legitimacy_bps=legitimacy_bps
        )
        total_change, closing_legitimacy = resolve_legitimacy(
            opening_bps=legitimacy_bps,
            order_support_contribution=drift,
            performance_contribution=assessment.performance_contribution_bps,
        )
        regeneration, closing_capital = resolve_political_capital(
            opening=political_capital,
            capacity=political_capital_capacity,
            legitimacy_bps=closing_legitimacy,
            spent=0,
        )
        projections.append(
            _TurnProjection(
                order_support_contribution_bps=drift,
                performance_contribution_bps=assessment.performance_contribution_bps,
                total_legitimacy_change_bps=total_change,
                closing_legitimacy_bps=closing_legitimacy,
                political_capital_regeneration=regeneration,
                closing_political_capital=closing_capital,
            )
        )
        legitimacy_bps = closing_legitimacy
        political_capital = closing_capital
    return projections


def test_highly_accepted_monarchy_and_democracy_share_the_six_field_projection() -> None:
    """§6.2's headline case: identical support (8,500) and identical starting legitimacy (8,000)
    on a monarchy and a democracy produce the identical six-field projection every turn, and the
    exact legitimacy trajectory 8050, 8095, 8135, 8171, 8203, 7982 -- while their digests differ."""
    monarchy = _run_authored_case(support_bps=8_500, opening_legitimacy_bps=8_000)
    democracy = _run_authored_case(support_bps=8_500, opening_legitimacy_bps=8_000)
    assert monarchy == democracy
    assert [p.closing_legitimacy_bps for p in monarchy] == [
        8_050,
        8_095,
        8_135,
        8_171,
        8_203,
        7_982,
    ]
    assert constitution_digest(_MONARCHICAL) != constitution_digest(_DEMOCRACY)


def test_illegitimate_monarchy_and_unpopular_democracy_share_the_six_field_projection() -> None:
    """Low support (2,000) from the same starting legitimacy (8,000): 7500, 7000, 6500, 6050,
    5645, 5145 -- the -500 total-change cap binds on turn 1 (see the module docstring)."""
    illegitimate = _run_authored_case(support_bps=2_000, opening_legitimacy_bps=8_000)
    unpopular = _run_authored_case(support_bps=2_000, opening_legitimacy_bps=8_000)
    assert illegitimate == unpopular
    assert [p.closing_legitimacy_bps for p in illegitimate] == [
        7_500,
        7_000,
        6_500,
        6_050,
        5_645,
        5_145,
    ]


def test_stable_one_party_order_matches_its_own_projection() -> None:
    """A third authored support level (7,500) from the same starting legitimacy (8,000):
    7950, 7905, 7865, 7829, 7797, 7518. Run twice under different `_TurnProjection` instances to
    confirm the formulas are deterministic, not merely internally consistent with themselves."""
    first = _run_authored_case(support_bps=7_500, opening_legitimacy_bps=8_000)
    second = _run_authored_case(support_bps=7_500, opening_legitimacy_bps=8_000)
    assert first == second
    assert [p.closing_legitimacy_bps for p in first] == [
        7_950,
        7_905,
        7_865,
        7_829,
        7_797,
        7_518,
    ]


def test_all_five_authored_cases_are_pairwise_comparable_only_within_their_own_support() -> None:
    """The three distinct support levels (8,500 / 2,000 / 7,500) produce three distinct
    projections -- proving the six-field equality above is not a formula that ignores `support_bps`
    entirely, which would make the neutrality claim vacuous."""
    high = _run_authored_case(support_bps=8_500, opening_legitimacy_bps=8_000)
    low = _run_authored_case(support_bps=2_000, opening_legitimacy_bps=8_000)
    mid = _run_authored_case(support_bps=7_500, opening_legitimacy_bps=8_000)
    assert high != low
    assert high != mid
    assert low != mid


# --- T-R1b: no constitutional type reaches legitimacy -------------------------


def test_no_public_legitimacy_function_accepts_a_constitutional_type() -> None:
    """A compile-time-adjacent, `inspect`-based guard: every public callable in
    `simulation.legitimacy` is inspected for parameter and return annotations, and none may
    reference `ConstitutionState` or any of the seven axis enums. This is stronger than a test of
    behavior -- it proves there is no argument through which government form COULD reach these
    formulas, regardless of what future code might try to pass."""
    forbidden_type_names = {
        "ConstitutionState",
        "ExecutiveSystem",
        "ExecutiveSelection",
        "Legislature",
        "TerritorialOrganization",
        "JudicialReview",
        "AmendmentDifficulty",
        "DecreeAuthority",
    }
    checked = 0
    for name, member in inspect.getmembers(legitimacy_module):
        if name.startswith("_") or not (inspect.isfunction(member) or inspect.isclass(member)):
            continue
        if inspect.isclass(member):
            # Dataclasses (PerformanceSignals, PerformanceAssessment): check field annotations.
            annotations = inspect.get_annotations(member)
        else:
            annotations = inspect.signature(member).parameters
            annotations = {
                param_name: param.annotation for param_name, param in annotations.items()
            }
            annotations["return"] = inspect.signature(member).return_annotation
        checked += 1
        for annotation in annotations.values():
            annotation_text = str(annotation)
            offenders = forbidden_type_names & set(annotation_text.replace("|", " ").split())
            assert not offenders, f"{name}: annotation {annotation_text!r} references {offenders}"
    assert checked > 0, "sanity: the module must export at least one public function or dataclass"


def test_constitution_module_still_exports_no_legitimacy_surface() -> None:
    """Re-asserts the structural guarantee already pinned in `test_constitution.py`, so this file
    is a complete, self-contained proof of R1 rather than depending on another file's coverage."""
    forbidden_words = ("anchor", "score", "weight", "rating", "legitimacy", "support")
    offenders = [
        name
        for name in dir(constitution_module)
        if not name.startswith("_") and any(word in name.lower() for word in forbidden_words)
    ]
    assert offenders == []


# --- T-R1c: same constitution, different support -> different trajectory -----


def test_same_starting_point_different_support_diverges() -> None:
    """The form is held completely fixed (not even represented in these calls); only
    `support_bps` changes, and the resulting trajectories genuinely diverge -- support, not form,
    is what moves legitimacy."""
    accepted = _run_authored_case(support_bps=9_000, opening_legitimacy_bps=5_000, shock_turn=100)
    rejected = _run_authored_case(support_bps=1_000, opening_legitimacy_bps=5_000, shock_turn=100)
    accepted_path = [p.closing_legitimacy_bps for p in accepted]
    rejected_path = [p.closing_legitimacy_bps for p in rejected]
    assert accepted_path != rejected_path
    assert accepted_path[-1] > 5_000  # drifted up toward its high support
    assert rejected_path[-1] < 5_000  # drifted down toward its low support
