"""Asking a foreign counterpart for a bounded assistance grant.

Four claims, and they are what this file is organised around.

* **The foreign minister is finally worth something.** Until this slice the post existed and
  nothing read it: `FOREIGN_MINISTER` appeared exactly once outside its own enum. Here the same
  counterpart, approached by the same country on the same turn, gives measurably more to a
  government with a competent diplomat in post than to one with a vacant chair -- and a minister
  appointed in the very same decision set contributes nothing, because the effectivity rule has
  one definition and this reads it.
* **Aid is an external transfer, not revenue and not a smaller deficit.**
  `pre_financing_balance` keeps its exact three-term meaning; the grant enters at the financing
  step, where what it actually does -- reduce borrowing or raise closing cash -- is what it is
  recorded as doing.
* **The pool is finite and the refusals are distinct.** A hostile counterpart and an exhausted one
  both give nothing and are completely different political facts; collapsing them would hide the
  only one of the two a player can act on.
* **Group 59 is an independent oracle.** It transcribes the share formula rather than calling the
  production assessment, and an AST allowlist keeps it that way.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.api.decision_preflight import first_decision_problem
from app.api.preview import preview_decisions
from app.api.projections import build_decision_options
from app.cli import REASON_RENDERERS, render_entry
from app.content.scenarios import load_scenario_file
from app.core.errors import TurnResolutionError
from app.core.money import BPS_DENOMINATOR
from app.core.politics import trunc_div_toward_zero
from app.simulation.decisions import (
    CabinetDecision,
    CabinetOrder,
    DecisionSet,
    ForeignAssistanceDecision,
)
from app.simulation.foreign_assistance import (
    FOREIGN_ASSISTANCE_BASE_SHARE_BPS,
    FOREIGN_ASSISTANCE_STANDING_SHARE_MAX_BPS,
    FOREIGN_ASSISTANCE_TRUST_SHARE_MAX_BPS,
    FOREIGN_MINISTER_ASSISTANCE_SHARE_MAX_BPS,
    MINIMUM_ASSISTANCE_STANDING_BPS,
    ForeignAssistanceAssessment,
    ForeignAssistanceRefusal,
    assess_foreign_assistance,
    assistance_share_bps,
    remaining_pool,
)
from app.simulation.history import advance_game, new_game, validate_history
from app.simulation.invariants import check_invariants
from app.simulation.reconciliation import reconcile_foreign_affairs_report
from app.simulation.report import FinanceReport
from app.simulation.resolver import resolve_turn
from app.simulation.save_format import SAVE_FORMAT_VERSION
from app.simulation.state import RULESET_VERSION
from tests.conftest import SCENARIO_DIR

_ASSISTANCE_MODULE = Path("app/simulation/foreign_assistance.py")
_RECONCILIATION_MODULE = Path("app/simulation/reconciliation.py")

_FIXTURE = Path(__file__).parent / "fixtures" / "assistance_save_ruleset_0.20.0.json"
"""The authentic ruleset-0.20.0 save frozen in commit 5a, from the engine as it stood BEFORE this
mechanic existed. Never regenerated: a fixture reproduced under the current engine would make the
compatibility proofs pass for the wrong reason."""


def _state(name: str):  # type: ignore[no-untyped-def]
    return load_scenario_file(SCENARIO_DIR / f"{name}.yaml")


def _resolve(state, *decisions):  # type: ignore[no-untyped-def]
    return resolve_turn(
        state,
        DecisionSet(
            expected_turn=state.turn,
            expected_state_version=state.state_version,
            decisions=tuple(sorted(decisions, key=lambda d: d.kind)),
        ),
    )


def _ask(profile_id: str) -> ForeignAssistanceDecision:
    return ForeignAssistanceDecision(profile_id=profile_id)


# --------------------------------------------------------------------------------------------
# The pure module.
# --------------------------------------------------------------------------------------------


class TestTheShareFormula:
    def test_the_base_share_is_what_a_bare_request_draws(self) -> None:
        assert (
            assistance_share_bps(
                personal_trust_bps=0,
                standing_bps=0,
                foreign_minister_competence_bps=0,
                independence_bps=0,
            )
            == FOREIGN_ASSISTANCE_BASE_SHARE_BPS
        )

    def test_every_term_moves_the_share_in_its_declared_direction(self) -> None:
        base = assistance_share_bps(
            personal_trust_bps=0,
            standing_bps=0,
            foreign_minister_competence_bps=0,
            independence_bps=0,
        )
        raises = {
            "trust": assistance_share_bps(
                personal_trust_bps=BPS_DENOMINATOR,
                standing_bps=0,
                foreign_minister_competence_bps=0,
                independence_bps=0,
            ),
            "standing": assistance_share_bps(
                personal_trust_bps=0,
                standing_bps=BPS_DENOMINATOR,
                foreign_minister_competence_bps=0,
                independence_bps=0,
            ),
            "minister": assistance_share_bps(
                personal_trust_bps=0,
                standing_bps=0,
                foreign_minister_competence_bps=BPS_DENOMINATOR,
                independence_bps=0,
            ),
        }
        for term, value in raises.items():
            assert value > base, term
        assert (
            assistance_share_bps(
                personal_trust_bps=0,
                standing_bps=0,
                foreign_minister_competence_bps=0,
                independence_bps=BPS_DENOMINATOR,
            )
            < base
        )

    def test_the_minister_term_is_smaller_than_trust_and_standing(self) -> None:
        """A good diplomat improves terms; they do not substitute for a relationship."""
        assert FOREIGN_MINISTER_ASSISTANCE_SHARE_MAX_BPS < FOREIGN_ASSISTANCE_TRUST_SHARE_MAX_BPS
        assert FOREIGN_MINISTER_ASSISTANCE_SHARE_MAX_BPS < FOREIGN_ASSISTANCE_STANDING_SHARE_MAX_BPS

    def test_a_negative_standing_subtracts_and_the_share_floors_at_one(self) -> None:
        """The sign is exactly what `//` would get wrong on a negative operand, which is why the
        formula uses `trunc_div_toward_zero` throughout."""
        cool = assistance_share_bps(
            personal_trust_bps=0,
            standing_bps=-3_000,
            foreign_minister_competence_bps=0,
            independence_bps=0,
        )
        assert cool < FOREIGN_ASSISTANCE_BASE_SHARE_BPS
        floored = assistance_share_bps(
            personal_trust_bps=0,
            standing_bps=MINIMUM_ASSISTANCE_STANDING_BPS,
            foreign_minister_competence_bps=0,
            independence_bps=BPS_DENOMINATOR,
        )
        assert floored == 1

    def test_the_share_is_integral_across_a_sweep(self) -> None:
        for trust in range(0, 10_001, 1_250):
            for standing in range(-10_000, 10_001, 2_500):
                for competence in (0, 5_000, 10_000):
                    share = assistance_share_bps(
                        personal_trust_bps=trust,
                        standing_bps=standing,
                        foreign_minister_competence_bps=competence,
                        independence_bps=7_000,
                    )
                    assert isinstance(share, int) and share >= 1


class TestThePool:
    def test_remaining_is_derived_and_never_negative(self) -> None:
        assert remaining_pool(capacity=100, drawn=30) == 70
        assert remaining_pool(capacity=100, drawn=100) == 0
        assert remaining_pool(capacity=100, drawn=180) == 0

    def test_a_grant_never_exceeds_the_remaining_pool(self) -> None:
        for drawn in range(0, 1_000, 97):
            assessment = assess_foreign_assistance(
                personal_trust_bps=10_000,
                standing_bps=10_000,
                foreign_minister_competence_bps=10_000,
                independence_bps=0,
                capacity=1_000,
                drawn=drawn,
            )
            assert assessment.granted <= remaining_pool(capacity=1_000, drawn=drawn)

    def test_an_exhausted_pool_refuses_rather_than_granting_zero(self) -> None:
        assessment = assess_foreign_assistance(
            personal_trust_bps=10_000,
            standing_bps=10_000,
            foreign_minister_competence_bps=10_000,
            independence_bps=0,
            capacity=500,
            drawn=500,
        )
        assert assessment.refusal is ForeignAssistanceRefusal.POOL_EXHAUSTED
        assert assessment.granted == 0

    def test_a_pool_too_small_for_the_share_still_grants_rather_than_reporting_exhaustion(
        self,
    ) -> None:
        """The defect this rule replaced: a POSITIVE pool whose proportional share truncated to
        zero used to be reported as exhausted.

        Two things were wrong with that. It was a false statement -- the counterpart still had
        money -- and it was ABSORBING: any pool below `10_000 // share` could never be drawn
        again, so authored capacity became permanently unreachable while the report claimed it had
        been spent. The floor moves to the grant instead, so the small-pool case is an accepted
        grant of 1, not a new kind of refusal.
        """
        assessment = assess_foreign_assistance(
            personal_trust_bps=0,
            standing_bps=0,
            foreign_minister_competence_bps=0,
            independence_bps=0,
            capacity=5,
            drawn=0,
        )
        # The proportional share genuinely rounds away -- this is the exact case, not a near miss.
        assert trunc_div_toward_zero(5 * FOREIGN_ASSISTANCE_BASE_SHARE_BPS, BPS_DENOMINATOR) == 0
        assert assessment.refusal is None
        assert assessment.granted == 1
        assert assessment.share_bps == FOREIGN_ASSISTANCE_BASE_SHARE_BPS

    def test_exhaustion_is_reported_exactly_when_the_remaining_capacity_is_zero(self) -> None:
        """Both directions, so neither a false exhausted report nor a missed one can pass.

        Swept across pools that straddle the truncation boundary and across shares from the
        smallest the formula can produce to the largest, because the defect lived precisely where
        `pool * share` was small enough to vanish.
        """
        for capacity in (0, 1, 2, 3, 5, 9, 10, 11, 99, 100, 101, 10_000):
            for trust, standing, competence, independence in (
                (0, MINIMUM_ASSISTANCE_STANDING_BPS, 0, 10_000),  # smallest reachable share
                (0, 0, 0, 0),
                (10_000, 10_000, 10_000, 0),  # largest reachable share
            ):
                assessment = assess_foreign_assistance(
                    personal_trust_bps=trust,
                    standing_bps=standing,
                    foreign_minister_competence_bps=competence,
                    independence_bps=independence,
                    capacity=capacity,
                    drawn=0,
                )
                exhausted = assessment.refusal is ForeignAssistanceRefusal.POOL_EXHAUSTED
                assert exhausted == (capacity == 0), (
                    f"capacity={capacity} share inputs={(trust, standing, competence, independence)}"
                )

    def test_every_willing_assessment_with_a_positive_pool_grants_at_least_one(self) -> None:
        for capacity in range(1, 60):
            for drawn in range(0, capacity):
                assessment = assess_foreign_assistance(
                    personal_trust_bps=0,
                    standing_bps=MINIMUM_ASSISTANCE_STANDING_BPS,
                    foreign_minister_competence_bps=0,
                    independence_bps=10_000,
                    capacity=capacity,
                    drawn=drawn,
                )
                assert assessment.refusal is None
                assert assessment.granted >= 1

    def test_the_grant_is_bounded_by_the_remaining_pool_across_every_share(self) -> None:
        """The floor is applied INSIDE the `min`, so it can raise a vanishing grant to 1 but can
        never carry it past what the counterpart actually has left."""
        for capacity in (1, 2, 7, 50, 1_000, 10_000):
            for drawn in (0, capacity // 3, capacity - 1, capacity):
                pool = remaining_pool(capacity=capacity, drawn=drawn)
                for trust, standing, competence, independence in (
                    (0, MINIMUM_ASSISTANCE_STANDING_BPS, 0, 10_000),
                    (5_000, 0, 5_000, 5_000),
                    (10_000, 10_000, 10_000, 0),
                ):
                    assessment = assess_foreign_assistance(
                        personal_trust_bps=trust,
                        standing_bps=standing,
                        foreign_minister_competence_bps=competence,
                        independence_bps=independence,
                        capacity=capacity,
                        drawn=drawn,
                    )
                    assert 0 <= assessment.granted <= pool
                    if pool > 0:
                        assert 1 <= assessment.granted <= pool

    def test_repeated_grants_drain_a_small_pool_until_it_is_genuinely_exhausted(self) -> None:
        """The property the old rule destroyed.

        Under the defect a pool of 5 granted nothing and reported exhaustion forever. Under the
        corrected rule it is drawn down a unit at a time and reaches a real zero, at which point
        -- and only at which point -- exhaustion is reported.
        """
        capacity, drawn, draws = 5, 0, 0
        while True:
            assessment = assess_foreign_assistance(
                personal_trust_bps=0,
                standing_bps=0,
                foreign_minister_competence_bps=0,
                independence_bps=0,
                capacity=capacity,
                drawn=drawn,
            )
            if assessment.refusal is not None:
                break
            assert assessment.granted >= 1
            drawn += assessment.granted
            draws += 1
            assert draws <= capacity, "a positive grant each turn must terminate"

        assert assessment.refusal is ForeignAssistanceRefusal.POOL_EXHAUSTED
        assert remaining_pool(capacity=capacity, drawn=drawn) == 0
        assert drawn == capacity
        assert draws == 5

    def test_hostility_is_checked_before_the_pool(self) -> None:
        """Two different political facts, and only one of them is something a player can act on
        today -- so a hostile counterpart with an empty pool reports hostility."""
        assessment = assess_foreign_assistance(
            personal_trust_bps=0,
            standing_bps=MINIMUM_ASSISTANCE_STANDING_BPS - 1,
            foreign_minister_competence_bps=0,
            independence_bps=0,
            capacity=0,
            drawn=0,
        )
        assert assessment.refusal is ForeignAssistanceRefusal.HOSTILE

    def test_an_assessment_cannot_grant_and_refuse_at_once(self) -> None:
        with pytest.raises(ValueError, match="must grant nothing"):
            ForeignAssistanceAssessment(
                granted=10, share_bps=0, refusal=ForeignAssistanceRefusal.HOSTILE
            )
        with pytest.raises(ValueError, match="must grant a positive amount"):
            ForeignAssistanceAssessment(granted=0, share_bps=100, refusal=None)


class TestTheImportFence:
    """`war_capability_bps` is an abstract capability for non-player wars. Aid is diplomatic, and
    letting one decide the other would couple two systems the repository keeps deliberately
    apart."""

    def test_the_module_never_reads_war_capability(self) -> None:
        """An AST scan for real attribute ACCESS, not a text search.

        The module's own docstring explains the fence at length, so a text search would fail on the
        explanation rather than on a breach -- and would equally pass a module that spelled the
        access `getattr(profile, "war_capability" + "_bps")`. What matters is whether the value is
        ever actually read.
        """
        tree = ast.parse(_ASSISTANCE_MODULE.read_text(encoding="utf-8"))
        accessed = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)} | {
            node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
        }
        assert "war_capability_bps" not in accessed

    def test_the_module_imports_neither_conflict_nor_survival(self) -> None:
        tree = ast.parse(_ASSISTANCE_MODULE.read_text(encoding="utf-8"))
        modules = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        assert "app.simulation.foreign_conflict" not in modules
        assert "app.simulation.government_survival" not in modules

    def test_the_module_imports_no_state_models(self) -> None:
        """Formulas over metrics, the `government_survival` shape: it takes plain ints it declares
        itself, so `simulation.state` never appears."""
        tree = ast.parse(_ASSISTANCE_MODULE.read_text(encoding="utf-8"))
        modules = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        assert "app.simulation.state" not in modules


# --------------------------------------------------------------------------------------------
# The foreign minister's first real consumer.
# --------------------------------------------------------------------------------------------


class TestTheForeignMinisterFinallyMatters:
    """Until this slice `FOREIGN_MINISTER` appeared exactly once outside its own enum -- an office
    nothing read. These are the tests that make it consequential."""

    def test_the_minister_is_the_only_difference_when_only_the_minister_differs(self) -> None:
        """One scenario, one counterpart, one turn -- and the cabinet vacated in the second run.

        Comparing `decree_state` against `deficit_demo` would NOT isolate the minister: those two
        also author different `standing_bps` (-1,000 against +1,000), so their gap is the minister
        term less the standing term and attributing all of it to the diplomat would be wrong.
        Emptying one scenario's own cabinet holds every other input fixed, which is what makes the
        exact-equality assertion below meaningful.
        """
        seated_state = _state("decree_state")
        vacant_state = seated_state.model_copy(update={"world": seated_state.world})
        player = vacant_state.world.countries[vacant_state.world.player_country_id]
        countries = dict(vacant_state.world.countries)
        countries[player.id] = player.model_copy(
            update={"cabinet": player.cabinet.model_copy(update={"offices": {}})}
        )
        vacant_state = vacant_state.model_copy(
            update={"world": vacant_state.world.model_copy(update={"countries": countries})}
        )

        seated = _resolve(seated_state, _ask("marnil")).report.foreign_affairs.assistance[0]
        vacant = _resolve(vacant_state, _ask("marnil")).report.foreign_affairs.assistance[0]

        assert seated.foreign_minister_competence_bps == 8_600
        assert vacant.foreign_minister_competence_bps == 0
        assert seated.standing_bps == vacant.standing_bps
        assert seated.opening_capacity == vacant.opening_capacity
        assert seated.share_bps - vacant.share_bps == trunc_div_toward_zero(
            8_600 * FOREIGN_MINISTER_ASSISTANCE_SHARE_MAX_BPS, BPS_DENOMINATOR
        )
        assert seated.granted > vacant.granted

    def test_the_shipped_scenarios_still_show_the_contrast_end_to_end(self) -> None:
        """The weaker but real claim across scenarios: `decree_state` seats a diplomat at 8,600
        and `deficit_demo`'s chair is empty, and the same counterpart gives the first a larger
        share. Stated as an inequality, because those two scenarios differ in standing as well."""
        seated = _resolve(_state("decree_state"), _ask("marnil")).report
        vacant = _resolve(_state("deficit_demo"), _ask("marnil")).report
        assert seated.foreign_affairs.assistance[0].foreign_minister_competence_bps == 8_600
        assert vacant.foreign_affairs.assistance[0].foreign_minister_competence_bps == 0
        assert (
            seated.foreign_affairs.assistance[0].share_bps
            > vacant.foreign_affairs.assistance[0].share_bps
        )

    def test_a_vacant_post_still_receives_aid(self) -> None:
        """The contribution raises the fraction; it never unlocks the grant. A wall would make the
        vacancy unmeasurable, which is the opposite of the point."""
        report = _resolve(_state("deficit_demo"), _ask("marnil")).report
        row = report.foreign_affairs.assistance[0]
        assert row.refusal_code is None
        assert row.granted > 0
        assert row.foreign_minister_competence_bps == 0

    def test_a_minister_appointed_this_very_turn_contributes_nothing(self) -> None:
        """The effectivity rule has ONE definition, in `simulation.cabinet`, and this reads it: an
        appointment resolved on turn `t` takes office at `t + 1`, so it cannot pay for the turn
        that hired it."""
        state = _state("deficit_demo")
        hire = CabinetDecision(
            orders=(CabinetOrder(post="foreign_minister", character_id="freya_lund"),)
        )
        with_hire = _resolve(state, hire, _ask("marnil")).report
        without = _resolve(state, _ask("marnil")).report
        hired_row = with_hire.foreign_affairs.assistance[0]
        assert hired_row.foreign_minister_competence_bps == 0
        assert hired_row.granted == without.foreign_affairs.assistance[0].granted


# --------------------------------------------------------------------------------------------
# Accounting: an external transfer, not revenue and not a smaller deficit.
# --------------------------------------------------------------------------------------------


class TestTheAccountingTerm:
    def test_a_grant_reduces_borrowing_by_exactly_its_own_amount(self) -> None:
        """`deficit_demo` runs a real deficit, so the grant's effect is visible in `new_borrowing`
        rather than absorbed into cash."""
        baseline = _resolve(_state("deficit_demo")).report.finance
        granted = _resolve(_state("deficit_demo"), _ask("marnil")).report.finance
        assert granted.external_assistance > 0
        assert baseline.new_borrowing - granted.new_borrowing == granted.external_assistance

    def test_the_grant_never_enters_revenue_or_the_pre_financing_balance(self) -> None:
        """The load-bearing claim of this slice's accounting. Aid is not tax, and it is not part of
        the country's own fiscal position; a government must not look solvent because somebody else
        paid."""
        baseline = _resolve(_state("deficit_demo")).report.finance
        granted = _resolve(_state("deficit_demo"), _ask("marnil")).report.finance
        assert granted.revenue.total_revenue == baseline.revenue.total_revenue
        assert granted.pre_financing_balance == baseline.pre_financing_balance
        assert granted.pre_financing_balance == (
            granted.revenue.total_revenue
            - granted.total_program_spending
            - granted.quarterly_interest_expense
        )

    def test_a_surplus_government_keeps_the_grant_as_cash(self) -> None:
        """The other financing branch: with nothing to borrow, the transfer lands in closing cash,
        again by exactly its own amount."""
        baseline = _resolve(_state("tiny_valid")).report.finance
        granted = _resolve(_state("tiny_valid"), _ask("kessia")).report.finance
        assert baseline.new_borrowing == granted.new_borrowing == 0
        assert granted.closing_cash - baseline.closing_cash == granted.external_assistance

    def test_the_cash_flow_identity_holds_with_a_grant(self) -> None:
        finance = _resolve(_state("deficit_demo"), _ask("marnil")).report.finance
        assert (
            finance.opening_cash
            + finance.revenue.total_revenue
            + finance.new_borrowing
            + finance.external_assistance
            == finance.closing_cash
            + finance.total_program_spending
            + finance.quarterly_interest_expense
        )

    def test_a_quiet_turn_transfers_nothing(self) -> None:
        report = _resolve(_state("tiny_valid")).report
        assert report.finance.external_assistance == 0
        assert report.foreign_affairs.assistance == ()

    def test_the_finance_field_is_required_with_no_default(self) -> None:
        """A default would make every stored 0.20.0 report load and would assert that a turn
        resolved before this mechanic existed had "no assistance"."""
        assert FinanceReport.model_fields["external_assistance"].is_required()


class TestThePd1Sweep:
    """The permanent sweep PD-1's correction requires whenever a REQUIRED parameter is added.

    PD-1 (Commit 5): `endorsement_bps` was made required on two support functions, a grep found
    call sites in eight files, two were patched, and a stale partial-run failure list was then
    trusted as the complete inventory. It was not -- an enum-membership pin that no call-site grep
    would ever have found was missed, and the first full suite cost 24 minutes to say so.

    The rule adopted was: sweep for the SYMBOL, not the call shape, and do it BEFORE the first full
    suite rather than deriving the impacted list from a partial run. `external_assistance` is the
    same kind of change, so it gets the same kind of sweep -- as a permanent test, because the
    inventory needs to stay correct for every future call site too, not just today's.
    """

    def _iter_sources(self) -> list[Path]:
        root = Path(__file__).resolve().parents[1]
        files = sorted((root / "app").rglob("*.py")) + sorted((root / "tests").rglob("*.py"))
        return files

    def _calls_named(self, tree: ast.AST, name: str) -> list[ast.Call]:
        """Every call whose callee spells `name`, written either bare or attribute-style."""
        found: list[ast.Call] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            spelled = (
                func.id
                if isinstance(func, ast.Name)
                else func.attr
                if isinstance(func, ast.Attribute)
                else None
            )
            if spelled == name:
                found.append(node)
        return found

    def test_the_production_parameter_has_no_default(self) -> None:
        """The whole point of the sweep: a default would silently absorb every missed call site,
        and the missing term would surface as a wrong number rather than as an error."""
        import inspect

        from app.simulation.accounting import resolve_cash_and_debt

        parameter = inspect.signature(resolve_cash_and_debt).parameters["external_assistance"]
        assert parameter.default is inspect.Parameter.empty
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY

    def test_every_call_site_in_the_repository_names_it_explicitly(self) -> None:
        checked = 0
        for path in self._iter_sources():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for call in self._calls_named(tree, "resolve_cash_and_debt"):
                keywords = {keyword.arg for keyword in call.keywords}
                assert "external_assistance" in keywords, (
                    f"{path}:{call.lineno} calls resolve_cash_and_debt without naming "
                    f"external_assistance"
                )
                checked += 1
        assert checked >= 10, f"the sweep found only {checked} call sites, which looks like a bug"

    def test_every_direct_finance_report_construction_names_it_explicitly(self) -> None:
        """`FinanceReport` is required-field-validated, so a missed construction would raise -- but
        it would raise wherever the object happened to be built, which is exactly the diffuse
        failure mode PD-1 is about. Enumerating them keeps the inventory a fact."""
        checked = 0
        for path in self._iter_sources():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for call in self._calls_named(tree, "FinanceReport"):
                if any(keyword.arg is None for keyword in call.keywords):
                    continue  # a **kwargs splat carries the field without naming it here
                keywords = {keyword.arg for keyword in call.keywords}
                if not keywords:
                    continue  # `FinanceReport` used as a bare annotation-style call, not a build
                assert "external_assistance" in keywords, (
                    f"{path}:{call.lineno} constructs a FinanceReport without external_assistance"
                )
                checked += 1
        assert checked >= 1

    def test_the_sweep_detects_a_planted_violation(self) -> None:
        """Anti-vacuity: a scan that matches nothing passes silently, which is the failure mode
        that made PD-1 possible in the first place."""
        planted = ast.parse(
            "resolve_cash_and_debt(opening_cash=1)\nFinanceReport(opening_cash=1)\n"
        )
        for name in ("resolve_cash_and_debt", "FinanceReport"):
            calls = self._calls_named(planted, name)
            assert len(calls) == 1
            assert "external_assistance" not in {keyword.arg for keyword in calls[0].keywords}


# --------------------------------------------------------------------------------------------
# Outcomes, capacity and state.
# --------------------------------------------------------------------------------------------


class TestOutcomes:
    def test_an_accepted_request_draws_exactly_what_it_granted(self) -> None:
        state = _state("tiny_valid")
        resolution = _resolve(state, _ask("kessia"))
        row = resolution.report.foreign_affairs.assistance[0]
        opening = state.world.foreign_relationships["kessia"].assistance_drawn
        closing = resolution.state.world.foreign_relationships["kessia"].assistance_drawn
        assert closing - opening == row.granted == resolution.report.finance.external_assistance
        assert row.closing_drawn == closing

    def test_a_hostile_counterpart_refuses_from_shipped_content(self) -> None:
        """`tiny_valid` authors Vetruska below the hostility floor deliberately, so this branch is
        reachable from content rather than only from a constructed state."""
        state = _state("tiny_valid")
        assert state.world.foreign_relationships["vetruska"].standing_bps < (
            MINIMUM_ASSISTANCE_STANDING_BPS
        )
        resolution = _resolve(state, _ask("vetruska"))
        row = resolution.report.foreign_affairs.assistance[0]
        assert row.refusal_code == "foreign_assistance_counterpart_is_hostile"
        assert row.granted == 0
        assert resolution.report.finance.external_assistance == 0
        assert resolution.state.world.foreign_relationships["vetruska"].assistance_drawn == 0

    def test_an_exhausted_pool_refuses_and_draws_nothing(self) -> None:
        state = _state("tiny_valid")
        profile = state.world.foreign_profiles["kessia"]
        relationships = dict(state.world.foreign_relationships)
        relationships["kessia"] = relationships["kessia"].model_copy(
            update={"assistance_drawn": profile.assistance_capacity}
        )
        drained = state.model_copy(
            update={
                "world": state.world.model_copy(update={"foreign_relationships": relationships})
            }
        )
        assert check_invariants(drained) == []
        row = _resolve(drained, _ask("kessia")).report.foreign_affairs.assistance[0]
        assert row.refusal_code == "foreign_assistance_pool_exhausted"
        assert row.granted == 0

    def test_no_counterpart_but_the_one_asked_is_touched(self) -> None:
        state = _state("tiny_valid")
        resolution = _resolve(state, _ask("kessia"))
        assert (
            resolution.state.world.foreign_relationships["vetruska"]
            == state.world.foreign_relationships["vetruska"]
        )

    def test_capacity_and_standing_are_never_written(self) -> None:
        """Only `assistance_drawn` moves. Capacity is authored, and standing is a later slice's
        business."""
        state = _state("tiny_valid")
        resolution = _resolve(state, _ask("kessia"))
        assert resolution.state.world.foreign_profiles == state.world.foreign_profiles
        for profile_id, opening in state.world.foreign_relationships.items():
            closing = resolution.state.world.foreign_relationships[profile_id]
            assert closing.standing_bps == opening.standing_bps

    def test_the_character_registry_is_byte_identical(self) -> None:
        """This slice READS `personal_trust` and never writes it; a later slice is the only
        writer."""
        state = _state("tiny_valid")
        for decision in (_ask("kessia"), _ask("vetruska")):
            resolution = _resolve(state, decision)
            assert resolution.state.world.characters == state.world.characters


class TestTheDecisionUnion:
    """The serialized discriminators, pinned as an exact tuple in CANONICAL order.

    `decisions_json` is hash-covered and `_decisions_are_in_canonical_kind_order` rejects rather
    than sorts, so the kind VALUES and their ascending order are a save-format fact, not a naming
    preference. Read off the real models rather than transcribed from the plan, which is what
    turns "`cabinet` is presumably the tag" into a verified claim.
    """

    def _members(self) -> tuple[type, ...]:
        import typing

        from app.simulation.decisions import Decision

        return typing.get_args(typing.get_args(Decision)[0])

    def test_the_seven_serialized_kinds_are_exactly_these_in_canonical_order(self) -> None:
        kinds = sorted(member.model_fields["kind"].default for member in self._members())
        assert kinds == [
            "bloc_relationship_investment",
            "budget",
            "cabinet",
            "constitutional_amendment",
            "foreign_assistance",
            "legislative_bargain",
            "military_movement",
        ]

    def test_foreign_assistance_sorts_fifth_so_no_existing_canonical_order_changes(self) -> None:
        """The six kinds that already existed keep their relative order, so every
        already-serialised multi-kind `decisions_json` digests identically."""
        existing = [
            "bloc_relationship_investment",
            "budget",
            "cabinet",
            "constitutional_amendment",
            "legislative_bargain",
            "military_movement",
        ]
        assert existing == sorted(existing)
        combined = sorted([*existing, "foreign_assistance"])
        assert combined.index("foreign_assistance") == 4
        assert [kind for kind in combined if kind != "foreign_assistance"] == existing

    def test_every_member_declares_its_kind_as_an_explicit_literal_default(self) -> None:
        """Discrimination is by tag, never by shape -- so a member without a concrete default
        would silently become undiscriminable."""
        for member in self._members():
            default = member.model_fields["kind"].default
            assert isinstance(default, str) and default, member.__name__

    def test_the_union_declaration_order_is_append_order_and_is_left_alone(self) -> None:
        """Declaration order is NOT canonical order and must not be 'tidied' into alphabetical.

        Canonical order is enforced on the serialized `kind` values by
        `_decisions_are_in_canonical_kind_order`; the union's declaration order is just the order
        the slices landed in, and reordering it would be a diff that looks like housekeeping while
        changing nothing -- or, if a future member ever overlapped structurally, changing
        resolution.
        """
        declared = [member.model_fields["kind"].default for member in self._members()]
        assert declared == [
            "budget",
            "bloc_relationship_investment",
            "constitutional_amendment",
            "military_movement",
            "cabinet",
            "legislative_bargain",
            "foreign_assistance",
        ]
        assert declared != sorted(declared), (
            "declaration order is append order, not canonical order"
        )


class TestSubmissionRejection:
    @pytest.mark.parametrize(
        ("profile_id", "expected_code"),
        [
            ("atlantis", "foreign_assistance_profile_unknown"),
        ],
    )
    def test_each_code_is_reported_by_both_surfaces(
        self, profile_id: str, expected_code: str
    ) -> None:
        state = _state("tiny_valid")
        decision_set = DecisionSet(
            expected_turn=state.turn,
            expected_state_version=state.state_version,
            decisions=(_ask(profile_id),),
        )
        with pytest.raises(TurnResolutionError, match=expected_code):
            resolve_turn(state, decision_set)
        problem = first_decision_problem(state, decision_set)
        assert problem is not None and problem.code == expected_code

    def test_a_counterpart_with_no_authored_capacity_is_refused_at_submission(self) -> None:
        state = _state("tiny_valid")
        profiles = dict(state.world.foreign_profiles)
        profiles["kessia"] = profiles["kessia"].model_copy(update={"assistance_capacity": 0})
        poor = state.model_copy(
            update={"world": state.world.model_copy(update={"foreign_profiles": profiles})}
        )
        decision_set = DecisionSet(
            expected_turn=poor.turn,
            expected_state_version=poor.state_version,
            decisions=(_ask("kessia"),),
        )
        with pytest.raises(TurnResolutionError, match="foreign_assistance_profile_offers_none"):
            resolve_turn(poor, decision_set)
        problem = first_decision_problem(poor, decision_set)
        assert problem is not None
        assert problem.code == "foreign_assistance_profile_offers_none"

    def test_a_counterpart_with_no_relationship_is_refused_at_submission(self) -> None:
        """ "We have no dealings with them" is a different state of the world from "we have neutral
        dealings with them", and the engine refuses rather than inventing the second."""
        state = _state("tiny_valid")
        relationships = dict(state.world.foreign_relationships)
        del relationships["kessia"]
        stranger = state.model_copy(
            update={
                "world": state.world.model_copy(update={"foreign_relationships": relationships})
            }
        )
        decision_set = DecisionSet(
            expected_turn=stranger.turn,
            expected_state_version=stranger.state_version,
            decisions=(_ask("kessia"),),
        )
        with pytest.raises(TurnResolutionError, match="foreign_assistance_no_relationship"):
            resolve_turn(stranger, decision_set)
        problem = first_decision_problem(stranger, decision_set)
        assert problem is not None and problem.code == "foreign_assistance_no_relationship"

    def test_a_refusal_is_not_a_submission_rejection(self) -> None:
        state = _state("tiny_valid")
        decision_set = DecisionSet(
            expected_turn=state.turn,
            expected_state_version=state.state_version,
            decisions=(_ask("vetruska"),),
        )
        assert first_decision_problem(state, decision_set) is None

    def test_at_most_one_request_per_turn(self) -> None:
        with pytest.raises(ValidationError, match="at most one foreign-assistance decision"):
            DecisionSet(
                expected_turn=0,
                expected_state_version=0,
                decisions=(_ask("kessia"), _ask("vetruska")),
            )

    def test_an_overdrawn_state_is_refused_by_the_invariant(self) -> None:
        state = _state("tiny_valid")
        relationships = dict(state.world.foreign_relationships)
        relationships["kessia"] = relationships["kessia"].model_copy(
            update={
                "assistance_drawn": state.world.foreign_profiles["kessia"].assistance_capacity + 1
            }
        )
        overdrawn = state.model_copy(
            update={
                "world": state.world.model_copy(update={"foreign_relationships": relationships})
            }
        )
        codes = {violation.code for violation in check_invariants(overdrawn)}
        assert "foreign_assistance_overdrawn" in codes

    def test_a_relationship_with_no_profile_is_refused_by_the_invariant(self) -> None:
        state = _state("tiny_valid")
        relationships = dict(state.world.foreign_relationships)
        relationships["atlantis"] = relationships["kessia"]
        dangling = state.model_copy(
            update={
                "world": state.world.model_copy(update={"foreign_relationships": relationships})
            }
        )
        codes = {violation.code for violation in check_invariants(dangling)}
        assert "foreign_relationship_profile_unknown" in codes


# --------------------------------------------------------------------------------------------
# Group 59: an INDEPENDENT oracle.
# --------------------------------------------------------------------------------------------


_ALLOWED_ASSISTANCE_IMPORTS = frozenset(
    {
        "FOREIGN_ASSISTANCE_BASE_SHARE_BPS",
        "FOREIGN_ASSISTANCE_INDEPENDENCE_PENALTY_MAX_BPS",
        "FOREIGN_ASSISTANCE_STANDING_SHARE_MAX_BPS",
        "FOREIGN_ASSISTANCE_TRUST_SHARE_MAX_BPS",
        "FOREIGN_MINISTER_ASSISTANCE_SHARE_MAX_BPS",
        "MINIMUM_ASSISTANCE_STANDING_BPS",
    }
)
"""What `reconciliation.py` may take from `foreign_assistance`: CONSTANTS, and nothing else.

An ALLOWLIST, not a denylist of the three function names -- a denylist would silently permit a
newly added helper, which is exactly how this boundary would erode. Anything not named here fails
by default and has to be argued for. The same instrument PD-1 produced for group 58.
"""


class TestGroup59IsIndependent:
    def test_reconciliation_imports_only_constants(self) -> None:
        tree = ast.parse(_RECONCILIATION_MODULE.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module == "app.simulation.foreign_assistance"
            ):
                imported.update(alias.name for alias in node.names)
        assert imported, "reconciliation is expected to import the calibration constants"
        assert imported <= _ALLOWED_ASSISTANCE_IMPORTS, sorted(
            imported - _ALLOWED_ASSISTANCE_IMPORTS
        )

    def test_reconciliation_never_calls_the_production_assessment(self) -> None:
        forbidden = {"assess_foreign_assistance", "assistance_share_bps", "remaining_pool"}
        tree = ast.parse(_RECONCILIATION_MODULE.read_text(encoding="utf-8"))
        called = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert not (called & forbidden), sorted(called & forbidden)

    def test_the_scan_detects_a_call_when_one_is_present(self) -> None:
        """Anti-vacuity: a scan that matches nothing would pass whatever the module did."""
        sample = ast.parse(
            "from app.simulation.foreign_assistance import assistance_share_bps\n"
            "x = assistance_share_bps(personal_trust_bps=0, standing_bps=0,\n"
            "                         foreign_minister_competence_bps=0, independence_bps=0)\n"
        )
        called = {
            node.func.id
            for node in ast.walk(sample)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "assistance_share_bps" in called

    def test_the_transcription_agrees_with_the_engine_across_a_sweep(self) -> None:
        """Two implementations, one answer. A disagreement surfaces here rather than as a save
        that silently reconciles against a wrong number."""
        from app.simulation.reconciliation import _transcribed_assistance_share_bps

        for trust in range(0, 10_001, 1_250):
            for standing in range(-10_000, 10_001, 2_500):
                for competence in (0, 4_300, 8_600, 10_000):
                    for independence in (0, 9_100):
                        assert _transcribed_assistance_share_bps(
                            personal_trust_bps=trust,
                            standing_bps=standing,
                            foreign_minister_competence_bps=competence,
                            independence_bps=independence,
                        ) == assistance_share_bps(
                            personal_trust_bps=trust,
                            standing_bps=standing,
                            foreign_minister_competence_bps=competence,
                            independence_bps=independence,
                        )


def _reconciled(scenario: str, *decisions):  # type: ignore[no-untyped-def]
    state = _state(scenario)
    decision_set = DecisionSet(
        expected_turn=state.turn,
        expected_state_version=state.state_version,
        decisions=tuple(sorted(decisions, key=lambda d: d.kind)),
    )
    return state, resolve_turn(state, decision_set), decision_set


class TestGroup59Tampers:
    def test_an_untampered_turn_reconciles_clean(self) -> None:
        """Anti-vacuity for every tamper below."""
        state, resolution, decision_set = _reconciled("tiny_valid", _ask("kessia"))
        assert (
            reconcile_foreign_affairs_report(
                opening_state=state,
                closing_state=resolution.state,
                report=resolution.report,
                decisions=decision_set,
            )
            == []
        )

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("granted", 1),
            ("share_bps", 1),
            ("foreign_minister_competence_bps", 0),
            ("standing_bps", -9_000),
            ("opening_capacity", 1),
            ("opening_drawn", 7),
            ("profile_display_name", "Somewhere Else"),
            ("refusal_code", "foreign_assistance_pool_exhausted"),
        ],
    )
    def test_a_forged_assistance_row_field_is_caught(self, field: str, value: object) -> None:
        state, resolution, decision_set = _reconciled("tiny_valid", _ask("kessia"))
        report = resolution.report
        row = report.foreign_affairs.assistance[0]
        # `model_copy`, not a dump-and-reconstruct: dumping would flatten every nested report into
        # a dict and the tamper would fail for the wrong reason. Validation is deliberately
        # skipped -- the row's own validators refuse most of these, and the point is that
        # reconciliation catches a row forged directly into a save.
        forged_affairs = report.foreign_affairs.model_copy(
            update={"assistance": (row.model_copy(update={field: value}),)}
        )
        forged = report.model_copy(update={"foreign_affairs": forged_affairs})
        problems = reconcile_foreign_affairs_report(
            opening_state=state,
            closing_state=resolution.state,
            report=forged,
            decisions=decision_set,
        )
        assert any("group 59" in problem for problem in problems), problems

    def test_a_state_whose_draw_disagrees_with_the_row_is_caught(self) -> None:
        state, resolution, decision_set = _reconciled("tiny_valid", _ask("kessia"))
        closing = resolution.state
        relationships = dict(closing.world.foreign_relationships)
        relationships["kessia"] = relationships["kessia"].model_copy(
            update={"assistance_drawn": relationships["kessia"].assistance_drawn + 1}
        )
        forged_state = closing.model_copy(
            update={
                "world": closing.world.model_copy(update={"foreign_relationships": relationships})
            }
        )
        problems = reconcile_foreign_affairs_report(
            opening_state=state,
            closing_state=forged_state,
            report=resolution.report,
            decisions=decision_set,
        )
        assert any("group 59" in problem for problem in problems), problems

    def test_a_self_consistent_exhausted_row_against_a_positive_pool_is_caught(self) -> None:
        """The corrected rule's own guard rail.

        The parametrized tamper above forges `refusal_code` alone, which is internally
        contradictory and could in principle be caught by a consistency check rather than by the
        re-derivation. This forges the WHOLE row into the exact shape a genuine exhaustion would
        have -- zero granted, zero share, the exhausted code -- so nothing about it is
        self-contradictory and only an independent re-derivation against the opening pool can
        refuse it. That is the false report C1 exists to make impossible.
        """
        state, resolution, decision_set = _reconciled("tiny_valid", _ask("kessia"))
        report = resolution.report
        row = report.foreign_affairs.assistance[0]
        assert row.opening_capacity - row.opening_drawn > 0, "the pool must really have money in it"

        forged_row = row.model_copy(
            update={
                "granted": 0,
                "share_bps": 0,
                "refusal_code": "foreign_assistance_pool_exhausted",
            }
        )
        forged_affairs = report.foreign_affairs.model_copy(update={"assistance": (forged_row,)})
        forged = report.model_copy(update={"foreign_affairs": forged_affairs})
        problems = reconcile_foreign_affairs_report(
            opening_state=state,
            closing_state=resolution.state,
            report=forged,
            decisions=decision_set,
        )
        assert any("group 59" in problem for problem in problems), problems

    def test_a_turn_reporting_assistance_it_never_asked_for_is_caught(self) -> None:
        state, resolution, _ = _reconciled("tiny_valid", _ask("kessia"))
        quiet = DecisionSet(
            expected_turn=state.turn, expected_state_version=state.state_version, decisions=()
        )
        problems = reconcile_foreign_affairs_report(
            opening_state=state,
            closing_state=resolution.state,
            report=resolution.report,
            decisions=quiet,
        )
        assert any("group 59" in problem for problem in problems), problems


class TestRenderedSentences:
    def test_the_granted_sentence_names_the_counterpart_and_what_remains(self) -> None:
        report = _resolve(_state("tiny_valid"), _ask("kessia")).report
        entry = next(e for e in report.entries if e.reason_id == "foreign_assistance_granted")
        assert render_entry(entry) == (
            "Chancellor Dietrich Halm of Kessia sent 38,150,000 in assistance; "
            "211,850,000 of their capacity remains."
        )

    def test_the_hostile_sentence_states_no_figure(self) -> None:
        report = _resolve(_state("tiny_valid"), _ask("vetruska")).report
        entry = next(
            e for e in report.entries if e.reason_id == "foreign_assistance_counterpart_is_hostile"
        )
        assert render_entry(entry) == "Vetruska is too hostile to send assistance."
        assert set(entry.params) == {
            "profile_id",
            "profile_display_name",
            "counterpart_character_id",
            "counterpart_display_name",
        }

    def test_every_reason_id_has_a_renderer(self) -> None:
        for reason_id in (
            "foreign_assistance_granted",
            "foreign_assistance_counterpart_is_hostile",
            "foreign_assistance_pool_exhausted",
        ):
            assert reason_id in REASON_RENDERERS


class TestTheProjectionAndPreview:
    @pytest.mark.parametrize("scenario", ["tiny_valid", "decree_state", "deficit_demo"])
    def test_grant_and_refusal_are_exclusive_everywhere(self, scenario: str) -> None:
        options = build_decision_options(_state(scenario)).foreign_assistance_counterparties
        assert options
        for option in options:
            if option.will_assist:
                assert option.estimated_grant is not None and option.refusal_reason is None
            else:
                assert option.estimated_grant is None
                assert option.refusal_reason is not None

    def test_the_exclusive_shape_is_enforced(self) -> None:
        from app.api.projections import ForeignAssistanceCounterpartyOption

        base = {
            "profile_id": "x",
            "display_name": "X",
            "standing_bps": 0,
            "remaining_capacity": 100,
        }
        with pytest.raises(ValidationError, match="willing counterpart"):
            ForeignAssistanceCounterpartyOption(**base, will_assist=True, estimated_grant=None)
        with pytest.raises(ValidationError, match="unwilling counterpart"):
            ForeignAssistanceCounterpartyOption(
                **base,
                will_assist=False,
                estimated_grant=5,
                refusal_reason="foreign_assistance_pool_exhausted",
            )

    def test_the_preview_estimate_equals_what_the_resolver_transfers(self) -> None:
        state = _state("deficit_demo")
        decision_set = DecisionSet(
            expected_turn=state.turn,
            expected_state_version=state.state_version,
            decisions=(_ask("marnil"),),
        )
        projection = preview_decisions(state, decision_set)
        resolved = resolve_turn(state, decision_set).report.finance.external_assistance
        assert projection.foreign_assistance_estimate == resolved > 0

    def test_the_estimate_is_not_part_of_committed_capital(self) -> None:
        """Money received, not capital spent. A grant costs no political capital at all."""
        state = _state("deficit_demo")
        with_request = preview_decisions(
            state,
            DecisionSet(
                expected_turn=state.turn,
                expected_state_version=state.state_version,
                decisions=(_ask("marnil"),),
            ),
        )
        without = preview_decisions(
            state,
            DecisionSet(
                expected_turn=state.turn,
                expected_state_version=state.state_version,
                decisions=(),
            ),
        )
        assert with_request.foreign_assistance_estimate > 0
        assert with_request.committed_capital == without.committed_capital

    def test_a_refused_counterpart_estimates_nothing(self) -> None:
        state = _state("tiny_valid")
        projection = preview_decisions(
            state,
            DecisionSet(
                expected_turn=state.turn,
                expected_state_version=state.state_version,
                decisions=(_ask("vetruska"),),
            ),
        )
        assert projection.foreign_assistance_estimate == 0


class TestCompatibility:
    """Two proofs, each falsifiable on its own -- the version gate and the payload shape are
    separate claims, and a save rejected on its version never reaches the parser."""

    def test_the_fixture_really_predates_this_ruleset(self) -> None:
        raw = json.loads(_FIXTURE.read_text(encoding="utf-8"))
        assert raw["ruleset_version"] == "0.20.0"
        assert raw["content_version"] == "0.17.0"
        assert RULESET_VERSION == "0.21.0"

    def _one_stored_finance_report(self) -> dict[str, object]:
        raw = json.loads(_FIXTURE.read_text(encoding="utf-8"))
        for entry in raw["entries"]:
            payload = entry.get("report_json")
            if not payload:
                continue
            document = json.loads(payload) if isinstance(payload, str) else payload
            if document.get("finance"):
                return dict(document["finance"])
        raise AssertionError("the fixture is expected to carry a real FinanceReport")

    def test_proof_a_the_payload_fails_specifically_on_the_missing_field(self) -> None:
        """Bypasses the version gate entirely and parses one stored report under the NEW model.

        Asserts the SPECIFIC error -- type `missing`, location `external_assistance` -- rather than
        "some ValidationError", because a test that accepted any failure would keep passing if the
        payload later broke for an unrelated reason.
        """
        stored = self._one_stored_finance_report()
        assert "external_assistance" not in stored
        with pytest.raises(ValidationError) as exc_info:
            FinanceReport.model_validate(stored)
        errors = exc_info.value.errors()
        assert [error["type"] for error in errors] == ["missing"]
        assert [error["loc"] for error in errors] == [("external_assistance",)]

    def test_proof_a_anti_vacuity_the_single_field_is_the_whole_incompatibility(self) -> None:
        """A LOCAL COPY with `external_assistance: 0` injected parses cleanly.

        The production model must never gain a default -- that is the whole reason 0.20.0 is
        incompatible; the injection happens in the test's own copy only.
        """
        stored = self._one_stored_finance_report()
        report = FinanceReport.model_validate(stored | {"external_assistance": 0})
        assert report.external_assistance == 0
        assert FinanceReport.model_fields["external_assistance"].is_required()

    def test_proof_b_the_version_rejection_happens_before_any_parsing(self) -> None:
        """Every payload replaced with text that is not even valid JSON, envelope left at 0.20.0.
        A clean version rejection is only possible if the version check runs FIRST -- and because
        the payloads are unparseable, this cannot pass by accident on a build where the order is
        reversed."""
        from app.core.errors import UnsupportedRulesetVersionError
        from app.simulation.save_format import load_save_json

        raw = json.loads(_FIXTURE.read_text(encoding="utf-8"))
        for entry in raw["entries"]:
            if "state_json" in entry:
                entry["state_json"] = "{definitely not json"
            if entry.get("report_json") is not None:
                entry["report_json"] = "{definitely not json"
        with pytest.raises(UnsupportedRulesetVersionError) as exc_info:
            load_save_json(json.dumps(raw), source="corrupted-but-still-incompatible")
        message = str(exc_info.value)
        assert "0.20.0" in message and RULESET_VERSION in message

    def test_the_fixture_still_carries_both_pre_assistance_shapes(self) -> None:
        """If either shape were regenerated under the current engine, the proofs above would be
        hollow."""
        raw = json.loads(_FIXTURE.read_text(encoding="utf-8"))
        world = json.loads(raw["entries"][-1]["state_json"])["world"]
        assert all(
            "assistance_capacity" not in profile for profile in world["foreign_profiles"].values()
        )
        assert "foreign_relationships" not in world


class TestSaveAndReplay:
    def test_a_multi_turn_campaign_that_asks_is_refused_and_asks_again_validates(self) -> None:
        """Through the real history layer, with the hash chain intact and every turn reconciled --
        including group 59, which `validate_history` runs on replay."""
        save = new_game(_state("tiny_valid"), save_format_version=SAVE_FORMAT_VERSION)
        for decision in (_ask("kessia"), _ask("vetruska"), _ask("kessia")):
            current = save.current_state()
            save = advance_game(
                save,
                DecisionSet(
                    expected_turn=current.turn,
                    expected_state_version=current.state_version,
                    decisions=(decision,),
                ),
            )

        assert validate_history(save) == []
        rows = [
            entry.report().foreign_affairs.assistance[0]
            for entry in save.entries[1:]
            if entry.report() is not None
        ]
        assert [row.refusal_code for row in rows] == [
            None,
            "foreign_assistance_counterpart_is_hostile",
            None,
        ]
        # The pool depletes monotonically across the two accepted draws, and the second draw is
        # smaller because it takes a share of what is left rather than of the original capacity.
        assert rows[0].granted > rows[2].granted > 0
        assert rows[2].opening_drawn == rows[0].closing_drawn
        final = save.current_state().world.foreign_relationships["kessia"]
        assert final.assistance_drawn == rows[2].closing_drawn
