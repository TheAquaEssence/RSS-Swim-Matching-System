"""
Configuration for CP-SAT v2 Matching System.

Scoring weights live in swim_matching.scoring.config — this file
contains only CP-SAT solver params, confidence scoring, and thresholds.
"""

# =============================================================================
# CONFIDENCE SCORE PARAMETERS (README 5-signal formula)
# =============================================================================

CONFIDENCE = {
    # Signal 1: Continuity base
    'continuity_base': 90,

    # Signal 1: Compatibility tiered bases
    'compat_base_high': 80,      # score >= 75%
    'compat_base_mid_high': 65,  # score 50-74%
    'compat_base_mid_low': 45,   # score 25-49%
    'compat_base_low': 25,       # score < 25%

    # Signal 2: Margin bonus
    'margin_bonus_divisor': 5,   # margin / 5
    'margin_bonus_max': 10,      # capped at 10

    # Signal 4: Dispute penalty
    'dispute_penalty': 10,       # subtracted when continuity_dispute = True

    # Signal 5: Forced penalty
    'forced_penalty': 5,         # subtracted when only 1 valid instructor
}


# =============================================================================
# CP-SAT SOLVER CONFIGURATION
# =============================================================================

CPSAT = {
    'max_time_seconds': 20.0,        # Maximum solve time (spec says <100ms typical)
    'num_workers': 0,                # 0 = use all available cores
    'log_search_progress': False,    # Set True for debugging
    'score_scale_factor': 100,       # Multiply float scores by this for integer conversion
    'min_auto_assign_score': 50.0,     # Below this, leave unassigned for manual review
}


# =============================================================================
# CONFIDENCE THRESHOLDS FOR REVIEW
# =============================================================================

REVIEW_THRESHOLDS = {
    'excellent': 90,    # 90-100%: Accept confidently
    'strong': 80,       # 80-89%: Accept with minimal review
    'good': 70,         # 70-79%: Quick review recommended
    'moderate': 60,     # 60-69%: Detailed review recommended
    'weak': 50,         # 50-59%: Consider alternatives
    # Below 50%: Flag for manual override
}


# =============================================================================
# AGE THRESHOLDS
# =============================================================================

AGE_THRESHOLDS = {
    'baby_max': 2.5,    # Ages below this require baby-capable instructor
    'adult_min': 18,    # Ages at or above this require adult-capable instructor
}


# =============================================================================
# PAIRING CONSTRAINTS (HC-4)
# =============================================================================

PAIRING_CONSTRAINTS = {
    'max_level_diff': 1,    # Max RSS level difference for pairs
    'max_age_diff': 2,      # Max age difference (years) for pairs
}


# =============================================================================
# INPUT DATA VALIDATION
# =============================================================================

DATA_VALIDATION = {
    'min_age': 0.0,
    'max_age': 100.0,
    'min_skill_level': 1,
    'max_skill_level': 12,
}


# =============================================================================
# NOTES KEYWORD BOOSTS (P3 — applied in Phase 2 CP-SAT scoring)
# =============================================================================

NOTES_BOOSTS = {
    'prefer_bonus': 15,   # Moderate boost for "prefer [name]"
    'always_bonus': 40,   # Strong boost for "always [name]" (approaches continuity)
}
