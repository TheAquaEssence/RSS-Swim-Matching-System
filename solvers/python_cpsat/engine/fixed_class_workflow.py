from __future__ import annotations

from typing import Dict, List, Set, Tuple

from ortools.sat.python import cp_model

from core.scoring import CompatibilityScorer

from .config import AGE_THRESHOLDS, CPSAT, NOTES_BOOSTS
from .data_loader import Class, DataLoader, Instructor, Swimmer
from .hard_constraints import instructor_is_qualified, pair_satisfies_constraints
from .notes_parser import parse_notes
from .phase2_cpsat import _resolve_min_auto_assign_score, _resolve_time_limit_seconds


IndividualClass = Tuple[Class, Swimmer]
PairClass = Tuple[Class, Swimmer, Swimmer]


def preassigned_pass_fixed_rosters(
    individual_classes: List[IndividualClass],
    pair_classes: List[PairClass],
    instructors: List[Instructor],
) -> Tuple[List[Dict], List[IndividualClass], List[PairClass], List[Instructor]]:
    instructor_lookup = {instructor.instructor_id: instructor for instructor in instructors}
    reserved_instructor_ids: Set[int] = set()
    preassigned_matches: List[Dict] = []
    unmatched_individual_classes: List[IndividualClass] = []
    unmatched_pair_classes: List[PairClass] = []

    for class_obj, swimmer in individual_classes:
        instructor_id = class_obj.instructor_id
        if instructor_id is None or instructor_id not in instructor_lookup or instructor_id in reserved_instructor_ids:
            unmatched_individual_classes.append((class_obj, swimmer))
            continue
        instructor = instructor_lookup[instructor_id]
        if not instructor_is_qualified(swimmer, instructor):
            unmatched_individual_classes.append((class_obj, swimmer))
            continue
        reserved_instructor_ids.add(instructor_id)
        preassigned_matches.append({
            "class_id": class_obj.class_id,
            "type": "individual",
            "swimmer_id": swimmer.swimmer_id,
            "swimmer": swimmer,
            "instructor_id": instructor_id,
            "match_type": "pre-assigned",
            "flag_codes": ["pre_assigned_instructor"],
        })

    for class_obj, swimmer1, swimmer2 in pair_classes:
        instructor_id = class_obj.instructor_id
        if instructor_id is None or instructor_id not in instructor_lookup or instructor_id in reserved_instructor_ids:
            unmatched_pair_classes.append((class_obj, swimmer1, swimmer2))
            continue
        instructor = instructor_lookup[instructor_id]
        if (
            not pair_satisfies_constraints(swimmer1, swimmer2)
            or not instructor_is_qualified(swimmer1, instructor)
            or not instructor_is_qualified(swimmer2, instructor)
        ):
            unmatched_pair_classes.append((class_obj, swimmer1, swimmer2))
            continue
        reserved_instructor_ids.add(instructor_id)
        preassigned_matches.append({
            "class_id": class_obj.class_id,
            "type": "pair",
            "swimmer_1_id": swimmer1.swimmer_id,
            "swimmer_2_id": swimmer2.swimmer_id,
            "swimmer_1": swimmer1,
            "swimmer_2": swimmer2,
            "instructor_id": instructor_id,
            "match_type": "pre-assigned",
            "flag_codes": ["pre_assigned_instructor"],
        })

    available_instructors = [
        instructor for instructor in instructors
        if instructor.instructor_id not in reserved_instructor_ids
    ]
    return (
        preassigned_matches,
        unmatched_individual_classes,
        unmatched_pair_classes,
        available_instructors,
    )


def continuity_pass_fixed_rosters(
    individual_classes: List[IndividualClass],
    pair_classes: List[PairClass],
    instructors: List[Instructor],
    historical_pairings,
) -> Tuple[List[Dict], List[IndividualClass], List[PairClass], List[Instructor], Set[int], Dict[int, List[str]]]:
    continuity_matches: List[Dict] = []
    unmatched_individual_classes: List[IndividualClass] = []
    unmatched_pair_classes: List[PairClass] = []
    disputed_swimmer_ids: Set[int] = set()
    swimmer_blocked_flags: Dict[int, List[str]] = {}

    instructor_capacity: Dict[int, int] = {
        instructor.instructor_id: 1 for instructor in instructors
    }
    individual_claimants: Set[int] = set()
    history_lookup = {pairing.swimmer_id: pairing for pairing in historical_pairings}
    instructor_lookup = {instructor.instructor_id: instructor for instructor in instructors}

    individuals_with_history: List[Tuple[Class, Swimmer, object]] = []
    for class_obj, swimmer in individual_classes:
        history = history_lookup.get(swimmer.swimmer_id)
        if history is None:
            unmatched_individual_classes.append((class_obj, swimmer))
            continue
        individuals_with_history.append((class_obj, swimmer, history))

    individuals_with_history.sort(key=lambda item: item[2].num_sessions, reverse=True)

    for class_obj, swimmer, history in individuals_with_history:
        instructor = instructor_lookup.get(history.instructor_id)
        if instructor and _notes_block_instructor(swimmer, instructor):
            unmatched_individual_classes.append((class_obj, swimmer))
            continue

        match_flags: List[str] = []
        if instructor:
            allowed, hc_flags = _continuity_hc_check(swimmer, instructor)
            if not allowed:
                if hc_flags:
                    swimmer_blocked_flags[swimmer.swimmer_id] = hc_flags
                unmatched_individual_classes.append((class_obj, swimmer))
                continue
            match_flags = hc_flags

        if instructor_capacity.get(history.instructor_id, 0) > 0:
            continuity_matches.append({
                "class_id": class_obj.class_id,
                "type": "individual",
                "swimmer_id": swimmer.swimmer_id,
                "swimmer": swimmer,
                "instructor_id": history.instructor_id,
                "match_type": "continuity",
                "num_sessions": history.num_sessions,
                "flag_codes": match_flags,
            })
            instructor_capacity[history.instructor_id] = 0
            individual_claimants.add(history.instructor_id)
        else:
            if history.instructor_id in instructor_capacity:
                swimmer_blocked_flags[swimmer.swimmer_id] = ["continuity_capacity_conflict"]
            unmatched_individual_classes.append((class_obj, swimmer))

    for class_obj, swimmer1, swimmer2 in pair_classes:
        if not pair_satisfies_constraints(swimmer1, swimmer2):
            unmatched_pair_classes.append((class_obj, swimmer1, swimmer2))
            continue

        history1 = history_lookup.get(swimmer1.swimmer_id)
        history2 = history_lookup.get(swimmer2.swimmer_id)
        if not history1 or not history2 or history1.instructor_id != history2.instructor_id:
            unmatched_pair_classes.append((class_obj, swimmer1, swimmer2))
            continue

        instructor_id = history1.instructor_id
        instructor = instructor_lookup.get(instructor_id)
        pair_flags: List[str] = []
        if instructor:
            allowed1, flags1 = _continuity_hc_check(swimmer1, instructor)
            allowed2, flags2 = _continuity_hc_check(swimmer2, instructor)
            if not (allowed1 and allowed2):
                if not allowed1 and flags1:
                    swimmer_blocked_flags[swimmer1.swimmer_id] = flags1
                if not allowed2 and flags2:
                    swimmer_blocked_flags[swimmer2.swimmer_id] = flags2
                unmatched_pair_classes.append((class_obj, swimmer1, swimmer2))
                continue
            seen: Set[str] = set()
            for flag in flags1 + flags2:
                if flag not in seen:
                    seen.add(flag)
                    pair_flags.append(flag)

        if instructor_capacity.get(instructor_id, 0) > 0:
            continuity_matches.append({
                "class_id": class_obj.class_id,
                "type": "pair",
                "swimmer_1_id": swimmer1.swimmer_id,
                "swimmer_2_id": swimmer2.swimmer_id,
                "swimmer_1": swimmer1,
                "swimmer_2": swimmer2,
                "instructor_id": instructor_id,
                "match_type": "continuity",
                "num_sessions": min(history1.num_sessions, history2.num_sessions),
                "flag_codes": pair_flags,
            })
            instructor_capacity[instructor_id] = 0
            continue

        if instructor_id in individual_claimants:
            disputed_swimmer_ids.add(swimmer1.swimmer_id)
            disputed_swimmer_ids.add(swimmer2.swimmer_id)
        if instructor_id in instructor_capacity:
            conflict_flags = ["continuity_capacity_conflict"]
            if instructor_id in individual_claimants:
                conflict_flags.append("continuity_pairing_conflict")
            swimmer_blocked_flags[swimmer1.swimmer_id] = list(conflict_flags)
            swimmer_blocked_flags[swimmer2.swimmer_id] = list(conflict_flags)
        unmatched_pair_classes.append((class_obj, swimmer1, swimmer2))

    available_instructors = [
        instructor for instructor in instructors
        if instructor_capacity.get(instructor.instructor_id, 0) > 0
    ]
    return (
        continuity_matches,
        unmatched_individual_classes,
        unmatched_pair_classes,
        available_instructors,
        disputed_swimmer_ids,
        swimmer_blocked_flags,
    )


def compatibility_pass_fixed_rosters(
    unmatched_individual_classes: List[IndividualClass],
    unmatched_pair_classes: List[PairClass],
    available_instructors: List[Instructor],
    scorer: CompatibilityScorer,
    data_loader: DataLoader,
    config: Dict | None = None,
) -> List[Dict]:
    if (not unmatched_individual_classes and not unmatched_pair_classes) or not available_instructors:
        return []

    compatibility_scores, pair_details = _compute_class_scores(
        unmatched_individual_classes,
        unmatched_pair_classes,
        available_instructors,
        scorer,
        data_loader,
    )
    min_auto_assign_score = _resolve_min_auto_assign_score(config)
    model, x, y = _build_fixed_class_model(
        unmatched_individual_classes,
        unmatched_pair_classes,
        available_instructors,
        compatibility_scores,
        min_auto_assign_score,
    )

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = _resolve_time_limit_seconds(
        [entity[1] for entity in unmatched_individual_classes],
        [(entity[1], entity[2]) for entity in unmatched_pair_classes],
        available_instructors,
        config,
    )
    solver.parameters.num_workers = CPSAT["num_workers"]
    solver.parameters.log_search_progress = CPSAT["log_search_progress"]
    status = solver.Solve(model)
    if status not in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        return []

    matches: List[Dict] = []
    for class_obj, swimmer in unmatched_individual_classes:
        for instructor in available_instructors:
            if solver.Value(x[(class_obj.class_id, instructor.instructor_id)]) == 1:
                matches.append({
                    "class_id": class_obj.class_id,
                    "type": "individual",
                    "swimmer_id": swimmer.swimmer_id,
                    "swimmer": swimmer,
                    "instructor_id": instructor.instructor_id,
                    "match_type": "compatibility",
                    "compatibility_score": compatibility_scores[("individual", class_obj.class_id, instructor.instructor_id)],
                })
                break

    for class_obj, swimmer1, swimmer2 in unmatched_pair_classes:
        for instructor in available_instructors:
            if solver.Value(y[(class_obj.class_id, instructor.instructor_id)]) == 1:
                pair_score, swimmer_1_score, swimmer_2_score = pair_details[(class_obj.class_id, instructor.instructor_id)]
                matches.append({
                    "class_id": class_obj.class_id,
                    "type": "pair",
                    "swimmer_1_id": swimmer1.swimmer_id,
                    "swimmer_2_id": swimmer2.swimmer_id,
                    "swimmer_1": swimmer1,
                    "swimmer_2": swimmer2,
                    "instructor_id": instructor.instructor_id,
                    "match_type": "compatibility",
                    "compatibility_score": pair_score,
                    "swimmer_1_score": swimmer_1_score,
                    "swimmer_2_score": swimmer_2_score,
                })
                break
    return matches


def _compute_class_scores(
    individual_classes: List[IndividualClass],
    pair_classes: List[PairClass],
    instructors: List[Instructor],
    scorer: CompatibilityScorer,
    data_loader: DataLoader,
) -> Tuple[Dict, Dict]:
    scores: Dict = {}
    pair_details: Dict = {}
    style_lookup = data_loader.get_style_code

    for class_obj, swimmer in individual_classes:
        parsed_notes = parse_notes(swimmer.notes or "")
        for instructor in instructors:
            score = scorer.score_match_value(swimmer, instructor, style_lookup)
            instructor_name = f"{instructor.first_name} {instructor.last_name}"
            if instructor_name in parsed_notes.get("always", []):
                score += NOTES_BOOSTS["always_bonus"]
            elif instructor_name in parsed_notes.get("prefer", []):
                score += NOTES_BOOSTS["prefer_bonus"]
            scores[("individual", class_obj.class_id, instructor.instructor_id)] = min(score, 100.0)

    for class_obj, swimmer1, swimmer2 in pair_classes:
        parsed_notes_1 = parse_notes(swimmer1.notes or "")
        parsed_notes_2 = parse_notes(swimmer2.notes or "")
        for instructor in instructors:
            pair_score, swimmer_1_score, swimmer_2_score = scorer.score_pair_match(
                swimmer1, swimmer2, instructor, style_lookup
            )
            instructor_name = f"{instructor.first_name} {instructor.last_name}"
            boost = 0
            for parsed_notes in (parsed_notes_1, parsed_notes_2):
                if instructor_name in parsed_notes.get("always", []):
                    boost = max(boost, NOTES_BOOSTS["always_bonus"])
                elif instructor_name in parsed_notes.get("prefer", []):
                    boost = max(boost, NOTES_BOOSTS["prefer_bonus"])
            pair_score = min(pair_score + boost, 100.0)
            scores[("pair", class_obj.class_id, instructor.instructor_id)] = pair_score
            pair_details[(class_obj.class_id, instructor.instructor_id)] = (
                pair_score,
                swimmer_1_score,
                swimmer_2_score,
            )

    return scores, pair_details


def _build_fixed_class_model(
    individual_classes: List[IndividualClass],
    pair_classes: List[PairClass],
    instructors: List[Instructor],
    compatibility_scores: Dict,
    min_auto_assign_score: float,
) -> Tuple[cp_model.CpModel, Dict, Dict]:
    model = cp_model.CpModel()
    scale = CPSAT["score_scale_factor"]

    x: Dict = {}
    for class_obj, _ in individual_classes:
        for instructor in instructors:
            x[(class_obj.class_id, instructor.instructor_id)] = model.NewBoolVar(
                f"class_{class_obj.class_id}_instr_{instructor.instructor_id}"
            )

    y: Dict = {}
    for class_obj, _, _ in pair_classes:
        for instructor in instructors:
            y[(class_obj.class_id, instructor.instructor_id)] = model.NewBoolVar(
                f"class_pair_{class_obj.class_id}_instr_{instructor.instructor_id}"
            )

    for class_obj, _ in individual_classes:
        model.Add(
            sum(x[(class_obj.class_id, instructor.instructor_id)] for instructor in instructors) <= 1
        )

    for class_obj, _, _ in pair_classes:
        model.Add(
            sum(y[(class_obj.class_id, instructor.instructor_id)] for instructor in instructors) <= 1
        )

    for instructor in instructors:
        model.Add(
            sum(x[(class_obj.class_id, instructor.instructor_id)] for class_obj, _ in individual_classes)
            + sum(y[(class_obj.class_id, instructor.instructor_id)] for class_obj, _, _ in pair_classes)
            <= 1
        )

    for class_obj, swimmer in individual_classes:
        for instructor in instructors:
            if not _individual_candidate_is_feasible(swimmer, instructor):
                model.Add(x[(class_obj.class_id, instructor.instructor_id)] == 0)
                continue
            if compatibility_scores[("individual", class_obj.class_id, instructor.instructor_id)] < min_auto_assign_score:
                model.Add(x[(class_obj.class_id, instructor.instructor_id)] == 0)

    for class_obj, swimmer1, swimmer2 in pair_classes:
        for instructor in instructors:
            if not _pair_candidate_is_feasible(swimmer1, swimmer2, instructor):
                model.Add(y[(class_obj.class_id, instructor.instructor_id)] == 0)
                continue
            if compatibility_scores[("pair", class_obj.class_id, instructor.instructor_id)] < min_auto_assign_score:
                model.Add(y[(class_obj.class_id, instructor.instructor_id)] == 0)

    assignment_terms = []
    compatibility_terms = []
    max_compatibility_sum = 0
    for class_obj, _ in individual_classes:
        for instructor in instructors:
            score_int = int(compatibility_scores[("individual", class_obj.class_id, instructor.instructor_id)] * scale)
            assignment_terms.append(x[(class_obj.class_id, instructor.instructor_id)])
            compatibility_terms.append(x[(class_obj.class_id, instructor.instructor_id)] * score_int)
            max_compatibility_sum += score_int

    for class_obj, _, _ in pair_classes:
        for instructor in instructors:
            score_int = int(compatibility_scores[("pair", class_obj.class_id, instructor.instructor_id)] * scale)
            assignment_terms.append(y[(class_obj.class_id, instructor.instructor_id)] * 2)
            compatibility_terms.append(y[(class_obj.class_id, instructor.instructor_id)] * score_int)
            max_compatibility_sum += score_int

    assignment_weight = max_compatibility_sum + 1
    model.Maximize(
        sum(term * assignment_weight for term in assignment_terms)
        + sum(compatibility_terms)
    )
    return model, x, y


def _individual_candidate_is_feasible(swimmer: Swimmer, instructor: Instructor) -> bool:
    if not instructor_is_qualified(swimmer, instructor):
        return False
    blocked_names = _blocked_instructor_names(swimmer.notes)
    return f"{instructor.first_name} {instructor.last_name}" not in blocked_names


def _pair_candidate_is_feasible(swimmer1: Swimmer, swimmer2: Swimmer, instructor: Instructor) -> bool:
    return (
        pair_satisfies_constraints(swimmer1, swimmer2)
        and _individual_candidate_is_feasible(swimmer1, instructor)
        and _individual_candidate_is_feasible(swimmer2, instructor)
    )


def _blocked_instructor_names(notes: str | None) -> set[str]:
    parsed = parse_notes(notes or "")
    return set(parsed.get("avoid", [])) | set(parsed.get("never", []))


def _continuity_hc_check(swimmer: Swimmer, instructor: Instructor) -> Tuple[bool, List[str]]:
    if swimmer.age < AGE_THRESHOLDS["baby_max"] and not instructor.can_teach_babies:
        return False, ["continuity_blocked_by_baby_capability"]
    if swimmer.age >= AGE_THRESHOLDS["adult_min"] and not instructor.can_teach_adults:
        return False, ["continuity_blocked_by_adult_capability"]
    if swimmer.has_special_needs and not instructor.can_teach_adapted:
        return False, ["continuity_blocked_by_adapted_capability"]
    return True, []


def _notes_block_instructor(swimmer: Swimmer, instructor: Instructor) -> bool:
    if not swimmer.notes:
        return False
    blocked_names = _blocked_instructor_names(swimmer.notes)
    return f"{instructor.first_name} {instructor.last_name}" in blocked_names
