"""
Shared compatibility scoring module for swimmer-instructor matching.

Reusable across all solution implementations (CP-SAT, greedy, etc.).
"""

from .compatibility_scorer import (
    CompatibilityScorer,
    CompatibilityResult,
    ColorScore,
    StyleScore,
)
from .ranking_loader import RankingLoader
from .config import SCORING_WEIGHTS, NORMALIZATION

__all__ = [
    'CompatibilityScorer',
    'CompatibilityResult',
    'ColorScore',
    'StyleScore',
    'RankingLoader',
    'SCORING_WEIGHTS',
    'NORMALIZATION',
]
