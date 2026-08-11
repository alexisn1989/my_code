"""Tests for `app.simulation.legislative_voting` — the support chain, the change representation
and chamber passage (Phase 3B1, T-V1..T-V8).

Every expected number below is computed by hand from the formulas in the module docstring, not
copied from a run. Where a step saturates or clamps, the test says so, because a clamped result
that happens to equal an unclamped one would otherwise hide a broken formula.
"""

from __future__ import annotations

import pytest

from app.simulation.apportionment import SeatSupport, apportion_supporting_seats
from app.simulation.legislative_voting import (
    MAX_INFLUENCE_BPS,
    PolicyChange,
    baseline_support_bps,
    chamber_carries,
    influence_bps,
    policy_compatibility_bps,
    required_yes_seats,
    resolve_bloc_support,
    spending_policy_change,
    tax_policy_change,
)
from app.simulation.legislature import ChangeDirection, GovernmentRole

UNCHANGED = PolicyChange(direction=ChangeDirection.UNCHANGED, intensity_bps=0)


# --- T-V1: baseline support from role and relationship ------------------------


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        pytest.param(GovernmentRole.COALITION, 8_000, id="coalition"),
        pytest.param(GovernmentRole.CONFIDENCE_AND_SUPPLY, 6_000, id="confidence-and-supply"),
        pytest.param(GovernmentRole.OPPOSITION, 2_000, id="opposition"),
    ],
)
def test_a_neutral_relationship_leaves_the_bloc_on_its_role_anchor(
    role: GovernmentRole, expected: int
) -> None:
    assert baseline_support_bps(role=role, relationship_bps=0) == expected


@pytest.mark.parametrize(
    ("role", "relationship", "expected"),
    [
        pytest.param(GovernmentRole.COALITION, 10_000, 10_000, id="devoted-coalition"),
        pytest.param(GovernmentRole.COALITION, -10_000, 6_000, id="rebel-coalition"),
        pytest.param(GovernmentRole.OPPOSITION, 10_000, 4_000, id="friendly-opposition"),
        pytest.param(GovernmentRole.OPPOSITION, -10_000, 0, id="implacable-opposition"),
        pytest.param(GovernmentRole.COALITION, 5_000, 9_000, id="warm-coalition"),
        pytest.param(GovernmentRole.OPPOSITION, -5_000, 1_000, id="cold-opposition"),
    ],
)
def test_relationship_moves_a_bloc_at_most_twenty_points_off_its_anchor(
    role: GovernmentRole, relationship: int, expected: int
) -> None:
    assert baseline_support_bps(role=role, relationship_bps=relationship) == expected


def test_formal_role_still_dominates_relationship() -> None:
    """The reason `RELATIONSHIP_WEIGHT_BPS` is smaller than the gaps between anchors: a coalition
    bloc that despises the government is still more supportive than an opposition bloc that adores
    it. Joining a government has to mean something."""
    rebel_insider = baseline_support_bps(role=GovernmentRole.COALITION, relationship_bps=-10_000)
    friendly_outsider = baseline_support_bps(
        role=GovernmentRole.OPPOSITION, relationship_bps=10_000
    )
    assert rebel_insider > friendly_outsider


@pytest.mark.parametrize("relationship", [-10_001, 10_001])
def test_a_relationship_outside_the_scale_is_rejected(relationship: int) -> None:
    with pytest.raises(ValueError, match="relationship_bps must be within"):
        baseline_support_bps(role=GovernmentRole.COALITION, relationship_bps=relationship)


# --- T-V2: tax change direction and intensity ---------------------------------


@pytest.mark.parametrize(
    ("rate_changes", "direction", "intensity"),
    [
        pytest.param(((2_000, 2_500),), ChangeDirection.INCREASE, 5_000, id="plus-5pp"),
        pytest.param(((2_000, 3_000),), ChangeDirection.INCREASE, 10_000, id="plus-10pp-is-full"),
        pytest.param(((2_000, 4_000),), ChangeDirection.INCREASE, 10_000, id="plus-20pp-saturates"),
        pytest.param(((2_500, 2_000),), ChangeDirection.DECREASE, 5_000, id="minus-5pp"),
        pytest.param(((2_000, 2_000),), ChangeDirection.UNCHANGED, 0, id="rate-set-to-itself"),
        pytest.param((), ChangeDirection.UNCHANGED, 0, id="no-rates-set"),
    ],
)
def test_tax_change_reads_direction_and_saturated_intensity(
    rate_changes: tuple[tuple[int, int], ...], direction: ChangeDirection, intensity: int
) -> None:
    change = tax_policy_change(rate_changes=rate_changes)
    assert change.direction is direction
    assert change.intensity_bps == intensity


def test_tax_changes_across_several_rates_combine_into_one_movement() -> None:
    """A budget that raises one rate and cuts another has moved taxes by the net amount — blocs
    react to the package, not to each line separately."""
    change = tax_policy_change(rate_changes=((2_000, 2_500), (1_000, 900)))
    assert change.direction is ChangeDirection.INCREASE
    assert change.intensity_bps == 4_000  # net +400 bps


def test_an_exactly_offsetting_package_is_unchanged() -> None:
    """A 5 pp rise paid for by a 5 pp cut is a wash, and is reported as one rather than as two
    changes that happen to cancel."""
    change = tax_policy_change(rate_changes=((2_000, 2_500), (1_000, 500)))
    assert change.direction is ChangeDirection.UNCHANGED
    assert change.intensity_bps == 0


# --- T-V3 (R7): the four spending branches ------------------------------------


def test_spending_unchanged_at_zero() -> None:
    change = spending_policy_change(opening_total=0, proposed_total=0)
    assert change.direction is ChangeDirection.UNCHANGED
    assert change.intensity_bps == 0


def test_creating_a_program_from_nothing_is_a_maximum_increase() -> None:
    """The case a signed percentage cannot express. The relative change from zero is undefined,
    and the plausible-looking answer — 0% — would read as "nothing changed" for what is in fact
    the largest spending change available."""
    change = spending_policy_change(opening_total=0, proposed_total=1)
    assert change.direction is ChangeDirection.INCREASE
    assert change.intensity_bps == 10_000

    huge = spending_policy_change(opening_total=0, proposed_total=50_000_000_000)
    assert huge == change


def test_abolishing_all_spending_is_a_maximum_decrease() -> None:
    """Exactly -100%, i.e. -10,000 bps, which saturates against a full-intensity constant of
    1,000."""
    change = spending_policy_change(opening_total=5_000_000, proposed_total=0)
    assert change.direction is ChangeDirection.DECREASE
    assert change.intensity_bps == 10_000


@pytest.mark.parametrize(
    ("opening", "proposed", "direction", "intensity"),
    [
        pytest.param(1_000, 1_050, ChangeDirection.INCREASE, 5_000, id="plus-5-percent"),
        pytest.param(1_000, 1_100, ChangeDirection.INCREASE, 10_000, id="plus-10-percent-is-full"),
        pytest.param(1_000, 2_000, ChangeDirection.INCREASE, 10_000, id="doubling-saturates"),
        pytest.param(1_000, 950, ChangeDirection.DECREASE, 5_000, id="minus-5-percent"),
        pytest.param(1_000, 1_000, ChangeDirection.UNCHANGED, 0, id="identical-totals"),
    ],
)
def test_ordinary_spending_changes_are_relative(
    opening: int, proposed: int, direction: ChangeDirection, intensity: int
) -> None:
    change = spending_policy_change(opening_total=opening, proposed_total=proposed)
    assert change.direction is direction
    assert change.intensity_bps == intensity


def test_a_change_too_small_to_measure_keeps_its_direction() -> None:
    """Intensity 0 does not imply `UNCHANGED`. Spending genuinely rose here; it rose by less than
    the scale can register. Reporting `UNCHANGED` would assert nothing moved when something did."""
    change = spending_policy_change(opening_total=1_000_000, proposed_total=1_000_001)
    assert change.direction is ChangeDirection.INCREASE
    assert change.intensity_bps == 0


@pytest.mark.parametrize(
    ("opening", "proposed"),
    [pytest.param(-1, 100, id="negative-opening"), pytest.param(100, -1, id="negative-proposed")],
)
def test_negative_program_spending_is_rejected(opening: int, proposed: int) -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        spending_policy_change(opening_total=opening, proposed_total=proposed)


# --- T-V4: policy compatibility -----------------------------------------------


def test_a_bloc_that_wants_higher_taxes_is_pleased_by_a_rise_and_displeased_by_a_cut() -> None:
    """The same magnitude, opposite signs — which is what makes truncation toward zero rather
    than toward negative infinity load-bearing rather than decorative."""
    rise = policy_compatibility_bps(
        tax_change=tax_policy_change(rate_changes=((2_000, 2_500),)),
        tax_preference_bps=4_000,
        spending_change=UNCHANGED,
        spending_preference_bps=0,
    )
    cut = policy_compatibility_bps(
        tax_change=tax_policy_change(rate_changes=((2_500, 2_000),)),
        tax_preference_bps=4_000,
        spending_change=UNCHANGED,
        spending_preference_bps=0,
    )
    assert rise == 400
    assert cut == -400


def test_the_two_axes_are_independent_and_add() -> None:
    """A bloc can love a budget's spending and hate its taxes; the sum is how it feels about the
    budget. Collapsing the axes would make that combination unrepresentable."""
    mixed = policy_compatibility_bps(
        tax_change=PolicyChange(direction=ChangeDirection.INCREASE, intensity_bps=10_000),
        tax_preference_bps=-10_000,
        spending_change=PolicyChange(direction=ChangeDirection.INCREASE, intensity_bps=10_000),
        spending_preference_bps=10_000,
    )
    assert mixed == 0  # -2,000 on tax, +2,000 on spending


def test_compatibility_is_bounded_at_forty_points_combined() -> None:
    """The declared range. Policy content can flip a marginal bloc; it can never turn a committed
    opponent into a supporter on content alone — that is what the bargaining is for."""
    full_agreement = policy_compatibility_bps(
        tax_change=PolicyChange(direction=ChangeDirection.INCREASE, intensity_bps=10_000),
        tax_preference_bps=10_000,
        spending_change=PolicyChange(direction=ChangeDirection.INCREASE, intensity_bps=10_000),
        spending_preference_bps=10_000,
    )
    full_disagreement = policy_compatibility_bps(
        tax_change=PolicyChange(direction=ChangeDirection.DECREASE, intensity_bps=10_000),
        tax_preference_bps=10_000,
        spending_change=PolicyChange(direction=ChangeDirection.DECREASE, intensity_bps=10_000),
        spending_preference_bps=10_000,
    )
    assert full_agreement == 4_000
    assert full_disagreement == -4_000


def test_an_unchanged_axis_contributes_nothing_however_strong_the_preference() -> None:
    """A bloc with violent opinions about spending has no opinion about a budget that does not
    touch spending."""
    assert (
        policy_compatibility_bps(
            tax_change=UNCHANGED,
            tax_preference_bps=10_000,
            spending_change=UNCHANGED,
            spending_preference_bps=-10_000,
        )
        == 0
    )


def test_an_indifferent_bloc_is_unmoved_by_any_proposal() -> None:
    assert (
        policy_compatibility_bps(
            tax_change=PolicyChange(direction=ChangeDirection.INCREASE, intensity_bps=10_000),
            tax_preference_bps=0,
            spending_change=PolicyChange(direction=ChangeDirection.DECREASE, intensity_bps=10_000),
            spending_preference_bps=0,
        )
        == 0
    )


@pytest.mark.parametrize("preference", [-10_001, 10_001])
def test_a_preference_outside_the_scale_is_rejected(preference: int) -> None:
    with pytest.raises(ValueError, match="tax_preference_bps must be within"):
        policy_compatibility_bps(
            tax_change=UNCHANGED,
            tax_preference_bps=preference,
            spending_change=UNCHANGED,
            spending_preference_bps=0,
        )


# --- T-V5: political-capital influence ----------------------------------------


@pytest.mark.parametrize(
    ("capital", "expected"),
    [
        pytest.param(0, 0, id="nothing-spent"),
        pytest.param(1, 10, id="one-unit"),
        pytest.param(100, 1_000, id="100-buys-10-points"),
        pytest.param(299, 2_990, id="just-below-the-cap"),
        pytest.param(300, 3_000, id="exactly-at-the-cap"),
        pytest.param(301, 3_000, id="just-past-the-cap"),
        pytest.param(10**9, 3_000, id="absurd-sums-buy-nothing-more"),
    ],
)
def test_influence_is_linear_then_hard_capped(capital: int, expected: int) -> None:
    assert influence_bps(political_capital=capital) == expected


def test_the_cap_is_what_makes_a_hostile_chamber_unpassable_rather_than_expensive() -> None:
    """Without a ceiling, every legislature would eventually yield to a large enough cheque and
    the political system would collapse into an accounting exercise."""
    assert influence_bps(political_capital=10**12) == MAX_INFLUENCE_BPS


def test_negative_capital_is_rejected() -> None:
    with pytest.raises(ValueError, match="political_capital cannot be negative"):
        influence_bps(political_capital=-1)


# --- T-V6: the whole chain, and discipline ------------------------------------


def _support(
    *,
    role: GovernmentRole = GovernmentRole.COALITION,
    relationship_bps: int = 0,
    tax_preference_bps: int = 0,
    allocated_political_capital: int = 0,
    discipline_bps: int = 0,
    tax_change: PolicyChange = UNCHANGED,
) -> int:
    return resolve_bloc_support(
        role=role,
        relationship_bps=relationship_bps,
        tax_change=tax_change,
        tax_preference_bps=tax_preference_bps,
        spending_change=UNCHANGED,
        spending_preference_bps=0,
        allocated_political_capital=allocated_political_capital,
        discipline_bps=discipline_bps,
    ).effective_support_bps


def test_the_chain_records_every_step_it_passed_through() -> None:
    """A coalition bloc at +6,000 relationship, facing a +5 pp tax rise it mildly wants, bought
    with 100 capital and whipped at 50% discipline."""
    support = resolve_bloc_support(
        role=GovernmentRole.COALITION,
        relationship_bps=6_000,
        tax_change=tax_policy_change(rate_changes=((2_000, 2_500),)),
        tax_preference_bps=2_000,
        spending_change=UNCHANGED,
        spending_preference_bps=0,
        allocated_political_capital=100,
        discipline_bps=5_000,
    )
    assert support.baseline_support_bps == 9_200  # 8,000 + 6,000 * 0.2
    assert support.policy_compatibility_bps == 200  # 2,000 * 0.5 * 0.2
    assert support.influence_bps == 1_000  # 100 * 10
    assert support.raw_support_bps == 9_400
    assert support.final_support_bps == 10_000  # 10,400 clamped to the top of the scale
    assert support.effective_support_bps == 10_000


def test_zero_discipline_leaves_the_bloc_exactly_where_content_put_it() -> None:
    assert _support(relationship_bps=-10_000, discipline_bps=0) == 6_000


@pytest.mark.parametrize(
    ("final_before_whip", "relationship", "discipline", "expected"),
    [
        # Coalition at -10,000 relationship sits at 6,000 — 1,000 above the midpoint.
        pytest.param(6_000, -10_000, 5_000, 6_500, id="half-discipline-adds-half-the-lean"),
        pytest.param(6_000, -10_000, 10_000, 7_000, id="full-discipline-doubles-the-lean"),
    ],
)
def test_discipline_amplifies_the_lean_away_from_the_midpoint(
    final_before_whip: int, relationship: int, discipline: int, expected: int
) -> None:
    assert _support(relationship_bps=relationship, discipline_bps=0) == final_before_whip
    assert _support(relationship_bps=relationship, discipline_bps=discipline) == expected


def test_discipline_pushes_a_hostile_bloc_further_against() -> None:
    """The amplification is symmetric: a whip does not only deliver yes votes."""
    undisciplined = _support(role=GovernmentRole.OPPOSITION, relationship_bps=0, discipline_bps=0)
    disciplined = _support(
        role=GovernmentRole.OPPOSITION, relationship_bps=0, discipline_bps=10_000
    )
    assert undisciplined == 2_000
    assert disciplined == 0  # 2,000 - 3,000 = -1,000, clamped to the floor


def test_a_bloc_exactly_at_the_midpoint_has_no_lean_to_amplify() -> None:
    """5,000 is the pivot of the whole discipline step; no amount of whipping moves a caucus that
    is genuinely evenly split."""
    for discipline in (0, 5_000, 10_000):
        assert (
            _support(
                role=GovernmentRole.CONFIDENCE_AND_SUPPLY,
                relationship_bps=-5_000,
                discipline_bps=discipline,
            )
            == 5_000
        )


def test_discipline_amplifies_bought_support_too() -> None:
    """Influence is applied before the whip, so a well-disciplined party delivers the votes it was
    paid for. An opposition bloc at 2,000 bought to 5,000 is at the midpoint and unwhippable; the
    same bloc bought to 4,000 is still leaning against and gets whipped further against."""
    bought_to_midpoint = _support(
        role=GovernmentRole.OPPOSITION, allocated_political_capital=300, discipline_bps=10_000
    )
    assert bought_to_midpoint == 5_000

    partly_bought = _support(
        role=GovernmentRole.OPPOSITION, allocated_political_capital=200, discipline_bps=10_000
    )
    assert partly_bought == 3_000  # 4,000, then the whip doubles its 1,000 lean against


@pytest.mark.parametrize("discipline", [-1, 10_001])
def test_discipline_outside_the_scale_is_rejected(discipline: int) -> None:
    with pytest.raises(ValueError, match="discipline_bps must be within"):
        _support(discipline_bps=discipline)


def test_support_never_leaves_the_scale_at_either_end() -> None:
    ceiling = _support(
        relationship_bps=10_000, allocated_political_capital=10**6, discipline_bps=10_000
    )
    floor = _support(
        role=GovernmentRole.OPPOSITION,
        relationship_bps=-10_000,
        tax_change=PolicyChange(direction=ChangeDirection.DECREASE, intensity_bps=10_000),
        tax_preference_bps=10_000,
        discipline_bps=10_000,
    )
    assert ceiling == 10_000
    assert floor == 0


# --- T-V7: chamber passage ----------------------------------------------------


@pytest.mark.parametrize(
    ("total_seats", "expected"),
    [
        pytest.param(100, 51, id="even-chamber"),
        pytest.param(99, 50, id="odd-chamber"),
        pytest.param(60, 31, id="small-upper-house"),
        pytest.param(200, 101, id="large-chamber"),
        pytest.param(2, 2, id="two-seats-needs-both"),
        pytest.param(1, 1, id="one-seat"),
    ],
)
def test_the_required_majority_is_strict(total_seats: int, expected: int) -> None:
    assert required_yes_seats(total_seats=total_seats) == expected


def test_a_chamber_with_no_seats_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least one seat"):
        required_yes_seats(total_seats=0)


@pytest.mark.parametrize(
    ("supporting", "total", "carries"),
    [
        pytest.param(51, 100, True, id="bare-majority-carries"),
        pytest.param(50, 100, False, id="an-exact-tie-fails"),
        pytest.param(49, 100, False, id="short"),
        pytest.param(50, 99, True, id="odd-chamber-bare-majority"),
        pytest.param(49, 99, False, id="odd-chamber-one-short"),
        pytest.param(100, 100, True, id="unanimous"),
        pytest.param(0, 100, False, id="unanimously-against"),
    ],
)
def test_a_chamber_carries_only_on_a_strict_majority(
    supporting: int, total: int, carries: bool
) -> None:
    assert chamber_carries(supporting_seats=supporting, total_seats=total) is carries


def test_a_tie_fails_and_nothing_is_consulted_to_break_it() -> None:
    """An evenly split chamber — 50 fully loyal seats against 50 implacably hostile ones — does
    not carry. There is no casting vote, speaker or quorum anywhere in state, so inventing a
    tie-breaker would be an undefined mechanism."""
    loyal = _support(relationship_bps=10_000, discipline_bps=10_000)
    hostile = _support(role=GovernmentRole.OPPOSITION, relationship_bps=-10_000)
    assert (loyal, hostile) == (10_000, 0)

    tally = apportion_supporting_seats(
        rows=(
            SeatSupport(party_id="gov", bloc_id="all", seats=50, effective_support_bps=loyal),
            SeatSupport(party_id="opp", bloc_id="all", seats=50, effective_support_bps=hostile),
        )
    )
    assert tally.supporting_seats == 50
    assert chamber_carries(supporting_seats=tally.supporting_seats, total_seats=100) is False


# --- T-V8: end to end, voting into apportionment ------------------------------

_CHAMBER = (
    # (party, bloc, role, relationship, tax preference, discipline, seats)
    ("gov", "mainstream", GovernmentRole.COALITION, 6_000, 2_000, 5_000, 45),
    ("gov", "left", GovernmentRole.COALITION, 2_000, 2_000, 1_000, 13),
    ("opp", "conservative", GovernmentRole.OPPOSITION, -8_000, -6_000, 8_000, 32),
    ("opp", "regional", GovernmentRole.OPPOSITION, -2_000, -2_000, 2_000, 10),
)


def _tally(*, allocations: dict[tuple[str, str], int]) -> int:
    """Run the whole 100-seat chamber above through the support chain and apportionment, for a
    +5 pp personal income tax rise."""
    tax_change = tax_policy_change(rate_changes=((2_000, 2_500),))
    rows = tuple(
        SeatSupport(
            party_id=party,
            bloc_id=bloc,
            seats=seats,
            effective_support_bps=resolve_bloc_support(
                role=role,
                relationship_bps=relationship,
                tax_change=tax_change,
                tax_preference_bps=preference,
                spending_change=UNCHANGED,
                spending_preference_bps=0,
                allocated_political_capital=allocations.get((party, bloc), 0),
                discipline_bps=discipline,
            ).effective_support_bps,
        )
        for party, bloc, role, relationship, preference, discipline, seats in _CHAMBER
    )
    return apportion_supporting_seats(rows=rows).supporting_seats


def test_a_majority_coalition_carries_its_own_budget_unaided() -> None:
    """45 + 13 government seats, both parties' blocs mildly in favour, opposition against.
    `gov/mainstream` saturates at full support; `gov/left` reaches 8,960 and contributes 11 of its
    13 seats; `opp/regional` at 680 contributes none of its own but wins the single remainder
    seat, taking the chamber to 57."""
    assert _tally(allocations={}) == 57
    assert chamber_carries(supporting_seats=57, total_seats=100) is True


def test_buying_a_wavering_opposition_bloc_moves_real_seats() -> None:
    """300 capital on `opp/regional` lifts it from 680 to 4,280 effective support — 3 more seats
    in the tally. This is the whole mechanism the phase exists for: a government short of a
    majority can go and find one."""
    assert _tally(allocations={("opp", "regional"): 300}) == 60


def test_capital_below_the_whips_pull_on_a_hostile_bloc_is_wasted_entirely() -> None:
    """`opp/conservative` is hostile, opposed to the policy and heavily whipped, sitting at 0
    effective support. 200 capital lifts it to 4,000 before the whip, which then drags it back
    below the floor — the tally is unchanged, and the spending bought literally nothing."""
    assert _tally(allocations={("opp", "conservative"): 200}) == 57


def test_the_influence_cap_bounds_what_a_hostile_bloc_can_ever_be_worth() -> None:
    """Past the cap, more capital changes nothing at all: 300 and 10,000 buy the identical 4 of
    32 seats. This is what keeps a sufficiently hostile chamber genuinely unreachable rather than
    merely expensive — regime 4 of the plan's decree analysis rests on exactly this ceiling."""
    at_the_cap = _tally(allocations={("opp", "conservative"): 300})
    far_past_it = _tally(allocations={("opp", "conservative"): 10_000})
    assert at_the_cap == far_past_it == 61
