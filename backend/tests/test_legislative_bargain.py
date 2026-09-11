"""Buying one party leader's endorsement for one exact proposal.

Four claims are worth proving about this mechanic, and they are what this file is organised around.

* **There is no offer, and therefore no dominant strategy.** The decision carries three fields and
  none of them is money. Two earlier designs let the player name an offer -- first paying the
  leader's price for any offer at or above it, then paying the offer itself -- and both left the
  field with exactly one rational value, because the price is projected. The regression test is a
  set-equality assertion on `model_fields`, so *any* added field fails, not just a rediscovered
  `offered_capital`.
* **The endorsement is a second support channel, and it is consequential.** It is not capped by
  `MAX_INFLUENCE_BPS` -- that bounds direct bloc influence -- and the two combine as independent
  addends inside the existing `final` clamp. In `deficit_demo` a real budget fails 48/51 without it
  and passes 51/51 with it, through the real resolver, at the price a real leader really charges.
* **A refusal is an outcome, not an error.** A leader who will not deal resolves the turn normally,
  commits nothing, and produces a report row saying so. Its entry params are a strict subset of an
  acceptance's, omitting every monetary key, so no surface can quote a figure for an approach that
  cost nothing -- the last trace of the deleted counteroffer.
* **Reconciliation is an independent oracle.** Group 58 transcribes the price and gate formulas
  rather than calling the production assessment, because a check that calls the function which
  produced the report cannot fail when that function is wrong. An AST scan enforces the boundary.
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
from app.core.politics import clamp_bps, trunc_div_toward_zero
from app.simulation.decisions import (
    BudgetDecision,
    DecisionSet,
    LegislativeBargainDecision,
    SpendingUpdate,
)
from app.simulation.history import advance_game, new_game, validate_history
from app.simulation.legislative_bargaining import (
    LEGISLATIVE_BARGAIN_LOYALTY_REFUSAL_CEILING_BPS,
    LEGISLATIVE_BARGAIN_TRUST_OVERRIDE_BPS,
    LEGISLATIVE_ENDORSEMENT_BPS,
    asking_price_capital,
    assess_legislative_bargain,
    will_deal,
)
from app.simulation.legislative_voting import (
    MAX_INFLUENCE_BPS,
    PolicyChange,
    resolve_amendment_support,
    resolve_bloc_support,
)
from app.simulation.legislature import CapitalExpenditureCategory, ChangeDirection
from app.simulation.reconciliation import reconcile_political_legislative_and_survival_report
from app.simulation.report import BlocVoteReport, LegislativeBargainOutcome
from app.simulation.resolver import resolve_turn
from app.simulation.save_format import SAVE_FORMAT_VERSION
from app.simulation.state import LEGISLATIVE_PROPOSAL_DISPLAY_NAMES, RULESET_VERSION
from tests.conftest import SCENARIO_DIR

#: The two leaders who actually accept under the shipped gate, and the two who actually refuse.
#: Both refusal examples are real: illustrating a refusal with somebody who would in fact accept
#: would make the example unreachable from content and the assertion a fiction.
_ACCEPTS_TINY = "leader_rural_alliance"  # Maret Kuusk, price 105
_ACCEPTS_DEFICIT = "leader_independents"  # Sofia Renn, price 113
_REFUSES_DECREE = "leader_opposition_party"  # Nadia Brekke, loyalty 900 / trust 2100

_BARGAIN_MODULE = Path("app/simulation/legislative_bargaining.py")
_RECONCILIATION_MODULE = Path("app/simulation/reconciliation.py")


def _state(name: str):  # type: ignore[no-untyped-def]
    return load_scenario_file(SCENARIO_DIR / name)


def _bargain(state, character_id: str, *, proposal_kind: str = "budget", **extra):  # type: ignore[no-untyped-def]
    """A decision set carrying a legislative-route budget and a bargain over it.

    The budget is the minimum that is a real proposal: one spending line moved. `proposal_kind`
    defaults to `"budget"` because that is the target the shipped content can actually vote on.
    """
    decisions: list[object] = []
    budget = extra.pop("budget", None)
    if budget is not None:
        decisions.append(budget)
    decisions.append(
        LegislativeBargainDecision(character_id=character_id, proposal_kind=proposal_kind)
    )
    return DecisionSet(
        expected_turn=state.turn,
        expected_state_version=state.state_version,
        decisions=tuple(sorted(decisions, key=lambda d: d.kind)),  # type: ignore[attr-defined]
    )


def _budget(*, category: str = "health", amount: int) -> BudgetDecision:
    return BudgetDecision(
        route="legislative", spending_updates=(SpendingUpdate(category=category, amount=amount),)
    )


# --------------------------------------------------------------------------------------------
# The decision shape: three fields, and no money among them.
# --------------------------------------------------------------------------------------------


class TestTheDecisionCarriesNoMoney:
    def test_the_decision_has_exactly_three_fields(self) -> None:
        """Set EQUALITY, not a subset check and not an absence check for one remembered name.

        The defect this guards against is a re-added capital field under any spelling -- an
        `offered_capital`, a `maximum_price`, a `budget` -- so the assertion has to fail on any
        addition rather than on a denylist of the two names that happened to exist before.
        """
        assert set(LegislativeBargainDecision.model_fields) == {
            "kind",
            "character_id",
            "proposal_kind",
        }

    def test_there_are_exactly_two_outcomes_in_declaration_order(self) -> None:
        """Membership AND order: the values are serialised into `report_json` and hash-covered, so
        declaration order is canonical order and a reordering is a save-format change."""
        assert [member.value for member in LegislativeBargainOutcome] == [
            "accepted",
            "refused_will_not_deal",
        ]

    def test_the_deleted_band_outcomes_are_not_representable(self) -> None:
        """`counteroffered` and `refused_offer_too_low` were removed with the offer.

        Asserted against the enum rather than by grepping the tree: a repository-wide text search
        would fail on a code comment that merely mentions them (this file does) and would pass on a
        member added under a different spelling.
        """
        values = {member.value for member in LegislativeBargainOutcome}
        assert "counteroffered" not in values
        assert "refused_offer_too_low" not in values

    def test_at_most_one_bargain_per_decision_set(self) -> None:
        decision = LegislativeBargainDecision(character_id=_ACCEPTS_TINY, proposal_kind="budget")
        with pytest.raises(ValidationError, match="at most one legislative-bargain decision"):
            DecisionSet(expected_turn=0, expected_state_version=0, decisions=(decision, decision))

    def test_the_kind_sorts_between_amendment_and_movement(self) -> None:
        """Canonical kind order is ascending by `kind`; this is what keeps every already-serialised
        multi-kind `decisions_json` digesting identically."""
        existing = ["bloc_relationship_investment", "budget", "cabinet", "constitutional_amendment"]
        assert sorted([*existing, "legislative_bargain", "military_movement"]) == [
            *existing,
            "legislative_bargain",
            "military_movement",
        ]


# --------------------------------------------------------------------------------------------
# Price and gate.
# --------------------------------------------------------------------------------------------


class TestPriceAndGate:
    @pytest.mark.parametrize(
        ("independence", "ambition", "trust", "expected"),
        [
            (0, 0, 0, 60),
            (10_000, 10_000, 0, 200),
            (0, 0, 10_000, 1),  # the floor, and the only way to reach it
            (6_100, 4_400, 5_200, 105),  # Maret Kuusk
            (7_400, 3_900, 5_400, 113),  # Sofia Renn
        ],
    )
    def test_price_at_named_points(
        self, independence: int, ambition: int, trust: int, expected: int
    ) -> None:
        assert (
            asking_price_capital(
                independence_bps=independence,
                ambition_bps=ambition,
                personal_trust_bps=trust,
            )
            == expected
        )

    def test_price_is_integral_monotone_and_never_below_one(self) -> None:
        """A sweep rather than a handful of points, because the floor and the integer division are
        both places a float would hide."""
        for independence in range(0, 10_001, 250):
            for trust in range(0, 10_001, 500):
                price = asking_price_capital(
                    independence_bps=independence, ambition_bps=5_000, personal_trust_bps=trust
                )
                assert isinstance(price, int)
                assert price >= 1
        rising = [
            asking_price_capital(independence_bps=i, ambition_bps=0, personal_trust_bps=0)
            for i in range(0, 10_001, 1_000)
        ]
        assert rising == sorted(rising)
        falling = [
            asking_price_capital(independence_bps=10_000, ambition_bps=10_000, personal_trust_bps=t)
            for t in range(0, 10_001, 1_000)
        ]
        assert falling == sorted(falling, reverse=True)

    def test_the_gate_needs_both_conditions(self) -> None:
        """Two conditions with different subjects, which is what lets a later slice open a leader by
        moving trust alone."""
        below = LEGISLATIVE_BARGAIN_LOYALTY_REFUSAL_CEILING_BPS - 1
        assert will_deal(loyalty_bps=below, personal_trust_bps=0) is False
        # Disloyal, but the player's word has been good.
        assert (
            will_deal(loyalty_bps=below, personal_trust_bps=LEGISLATIVE_BARGAIN_TRUST_OVERRIDE_BPS)
            is True
        )
        # Loyal enough, regardless of trust.
        assert (
            will_deal(
                loyalty_bps=LEGISLATIVE_BARGAIN_LOYALTY_REFUSAL_CEILING_BPS, personal_trust_bps=0
            )
            is True
        )

    def test_loyalty_is_the_gate_and_never_the_price(self) -> None:
        """Money cannot buy a leader who will not deal, and loyalty does not make one cheaper."""
        cheap = asking_price_capital(
            independence_bps=1_000, ambition_bps=1_000, personal_trust_bps=0
        )
        assert (
            asking_price_capital(independence_bps=1_000, ambition_bps=1_000, personal_trust_bps=0)
            == cheap
        )
        refused = assess_legislative_bargain(
            loyalty_bps=0, independence_bps=0, ambition_bps=0, personal_trust_bps=0
        )
        assert refused.will_deal is False
        assert refused.asking_price is None

    def test_an_assessment_cannot_carry_a_price_and_a_refusal_together(self) -> None:
        from app.simulation.legislative_bargaining import LegislativeBargainAssessment

        with pytest.raises(ValueError, match="must carry an asking price"):
            LegislativeBargainAssessment(will_deal=True, asking_price=None)
        with pytest.raises(ValueError, match="must carry no asking price"):
            LegislativeBargainAssessment(will_deal=False, asking_price=99)


class TestShippedContent:
    """The authored table, leader by leader. If a scenario is ever retuned, this fails first."""

    @pytest.mark.parametrize(
        ("scenario", "character_id", "expected_deal", "expected_price"),
        [
            ("tiny_valid.yaml", "leader_national_front", False, None),
            ("tiny_valid.yaml", _ACCEPTS_TINY, True, 105),
            ("decree_state.yaml", _REFUSES_DECREE, False, None),
            ("deficit_demo.yaml", "leader_citizens_bloc", False, None),
            ("deficit_demo.yaml", _ACCEPTS_DEFICIT, True, 113),
        ],
    )
    def test_every_offered_leader_answers_as_authored(
        self, scenario: str, character_id: str, expected_deal: bool, expected_price: int | None
    ) -> None:
        character = _state(scenario).world.characters[character_id]
        assessment = assess_legislative_bargain(
            loyalty_bps=character.loyalty,
            independence_bps=character.independence,
            ambition_bps=character.ambition,
            personal_trust_bps=character.personal_trust,
        )
        assert assessment.will_deal is expected_deal
        assert assessment.asking_price == expected_price

    def test_decree_state_has_no_acceptable_counterparty(self) -> None:
        """A coherent statement about a decree state, recorded as a test so a later retune of its
        characters cannot quietly change it without a failure to explain."""
        options = build_decision_options(_state("decree_state.yaml"))
        assert options.legislative_bargain_counterparties
        assert not any(option.will_deal for option in options.legislative_bargain_counterparties)


# --------------------------------------------------------------------------------------------
# The two support channels.
# --------------------------------------------------------------------------------------------


class TestTheTwoSupportChannels:
    """Direct influence and a leader endorsement are independent addends inside one clamp.

    Numbers here are `deficit_demo`'s `independents/regional` on the demonstration budget:
    `raw = 6,710`, `discipline_bps = 1,000`.
    """

    _RAW_INPUTS = {
        "role": None,  # filled per-test from the scenario
    }

    @staticmethod
    def _regional_chain(capital: int, endorsement: int):  # type: ignore[no-untyped-def]
        state = _state("deficit_demo.yaml")
        legislature = state.world.countries[state.world.player_country_id].politics.legislature
        party = next(p for p in legislature.parties if p.id == "independents")
        bloc = party.blocs[0]
        return resolve_bloc_support(
            role=party.government_role,
            relationship_bps=bloc.government_relationship_bps,
            tax_change=PolicyChange(direction=ChangeDirection.DECREASE, intensity_bps=2_750),
            tax_preference_bps=bloc.tax_preference_bps,
            spending_change=PolicyChange(
                direction=ChangeDirection.INCREASE, intensity_bps=BPS_DENOMINATOR
            ),
            spending_preference_bps=bloc.spending_preference_bps,
            allocated_political_capital=capital,
            discipline_bps=bloc.discipline_bps,
            endorsement_bps=endorsement,
        )

    def test_neither_channel_alone_equals_the_pair(self) -> None:
        """200 capital of direct influence buys exactly what the endorsement buys in this bloc --
        and the two together are strictly more than either."""
        neither = self._regional_chain(0, 0)
        influence_only = self._regional_chain(200, 0)
        endorsement_only = self._regional_chain(0, LEGISLATIVE_ENDORSEMENT_BPS)
        assert neither.final_support_bps == 6_710
        assert influence_only.final_support_bps == 8_710
        assert endorsement_only.final_support_bps == 8_710
        both = self._regional_chain(200, LEGISLATIVE_ENDORSEMENT_BPS)
        assert both.final_support_bps > influence_only.final_support_bps

    def test_the_pair_saturates_at_the_existing_final_clamp(self) -> None:
        """`raw + influence + endorsement = 10,710` -- clamped, not overflowed. This is the real
        bound on the two channels, and it is why neither needs to be bounded against the other."""
        both = self._regional_chain(200, LEGISLATIVE_ENDORSEMENT_BPS)
        assert 6_710 + 2_000 + LEGISLATIVE_ENDORSEMENT_BPS == 10_710
        assert both.final_support_bps == BPS_DENOMINATOR
        assert both.effective_support_bps == BPS_DENOMINATOR

    def test_the_endorsement_is_not_capped_by_max_influence(self) -> None:
        """The influence term saturates at `MAX_INFLUENCE_BPS`; the endorsement passes through it
        untouched. The two bounds are independent, which is the whole point of the second channel.
        """
        saturated = self._regional_chain(300, LEGISLATIVE_ENDORSEMENT_BPS)
        assert saturated.influence_bps == MAX_INFLUENCE_BPS
        assert saturated.endorsement_bps == LEGISLATIVE_ENDORSEMENT_BPS
        assert LEGISLATIVE_ENDORSEMENT_BPS < MAX_INFLUENCE_BPS  # true today, and not relied upon

    def test_discipline_amplifies_the_endorsed_position(self) -> None:
        """The existing whip, applied to a `final` the endorsement moved: `8,710 -> 9,081`."""
        endorsed = self._regional_chain(0, LEGISLATIVE_ENDORSEMENT_BPS)
        expected = clamp_bps(
            8_710 + trunc_div_toward_zero((8_710 - 5_000) * 1_000, BPS_DENOMINATOR)
        )
        assert expected == 9_081
        assert endorsed.effective_support_bps == 9_081

    def test_zero_discipline_carries_the_endorsed_final_through_unamplified(self) -> None:
        support = resolve_amendment_support(
            role=next(
                p.government_role
                for p in _state("deficit_demo.yaml")
                .world.countries["strapped"]
                .politics.legislature.parties
                if p.id == "independents"
            ),
            relationship_bps=1_000,
            discipline_bps=0,
            allocated_political_capital=0,
            endorsement_bps=LEGISLATIVE_ENDORSEMENT_BPS,
        )
        assert support.effective_support_bps == support.final_support_bps

    def test_the_amendment_path_takes_the_endorsement_too(self) -> None:
        """Omitting it there would leave a bargain struck over an amendment paid for and inert."""
        without = resolve_amendment_support(
            role=next(
                p.government_role
                for p in _state("tiny_valid.yaml")
                .world.countries["arken"]
                .politics.legislature.parties
                if p.id == "rural_alliance"
            ),
            relationship_bps=2_000,
            discipline_bps=4_000,
            allocated_political_capital=0,
            endorsement_bps=0,
        )
        with_endorsement = resolve_amendment_support(
            role=next(
                p.government_role
                for p in _state("tiny_valid.yaml")
                .world.countries["arken"]
                .politics.legislature.parties
                if p.id == "rural_alliance"
            ),
            relationship_bps=2_000,
            discipline_bps=4_000,
            allocated_political_capital=0,
            endorsement_bps=LEGISLATIVE_ENDORSEMENT_BPS,
        )
        assert (
            with_endorsement.final_support_bps - without.final_support_bps
            == LEGISLATIVE_ENDORSEMENT_BPS
        )

    def test_a_bloc_vote_row_rejects_a_doubled_endorsement_the_clamp_would_have_hidden(
        self,
    ) -> None:
        """This is the case the clamped-sum check CANNOT catch, which is why the constant check
        exists beside it.

        `_bloc_vote_row` recomputes `final` and `effective` for whatever endorsement it is given, so
        a doubled `2 x 2,000` produces a row that is internally consistent in every other respect:
        `6,710 + 4,000 = 10,710` saturates at the `final` clamp to exactly the same 10,000 a legally
        endorsed high-support bloc could reach. Only the comparison against the constant itself
        separates them.
        """
        doubled = 2 * LEGISLATIVE_ENDORSEMENT_BPS
        assert clamp_bps(6_710 + doubled) == BPS_DENOMINATOR  # the clamp really does absorb it
        with pytest.raises(ValidationError, match="must be either 0 or exactly"):
            _bloc_vote_row(endorsement=doubled)

    def test_a_legal_endorsement_of_the_constant_is_accepted(self) -> None:
        """Anti-vacuity for the test above: the same builder, at the real constant, constructs."""
        assert (
            _bloc_vote_row(endorsement=LEGISLATIVE_ENDORSEMENT_BPS).endorsement_bps
            == LEGISLATIVE_ENDORSEMENT_BPS
        )
        assert _bloc_vote_row(endorsement=0).endorsement_bps == 0

    def test_a_bloc_vote_row_replays_its_own_clamped_sum(self) -> None:
        row = _bloc_vote_row(endorsement=LEGISLATIVE_ENDORSEMENT_BPS)
        payload = row.model_dump()
        payload["final_support_bps"] = row.final_support_bps - 1
        with pytest.raises(ValidationError, match="does not match clamp"):
            BlocVoteReport.model_validate(payload)


def _bloc_vote_row(*, endorsement: int) -> BlocVoteReport:
    """A minimal self-consistent bloc-vote row carrying `endorsement`."""
    raw = 6_710
    final = clamp_bps(raw + endorsement)
    effective = clamp_bps(final + trunc_div_toward_zero((final - 5_000) * 1_000, BPS_DENOMINATOR))
    numerator = 10 * effective
    return BlocVoteReport(
        party_id="independents",
        bloc_id="regional",
        chamber="lower",
        seats=10,
        government_role="confidence_and_supply",
        government_relationship_bps=1_000,
        discipline_bps=1_000,
        tax_preference_bps=-2_000,
        spending_preference_bps=2_000,
        baseline_support_bps=6_200,
        policy_compatibility_bps=510,
        raw_support_bps=raw,
        political_capital_allocated=0,
        influence_bps=0,
        endorsement_bps=endorsement,
        final_support_bps=final,
        effective_support_bps=effective,
        numerator=numerator,
        base_seats=numerator // BPS_DENOMINATOR,
        remainder=numerator % BPS_DENOMINATOR,
        bonus_seat=False,
        supporting_seats=numerator // BPS_DENOMINATOR,
    )


# --------------------------------------------------------------------------------------------
# End to end, through the real resolver.
# --------------------------------------------------------------------------------------------


_DEMO_BUDGET = BudgetDecision(
    route="legislative",
    personal_income_rate_bps=1_225,
    spending_updates=(SpendingUpdate(category="health", amount=220_000_000),),
)
"""`deficit_demo`'s demonstration proposal: a personal-rate cut and a health rise.

Chosen because it sits one bloc short of a majority without help, so the endorsement is what decides
it -- and because it is an ordinary budget a player would plausibly submit, not a contrivance.
"""


def _resolve(state, *decisions):  # type: ignore[no-untyped-def]
    return resolve_turn(
        state,
        DecisionSet(
            expected_turn=state.turn,
            expected_state_version=state.state_version,
            decisions=tuple(sorted(decisions, key=lambda d: d.kind)),
        ),
    )


class TestTheEndorsementDecidesARealVote:
    """The measured case, through the real engine rather than the pure functions."""

    def test_the_budget_fails_without_a_bargain(self) -> None:
        report = _resolve(_state("deficit_demo.yaml"), _DEMO_BUDGET).report
        chamber = report.legislative.chambers[0]
        assert (chamber.supporting_seats, chamber.required_yes_seats) == (48, 51)
        assert chamber.passed is False

    def test_the_same_budget_passes_with_the_endorsement(self) -> None:
        report = _resolve(
            _state("deficit_demo.yaml"),
            _DEMO_BUDGET,
            LegislativeBargainDecision(character_id=_ACCEPTS_DEFICIT, proposal_kind="budget"),
        ).report
        chamber = report.legislative.chambers[0]
        assert (chamber.supporting_seats, chamber.required_yes_seats) == (51, 51)
        assert chamber.passed is True
        row = report.legislative.bargains[0]
        assert row.character_display_name == "Sofia Renn"
        assert row.outcome is LegislativeBargainOutcome.ACCEPTED
        assert (row.asking_price, row.capital_committed) == (113, 113)
        assert row.endorsement_bps == LEGISLATIVE_ENDORSEMENT_BPS

    def test_the_constant_is_pinned_to_the_measurement_that_chose_it(self) -> None:
        """1,200 and 1,600 both leave this exact vote short; 2,000 carries it.

        Recomputed here from the report's own stored rows rather than re-running the engine at other
        constants, which cannot be done without editing the engine. If a future retune moves the
        constant below 1,600 this fails, which is the point: the number was measured, not chosen.
        """
        report = _resolve(
            _state("deficit_demo.yaml"),
            _DEMO_BUDGET,
            LegislativeBargainDecision(character_id=_ACCEPTS_DEFICIT, proposal_kind="budget"),
        ).report
        endorsed = [row for row in report.legislative.blocs if row.endorsement_bps > 0]
        assert endorsed, "the endorsed party must have at least one seated bloc"
        assert LEGISLATIVE_ENDORSEMENT_BPS >= 1_600

    def test_the_endorsement_reaches_every_bloc_of_the_party_and_no_other(self) -> None:
        report = _resolve(
            _state("deficit_demo.yaml"),
            _DEMO_BUDGET,
            LegislativeBargainDecision(character_id=_ACCEPTS_DEFICIT, proposal_kind="budget"),
        ).report
        for row in report.legislative.blocs:
            expected = LEGISLATIVE_ENDORSEMENT_BPS if row.party_id == "independents" else 0
            assert row.endorsement_bps == expected, (row.party_id, row.bloc_id)

    def test_the_endorsement_applies_once_per_chamber_not_cumulatively(self) -> None:
        """`tiny_valid` is bicameral and `rural_alliance/farmers` sits in BOTH chambers, so a
        cumulative application would show up as a doubled value in the second one."""
        report = _resolve(
            _state("tiny_valid.yaml"),
            _budget(amount=210_000_000),
            LegislativeBargainDecision(character_id=_ACCEPTS_TINY, proposal_kind="budget"),
        ).report
        farmers = [row for row in report.legislative.blocs if row.party_id == "rural_alliance"]
        assert {row.chamber.value for row in farmers} == {"lower", "upper"}
        assert all(row.endorsement_bps == LEGISLATIVE_ENDORSEMENT_BPS for row in farmers)

    def test_a_turn_with_no_bargain_shows_no_endorsement_anywhere(self) -> None:
        report = _resolve(_state("deficit_demo.yaml"), _DEMO_BUDGET).report
        assert report.legislative.bargains == ()
        assert all(row.endorsement_bps == 0 for row in report.legislative.blocs)
        assert not [
            row
            for row in report.political_capital.expenditures
            if row.category is CapitalExpenditureCategory.LEGISLATIVE_BARGAIN
        ]


class TestMoney:
    def test_the_price_is_paid_even_when_the_vote_is_lost(self) -> None:
        """A bargain buys a vote, not an outcome -- exactly as influence does."""
        hostile = BudgetDecision(
            route="legislative",
            personal_income_rate_bps=5_000,
            spending_updates=(SpendingUpdate(category="health", amount=1),),
        )
        report = _resolve(
            _state("deficit_demo.yaml"),
            hostile,
            LegislativeBargainDecision(character_id=_ACCEPTS_DEFICIT, proposal_kind="budget"),
        ).report
        assert report.legislative.chambers[0].passed is False
        row = report.legislative.bargains[0]
        assert row.outcome is LegislativeBargainOutcome.ACCEPTED
        assert row.capital_committed == 113
        ledger = [
            entry
            for entry in report.political_capital.expenditures
            if entry.category is CapitalExpenditureCategory.LEGISLATIVE_BARGAIN
        ]
        assert [entry.political_capital for entry in ledger] == [113]

    def test_a_refusal_commits_nothing_and_emits_no_ledger_row(self) -> None:
        report = _resolve(
            _state("deficit_demo.yaml"),
            _DEMO_BUDGET,
            LegislativeBargainDecision(character_id="leader_citizens_bloc", proposal_kind="budget"),
        ).report
        row = report.legislative.bargains[0]
        assert row.outcome is LegislativeBargainOutcome.REFUSED_WILL_NOT_DEAL
        assert row.asking_price is None
        assert (row.capital_committed, row.endorsement_bps) == (0, 0)
        assert not [
            entry
            for entry in report.political_capital.expenditures
            if entry.category is CapitalExpenditureCategory.LEGISLATIVE_BARGAIN
        ]

    def test_the_ledger_row_is_untargeted_and_carries_no_identity(self) -> None:
        """Identity lives on the bargain report; the ledger carries category and amount only."""
        report = _resolve(
            _state("deficit_demo.yaml"),
            _DEMO_BUDGET,
            LegislativeBargainDecision(character_id=_ACCEPTS_DEFICIT, proposal_kind="budget"),
        ).report
        row = next(
            entry
            for entry in report.political_capital.expenditures
            if entry.category is CapitalExpenditureCategory.LEGISLATIVE_BARGAIN
        )
        assert row.party_id is None and row.bloc_id is None
        assert report.legislative.bargains[0].character_id == _ACCEPTS_DEFICIT

    def test_the_category_is_declared_fifth_so_the_ledger_sort_is_unchanged(self) -> None:
        """Declaration order IS canonical order, and the ledger sorts on `category.value`."""
        values = [member.value for member in CapitalExpenditureCategory]
        assert values == sorted(values)
        assert values.index("legislative_bargain") == 4
        assert values[3:6] == ["decree", "legislative_bargain", "legislative_influence"]

    def test_the_affordability_message_names_all_five_terms(self) -> None:
        """`deficit_demo` opens on 300: Freya Lund costs 197 and Sofia Renn 113, so 310 is refused.

        Fully determined by authored traits, with no offer the player could have chosen differently,
        which is what makes it a stable boundary rather than a calibration that moves.
        """
        from app.simulation.decisions import CabinetDecision, CabinetOrder

        hire = CabinetDecision(
            orders=(CabinetOrder(post="chief_of_staff", character_id="freya_lund"),)
        )
        with pytest.raises(TurnResolutionError) as exc_info:
            _resolve(
                _state("deficit_demo.yaml"),
                hire,
                LegislativeBargainDecision(character_id=_ACCEPTS_DEFICIT, proposal_kind="budget"),
                _DEMO_BUDGET,
            )
        message = str(exc_info.value)
        assert "310" in message and "300" in message
        for term in (
            "route commitment",
            "relationship investment",
            "constitutional amendment",
            "cabinet appointment",
            "legislative bargain",
        ):
            assert term in message

    def test_the_cheaper_hire_plus_the_same_bargain_is_affordable(self) -> None:
        """Anti-vacuity for the boundary above: 147 + 113 = 260 resolves."""
        from app.simulation.decisions import CabinetDecision, CabinetOrder

        hire = CabinetDecision(
            orders=(CabinetOrder(post="chief_of_staff", character_id="bela_ronsard"),)
        )
        report = _resolve(
            _state("deficit_demo.yaml"),
            hire,
            LegislativeBargainDecision(character_id=_ACCEPTS_DEFICIT, proposal_kind="budget"),
            _DEMO_BUDGET,
        ).report
        assert report.legislative.bargains[0].capital_committed == 113


# --------------------------------------------------------------------------------------------
# Submission rejection: six codes, fixed precedence, and preflight parity.
# --------------------------------------------------------------------------------------------


def _decisions(state, *decisions):  # type: ignore[no-untyped-def]
    return DecisionSet(
        expected_turn=state.turn,
        expected_state_version=state.state_version,
        decisions=tuple(sorted(decisions, key=lambda d: d.kind)),
    )


def _no_legislature(state):  # type: ignore[no-untyped-def]
    """The same state with no legislature, and a constitution that agrees there is none.

    The only way to reach `legislative_bargain_party_not_in_legislature` at all: every scenario's
    authored characters lead parties that really exist, which `simulation.invariants` enforces, so
    the reachable form of "that party is not in this legislature" is "there is no legislature".

    The constitution has to move with the state or `legislature_required_by_constitution` refuses
    the input before slot 1 is ever reached -- which is itself the right behaviour, and is why this
    helper changes both rather than only the one field the test is about.
    """
    from app.simulation.constitution import Legislature

    player = state.world.countries[state.world.player_country_id]
    constitution = player.politics.constitution.model_copy(update={"legislature": Legislature.NONE})
    politics = player.politics.model_copy(
        update={"legislature": None, "constitution": constitution}
    )
    countries = dict(state.world.countries)
    countries[player.id] = player.model_copy(update={"politics": politics})
    return state.model_copy(
        update={"world": state.world.model_copy(update={"countries": countries})}
    )


class TestSubmissionRejection:
    @pytest.mark.parametrize(
        ("scenario", "character_id", "expected_code"),
        [
            ("tiny_valid.yaml", "nobody_at_all", "legislative_bargain_character_unknown"),
            ("tiny_valid.yaml", "leader_kessia", "legislative_bargain_character_not_domestic"),
            ("tiny_valid.yaml", "hal_verrin", "legislative_bargain_character_leads_no_party"),
            ("tiny_valid.yaml", "leader_civic_union", "legislative_bargain_party_is_in_government"),
        ],
    )
    def test_each_code_is_reachable_from_shipped_content(
        self, scenario: str, character_id: str, expected_code: str
    ) -> None:
        state = _state(scenario)
        decision_set = _decisions(
            state,
            _budget(amount=210_000_000),
            LegislativeBargainDecision(character_id=character_id, proposal_kind="budget"),
        )
        with pytest.raises(TurnResolutionError, match=expected_code):
            resolve_turn(state, decision_set)
        problem = first_decision_problem(state, decision_set)
        assert problem is not None and problem.code == expected_code

    def test_an_absent_legislature_reports_the_party_code(self) -> None:
        """`decree_state`, because a country with no legislature still needs a legal route for the
        proposal the bargain names -- and it is the one shipped scenario with unlimited decree
        authority."""
        state = _no_legislature(_state("decree_state.yaml"))
        decree_budget = BudgetDecision(
            route="decree",
            spending_updates=(SpendingUpdate(category="health", amount=210_000_000),),
        )
        decision_set = _decisions(
            state,
            LegislativeBargainDecision(character_id=_REFUSES_DECREE, proposal_kind="budget"),
            decree_budget,
        )
        with pytest.raises(
            TurnResolutionError, match="legislative_bargain_party_not_in_legislature"
        ):
            resolve_turn(state, decision_set)
        problem = first_decision_problem(state, decision_set)
        assert problem is not None
        assert problem.code == "legislative_bargain_party_not_in_legislature"

    def test_a_bargain_over_an_absent_proposal_is_rejected(self) -> None:
        """`proposal_kind` is an assertion of intent: this is a client that bargained for an
        amendment while the set carries a budget, buying support for the wrong vote."""
        state = _state("tiny_valid.yaml")
        decision_set = _decisions(
            state,
            _budget(amount=210_000_000),
            LegislativeBargainDecision(
                character_id=_ACCEPTS_TINY, proposal_kind="constitutional_amendment"
            ),
        )
        with pytest.raises(TurnResolutionError, match="legislative_bargain_proposal_absent"):
            resolve_turn(state, decision_set)
        problem = first_decision_problem(state, decision_set)
        assert problem is not None and problem.code == "legislative_bargain_proposal_absent"

    def test_an_unknown_id_is_reported_before_affiliation(self) -> None:
        """Code 1 before 2: an unknown id has no affiliation to test."""
        state = _state("tiny_valid.yaml")
        problem = first_decision_problem(
            state,
            _decisions(
                state,
                _budget(amount=210_000_000),
                LegislativeBargainDecision(character_id="nobody_at_all", proposal_kind="budget"),
            ),
        )
        assert problem is not None and problem.code == "legislative_bargain_character_unknown"

    def test_a_foreign_leader_is_reported_as_foreign_not_as_partyless(self) -> None:
        """Code 2 before 3, on a character that genuinely violates both: a foreign profile's leader
        has no `party_id`, so a naive order would blame the wrong thing."""
        state = _state("tiny_valid.yaml")
        assert state.world.characters["leader_kessia"].party_id is None
        problem = first_decision_problem(
            state,
            _decisions(
                state,
                _budget(amount=210_000_000),
                LegislativeBargainDecision(character_id="leader_kessia", proposal_kind="budget"),
            ),
        )
        assert problem is not None
        assert problem.code == "legislative_bargain_character_not_domestic"

    def test_a_governing_leader_is_reported_before_an_absent_proposal(self) -> None:
        """Code 5 before 6: a request naming somebody who has nothing to sell should say so before
        it complains about the target."""
        state = _state("tiny_valid.yaml")
        problem = first_decision_problem(
            state,
            _decisions(
                state,
                _budget(amount=210_000_000),
                LegislativeBargainDecision(
                    character_id="leader_civic_union", proposal_kind="constitutional_amendment"
                ),
            ),
        )
        assert problem is not None
        assert problem.code == "legislative_bargain_party_is_in_government"

    def test_a_gate_refusal_is_not_a_submission_rejection(self) -> None:
        """The ruling, asserted on every shipped leader who fails the gate: the approach is legal,
        previews clean, resolves normally and produces a row."""
        for scenario, character_id in (
            ("tiny_valid.yaml", "leader_national_front"),
            ("decree_state.yaml", _REFUSES_DECREE),
            ("deficit_demo.yaml", "leader_citizens_bloc"),
        ):
            state = _state(scenario)
            decision_set = _decisions(
                state,
                _budget(amount=1_000_000),
                LegislativeBargainDecision(character_id=character_id, proposal_kind="budget"),
            )
            assert first_decision_problem(state, decision_set) is None, scenario
            report = resolve_turn(state, decision_set).report
            row = report.legislative.bargains[0]
            assert row.outcome is LegislativeBargainOutcome.REFUSED_WILL_NOT_DEAL
            assert row.capital_committed == 0


# --------------------------------------------------------------------------------------------
# The projected counterparty, and the surfaces that render an outcome.
# --------------------------------------------------------------------------------------------


class TestTheProjection:
    @pytest.mark.parametrize(
        "scenario", ["tiny_valid.yaml", "decree_state.yaml", "deficit_demo.yaml"]
    )
    def test_price_and_refusal_are_exclusive_on_every_shipped_counterparty(
        self, scenario: str
    ) -> None:
        for option in build_decision_options(_state(scenario)).legislative_bargain_counterparties:
            if option.will_deal:
                assert option.asking_price is not None and option.refusal_reason is None
            else:
                # The whole point: a leader who will never deal is shown NO payable-looking price.
                assert option.asking_price is None
                assert option.refusal_reason == "refused_will_not_deal"

    def test_the_exclusive_shape_is_enforced_not_merely_intended(self) -> None:
        from app.api.projections import LegislativeBargainCounterpartyOption

        base = {
            "character_id": "x",
            "display_name": "X",
            "party_id": "p",
            "party_display_name": "P",
            "loyalty_bps": 0,
            "independence_bps": 0,
            "ambition_bps": 0,
            "personal_trust_bps": 0,
        }
        with pytest.raises(ValidationError, match="willing counterparty"):
            LegislativeBargainCounterpartyOption(**base, will_deal=True, asking_price=None)
        with pytest.raises(ValidationError, match="unwilling counterparty"):
            LegislativeBargainCounterpartyOption(
                **base, will_deal=False, asking_price=105, refusal_reason="refused_will_not_deal"
            )

    def test_coalition_leaders_are_absent_rather_than_listed_as_refusing(self) -> None:
        """Being in government is a structural fact about the PARTY. Listing its leader as a
        refusal would state a falsehood about a person."""
        options = build_decision_options(_state("tiny_valid.yaml"))
        listed = {option.character_id for option in options.legislative_bargain_counterparties}
        assert "leader_civic_union" not in listed
        assert {_ACCEPTS_TINY, "leader_national_front"} <= listed

    def test_traits_are_carried_even_for_a_leader_who_will_not_deal(self) -> None:
        """They explain WHY, and what would have to change -- facts about the person, not a
        quotation."""
        options = build_decision_options(_state("decree_state.yaml"))
        refuser = next(
            option
            for option in options.legislative_bargain_counterparties
            if option.character_id == _REFUSES_DECREE
        )
        assert refuser.loyalty_bps == 900
        assert refuser.personal_trust_bps == 2_100

    def test_the_preview_quotes_the_price_the_resolver_charges(self) -> None:
        state = _state("deficit_demo.yaml")
        projection = preview_decisions(
            state,
            _decisions(
                state,
                _DEMO_BUDGET,
                LegislativeBargainDecision(character_id=_ACCEPTS_DEFICIT, proposal_kind="budget"),
            ),
        )
        assert projection.legislative_bargain_capital == 113
        assert projection.would_pass is True

    def test_the_preview_charges_nothing_for_an_approach_that_will_be_refused(self) -> None:
        state = _state("deficit_demo.yaml")
        projection = preview_decisions(
            state,
            _decisions(
                state,
                _DEMO_BUDGET,
                LegislativeBargainDecision(
                    character_id="leader_citizens_bloc", proposal_kind="budget"
                ),
            ),
        )
        assert projection.legislative_bargain_capital == 0
        assert projection.would_pass is False


class TestRenderedSentences:
    def test_the_accepted_sentence_is_exact(self) -> None:
        report = _resolve(
            _state("tiny_valid.yaml"),
            _budget(amount=210_000_000),
            LegislativeBargainDecision(character_id=_ACCEPTS_TINY, proposal_kind="budget"),
        ).report
        entry = next(e for e in report.entries if e.reason_id == "legislative_bargain_accepted")
        assert render_entry(entry) == (
            "Maret Kuusk of the Rural Alliance backed the budget, for 105 political capital."
        )

    def test_the_refused_sentence_is_exact_and_names_no_figure(self) -> None:
        """Asserted with the leader who genuinely refuses under the gate, not with an accepting one
        forced into a refusal."""
        report = _resolve(
            _state("decree_state.yaml"),
            _budget(amount=210_000_000),
            LegislativeBargainDecision(character_id=_REFUSES_DECREE, proposal_kind="budget"),
        ).report
        entry = next(
            e for e in report.entries if e.reason_id == "legislative_bargain_refused_will_not_deal"
        )
        assert render_entry(entry) == (
            "Nadia Brekke of the Reform Opposition would not deal over the budget."
        )

    def test_the_refused_entry_has_no_field_a_price_could_travel_in(self) -> None:
        """Set EQUALITY against the six identity keys, so a newly added monetary key fails here
        rather than leaking into a sentence."""
        report = _resolve(
            _state("decree_state.yaml"),
            _budget(amount=210_000_000),
            LegislativeBargainDecision(character_id=_REFUSES_DECREE, proposal_kind="budget"),
        ).report
        entry = next(
            e for e in report.entries if e.reason_id == "legislative_bargain_refused_will_not_deal"
        )
        assert set(entry.params) == {
            "character_id",
            "character_display_name",
            "party_id",
            "party_display_name",
            "proposal_kind",
            "proposal_display_name",
        }

    def test_both_reason_ids_have_renderers(self) -> None:
        for reason_id in (
            "legislative_bargain_accepted",
            "legislative_bargain_refused_will_not_deal",
        ):
            assert reason_id in REASON_RENDERERS

    def test_no_surface_transforms_a_proposal_identifier_into_prose(self) -> None:
        """The label is authored once in `state`, exactly as post labels are."""
        assert LEGISLATIVE_PROPOSAL_DISPLAY_NAMES == {
            "budget": "the budget",
            "constitutional_amendment": "the constitutional amendment",
        }
        report = _resolve(
            _state("tiny_valid.yaml"),
            _budget(amount=210_000_000),
            LegislativeBargainDecision(character_id=_ACCEPTS_TINY, proposal_kind="budget"),
        ).report
        entry = next(e for e in report.entries if e.reason_id == "legislative_bargain_accepted")
        sentence = render_entry(entry)
        for raw in ("legislative_bargain", "rural_alliance", "leader_rural_alliance"):
            assert raw not in sentence


# --------------------------------------------------------------------------------------------
# Group 58: an INDEPENDENT oracle.
# --------------------------------------------------------------------------------------------


_ALLOWED_BARGAIN_IMPORTS = frozenset(
    {
        "LEGISLATIVE_BARGAIN_AMBITION_PRICE_MAX",
        "LEGISLATIVE_BARGAIN_BASE_PRICE",
        "LEGISLATIVE_BARGAIN_INDEPENDENCE_PRICE_MAX",
        "LEGISLATIVE_BARGAIN_LOYALTY_REFUSAL_CEILING_BPS",
        "LEGISLATIVE_BARGAIN_TRUST_DISCOUNT_MAX",
        "LEGISLATIVE_BARGAIN_TRUST_OVERRIDE_BPS",
        "LEGISLATIVE_ENDORSEMENT_BPS",
    }
)
"""What `reconciliation.py` may take from `legislative_bargaining`: CONSTANTS, and nothing else.

An ALLOWLIST rather than a denylist of the three function names, deliberately. A denylist would
silently permit a newly added helper -- `price_for`, `assess_v2` -- which is exactly how this
boundary would erode. Anything not named here fails by default and has to be argued for.
"""


class TestGroup58IsIndependent:
    """Reconciliation must not check the engine's arithmetic by asking the engine.

    A group that called `assess_legislative_bargain` could not fail when that function is wrong: it
    would compute the same wrong answer and certify it. Sharing the CONSTANTS is different in kind
    -- one number both sides read, so a transcription error in the formula still surfaces.
    """

    def test_reconciliation_imports_only_constants_from_the_bargaining_module(self) -> None:
        tree = ast.parse(_RECONCILIATION_MODULE.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module == "app.simulation.legislative_bargaining"
            ):
                imported.update(alias.name for alias in node.names)
        assert imported, "reconciliation is expected to import the calibration constants"
        assert imported <= _ALLOWED_BARGAIN_IMPORTS, sorted(imported - _ALLOWED_BARGAIN_IMPORTS)

    def test_reconciliation_never_calls_the_production_assessment(self) -> None:
        forbidden = {"assess_legislative_bargain", "asking_price_capital", "will_deal"}
        tree = ast.parse(_RECONCILIATION_MODULE.read_text(encoding="utf-8"))
        called = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert not (called & forbidden), sorted(called & forbidden)

    def test_the_scan_detects_a_call_when_one_is_present(self) -> None:
        """Anti-vacuity: a scan that matches nothing would pass no matter what the module did."""
        sample = ast.parse(
            "from app.simulation.legislative_bargaining import will_deal\n"
            "x = will_deal(loyalty_bps=0, personal_trust_bps=0)\n"
        )
        called = {
            node.func.id
            for node in ast.walk(sample)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "will_deal" in called

    def test_the_transcription_agrees_with_the_engine_across_a_sweep(self) -> None:
        """Two implementations, one answer. If they ever disagree the sweep says so here rather
        than a save silently reconciling against a wrong number."""
        from app.simulation.reconciliation import (
            _transcribed_bargain_price,
            _transcribed_bargain_will_deal,
        )

        for independence in range(0, 10_001, 1_250):
            for ambition in range(0, 10_001, 2_500):
                for trust in range(0, 10_001, 1_250):
                    assert _transcribed_bargain_price(
                        independence_bps=independence,
                        ambition_bps=ambition,
                        personal_trust_bps=trust,
                    ) == asking_price_capital(
                        independence_bps=independence,
                        ambition_bps=ambition,
                        personal_trust_bps=trust,
                    )
        for loyalty in range(0, 10_001, 500):
            for trust in range(0, 10_001, 500):
                assert _transcribed_bargain_will_deal(
                    loyalty_bps=loyalty, personal_trust_bps=trust
                ) == will_deal(loyalty_bps=loyalty, personal_trust_bps=trust)


def _reconciled(scenario: str, *decisions):  # type: ignore[no-untyped-def]
    """Resolve, then hand reconciliation the real opening/closing states and submitted set."""
    state = _state(scenario)
    decision_set = _decisions(state, *decisions)
    resolution = resolve_turn(state, decision_set)
    return state, resolution, decision_set


class TestGroup58Tampers:
    def test_an_untampered_turn_reconciles_clean(self) -> None:
        """Anti-vacuity for every tamper below."""
        state, resolution, decision_set = _reconciled(
            "deficit_demo.yaml",
            _DEMO_BUDGET,
            LegislativeBargainDecision(character_id=_ACCEPTS_DEFICIT, proposal_kind="budget"),
        )
        assert (
            reconcile_political_legislative_and_survival_report(
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
            ("asking_price", 1),
            ("capital_committed", 1),
            ("endorsement_bps", 0),
            ("character_display_name", "Somebody Else"),
            ("party_display_name", "Another Party"),
            ("proposal_display_name", "the amendment"),
        ],
    )
    def test_a_forged_bargain_row_field_is_caught(self, field: str, value: object) -> None:
        state, resolution, decision_set = _reconciled(
            "deficit_demo.yaml",
            _DEMO_BUDGET,
            LegislativeBargainDecision(character_id=_ACCEPTS_DEFICIT, proposal_kind="budget"),
        )
        report = resolution.report
        row = report.legislative.bargains[0]
        # `model_copy`, not `model_construct` over `model_dump()`: dumping would turn every nested
        # report into a plain dict and the tamper would fail for the wrong reason. Validation is
        # deliberately skipped -- the row's own validators would refuse most of these, and the point
        # is that reconciliation catches a row forged directly into a save.
        forged_row = row.model_copy(update={field: value})
        forged_legislative = report.legislative.model_copy(update={"bargains": (forged_row,)})
        forged = report.model_copy(update={"legislative": forged_legislative})
        problems = reconcile_political_legislative_and_survival_report(
            opening_state=state,
            closing_state=resolution.state,
            report=forged,
            decisions=decision_set,
        )
        assert any("group 58" in problem for problem in problems), problems

    def test_a_turn_that_reports_a_bargain_it_never_submitted_is_caught(self) -> None:
        state, resolution, _ = _reconciled(
            "deficit_demo.yaml",
            _DEMO_BUDGET,
            LegislativeBargainDecision(character_id=_ACCEPTS_DEFICIT, proposal_kind="budget"),
        )
        quiet = DecisionSet(
            expected_turn=state.turn,
            expected_state_version=state.state_version,
            decisions=(_DEMO_BUDGET,),
        )
        problems = reconcile_political_legislative_and_survival_report(
            opening_state=state,
            closing_state=resolution.state,
            report=resolution.report,
            decisions=quiet,
        )
        assert any("group 58" in problem for problem in problems), problems


class TestTrustIsReadNeverWritten:
    @pytest.mark.parametrize("character_id", [_ACCEPTS_DEFICIT, "leader_citizens_bloc"])
    def test_the_character_registry_is_byte_identical_across_both_outcomes(
        self, character_id: str
    ) -> None:
        """This slice reads `personal_trust` and never writes it; a later slice is the only writer.
        Asserted for an acceptance AND a refusal, since either could plausibly have been made to
        move it."""
        state = _state("deficit_demo.yaml")
        resolution = _resolve(
            state,
            _DEMO_BUDGET,
            LegislativeBargainDecision(character_id=character_id, proposal_kind="budget"),
        )
        assert resolution.state.world.characters == state.world.characters


# --------------------------------------------------------------------------------------------
# Compatibility: two proofs, each falsifiable on its own.
# --------------------------------------------------------------------------------------------


_BARGAIN_FIXTURE = Path(__file__).parent / "fixtures" / "bargain_save_ruleset_0.19.0.json"
"""The authentic ruleset-0.19.0 save frozen in commit 4b, from the engine as it stood BEFORE this
mechanic existed. Never regenerated: a fixture reproduced under the current engine would make the
proofs below pass for the wrong reason."""


class TestCompatibility:
    """The version gate and the payload shape are SEPARATE claims, and one test cannot establish
    both -- a save rejected on its version never reaches the parser, so a passing version test says
    nothing about whether the payload would have failed."""

    def test_the_fixture_really_predates_this_ruleset(self) -> None:
        raw = json.loads(_BARGAIN_FIXTURE.read_text(encoding="utf-8"))
        assert raw["ruleset_version"] == "0.19.0"
        assert raw["ruleset_version"] != RULESET_VERSION
        assert RULESET_VERSION == "0.20.0"

    def _one_stored_bloc_row(self) -> dict[str, object]:
        raw = json.loads(_BARGAIN_FIXTURE.read_text(encoding="utf-8"))
        for entry in raw["entries"]:
            payload = entry.get("report_json")
            if not payload:
                continue
            document = json.loads(payload) if isinstance(payload, str) else payload
            legislative = document.get("legislative")
            if legislative and legislative.get("blocs"):
                return dict(legislative["blocs"][0])
        raise AssertionError("the fixture is expected to carry a real bloc-vote row")

    def test_proof_a_the_payload_fails_specifically_on_the_missing_field(self) -> None:
        """Bypasses the version gate entirely and parses one stored row under the NEW model.

        Asserts the specific error -- type `missing`, location `endorsement_bps` -- rather than
        "some ValidationError", because a test that accepted any failure would keep passing if the
        payload later broke for an unrelated reason, which is the false green this exists to stop.
        """
        stored = self._one_stored_bloc_row()
        assert "endorsement_bps" not in stored
        with pytest.raises(ValidationError) as exc_info:
            BlocVoteReport.model_validate(stored)
        errors = exc_info.value.errors()
        assert [error["type"] for error in errors] == ["missing"]
        assert [error["loc"] for error in errors] == [("endorsement_bps",)]

    def test_proof_a_anti_vacuity_the_single_field_is_the_whole_incompatibility(self) -> None:
        """The same row parses cleanly once `endorsement_bps` is supplied.

        The zero is injected into a LOCAL COPY. The production model must never gain a default: a
        default would make every stored 0.19.0 row load and quietly assert that a turn resolved
        before this mechanic existed had "no endorsement" -- a claim about a vote nobody could have
        influenced.
        """
        stored = self._one_stored_bloc_row()
        row = BlocVoteReport.model_validate(stored | {"endorsement_bps": 0})
        assert row.endorsement_bps == 0
        assert BlocVoteReport.model_fields["endorsement_bps"].is_required()

    def test_proof_b_the_version_rejection_happens_before_any_parsing(self) -> None:
        """Every payload is replaced with text that is not even valid JSON, and the envelope is left
        at 0.19.0. A clean ruleset rejection is only possible if the version check runs FIRST -- and
        because the payloads are unparseable, this cannot pass by accident on a build where the
        order is reversed.
        """
        from app.core.errors import UnsupportedRulesetVersionError
        from app.simulation.save_format import load_save_json

        raw = json.loads(_BARGAIN_FIXTURE.read_text(encoding="utf-8"))
        for entry in raw["entries"]:
            if "state_json" in entry:
                entry["state_json"] = "{definitely not json"
            if entry.get("report_json") is not None:
                entry["report_json"] = "{definitely not json"
        with pytest.raises(UnsupportedRulesetVersionError) as exc_info:
            load_save_json(json.dumps(raw), source="corrupted-but-still-incompatible")
        message = str(exc_info.value)
        assert "0.19.0" in message and RULESET_VERSION in message

    def test_the_fixture_is_never_regenerated_under_the_current_engine(self) -> None:
        """Its rows must still be in the pre-change shape, or the two proofs above are hollow."""
        raw = json.loads(_BARGAIN_FIXTURE.read_text(encoding="utf-8"))
        rows = []
        for entry in raw["entries"]:
            payload = entry.get("report_json")
            if not payload:
                continue
            document = json.loads(payload) if isinstance(payload, str) else payload
            legislative = document.get("legislative")
            if legislative:
                rows.extend(legislative.get("blocs", []))
        assert len(rows) == 10
        assert not any("endorsement_bps" in row for row in rows)


class TestSaveAndReplay:
    def test_a_multi_turn_campaign_that_bargains_and_is_refused_validates(self) -> None:
        """The whole loop through the real history layer: a turn that buys an endorsement, a turn
        that is turned down, and a quiet turn -- with the hash chain intact at the end."""
        save = new_game(_state("deficit_demo.yaml"), save_format_version=SAVE_FORMAT_VERSION)
        accepted = DecisionSet(
            expected_turn=save.current_state().turn,
            expected_state_version=save.current_state().state_version,
            decisions=tuple(
                sorted(
                    [
                        _DEMO_BUDGET,
                        LegislativeBargainDecision(
                            character_id=_ACCEPTS_DEFICIT, proposal_kind="budget"
                        ),
                    ],
                    key=lambda d: d.kind,
                )
            ),
        )
        save = advance_game(save, accepted)
        current = save.current_state()
        refused = DecisionSet(
            expected_turn=current.turn,
            expected_state_version=current.state_version,
            decisions=tuple(
                sorted(
                    [
                        _budget(amount=155_000_000),
                        LegislativeBargainDecision(
                            character_id="leader_citizens_bloc", proposal_kind="budget"
                        ),
                    ],
                    key=lambda d: d.kind,
                )
            ),
        )
        save = advance_game(save, refused)
        current = save.current_state()
        save = advance_game(
            save,
            DecisionSet(
                expected_turn=current.turn,
                expected_state_version=current.state_version,
                decisions=(),
            ),
        )

        assert validate_history(save) == []
        outcomes = [
            entry.report().legislative.bargains
            for entry in save.entries[1:]
            if entry.report() is not None
        ]
        assert [row[0].outcome for row in outcomes if row] == [
            LegislativeBargainOutcome.ACCEPTED,
            LegislativeBargainOutcome.REFUSED_WILL_NOT_DEAL,
        ]
        assert outcomes[-1] == ()
