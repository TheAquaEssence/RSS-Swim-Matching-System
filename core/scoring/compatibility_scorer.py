"""
Ranking-based compatibility scorer for swimmer-instructor matching.

Implements the scoring formula from the CP-SAT specification v2.0:
1. Look up swimmer type's ranking for instructor traits
2. Convert ranks to points (linear decay)
3. Apply 2:1 primary:secondary weighting
4. Handle DIA universal bonus
5. Normalize color and style to 0-100
6. Combine 50/50 color:style
7. Pair compatibility via harmonic mean
"""

from dataclasses import dataclass
from typing import Callable, Dict, Optional, Tuple

from .config import SCORING_WEIGHTS, NORMALIZATION


@dataclass
class ColorScore:
    """Detailed color compatibility score breakdown."""
    primary_rank: int
    secondary_rank: int
    primary_points: float
    secondary_points: float
    primary_weighted: float
    secondary_weighted: float
    raw_total: float
    normalized: float  # 0-100


@dataclass
class StyleScore:
    """Detailed style compatibility score breakdown."""
    primary_rank: Optional[int]  # None for DIA (uses universal bonus)
    secondary_rank: int
    primary_points: float        # Universal bonus (3.0) for DIA
    secondary_points: float
    primary_weighted: float
    secondary_weighted: float
    raw_total: float
    normalized: float  # 0-100
    is_dia: bool


@dataclass
class CompatibilityResult:
    """Complete compatibility scoring result with full breakdown."""
    color_score: ColorScore
    style_score: StyleScore
    combined_score: float  # Final 0-100 (50/50 color:style)


def _rank_to_points(rank: int, total_options: int) -> float:
    """Convert a preference rank to points. Rank 1 = max points."""
    return float(total_options - (rank - 1))


class CompatibilityScorer:
    """
    Ranking-based compatibility scorer for swimmer-instructor matching.

    Accepts ranking lookup dictionaries at init time. All scoring methods
    are stateless with respect to calls — safe to reuse across phases.
    """

    def __init__(
        self,
        color_rankings: Dict[Tuple[int, int], int],
        style_rankings: Dict[Tuple[int, int], int],
        weights: Optional[Dict] = None,
    ):
        """
        Initialize scorer with ranking tables.

        Args:
            color_rankings: Dict[(swimmer_type_id, color_id)] -> rank (1-4)
            style_rankings: Dict[(swimmer_type_id, style_id)] -> rank (1-6)
            weights: Optional custom weights (defaults to SCORING_WEIGHTS)
        """
        self._color_rankings = color_rankings
        self._style_rankings = style_rankings
        self._weights = weights or SCORING_WEIGHTS
        self._norm = NORMALIZATION

    # =========================================================================
    # Core methods (primitive IDs — maximum reusability)
    # =========================================================================

    def score(
        self,
        swimmer_type_id: int,
        primary_color_id: int,
        secondary_color_id: int,
        primary_style_id: int,
        secondary_style_id: int,
        primary_style_code: str,
    ) -> CompatibilityResult:
        """
        Calculate full compatibility with detailed breakdown.

        Args:
            swimmer_type_id: The swimmer's personality type ID
            primary_color_id: Instructor's primary personality color ID
            secondary_color_id: Instructor's secondary personality color ID
            primary_style_id: Instructor's primary teaching style ID
            secondary_style_id: Instructor's secondary teaching style ID
            primary_style_code: Instructor's primary style code (e.g., 'DIA')

        Returns:
            CompatibilityResult with color_score, style_score, and combined_score
        """
        color = self.score_color(swimmer_type_id, primary_color_id, secondary_color_id)
        style = self.score_style(swimmer_type_id, primary_style_id, secondary_style_id, primary_style_code)

        color_weight = self._weights['color_vs_style']
        style_weight = 1.0 - color_weight
        combined = (color.normalized * color_weight + style.normalized * style_weight)

        return CompatibilityResult(
            color_score=color,
            style_score=style,
            combined_score=round(combined, 2),
        )

    def score_value(
        self,
        swimmer_type_id: int,
        primary_color_id: int,
        secondary_color_id: int,
        primary_style_id: int,
        secondary_style_id: int,
        primary_style_code: str,
    ) -> float:
        """Convenience: return just the combined float score (0-100)."""
        result = self.score(
            swimmer_type_id, primary_color_id, secondary_color_id,
            primary_style_id, secondary_style_id, primary_style_code,
        )
        return result.combined_score

    def score_color(
        self,
        swimmer_type_id: int,
        primary_color_id: int,
        secondary_color_id: int,
    ) -> ColorScore:
        """Calculate color compatibility score with full breakdown."""
        num_colors = self._norm['num_colors']

        pri_rank = self._color_rankings[(swimmer_type_id, primary_color_id)]
        sec_rank = self._color_rankings[(swimmer_type_id, secondary_color_id)]

        pri_points = _rank_to_points(pri_rank, num_colors)
        sec_points = _rank_to_points(sec_rank, num_colors)

        pri_weighted = pri_points * self._weights['color_primary']
        sec_weighted = sec_points * self._weights['color_secondary']

        raw_total = pri_weighted + sec_weighted

        color_min = self._norm['color_min']
        color_max = self._norm['color_max']
        normalized = ((raw_total - color_min) / (color_max - color_min)) * 100

        return ColorScore(
            primary_rank=pri_rank,
            secondary_rank=sec_rank,
            primary_points=pri_points,
            secondary_points=sec_points,
            primary_weighted=pri_weighted,
            secondary_weighted=sec_weighted,
            raw_total=raw_total,
            normalized=round(normalized, 2),
        )

    def score_style(
        self,
        swimmer_type_id: int,
        primary_style_id: int,
        secondary_style_id: int,
        primary_style_code: str,
    ) -> StyleScore:
        """Calculate style compatibility score with full breakdown."""
        num_styles = self._norm['num_styles']
        is_dia = (primary_style_code == 'DIA')

        sec_rank = self._style_rankings[(swimmer_type_id, secondary_style_id)]
        sec_points = _rank_to_points(sec_rank, num_styles)

        if is_dia:
            # DIA: universal bonus replaces rank-based primary
            pri_rank = None
            pri_points = self._weights['dia_universal_bonus']
            pri_weighted = pri_points  # bonus is already the weighted value
            sec_weighted = sec_points * self._weights['dia_secondary_weight']
        else:
            pri_rank = self._style_rankings[(swimmer_type_id, primary_style_id)]
            pri_points = _rank_to_points(pri_rank, num_styles)
            pri_weighted = pri_points * self._weights['style_primary']
            sec_weighted = sec_points * self._weights['style_secondary']

        raw_total = pri_weighted + sec_weighted

        if is_dia:
            style_min = self._norm['dia_style_min']
            style_max = self._norm['dia_style_max']
        else:
            style_min = self._norm['style_min']
            style_max = self._norm['style_max']
        normalized = ((raw_total - style_min) / (style_max - style_min)) * 100

        return StyleScore(
            primary_rank=pri_rank,
            secondary_rank=sec_rank,
            primary_points=pri_points,
            secondary_points=sec_points,
            primary_weighted=pri_weighted,
            secondary_weighted=sec_weighted,
            raw_total=raw_total,
            normalized=round(normalized, 2),
            is_dia=is_dia,
        )

    def score_pair(
        self,
        swimmer_type_id_1: int,
        swimmer_type_id_2: int,
        primary_color_id: int,
        secondary_color_id: int,
        primary_style_id: int,
        secondary_style_id: int,
        primary_style_code: str,
    ) -> Tuple[float, float, float]:
        """
        Calculate pair compatibility using harmonic mean.

        Returns:
            (pair_score, score1, score2) — all floats 0-100
        """
        score1 = self.score_value(
            swimmer_type_id_1, primary_color_id, secondary_color_id,
            primary_style_id, secondary_style_id, primary_style_code,
        )
        score2 = self.score_value(
            swimmer_type_id_2, primary_color_id, secondary_color_id,
            primary_style_id, secondary_style_id, primary_style_code,
        )

        if score1 == 0 or score2 == 0:
            pair_score = 0.0
        else:
            pair_score = round((2 * score1 * score2) / (score1 + score2), 2)

        return pair_score, score1, score2

    # =========================================================================
    # Convenience methods (domain objects — cleaner call sites)
    # =========================================================================

    def score_match(
        self,
        swimmer,
        instructor,
        style_lookup_fn: Callable[[int], Optional[str]],
    ) -> CompatibilityResult:
        """
        Score a swimmer-instructor pair using domain objects.

        Args:
            swimmer: Object with .swimmer_type_id attribute
            instructor: Object with .primary_color_id, .secondary_color_id,
                        .primary_style_id, .secondary_style_id attributes
            style_lookup_fn: Function that maps style_id -> style_code (e.g., 'DIA')
        """
        return self.score(
            swimmer.swimmer_type_id,
            instructor.primary_color_id,
            instructor.secondary_color_id,
            instructor.primary_style_id,
            instructor.secondary_style_id,
            style_lookup_fn(instructor.primary_style_id),
        )

    def score_match_value(
        self,
        swimmer,
        instructor,
        style_lookup_fn: Callable[[int], Optional[str]],
    ) -> float:
        """Convenience: return just the combined float score for domain objects."""
        return self.score_match(swimmer, instructor, style_lookup_fn).combined_score

    def score_pair_match(
        self,
        swimmer1,
        swimmer2,
        instructor,
        style_lookup_fn: Callable[[int], Optional[str]],
    ) -> Tuple[float, float, float]:
        """
        Calculate pair compatibility using domain objects.

        Returns:
            (pair_score, score1, score2) — all floats 0-100
        """
        return self.score_pair(
            swimmer1.swimmer_type_id,
            swimmer2.swimmer_type_id,
            instructor.primary_color_id,
            instructor.secondary_color_id,
            instructor.primary_style_id,
            instructor.secondary_style_id,
            style_lookup_fn(instructor.primary_style_id),
        )
