"""Central hard-constraint checks for every production assignment path.

The solver phases still encode constraints where they make decisions, but this
module is the final fail-closed boundary: no successful result may contain an
assignment that violates HC-1 through HC-4.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .config import AGE_THRESHOLDS, PAIRING_CONSTRAINTS
from .data_loader import Class, EntityId, Instructor, Swimmer


@dataclass(frozen=True)
class HardConstraintViolation:
    """One invariant violation found in a proposed match list."""

    code: str
    message: str
    match_index: int | None = None


class HardConstraintViolationError(ValueError):
    """Raised when a proposed result is not safe to publish."""

    def __init__(self, violations: Sequence[HardConstraintViolation]):
        self.violations = tuple(violations)
        details = "; ".join(
            f"{violation.code}: {violation.message}"
            for violation in self.violations
        )
        super().__init__(
            f"Hard-constraint validation failed ({len(self.violations)} violation(s)): {details}"
        )


def instructor_qualification_violations(
    swimmer: Swimmer,
    instructor: Instructor,
) -> tuple[str, ...]:
    """Return HC codes that make an instructor unsafe for a swimmer."""
    violations: list[str] = []
    if swimmer.has_special_needs and not instructor.can_teach_adapted:
        violations.append("HC-2")
    if swimmer.age < AGE_THRESHOLDS["baby_max"] and not instructor.can_teach_babies:
        violations.append("HC-3")
    if swimmer.age >= AGE_THRESHOLDS["adult_min"] and not instructor.can_teach_adults:
        violations.append("HC-3")
    return tuple(violations)


def instructor_is_qualified(swimmer: Swimmer, instructor: Instructor) -> bool:
    """Return whether HC-2 and HC-3 allow this instructor assignment."""
    return not instructor_qualification_violations(swimmer, instructor)


def pair_constraint_violations(
    swimmer1: Swimmer,
    swimmer2: Swimmer,
) -> tuple[str, ...]:
    """Return HC-4 reasons that make two swimmers an illegal pair."""
    violations: list[str] = []
    if abs(swimmer1.skill_level - swimmer2.skill_level) > PAIRING_CONSTRAINTS["max_level_diff"]:
        violations.append(
            "skill-level difference exceeds "
            f"{PAIRING_CONSTRAINTS['max_level_diff']}"
        )
    if abs(swimmer1.age - swimmer2.age) > PAIRING_CONSTRAINTS["max_age_diff"]:
        violations.append(
            f"age difference exceeds {PAIRING_CONSTRAINTS['max_age_diff']} years"
        )
    return tuple(violations)


def pair_satisfies_constraints(swimmer1: Swimmer, swimmer2: Swimmer) -> bool:
    """Return whether HC-4 permits two swimmers to share one class."""
    return not pair_constraint_violations(swimmer1, swimmer2)


def collect_hard_constraint_violations(
    matches: Sequence[Mapping[str, Any]],
    swimmers: Iterable[Swimmer],
    instructors: Iterable[Instructor],
    classes: Mapping[object, Class] | Iterable[Class] | None = None,
) -> list[HardConstraintViolation]:
    """Collect all HC-1 through HC-4 violations in proposed assignments."""
    swimmer_lookup = {swimmer.swimmer_id: swimmer for swimmer in swimmers}
    instructor_lookup = {
        instructor.instructor_id: instructor for instructor in instructors
    }
    class_lookup = _class_lookup(classes)

    violations: list[HardConstraintViolation] = []
    seen_swimmers: dict[EntityId, int] = {}
    seen_classes: dict[object, int] = {}
    seen_instructor_slots: dict[tuple[Any, ...], int] = {}

    for match_index, match in enumerate(matches):
        match_type = match.get("type")
        swimmer_ids = _match_swimmer_ids(match)
        if swimmer_ids is None:
            violations.append(HardConstraintViolation(
                "DATA",
                f"match {match_index} has invalid type or swimmer identifiers",
                match_index,
            ))
            continue

        if len(swimmer_ids) == 2 and swimmer_ids[0] == swimmer_ids[1]:
            violations.append(HardConstraintViolation(
                "HC-1",
                f"match {match_index} repeats swimmer {swimmer_ids[0]}",
                match_index,
            ))

        resolved_swimmers: list[Swimmer] = []
        for swimmer_id in swimmer_ids:
            swimmer = swimmer_lookup.get(swimmer_id)
            if swimmer is None:
                violations.append(HardConstraintViolation(
                    "DATA",
                    f"match {match_index} references unknown swimmer {swimmer_id}",
                    match_index,
                ))
                continue
            resolved_swimmers.append(swimmer)
            previous_match = seen_swimmers.get(swimmer_id)
            if previous_match is not None:
                violations.append(HardConstraintViolation(
                    "HC-1",
                    f"swimmer {swimmer_id} is assigned in matches {previous_match} and {match_index}",
                    match_index,
                ))
            else:
                seen_swimmers[swimmer_id] = match_index

        instructor_id = match.get("instructor_id")
        instructor = instructor_lookup.get(instructor_id)
        if instructor is None:
            violations.append(HardConstraintViolation(
                "DATA",
                f"match {match_index} references unknown instructor {instructor_id}",
                match_index,
            ))
        else:
            capacity_key = _instructor_capacity_key(
                instructor_id,
                match.get("class_id"),
                class_lookup,
            )
            previous_match = seen_instructor_slots.get(capacity_key)
            if previous_match is not None:
                violations.append(HardConstraintViolation(
                    "HC-1",
                    f"instructor {instructor_id} exceeds capacity in matches "
                    f"{previous_match} and {match_index}",
                    match_index,
                ))
            else:
                seen_instructor_slots[capacity_key] = match_index

            for swimmer in resolved_swimmers:
                for code in instructor_qualification_violations(swimmer, instructor):
                    requirement = (
                        "adapted-capable" if code == "HC-2" else "age-qualified"
                    )
                    violations.append(HardConstraintViolation(
                        code,
                        f"swimmer {swimmer.swimmer_id} requires an {requirement} "
                        f"instructor, but instructor {instructor_id} is not qualified",
                        match_index,
                    ))

        class_id = match.get("class_id")
        if class_id is not None:
            class_key = (class_id, instructor_id)
            if class_key not in class_lookup and class_id in class_lookup:
                class_key = class_id
            if class_key not in class_lookup:
                violations.append(HardConstraintViolation(
                    "DATA",
                    f"match {match_index} references unknown class {class_id}",
                    match_index,
                ))
            previous_match = seen_classes.get(class_key)
            if previous_match is not None:
                violations.append(HardConstraintViolation(
                    "HC-1",
                    f"class {class_id} is filled by matches {previous_match} and {match_index}",
                    match_index,
                ))
            else:
                seen_classes[class_key] = match_index

        if match_type == "pair" and len(resolved_swimmers) == 2:
            for reason in pair_constraint_violations(
                resolved_swimmers[0], resolved_swimmers[1]
            ):
                violations.append(HardConstraintViolation(
                    "HC-4",
                    f"pair {swimmer_ids[0]}/{swimmer_ids[1]} {reason}",
                    match_index,
                ))

    return violations


def validate_hard_constraints(
    matches: Sequence[Mapping[str, Any]],
    swimmers: Iterable[Swimmer],
    instructors: Iterable[Instructor],
    classes: Mapping[object, Class] | Iterable[Class] | None = None,
) -> None:
    """Raise if any proposed assignment violates a hard constraint."""
    violations = collect_hard_constraint_violations(
        matches,
        swimmers,
        instructors,
        classes,
    )
    if violations:
        raise HardConstraintViolationError(violations)


def _is_entity_id(value: object) -> bool:
    return (
        isinstance(value, int) and not isinstance(value, bool) and value > 0
    ) or (
        isinstance(value, str) and bool(value) and value.isascii() and value.isdigit()
    )


def _match_swimmer_ids(match: Mapping[str, Any]) -> tuple[EntityId, ...] | None:
    match_type = match.get("type")
    if match_type == "individual" and _is_entity_id(match.get("swimmer_id")):
        return (match["swimmer_id"],)
    if (
        match_type == "pair"
        and _is_entity_id(match.get("swimmer_1_id"))
        and _is_entity_id(match.get("swimmer_2_id"))
    ):
        return (match["swimmer_1_id"], match["swimmer_2_id"])
    return None


def _class_lookup(
    classes: Mapping[object, Class] | Iterable[Class] | None,
) -> dict[object, Class]:
    if classes is None:
        return {}
    class_values = list(classes.values()) if isinstance(classes, Mapping) else list(classes)
    counts: dict[EntityId, int] = {}
    for class_obj in class_values:
        counts[class_obj.class_id] = counts.get(class_obj.class_id, 0) + 1
    lookup: dict[object, Class] = {}
    for class_obj in class_values:
        lookup[(class_obj.class_id, class_obj.instructor_id)] = class_obj
        if counts[class_obj.class_id] == 1:
            lookup[class_obj.class_id] = class_obj
    return lookup


def _instructor_capacity_key(
    instructor_id: EntityId,
    class_id: EntityId | None,
    class_lookup: Mapping[object, Class],
) -> tuple[Any, ...]:
    class_obj = (
        class_lookup.get((class_id, instructor_id)) or class_lookup.get(class_id)
        if class_id is not None
        else None
    )
    if class_obj is None:
        return (instructor_id, "unscheduled")
    return (
        instructor_id,
        class_obj.day_of_week,
        class_obj.start_time,
        class_obj.end_time,
    )
