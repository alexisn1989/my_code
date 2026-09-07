"""Government structure as an input to violent-removal risk (ruleset 0.17.0).

Coups and popular uprisings used to be the one removal channel that could not see what kind of
government it was removing: identical loyalty, legitimacy, opposition and population mood produced
identical risk under a hereditary monarchy ruling by decree and under an accountable electoral
republic. `structural_removal_exposure_bps` closes that, and this file proves the four things that
claim has to survive:

* the **truth table** is what the design says it is, over REAL `ConstitutionState` objects, so the
  ten validity rules are exercised rather than assumed and no case here is a combination the engine
  would refuse;
* **matched conditions** -- everything except the constitution held equal -- separate structure
  from scenario differences, which is the only way to show a regime effect rather than a
  confounded one;
* the **exceptions** hold: a saturated cap does not move, and where conditional success is zero a
  higher attempt rate produces more attempts and no removals;
* the existing conditions still **work in both directions within either structure**, so a
  dictatorship that earns its army's loyalty is safer and a democracy that loses it is not.

`is_noncompetitive_constitution` is deliberately NOT reused, and this file pins why: it treats any
non-`NONE` decree authority as noncompetitive, which would classify two of the three shipped
scenarios -- both accountable electoral governments -- as dictatorships.
"""

from __future__ import annotations

import pytest

from app.content.scenarios import load_scenario_file
from app.simulation.constitution import (
    AmendmentDifficulty,
    ConstitutionState,
    DecreeAuthority,
    ExecutiveSelection,
    ExecutiveSystem,
    JudicialReview,
    Legislature,
    TerritorialOrganization,
)
from app.simulation.government_survival import (
    COUP_STRUCTURAL_WEIGHT_BPS,
    ELECTED_WITHOUT_SCHEDULED_ELECTION_EXPOSURE_BPS,
    EMERGENCY_DECREE_EXPOSURE_BPS,
    MAX_COUP_ATTEMPT_RISK_BPS,
    MAX_STRUCTURAL_EXPOSURE_BPS,
    MAX_UNREST_ATTEMPT_RISK_BPS,
    NO_JUDICIAL_REVIEW_EXPOSURE_BPS,
    NO_LEGISLATURE_EXPOSURE_BPS,
    UNELECTED_EXECUTIVE_EXPOSURE_BPS,
    UNLIMITED_DECREE_EXPOSURE_BPS,
    UNREST_STRUCTURAL_WEIGHT_BPS,
    WEAK_JUDICIAL_REVIEW_EXPOSURE_BPS,
    coup_attempt_risk_bps,
    coup_success_probability_bps,
    is_noncompetitive_constitution,
    structural_removal_exposure_bps,
    unrest_attempt_risk_bps,
)
from tests.conftest import SCENARIO_DIR


def _exposure(constitution: ConstitutionState):  # type: ignore[no-untyped-def]
    """Always routed through a real, VALIDATED `ConstitutionState`, never loose enums -- so every
    case below is a constitution the engine would actually accept."""
    return structural_removal_exposure_bps(
        executive_selection=constitution.executive_selection,
        decree_authority=constitution.decree_authority,
        legislature=constitution.legislature,
        judicial_review=constitution.judicial_review,
        national_election_interval_turns=constitution.national_election_interval_turns,
    )


# --- The truth table, as real constitutions -------------------------------------------------

ACCOUNTABLE_DEMOCRACY = ConstitutionState(
    executive_system=ExecutiveSystem.PRESIDENTIAL,
    executive_selection=ExecutiveSelection.DIRECT_ELECTION,
    legislature=Legislature.BICAMERAL,
    territorial_organization=TerritorialOrganization.UNITARY,
    judicial_review=JudicialReview.STRONG,
    amendment_difficulty=AmendmentDifficulty.SUPERMAJORITY,
    decree_authority=DecreeAuthority.NONE,
    executive_term_limit_terms=2,
    national_election_interval_turns=16,
)
"""The zero point: elected, on a schedule, with a legislature, strong courts and no decree power.
Nothing about this shape adds risk, which is what makes every other number below a comparison
rather than an absolute."""

EMERGENCY_POWERS_DEMOCRACY = ACCOUNTABLE_DEMOCRACY.model_copy(
    update={"decree_authority": DecreeAuthority.EMERGENCY_ONLY}
)
"""The case the design exists to get right. `is_noncompetitive_constitution` calls this
noncompetitive; the structural policy charges it 500 of a possible 10,000."""

CONSTRAINED_MONARCHY = ConstitutionState(
    executive_system=ExecutiveSystem.MONARCHICAL,
    executive_selection=ExecutiveSelection.HEREDITARY,
    legislature=Legislature.UNICAMERAL,
    territorial_organization=TerritorialOrganization.UNITARY,
    judicial_review=JudicialReview.STRONG,
    amendment_difficulty=AmendmentDifficulty.SUPERMAJORITY,
    decree_authority=DecreeAuthority.NONE,
)
"""A hereditary head of state who cannot legislate alone, sits with a chamber, and answers to
strong courts. Unaccountable to voters and constrained by everything else."""

UNRESTRICTED_PERSONAL_RULE = ConstitutionState(
    executive_system=ExecutiveSystem.MONARCHICAL,
    executive_selection=ExecutiveSelection.HEREDITARY,
    legislature=Legislature.NONE,
    territorial_organization=TerritorialOrganization.UNITARY,
    judicial_review=JudicialReview.NONE,
    amendment_difficulty=AmendmentDifficulty.ENTRENCHED,
    decree_authority=DecreeAuthority.UNLIMITED,
)
"""The saturated endpoint. Note it CANNOT be authored any other way: rule C10 requires unlimited
decree wherever the legislature is absent, so 'no chamber' always arrives with 'rules alone'."""

ELECTED_BUT_NEVER_SCHEDULED = ConstitutionState(
    executive_system=ExecutiveSystem.PRESIDENTIAL,
    executive_selection=ExecutiveSelection.DIRECT_ELECTION,
    legislature=Legislature.UNICAMERAL,
    territorial_organization=TerritorialOrganization.UNITARY,
    judicial_review=JudicialReview.WEAK,
    amendment_difficulty=AmendmentDifficulty.SIMPLE_MAJORITY,
    decree_authority=DecreeAuthority.NONE,
)
"""Answerable in form, with no election ever falling due -- `national_election_interval_turns` is
`None`. Half the unelected charge, not zero and not full."""


class TestTheTruthTable:
    @pytest.mark.parametrize(
        ("constitution", "expected"),
        [
            (ACCOUNTABLE_DEMOCRACY, 0),
            (EMERGENCY_POWERS_DEMOCRACY, EMERGENCY_DECREE_EXPOSURE_BPS),
            (CONSTRAINED_MONARCHY, UNELECTED_EXECUTIVE_EXPOSURE_BPS),
            (UNRESTRICTED_PERSONAL_RULE, MAX_STRUCTURAL_EXPOSURE_BPS),
            (
                ELECTED_BUT_NEVER_SCHEDULED,
                ELECTED_WITHOUT_SCHEDULED_ELECTION_EXPOSURE_BPS + WEAK_JUDICIAL_REVIEW_EXPOSURE_BPS,
            ),
        ],
    )
    def test_each_named_case_scores_what_the_design_says(
        self, constitution: ConstitutionState, expected: int
    ) -> None:
        assert _exposure(constitution).exposure_bps == expected

    def test_the_endpoint_saturates_the_scale_exactly(self) -> None:
        """The components sum to exactly 10,000 at the worst case, so the clamp is DEFENSIVE and
        never actually engages -- the same property `coup_success_probability_bps`'s 3,500-of-7,000
        headroom has. A future component that pushed the sum past the cap would make the total stop
        distinguishing bad from worse, and this is where that shows up."""
        assessment = _exposure(UNRESTRICTED_PERSONAL_RULE)
        assert assessment.executive_accountability_exposure_bps == UNELECTED_EXECUTIVE_EXPOSURE_BPS
        assert assessment.decree_authority_exposure_bps == UNLIMITED_DECREE_EXPOSURE_BPS
        assert assessment.legislature_exposure_bps == NO_LEGISLATURE_EXPOSURE_BPS
        assert assessment.judicial_review_exposure_bps == NO_JUDICIAL_REVIEW_EXPOSURE_BPS
        unclamped = (
            assessment.executive_accountability_exposure_bps
            + assessment.decree_authority_exposure_bps
            + assessment.legislature_exposure_bps
            + assessment.judicial_review_exposure_bps
        )
        assert unclamped == MAX_STRUCTURAL_EXPOSURE_BPS
        assert assessment.exposure_bps == unclamped

    def test_a_constrained_monarchy_is_not_personal_rule(self) -> None:
        """The distinction the mandate names explicitly. Both are hereditary and neither can be
        voted out, so both carry the full unelected charge -- but a monarch who cannot legislate
        alone, sits with a chamber and answers to strong courts is 6,000 bps less exposed than one
        who does none of those things. Structure is not a binary."""
        constrained = _exposure(CONSTRAINED_MONARCHY).exposure_bps
        personal = _exposure(UNRESTRICTED_PERSONAL_RULE).exposure_bps
        assert constrained == 4_000
        assert personal == 10_000
        assert personal - constrained == 6_000

    def test_a_missing_legislature_can_never_be_a_low_exposure_case(self) -> None:
        """Rule C10 makes 'no chamber' imply 'unlimited decree', so the two components always
        arrive together and any legislature-less constitution scores at least 5,000 whatever else
        it does. Asserted rather than assumed, because it is the reason the no-legislature weight
        can be modest without leaving a cheap way to abolish parliament."""
        assessment = _exposure(UNRESTRICTED_PERSONAL_RULE)
        assert (
            assessment.legislature_exposure_bps + assessment.decree_authority_exposure_bps
            == NO_LEGISLATURE_EXPOSURE_BPS + UNLIMITED_DECREE_EXPOSURE_BPS
        )
        with pytest.raises(ValueError, match="legislature_absent_requires_unlimited_decree"):
            UNRESTRICTED_PERSONAL_RULE.model_copy(
                update={"decree_authority": DecreeAuthority.EMERGENCY_ONLY}
            ).model_validate(
                UNRESTRICTED_PERSONAL_RULE.model_dump()
                | {"decree_authority": DecreeAuthority.EMERGENCY_ONLY.value}
            )


class TestEmergencyPowersAreNotADictatorship:
    """The single most important thing this policy must NOT do."""

    def test_emergency_powers_add_only_a_token_charge_to_an_electoral_government(self) -> None:
        """Exact ratios rather than a vague "small": emergency powers cost an eighth of what being
        unelected costs, and a twentieth of full personal rule. The whole charge is 2 bps of coup
        risk once scaled -- visible in the report, negligible in play."""
        emergency = _exposure(EMERGENCY_POWERS_DEMOCRACY).exposure_bps
        assert emergency == EMERGENCY_DECREE_EXPOSURE_BPS
        assert emergency * 8 == _exposure(CONSTRAINED_MONARCHY).exposure_bps
        assert emergency * 20 == _exposure(UNRESTRICTED_PERSONAL_RULE).exposure_bps

    def test_the_victory_helper_disagrees_and_that_is_the_point(self) -> None:
        """`is_noncompetitive_constitution` answers a different question and answers it
        differently: it calls an emergency-powers democracy noncompetitive. Reusing it here would
        have made `tiny_valid` and `deficit_demo` -- both elected, both on an election schedule --
        score as dictatorships. Pinned so a future edit to either function has to notice the other
        exists."""
        assert is_noncompetitive_constitution(
            executive_selection=EMERGENCY_POWERS_DEMOCRACY.executive_selection,
            decree_authority=EMERGENCY_POWERS_DEMOCRACY.decree_authority,
        )
        assert _exposure(EMERGENCY_POWERS_DEMOCRACY).exposure_bps < 1_000

    def test_the_two_functions_agree_only_at_the_accountable_endpoint(self) -> None:
        assert not is_noncompetitive_constitution(
            executive_selection=ACCOUNTABLE_DEMOCRACY.executive_selection,
            decree_authority=ACCOUNTABLE_DEMOCRACY.decree_authority,
        )
        assert _exposure(ACCOUNTABLE_DEMOCRACY).exposure_bps == 0


@pytest.mark.parametrize(
    ("scenario_file", "expected"),
    [("tiny_valid.yaml", 500), ("deficit_demo.yaml", 1_000), ("decree_state.yaml", 7_500)],
)
def test_each_shipped_scenario_scores_from_its_own_authored_constitution(
    scenario_file: str, expected: int
) -> None:
    """Derived from the real authored file, so the literals mirrored into
    `test_government_survival.py`'s worked examples cannot drift away from the scenarios."""
    state = load_scenario_file(SCENARIO_DIR / scenario_file)
    politics = state.world.countries[state.world.player_country_id].politics
    assert politics is not None
    assert _exposure(politics.constitution).exposure_bps == expected


# --- Matched conditions: only the constitution differs ----------------------------------------

_MATCHED_CONDITIONS = {
    "military_loyalty_bps": 7_500,
    "military_power_bps": 6_500,
    "legitimacy_bps": 6_000,
    "opposition_seat_share_bps": 5_000,
    "transition_pressure_bps": 0,
}
"""Deliberately `decree_state`-like numbers, held IDENTICAL across every comparison below --
including opposition share and transition pressure, the two inputs most likely to differ between a
real democracy and a real dictatorship and so most likely to masquerade as a regime effect."""

_MATCHED_POPULATION = {
    "radicalization_bps": 3_000,
    "organization_bps": 6_000,
    "disapproval_bps": 6_000,
}


class TestMatchedConditionsIsolateTheStructuralEffect:
    def test_coup_risk_is_strictly_greater_for_the_unaccountable_government(self) -> None:
        democracy = coup_attempt_risk_bps(
            **_MATCHED_CONDITIONS,
            structural_exposure_bps=_exposure(ACCOUNTABLE_DEMOCRACY).exposure_bps,
        )
        dictatorship = coup_attempt_risk_bps(
            **_MATCHED_CONDITIONS,
            structural_exposure_bps=_exposure(UNRESTRICTED_PERSONAL_RULE).exposure_bps,
        )
        assert dictatorship.attempt_risk_bps > democracy.attempt_risk_bps
        # And the entire gap is the structural term -- every other contribution is identical,
        # which is what makes this a regime effect rather than a confounded one.
        for field in (
            "loyalty_contribution_bps",
            "legitimacy_contribution_bps",
            "opposition_contribution_bps",
            "transition_pressure_contribution_bps",
        ):
            assert getattr(dictatorship, field) == getattr(democracy, field)
        assert dictatorship.attempt_risk_bps - democracy.attempt_risk_bps == (
            dictatorship.structural_contribution_bps - democracy.structural_contribution_bps
        )
        assert dictatorship.structural_contribution_bps == COUP_STRUCTURAL_WEIGHT_BPS

    def test_unrest_risk_is_strictly_greater_for_the_unaccountable_government(self) -> None:
        democracy = unrest_attempt_risk_bps(
            **_MATCHED_POPULATION,
            structural_exposure_bps=_exposure(ACCOUNTABLE_DEMOCRACY).exposure_bps,
        )
        dictatorship = unrest_attempt_risk_bps(
            **_MATCHED_POPULATION,
            structural_exposure_bps=_exposure(UNRESTRICTED_PERSONAL_RULE).exposure_bps,
        )
        assert dictatorship.attempt_risk_bps > democracy.attempt_risk_bps
        assert dictatorship.radicalization_contribution_bps == (
            democracy.radicalization_contribution_bps
        )
        assert dictatorship.disapproval_contribution_bps == democracy.disapproval_contribution_bps
        assert dictatorship.structural_contribution_bps == UNREST_STRUCTURAL_WEIGHT_BPS

    def test_the_ordering_follows_the_whole_exposure_scale_not_just_the_endpoints(self) -> None:
        """Every step of the truth table is monotone in risk. A policy that only separated the two
        extremes would pass the tests above and still tell a player nothing about the middle."""
        ordered = [
            ACCOUNTABLE_DEMOCRACY,
            EMERGENCY_POWERS_DEMOCRACY,
            ELECTED_BUT_NEVER_SCHEDULED,
            CONSTRAINED_MONARCHY,
            UNRESTRICTED_PERSONAL_RULE,
        ]
        risks = [
            coup_attempt_risk_bps(
                **_MATCHED_CONDITIONS, structural_exposure_bps=_exposure(c).exposure_bps
            ).attempt_risk_bps
            for c in ordered
        ]
        assert risks == sorted(risks)
        assert risks[0] < risks[-1]

    def test_removal_probability_rises_wherever_conditional_success_is_positive(self) -> None:
        """Attempt risk is not the outcome. What a player actually faces is
        `attempt_risk * success_probability`, and since this feature leaves the success formula
        untouched, a strictly greater attempt risk is a strictly greater removal probability
        exactly when success is positive."""
        success = coup_success_probability_bps(
            military_power_bps=_MATCHED_CONDITIONS["military_power_bps"],
            military_competence_bps=6_000,
            legitimacy_bps=_MATCHED_CONDITIONS["legitimacy_bps"],
        )
        assert success > 0, "this comparison is vacuous unless a coup can actually succeed"
        democracy = coup_attempt_risk_bps(
            **_MATCHED_CONDITIONS,
            structural_exposure_bps=_exposure(ACCOUNTABLE_DEMOCRACY).exposure_bps,
        ).attempt_risk_bps
        dictatorship = coup_attempt_risk_bps(
            **_MATCHED_CONDITIONS,
            structural_exposure_bps=_exposure(UNRESTRICTED_PERSONAL_RULE).exposure_bps,
        ).attempt_risk_bps
        assert dictatorship * success > democracy * success


class TestTheTwoExceptions:
    def test_a_saturated_cap_does_not_move(self) -> None:
        """Non-decrease, never strict increase, at the cap. Conditions bad enough to max the risk
        out leave nothing for structure to add -- which is correct: a government already certain to
        face a coup attempt cannot face one harder."""
        catastrophic = {
            "military_loyalty_bps": 0,
            "military_power_bps": 10_000,
            "legitimacy_bps": 0,
            "opposition_seat_share_bps": 10_000,
            "transition_pressure_bps": 10_000,
        }
        democracy = coup_attempt_risk_bps(**catastrophic, structural_exposure_bps=0)
        dictatorship = coup_attempt_risk_bps(
            **catastrophic, structural_exposure_bps=MAX_STRUCTURAL_EXPOSURE_BPS
        )
        assert democracy.attempt_risk_bps == MAX_COUP_ATTEMPT_RISK_BPS
        assert dictatorship.attempt_risk_bps == MAX_COUP_ATTEMPT_RISK_BPS
        assert dictatorship.attempt_risk_bps >= democracy.attempt_risk_bps
        # The contribution is still computed and still published -- it is the TOTAL that is
        # capped, not the term, so the report can still explain where the risk came from.
        assert dictatorship.structural_contribution_bps == COUP_STRUCTURAL_WEIGHT_BPS

    def test_the_same_holds_on_the_unrest_channel(self) -> None:
        catastrophic = {
            "radicalization_bps": 10_000,
            "organization_bps": 10_000,
            "disapproval_bps": 10_000,
        }
        democracy = unrest_attempt_risk_bps(**catastrophic, structural_exposure_bps=0)
        dictatorship = unrest_attempt_risk_bps(
            **catastrophic, structural_exposure_bps=MAX_STRUCTURAL_EXPOSURE_BPS
        )
        assert democracy.attempt_risk_bps == MAX_UNREST_ATTEMPT_RISK_BPS
        assert dictatorship.attempt_risk_bps == MAX_UNREST_ATTEMPT_RISK_BPS

    def test_zero_conditional_success_makes_more_attempts_produce_no_removals(self) -> None:
        """The other exception. A well-regarded government facing a disorganized population has a
        popular-uprising success probability of exactly 0; structure raises how often the attempt
        is made and the removal probability stays 0 either way. Structure cannot manufacture an
        outcome the conditional formula rules out."""
        from app.simulation.government_survival import unrest_success_probability_bps

        success = unrest_success_probability_bps(organization_bps=1_000, legitimacy_bps=9_000)
        assert success == 0
        democracy = unrest_attempt_risk_bps(
            **_MATCHED_POPULATION, structural_exposure_bps=0
        ).attempt_risk_bps
        dictatorship = unrest_attempt_risk_bps(
            **_MATCHED_POPULATION, structural_exposure_bps=MAX_STRUCTURAL_EXPOSURE_BPS
        ).attempt_risk_bps
        assert dictatorship > democracy
        assert dictatorship * success == 0
        assert democracy * success == 0


class TestConditionsStillWorkWithinEitherStructure:
    """A dictatorship is not doomed and a democracy is not safe. Both directions, both structures."""

    @pytest.mark.parametrize("constitution", [ACCOUNTABLE_DEMOCRACY, UNRESTRICTED_PERSONAL_RULE])
    def test_a_more_loyal_army_lowers_coup_risk(self, constitution: ConstitutionState) -> None:
        exposure = _exposure(constitution).exposure_bps
        disloyal = coup_attempt_risk_bps(
            **{**_MATCHED_CONDITIONS, "military_loyalty_bps": 1_000},
            structural_exposure_bps=exposure,
        )
        loyal = coup_attempt_risk_bps(
            **{**_MATCHED_CONDITIONS, "military_loyalty_bps": 9_000},
            structural_exposure_bps=exposure,
        )
        assert loyal.attempt_risk_bps < disloyal.attempt_risk_bps
        assert loyal.structural_contribution_bps == disloyal.structural_contribution_bps

    def test_a_loyal_dictatorship_is_safer_than_a_democracy_whose_army_has_turned(self) -> None:
        """The comparison that stops this feature from reading as 'dictatorship loses'. Structure
        is one term among five, and it is not the largest."""
        loyal_dictatorship = coup_attempt_risk_bps(
            **{**_MATCHED_CONDITIONS, "military_loyalty_bps": 9_500},
            structural_exposure_bps=_exposure(UNRESTRICTED_PERSONAL_RULE).exposure_bps,
        )
        betrayed_democracy = coup_attempt_risk_bps(
            **{**_MATCHED_CONDITIONS, "military_loyalty_bps": 0},
            structural_exposure_bps=_exposure(ACCOUNTABLE_DEMOCRACY).exposure_bps,
        )
        assert betrayed_democracy.attempt_risk_bps > loyal_dictatorship.attempt_risk_bps

    @pytest.mark.parametrize("constitution", [ACCOUNTABLE_DEMOCRACY, UNRESTRICTED_PERSONAL_RULE])
    def test_a_calmer_population_lowers_unrest_risk(self, constitution: ConstitutionState) -> None:
        exposure = _exposure(constitution).exposure_bps
        angry = unrest_attempt_risk_bps(
            radicalization_bps=9_000,
            organization_bps=9_000,
            disapproval_bps=9_000,
            structural_exposure_bps=exposure,
        )
        calm = unrest_attempt_risk_bps(
            radicalization_bps=500,
            organization_bps=500,
            disapproval_bps=500,
            structural_exposure_bps=exposure,
        )
        assert calm.attempt_risk_bps < angry.attempt_risk_bps
