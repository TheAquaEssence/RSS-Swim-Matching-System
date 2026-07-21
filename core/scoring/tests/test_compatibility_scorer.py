"""Tests for CompatibilityScorer."""

import pytest
from core.scoring.compatibility_scorer import (
    CompatibilityScorer,
    CompatibilityResult,
    ColorScore,
    StyleScore,
    _rank_to_points,
)


# ============================================================================
# Test fixtures — minimal ranking tables for 1 swimmer type
# ============================================================================

@pytest.fixture
def rankings():
    """
    Rankings for swimmer type 1 (The Nervous/New):
    Colors: Blue(1)=1st, Orange(2)=2nd, Green(3)=3rd, Gold(4)=4th
    Styles: NR(1)=1st, HE(2)=2nd, SS(5)=3rd, A(4)=4th, TD(3)=5th, DIA(6)=6th
    """
    color_rankings = {
        (1, 1): 1, (1, 2): 2, (1, 3): 3, (1, 4): 4,
    }
    style_rankings = {
        (1, 1): 1, (1, 2): 2, (1, 5): 3, (1, 4): 4, (1, 3): 5, (1, 6): 6,
    }
    return color_rankings, style_rankings


@pytest.fixture
def two_type_rankings():
    """Rankings for 2 swimmer types to test pair scoring."""
    color_rankings = {
        # Type 1: Blue(1)=1st, Orange(2)=2nd, Green(3)=3rd, Gold(4)=4th
        (1, 1): 1, (1, 2): 2, (1, 3): 3, (1, 4): 4,
        # Type 2: Green(3)=1st, Gold(4)=2nd, Blue(1)=3rd, Orange(2)=4th
        (2, 3): 1, (2, 4): 2, (2, 1): 3, (2, 2): 4,
    }
    style_rankings = {
        # Type 1: NR(1)=1st, HE(2)=2nd, SS(5)=3rd, A(4)=4th, TD(3)=5th, DIA(6)=6th
        (1, 1): 1, (1, 2): 2, (1, 5): 3, (1, 4): 4, (1, 3): 5, (1, 6): 6,
        # Type 2: HE(2)=1st, TD(3)=2nd, SS(5)=3rd, A(4)=4th, NR(1)=5th, DIA(6)=6th
        (2, 2): 1, (2, 3): 2, (2, 5): 3, (2, 4): 4, (2, 1): 5, (2, 6): 6,
    }
    return color_rankings, style_rankings


@pytest.fixture
def scorer(rankings):
    color_rankings, style_rankings = rankings
    return CompatibilityScorer(color_rankings, style_rankings)


@pytest.fixture
def two_type_scorer(two_type_rankings):
    color_rankings, style_rankings = two_type_rankings
    return CompatibilityScorer(color_rankings, style_rankings)


# ============================================================================
# rank_to_points
# ============================================================================

class TestRankToPoints:

    def test_first_choice_color(self):
        assert _rank_to_points(1, 4) == 4.0

    def test_last_choice_color(self):
        assert _rank_to_points(4, 4) == 1.0

    def test_first_choice_style(self):
        assert _rank_to_points(1, 6) == 6.0

    def test_last_choice_style(self):
        assert _rank_to_points(6, 6) == 1.0

    def test_middle_rank(self):
        assert _rank_to_points(3, 6) == 4.0


# ============================================================================
# Color scoring
# ============================================================================

class TestColorScore:

    def test_perfect_color_match(self, scorer):
        """Best valid combo: rank 1 primary, rank 2 secondary (primary ≠ secondary)."""
        result = scorer.score_color(1, 1, 2)  # Blue primary, Orange secondary
        # Points: 4×2 + 3×1 = 11, normalized: (11-4)/(11-4)*100 = 100
        assert result.normalized == 100.0
        assert result.primary_rank == 1
        assert result.secondary_rank == 2

    def test_worst_color_match(self, scorer):
        """Worst valid combo: rank 4 primary, rank 3 secondary (primary ≠ secondary)."""
        result = scorer.score_color(1, 4, 3)  # Gold primary, Green secondary
        # Points: 1×2 + 2×1 = 4, normalized: (4-4)/(11-4)*100 = 0
        assert result.normalized == 0.0

    def test_mixed_color_match(self, scorer):
        """Primary rank 1, secondary rank 4."""
        result = scorer.score_color(1, 1, 4)  # Blue primary, Gold secondary
        # Points: 4×2 + 1×1 = 9, normalized: (9-4)/(11-4)*100 = 71.43
        assert result.primary_points == 4.0
        assert result.secondary_points == 1.0
        assert result.primary_weighted == 8.0
        assert result.secondary_weighted == 1.0
        assert result.raw_total == 9.0
        assert result.normalized == pytest.approx(71.43, abs=0.01)

    def test_2_to_1_weighting(self, scorer):
        """Verify primary has 2x weight vs secondary."""
        # Primary=rank2 (3pts), Secondary=rank1 (4pts)
        result = scorer.score_color(1, 2, 1)
        # 3×2 + 4×1 = 10
        assert result.primary_weighted == 6.0
        assert result.secondary_weighted == 4.0
        assert result.raw_total == 10.0


# ============================================================================
# Style scoring
# ============================================================================

class TestStyleScore:

    def test_perfect_style_match(self, scorer):
        """Best valid combo: rank 1 primary, rank 2 secondary (primary ≠ secondary)."""
        result = scorer.score_style(1, 1, 2, 'NR')  # NR primary, HE secondary
        # Points: 6×2 + 5×1 = 17, normalized: (17-4)/(17-4)*100 = 100
        assert result.normalized == 100.0
        assert result.is_dia is False

    def test_worst_style_match(self, scorer):
        """DIA with worst secondary (rank 6)."""
        result = scorer.score_style(1, 6, 6, 'DIA')
        # DIA: primary=3.0 (bonus), secondary=1pt×2.0=2.0, total=5.0
        # DIA normalized: (5-5)/(15-5)*100 = 0.0
        assert result.is_dia is True
        assert result.normalized == 0.0

    def test_standard_style(self, scorer):
        """Non-DIA instructor with known ranks."""
        # TD primary (rank 5), SS secondary (rank 3)
        result = scorer.score_style(1, 3, 5, 'TD')
        # Points: 2×2 + 4×1 = 8, normalized: (8-4)/(17-4)*100 = 30.77
        assert result.primary_rank == 5
        assert result.secondary_rank == 3
        assert result.primary_points == 2.0
        assert result.secondary_points == 4.0
        assert result.raw_total == 8.0
        assert result.normalized == pytest.approx(30.77, abs=0.01)
        assert result.is_dia is False

    def test_dia_universal_bonus(self, scorer):
        """DIA instructor gets 3.0 bonus for primary, 2x secondary weight."""
        # DIA primary (style 6), SS secondary (style 5, rank 3 → 4pts)
        result = scorer.score_style(1, 6, 5, 'DIA')
        # DIA: primary=3.0, secondary=4×2.0=8.0, total=11.0
        # DIA normalized: (11-5)/(15-5)*100 = 60.0
        assert result.primary_rank is None
        assert result.primary_points == 3.0
        assert result.primary_weighted == 3.0
        assert result.secondary_weighted == 8.0
        assert result.raw_total == 11.0
        assert result.normalized == pytest.approx(60.0, abs=0.01)
        assert result.is_dia is True


# ============================================================================
# Combined scoring
# ============================================================================

class TestCombinedScore:

    def test_spec_worked_example(self, scorer):
        """
        From the specification worked example:
        Swimmer: Type 1 (Nervous/New)
        Instructor: Blue(1) primary, Gold(4) secondary, TD(3) primary, SS(5) secondary
        Expected: 51.1%
        """
        result = scorer.score(
            swimmer_type_id=1,
            primary_color_id=1,    # Blue → rank 1
            secondary_color_id=4,  # Gold → rank 4
            primary_style_id=3,    # TD → rank 5
            secondary_style_id=5,  # SS → rank 3
            primary_style_code='TD',
        )
        # Color: 4×2 + 1×1 = 9, norm: (9-4)/(11-4)*100 = 71.43
        assert result.color_score.normalized == pytest.approx(71.43, abs=0.01)
        # Style: 2×2 + 4×1 = 8, norm: (8-4)/(17-4)*100 = 30.77
        assert result.style_score.normalized == pytest.approx(30.77, abs=0.01)
        # Combined: (71.43 + 30.77) / 2 = 51.1
        assert result.combined_score == pytest.approx(51.1, abs=0.1)

    def test_score_value_matches_score(self, scorer):
        """score_value() returns the same as score().combined_score."""
        val = scorer.score_value(1, 1, 4, 3, 5, 'TD')
        result = scorer.score(1, 1, 4, 3, 5, 'TD')
        assert val == result.combined_score

    def test_perfect_overall_score(self, scorer):
        """Best valid combo: rank 1 primary + rank 2 secondary for both color and style."""
        result = scorer.score(1, 1, 2, 1, 2, 'NR')
        assert result.combined_score == 100.0

    def test_score_range(self, scorer):
        """All valid scores (primary ≠ secondary) should be in [0, 100]."""
        for pc in [1, 2, 3, 4]:
            for sc in [1, 2, 3, 4]:
                if pc == sc:
                    continue  # primary ≠ secondary
                for ps in [1, 2, 3, 4, 5, 6]:
                    for ss in [1, 2, 3, 4, 5, 6]:
                        if ps == ss:
                            continue  # primary ≠ secondary
                        code = 'DIA' if ps == 6 else 'TD'
                        val = scorer.score_value(1, pc, sc, ps, ss, code)
                        assert 0 <= val <= 100, f"Score {val} out of range for ({pc},{sc},{ps},{ss})"


# ============================================================================
# Pair scoring (harmonic mean)
# ============================================================================

class TestPairScoring:

    def test_equal_scores_harmonic_mean(self, two_type_scorer):
        """When both scores are equal, harmonic mean = that score."""
        # Use same type for both swimmers to get equal scores
        pair, s1, s2 = two_type_scorer.score_pair(1, 1, 1, 1, 1, 1, 'NR')
        assert s1 == s2
        assert pair == s1

    def test_harmonic_mean_less_than_arithmetic(self, two_type_scorer):
        """Harmonic mean should be ≤ arithmetic mean for unequal scores."""
        pair, s1, s2 = two_type_scorer.score_pair(1, 2, 1, 4, 3, 5, 'TD')
        arithmetic = (s1 + s2) / 2
        assert pair <= arithmetic

    def test_harmonic_mean_penalizes_imbalance(self, two_type_scorer):
        """Larger gap between scores → larger harmonic mean penalty."""
        # Well-matched pair (similar types for this instructor)
        pair1, s1a, s1b = two_type_scorer.score_pair(1, 1, 1, 1, 1, 1, 'NR')
        gap1 = abs(s1a - s1b)

        # Mismatched pair (Blue instructor — great for type 1, bad for type 2)
        pair2, s2a, s2b = two_type_scorer.score_pair(1, 2, 1, 4, 3, 5, 'TD')
        gap2 = abs(s2a - s2b)

        # If gap2 > gap1, the harmonic penalty should be larger
        if gap2 > gap1:
            arith2 = (s2a + s2b) / 2
            penalty2 = arith2 - pair2
            assert penalty2 > 0

    def test_zero_score_returns_zero(self, two_type_scorer):
        """If either swimmer scores 0, pair score is 0."""
        # Worst possible: rank 4 colors, rank 6 styles
        pair, s1, s2 = two_type_scorer.score_pair(1, 2, 4, 4, 6, 6, 'DIA')
        if s1 == 0 or s2 == 0:
            assert pair == 0.0


# ============================================================================
# Convenience methods (domain objects)
# ============================================================================

class TestConvenienceMethods:

    def test_score_match(self, scorer):
        """score_match() produces same result as score() with IDs."""

        class MockSwimmer:
            swimmer_type_id = 1

        class MockInstructor:
            primary_color_id = 1
            secondary_color_id = 4
            primary_style_id = 3
            secondary_style_id = 5

        def style_lookup(style_id):
            return {3: 'TD', 5: 'SS', 6: 'DIA'}.get(style_id)

        result_obj = scorer.score_match(MockSwimmer(), MockInstructor(), style_lookup)
        result_ids = scorer.score(1, 1, 4, 3, 5, 'TD')
        assert result_obj.combined_score == result_ids.combined_score

    def test_score_match_value(self, scorer):
        """score_match_value() returns float matching score_value()."""

        class MockSwimmer:
            swimmer_type_id = 1

        class MockInstructor:
            primary_color_id = 1
            secondary_color_id = 4
            primary_style_id = 3
            secondary_style_id = 5

        def style_lookup(style_id):
            return {3: 'TD', 5: 'SS'}.get(style_id)

        val = scorer.score_match_value(MockSwimmer(), MockInstructor(), style_lookup)
        expected = scorer.score_value(1, 1, 4, 3, 5, 'TD')
        assert val == expected

    def test_score_pair_match(self, two_type_scorer):
        """score_pair_match() matches score_pair() with IDs."""

        class Swimmer1:
            swimmer_type_id = 1

        class Swimmer2:
            swimmer_type_id = 2

        class MockInstructor:
            primary_color_id = 1
            secondary_color_id = 4
            primary_style_id = 3
            secondary_style_id = 5

        def style_lookup(style_id):
            return {3: 'TD', 5: 'SS'}.get(style_id)

        pair_obj, s1_obj, s2_obj = two_type_scorer.score_pair_match(
            Swimmer1(), Swimmer2(), MockInstructor(), style_lookup
        )
        pair_ids, s1_ids, s2_ids = two_type_scorer.score_pair(1, 2, 1, 4, 3, 5, 'TD')
        assert pair_obj == pair_ids
        assert s1_obj == s1_ids
        assert s2_obj == s2_ids
