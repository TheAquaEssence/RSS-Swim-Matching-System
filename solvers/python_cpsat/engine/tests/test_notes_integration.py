"""Tests for P3 notes keyword integration in CP-SAT solver."""
import pytest
from unittest.mock import MagicMock
from solvers.python_cpsat.engine.data_loader import Swimmer, Instructor
from solvers.python_cpsat.engine.phase2_cpsat import _compute_all_scores
from solvers.python_cpsat.engine.notes_parser import parse_notes


def _make_swimmer(swimmer_id, notes='', pair_id=None, **kwargs):
    """Create a test Swimmer."""
    defaults = {
        'swimmer_id': swimmer_id,
        'first_name': 'Test',
        'last_name': f'Swimmer{swimmer_id}',
        'swimmer_type_id': 1,
        'skill_level': 5,
        'age': 8.0,
        'has_special_needs': False,
        'notes': notes,
        'pair_id': pair_id,
    }
    defaults.update(kwargs)
    return Swimmer(**defaults)


def _make_instructor(instructor_id, first_name='Test', last_name='Instructor', **kwargs):
    """Create a test Instructor."""
    defaults = {
        'instructor_id': instructor_id,
        'first_name': first_name,
        'last_name': last_name,
        'primary_color_id': 1,
        'secondary_color_id': 2,
        'primary_style_id': 1,
        'secondary_style_id': 2,
        'is_team_captain': False,
        'can_teach_NL': False,
        'can_teach_adapted': True,
        'can_teach_babies': True,
        'can_teach_adults': True,
    }
    defaults.update(kwargs)
    return Instructor(**defaults)


class TestNotesBoosts:
    """Test that prefer/always keywords boost compatibility scores."""

    def test_prefer_boosts_score(self):
        """prefer keyword should moderately boost the instructor's score."""
        swimmer = _make_swimmer(1, notes='prefer Jane Smith')
        instr_preferred = _make_instructor(1, first_name='Jane', last_name='Smith')
        instr_other = _make_instructor(2, first_name='Bob', last_name='Jones')

        scorer = MagicMock()
        scorer.score_match_value.return_value = 50.0

        data_loader = MagicMock()
        data_loader.get_style_code = MagicMock()

        scores, _ = _compute_all_scores(
            [swimmer], [], [instr_preferred, instr_other], scorer, data_loader
        )

        preferred_score = scores[('individual', 1, 1)]
        other_score = scores[('individual', 1, 2)]

        assert preferred_score > other_score
        assert preferred_score == 65.0  # 50 + 15 prefer bonus
        assert other_score == 50.0

    def test_always_boosts_score_strongly(self):
        """always keyword should strongly boost, more than prefer."""
        swimmer = _make_swimmer(1, notes='always Jane Smith')
        instr = _make_instructor(1, first_name='Jane', last_name='Smith')

        scorer = MagicMock()
        scorer.score_match_value.return_value = 50.0

        data_loader = MagicMock()
        data_loader.get_style_code = MagicMock()

        scores, _ = _compute_all_scores(
            [swimmer], [], [instr], scorer, data_loader
        )

        assert scores[('individual', 1, 1)] == 90.0  # 50 + 40 always bonus

    def test_always_beats_prefer(self):
        """always bonus (40) should be larger than prefer bonus (15)."""
        swimmer_always = _make_swimmer(1, notes='always Jane Smith')
        swimmer_prefer = _make_swimmer(2, notes='prefer Jane Smith')
        instr = _make_instructor(1, first_name='Jane', last_name='Smith')

        scorer = MagicMock()
        scorer.score_match_value.return_value = 50.0

        data_loader = MagicMock()
        data_loader.get_style_code = MagicMock()

        scores, _ = _compute_all_scores(
            [swimmer_always, swimmer_prefer], [], [instr], scorer, data_loader
        )

        assert scores[('individual', 1, 1)] > scores[('individual', 2, 1)]

    def test_score_capped_at_100(self):
        """Boosted score should not exceed 100."""
        swimmer = _make_swimmer(1, notes='always Jane Smith')
        instr = _make_instructor(1, first_name='Jane', last_name='Smith')

        scorer = MagicMock()
        scorer.score_match_value.return_value = 85.0

        data_loader = MagicMock()
        data_loader.get_style_code = MagicMock()

        scores, _ = _compute_all_scores(
            [swimmer], [], [instr], scorer, data_loader
        )

        assert scores[('individual', 1, 1)] == 100.0  # 85 + 40 = 125, capped at 100

    def test_no_boost_without_matching_name(self):
        """Notes mentioning a different name should not boost."""
        swimmer = _make_swimmer(1, notes='prefer Alice Wonderland')
        instr = _make_instructor(1, first_name='Jane', last_name='Smith')

        scorer = MagicMock()
        scorer.score_match_value.return_value = 50.0

        data_loader = MagicMock()
        data_loader.get_style_code = MagicMock()

        scores, _ = _compute_all_scores(
            [swimmer], [], [instr], scorer, data_loader
        )

        assert scores[('individual', 1, 1)] == 50.0  # No boost

    def test_pair_boost_from_either_swimmer(self):
        """Pair score should be boosted if either swimmer has prefer/always."""
        swimmer1 = _make_swimmer(1, notes='prefer Jane Smith', pair_id=100)
        swimmer2 = _make_swimmer(2, notes='', pair_id=100)
        instr = _make_instructor(1, first_name='Jane', last_name='Smith')

        scorer = MagicMock()
        scorer.score_pair_match.return_value = (50.0, 55.0, 45.0)

        data_loader = MagicMock()
        data_loader.get_style_code = MagicMock()

        scores, _ = _compute_all_scores(
            [], [(swimmer1, swimmer2)], [instr], scorer, data_loader
        )

        pair_key = (1, 2)
        assert scores[('pair', pair_key, 1)] == 65.0  # 50 + 15 prefer bonus

    def test_pair_boost_uses_max(self):
        """If one swimmer has always and the other prefer, use the larger boost."""
        swimmer1 = _make_swimmer(1, notes='always Jane Smith', pair_id=100)
        swimmer2 = _make_swimmer(2, notes='prefer Jane Smith', pair_id=100)
        instr = _make_instructor(1, first_name='Jane', last_name='Smith')

        scorer = MagicMock()
        scorer.score_pair_match.return_value = (50.0, 55.0, 45.0)

        data_loader = MagicMock()
        data_loader.get_style_code = MagicMock()

        scores, _ = _compute_all_scores(
            [], [(swimmer1, swimmer2)], [instr], scorer, data_loader
        )

        pair_key = (1, 2)
        assert scores[('pair', pair_key, 1)] == 90.0  # 50 + 40 always (max)


class TestNotesHardConstraints:
    """Test that avoid/never keywords prevent assignment in Phase 2."""

    def test_avoid_parsed_correctly(self):
        """avoid keyword should be recognized by the parser."""
        parsed = parse_notes('avoid Jane Smith')
        assert 'Jane Smith' in parsed['avoid']

    def test_never_parsed_correctly(self):
        """never keyword should be recognized by the parser."""
        parsed = parse_notes('never Bob Jones')
        assert 'Bob Jones' in parsed['never']

    def test_no_mapped_to_avoid(self):
        """no keyword should be treated as avoid."""
        parsed = parse_notes('no Jane Smith')
        assert 'Jane Smith' in parsed['avoid']

    def test_avoid_and_never_combined(self):
        """Multiple exclusion keywords should all be captured."""
        parsed = parse_notes('avoid Jane Smith; never Bob Jones')
        assert 'Jane Smith' in parsed['avoid']
        assert 'Bob Jones' in parsed['never']

    def test_empty_notes_no_exclusions(self):
        """Empty notes should produce no exclusions."""
        parsed = parse_notes('')
        assert parsed['avoid'] == []
        assert parsed['never'] == []
