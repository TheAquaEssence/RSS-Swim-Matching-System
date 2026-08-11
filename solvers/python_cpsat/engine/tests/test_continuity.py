"""Tests for Phase 1: Continuity Matching (v2)."""

import pytest
from solvers.python_cpsat.engine.data_loader import (
    Swimmer, Instructor, HistoricalPairing
)
from solvers.python_cpsat.engine.phase1_continuity import (
    continuity_pass, _separate_swimmers, group_pairs, get_individuals
)


def _make_swimmer(sid, pair_id=None, age=10.0, special_needs=False):
    return Swimmer(
        swimmer_id=sid, first_name=f"S{sid}", last_name="Test",
        swimmer_type_id=1, skill_level=3, age=age,
        has_special_needs=special_needs, notes="", pair_id=pair_id
    )


def _make_instructor(iid):
    return Instructor(
        instructor_id=iid, first_name=f"I{iid}", last_name="Test",
        primary_color_id=1, secondary_color_id=2,
        primary_style_id=1, secondary_style_id=2,
        is_team_captain=False, can_teach_NL=True,
        can_teach_babies=True, can_teach_adults=True,
        can_teach_adapted=True
    )


class TestSeparateSwimmers:

    def test_all_individuals(self):
        swimmers = [_make_swimmer(1), _make_swimmer(2)]
        individuals, pairs = _separate_swimmers(swimmers)
        assert len(individuals) == 2
        assert len(pairs) == 0

    def test_one_pair(self):
        swimmers = [_make_swimmer(1, pair_id=10), _make_swimmer(2, pair_id=10)]
        individuals, pairs = _separate_swimmers(swimmers)
        assert len(individuals) == 0
        assert len(pairs) == 1

    def test_orphan_pair_id_becomes_individual(self):
        swimmers = [_make_swimmer(1, pair_id=10)]
        individuals, pairs = _separate_swimmers(swimmers)
        assert len(individuals) == 1
        assert len(pairs) == 0

    def test_mixed(self):
        swimmers = [
            _make_swimmer(1),
            _make_swimmer(2, pair_id=10),
            _make_swimmer(3, pair_id=10),
            _make_swimmer(4),
        ]
        individuals, pairs = _separate_swimmers(swimmers)
        assert len(individuals) == 2
        assert len(pairs) == 1


class TestContinuityPass:

    def test_basic_continuity_match(self):
        swimmers = [_make_swimmer(1)]
        instructors = [_make_instructor(100)]
        history = [HistoricalPairing(swimmer_id=1, instructor_id=100, session='F25', num_sessions=3)]

        matches, unmatched, available, disputes, _ = continuity_pass(swimmers, instructors, history)
        assert len(matches) == 1
        assert matches[0]['match_type'] == 'continuity'
        assert matches[0]['instructor_id'] == 100
        assert len(unmatched) == 0
        assert len(available) == 0

    def test_no_history_goes_to_unmatched(self):
        swimmers = [_make_swimmer(1)]
        instructors = [_make_instructor(100)]
        history = []

        matches, unmatched, available, disputes, _ = continuity_pass(swimmers, instructors, history)
        assert len(matches) == 0
        assert len(unmatched) == 1
        assert len(available) == 1

    def test_instructor_capacity_consumed(self):
        swimmers = [_make_swimmer(1), _make_swimmer(2)]
        instructors = [_make_instructor(100)]
        history = [
            HistoricalPairing(swimmer_id=1, instructor_id=100, session='F25', num_sessions=5),
            HistoricalPairing(swimmer_id=2, instructor_id=100, session='F25', num_sessions=1),
        ]

        matches, unmatched, available, disputes, _ = continuity_pass(swimmers, instructors, history)
        # Swimmer 1 should win (more sessions)
        assert len(matches) == 1
        assert matches[0]['swimmer_id'] == 1
        assert len(unmatched) == 1
        assert unmatched[0].swimmer_id == 2

    def test_pair_shared_history(self):
        swimmers = [_make_swimmer(1, pair_id=10), _make_swimmer(2, pair_id=10)]
        instructors = [_make_instructor(100)]
        history = [
            HistoricalPairing(swimmer_id=1, instructor_id=100, session='F25', num_sessions=2),
            HistoricalPairing(swimmer_id=2, instructor_id=100, session='F25', num_sessions=2),
        ]

        matches, unmatched, available, disputes, _ = continuity_pass(swimmers, instructors, history)
        assert len(matches) == 1
        assert matches[0]['type'] == 'pair'
        assert len(unmatched) == 0

    def test_pair_different_history_no_match(self):
        swimmers = [_make_swimmer(1, pair_id=10), _make_swimmer(2, pair_id=10)]
        instructors = [_make_instructor(100), _make_instructor(200)]
        history = [
            HistoricalPairing(swimmer_id=1, instructor_id=100, session='F25', num_sessions=2),
            HistoricalPairing(swimmer_id=2, instructor_id=200, session='F25', num_sessions=2),
        ]

        matches, unmatched, available, disputes, _ = continuity_pass(swimmers, instructors, history)
        assert len(matches) == 0
        assert len(unmatched) == 2  # Both go to Phase 2


def _make_history(swimmer_id, instructor_id, num_sessions=3):
    return HistoricalPairing(
        swimmer_id=swimmer_id,
        instructor_id=instructor_id,
        num_sessions=num_sessions,
        session="2026-01"
    )


class TestContinuityDispute:

    def test_no_dispute_when_no_conflict(self):
        """Individual and pair each have different previous instructors."""
        swimmers = [
            _make_swimmer(1),              # individual → instructor 10
            _make_swimmer(2, pair_id=99),  # pair → instructor 20
            _make_swimmer(3, pair_id=99),  # pair → instructor 20
        ]
        instructors = [_make_instructor(10), _make_instructor(20)]
        history = [
            _make_history(1, 10),
            _make_history(2, 20),
            _make_history(3, 20),
        ]
        matches, unmatched, available, disputes, _ = continuity_pass(
            swimmers, instructors, history
        )
        assert disputes == set()

    def test_individual_beats_pair_and_pair_is_disputed(self):
        """Individual (5 sessions) and pair both want instructor 10. Individual wins."""
        swimmers = [
            _make_swimmer(1),              # individual → instructor 10 (5 sessions)
            _make_swimmer(2, pair_id=99),  # pair → instructor 10
            _make_swimmer(3, pair_id=99),  # pair → instructor 10
        ]
        instructors = [_make_instructor(10)]
        history = [
            _make_history(1, 10, num_sessions=5),
            _make_history(2, 10, num_sessions=3),
            _make_history(3, 10, num_sessions=3),
        ]
        matches, unmatched, available, disputes, _ = continuity_pass(
            swimmers, instructors, history
        )
        # Individual got the slot
        assert len(matches) == 1
        assert matches[0]['swimmer_id'] == 1
        # Both pair members flagged as disputed
        assert 2 in disputes
        assert 3 in disputes

    def test_pair_not_disputed_when_instructor_simply_unavailable(self):
        """Pair wants instructor 10 but instructor 10 has no capacity (no individual took it)."""
        swimmers = [
            _make_swimmer(1, pair_id=99),
            _make_swimmer(2, pair_id=99),
        ]
        instructors = []  # instructor 10 simply doesn't exist this slot
        history = [
            _make_history(1, 10),
            _make_history(2, 10),
        ]
        matches, unmatched, available, disputes, _ = continuity_pass(
            swimmers, instructors, history
        )
        assert disputes == set()  # no dispute — instructor just wasn't available


class TestContinuityNotesSuppress:

    def test_avoid_suppresses_continuity(self):
        """If swimmer notes say 'no [instructor name]', skip continuity for that instructor."""
        swimmer = Swimmer(
            swimmer_id=1, first_name="S1", last_name="Test",
            swimmer_type_id=1, skill_level=3, age=10.0,
            has_special_needs=False, notes="no I10 Test"
        )
        instructor = Instructor(
            instructor_id=10, first_name="I10", last_name="Test",
            primary_color_id=1, secondary_color_id=2,
            primary_style_id=1, secondary_style_id=2,
            is_team_captain=False, can_teach_NL=True,
            can_teach_babies=True, can_teach_adults=True,
            can_teach_adapted=True
        )
        history = [_make_history(1, 10, num_sessions=5)]
        matches, unmatched, available, disputes, _ = continuity_pass(
            [swimmer], [instructor], history
        )
        assert len(matches) == 0
        assert swimmer in unmatched


def _make_nonadapted_instructor(iid):
    """Instructor who is NOT adapted-capable (for HC-2 override tests)."""
    return Instructor(
        instructor_id=iid, first_name=f"I{iid}", last_name="Test",
        primary_color_id=1, secondary_color_id=2,
        primary_style_id=1, secondary_style_id=2,
        is_team_captain=False, can_teach_NL=True,
        can_teach_babies=True, can_teach_adults=True,
        can_teach_adapted=False  # not adapted-capable
    )


def _make_nobaby_instructor(iid):
    """Instructor who cannot teach baby swimmers (for HC-3 hard-stop tests)."""
    return Instructor(
        instructor_id=iid, first_name=f"I{iid}", last_name="Test",
        primary_color_id=1, secondary_color_id=2,
        primary_style_id=1, secondary_style_id=2,
        is_team_captain=False, can_teach_NL=True,
        can_teach_babies=False,  # cannot teach babies
        can_teach_adults=True,
        can_teach_adapted=True
    )


class TestAdaptedCapabilityHardConstraint:
    """HC-2 is a hard stop even when a swimmer has continuity."""

    def test_adapted_swimmer_does_not_match_nonadapted_continuity_instructor(self):
        swimmer = _make_swimmer(1, special_needs=True)
        instructor = _make_nonadapted_instructor(100)
        history = [_make_history(1, 100, num_sessions=3)]

        matches, unmatched, available, _, blocked_flags = continuity_pass(
            [swimmer], [instructor], history
        )

        assert matches == []
        assert [item.swimmer_id for item in unmatched] == [1]
        assert [item.instructor_id for item in available] == [100]
        assert blocked_flags[1] == ['continuity_blocked_by_adapted_capability']

    def test_adapted_block_leaves_instructor_capacity_for_phase_two(self):
        adapted = _make_swimmer(1, special_needs=True)
        regular = _make_swimmer(2)
        instructor = _make_nonadapted_instructor(100)
        history = [_make_history(1, 100, num_sessions=3)]

        matches, unmatched, available, _, _ = continuity_pass(
            [adapted, regular], [instructor], history
        )

        assert matches == []
        assert {item.swimmer_id for item in unmatched} == {1, 2}
        assert [item.instructor_id for item in available] == [100]

    def test_normal_match_has_empty_flag_codes(self):
        """A regular continuity match with no HC issues has flag_codes=[]."""
        swimmer = _make_swimmer(1)
        instructor = _make_instructor(100)
        history = [_make_history(1, 100, num_sessions=3)]

        matches, _, _, _, _ = continuity_pass([swimmer], [instructor], history)
        assert len(matches) == 1
        assert matches[0].get('flag_codes') == []

    def test_adapted_swimmer_with_adapted_instructor_matches_normally(self):
        swimmer = _make_swimmer(1, special_needs=True)
        instructor = _make_instructor(100)  # can_teach_adapted=True
        history = [_make_history(1, 100, num_sessions=3)]

        matches, _, _, _, _ = continuity_pass([swimmer], [instructor], history)
        assert len(matches) == 1
        assert matches[0].get('flag_codes') == []

    def test_hc3_baby_still_hard_blocks_continuity(self):
        """HC-3 is NOT overridable: baby swimmer with non-baby-capable instructor → no match."""
        swimmer = _make_swimmer(1, age=1.0)  # baby (< 2.5)
        instructor = _make_nobaby_instructor(100)
        history = [_make_history(1, 100, num_sessions=5)]

        matches, unmatched, available, disputes, _ = continuity_pass(
            [swimmer], [instructor], history
        )
        assert len(matches) == 0, "HC-3 must still block — baby swimmer cannot match non-baby-capable instructor"
        assert any(s.swimmer_id == 1 for s in unmatched)

    def test_pair_with_adapted_swimmer_is_blocked(self):
        swimmer1 = _make_swimmer(1, pair_id=10, special_needs=True)
        swimmer2 = _make_swimmer(2, pair_id=10, special_needs=False)
        instructor = _make_nonadapted_instructor(100)
        history = [
            _make_history(1, 100, num_sessions=3),
            _make_history(2, 100, num_sessions=3),
        ]

        matches, unmatched, available, _, blocked_flags = continuity_pass(
            [swimmer1, swimmer2], [instructor], history
        )
        assert matches == []
        assert {item.swimmer_id for item in unmatched} == {1, 2}
        assert [item.instructor_id for item in available] == [100]
        assert blocked_flags[1] == ['continuity_blocked_by_adapted_capability']

    def test_pair_with_two_adapted_swimmers_records_both_blocks(self):
        swimmer1 = _make_swimmer(1, pair_id=10, special_needs=True)
        swimmer2 = _make_swimmer(2, pair_id=10, special_needs=True)
        instructor = _make_nonadapted_instructor(100)
        history = [
            _make_history(1, 100, num_sessions=3),
            _make_history(2, 100, num_sessions=3),
        ]

        matches, _, _, _, blocked_flags = continuity_pass(
            [swimmer1, swimmer2], [instructor], history
        )
        assert matches == []
        assert blocked_flags == {
            1: ['continuity_blocked_by_adapted_capability'],
            2: ['continuity_blocked_by_adapted_capability'],
        }

    def test_pair_hc3_still_blocks(self):
        """HC-3 remains hard for pairs: baby swimmer + non-baby-capable instructor → no match."""
        swimmer1 = _make_swimmer(1, pair_id=10, age=1.0)  # baby
        swimmer2 = _make_swimmer(2, pair_id=10, age=10.0)
        instructor = _make_nobaby_instructor(100)
        history = [
            _make_history(1, 100, num_sessions=3),
            _make_history(2, 100, num_sessions=3),
        ]

        matches, unmatched, _, _, _ = continuity_pass(
            [swimmer1, swimmer2], [instructor], history
        )
        assert len(matches) == 0, "HC-3 must block pair with baby swimmer"
        assert len(unmatched) == 2


class TestBlockedContinuityFlags:
    """Issues B & C: flags for adult/baby capability blocking continuity (HC-3 hard stop)."""

    def test_continuity_pass_returns_five_values(self):
        """continuity_pass must now return a 5-tuple (adds swimmer_blocked_flags)."""
        swimmers = [_make_swimmer(1)]
        instructors = [_make_instructor(100)]
        history = []
        result = continuity_pass(swimmers, instructors, history)
        assert len(result) == 5, (
            "continuity_pass must return 5 values: matches, unmatched, available, disputes, blocked_flags"
        )

    def test_adult_swimmer_hc3_blocked_returns_adult_flag(self):
        """Adult swimmer whose continuity instructor is not adult-capable → blocked flag in 5th value."""
        swimmer = _make_swimmer(1, age=20.0)  # adult (≥ 18)
        instructor = Instructor(
            instructor_id=100, first_name="I100", last_name="Test",
            primary_color_id=1, secondary_color_id=2,
            primary_style_id=1, secondary_style_id=2,
            is_team_captain=False, can_teach_NL=True,
            can_teach_babies=True, can_teach_adults=False,  # not adult-capable
            can_teach_adapted=True
        )
        history = [_make_history(1, 100, num_sessions=5)]

        matches, unmatched, available, disputes, blocked_flags = continuity_pass(
            [swimmer], [instructor], history
        )
        assert 'continuity_blocked_by_adult_capability' in blocked_flags.get(1, [])

    def test_adult_blocked_swimmer_still_in_unmatched(self):
        """HC-3 hard stop: adult swimmer still goes to unmatched even with flag."""
        swimmer = _make_swimmer(1, age=20.0)
        instructor = Instructor(
            instructor_id=100, first_name="I100", last_name="Test",
            primary_color_id=1, secondary_color_id=2,
            primary_style_id=1, secondary_style_id=2,
            is_team_captain=False, can_teach_NL=True,
            can_teach_babies=True, can_teach_adults=False,
            can_teach_adapted=True
        )
        history = [_make_history(1, 100, num_sessions=5)]

        matches, unmatched, available, disputes, blocked_flags = continuity_pass(
            [swimmer], [instructor], history
        )
        assert len(matches) == 0
        assert any(s.swimmer_id == 1 for s in unmatched)

    def test_baby_swimmer_hc3_blocked_returns_baby_flag(self):
        """Baby swimmer whose continuity instructor is not baby-capable → baby blocked flag."""
        swimmer = _make_swimmer(1, age=1.0)  # baby (< 2.5)
        instructor = _make_nobaby_instructor(100)
        history = [_make_history(1, 100, num_sessions=3)]

        matches, unmatched, available, disputes, blocked_flags = continuity_pass(
            [swimmer], [instructor], history
        )
        assert 'continuity_blocked_by_baby_capability' in blocked_flags.get(1, [])

    def test_no_blocked_flag_when_no_history(self):
        """Swimmer without history has no blocked continuity flags."""
        swimmer = _make_swimmer(1, age=20.0)
        instructor = Instructor(
            instructor_id=100, first_name="I100", last_name="Test",
            primary_color_id=1, secondary_color_id=2,
            primary_style_id=1, secondary_style_id=2,
            is_team_captain=False, can_teach_NL=True,
            can_teach_babies=True, can_teach_adults=False,
            can_teach_adapted=True
        )
        history = []  # no history

        matches, unmatched, available, disputes, blocked_flags = continuity_pass(
            [swimmer], [instructor], history
        )
        assert 1 not in blocked_flags

    def test_no_blocked_flag_when_instructor_capable(self):
        """Adult swimmer with adult-capable instructor → no blocked flags."""
        swimmer = _make_swimmer(1, age=20.0)
        instructor = _make_instructor(100)  # can_teach_adults=True
        history = [_make_history(1, 100, num_sessions=3)]

        matches, unmatched, available, disputes, blocked_flags = continuity_pass(
            [swimmer], [instructor], history
        )
        assert 1 not in blocked_flags

    def test_blocked_flag_not_on_continuity_match(self):
        """The blocked flag must NOT be in a continuity match (the match wasn't made)."""
        swimmer = _make_swimmer(1, age=20.0)
        instructor = Instructor(
            instructor_id=100, first_name="I100", last_name="Test",
            primary_color_id=1, secondary_color_id=2,
            primary_style_id=1, secondary_style_id=2,
            is_team_captain=False, can_teach_NL=True,
            can_teach_babies=True, can_teach_adults=False,
            can_teach_adapted=True
        )
        history = [_make_history(1, 100, num_sessions=5)]

        matches, _, _, _, _ = continuity_pass([swimmer], [instructor], history)
        assert len(matches) == 0  # no continuity match was made


# -------------------------------------------------------------------------
# Phase 3 swimmer_flags merge
# -------------------------------------------------------------------------

class TestGenerateExplanationsSwimmerFlags:
    """Issue B/C: generate_explanations merges swimmer_flags from Phase 1 into match flag_codes."""

    def _make_compatibility_match(self, swimmer_id):
        return {
            'type': 'individual',
            'match_type': 'compatibility',
            'swimmer_id': swimmer_id,
            'swimmer': _make_swimmer(swimmer_id),
            'instructor_id': 10,
            'compatibility_score': 75.0,
            'top_score': 75.0,
            'second_best_score': 60.0,
            # No flag_codes key — as Phase 2 currently produces
        }

    def _make_scorer(self):
        from core.scoring import CompatibilityScorer
        color = {(1, 1): 1, (1, 2): 2, (1, 3): 3, (1, 4): 4}
        style = {(1, 1): 1, (1, 2): 2, (1, 5): 3, (1, 4): 4, (1, 3): 5, (1, 6): 6}
        return CompatibilityScorer(color, style)

    def _make_instructor(self):
        return _make_instructor(10)

    class _MockLoader:
        _styles = {1: 'NR', 2: 'HE', 3: 'TD', 4: 'A', 5: 'SS', 6: 'DIA'}
        _colors = {1: 'Blue', 2: 'Orange', 3: 'Green', 4: 'Gold'}
        _types = {1: 'The Nervous/New'}
        _style_names = {1: 'New RSS', 2: 'High Energy', 3: 'Technique', 4: 'Adapted', 5: 'Soft-Spoken', 6: 'Do-It-All'}

        def __init__(self):
            self.swimmer_types = {
                type_id: type("SwimmerType", (), {"swimmer_type_name": name})()
                for type_id, name in self._types.items()
            }
            self.class_resolution_flags = {}

        def get_style_code(self, style_id): return self._styles.get(style_id)
        def get_color_name(self, color_id): return self._colors.get(color_id)
        def get_style_name(self, style_id): return self._style_names.get(style_id)
        def get_swimmer_type_name(self, type_id): return self._types.get(type_id)

    def test_swimmer_flags_merged_into_match_flag_codes(self):
        """generate_explanations merges swimmer_flags into match flag_codes."""
        from solvers.python_cpsat.engine.phase3_explainability import generate_explanations

        match = self._make_compatibility_match(swimmer_id=1)
        swimmer_flags = {1: ['continuity_blocked_by_adult_capability']}

        results = generate_explanations(
            [match],
            [self._make_instructor()],
            [_make_swimmer(1)],
            self._make_scorer(),
            self._MockLoader(),
            swimmer_flags=swimmer_flags,
        )
        assert 'continuity_blocked_by_adult_capability' in results[0]['flag_codes']

    def test_swimmer_flags_additive_to_existing_flags(self):
        """Merged swimmer_flags don't overwrite existing flag_codes in the match dict."""
        from solvers.python_cpsat.engine.phase3_explainability import generate_explanations

        match = self._make_compatibility_match(swimmer_id=1)
        match['flag_codes'] = ['forced_assignment']  # already has a flag
        swimmer_flags = {1: ['continuity_blocked_by_adult_capability']}

        results = generate_explanations(
            [match],
            [self._make_instructor()],
            [_make_swimmer(1)],
            self._make_scorer(),
            self._MockLoader(),
            swimmer_flags=swimmer_flags,
        )
        assert 'forced_assignment' in results[0]['flag_codes']
        assert 'continuity_blocked_by_adult_capability' in results[0]['flag_codes']

    def test_no_swimmer_flags_param_leaves_match_unchanged(self):
        """Omitting swimmer_flags (or passing None) leaves flag_codes from match dict alone."""
        from solvers.python_cpsat.engine.phase3_explainability import generate_explanations

        match = self._make_compatibility_match(swimmer_id=1)
        match['flag_codes'] = ['forced_assignment']

        results = generate_explanations(
            [match],
            [self._make_instructor()],
            [_make_swimmer(1)],
            self._make_scorer(),
            self._MockLoader(),
        )
        assert results[0]['flag_codes'] == ['forced_assignment']

    def test_swimmer_without_flags_unaffected(self):
        """Swimmer not in swimmer_flags dict does not receive another swimmer's flags."""
        from solvers.python_cpsat.engine.phase3_explainability import generate_explanations

        match = self._make_compatibility_match(swimmer_id=99)
        swimmer_flags = {1: ['continuity_blocked_by_adult_capability']}  # for swimmer 1, not 99

        results = generate_explanations(
            [match],
            [self._make_instructor()],
            [_make_swimmer(99)],
            self._make_scorer(),
            self._MockLoader(),
            swimmer_flags=swimmer_flags,
        )
        # Swimmer 99 must NOT have swimmer 1's flag — that's the behaviour under test.
        # (forced_assignment may also appear here due to a single eligible instructor,
        #  which is correct and tested separately in TestForcedAssignmentFlag.)
        assert 'continuity_blocked_by_adult_capability' not in results[0].get('flag_codes', [])


class TestCapacityConflictFlag:
    """Issue D: continuity_capacity_conflict flag when a swimmer loses their
    continuity instructor to someone else due to capacity."""

    def test_individual_losing_to_higher_seniority_individual_gets_capacity_conflict_flag(self):
        """Swimmer with fewer sessions loses instructor to swimmer with more sessions.
        The loser must have continuity_capacity_conflict in swimmer_blocked_flags."""
        winner = _make_swimmer(1)   # 5 sessions → wins
        loser = _make_swimmer(2)    # 2 sessions → loses
        instructor = _make_instructor(100)
        history = [
            _make_history(1, 100, num_sessions=5),
            _make_history(2, 100, num_sessions=2),
        ]

        _, unmatched, _, _, blocked_flags = continuity_pass(
            [winner, loser], [instructor], history
        )
        assert any(s.swimmer_id == 2 for s in unmatched), "Loser must be in unmatched"
        assert 'continuity_capacity_conflict' in blocked_flags.get(2, []), (
            "Losing swimmer must have continuity_capacity_conflict in blocked_flags"
        )

    def test_winning_individual_has_no_capacity_conflict_flag(self):
        """The swimmer who successfully claims the instructor has no capacity conflict."""
        winner = _make_swimmer(1)
        loser = _make_swimmer(2)
        instructor = _make_instructor(100)
        history = [
            _make_history(1, 100, num_sessions=5),
            _make_history(2, 100, num_sessions=2),
        ]

        matches, _, _, _, blocked_flags = continuity_pass(
            [winner, loser], [instructor], history
        )
        assert any(m['swimmer_id'] == 1 for m in matches), "Winner must have a match"
        assert 'continuity_capacity_conflict' not in blocked_flags.get(1, []), (
            "Winning swimmer must NOT have continuity_capacity_conflict"
        )

    def test_pair_losing_instructor_to_individual_gets_capacity_conflict_flag(self):
        """Pair loses continuity instructor because an individual already claimed it.
        Both pair members must have continuity_capacity_conflict in swimmer_blocked_flags."""
        individual = _make_swimmer(1)                     # claims instructor 100
        pair_s1 = _make_swimmer(2, pair_id=10)            # pair also wants instructor 100
        pair_s2 = _make_swimmer(3, pair_id=10)
        instructor = _make_instructor(100)
        history = [
            _make_history(1, 100, num_sessions=5),
            _make_history(2, 100, num_sessions=3),
            _make_history(3, 100, num_sessions=3),
        ]

        _, unmatched, _, disputed, blocked_flags = continuity_pass(
            [individual, pair_s1, pair_s2], [instructor], history
        )
        assert 'continuity_capacity_conflict' in blocked_flags.get(2, []), (
            "Pair swimmer 1 must have continuity_capacity_conflict"
        )
        assert 'continuity_capacity_conflict' in blocked_flags.get(3, []), (
            "Pair swimmer 2 must have continuity_capacity_conflict"
        )

    def test_pair_capacity_conflict_also_populates_disputed_ids(self):
        """Backward compat: pair losing to an individual populates both
        disputed_swimmer_ids AND swimmer_blocked_flags with the capacity conflict flag."""
        individual = _make_swimmer(1)
        pair_s1 = _make_swimmer(2, pair_id=10)
        pair_s2 = _make_swimmer(3, pair_id=10)
        instructor = _make_instructor(100)
        history = [
            _make_history(1, 100, num_sessions=5),
            _make_history(2, 100, num_sessions=3),
            _make_history(3, 100, num_sessions=3),
        ]

        _, _, _, disputed, blocked_flags = continuity_pass(
            [individual, pair_s1, pair_s2], [instructor], history
        )
        assert 2 in disputed, "Pair swimmer 1 must be in disputed_swimmer_ids"
        assert 3 in disputed, "Pair swimmer 2 must be in disputed_swimmer_ids"
        assert 'continuity_capacity_conflict' in blocked_flags.get(2, [])
        assert 'continuity_capacity_conflict' in blocked_flags.get(3, [])

    def test_no_capacity_conflict_when_swimmer_has_no_history(self):
        """A swimmer with no history has no capacity conflict flag (they were never blocked)."""
        swimmer = _make_swimmer(1)
        instructor = _make_instructor(100)
        history = []  # no history

        _, _, _, _, blocked_flags = continuity_pass([swimmer], [instructor], history)
        assert 'continuity_capacity_conflict' not in blocked_flags.get(1, [])


class TestPairingConflictFlag:
    """Issue E: continuity_pairing_conflict flag when a pair's continuity instructor
    was already taken by a private (individual) continuity swimmer."""

    def test_pair_losing_to_individual_claimant_gets_pairing_conflict_flag(self):
        """Pair's continuity instructor was taken by an individual swimmer.
        Both pair members must have continuity_pairing_conflict in swimmer_blocked_flags."""
        individual = _make_swimmer(1)
        pair_s1 = _make_swimmer(2, pair_id=10)
        pair_s2 = _make_swimmer(3, pair_id=10)
        instructor = _make_instructor(100)
        history = [
            _make_history(1, 100, num_sessions=5),
            _make_history(2, 100, num_sessions=3),
            _make_history(3, 100, num_sessions=3),
        ]

        _, _, _, _, blocked_flags = continuity_pass(
            [individual, pair_s1, pair_s2], [instructor], history
        )
        assert 'continuity_pairing_conflict' in blocked_flags.get(2, []), (
            "Pair swimmer 1 must have continuity_pairing_conflict"
        )
        assert 'continuity_pairing_conflict' in blocked_flags.get(3, []), (
            "Pair swimmer 2 must have continuity_pairing_conflict"
        )

    def test_pairing_conflict_coexists_with_capacity_conflict_for_pair(self):
        """When a pair loses to an individual, both continuity_capacity_conflict
        AND continuity_pairing_conflict must appear in swimmer_blocked_flags."""
        individual = _make_swimmer(1)
        pair_s1 = _make_swimmer(2, pair_id=10)
        pair_s2 = _make_swimmer(3, pair_id=10)
        instructor = _make_instructor(100)
        history = [
            _make_history(1, 100, num_sessions=5),
            _make_history(2, 100, num_sessions=3),
            _make_history(3, 100, num_sessions=3),
        ]

        _, _, _, _, blocked_flags = continuity_pass(
            [individual, pair_s1, pair_s2], [instructor], history
        )
        flags_s1 = blocked_flags.get(2, [])
        assert 'continuity_capacity_conflict' in flags_s1, (
            "continuity_capacity_conflict must still be present (Issue D)"
        )
        assert 'continuity_pairing_conflict' in flags_s1, (
            "continuity_pairing_conflict must also be present (Issue E)"
        )

    def test_individual_vs_individual_does_not_get_pairing_conflict_flag(self):
        """An individual who loses to another individual gets continuity_capacity_conflict,
        but NOT continuity_pairing_conflict (that flag is only for pairs)."""
        winner = _make_swimmer(1)
        loser = _make_swimmer(2)
        instructor = _make_instructor(100)
        history = [
            _make_history(1, 100, num_sessions=5),
            _make_history(2, 100, num_sessions=2),
        ]

        _, _, _, _, blocked_flags = continuity_pass(
            [winner, loser], [instructor], history
        )
        assert 'continuity_pairing_conflict' not in blocked_flags.get(2, []), (
            "Individual swimmers must NOT get continuity_pairing_conflict"
        )

    def test_successful_pair_match_has_no_pairing_conflict_flag(self):
        """A pair that successfully claims their continuity instructor has no pairing conflict."""
        pair_s1 = _make_swimmer(1, pair_id=10)
        pair_s2 = _make_swimmer(2, pair_id=10)
        instructor = _make_instructor(100)
        history = [
            _make_history(1, 100, num_sessions=3),
            _make_history(2, 100, num_sessions=3),
        ]

        matches, _, _, _, blocked_flags = continuity_pass(
            [pair_s1, pair_s2], [instructor], history
        )
        assert len(matches) == 1, "Pair must have a continuity match"
        assert 'continuity_pairing_conflict' not in blocked_flags.get(1, [])
        assert 'continuity_pairing_conflict' not in blocked_flags.get(2, [])


class TestPublicHelpers:

    def test_group_pairs(self):
        swimmers = [_make_swimmer(1, pair_id=10), _make_swimmer(2, pair_id=10), _make_swimmer(3)]
        pairs = group_pairs(swimmers)
        assert len(pairs) == 1

    def test_get_individuals(self):
        swimmers = [_make_swimmer(1, pair_id=10), _make_swimmer(2, pair_id=10), _make_swimmer(3)]
        individuals = get_individuals(swimmers)
        assert len(individuals) == 1
        assert individuals[0].swimmer_id == 3
