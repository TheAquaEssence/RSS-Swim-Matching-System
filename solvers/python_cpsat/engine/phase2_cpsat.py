"""
Phase 2: CP-SAT Optimization

Uses Google OR-Tools CP-SAT solver to find the globally optimal assignment
of remaining swimmers to available instructors.

Uses the shared ranking-based CompatibilityScorer from swim_matching.scoring.

The model maximizes total compatibility score while respecting hard constraints:
- HC-1: Capacity (each instructor teaches at most one entity)
- HC-2: Adapted routing (special needs swimmers -> adapted-capable instructors)
- HC-3: Age categories (babies -> baby-capable, adults -> adult-capable)
- HC-4: Pair compatibility (RSS level difference <= 1, age difference <= 2)
"""

from typing import Dict, List, Tuple
from ortools.sat.python import cp_model

from core.scoring import CompatibilityScorer

from .config import CPSAT, AGE_THRESHOLDS, NOTES_BOOSTS
from .data_loader import Swimmer, Instructor, DataLoader
from .hard_constraints import instructor_is_qualified, pair_satisfies_constraints
from .notes_parser import parse_notes
from .phase1_continuity import _separate_swimmers


def compatibility_pass(
    unmatched_swimmers: List[Swimmer],
    available_instructors: List[Instructor],
    scorer: CompatibilityScorer,
    data_loader: DataLoader,
    config: Dict | None = None,
) -> List[Dict]:
    """
    Phase 2: CP-SAT optimization for compatibility-based matching.

    Args:
        unmatched_swimmers: List of swimmers not assigned in Phase 1
        available_instructors: List of instructors with remaining capacity
        scorer: Shared CompatibilityScorer instance
        data_loader: DataLoader instance for style code lookups

    Returns:
        List of compatibility match dictionaries
    """
    if not unmatched_swimmers or not available_instructors:
        return []

    individuals, pairs = _separate_swimmers(unmatched_swimmers)

    # Pre-compute all compatibility scores
    compatibility_scores, pair_details = _compute_all_scores(
        individuals, pairs, available_instructors, scorer, data_loader
    )
    min_auto_assign_score = _resolve_min_auto_assign_score(config)
    # Build and solve the CP-SAT model
    model, x, y = _build_model(
        individuals, pairs, available_instructors, compatibility_scores,
        min_auto_assign_score=min_auto_assign_score,
    )
    hinted_individuals, hinted_pairs = _build_greedy_hint(
        individuals, pairs, available_instructors, compatibility_scores,
        min_auto_assign_score=min_auto_assign_score,
    )
    _apply_solution_hint(model, x, y, hinted_individuals, hinted_pairs)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = _resolve_time_limit_seconds(
        individuals, pairs, available_instructors, config
    )
    solver.parameters.num_workers = CPSAT['num_workers']
    solver.parameters.log_search_progress = CPSAT['log_search_progress']

    status = solver.Solve(model)

    if status not in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        print(
            f"CP-SAT solver returned {solver.StatusName(status)} — "
            "no assignments possible under current constraints."
        )
        return []

    matches = _extract_solution(
        solver, x, y, individuals, pairs, available_instructors,
        compatibility_scores, pair_details
    )

    print(f"\n*** CP-SAT Status: {solver.StatusName(status)} ***")
    if status == cp_model.OPTIMAL:
        print("Solution is OPTIMAL — best possible assignment found.")
    elif status == cp_model.FEASIBLE:
        print("Solution is FEASIBLE — valid assignment found (may not be optimal).")

    stats = get_solver_statistics(solver, status)
    print(f"  Objective value: {stats['objective_value']}")
    print(f"  Wall time: {stats['wall_time']:.3f}s")
    print(f"  Conflicts: {stats['num_conflicts']}")
    print(f"  Branches: {stats['num_branches']}")

    return matches


def _resolve_time_limit_seconds(
    individuals: List[Swimmer],
    pairs: List[Tuple[Swimmer, Swimmer]],
    instructors: List[Instructor],
    config: Dict | None = None,
) -> float:
    """Return the CP-SAT time limit for the current problem size."""
    if config:
        override = config.get('max_time_seconds')
        if override is not None:
            try:
                override_val = float(override)
            except (TypeError, ValueError):
                override_val = 0.0
            if override_val > 0:
                return override_val

    entities = len(individuals) + len(pairs)
    instructors_count = len(instructors)

    if entities <= 75 and instructors_count <= 75:
        return 20.0
    if entities <= 250 and instructors_count <= 250:
        return 30.0
    if entities <= 450 and instructors_count <= 450:
        return 45.0
    return 60.0


def _resolve_min_auto_assign_score(config: Dict | None = None) -> float:
    """Return the minimum compatibility score allowed for automatic assignment."""
    threshold = CPSAT['min_auto_assign_score']
    if config:
        override = config.get('min_auto_assign_score')
        if override is not None:
            try:
                threshold = float(override)
            except (TypeError, ValueError):
                threshold = CPSAT['min_auto_assign_score']
    return max(0.0, min(100.0, threshold))


def diagnose_unassigned_swimmers(
    unassigned_swimmers: List[Swimmer],
    phase2_swimmers: List[Swimmer],
    available_instructors: List[Instructor],
    scorer: CompatibilityScorer,
    data_loader: DataLoader,
    config: Dict | None = None,
) -> Dict[int, Dict]:
    """Return diagnostics for unassigned swimmers blocked by the quality floor.

    A swimmer is flagged only when at least one legal candidate exists, but every
    legal candidate is below min_auto_assign_score. Capacity-only and hard-
    constraint-only failures are left to the existing unassigned reason logic.
    """
    threshold = _resolve_min_auto_assign_score(config)
    if threshold <= 0 or not unassigned_swimmers or not available_instructors:
        return {}

    unassigned_ids = {swimmer.swimmer_id for swimmer in unassigned_swimmers}
    individuals, pairs = _separate_swimmers(phase2_swimmers)
    compatibility_scores, _ = _compute_all_scores(
        individuals, pairs, available_instructors, scorer, data_loader
    )
    diagnostics: Dict[int, Dict] = {}

    for swimmer in individuals:
        if swimmer.swimmer_id not in unassigned_ids:
            continue
        candidates = []
        for instructor in available_instructors:
            if not _individual_candidate_is_feasible(swimmer, instructor):
                continue
            score = compatibility_scores[(
                'individual', swimmer.swimmer_id, instructor.instructor_id
            )]
            candidates.append((score, instructor))
        best = _best_candidate(candidates)
        if best is not None and best[0] < threshold:
            diagnostics[swimmer.swimmer_id] = _quality_floor_diagnostic(
                best[0], best[1], threshold
            )

    for swimmer1, swimmer2 in pairs:
        if not ({swimmer1.swimmer_id, swimmer2.swimmer_id} & unassigned_ids):
            continue
        pair_key = _get_pair_key(swimmer1, swimmer2)
        candidates = []
        for instructor in available_instructors:
            if not _pair_candidate_is_feasible(swimmer1, swimmer2, instructor):
                continue
            score = compatibility_scores[('pair', pair_key, instructor.instructor_id)]
            candidates.append((score, instructor))
        best = _best_candidate(candidates)
        if best is not None and best[0] < threshold:
            diagnostic = _quality_floor_diagnostic(best[0], best[1], threshold)
            diagnostic['unassigned_entity_type'] = 'pair'
            diagnostic['pair_swimmer_ids'] = [swimmer1.swimmer_id, swimmer2.swimmer_id]
            for swimmer in (swimmer1, swimmer2):
                if swimmer.swimmer_id in unassigned_ids:
                    diagnostics[swimmer.swimmer_id] = dict(diagnostic)

    return diagnostics


def _best_candidate(candidates: List[Tuple[float, Instructor]]) -> Tuple[float, Instructor] | None:
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item[0], -item[1].instructor_id))


def _quality_floor_diagnostic(
    best_score: float,
    instructor: Instructor,
    threshold: float,
) -> Dict:
    return {
        'flag_codes': ['below_min_auto_assign_score'],
        'best_available_score': round(best_score, 2),
        'best_available_instructor_id': instructor.instructor_id,
        'best_available_instructor_name': instructor.name,
        'min_auto_assign_score': threshold,
        'unassigned_entity_type': 'individual',
    }


def _blocked_instructor_names(notes: str | None) -> set[str]:
    parsed = parse_notes(notes or '')
    return set(parsed.get('avoid', []) + parsed.get('never', []))


def _individual_candidate_is_feasible(swimmer: Swimmer, instructor: Instructor) -> bool:
    """Return True when an instructor is legal for an individual swimmer."""
    if not instructor_is_qualified(swimmer, instructor):
        return False
    instr_name = f"{instructor.first_name} {instructor.last_name}"
    return instr_name not in _blocked_instructor_names(swimmer.notes)


def _pair_candidate_is_feasible(
    swimmer1: Swimmer,
    swimmer2: Swimmer,
    instructor: Instructor,
) -> bool:
    """Return True when an instructor is legal for both swimmers in a pair."""
    return (
        pair_satisfies_constraints(swimmer1, swimmer2)
        and
        _individual_candidate_is_feasible(swimmer1, instructor)
        and _individual_candidate_is_feasible(swimmer2, instructor)
    )


def _build_greedy_hint(
    individuals: List[Swimmer],
    pairs: List[Tuple[Swimmer, Swimmer]],
    instructors: List[Instructor],
    compatibility_scores: Dict,
    min_auto_assign_score: float | None = None,
) -> Tuple[Dict[int, int], Dict[Tuple[int, int], int]]:
    """Build a quick feasible assignment hint for CP-SAT."""
    threshold = CPSAT['min_auto_assign_score'] if min_auto_assign_score is None else min_auto_assign_score
    entities = []

    for swimmer in individuals:
        feasible_ids = [
            instructor.instructor_id for instructor in instructors
            if (
                _individual_candidate_is_feasible(swimmer, instructor)
                and compatibility_scores[('individual', swimmer.swimmer_id, instructor.instructor_id)] >= threshold
            )
        ]
        best_score = max(
            (
                compatibility_scores[('individual', swimmer.swimmer_id, instructor_id)]
                for instructor_id in feasible_ids
            ),
            default=0.0,
        )
        entities.append({
            'kind': 'individual',
            'key': swimmer.swimmer_id,
            'weight': 1,
            'feasible_ids': feasible_ids,
            'best_score': best_score,
        })

    for swimmer1, swimmer2 in pairs:
        pair_key = _get_pair_key(swimmer1, swimmer2)
        feasible_ids = [
            instructor.instructor_id for instructor in instructors
            if (
                _pair_candidate_is_feasible(swimmer1, swimmer2, instructor)
                and compatibility_scores[('pair', pair_key, instructor.instructor_id)] >= threshold
            )
        ]
        best_score = max(
            (
                compatibility_scores[('pair', pair_key, instructor_id)]
                for instructor_id in feasible_ids
            ),
            default=0.0,
        )
        entities.append({
            'kind': 'pair',
            'key': pair_key,
            'weight': 2,
            'feasible_ids': feasible_ids,
            'best_score': best_score,
        })

    entities.sort(
        key=lambda entity: (
            len(entity['feasible_ids']),
            -entity['weight'],
            -entity['best_score'],
        )
    )

    assigned_instructors: set[int] = set()
    hinted_individuals: Dict[int, int] = {}
    hinted_pairs: Dict[Tuple[int, int], int] = {}

    for entity in entities:
        available_ids = [
            instructor_id for instructor_id in entity['feasible_ids']
            if instructor_id not in assigned_instructors
        ]
        if not available_ids:
            continue

        if entity['kind'] == 'individual':
            swimmer_id = entity['key']
            chosen_id = max(
                available_ids,
                key=lambda instructor_id: (
                    compatibility_scores[('individual', swimmer_id, instructor_id)],
                    -instructor_id,
                ),
            )
            hinted_individuals[swimmer_id] = chosen_id
        else:
            pair_key = entity['key']
            chosen_id = max(
                available_ids,
                key=lambda instructor_id: (
                    compatibility_scores[('pair', pair_key, instructor_id)],
                    -instructor_id,
                ),
            )
            hinted_pairs[pair_key] = chosen_id

        assigned_instructors.add(chosen_id)

    return hinted_individuals, hinted_pairs


def _apply_solution_hint(
    model: cp_model.CpModel,
    x: Dict,
    y: Dict,
    hinted_individuals: Dict[int, int],
    hinted_pairs: Dict[Tuple[int, int], int],
) -> None:
    """Attach a partial feasible hint to the CP-SAT model."""
    for swimmer_id, instructor_id in hinted_individuals.items():
        var = x.get((swimmer_id, instructor_id))
        if var is not None:
            model.AddHint(var, 1)

    for pair_key, instructor_id in hinted_pairs.items():
        var = y.get((pair_key, instructor_id))
        if var is not None:
            model.AddHint(var, 1)


def _compute_all_scores(
    individuals: List[Swimmer],
    pairs: List[Tuple[Swimmer, Swimmer]],
    instructors: List[Instructor],
    scorer: CompatibilityScorer,
    data_loader: DataLoader
) -> Tuple[Dict, Dict]:
    """
    Pre-compute compatibility scores for all possible assignments.

    Returns:
        (compatibility_scores, pair_details) where:
        - compatibility_scores maps (entity_key, instructor_id) to float score
        - pair_details maps (pair_key, instructor_id) to (pair_score, s1_score, s2_score)
    """
    scores = {}
    pair_details = {}
    style_lookup = data_loader.get_style_code

    for swimmer in individuals:
        parsed_notes = parse_notes(swimmer.notes or '')
        for instructor in instructors:
            score = scorer.score_match_value(swimmer, instructor, style_lookup)

            # Apply P3 notes boosts
            instr_name = f"{instructor.first_name} {instructor.last_name}"
            if instr_name in parsed_notes.get('always', []):
                score += NOTES_BOOSTS['always_bonus']
            elif instr_name in parsed_notes.get('prefer', []):
                score += NOTES_BOOSTS['prefer_bonus']

            # Cap score at 100
            score = min(score, 100.0)

            scores[('individual', swimmer.swimmer_id, instructor.instructor_id)] = score

    for swimmer1, swimmer2 in pairs:
        parsed1 = parse_notes(swimmer1.notes or '')
        parsed2 = parse_notes(swimmer2.notes or '')
        pair_key = _get_pair_key(swimmer1, swimmer2)
        for instructor in instructors:
            pair_score, s1_score, s2_score = scorer.score_pair_match(
                swimmer1, swimmer2, instructor, style_lookup
            )

            # Apply P3 notes boosts (max of both swimmers' boosts)
            instr_name = f"{instructor.first_name} {instructor.last_name}"
            boost = 0
            for parsed in [parsed1, parsed2]:
                if instr_name in parsed.get('always', []):
                    boost = max(boost, NOTES_BOOSTS['always_bonus'])
                elif instr_name in parsed.get('prefer', []):
                    boost = max(boost, NOTES_BOOSTS['prefer_bonus'])

            pair_score = min(pair_score + boost, 100.0)

            scores[('pair', pair_key, instructor.instructor_id)] = pair_score
            pair_details[(pair_key, instructor.instructor_id)] = (
                pair_score, s1_score, s2_score
            )

    return scores, pair_details


def _get_pair_key(swimmer1: Swimmer, swimmer2: Swimmer) -> Tuple[int, int]:
    """Get a consistent key for a pair (sorted by swimmer_id)."""
    ids = sorted([swimmer1.swimmer_id, swimmer2.swimmer_id])
    return (ids[0], ids[1])


def _build_model(
    individuals: List[Swimmer],
    pairs: List[Tuple[Swimmer, Swimmer]],
    instructors: List[Instructor],
    compatibility_scores: Dict,
    min_auto_assign_score: float | None = None,
) -> Tuple[cp_model.CpModel, Dict, Dict]:
    """Build the CP-SAT model with variables, constraints, and objective."""
    model = cp_model.CpModel()
    scale = CPSAT['score_scale_factor']
    threshold = CPSAT['min_auto_assign_score'] if min_auto_assign_score is None else min_auto_assign_score

    # =========================================================================
    # DECISION VARIABLES
    # =========================================================================

    x = {}
    for swimmer in individuals:
        for instructor in instructors:
            x[(swimmer.swimmer_id, instructor.instructor_id)] = model.NewBoolVar(
                f'assign_s{swimmer.swimmer_id}_i{instructor.instructor_id}'
            )

    y = {}
    for swimmer1, swimmer2 in pairs:
        pair_key = _get_pair_key(swimmer1, swimmer2)
        for instructor in instructors:
            y[(pair_key, instructor.instructor_id)] = model.NewBoolVar(
                f'assign_pair{pair_key}_i{instructor.instructor_id}'
            )

    # =========================================================================
    # HARD CONSTRAINTS
    # =========================================================================

    # HC-1a: Each individual swimmer assigned to at most one instructor
    # (swimmers blocked by HC-2/HC-3 may have no valid instructor and remain unassigned)
    for swimmer in individuals:
        model.Add(
            sum(
                x[(swimmer.swimmer_id, instr.instructor_id)]
                for instr in instructors
            ) <= 1
        )

    # HC-1b: Each pair assigned to at most one instructor
    for swimmer1, swimmer2 in pairs:
        pair_key = _get_pair_key(swimmer1, swimmer2)
        model.Add(
            sum(
                y[(pair_key, instr.instructor_id)]
                for instr in instructors
            ) <= 1
        )

    # HC-1c: Each instructor gets at most one entity
    for instructor in instructors:
        individuals_assigned = sum(
            x[(swimmer.swimmer_id, instructor.instructor_id)]
            for swimmer in individuals
        )
        pairs_assigned = sum(
            y[(_get_pair_key(s1, s2), instructor.instructor_id)]
            for s1, s2 in pairs
        )
        model.Add(individuals_assigned + pairs_assigned <= 1)

    # HC-2: Adapted routing
    for swimmer in individuals:
        if swimmer.has_special_needs:
            for instructor in instructors:
                if not instructor.can_teach_adapted:
                    model.Add(
                        x[(swimmer.swimmer_id, instructor.instructor_id)] == 0
                    )

    for swimmer1, swimmer2 in pairs:
        if swimmer1.has_special_needs or swimmer2.has_special_needs:
            pair_key = _get_pair_key(swimmer1, swimmer2)
            for instructor in instructors:
                if not instructor.can_teach_adapted:
                    model.Add(y[(pair_key, instructor.instructor_id)] == 0)

    # HC-3: Age category capabilities
    baby_threshold = AGE_THRESHOLDS['baby_max']
    adult_threshold = AGE_THRESHOLDS['adult_min']

    for swimmer in individuals:
        if swimmer.age < baby_threshold:
            for instructor in instructors:
                if not instructor.can_teach_babies:
                    model.Add(
                        x[(swimmer.swimmer_id, instructor.instructor_id)] == 0
                    )

    for swimmer1, swimmer2 in pairs:
        if swimmer1.age < baby_threshold or swimmer2.age < baby_threshold:
            pair_key = _get_pair_key(swimmer1, swimmer2)
            for instructor in instructors:
                if not instructor.can_teach_babies:
                    model.Add(y[(pair_key, instructor.instructor_id)] == 0)

    for swimmer in individuals:
        if swimmer.age >= adult_threshold:
            for instructor in instructors:
                if not instructor.can_teach_adults:
                    model.Add(
                        x[(swimmer.swimmer_id, instructor.instructor_id)] == 0
                    )

    for swimmer1, swimmer2 in pairs:
        if swimmer1.age >= adult_threshold or swimmer2.age >= adult_threshold:
            pair_key = _get_pair_key(swimmer1, swimmer2)
            for instructor in instructors:
                if not instructor.can_teach_adults:
                    model.Add(y[(pair_key, instructor.instructor_id)] == 0)

    # P3/HC: Notes exclusions (avoid/never) prevent assignment
    for swimmer in individuals:
        parsed = parse_notes(swimmer.notes or '')
        blocked_names = parsed.get('avoid', []) + parsed.get('never', [])
        if blocked_names:
            for instructor in instructors:
                instr_name = f"{instructor.first_name} {instructor.last_name}"
                if instr_name in blocked_names:
                    model.Add(x[(swimmer.swimmer_id, instructor.instructor_id)] == 0)

    for swimmer1, swimmer2 in pairs:
        parsed1 = parse_notes(swimmer1.notes or '')
        parsed2 = parse_notes(swimmer2.notes or '')
        blocked_names = (parsed1.get('avoid', []) + parsed1.get('never', []) +
                         parsed2.get('avoid', []) + parsed2.get('never', []))
        if blocked_names:
            pair_key = _get_pair_key(swimmer1, swimmer2)
            for instructor in instructors:
                instr_name = f"{instructor.first_name} {instructor.last_name}"
                if instr_name in blocked_names:
                    model.Add(y[(pair_key, instructor.instructor_id)] == 0)

    # Quality floor: do not force legal but poor compatibility assignments.
    for swimmer in individuals:
        for instructor in instructors:
            score = compatibility_scores[('individual', swimmer.swimmer_id, instructor.instructor_id)]
            if score < threshold:
                model.Add(x[(swimmer.swimmer_id, instructor.instructor_id)] == 0)

    for swimmer1, swimmer2 in pairs:
        pair_key = _get_pair_key(swimmer1, swimmer2)
        for instructor in instructors:
            score = compatibility_scores[('pair', pair_key, instructor.instructor_id)]
            if score < threshold:
                model.Add(y[(pair_key, instructor.instructor_id)] == 0)

    # =========================================================================
    # OBJECTIVE: MAXIMIZE ASSIGNED SWIMMERS FIRST, THEN COMPATIBILITY
    # =========================================================================

    assignment_terms = []
    compatibility_terms = []
    max_compatibility_sum = 0

    for swimmer in individuals:
        for instructor in instructors:
            score = compatibility_scores[
                ('individual', swimmer.swimmer_id, instructor.instructor_id)
            ]
            score_int = int(score * scale)
            assignment_terms.append(
                x[(swimmer.swimmer_id, instructor.instructor_id)]
            )
            compatibility_terms.append(
                x[(swimmer.swimmer_id, instructor.instructor_id)] * score_int
            )
            max_compatibility_sum += score_int

    for swimmer1, swimmer2 in pairs:
        pair_key = _get_pair_key(swimmer1, swimmer2)
        for instructor in instructors:
            score = compatibility_scores[
                ('pair', pair_key, instructor.instructor_id)
            ]
            score_int = int(score * scale)
            assignment_terms.append(
                y[(pair_key, instructor.instructor_id)] * 2
            )
            compatibility_terms.append(
                y[(pair_key, instructor.instructor_id)] * score_int
            )
            max_compatibility_sum += score_int

    # One additional assigned swimmer must always outweigh any possible
    # compatibility gain from alternate solutions.
    assignment_weight = max_compatibility_sum + 1
    model.Maximize(
        sum(term * assignment_weight for term in assignment_terms)
        + sum(compatibility_terms)
    )

    return model, x, y


def _extract_solution(
    solver: cp_model.CpSolver,
    x: Dict,
    y: Dict,
    individuals: List[Swimmer],
    pairs: List[Tuple[Swimmer, Swimmer]],
    instructors: List[Instructor],
    compatibility_scores: Dict,
    pair_details: Dict
) -> List[Dict]:
    """Extract assignments from the solved model."""
    matches = []

    for swimmer in individuals:
        for instructor in instructors:
            if solver.Value(x[(swimmer.swimmer_id, instructor.instructor_id)]) == 1:
                score = compatibility_scores[
                    ('individual', swimmer.swimmer_id, instructor.instructor_id)
                ]
                matches.append({
                    'type': 'individual',
                    'swimmer_id': swimmer.swimmer_id,
                    'swimmer': swimmer,
                    'instructor_id': instructor.instructor_id,
                    'match_type': 'compatibility',
                    'compatibility_score': score
                })
                break

    for swimmer1, swimmer2 in pairs:
        pair_key = _get_pair_key(swimmer1, swimmer2)
        for instructor in instructors:
            if solver.Value(y[(pair_key, instructor.instructor_id)]) == 1:
                score = compatibility_scores[
                    ('pair', pair_key, instructor.instructor_id)
                ]
                details = pair_details[(pair_key, instructor.instructor_id)]
                matches.append({
                    'type': 'pair',
                    'swimmer_1_id': swimmer1.swimmer_id,
                    'swimmer_2_id': swimmer2.swimmer_id,
                    'swimmer_1': swimmer1,
                    'swimmer_2': swimmer2,
                    'instructor_id': instructor.instructor_id,
                    'match_type': 'compatibility',
                    'compatibility_score': score,
                    'swimmer_1_score': details[1],
                    'swimmer_2_score': details[2],
                })
                break

    return matches


def get_solver_statistics(solver: cp_model.CpSolver, status=None) -> Dict:
    """Get statistics from the solver for reporting."""
    return {
        'status': solver.StatusName(status) if status is not None else 'UNKNOWN',
        'objective_value': solver.ObjectiveValue(),
        'wall_time': solver.WallTime(),
        'num_conflicts': solver.NumConflicts(),
        'num_branches': solver.NumBranches(),
    }
