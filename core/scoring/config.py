"""
Scoring configuration for the ranking-based compatibility system.

All tunable scoring parameters live here. Never hardcode weights elsewhere.
"""

# Primary:secondary weighting ratio (2:1)
SCORING_WEIGHTS = {
    'color_primary': 2.0,
    'color_secondary': 1.0,
    'style_primary': 2.0,
    'style_secondary': 1.0,
    'dia_universal_bonus': 3.0,      # Replaces rank-based primary style for DIA
    'dia_secondary_weight': 2.0,     # Enhanced secondary style weight for DIA
    'color_vs_style': 0.5,           # 50/50 balance (color weight = style weight)
}

# Normalization bounds derived from the ranking system
# Primary and secondary traits must differ, so bounds reflect the constraint.
# Color: 4 options, ranks 1-4, points = num_colors - (rank - 1)
# Style: 6 options, ranks 1-6, points = num_styles - (rank - 1)
NORMALIZATION = {
    'num_colors': 4,
    'num_styles': 6,
    # Color bounds (primary ≠ secondary):
    #   best  = rank 1 primary (4pt×2) + rank 2 secondary (3pt×1) = 11
    #   worst = rank 4 primary (1pt×2) + rank 3 secondary (2pt×1) = 4
    'color_min': 4.0,
    'color_max': 11.0,
    # Style bounds — standard instructors (primary ≠ secondary):
    #   best  = rank 1 primary (6pt×2) + rank 2 secondary (5pt×1) = 17
    #   worst = rank 6 primary (1pt×2) + rank 5 secondary (2pt×1) = 4
    'style_min': 4.0,
    'style_max': 17.0,
    # Style bounds — DIA instructors (universal bonus + enhanced secondary):
    #   best  = 3.0 + rank 1 secondary (6pt×2) = 15
    #   worst = 3.0 + rank 6 secondary (1pt×2) = 5
    'dia_style_min': 5.0,
    'dia_style_max': 15.0,
}
