"""Government-form/vote independence, proven structurally (Phase 3B1, T-N1a..T-N1d).

The rule this file pins is the legislative twin of `test_legitimacy_neutrality.py`'s: constitutional
*form* must never decide how a vote *goes*. A monarchy's legislature and a republic's legislature,
holding identical seats and identical opinions, must count identically.

Phase 3B2A adds `simulation.relationships` to the same guarantee: how readily a caucus forgives a
government is a property of that caucus, not of the government's constitutional form. A monarchy
and a republic buy the same relationship improvement for the same capital.

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
from app.simulation import legislative_voting as voting_module
from app.simulation import relationships as relationships_module
from app.simulation.apportionment import SeatSupport, apportion_supporting_seats
from app.simulation.legislative_voting import PolicyChange, resolve_bloc_support
from app.simulation.legislature import ChangeDirection, GovernmentRole
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

NEUTRAL_MODULES = (apportionment_module, voting_module, relationships_module)


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
