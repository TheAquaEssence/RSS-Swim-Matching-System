"""Tests for Phase 3: Explainability Layer (v2)."""

import pytest
from core.scoring import CompatibilityScorer
from solvers.python_cpsat.engine.data_loader import Swimmer, Instructor
from solvers.python_cpsat.engine.phase3_explainability import (
    generate_explanations,
    _calculate_confidence,
    _has_weak_signals,
    get_confidence_category,
)


@pytest.fixture
def rankings():
    color = {
        (1, 1): 1, (1, 2): 2, (1, 3): 3, (1, 4): 4,
        (8, 1): 1, (8, 4): 2, (8, 3): 3, (8, 2): 4,
    }
    style = {
        (1, 1): 1, (1, 2): 2, (1, 5): 3, (1, 4): 4, (1, 3): 5, (1, 6): 6,
        (8, 2): 1, (8, 3): 2, (8, 4): 3, (8, 5): 4, (8, 1): 5, (8, 6): 6,
    }
    return color, style


@pytest.fixture
def scorer(rankings):
    return CompatibilityScorer(*rankings)


def _make_swimmer(sid, type_id=1):
    return Swimmer(
        swimmer_id=sid, first_name=f"S{sid}", last_name="Test",
        swimmer_type_id=type_id, skill_level=3, age=10.0,
        has_special_needs=False, notes=""
    )


def _make_instructor(iid, primary_color=1, secondary_color=2,
                     primary_style=1, secondary_style=2):
    return Instructor(
        instructor_id=iid, first_name=f"I{iid}", last_name="Test",
        primary_color_id=primary_color, secondary_color_id=secondary_color,
        primary_style_id=primary_style, secondary_style_id=secondary_style,
        is_team_captain=False, can_teach_NL=True,
        can_teach_babies=True, can_teach_adults=True,
        can_teach_adapted=True
    )


class MockDataLoader:
    _styles = {1: 'NR', 2: 'HE', 3: 'TD', 4: 'A', 5: 'SS', 6: 'DIA'}
    _colors = {1: 'Blue', 2: 'Orange', 3: 'Green', 4: 'Gold'}
    _types = {1: 'The Nervous/New', 8: 'Non-Response / Unknown'}
    _style_names = {1: 'New RSS', 2: 'High Energy', 3: 'Technique', 4: 'Adapted', 5: 'Soft-Spoken', 6: 'Do-It-All'}

    def __init__(self):
        self.swimmer_types = {
            type_id: type("SwimmerType", (), {"swimmer_type_name": type_name})()
            for type_id, type_name in self._types.items()
        }
        self.class_resolution_flags = {}

    def get_style_code(self, style_id):
        return self._styles.get(style_id)

    def get_color_name(self, color_id):
        return self._colors.get(color_id)

    def get_style_name(self, style_id):
        return self._style_names.get(style_id)

    def get_swimmer_type_name(self, type_id):
        return self._types.get(type_id)


# ============================================================================
# Confidence scoring
# ============================================================================

class TestNewConfidenceFormula:

    def test_continuity_base_is_90(self):
        match = {'match_type': 'continuity', 'type': 'individual',
                 'swimmer_id': 1, 'num_sessions': 3}
        conf = _calculate_confidence(match, disputed_ids=set(), all_instructors=[])
        assert conf == 90  # flat base, no session bonus

    def test_continuity_not_affected_by_session_count(self):
        """Session count no longer adds a bonus."""
        match_1 = {'match_type': 'continuity', 'type': 'individual',
                   'swimmer_id': 1, 'num_sessions': 1}
        match_5 = {'match_type': 'continuity', 'type': 'individual',
                   'swimmer_id': 1, 'num_sessions': 5}
        c1 = _calculate_confidence(match_1, disputed_ids=set(), all_instructors=[])
        c5 = _calculate_confidence(match_5, disputed_ids=set(), all_instructors=[])
        assert c1 == c5 == 90

    def test_compatibility_tiered_base_high(self):
        """Score >= 75 → base 80."""
        match = {'match_type': 'compatibility', 'type': 'individual',
                 'swimmer_id': 1, 'compatibility_score': 80.0,
                 'top_score': 80.0, 'second_best_score': 60.0}
        conf = _calculate_confidence(match, disputed_ids=set(), all_instructors=[])
        # base=80, margin_bonus=min(10, (80-60)/5)=4 → 84
        assert conf == 84

    def test_compatibility_tiered_base_low(self):
        """Score < 25 → base 25."""
        match = {'match_type': 'compatibility', 'type': 'individual',
                 'swimmer_id': 1, 'compatibility_score': 20.0,
                 'top_score': 20.0, 'second_best_score': 15.0}
        conf = _calculate_confidence(match, disputed_ids=set(), all_instructors=[])
        # base=25, margin_bonus=min(10,(20-15)/5)=1 → 26
        assert conf == 26

    def test_dispute_penalty_applied(self):
        """Swimmer with continuity dispute gets -10."""
        match = {'match_type': 'compatibility', 'type': 'individual',
                 'swimmer_id': 1, 'compatibility_score': 80.0,
                 'top_score': 80.0, 'second_best_score': 60.0}
        conf_no_dispute = _calculate_confidence(match, disputed_ids=set(), all_instructors=[])
        conf_dispute = _calculate_confidence(match, disputed_ids={1}, all_instructors=[])
        assert conf_dispute == conf_no_dispute - 10

    def test_confidence_clamped_0_to_100(self):
        match = {'match_type': 'compatibility', 'type': 'individual',
                 'swimmer_id': 1, 'compatibility_score': 5.0,
                 'top_score': 5.0, 'second_best_score': 0.0}
        conf = _calculate_confidence(match, disputed_ids={1}, all_instructors=[])
        assert 0 <= conf <= 100


class TestWeakSignals:

    def test_good_match_no_weak_signals(self, scorer):
        # Blue primary (rank 1), NR primary (rank 1) — great match
        result = scorer.score(1, 1, 2, 1, 2, 'NR')
        assert _has_weak_signals(result) is False

    def test_worst_color_triggers_weak(self, scorer):
        # Gold primary (rank 4) — worst color for type 1
        result = scorer.score(1, 4, 1, 1, 2, 'NR')
        assert _has_weak_signals(result) is True

    def test_poor_style_triggers_weak(self, scorer):
        # TD primary (rank 5) — poor style for type 1
        result = scorer.score(1, 1, 2, 3, 5, 'TD')
        assert _has_weak_signals(result) is True


# ============================================================================
# Confidence categories
# ============================================================================

class TestConfidenceCategory:

    def test_excellent(self):
        assert get_confidence_category(95) == 'Excellent'

    def test_strong(self):
        assert get_confidence_category(85) == 'Strong'

    def test_good(self):
        assert get_confidence_category(75) == 'Good'

    def test_moderate(self):
        assert get_confidence_category(65) == 'Moderate'

    def test_weak(self):
        assert get_confidence_category(55) == 'Weak'

    def test_poor(self):
        assert get_confidence_category(40) == 'Poor'


# ============================================================================
# Full explanation generation
# ============================================================================

class TestOutputCSVDisputeColumn:

    def test_dispute_column_present_in_csv(self, tmp_path):
        """Output CSV must include continuity_dispute column."""
        import pandas as pd
        from solvers.python_cpsat.engine.phase3_explainability import generate_output_csv
        from solvers.python_cpsat.engine.data_loader import Class

        mock_class = Class(
            class_id=1, instructor_id=10, day_of_week='Monday',
            start_time='09:00', end_time='09:30'
        )
        assignment = {
            'type': 'individual',
            'match_type': 'continuity',
            'swimmer_id': 1,
            'swimmer': _make_swimmer(1),
            'instructor_id': 10,
            'instructor_name': 'I10 Test',
            'confidence': 90.0,
            'reason_summary': 'Continuity: 3 session(s)',
            'compatibility_score': None,
        }
        output_path = str(tmp_path / 'out.csv')
        df = generate_output_csv(
            [assignment],
            {1: mock_class},
            output_path,
            disputed_ids={1}
        )
        assert 'continuity_dispute' in df.columns
        assert df.iloc[0]['continuity_dispute'] == True

    def test_no_dispute_marked_false(self, tmp_path):
        """Swimmers not in disputed set get continuity_dispute = False."""
        from solvers.python_cpsat.engine.phase3_explainability import generate_output_csv
        from solvers.python_cpsat.engine.data_loader import Class

        mock_class = Class(
            class_id=1, instructor_id=10, day_of_week='Monday',
            start_time='09:00', end_time='09:30'
        )
        assignment = {
            'type': 'individual',
            'match_type': 'continuity',
            'swimmer_id': 1,
            'swimmer': _make_swimmer(1),
            'instructor_id': 10,
            'instructor_name': 'I10 Test',
            'confidence': 90.0,
            'reason_summary': 'Continuity: 3 session(s)',
            'compatibility_score': None,
        }
        output_path = str(tmp_path / 'out.csv')
        df = generate_output_csv(
            [assignment],
            {1: mock_class},
            output_path,
            disputed_ids=set()
        )
        assert df.iloc[0]['continuity_dispute'] == False

    def test_name_columns_are_exported_before_id_columns(self, tmp_path):
        """CSV should surface human-readable names before raw IDs."""
        from solvers.python_cpsat.engine.phase3_explainability import generate_output_csv
        from solvers.python_cpsat.engine.data_loader import Class

        mock_class = Class(
            class_id=1, instructor_id=10, day_of_week='Monday',
            start_time='09:00', end_time='09:30'
        )
        assignment = {
            'type': 'pair',
            'match_type': 'compatibility',
            'swimmer_1_id': 1,
            'swimmer_2_id': 2,
            'swimmer_1': Swimmer(
                swimmer_id=1, first_name='Alice', last_name='Able',
                swimmer_type_id=1, skill_level=3, age=10.0,
                has_special_needs=False, notes=''
            ),
            'swimmer_2': Swimmer(
                swimmer_id=2, first_name='Bob', last_name='Baker',
                swimmer_type_id=1, skill_level=3, age=10.0,
                has_special_needs=False, notes=''
            ),
            'instructor_id': 10,
            'instructor_name': 'I10 Test',
            'confidence': 88.0,
            'reason_summary': 'Compatibility match',
            'compatibility_score': 81.0,
        }
        output_path = str(tmp_path / 'out.csv')
        df = generate_output_csv([assignment], {1: mock_class}, output_path, disputed_ids=set())

        columns = list(df.columns)
        assert columns.index('instructor_name') < columns.index('instructor_id')
        assert columns.index('swimmer_1_name') < columns.index('swimmer_1_id')
        assert columns.index('swimmer_2_name') < columns.index('swimmer_2_id')
        assert df.iloc[0]['instructor_name'] == 'I10 Test'
        assert df.iloc[0]['swimmer_1_name'] == 'Alice Able'
        assert df.iloc[0]['swimmer_2_name'] == 'Bob Baker'


class TestGenerateExplanations:

    def test_continuity_explanation(self, scorer):
        swimmer = _make_swimmer(1)
        instructor = _make_instructor(100)
        match = {
            'type': 'individual',
            'swimmer_id': 1,
            'swimmer': swimmer,
            'instructor_id': 100,
            'match_type': 'continuity',
            'num_sessions': 3,
        }

        results = generate_explanations(
            [match], [instructor], [swimmer], scorer, MockDataLoader()
        )
        assert len(results) == 1
        assert 'confidence' in results[0]
        assert 'explanation' in results[0]
        assert 'Continuity' in results[0]['explanation']

    def test_compatibility_explanation(self, scorer):
        swimmer = _make_swimmer(1)
        instructor = _make_instructor(100)
        match = {
            'type': 'individual',
            'swimmer_id': 1,
            'swimmer': swimmer,
            'instructor_id': 100,
            'match_type': 'compatibility',
            'compatibility_score': 80.0,
        }

        results = generate_explanations(
            [match], [instructor], [swimmer], scorer, MockDataLoader()
        )
        assert len(results) == 1
        assert 'Compatibility' in results[0]['explanation']
        assert '#' in results[0]['explanation']  # Should mention ranks

    def test_non_response_swimmer_type_adds_review_flag(self, scorer):
        swimmer = _make_swimmer(1, type_id=8)
        instructor = _make_instructor(100)
        match = {
            'type': 'individual',
            'swimmer_id': 1,
            'swimmer': swimmer,
            'instructor_id': 100,
            'match_type': 'compatibility',
            'compatibility_score': 80.0,
        }

        results = generate_explanations(
            [match], [instructor], [swimmer], scorer, MockDataLoader()
        )
        assert 'non_response_swimmer_type' in results[0]['flag_codes']


class TestFlagColumns:
    """New flag columns added to the output CSV (Issue H)."""

    def _make_class(self):
        from solvers.python_cpsat.engine.data_loader import Class
        return Class(
            class_id=1, instructor_id=10, day_of_week='Monday',
            start_time='09:00', end_time='09:30'
        )

    def _make_assignment(self, flag_codes=None):
        return {
            'type': 'individual',
            'match_type': 'continuity',
            'swimmer_id': 1,
            'swimmer': _make_swimmer(1),
            'instructor_id': 10,
            'instructor_name': 'I10 Test',
            'confidence': 90.0,
            'reason_summary': 'Continuity: 3 session(s)',
            'compatibility_score': None,
            'flag_codes': flag_codes or [],
        }

    def test_flag_columns_present_in_csv(self, tmp_path):
        """Output CSV must include the four new flag columns."""
        from solvers.python_cpsat.engine.phase3_explainability import generate_output_csv

        df = generate_output_csv(
            [self._make_assignment()],
            {1: self._make_class()},
            str(tmp_path / 'out.csv'),
            disputed_ids=set(),
        )
        assert 'flag_codes' in df.columns
        assert 'flag_summary' in df.columns
        assert 'review_action' in df.columns
        assert 'review_severity' in df.columns

    def test_continuity_dispute_still_present(self, tmp_path):
        """continuity_dispute column must still exist for backward compatibility."""
        from solvers.python_cpsat.engine.phase3_explainability import generate_output_csv

        df = generate_output_csv(
            [self._make_assignment()],
            {1: self._make_class()},
            str(tmp_path / 'out.csv'),
            disputed_ids=set(),
        )
        assert 'continuity_dispute' in df.columns

    def test_no_flags_gives_empty_flag_codes(self, tmp_path):
        """When assignment has no flag_codes, flag_codes column is empty string."""
        from solvers.python_cpsat.engine.phase3_explainability import generate_output_csv

        df = generate_output_csv(
            [self._make_assignment(flag_codes=[])],
            {1: self._make_class()},
            str(tmp_path / 'out.csv'),
            disputed_ids=set(),
        )
        assert df.iloc[0]['flag_codes'] == ''

    def test_no_flags_gives_none_severity(self, tmp_path):
        """When assignment has no flag_codes, review_severity is 'none'."""
        from solvers.python_cpsat.engine.phase3_explainability import generate_output_csv

        df = generate_output_csv(
            [self._make_assignment(flag_codes=[])],
            {1: self._make_class()},
            str(tmp_path / 'out.csv'),
            disputed_ids=set(),
        )
        assert df.iloc[0]['review_severity'] == 'none'

    def test_flag_codes_written_as_comma_separated(self, tmp_path):
        """Multiple flag codes are joined with commas in the CSV column."""
        from solvers.python_cpsat.engine.phase3_explainability import generate_output_csv

        assignment = self._make_assignment(flag_codes=[
            'forced_assignment',
            'match_confidence_below_70',
        ])
        df = generate_output_csv(
            [assignment],
            {1: self._make_class()},
            str(tmp_path / 'out.csv'),
            disputed_ids=set(),
        )
        written = df.iloc[0]['flag_codes']
        assert 'forced_assignment' in written
        assert 'match_confidence_below_70' in written

    def test_urgent_flag_sets_severity_urgent(self, tmp_path):
        """An urgent flag code sets review_severity to 'urgent'."""
        from solvers.python_cpsat.engine.phase3_explainability import generate_output_csv

        assignment = self._make_assignment(flag_codes=[
            'continuity_overrides_adapted_capability',
        ])
        df = generate_output_csv(
            [assignment],
            {1: self._make_class()},
            str(tmp_path / 'out.csv'),
            disputed_ids=set(),
        )
        assert df.iloc[0]['review_severity'] == 'urgent'

    def test_review_action_matches_highest_severity_flag(self, tmp_path):
        """review_action is the default_review_action of the highest-severity flag."""
        from solvers.python_cpsat.engine.phase3_explainability import generate_output_csv
        from core.flags import FLAG_CODES

        assignment = self._make_assignment(flag_codes=[
            'match_confidence_below_70',             # info
            'continuity_overrides_adapted_capability',  # urgent
        ])
        df = generate_output_csv(
            [assignment],
            {1: self._make_class()},
            str(tmp_path / 'out.csv'),
            disputed_ids=set(),
        )
        expected_action = FLAG_CODES['continuity_overrides_adapted_capability']['default_review_action']
        assert df.iloc[0]['review_action'] == expected_action

    def test_flag_summary_describes_highest_severity_flag(self, tmp_path):
        """flag_summary contains the description of the highest-severity flag."""
        from solvers.python_cpsat.engine.phase3_explainability import generate_output_csv
        from core.flags import FLAG_CODES

        assignment = self._make_assignment(flag_codes=[
            'continuity_overrides_adapted_capability',
        ])
        df = generate_output_csv(
            [assignment],
            {1: self._make_class()},
            str(tmp_path / 'out.csv'),
            disputed_ids=set(),
        )
        expected_desc = FLAG_CODES['continuity_overrides_adapted_capability']['description']
        assert df.iloc[0]['flag_summary'] == expected_desc

    def test_assignment_without_flag_codes_key_treated_as_no_flags(self, tmp_path):
        """Assignments that predate flag_codes key degrade gracefully."""
        from solvers.python_cpsat.engine.phase3_explainability import generate_output_csv

        assignment = {
            'type': 'individual',
            'match_type': 'continuity',
            'swimmer_id': 1,
            'swimmer': _make_swimmer(1),
            'instructor_id': 10,
            'instructor_name': 'I10 Test',
            'confidence': 90.0,
            'reason_summary': 'Continuity: 3 session(s)',
            'compatibility_score': None,
            # No 'flag_codes' key at all
        }
        df = generate_output_csv(
            [assignment],
            {1: self._make_class()},
            str(tmp_path / 'out.csv'),
            disputed_ids=set(),
        )
        assert df.iloc[0]['flag_codes'] == ''
        assert df.iloc[0]['review_severity'] == 'none'


class TestForcedAssignmentFlag:
    """Issue F: forced_assignment flag must appear in flag_codes when Phase 3
    applies the forced_penalty (swimmer has only 1 eligible instructor)."""

    def _make_compat_match(self, swimmer, instructor):
        return {
            'type': 'individual',
            'match_type': 'compatibility',
            'swimmer_id': swimmer.swimmer_id,
            'swimmer': swimmer,
            'instructor_id': instructor.instructor_id,
            'compatibility_score': 80.0,
            'top_score': 80.0,
            'second_best_score': 60.0,
        }

    def test_compatibility_match_with_one_eligible_instructor_gets_forced_flag(self, scorer):
        """Compatibility match where only 1 instructor is eligible → forced_assignment in flag_codes."""
        swimmer = _make_swimmer(1)
        instructor = _make_instructor(100)
        match = self._make_compat_match(swimmer, instructor)

        results = generate_explanations(
            [match],
            [instructor],   # only 1 instructor → eligible_count == 1 → forced
            [swimmer],
            scorer,
            MockDataLoader(),
        )
        assert 'forced_assignment' in results[0]['flag_codes'], (
            "forced_assignment flag must be added when swimmer has only 1 eligible instructor"
        )

    def test_compatibility_match_with_multiple_instructors_no_forced_flag(self, scorer):
        """Compatibility match with 2+ eligible instructors → no forced_assignment flag."""
        swimmer = _make_swimmer(1)
        instructor1 = _make_instructor(100)
        instructor2 = _make_instructor(101)
        match = self._make_compat_match(swimmer, instructor1)

        results = generate_explanations(
            [match],
            [instructor1, instructor2],   # 2 instructors → not forced
            [swimmer],
            scorer,
            MockDataLoader(),
        )
        assert 'forced_assignment' not in results[0]['flag_codes'], (
            "forced_assignment must NOT appear when multiple eligible instructors exist"
        )

    def test_continuity_match_never_gets_forced_assignment_flag(self, scorer):
        """Continuity matches must never receive the forced_assignment flag,
        even when only 1 instructor is in the pool."""
        swimmer = _make_swimmer(1)
        instructor = _make_instructor(100)
        match = {
            'type': 'individual',
            'match_type': 'continuity',   # continuity, not compatibility
            'swimmer_id': swimmer.swimmer_id,
            'swimmer': swimmer,
            'instructor_id': instructor.instructor_id,
            'num_sessions': 3,
        }

        results = generate_explanations(
            [match],
            [instructor],   # only 1 instructor but continuity → no forced flag
            [swimmer],
            scorer,
            MockDataLoader(),
        )
        assert 'forced_assignment' not in results[0].get('flag_codes', []), (
            "Continuity matches must never get forced_assignment flag"
        )

    def test_forced_assignment_flag_coexists_with_other_flags(self, scorer):
        """forced_assignment is additive — existing flag_codes are preserved."""
        swimmer = _make_swimmer(1)
        instructor = _make_instructor(100)
        match = self._make_compat_match(swimmer, instructor)
        match['flag_codes'] = ['continuity_blocked_by_adult_capability']  # pre-existing flag

        results = generate_explanations(
            [match],
            [instructor],   # 1 instructor → forced
            [swimmer],
            scorer,
            MockDataLoader(),
        )
        flags = results[0]['flag_codes']
        assert 'forced_assignment' in flags
        assert 'continuity_blocked_by_adult_capability' in flags


def _make_adapted_swimmer(sid):
    """Helper: adapted swimmer (has_special_needs=True)."""
    return Swimmer(
        swimmer_id=sid, first_name=f"A{sid}", last_name="Test",
        swimmer_type_id=1, skill_level=3, age=10.0,
        has_special_needs=True, notes=""
    )


def _make_nonadapted_instructor(iid):
    """Helper: instructor who cannot teach adapted swimmers."""
    return Instructor(
        instructor_id=iid, first_name=f"I{iid}", last_name="Test",
        primary_color_id=1, secondary_color_id=2,
        primary_style_id=1, secondary_style_id=2,
        is_team_captain=False, can_teach_NL=True,
        can_teach_babies=True, can_teach_adults=True,
        can_teach_adapted=False,  # ← cannot teach adapted
    )


class TestAdaptedSingleInstructorFlag:
    """Issue G: adapted_swimmer_single_legal_instructor flag when an adapted
    swimmer has exactly one adapted-capable instructor available in the pool."""

    def _make_compat_match(self, swimmer, instructor):
        return {
            'type': 'individual',
            'match_type': 'compatibility',
            'swimmer_id': swimmer.swimmer_id,
            'swimmer': swimmer,
            'instructor_id': instructor.instructor_id,
            'compatibility_score': 80.0,
            'top_score': 80.0,
            'second_best_score': 60.0,
        }

    def test_adapted_swimmer_with_one_adapted_instructor_gets_flag(self, scorer):
        """Adapted swimmer matched against the only adapted-capable instructor
        in the pool → adapted_swimmer_single_legal_instructor in flag_codes."""
        swimmer = _make_adapted_swimmer(1)
        adapted_instr = _make_instructor(100)          # can_teach_adapted=True
        match = self._make_compat_match(swimmer, adapted_instr)

        results = generate_explanations(
            [match],
            [adapted_instr],                           # 1 adapted-capable instructor
            [swimmer],
            scorer,
            MockDataLoader(),
        )
        assert 'adapted_swimmer_single_legal_instructor' in results[0]['flag_codes'], (
            "Flag must fire when adapted swimmer has only 1 adapted-capable instructor"
        )

    def test_adapted_swimmer_with_multiple_adapted_instructors_no_flag(self, scorer):
        """Adapted swimmer with 2+ adapted-capable instructors in pool → no flag."""
        swimmer = _make_adapted_swimmer(1)
        instr1 = _make_instructor(100)
        instr2 = _make_instructor(101)
        match = self._make_compat_match(swimmer, instr1)

        results = generate_explanations(
            [match],
            [instr1, instr2],                          # 2 adapted-capable instructors
            [swimmer],
            scorer,
            MockDataLoader(),
        )
        assert 'adapted_swimmer_single_legal_instructor' not in results[0]['flag_codes'], (
            "Flag must NOT fire when multiple adapted-capable instructors exist"
        )

    def test_non_adapted_swimmer_never_gets_flag(self, scorer):
        """Non-adapted swimmer with 1 instructor in pool must NOT get this flag."""
        swimmer = _make_swimmer(1)                     # has_special_needs=False
        instructor = _make_instructor(100)
        match = self._make_compat_match(swimmer, instructor)

        results = generate_explanations(
            [match],
            [instructor],
            [swimmer],
            scorer,
            MockDataLoader(),
        )
        assert 'adapted_swimmer_single_legal_instructor' not in results[0]['flag_codes'], (
            "Flag is only for adapted swimmers"
        )

    def test_flag_fires_on_continuity_match_for_adapted_swimmer(self, scorer):
        """Flag must fire for continuity matches too — it's a pool-coverage signal,
        not limited to compatibility assignments."""
        swimmer = _make_adapted_swimmer(1)
        adapted_instr = _make_instructor(100)
        continuity_match = {
            'type': 'individual',
            'match_type': 'continuity',                # continuity, not compatibility
            'swimmer_id': swimmer.swimmer_id,
            'swimmer': swimmer,
            'instructor_id': adapted_instr.instructor_id,
            'num_sessions': 3,
        }

        results = generate_explanations(
            [continuity_match],
            [adapted_instr],                           # 1 adapted-capable instructor
            [swimmer],
            scorer,
            MockDataLoader(),
        )
        assert 'adapted_swimmer_single_legal_instructor' in results[0]['flag_codes'], (
            "Flag must fire on continuity matches too — it reflects pool coverage, not match phase"
        )

    def test_nonadapted_instructors_in_pool_do_not_count_toward_adapted_capacity(self, scorer):
        """Pool has 1 adapted + 1 non-adapted instructor.
        Adapted swimmer still has only 1 legal adapted option → flag fires."""
        swimmer = _make_adapted_swimmer(1)
        adapted_instr = _make_instructor(100)          # can_teach_adapted=True
        nonadapted_instr = _make_nonadapted_instructor(101)  # can_teach_adapted=False
        match = self._make_compat_match(swimmer, adapted_instr)

        results = generate_explanations(
            [match],
            [adapted_instr, nonadapted_instr],         # 1 adapted + 1 non-adapted
            [swimmer],
            scorer,
            MockDataLoader(),
        )
        assert 'adapted_swimmer_single_legal_instructor' in results[0]['flag_codes'], (
            "Non-adapted instructors must not count toward adapted coverage"
        )


class TestUnassignedReport:

    def test_generate_unassigned_report_returns_dataframe(self, tmp_path):
        from solvers.python_cpsat.engine.phase3_explainability import generate_unassigned_report
        swimmers = [_make_swimmer(1), _make_swimmer(2)]
        reasons = {1: 'no_available_instructor', 2: 'hard_constraint'}
        output_path = str(tmp_path / 'unassigned.csv')
        df = generate_unassigned_report(swimmers, reasons, output_path)
        assert len(df) == 2
        assert 'swimmer_id' in df.columns
        assert 'reason' in df.columns

    def test_empty_unassigned_report(self, tmp_path):
        from solvers.python_cpsat.engine.phase3_explainability import generate_unassigned_report
        output_path = str(tmp_path / 'unassigned.csv')
        df = generate_unassigned_report([], {}, output_path)
        assert len(df) == 0


# =============================================================================
# non_response_swimmer_type flag
# =============================================================================

class TestNonResponseSwimmerTypeFlag:
    """non_response_swimmer_type flag fires for swimmers whose type matches the configured non-response type (id=8)."""

    @pytest.fixture
    def scorer_nr(self):
        """Scorer that includes type_id=8 (non-response) neutral rankings alongside type_id=1."""
        color = {
            (1, 1): 1, (1, 2): 2, (1, 3): 3, (1, 4): 4,
            (8, 1): 1, (8, 2): 2, (8, 3): 3, (8, 4): 4,
        }
        style = {
            (1, 1): 1, (1, 2): 2, (1, 5): 3, (1, 4): 4, (1, 3): 5, (1, 6): 6,
            (8, 1): 1, (8, 2): 2, (8, 3): 3, (8, 4): 4, (8, 5): 5, (8, 6): 6,
        }
        return CompatibilityScorer(color, style)

    def _make_compat_match(self, swimmer, instructor):
        return {
            'swimmer_id': swimmer.swimmer_id,
            'instructor_id': instructor.instructor_id,
            'match_type': 'compatibility',
            'type': 'individual',
            'compatibility_score': 75.0,
            'swimmer': swimmer,
            'flag_codes': [],
        }

    def _make_continuity_match(self, swimmer, instructor):
        return {
            'swimmer_id': swimmer.swimmer_id,
            'instructor_id': instructor.instructor_id,
            'match_type': 'continuity',
            'type': 'individual',
            'num_sessions': 1,
            'swimmer': swimmer,
            'flag_codes': [],
        }

    def test_flag_added_for_individual_compatibility_match(self, scorer_nr):
        swimmer = _make_swimmer(1, type_id=8)
        instructor = _make_instructor(1)
        results = generate_explanations(
            [self._make_compat_match(swimmer, instructor)],
            [instructor], [swimmer], scorer_nr, MockDataLoader(),
        )
        assert 'non_response_swimmer_type' in results[0]['flag_codes']

    def test_flag_added_for_continuity_match(self, scorer_nr):
        swimmer = _make_swimmer(1, type_id=8)
        instructor = _make_instructor(1)
        results = generate_explanations(
            [self._make_continuity_match(swimmer, instructor)],
            [instructor], [swimmer], scorer_nr, MockDataLoader(),
        )
        assert 'non_response_swimmer_type' in results[0]['flag_codes']

    def test_flag_not_added_for_normal_swimmer(self, scorer_nr):
        """type_id != non-response must NOT trigger the flag."""
        swimmer = _make_swimmer(1, type_id=1)
        instructor = _make_instructor(1)
        results = generate_explanations(
            [self._make_compat_match(swimmer, instructor)],
            [instructor], [swimmer], scorer_nr, MockDataLoader(),
        )
        assert 'non_response_swimmer_type' not in results[0]['flag_codes']

    def test_flag_fires_for_pair_when_swimmer_1_is_type_zero(self, scorer_nr):
        """Flag fires if swimmer_1 in a pair has the non-response type_id (8)."""
        s1 = _make_swimmer(1, type_id=8)
        s2 = _make_swimmer(2, type_id=1)
        instructor = _make_instructor(1)
        match = {
            'swimmer_1_id': 1, 'swimmer_2_id': 2,
            'instructor_id': 1,
            'match_type': 'compatibility', 'type': 'pair',
            'compatibility_score': 70.0,
            'swimmer_1': s1, 'swimmer_2': s2,
            'swimmer_1_score': 70.0, 'swimmer_2_score': 70.0,
            'flag_codes': [],
        }
        results = generate_explanations(
            [match], [instructor], [s1, s2], scorer_nr, MockDataLoader(),
        )
        assert 'non_response_swimmer_type' in results[0]['flag_codes']

    def test_flag_coexists_with_other_flags(self, scorer_nr):
        """non_response_swimmer_type is additive — existing flags are preserved."""
        swimmer = _make_swimmer(1, type_id=8)
        instructor = _make_instructor(1)
        match = self._make_compat_match(swimmer, instructor)
        match['flag_codes'] = ['continuity_blocked_by_adult_capability']
        results = generate_explanations(
            [match], [instructor], [swimmer], scorer_nr, MockDataLoader(),
        )
        flags = results[0]['flag_codes']
        assert 'non_response_swimmer_type' in flags
        assert 'continuity_blocked_by_adult_capability' in flags
