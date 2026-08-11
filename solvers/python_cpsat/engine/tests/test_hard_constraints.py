import pytest

from solvers.python_cpsat.engine.data_loader import Class, Instructor, Swimmer
from solvers.python_cpsat.engine.fixed_class_workflow import (
    preassigned_pass_fixed_rosters,
)
from solvers.python_cpsat.engine.hard_constraints import (
    HardConstraintViolationError,
    collect_hard_constraint_violations,
    validate_hard_constraints,
)


def _swimmer(
    swimmer_id: int,
    *,
    age: float = 8.0,
    skill_level: int = 3,
    special_needs: bool = False,
) -> Swimmer:
    return Swimmer(
        swimmer_id=swimmer_id,
        first_name=f"S{swimmer_id}",
        last_name="Test",
        swimmer_type_id=1,
        skill_level=skill_level,
        age=age,
        has_special_needs=special_needs,
        notes="",
    )


def _instructor(
    instructor_id: int,
    *,
    babies: bool = True,
    adults: bool = True,
    adapted: bool = True,
) -> Instructor:
    return Instructor(
        instructor_id=instructor_id,
        first_name=f"I{instructor_id}",
        last_name="Test",
        primary_color_id=1,
        secondary_color_id=2,
        primary_style_id=1,
        secondary_style_id=2,
        is_team_captain=False,
        can_teach_NL=True,
        can_teach_babies=babies,
        can_teach_adults=adults,
        can_teach_adapted=adapted,
    )


def _class(class_id: int, instructor_id: int | None = None, start: str = "09:00") -> Class:
    return Class(
        class_id=class_id,
        day_of_week="Monday",
        start_time=start,
        end_time="09:30" if start == "09:00" else "10:00",
        instructor_id=instructor_id,
    )


def test_valid_individual_and_pair_pass_final_validation():
    swimmers = [_swimmer(1), _swimmer(2), _swimmer(3, age=9.0, skill_level=4)]
    instructors = [_instructor(10), _instructor(20)]
    matches = [
        {"type": "individual", "swimmer_id": 1, "instructor_id": 10},
        {
            "type": "pair",
            "swimmer_1_id": 2,
            "swimmer_2_id": 3,
            "instructor_id": 20,
        },
    ]

    validate_hard_constraints(matches, swimmers, instructors)


def test_hc1_rejects_duplicate_swimmer_and_instructor_capacity():
    swimmers = [_swimmer(1), _swimmer(2)]
    instructors = [_instructor(10)]
    matches = [
        {"type": "individual", "swimmer_id": 1, "instructor_id": 10},
        {"type": "individual", "swimmer_id": 1, "instructor_id": 10},
    ]

    violations = collect_hard_constraint_violations(matches, swimmers, instructors)

    assert sum(item.code == "HC-1" for item in violations) == 2
    with pytest.raises(HardConstraintViolationError, match="HC-1"):
        validate_hard_constraints(matches, swimmers, instructors)


def test_hc1_capacity_is_scoped_to_the_class_time_slot():
    swimmers = [_swimmer(1), _swimmer(2), _swimmer(3)]
    instructors = [_instructor(10)]
    classes = {
        100: _class(100, start="09:00"),
        200: _class(200, start="09:30"),
        300: _class(300, start="09:00"),
    }

    validate_hard_constraints(
        [
            {"class_id": 100, "type": "individual", "swimmer_id": 1, "instructor_id": 10},
            {"class_id": 200, "type": "individual", "swimmer_id": 2, "instructor_id": 10},
        ],
        swimmers,
        instructors,
        classes,
    )

    violations = collect_hard_constraint_violations(
        [
            {"class_id": 100, "type": "individual", "swimmer_id": 1, "instructor_id": 10},
            {"class_id": 300, "type": "individual", "swimmer_id": 3, "instructor_id": 10},
        ],
        swimmers,
        instructors,
        classes,
    )
    assert [item.code for item in violations] == ["HC-1"]


def test_hc2_rejects_nonadapted_instructor():
    swimmer = _swimmer(1, special_needs=True)
    instructor = _instructor(10, adapted=False)

    with pytest.raises(HardConstraintViolationError, match="HC-2"):
        validate_hard_constraints(
            [{"type": "individual", "swimmer_id": 1, "instructor_id": 10}],
            [swimmer],
            [instructor],
        )


@pytest.mark.parametrize(
    ("swimmer", "instructor"),
    [
        (_swimmer(1, age=2.0), _instructor(10, babies=False)),
        (_swimmer(1, age=18.0), _instructor(10, adults=False)),
    ],
)
def test_hc3_rejects_unqualified_age_routing(swimmer, instructor):
    with pytest.raises(HardConstraintViolationError, match="HC-3"):
        validate_hard_constraints(
            [{"type": "individual", "swimmer_id": 1, "instructor_id": 10}],
            [swimmer],
            [instructor],
        )


def test_hc4_rejects_pair_level_and_age_gaps():
    swimmers = [
        _swimmer(1, age=7.0, skill_level=1),
        _swimmer(2, age=10.0, skill_level=4),
    ]
    instructor = _instructor(10)
    matches = [{
        "type": "pair",
        "swimmer_1_id": 1,
        "swimmer_2_id": 2,
        "instructor_id": 10,
    }]

    violations = collect_hard_constraint_violations(matches, swimmers, [instructor])

    assert [item.code for item in violations] == ["HC-4", "HC-4"]


def test_preassigned_instructor_must_pass_hard_qualifications():
    swimmer = _swimmer(1, special_needs=True)
    instructor = _instructor(10, adapted=False)
    class_obj = _class(100, instructor_id=10)

    matches, unmatched_individuals, unmatched_pairs, available = (
        preassigned_pass_fixed_rosters(
            [(class_obj, swimmer)],
            [],
            [instructor],
        )
    )

    assert matches == []
    assert unmatched_individuals == [(class_obj, swimmer)]
    assert unmatched_pairs == []
    assert available == [instructor]


def test_preassigned_pair_must_pass_hc4():
    swimmer1 = _swimmer(1, age=7.0, skill_level=1)
    swimmer2 = _swimmer(2, age=10.0, skill_level=4)
    instructor = _instructor(10)
    class_obj = _class(100, instructor_id=10)

    matches, unmatched_individuals, unmatched_pairs, available = (
        preassigned_pass_fixed_rosters(
            [],
            [(class_obj, swimmer1, swimmer2)],
            [instructor],
        )
    )

    assert matches == []
    assert unmatched_individuals == []
    assert unmatched_pairs == [(class_obj, swimmer1, swimmer2)]
    assert available == [instructor]
