"""
Phase 3: Explainability Layer

Generates human-readable explanations and confidence scores for all matches.
Uses the shared CompatibilityScorer for rank-aware breakdowns.
"""

import os
from typing import Dict, List, Optional
import pandas as pd

from core.scoring import CompatibilityScorer, CompatibilityResult
from core.flags import (
    FLAG_CODES as _FLAG_CODES,
    get_highest_severity as _get_highest_severity,
    get_primary_review_action as _get_primary_review_action,
)
from core.swimmer_types import is_non_response_swimmer_type

from .config import CONFIDENCE, REVIEW_THRESHOLDS
from .data_loader import Swimmer, Instructor, DataLoader


def generate_explanations(
    all_matches: List[Dict],
    instructors: List[Instructor],
    swimmers: List[Swimmer],
    scorer: CompatibilityScorer,
    data_loader: DataLoader,
    disputed_ids: set = None,
    swimmer_flags: Dict[int, List[str]] = None,
) -> List[Dict]:
    """
    Phase 3: Add explanation text and confidence scores to all matches.

    Returns:
        List of matches with added 'confidence' and 'explanation' fields
    """
    if disputed_ids is None:
        disputed_ids = set()
    if swimmer_flags is None:
        swimmer_flags = {}

    annotated_matches = []
    instructors_dict = {i.instructor_id: i for i in instructors}
    style_lookup = data_loader.get_style_code
    swimmer_types = {
        swimmer_type_id: swimmer_type.swimmer_type_name
        for swimmer_type_id, swimmer_type in data_loader.swimmer_types.items()
    }

    for match in all_matches:
        instructor = instructors_dict[match['instructor_id']]

        confidence = _calculate_confidence(
            match,
            disputed_ids=disputed_ids,
            all_instructors=instructors,
        )

        explanation = _generate_match_explanation(
            match, instructor, instructors, scorer, style_lookup, data_loader
        )

        reason_summary = _generate_reason_summary(match, instructor)

        # Merge per-swimmer blocked-continuity flags from Phase 1 into match flag_codes
        swimmer_id = match.get('swimmer_id') or match.get('swimmer_1_id')
        extra_flags = swimmer_flags.get(swimmer_id, [])
        if extra_flags:
            existing = list(match.get('flag_codes', []))
            merged = existing + [f for f in extra_flags if f not in existing]
        else:
            merged = list(match.get('flag_codes', []))

        # Signal 5: Forced assignment — add flag when only 1 eligible instructor
        if match['match_type'] == 'compatibility' and instructors:
            swimmer = match.get('swimmer') or match.get('swimmer_1')
            if swimmer and _count_eligible_instructors(swimmer, instructors) <= 1:
                if 'forced_assignment' not in merged:
                    merged.append('forced_assignment')

        # Adapted single legal instructor — pool-coverage signal, fires on all match types
        if instructors:
            swimmer = match.get('swimmer') or match.get('swimmer_1')
            if swimmer and swimmer.has_special_needs:
                adapted_count = sum(1 for instr in instructors if instr.can_teach_adapted)
                if adapted_count == 1 and 'adapted_swimmer_single_legal_instructor' not in merged:
                    merged.append('adapted_swimmer_single_legal_instructor')

        swimmers_in_match = [
            swimmer for swimmer in (match.get('swimmer'), match.get('swimmer_1'), match.get('swimmer_2'))
            if swimmer is not None
        ]
        if any(
            is_non_response_swimmer_type(swimmer.swimmer_type_id, swimmer_types)
            for swimmer in swimmers_in_match
        ):
            if 'non_response_swimmer_type' not in merged:
                merged.append('non_response_swimmer_type')

        class_resolution_flags = data_loader.class_resolution_flags.get(match.get('class_id'), [])
        for flag_code in class_resolution_flags:
            if flag_code not in merged:
                merged.append(flag_code)

        annotated_matches.append({
            **match,
            'flag_codes': merged,
            'confidence': confidence,
            'explanation': explanation,
            'reason_summary': reason_summary,
            'instructor': instructor,
            'instructor_name': instructor.name
        })

    return annotated_matches


# =============================================================================
# CONFIDENCE SCORING (README 5-signal formula)
# =============================================================================

def _calculate_confidence(
    match: Dict,
    disputed_ids: set,
    all_instructors: List[Instructor],
) -> float:
    """
    README 5-signal confidence formula.

    Signal 1: Base by assignment method
    Signal 2: Margin bonus (top - second_best)
    Signal 3: Pair weakness penalty
    Signal 4: Dispute penalty
    Signal 5: Forced assignment penalty
    """
    # --- Signal 1: Base score ---
    if match['match_type'] == 'pre-assigned':
        return 65.0
    if match['match_type'] == 'continuity':
        base = CONFIDENCE['continuity_base']
        margin_bonus = 0.0
        pair_penalty = 0.0
    else:
        score = match.get('compatibility_score', 0.0)
        if score >= 75:
            base = CONFIDENCE['compat_base_high']
        elif score >= 50:
            base = CONFIDENCE['compat_base_mid_high']
        elif score >= 25:
            base = CONFIDENCE['compat_base_mid_low']
        else:
            base = CONFIDENCE['compat_base_low']

        # --- Signal 2: Margin bonus ---
        top = match.get('top_score', score)
        second = match.get('second_best_score', score)
        margin = top - second
        margin_bonus = min(
            CONFIDENCE['margin_bonus_max'],
            margin / CONFIDENCE['margin_bonus_divisor']
        )

        # --- Signal 3: Pair penalty ---
        if match['type'] == 'pair':
            s1 = match.get('swimmer_1_score', score)
            s2 = match.get('swimmer_2_score', score)
            harmonic = (2 * s1 * s2) / (s1 + s2) if (s1 + s2) > 0 else 0
            min_individual = min(s1, s2)
            pair_penalty = max(0.0, (harmonic - min_individual) / 2)
        else:
            pair_penalty = 0.0

    # --- Signal 4: Dispute penalty ---
    swimmer_id = match.get('swimmer_id') or match.get('swimmer_1_id')
    is_disputed = swimmer_id in disputed_ids if swimmer_id else False
    dispute_penalty = CONFIDENCE['dispute_penalty'] if is_disputed else 0

    # --- Signal 5: Forced penalty ---
    forced_penalty = 0
    if match['match_type'] == 'compatibility' and all_instructors:
        swimmer = match.get('swimmer') or match.get('swimmer_1')
        if swimmer:
            eligible_count = _count_eligible_instructors(swimmer, all_instructors)
            if eligible_count <= 1:
                forced_penalty = CONFIDENCE['forced_penalty']

    confidence = base + margin_bonus - pair_penalty - dispute_penalty - forced_penalty
    return max(0.0, min(100.0, confidence))


def _count_eligible_instructors(swimmer: Swimmer, instructors: List[Instructor]) -> int:
    """Count instructors eligible for this swimmer under HC-2 and HC-3."""
    from .config import AGE_THRESHOLDS
    count = 0
    for instr in instructors:
        if swimmer.has_special_needs and not instr.can_teach_adapted:
            continue
        if swimmer.age < AGE_THRESHOLDS['baby_max'] and not instr.can_teach_babies:
            continue
        if swimmer.age >= AGE_THRESHOLDS['adult_min'] and not instr.can_teach_adults:
            continue
        count += 1
    return count


def _flag_non_response_swimmers(match: Dict, merged: list) -> None:
    """Append non_response_swimmer_type flag if any swimmer in the match has type_id == 0."""
    swimmers_to_check = []
    if match.get('swimmer'):
        swimmers_to_check.append(match['swimmer'])
    if match.get('swimmer_1'):
        swimmers_to_check.append(match['swimmer_1'])
    if match.get('swimmer_2'):
        swimmers_to_check.append(match['swimmer_2'])
    if any(s.swimmer_type_id == 0 for s in swimmers_to_check):
        if 'non_response_swimmer_type' not in merged:
            merged.append('non_response_swimmer_type')


def _has_weak_signals(result: CompatibilityResult) -> bool:
    """Check if a match result has weak primary trait signals (rank >= 4)."""
    # Primary color rank 4 = worst color match
    if result.color_score.primary_rank >= 4:
        return True
    # Primary style rank 5+ = quite poor style fit (for non-DIA)
    if not result.style_score.is_dia and result.style_score.primary_rank is not None:
        if result.style_score.primary_rank >= 5:
            return True
    return False


def _check_first_choice(
    swimmer: Swimmer,
    instructor_id: int,
    instructors: List[Instructor],
    scorer: CompatibilityScorer,
    style_lookup
) -> bool:
    """Check if the assigned instructor was the swimmer's top match."""
    best_score = -1
    best_id = None
    for instr in instructors:
        s = scorer.score_match_value(swimmer, instr, style_lookup)
        if s > best_score:
            best_score = s
            best_id = instr.instructor_id
    return best_id == instructor_id


# =============================================================================
# EXPLANATION GENERATION
# =============================================================================

def _generate_match_explanation(
    match: Dict,
    instructor: Instructor,
    instructors: List[Instructor],
    scorer: CompatibilityScorer,
    style_lookup,
    data_loader: DataLoader
) -> str:
    """Generate detailed explanation text for a match."""
    if match['match_type'] == 'continuity':
        return _generate_continuity_explanation(match, instructor)
    if match['match_type'] == 'pre-assigned':
        return _generate_preassigned_explanation(match, instructor)
    else:
        return _generate_compatibility_explanation(
            match, instructor, instructors, scorer, style_lookup, data_loader
        )


def _generate_continuity_explanation(match: Dict, instructor: Instructor) -> str:
    num_sessions = match.get('num_sessions', 1)

    if match['type'] == 'pair':
        swimmer1_name = match['swimmer_1'].name
        swimmer2_name = match['swimmer_2'].name
        return (
            f"Continuity: Both {swimmer1_name} and {swimmer2_name} "
            f"had {instructor.name} in their previous session "
            f"({num_sessions} session(s) together)"
        )
    else:
        swimmer_name = match['swimmer'].name
        return (
            f"Continuity: {swimmer_name} returns to {instructor.name} "
            f"({num_sessions} session(s) together)"
        )


def _generate_preassigned_explanation(match: Dict, instructor: Instructor) -> str:
    if match['type'] == 'pair':
        swimmer1_name = match['swimmer_1'].name
        swimmer2_name = match['swimmer_2'].name
        return (
            f"Pre-assigned: {swimmer1_name} and {swimmer2_name} stay with {instructor.name} "
            f"because that instructor was already filled in on the selected class row."
        )
    swimmer_name = match['swimmer'].name
    return (
        f"Pre-assigned: {swimmer_name} stays with {instructor.name} "
        f"because that instructor was already filled in on the selected class row."
    )


def _generate_compatibility_explanation(
    match: Dict,
    instructor: Instructor,
    instructors: List[Instructor],
    scorer: CompatibilityScorer,
    style_lookup,
    data_loader: DataLoader
) -> str:
    """Generate rank-aware explanation for a compatibility match."""
    score = match.get('compatibility_score', 0)

    if match['type'] == 'pair':
        return _explain_pair(match, instructor, scorer, style_lookup, data_loader, score)
    else:
        return _explain_individual(
            match, instructor, instructors, scorer, style_lookup, data_loader, score
        )


def _explain_individual(
    match: Dict,
    instructor: Instructor,
    instructors: List[Instructor],
    scorer: CompatibilityScorer,
    style_lookup,
    data_loader: DataLoader,
    score: float
) -> str:
    swimmer = match['swimmer']
    result = scorer.score_match(swimmer, instructor, style_lookup)
    swimmer_type_name = data_loader.get_swimmer_type_name(swimmer.swimmer_type_id) or "Unknown"

    explanation = (
        f"{swimmer.name} -> {instructor.name} "
        f"(Compatibility: {score:.1f}%)\n\n"
    )

    # Positive signals
    positive = _get_positive_signals(result, instructor, swimmer_type_name, data_loader)
    if positive:
        explanation += "Why this match:\n"
        for signal in positive:
            explanation += f"  + {signal}\n"

    # Considerations
    negative = _get_negative_signals(result, instructor, swimmer_type_name, data_loader)
    if negative:
        explanation += "\nConsiderations:\n"
        for signal in negative:
            explanation += f"  - {signal}\n"

    # Alternatives
    alternatives = []
    for alt_instr in instructors:
        if alt_instr.instructor_id != instructor.instructor_id:
            alt_score = scorer.score_match_value(swimmer, alt_instr, style_lookup)
            alternatives.append((alt_instr, alt_score))
    alternatives.sort(key=lambda x: x[1], reverse=True)

    if alternatives:
        explanation += "\nOther instructors considered:\n"
        for alt_instr, alt_score in alternatives[:3]:
            explanation += f"  * {alt_instr.name}: {alt_score:.1f}%\n"

    explanation += f"\n-> {instructor.name} was the optimal choice among available instructors."
    return explanation


def _explain_pair(
    match: Dict,
    instructor: Instructor,
    scorer: CompatibilityScorer,
    style_lookup,
    data_loader: DataLoader,
    score: float
) -> str:
    swimmer1 = match['swimmer_1']
    swimmer2 = match['swimmer_2']
    s1_score = match.get('swimmer_1_score', score)
    s2_score = match.get('swimmer_2_score', score)

    result1 = scorer.score_match(swimmer1, instructor, style_lookup)
    result2 = scorer.score_match(swimmer2, instructor, style_lookup)

    type1_name = data_loader.get_swimmer_type_name(swimmer1.swimmer_type_id) or "Unknown"
    type2_name = data_loader.get_swimmer_type_name(swimmer2.swimmer_type_id) or "Unknown"

    explanation = (
        f"{swimmer1.name} & {swimmer2.name} -> {instructor.name} "
        f"(Pair score: {score:.1f}% | Individual: {s1_score:.1f}% / {s2_score:.1f}%)\n\n"
    )

    all_positive = (
        _get_positive_signals(result1, instructor, type1_name, data_loader) +
        _get_positive_signals(result2, instructor, type2_name, data_loader)
    )
    all_negative = (
        _get_negative_signals(result1, instructor, type1_name, data_loader) +
        _get_negative_signals(result2, instructor, type2_name, data_loader)
    )

    if all_positive:
        explanation += "Why this match:\n"
        for signal in list(set(all_positive))[:4]:
            explanation += f"  + {signal}\n"

    if all_negative:
        explanation += "\nConsiderations:\n"
        for signal in list(set(all_negative))[:3]:
            explanation += f"  - {signal}\n"

    explanation += f"\n-> {instructor.name} was the optimal choice among available instructors."
    return explanation


def _get_positive_signals(
    result: CompatibilityResult,
    instructor: Instructor,
    swimmer_type_name: str,
    data_loader: DataLoader
) -> List[str]:
    """Extract positive signals from a scoring result."""
    signals = []
    color_name = data_loader.get_color_name(instructor.primary_color_id) or "Unknown"
    sec_color_name = data_loader.get_color_name(instructor.secondary_color_id) or "Unknown"
    style_name = data_loader.get_style_name(instructor.primary_style_id) or "Unknown"
    sec_style_name = data_loader.get_style_name(instructor.secondary_style_id) or "Unknown"

    if result.color_score.primary_rank <= 2:
        signals.append(
            f"Primary color ({color_name}) is #{result.color_score.primary_rank} choice "
            f"for {swimmer_type_name}"
        )

    if result.color_score.secondary_rank <= 2:
        signals.append(
            f"Secondary color ({sec_color_name}) is #{result.color_score.secondary_rank} choice"
        )

    if result.style_score.is_dia:
        signals.append(
            f"Do-It-All instructor with universal adaptability"
        )
    elif result.style_score.primary_rank is not None and result.style_score.primary_rank <= 2:
        signals.append(
            f"Teaching style ({style_name}) is #{result.style_score.primary_rank} choice "
            f"for {swimmer_type_name}"
        )

    if result.style_score.secondary_rank <= 2:
        signals.append(
            f"Secondary style ({sec_style_name}) is #{result.style_score.secondary_rank} choice"
        )

    return signals


def _get_negative_signals(
    result: CompatibilityResult,
    instructor: Instructor,
    swimmer_type_name: str,
    data_loader: DataLoader
) -> List[str]:
    """Extract negative signals from a scoring result."""
    signals = []
    color_name = data_loader.get_color_name(instructor.primary_color_id) or "Unknown"
    style_name = data_loader.get_style_name(instructor.primary_style_id) or "Unknown"
    num_colors = 4
    num_styles = 6

    if result.color_score.primary_rank >= num_colors:
        signals.append(
            f"Primary color ({color_name}) is #{result.color_score.primary_rank}/{num_colors} "
            f"for {swimmer_type_name}"
        )

    if not result.style_score.is_dia and result.style_score.primary_rank is not None:
        if result.style_score.primary_rank >= num_styles - 1:
            signals.append(
                f"Teaching style ({style_name}) is #{result.style_score.primary_rank}/{num_styles} "
                f"for {swimmer_type_name}"
            )

    return signals


def _generate_reason_summary(match: Dict, instructor: Instructor) -> str:
    """Generate a short one-line reason summary for CSV output."""
    if match['match_type'] == 'continuity':
        num_sessions = match.get('num_sessions', 1)
        return f"Continuity: {num_sessions} session(s) together"
    if match['match_type'] == 'pre-assigned':
        return "Pre-assigned: instructor already filled in class"
    else:
        score = match.get('compatibility_score', 0)
        return f"Optimal compatibility match ({score:.1f}%)"


# =============================================================================
# REPORT GENERATION
# =============================================================================

def generate_summary_report(
    all_assignments: List[Dict],
    continuity_count: int,
    compatibility_count: int,
    preassigned_count: int = 0,
) -> str:
    """Generate executive summary report of matching results."""
    total_swimmers = sum(
        2 if a['type'] == 'pair' else 1
        for a in all_assignments
    )
    total_instructors = len(set(a['instructor_id'] for a in all_assignments))

    avg_confidence = (
        sum(a['confidence'] for a in all_assignments) / len(all_assignments)
        if all_assignments else 0
    )

    compat_matches = [a for a in all_assignments if a['match_type'] == 'compatibility']
    avg_compatibility = (
        sum(a.get('compatibility_score', 0) for a in compat_matches) / len(compat_matches)
        if compat_matches else 0
    )

    semi_private_count = sum(1 for a in all_assignments if a['type'] == 'pair')

    low_confidence = [
        a for a in all_assignments
        if a['confidence'] < REVIEW_THRESHOLDS['good']
    ]

    total_entities = preassigned_count + continuity_count + compatibility_count
    preassigned_pct = (preassigned_count / total_entities * 100) if total_entities else 0
    continuity_pct = (continuity_count / total_entities * 100) if total_entities else 0
    compatibility_pct = (compatibility_count / total_entities * 100) if total_entities else 0

    report = f"""
================================================================================
                    AQUA ESSENCE MATCHING SUMMARY (v2)
================================================================================

Total Swimmers: {total_swimmers}
Total Instructors: {total_instructors}

--------------------------------------------------------------------------------

PHASE 1 - CONTINUITY MATCHING:
  + {preassigned_count} entities ({preassigned_count}/{total_entities} = {preassigned_pct:.0f}%) preserved as pre-assigned classes
  + {continuity_count} entities ({continuity_count}/{total_entities} = {continuity_pct:.0f}%) matched with previous instructor

PHASE 2 - COMPATIBILITY MATCHING (ranking-based):
  + {compatibility_count} entities ({compatibility_count}/{total_entities} = {compatibility_pct:.0f}%) matched via optimization
  + Average compatibility score: {avg_compatibility:.1f}%
  + {semi_private_count} semi-private classes formed
  + All hard constraints satisfied:
      - Instructor and class capacity [OK]
      - Adapted swimmers -> adapted-capable instructors [OK]
      - Babies -> baby-capable instructors [OK]
      - Adults -> adult-capable instructors [OK]
      - Paired swimmers within age and RSS-level limits [OK]

--------------------------------------------------------------------------------

MATCHES REQUIRING REVIEW (confidence < {REVIEW_THRESHOLDS['good']}%):
"""

    if low_confidence:
        for assignment in low_confidence:
            if assignment['type'] == 'pair':
                swimmer_name = f"{assignment['swimmer_1'].name} & {assignment['swimmer_2'].name}"
            else:
                swimmer_name = assignment['swimmer'].name

            report += f"""
  ! {swimmer_name} -> {assignment['instructor_name']} ({assignment['confidence']:.0f}%)
    Reason: {assignment['reason_summary']}
"""
    else:
        report += "  (None - all matches have confidence >= 70%)\n"

    report += f"""
--------------------------------------------------------------------------------

OVERALL CONFIDENCE: {avg_confidence:.0f}% average across all matches

Status: Ready for review

================================================================================
"""

    return report


def generate_output_csv(
    assignments: List[Dict],
    classes: Dict,
    output_path: str,
    disputed_ids: set = None,
) -> pd.DataFrame:
    """Generate completed classes.csv with swimmer assignments and annotations."""
    if disputed_ids is None:
        disputed_ids = set()

    assignment_lookup_by_class_id = {
        a['class_id']: a for a in assignments
        if a.get('class_id') is not None
    }
    assignment_lookup_by_instructor_id = {
        a['instructor_id']: a for a in assignments
    }

    output_rows = []

    for class_obj in classes.values():
        assignment = assignment_lookup_by_class_id.get(class_obj.class_id)
        if assignment is None and class_obj.instructor_id is not None:
            assignment = assignment_lookup_by_instructor_id.get(class_obj.instructor_id)

        if assignment:
            if assignment['type'] == 'pair':
                skill1 = assignment['swimmer_1'].skill_level
                skill2 = assignment['swimmer_2'].skill_level
                class_level = min(skill1, skill2)
                swimmer_1_id = assignment['swimmer_1_id']
                swimmer_1_name = assignment['swimmer_1'].name
                swimmer_2_id = assignment['swimmer_2_id']
                swimmer_2_name = assignment['swimmer_2'].name
                is_disputed = (
                    assignment.get('swimmer_1_id') in disputed_ids or
                    assignment.get('swimmer_2_id') in disputed_ids
                )
            else:
                class_level = assignment['swimmer'].skill_level
                swimmer_1_id = assignment['swimmer_id']
                swimmer_1_name = assignment['swimmer'].name
                swimmer_2_id = ''
                swimmer_2_name = ''
                is_disputed = assignment.get('swimmer_id') in disputed_ids

            # Compatibility score: only present for compatibility matches
            if assignment['match_type'] == 'compatibility':
                compat_score = f"{assignment.get('compatibility_score', 0):.1f}%"
            else:
                compat_score = ''

            flag_codes = assignment.get('flag_codes', [])
            flag_severity = _get_highest_severity(flag_codes)
            flag_review_action = _get_primary_review_action(flag_codes)
            # flag_summary: description of the highest-severity flag, or empty
            if flag_codes:
                primary_code = next(
                    (c for c in flag_codes
                     if _FLAG_CODES.get(c, {}).get('severity') == flag_severity),
                    flag_codes[0],
                )
                flag_summary = _FLAG_CODES.get(primary_code, {}).get('description', '')
            else:
                flag_summary = ''

            output_rows.append({
                'class_id': class_obj.class_id,
                'day_of_week': class_obj.day_of_week,
                'start_time': class_obj.start_time,
                'end_time': class_obj.end_time,
                'instructor_name': assignment['instructor_name'],
                'instructor_id': assignment['instructor_id'],
                'class_level': f"RSS {class_level}",
                'swimmer_1_name': swimmer_1_name,
                'swimmer_1_id': swimmer_1_id,
                'swimmer_2_name': swimmer_2_name,
                'swimmer_2_id': swimmer_2_id,
                'match_type': assignment['match_type'],
                'compatibility_score': compat_score,
                'match_confidence': f"{assignment['confidence']:.1f}%",
                'match_reason': assignment['reason_summary'],
                'continuity_dispute': is_disputed,
                'flag_codes': ','.join(flag_codes),
                'flag_summary': flag_summary,
                'review_action': flag_review_action,
                'review_severity': flag_severity,
            })
        else:
            output_rows.append({
                'class_id': class_obj.class_id,
                'day_of_week': class_obj.day_of_week,
                'start_time': class_obj.start_time,
                'end_time': class_obj.end_time,
                'instructor_name': '',
                'instructor_id': class_obj.instructor_id or '',
                'class_level': '',
                'swimmer_1_name': '',
                'swimmer_1_id': '',
                'swimmer_2_name': '',
                'swimmer_2_id': '',
                'match_type': '',
                'compatibility_score': '',
                'match_confidence': '',
                'match_reason': '',
                'continuity_dispute': False,
                'flag_codes': '',
                'flag_summary': '',
                'review_action': '',
                'review_severity': 'none',
            })

    output_rows.sort(
        key=lambda x: float(x['match_confidence'].rstrip('%')) if x['match_confidence'] else 100
    )

    df = pd.DataFrame(output_rows)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.to_csv(output_path, index=False)

    return df


def get_confidence_category(confidence: float) -> str:
    """Get human-readable category for a confidence score."""
    if confidence >= REVIEW_THRESHOLDS['excellent']:
        return 'Excellent'
    elif confidence >= REVIEW_THRESHOLDS['strong']:
        return 'Strong'
    elif confidence >= REVIEW_THRESHOLDS['good']:
        return 'Good'
    elif confidence >= REVIEW_THRESHOLDS['moderate']:
        return 'Moderate'
    elif confidence >= REVIEW_THRESHOLDS['weak']:
        return 'Weak'
    else:
        return 'Poor'


def generate_unassigned_report(
    unassigned_swimmers: List[Swimmer],
    reasons: Dict[int, str],
    output_path: str
) -> 'pd.DataFrame':
    """
    Generate CSV report of swimmers who could not be matched.

    Args:
        unassigned_swimmers: Swimmers with no assignment after all phases
        reasons: Dict mapping swimmer_id → reason code string
        output_path: Where to write the CSV
    """
    rows = []
    for swimmer in unassigned_swimmers:
        rows.append({
            'swimmer_id': swimmer.swimmer_id,
            'swimmer_name': f"{swimmer.first_name} {swimmer.last_name}",
            'skill_level': swimmer.skill_level,
            'age': swimmer.age,
            'has_special_needs': swimmer.has_special_needs,
            'reason': reasons.get(swimmer.swimmer_id, 'unknown'),
        })

    df = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.to_csv(output_path, index=False)
    return df
