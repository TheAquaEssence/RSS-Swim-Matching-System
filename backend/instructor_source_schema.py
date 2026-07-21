from __future__ import annotations

from enum import Enum


class EditableInstructorPosition(str, Enum):
    INSTRUCTOR = "Instructor"
    INSTRUCTOR_TEAM_CAPTAIN = "Instructor Team Captain"
    YOUTH_LEADER = "Youth Leader"
    AQUAFIT_INSTRUCTOR = "Aquafit Instructor"
    COACH = "Coach"


EDITABLE_INSTRUCTOR_POSITION_VALUES = tuple(position.value for position in EditableInstructorPosition)

STYLE_COLOR_PROFILE_COLUMNS = (
    "primary_color_id",
    "secondary_color_id",
    "primary_style_id",
    "secondary_style_id",
)

CERTIFICATION_PROFILE_COLUMNS = (
    "is_team_captain",
    "can_teach_NL",
    "can_teach_babies",
    "can_teach_adults",
    "can_teach_adapted",
)

SOURCE_PROFILE_COLUMNS = STYLE_COLOR_PROFILE_COLUMNS + CERTIFICATION_PROFILE_COLUMNS + ("used_default_profile",)


def canonical_editable_instructor_position(value: str | None) -> str | None:
    normalized = " ".join(str(value or "").split())
    if not normalized:
        return None

    for candidate in sorted(EDITABLE_INSTRUCTOR_POSITION_VALUES, key=len, reverse=True):
        if normalized == candidate or normalized.startswith(f"{candidate} "):
            return candidate
    return None


def is_editable_instructor_position(value: str | None) -> bool:
    return canonical_editable_instructor_position(value) is not None
