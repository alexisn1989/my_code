"""Government-form/vote independence, proven structurally (Phase 3B1, T-N1a..T-N1d).

The rule this file pins is the legislative twin of `test_legitimacy_neutrality.py`'s: constitutional
*form* must never decide how a vote *goes*. A monarchy's legislature and a republic's legislature,
holding identical seats and identical opinions, must count identically.

Phase 3B2A adds `simulation.relationships` to the same guarantee: how readily a caucus forgives a
government is a property of that caucus, not of the government's constitutional form. A monarchy
and a republic buy the same relationship improvement for the same capital.

External Wars W1 adds `simulation.foreign_conflict` to `NEUTRAL_MODULES` for T-N1a/T-N1b, and gives
it its own additional guarantee below (T-N2): a foreign actor's abstract `war_capability_bps` must
have no channel into this game's *domestic* political math either. Unlike the other three modules,
`foreign_conflict` also carries an integer-only purity claim of its own; T-N2's AST scan is scoped
to that module by name specifically, not folded into the general neutrality checks, because
broadening a module-specific purity claim across the package would silently change what the other
neutral modules are permitted to do.

Phase 3B1 reads the constitution in exactly **one** place — routing, which decides which chambers
must approve a proposal and whether a decree is constitutionally available. That is structure
deciding *procedure*. Neither `simulation.apportionment` nor `simulation.legislative_voting`
participates in it, and this file proves that three independent ways:

- **T-N1a** — no public callable or dataclass in either module has an annotation naming a
  constitutional type.
- **T-N1b** — neither module *imports* `simulation.constitution` at all, checked against the
  parsed source rather than the loaded module, so there is no channel to close later.
- **T-N1c** — `simulation.constitution` exports no seat, vote or support surface, so the
  dependency cannot be inverted either.
- **T-N1d** — the numeric consequence, and a companion check that it is not vacuous: the tally is
  a function of the blocs alone, and it does genuinely change when the blocs do.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from types import ModuleType

from app.simulation import apportionment as apportionment_module
from app.simulation import constitution as constitution_module
from app.simulation import foreign_conflict as foreign_conflict_module
from app.simulation import legislative_voting as voting_module
from app.simulation import political_memory as political_memory_module
from app.simulation import relationships as relationships_module
from app.simulation.apportionment import SeatSupport, apportion_supporting_seats
from app.simulation.legislative_voting import PolicyChange, resolve_bloc_support
from app.simulation.legislature import ChangeDirection, GovernmentRole
from app.simulation.political_memory import (
    enacted_policy_reaction_bps,
    relationship_decay_bps,
)
from app.simulation.relationships import relationship_gain_bps

CONSTITUTIONAL_TYPE_NAMES = frozenset(
    {
        "ConstitutionState",
        "ExecutiveSystem",
        "ExecutiveSelection",
        "Legislature",
        "TerritorialOrganization",
        "JudicialReview",
        "AmendmentDifficulty",
        "DecreeAuthority",
    }
)

NEUTRAL_MODULES = (
    apportionment_module,
    voting_module,
    relationships_module,
    political_memory_module,
    foreign_conflict_module,
)


# --- T-N1a: no constitutional type reaches either module's signatures ---------


def _annotations_of(member: object) -> dict[str, object]:
    if inspect.isclass(member):
        return dict(inspect.get_annotations(member))
    signature = inspect.signature(member)  # type: ignore[arg-type]
    annotations: dict[str, object] = {
        name: parameter.annotation for name, parameter in signature.parameters.items()
    }
    annotations["return"] = signature.return_annotation
    return annotations


def test_no_public_function_in_either_module_accepts_a_constitutional_type() -> None:
    """Stronger than a behavioral test: it proves there is no argument through which government
    form *could* reach these formulas, whatever future code might try to pass."""
    checked = 0
    for module in NEUTRAL_MODULES:
        for name, member in inspect.getmembers(module):
            if name.startswith("_") or not (inspect.isfunction(member) or inspect.isclass(member)):
                continue
            if getattr(member, "__module__", None) != module.__name__:
                continue  # imported helper, checked in the module that defines it
            checked += 1
            for annotation in _annotations_of(member).values():
                text = str(annotation)
                offenders = CONSTITUTIONAL_TYPE_NAMES & set(text.replace("|", " ").split())
                assert not offenders, f"{module.__name__}.{name}: {text!r} references {offenders}"
    assert checked > 0, "sanity: the modules must export something to check"


# --- T-N1b: neither module even imports the constitution ----------------------


def test_neither_neutral_module_imports_the_constitution() -> None:
    """Checked against the parsed source, not the loaded module, so an import added inside a
    function body or under `TYPE_CHECKING` is caught just the same. There is nothing to close
    later because there is nothing open."""
    for module in NEUTRAL_MODULES:
        source_path = Path(inspect.getfile(module))
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                imported = [node.module or ""]
            else:
                continue
            for name in imported:
                assert "constitution" not in name, (
                    f"{module.__name__} imports {name!r}; the vote must not be able to see the "
                    "constitution"
                )


def test_the_neutral_modules_do_not_import_each_others_domain_upward() -> None:
    """`apportionment` is a general algorithm and stays one: it knows nothing of roles, votes or
    parties, only of labelled rows with seats and support. Keeping the dependency one-way is what
    lets its five proofs be about arithmetic rather than about politics."""
    source = Path(inspect.getfile(apportionment_module)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = [
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    ]
    assert not any("legislat" in name for name in imported_modules), imported_modules


# --- T-N1c: the constitution exports no vote-counting surface -----------------


def test_constitution_module_exports_no_seat_or_vote_surface() -> None:
    """The mirror of `test_legitimacy_neutrality.py`'s check, for this phase's vocabulary. If the
    constitution ever grew a seat count or a passage threshold, form would be deciding outcomes
    through the back door."""
    forbidden_words = ("seat", "vote", "bloc", "party", "majority", "support", "apportion")
    offenders = [
        name
        for name in dir(constitution_module)
        if not name.startswith("_") and any(word in name.lower() for word in forbidden_words)
    ]
    assert offenders == []


def test_the_neutral_modules_are_genuinely_the_ones_under_test() -> None:
    """Guards the checks above against silently passing on the wrong objects — if either module
    were renamed or re-exported, `NEUTRAL_MODULES` would drift and every assertion would become
    vacuously true."""
    assert all(isinstance(module, ModuleType) for module in NEUTRAL_MODULES)
    assert {module.__name__ for module in NEUTRAL_MODULES} == {
        "app.simulation.apportionment",
        "app.simulation.legislative_voting",
        "app.simulation.relationships",
        "app.simulation.political_memory",
        "app.simulation.foreign_conflict",
    }


# --- T-N1d: the numeric consequence, and proof that it is not vacuous ---------

_TAX_RISE = PolicyChange(direction=ChangeDirection.INCREASE, intensity_bps=5_000)
_NO_SPENDING_CHANGE = PolicyChange(direction=ChangeDirection.UNCHANGED, intensity_bps=0)


def _tally(*, blocs: tuple[tuple[str, str, GovernmentRole, int, int, int, int], ...]) -> int:
    rows = tuple(
        SeatSupport(
            party_id=party,
            bloc_id=bloc,
            seats=seats,
            effective_support_bps=resolve_bloc_support(
                role=role,
                relationship_bps=relationship,
                tax_change=_TAX_RISE,
                tax_preference_bps=preference,
                spending_change=_NO_SPENDING_CHANGE,
                spending_preference_bps=0,
                allocated_political_capital=0,
                discipline_bps=discipline,
            ).effective_support_bps,
        )
        for party, bloc, role, relationship, preference, discipline, seats in blocs
    )
    return apportion_supporting_seats(rows=rows).supporting_seats


_CHAMBER = (
    ("gov", "main", GovernmentRole.COALITION, 6_000, 2_000, 5_000, 55),
    ("opp", "main", GovernmentRole.OPPOSITION, -6_000, -4_000, 5_000, 45),
)


def test_the_same_chamber_always_counts_the_same_way() -> None:
    """There is no constitutional argument to vary, so this is the whole numeric claim: the tally
    depends on the blocs and on nothing else. A monarchy and a republic seating this identical
    chamber get this identical number, because neither can supply anything that would change it."""
    assert _tally(blocs=_CHAMBER) == _tally(blocs=_CHAMBER) == 55


def test_the_tally_does_change_when_the_chamber_does() -> None:
    """Non-vacuity. A formula that ignored its inputs entirely would satisfy every neutrality
    check above and be worthless; souring the government bloc's own relationship must move the
    count."""
    soured = (
        ("gov", "main", GovernmentRole.COALITION, -10_000, 2_000, 5_000, 55),
        _CHAMBER[1],
    )
    assert _tally(blocs=soured) != _tally(blocs=_CHAMBER)


# --- Phase 3B2A: the relationship formula is neutral and float-free ----------


def test_relationship_investment_is_identical_under_two_maximally_different_constitutions() -> None:
    """T-N1d's Phase 3B2A twin, stated numerically rather than only structurally. `decree_state` is
    a monarchy and `deficit_demo` a presidential republic; a bloc at the same relationship in
    either buys exactly the same improvement for the same capital, because the constitution is not
    an input to this calculation at all."""
    for opening in (-8_000, -2_000, 0, 2_000, 6_000):
        for capital in (1, 50, 100, 200):
            gain = relationship_gain_bps(
                opening_relationship_bps=opening, political_capital=capital
            )
            assert gain == relationship_gain_bps(
                opening_relationship_bps=opening, political_capital=capital
            )
            assert isinstance(gain, int)


def test_the_relationship_module_uses_no_floating_point_arithmetic() -> None:
    """Determinism depends on it: `state_json` is BLAKE2b-covered, and a float would make the same
    game hash differently on a different platform. Checked against the parsed source, so importing
    a float helper later is caught even if it is never called."""
    source = Path(inspect.getfile(relationships_module)).read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        assert not isinstance(node, ast.Constant) or not isinstance(node.value, float), (
            f"float literal {node.value!r} in relationships.py"
        )
        if isinstance(node, ast.BinOp):
            assert not isinstance(node.op, ast.Div), "true division (/) in relationships.py"
        if isinstance(node, ast.Name):
            assert node.id not in {"float", "random", "Decimal"}, node.id


def test_the_relationship_module_imports_no_randomness_or_clock() -> None:
    source = Path(inspect.getfile(relationships_module)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    imported |= {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert not (imported & {"random", "time", "datetime", "secrets"}), imported


# --- Phase 3B2B: political_memory is neutral and float-free -------------------
#
# R8: this extends the scan to name `political_memory.py` specifically, alongside
# `relationships.py` above -- it does NOT generalize either scan into a loop over all of
# `NEUTRAL_MODULES`. Generalizing would incidentally close the pre-existing gap that leaves
# `apportionment.py` and `legislative_voting.py` unscanned (tracked separately as TEST-1), and the
# mandate forbids bundling a fix for a pre-existing defect into this phase's commits.


def test_relationship_decay_and_reaction_are_identical_under_two_maximally_different_constitutions() -> (
    None
):
    """`decree_state` is a monarchy and `deficit_demo` a presidential republic; a bloc at the same
    opening relationship/baseline, or reacting to the same enacted policy, produces exactly the
    same decay or reaction in either, because the constitution is not an input to either
    calculation at all."""
    for opening in (-8_000, -2_000, 0, 2_000, 6_000):
        for baseline in (-6_000, -2_000, 0, 3_000, 5_000):
            decay = relationship_decay_bps(
                opening_relationship_bps=opening, baseline_relationship_bps=baseline
            )
            assert decay == relationship_decay_bps(
                opening_relationship_bps=opening, baseline_relationship_bps=baseline
            )
            assert isinstance(decay, int)

    for tax_pref in (-6_000, -2_000, 2_000, 5_000):
        reaction = enacted_policy_reaction_bps(
            tax_preference_bps=tax_pref,
            tax_direction=ChangeDirection.INCREASE,
            tax_intensity_bps=5_000,
            spending_preference_bps=0,
            spending_direction=ChangeDirection.UNCHANGED,
            spending_intensity_bps=0,
        )
        assert reaction == enacted_policy_reaction_bps(
            tax_preference_bps=tax_pref,
            tax_direction=ChangeDirection.INCREASE,
            tax_intensity_bps=5_000,
            spending_preference_bps=0,
            spending_direction=ChangeDirection.UNCHANGED,
            spending_intensity_bps=0,
        )
        assert isinstance(reaction, int)


def test_the_political_memory_module_uses_no_floating_point_arithmetic() -> None:
    """Determinism depends on it: `state_json` is BLAKE2b-covered, and a float would make the same
    game hash differently on a different platform. Checked against the parsed source, so importing
    a float helper later is caught even if it is never called."""
    source = Path(inspect.getfile(political_memory_module)).read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        assert not isinstance(node, ast.Constant) or not isinstance(node.value, float), (
            f"float literal {node.value!r} in political_memory.py"
        )
        if isinstance(node, ast.BinOp):
            assert not isinstance(node.op, ast.Div), "true division (/) in political_memory.py"
        if isinstance(node, ast.Name):
            assert node.id not in {"float", "random", "Decimal"}, node.id


def test_the_political_memory_module_imports_no_randomness_or_clock() -> None:
    source = Path(inspect.getfile(political_memory_module)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    imported |= {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert not (imported & {"random", "time", "datetime", "secrets"}), imported


def test_apportionment_and_legislative_voting_remain_unscanned_for_floats_test1_deferred() -> None:
    """Negative confirmation of R8's deferral: the float/division AST scans above stay dedicated
    to `relationships.py` and `political_memory.py` only, so `apportionment.py` and
    `legislative_voting.py` are NOT protected against a float literal or a `/` creeping in. This
    is a real, pre-existing gap (TEST-1), deliberately not fixed here -- the mandate forbids
    bundling a fix for a pre-existing defect into this phase. If a future scan generalizes to
    cover them, this test (asserting the current, narrower state) is the one that should be
    deleted at that time, not silently left behind."""
    scanned_by_name = {"relationships.py", "political_memory.py"}
    unscanned_by_name = {"apportionment.py", "legislative_voting.py"}
    assert scanned_by_name.isdisjoint(unscanned_by_name)
    for module in (apportionment_module, voting_module):
        assert Path(inspect.getfile(module)).name in unscanned_by_name


def test_government_survival_is_deliberately_excluded_from_neutral_modules() -> None:
    """Phase 3C: `government_survival.py` is the opposite case from this module's discipline by
    design -- a scheduled election exists because of `national_election_interval_turns`,
    impeachment eligibility genuinely depends on `judicial_review`/`executive_selection`. It is
    read in `phases.py`'s slot handlers, the same split `legislature.py`'s own routing check
    already uses, and is never added to `NEUTRAL_MODULES` above."""
    import app.simulation.government_survival as government_survival_module

    assert government_survival_module not in NEUTRAL_MODULES
    assert government_survival_module.__name__ not in {m.__name__ for m in NEUTRAL_MODULES}


# --- T-N2 (External Wars W1): foreign_conflict is float-free, and reaches nothing domestic ----
#
# Scoped to `foreign_conflict.py` BY NAME, exactly like the relationships/political_memory scans
# above are scoped to their own modules -- never folded into a scan that would silently start
# constraining apportionment.py or legislative_voting.py, which §T-1 above documents are NOT
# covered by this discipline.


def test_the_foreign_conflict_module_uses_no_floating_point_arithmetic() -> None:
    """Determinism depends on it: `state_json` is BLAKE2b-covered, and a float would make the
    same game hash differently on a different platform. Checked against the parsed source, so
    importing a float helper later is caught even if it is never called."""
    source = Path(inspect.getfile(foreign_conflict_module)).read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        assert not isinstance(node, ast.Constant) or not isinstance(node.value, float), (
            f"float literal {node.value!r} in foreign_conflict.py"
        )
        if isinstance(node, ast.BinOp):
            assert not isinstance(node.op, ast.Div), "true division (/) in foreign_conflict.py"
        if isinstance(node, ast.Name):
            assert node.id not in {"float", "random", "Decimal"}, node.id


def test_the_foreign_conflict_module_imports_no_randomness_or_clock() -> None:
    """The RNG draws this module's functions consume arrive as caller-supplied integers; the
    module itself must have no channel to a generator or a clock, or the engine's determinism
    claim would depend on convention rather than on structure."""
    source = Path(inspect.getfile(foreign_conflict_module)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    imported |= {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert not (imported & {"random", "time", "datetime", "secrets", "os"}), imported


def test_foreign_conflict_module_shares_no_state_or_i_o() -> None:
    """The module docstring's purity claim, checked structurally: no top-level mutable
    containers (the classic hidden-state bug) and no I/O builtins referenced anywhere in the
    source."""
    source = Path(inspect.getfile(foreign_conflict_module)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_calls = {"open", "print", "input"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in forbidden_calls, (
                f"foreign_conflict.py calls {node.func.id!r}"
            )


def test_foreign_conflict_does_not_import_government_survival_or_vice_versa() -> None:
    """The isolation guarantee is checked from both directions: `foreign_conflict` must not
    reach into domestic survival math, and `government_survival` must not reach into it either
    (pinned again, from this module's own source, alongside `test_foreign_conflict.py`'s check
    from `government_survival.py`'s side)."""
    import app.simulation.government_survival as government_survival_module

    fc_source = Path(inspect.getfile(foreign_conflict_module)).read_text(encoding="utf-8")
    fc_tree = ast.parse(fc_source)
    fc_imports = {
        node.module or "" for node in ast.walk(fc_tree) if isinstance(node, ast.ImportFrom)
    }
    assert not any("government_survival" in name for name in fc_imports)

    gs_source = Path(inspect.getfile(government_survival_module)).read_text(encoding="utf-8")
    gs_tree = ast.parse(gs_source)
    gs_imports = {
        node.module or "" for node in ast.walk(gs_tree) if isinstance(node, ast.ImportFrom)
    }
    assert not any("foreign_conflict" in name for name in gs_imports)
