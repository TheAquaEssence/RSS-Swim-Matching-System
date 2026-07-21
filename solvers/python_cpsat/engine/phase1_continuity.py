"""
Phase 1: Greedy Continuity Matching

Assigns swimmers to their previous instructor if available.
This phase is deterministic and prioritizes continuity over optimization.

Algorithm:
1. Separate swimmers into individuals and pre-paired groups
2. Sort individuals with history by num_sessions (descending) for tiebreaking
3. Assign to previous instructor if available and has capacity
4. For pairs: only assign if BOTH swimmers had the same previous instructor
"""

from typing import Dict, List, Tuple, Optional, Set
from .data_loader import Swimmer, Instructor, HistoricalPairing
from .notes_parser import parse_notes
from .config import AGE_THRESHOLDS

_ADAPTED_OVERRIDE_FLAGS = [
    'continuity_overrides_adapted_capability',
    'manual_policy_review_required',
]


def continuity_pass(
    swimmers: List[Swimmer],
    instructors: List[Instructor],
    historical_pairings: List[HistoricalPairing]
) -> Tuple[List[Dict], List[Swimmer], List[Instructor], Set[int], Dict[int, List[str]]]:
    """
    Phase 1: Greedy continuity matching.

    Returns:
        tuple containing:
        - continuity_matches: List of match dictionaries
        - unmatched_swimmers: List of swimmers not matched via continuity
        - available_instructors: List of instructors still available
        - disputed_swimmer_ids: Set of swimmer IDs whose pair continuity claim
          was beaten by an individual claim on the same instructor
        - swimmer_blocked_flags: Dict mapping swimmer_id → list of flag codes that
          should be applied to that swimmer's final match (regardless of phase).
          Populated when HC-3 (age) blocks a continuity claim.
    """
    continuity_matches = []
    unmatched_swimmers = []
    disputed_swimmer_ids: Set[int] = set()
    swimmer_blocked_flags: Dict[int, List[str]] = {}

    # Track instructor capacity (each instructor can teach 1 entity per slot)
    instructor_capacity: Dict[int, int] = {
        instr.instructor_id: 1 for instr in instructors
    }
    # Track which instructors were claimed by an individual this pass
    individual_claimants: Set[int] = set()  # set of instructor_ids

    # Build lookup for historical pairings
    history_lookup: Dict[int, HistoricalPairing] = {
        hp.swimmer_id: hp for hp in historical_pairings
    }

    # Build instructor lookup for notes checking
    instructor_lookup: Dict[int, Instructor] = {i.instructor_id: i for i in instructors}

    # Separate individuals and pairs
    individuals, pairs = _separate_swimmers(swimmers)

    # =========================================================================
    # PROCESS INDIVIDUALS WITH HISTORY
    # =========================================================================

    individuals_with_history: List[Tuple[Swimmer, HistoricalPairing]] = []
    individuals_without_history: List[Swimmer] = []

    for swimmer in individuals:
        if swimmer.swimmer_id in history_lookup:
            individuals_with_history.append(
                (swimmer, history_lookup[swimmer.swimmer_id])
            )
        else:
            individuals_without_history.append(swimmer)

    # Sort by num_sessions descending (longer relationships first)
    individuals_with_history.sort(
        key=lambda x: x[1].num_sessions,
        reverse=True
    )

    for swimmer, history in individuals_with_history:
        prev_instructor_id = history.instructor_id

        # Notes suppression: skip continuity if swimmer explicitly avoids this instructor
        instructor = instructor_lookup.get(prev_instructor_id)
        if instructor and _notes_block_instructor(swimmer, instructor):
            unmatched_swimmers.append(swimmer)
            continue

        # HC guard: check HC-3 (hard stop) and HC-2 (soft override with flag)
        match_flags: List[str] = []
        if instructor:
            allowed, hc_flags = _continuity_hc_check(swimmer, instructor)
            if not allowed:
                if hc_flags:
                    swimmer_blocked_flags[swimmer.swimmer_id] = hc_flags
                unmatched_swimmers.append(swimmer)
                continue
            match_flags = hc_flags

        if instructor_capacity.get(prev_instructor_id, 0) > 0:
            continuity_matches.append({
                'type': 'individual',
                'swimmer_id': swimmer.swimmer_id,
                'swimmer': swimmer,
                'instructor_id': prev_instructor_id,
                'match_type': 'continuity',
                'num_sessions': history.num_sessions,
                'flag_codes': match_flags,
            })
            instructor_capacity[prev_instructor_id] = 0
            individual_claimants.add(prev_instructor_id)
        else:
            # Instructor was in pool but already taken → capacity conflict
            if prev_instructor_id in instructor_capacity:
                swimmer_blocked_flags[swimmer.swimmer_id] = ['continuity_capacity_conflict']
            unmatched_swimmers.append(swimmer)

    # Individuals without history go to Phase 2
    unmatched_swimmers.extend(individuals_without_history)

    # =========================================================================
    # PROCESS PAIRS WITH SHARED HISTORY
    # =========================================================================

    for swimmer1, swimmer2 in pairs:
        history1 = history_lookup.get(swimmer1.swimmer_id)
        history2 = history_lookup.get(swimmer2.swimmer_id)

        if history1 and history2:
            prev_instr1 = history1.instructor_id
            prev_instr2 = history2.instructor_id

            if prev_instr1 == prev_instr2:
                instr = instructor_lookup.get(prev_instr1)
                # HC guard: HC-3 is a hard stop; HC-2 can be overridden with flags
                pair_flags: List[str] = []
                if instr:
                    allowed1, flags1 = _continuity_hc_check(swimmer1, instr)
                    allowed2, flags2 = _continuity_hc_check(swimmer2, instr)
                    if not (allowed1 and allowed2):
                        # Record per-swimmer blocked flags for HC-3 blocks
                        if not allowed1 and flags1:
                            swimmer_blocked_flags[swimmer1.swimmer_id] = flags1
                        if not allowed2 and flags2:
                            swimmer_blocked_flags[swimmer2.swimmer_id] = flags2
                        unmatched_swimmers.append(swimmer1)
                        unmatched_swimmers.append(swimmer2)
                        continue
                    # Merge flags from both swimmers (deduplicated)
                    seen: Set[str] = set()
                    for f in flags1 + flags2:
                        if f not in seen:
                            pair_flags.append(f)
                            seen.add(f)
                if instructor_capacity.get(prev_instr1, 0) > 0:
                    num_sessions = min(history1.num_sessions, history2.num_sessions)
                    continuity_matches.append({
                        'type': 'pair',
                        'swimmer_1_id': swimmer1.swimmer_id,
                        'swimmer_2_id': swimmer2.swimmer_id,
                        'swimmer_1': swimmer1,
                        'swimmer_2': swimmer2,
                        'instructor_id': prev_instr1,
                        'match_type': 'continuity',
                        'num_sessions': num_sessions,
                        'flag_codes': pair_flags,
                    })
                    instructor_capacity[prev_instr1] = 0
                    continue
                else:
                    # Capacity 0: was it taken by an individual? → dispute
                    if prev_instr1 in individual_claimants:
                        disputed_swimmer_ids.add(swimmer1.swimmer_id)
                        disputed_swimmer_ids.add(swimmer2.swimmer_id)
                    # Instructor was in pool but already taken → capacity conflict
                    if prev_instr1 in instructor_capacity:
                        conflict_flags = ['continuity_capacity_conflict']
                        # Pair lost specifically to a private individual → pairing conflict
                        if prev_instr1 in individual_claimants:
                            conflict_flags.append('continuity_pairing_conflict')
                        swimmer_blocked_flags[swimmer1.swimmer_id] = list(conflict_flags)
                        swimmer_blocked_flags[swimmer2.swimmer_id] = list(conflict_flags)

        # No shared continuity — pair goes to Phase 2
        unmatched_swimmers.append(swimmer1)
        unmatched_swimmers.append(swimmer2)

    # =========================================================================
    # DETERMINE AVAILABLE INSTRUCTORS
    # =========================================================================

    available_instructors = [
        instr for instr in instructors
        if instructor_capacity.get(instr.instructor_id, 0) > 0
    ]

    return continuity_matches, unmatched_swimmers, available_instructors, disputed_swimmer_ids, swimmer_blocked_flags


def _hc_allows(swimmer: Swimmer, instructor: Instructor) -> bool:
    """Return True if the instructor is legally allowed to teach this swimmer (HC-2, HC-3)."""
    # HC-2: adapted swimmers need adapted-capable instructor
    if swimmer.has_special_needs and not instructor.can_teach_adapted:
        return False
    # HC-3: baby swimmers need baby-capable instructor
    if swimmer.age < AGE_THRESHOLDS['baby_max'] and not instructor.can_teach_babies:
        return False
    # HC-3: adult swimmers need adult-capable instructor
    if swimmer.age >= AGE_THRESHOLDS['adult_min'] and not instructor.can_teach_adults:
        return False
    return True


def _continuity_hc_check(
    swimmer: Swimmer, instructor: Instructor
) -> Tuple[bool, List[str]]:
    """Check HC-2 and HC-3 for a continuity candidate.

    HC-3 (age qualification) is a hard stop — returns (False, []) when it blocks.
    HC-2 (adapted capability) can be overridden by continuity per client policy —
    returns (True, [override_flags]) when it would normally block.

    Returns:
        (allowed, flag_codes)
    """
    # HC-3 hard stop: age capability (never overridable by continuity)
    if swimmer.age < AGE_THRESHOLDS['baby_max'] and not instructor.can_teach_babies:
        return False, ['continuity_blocked_by_baby_capability']
    if swimmer.age >= AGE_THRESHOLDS['adult_min'] and not instructor.can_teach_adults:
        return False, ['continuity_blocked_by_adult_capability']

    # HC-2 soft override: adapted capability — allow but flag for human review
    if swimmer.has_special_needs and not instructor.can_teach_adapted:
        return True, list(_ADAPTED_OVERRIDE_FLAGS)

    return True, []


def _notes_block_instructor(swimmer: Swimmer, instructor: Instructor) -> bool:
    """Return True if swimmer's notes explicitly avoid/never this instructor."""
    if not swimmer.notes:
        return False
    parsed = parse_notes(swimmer.notes)
    instructor_full_name = f"{instructor.first_name} {instructor.last_name}"
    blocked_names = parsed['avoid'] + parsed['never']
    return instructor_full_name in blocked_names


def _separate_swimmers(
    swimmers: List[Swimmer]
) -> Tuple[List[Swimmer], List[Tuple[Swimmer, Swimmer]]]:
    """Separate swimmers into individuals and pre-paired groups."""
    individuals = []
    pairs_dict: Dict[int, List[Swimmer]] = {}

    for swimmer in swimmers:
        if swimmer.pair_id is None:
            individuals.append(swimmer)
        else:
            if swimmer.pair_id not in pairs_dict:
                pairs_dict[swimmer.pair_id] = []
            pairs_dict[swimmer.pair_id].append(swimmer)

    pairs = []
    for pair_id, pair_swimmers in pairs_dict.items():
        if len(pair_swimmers) == 2:
            pairs.append((pair_swimmers[0], pair_swimmers[1]))
        elif len(pair_swimmers) == 1:
            individuals.append(pair_swimmers[0])
        else:
            raise ValueError(
                f"Pair {pair_id} has {len(pair_swimmers)} swimmers (expected 2)"
            )

    return individuals, pairs


def group_pairs(swimmers: List[Swimmer]) -> List[Tuple[Swimmer, Swimmer]]:
    """Public wrapper: get list of (swimmer1, swimmer2) tuples for pre-paired groups."""
    _, pairs = _separate_swimmers(swimmers)
    return pairs


def get_individuals(swimmers: List[Swimmer]) -> List[Swimmer]:
    """Public wrapper: get swimmers not part of a pre-paired group."""
    individuals, _ = _separate_swimmers(swimmers)
    return individuals


def get_continuity_info(
    swimmer_id: int,
    historical_pairings: List[HistoricalPairing]
) -> Optional[Dict]:
    """Get continuity information for a swimmer."""
    for hp in historical_pairings:
        if hp.swimmer_id == swimmer_id:
            return {
                'instructor_id': hp.instructor_id,
                'num_sessions': hp.num_sessions,
                'session': hp.session
            }
    return None
