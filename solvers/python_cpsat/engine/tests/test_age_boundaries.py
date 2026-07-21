"""HC-3 age-routing boundary tests (D5).

AGE_THRESHOLDS: baby_max = 2.5 (ages strictly below need a baby-capable
instructor), adult_min = 18 (ages at or above need an adult-capable
instructor). These tests pin the inclusive/exclusive semantics at the exact
boundaries in both Phase 1 (continuity) and Phase 2 (CP-SAT candidates).
"""

from solvers.python_cpsat.engine.config import AGE_THRESHOLDS
from solvers.python_cpsat.engine.data_loader import Swimmer, Instructor
from solvers.python_cpsat.engine.phase1_continuity import _hc_allows, _continuity_hc_check
from solvers.python_cpsat.engine.phase2_cpsat import (
    _individual_candidate_is_feasible,
    _pair_candidate_is_feasible,
)


def _make_swimmer(sid=1, age=10.0, special_needs=False):
    return Swimmer(
        swimmer_id=sid, first_name=f"S{sid}", last_name="Test",
        swimmer_type_id=1, skill_level=3, age=age,
        has_special_needs=special_needs, notes="", pair_id=None,
    )


def _make_instructor(iid=1, can_babies=True, can_adults=True, can_adapted=True):
    return Instructor(
        instructor_id=iid, first_name=f"I{iid}", last_name="Test",
        primary_color_id=1, secondary_color_id=2,
        primary_style_id=1, secondary_style_id=2,
        is_team_captain=False, can_teach_NL=True,
        can_teach_babies=can_babies, can_teach_adults=can_adults,
        can_teach_adapted=can_adapted,
    )


NO_BABIES = dict(can_babies=False)
NO_ADULTS = dict(can_adults=False)


class TestConfigValues:
    def test_thresholds_match_business_rules(self):
        assert AGE_THRESHOLDS['baby_max'] == 2.5
        assert AGE_THRESHOLDS['adult_min'] == 18


class TestBabyBoundaryPhase1:
    def test_just_under_baby_max_requires_baby_capability(self):
        swimmer = _make_swimmer(age=2.49)
        assert not _hc_allows(swimmer, _make_instructor(**NO_BABIES))
        assert _hc_allows(swimmer, _make_instructor())

    def test_exactly_baby_max_is_not_a_baby(self):
        # age >= 2.5 routes as a regular swimmer
        swimmer = _make_swimmer(age=2.5)
        assert _hc_allows(swimmer, _make_instructor(**NO_BABIES))

    def test_continuity_check_blocks_baby_hard(self):
        # HC-3 is never overridable by continuity — blocked with the flag list
        allowed, flags = _continuity_hc_check(_make_swimmer(age=2.49), _make_instructor(**NO_BABIES))
        assert allowed is False
        assert flags == ['continuity_blocked_by_baby_capability']

    def test_continuity_check_allows_exactly_baby_max(self):
        allowed, flags = _continuity_hc_check(_make_swimmer(age=2.5), _make_instructor(**NO_BABIES))
        assert allowed is True
        assert flags == []


class TestAdultBoundaryPhase1:
    def test_just_under_adult_min_is_not_an_adult(self):
        swimmer = _make_swimmer(age=17.99)
        assert _hc_allows(swimmer, _make_instructor(**NO_ADULTS))

    def test_exactly_adult_min_requires_adult_capability(self):
        # age >= 18 routes as an adult
        swimmer = _make_swimmer(age=18.0)
        assert not _hc_allows(swimmer, _make_instructor(**NO_ADULTS))
        assert _hc_allows(swimmer, _make_instructor())

    def test_continuity_check_blocks_adult_hard(self):
        allowed, flags = _continuity_hc_check(_make_swimmer(age=18.0), _make_instructor(**NO_ADULTS))
        assert allowed is False
        assert flags == ['continuity_blocked_by_adult_capability']


class TestBoundariesPhase2:
    def test_baby_boundary_in_cpsat_candidates(self):
        no_babies = _make_instructor(**NO_BABIES)
        assert not _individual_candidate_is_feasible(_make_swimmer(age=2.49), no_babies)
        assert _individual_candidate_is_feasible(_make_swimmer(age=2.5), no_babies)

    def test_adult_boundary_in_cpsat_candidates(self):
        no_adults = _make_instructor(**NO_ADULTS)
        assert _individual_candidate_is_feasible(_make_swimmer(age=17.99), no_adults)
        assert not _individual_candidate_is_feasible(_make_swimmer(age=18.0), no_adults)

    def test_pair_feasibility_blocks_when_either_swimmer_is_routed(self):
        # One regular swimmer + one 18-year-old: a non-adult-capable
        # instructor is infeasible for the pair as a whole.
        no_adults = _make_instructor(**NO_ADULTS)
        regular = _make_swimmer(sid=1, age=16.0)
        adult = _make_swimmer(sid=2, age=18.0)
        assert not _pair_candidate_is_feasible(regular, adult, no_adults)
        assert _pair_candidate_is_feasible(regular, adult, _make_instructor())
