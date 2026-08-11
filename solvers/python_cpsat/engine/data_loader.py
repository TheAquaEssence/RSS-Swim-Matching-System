"""
Data loading module for CP-SAT v2 Swimmer-Instructor Matching System.

Loads all CSV input files and creates domain objects.
Uses ranking tables (not binary compatibility tables).
"""

import math
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import pandas as pd

from core.swimmer_types import coerce_swimmer_type_id
from .config import DATA_VALIDATION, PAIRING_CONSTRAINTS


# =============================================================================
# FORMAT HELPERS (real partner export format)
# =============================================================================

_DAY_ABBR = {
    'Mon': 'Monday', 'Tue': 'Tuesday', 'Wed': 'Wednesday',
    'Thu': 'Thursday', 'Fri': 'Friday', 'Sat': 'Saturday', 'Sun': 'Sunday',
}


def _normalize_day(day_str: str) -> str:
    """Expand abbreviated day ('Mon') to full name ('Monday')."""
    return _DAY_ABBR.get(day_str.strip(), day_str.strip())


def _normalize_time(time_str: str) -> str:
    """Convert '07:30 AM' / '07:30' to 24-hour 'HH:MM' string."""
    s = str(time_str).strip()
    if 'AM' in s.upper() or 'PM' in s.upper():
        return datetime.strptime(s, '%I:%M %p').strftime('%H:%M')
    return s


def _normalized_instructor_candidates(instructors: dict, name: str) -> Tuple[List["Instructor"], List["Instructor"]]:
    """Return exact and abbreviated instructor candidates for a raw instructor name."""
    parts = [part.strip(" .,") for part in str(name).split() if part.strip(" .,")]
    if len(parts) < 2:
        return [], []

    first = parts[0].casefold()
    last_token = parts[-1].casefold()
    full_name = " ".join(parts).casefold()
    exact_matches: List["Instructor"] = []
    abbreviated_matches: List["Instructor"] = []
    for inst in instructors.values():
        inst_first = str(inst.first_name).strip().casefold()
        inst_last = str(inst.last_name).strip().casefold()
        inst_full = f"{inst_first} {inst_last}".strip()
        if full_name == inst_full:
            exact_matches.append(inst)
        elif inst_first == first and inst_last.startswith(last_token):
            abbreviated_matches.append(inst)
    return exact_matches, abbreviated_matches


def _resolve_instructor_id(instructors: dict, name: str) -> Tuple[int, List[str]]:
    """Resolve an instructor name using exact or abbreviated forms."""
    exact_matches, abbreviated_matches = _normalized_instructor_candidates(instructors, name)
    if exact_matches:
        chosen = min(exact_matches, key=lambda inst: inst.instructor_id)
        return chosen.instructor_id, (["pre_assigned_instructor_name_ambiguous"] if len(exact_matches) > 1 else [])
    if abbreviated_matches:
        chosen = min(abbreviated_matches, key=lambda inst: inst.instructor_id)
        return chosen.instructor_id, (["pre_assigned_instructor_name_ambiguous"] if len(abbreviated_matches) > 1 else [])
    raise ValueError(f"No instructor found matching '{name}'")


def _has_value(value) -> bool:
    """Return True when a CSV cell contains a usable non-empty value."""
    return pd.notna(value) and str(value).strip() != ''


_NO_DEFAULT = object()


def _required_int(
    value,
    field_name: str,
    row_number: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    """Parse a required finite integer with a descriptive row-level error."""
    if not _has_value(value):
        raise ValueError(f"Row {row_number}: {field_name} is required")
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Row {row_number}: {field_name} must be an integer") from exc
    if not math.isfinite(numeric) or not numeric.is_integer():
        raise ValueError(f"Row {row_number}: {field_name} must be a finite integer")
    parsed = int(numeric)
    if minimum is not None and parsed < minimum:
        raise ValueError(f"Row {row_number}: {field_name} must be at least {minimum}")
    if maximum is not None and parsed > maximum:
        raise ValueError(f"Row {row_number}: {field_name} must be at most {maximum}")
    return parsed


def _optional_positive_int(value, field_name: str, row_number: int) -> Optional[int]:
    if not _has_value(value):
        return None
    return _required_int(value, field_name, row_number, minimum=1)


def _required_float(
    value,
    field_name: str,
    row_number: int,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    """Parse a required finite float with optional inclusive bounds."""
    if not _has_value(value):
        raise ValueError(f"Row {row_number}: {field_name} is required")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Row {row_number}: {field_name} must be numeric") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"Row {row_number}: {field_name} must be finite")
    if minimum is not None and parsed < minimum:
        raise ValueError(f"Row {row_number}: {field_name} must be at least {minimum}")
    if maximum is not None and parsed > maximum:
        raise ValueError(f"Row {row_number}: {field_name} must be at most {maximum}")
    return parsed


def _required_text(value, field_name: str, row_number: int) -> str:
    if not _has_value(value):
        raise ValueError(f"Row {row_number}: {field_name} is required")
    return str(value).strip()


def _optional_text(value) -> str:
    """Return trimmed descriptive metadata without turning NaN into text."""
    return str(value).strip() if _has_value(value) else ''


def _coerce_bool(
    value,
    field_name: str,
    row_number: int,
    *,
    default=_NO_DEFAULT,
) -> bool:
    """Parse an explicit boolean; missing qualification fields fail closed."""
    if not _has_value(value):
        if default is _NO_DEFAULT:
            raise ValueError(f"Row {row_number}: {field_name} is required")
        return bool(default)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        numeric = float(value)
        if math.isfinite(numeric) and numeric in {0.0, 1.0}:
            return bool(int(numeric))
    normalized = str(value).strip().casefold()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"0", "false", "no", "n"}:
        return False
    raise ValueError(
        f"Row {row_number}: {field_name} must be one of true/false, yes/no, or 1/0"
    )


def _require_columns(df: pd.DataFrame, columns: set[str], description: str) -> None:
    missing = sorted(columns - set(df.columns))
    if missing:
        raise ValueError(
            f"{description} CSV is missing required column(s): {', '.join(missing)}"
        )


def _reject_duplicate_keys(
    df: pd.DataFrame,
    columns: list[str],
    description: str,
) -> None:
    duplicates = df[df.duplicated(subset=columns, keep=False)]
    if duplicates.empty:
        return
    rendered = sorted({
        "/".join(str(row[column]) for column in columns)
        for _, row in duplicates.iterrows()
    })
    raise ValueError(
        f"{description} CSV contains duplicate key(s) for "
        f"{', '.join(columns)}: {', '.join(rendered)}"
    )


def _class_instructor_id(
    instructors: dict,
    row,
    row_number: int,
) -> Tuple[Optional[int], List[str]]:
    """Resolve class instructor from either generated or partner export schema."""
    if 'instructor_id' in row.index and _has_value(row['instructor_id']):
        return _required_int(
            row['instructor_id'], 'instructor_id', row_number, minimum=1
        ), []
    if 'instructor_name' in row.index and _has_value(row['instructor_name']):
        return _resolve_instructor_id(instructors, str(row['instructor_name']))
    return None, []


# =============================================================================
# DOMAIN OBJECTS
# =============================================================================

@dataclass
class Swimmer:
    """Represents a swimmer to be matched with an instructor."""
    swimmer_id: int
    first_name: str
    last_name: str
    swimmer_type_id: int
    skill_level: int
    age: float
    has_special_needs: bool
    notes: str
    pair_id: Optional[int] = None

    @property
    def name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def is_baby(self) -> bool:
        return self.age < 2.5

    @property
    def is_adult(self) -> bool:
        return self.age >= 18


@dataclass
class Instructor:
    """Represents an instructor who can teach swimmers."""
    instructor_id: int
    first_name: str
    last_name: str
    primary_color_id: int
    secondary_color_id: int
    primary_style_id: int
    secondary_style_id: int
    is_team_captain: bool
    can_teach_NL: bool
    can_teach_babies: bool
    can_teach_adults: bool
    can_teach_adapted: bool

    @property
    def name(self) -> str:
        return f"{self.first_name} {self.last_name}"


@dataclass
class Class:
    """Represents a class slot or fixed swimmer roster awaiting instructor assignment."""
    class_id: int
    day_of_week: str
    start_time: str
    end_time: str
    instructor_id: Optional[int]
    swimmer_1_id: Optional[int] = None
    swimmer_2_id: Optional[int] = None


@dataclass
class HistoricalPairing:
    """Represents a historical swimmer-instructor relationship."""
    swimmer_id: int
    instructor_id: int
    session: str
    num_sessions: int


@dataclass
class PersonalityColor:
    """Reference data for personality colors."""
    color_id: int
    color_name: str
    traits: str


@dataclass
class InstructorStyle:
    """Reference data for instructor teaching styles."""
    style_id: int
    style_code: str
    style_name: str
    traits: str
    expertise_area: str


@dataclass
class SwimmerType:
    """Reference data for swimmer personality types."""
    swimmer_type_id: int
    swimmer_type_name: str


# =============================================================================
# DATA LOADER CLASS
# =============================================================================

class DataLoader:
    """
    Loads and validates all CSV input files for the v2 matching system.

    Uses ranking tables (swimmer_type_color_rankings.csv,
    swimmer_type_style_rankings.csv) instead of binary compatibility tables.
    """

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.source_dir = os.path.join(data_dir, 'source')
        self.generated_dir = os.path.join(data_dir, 'generated')

        # Entity data
        self.instructors: Dict[int, Instructor] = {}
        self.swimmers: Dict[int, Swimmer] = {}
        self.classes: Dict[int, Class] = {}
        self.historical_pairings: List[HistoricalPairing] = []

        # Reference data
        self.personality_colors: Dict[int, PersonalityColor] = {}
        self.instructor_styles: Dict[int, InstructorStyle] = {}
        self.swimmer_types: Dict[int, SwimmerType] = {}

        # Ranking tables (v2 — replaces compatibility tables)
        self.color_rankings: Dict[Tuple[int, int], int] = {}
        self.style_rankings: Dict[Tuple[int, int], int] = {}
        self.class_resolution_flags: Dict[int, List[str]] = {}
        self.fixed_roster_mode_requested = False

    @classmethod
    def from_files(cls, classes_path, swimmers_path, instructors_path,
                   historical_path, source_dir):
        """Create DataLoader from individual file paths.

        Args:
            classes_path: Path to classes.csv
            swimmers_path: Path to swimmers.csv
            instructors_path: Path to instructors.csv
            historical_path: Path to historical_pairings.csv (or None)
            source_dir: Path to directory containing reference CSVs
                        (personality_colors.csv, instructor_styles.csv, etc.)
        """
        loader = cls.__new__(cls)
        loader.data_dir = None
        loader.source_dir = source_dir
        loader.generated_dir = None

        # Initialize containers
        loader.instructors = {}
        loader.swimmers = {}
        loader.classes = {}
        loader.historical_pairings = []
        loader.personality_colors = {}
        loader.instructor_styles = {}
        loader.swimmer_types = {}
        loader.color_rankings = {}
        loader.style_rankings = {}
        loader.class_resolution_flags = {}
        loader.fixed_roster_mode_requested = False

        # Load reference + ranking tables from source_dir
        loader._load_reference_tables()
        loader._load_ranking_tables()

        # Load entities through the same strict parsing path used by load_all().
        loader._load_instructors_from_path(instructors_path)
        loader._load_swimmers_from_path(swimmers_path)
        loader._load_classes_from_path(classes_path)
        if historical_path:
            loader._load_historical_pairings_from_path(historical_path)

        loader._validate_data()
        return loader

    def load_all(self) -> None:
        """Load all CSV files and validate data."""
        self._load_reference_tables()
        self._load_ranking_tables()
        self._load_instructors()
        self._load_swimmers()
        self._load_classes()
        self._load_historical_pairings()
        self._validate_data()

    # -------------------------------------------------------------------------
    # Reference Table Loading
    # -------------------------------------------------------------------------

    def _read_csv(self, filepath: str, description: str) -> pd.DataFrame:
        """Load a CSV with a descriptive error on failure."""
        if not os.path.exists(filepath):
            raise FileNotFoundError(
                f"Required CSV not found: {filepath} ({description}). "
                f"Run 'python data_generation/run_all.py --seed 42' to generate data."
            )
        try:
            return pd.read_csv(filepath)
        except Exception as e:
            raise ValueError(f"Failed to parse {filepath} ({description}): {e}") from e

    def _load_reference_tables(self) -> None:
        """Load personality colors, instructor styles, and swimmer types."""
        colors_df = self._read_csv(os.path.join(self.source_dir, 'personality_colors.csv'), "personality colors reference table")
        _require_columns(colors_df, {'color_id', 'color_name', 'traits'}, "personality colors")
        _reject_duplicate_keys(colors_df, ['color_id'], "personality colors")
        for row_number, (_, row) in enumerate(colors_df.iterrows(), start=2):
            color = PersonalityColor(
                color_id=_required_int(row['color_id'], 'color_id', row_number, minimum=1),
                color_name=_required_text(row['color_name'], 'color_name', row_number),
                traits=_optional_text(row['traits'])
            )
            self.personality_colors[color.color_id] = color

        styles_df = self._read_csv(os.path.join(self.source_dir, 'instructor_styles.csv'), "instructor styles reference table")
        _require_columns(
            styles_df,
            {'style_id', 'style_code', 'style_name', 'traits', 'expertise_area'},
            "instructor styles",
        )
        _reject_duplicate_keys(styles_df, ['style_id'], "instructor styles")
        for row_number, (_, row) in enumerate(styles_df.iterrows(), start=2):
            style = InstructorStyle(
                style_id=_required_int(row['style_id'], 'style_id', row_number, minimum=1),
                style_code=_optional_text(row['style_code']),
                style_name=_required_text(row['style_name'], 'style_name', row_number),
                traits=_optional_text(row['traits']),
                expertise_area=_optional_text(row['expertise_area'])
            )
            self.instructor_styles[style.style_id] = style

        types_df = self._read_csv(os.path.join(self.source_dir, 'swimmer_types.csv'), "swimmer types reference table")
        _require_columns(types_df, {'swimmer_type_id', 'swimmer_type_name'}, "swimmer types")
        _reject_duplicate_keys(types_df, ['swimmer_type_id'], "swimmer types")
        for row_number, (_, row) in enumerate(types_df.iterrows(), start=2):
            swimmer_type = SwimmerType(
                swimmer_type_id=_required_int(
                    row['swimmer_type_id'], 'swimmer_type_id', row_number, minimum=1
                ),
                swimmer_type_name=_required_text(
                    row['swimmer_type_name'], 'swimmer_type_name', row_number
                )
            )
            self.swimmer_types[swimmer_type.swimmer_type_id] = swimmer_type

    def _load_ranking_tables(self) -> None:
        """Load color and style ranking matrices (v2 format)."""
        color_rank_df = self._read_csv(
            os.path.join(self.source_dir, 'swimmer_type_color_rankings.csv'),
            "swimmer type-color rankings"
        )
        _require_columns(
            color_rank_df, {'swimmer_type_id', 'color_id', 'rank'}, "color rankings"
        )
        _reject_duplicate_keys(
            color_rank_df, ['swimmer_type_id', 'color_id'], "color rankings"
        )
        for row_number, (_, row) in enumerate(color_rank_df.iterrows(), start=2):
            key = (
                _required_int(row['swimmer_type_id'], 'swimmer_type_id', row_number, minimum=1),
                _required_int(row['color_id'], 'color_id', row_number, minimum=1),
            )
            self.color_rankings[key] = _required_int(
                row['rank'], 'rank', row_number, minimum=1
            )

        style_rank_df = self._read_csv(
            os.path.join(self.source_dir, 'swimmer_type_style_rankings.csv'),
            "swimmer type-style rankings"
        )
        _require_columns(
            style_rank_df, {'swimmer_type_id', 'style_id', 'rank'}, "style rankings"
        )
        _reject_duplicate_keys(
            style_rank_df, ['swimmer_type_id', 'style_id'], "style rankings"
        )
        for row_number, (_, row) in enumerate(style_rank_df.iterrows(), start=2):
            key = (
                _required_int(row['swimmer_type_id'], 'swimmer_type_id', row_number, minimum=1),
                _required_int(row['style_id'], 'style_id', row_number, minimum=1),
            )
            self.style_rankings[key] = _required_int(
                row['rank'], 'rank', row_number, minimum=1
            )

    def _coerce_swimmer_type_id(self, raw_value) -> int:
        swimmer_types = {
            swimmer_type_id: swimmer_type.swimmer_type_name
            for swimmer_type_id, swimmer_type in self.swimmer_types.items()
        }
        swimmer_type_id = coerce_swimmer_type_id(raw_value, swimmer_types)
        if swimmer_type_id is None:
            raise ValueError(f"Unknown swimmer_type_id: {raw_value}")
        return swimmer_type_id

    # -------------------------------------------------------------------------
    # Entity Loading
    # -------------------------------------------------------------------------

    def _load_instructors(self) -> None:
        """Load instructors from CSV."""
        self._load_instructors_from_path(
            os.path.join(self.generated_dir, 'instructors.csv')
        )

    def _load_instructors_from_path(self, filepath) -> None:
        df = self._read_csv(str(filepath), "instructors")
        _require_columns(
            df,
            {
                'instructor_id',
                'first_name',
                'last_name',
                'primary_color_id',
                'secondary_color_id',
                'primary_style_id',
                'secondary_style_id',
            },
            "instructors",
        )
        _reject_duplicate_keys(df, ['instructor_id'], "instructors")
        for row_number, (_, row) in enumerate(df.iterrows(), start=2):
            instructor = Instructor(
                instructor_id=_required_int(
                    row['instructor_id'], 'instructor_id', row_number, minimum=1
                ),
                first_name=_required_text(row['first_name'], 'first_name', row_number),
                last_name=_required_text(row['last_name'], 'last_name', row_number),
                primary_color_id=_required_int(
                    row['primary_color_id'], 'primary_color_id', row_number, minimum=1
                ),
                secondary_color_id=_required_int(
                    row['secondary_color_id'], 'secondary_color_id', row_number, minimum=1
                ),
                primary_style_id=_required_int(
                    row['primary_style_id'], 'primary_style_id', row_number, minimum=1
                ),
                secondary_style_id=_required_int(
                    row['secondary_style_id'], 'secondary_style_id', row_number, minimum=1
                ),
                is_team_captain=_coerce_bool(
                    row.get('is_team_captain'), 'is_team_captain', row_number, default=False
                ),
                can_teach_NL=_coerce_bool(
                    row.get('can_teach_NL'), 'can_teach_NL', row_number, default=True
                ),
                can_teach_babies=_coerce_bool(
                    row.get('can_teach_babies'), 'can_teach_babies', row_number, default=False
                ),
                can_teach_adults=_coerce_bool(
                    row.get('can_teach_adults'), 'can_teach_adults', row_number, default=False
                ),
                can_teach_adapted=_coerce_bool(
                    row.get('can_teach_adapted'), 'can_teach_adapted', row_number, default=False
                ),
            )
            self.instructors[instructor.instructor_id] = instructor

    def _load_swimmers(self) -> None:
        """Load swimmers from CSV."""
        self._load_swimmers_from_path(
            os.path.join(self.generated_dir, 'swimmers.csv')
        )

    def _load_swimmers_from_path(self, filepath) -> None:
        df = self._read_csv(str(filepath), "swimmers")
        _require_columns(
            df,
            {
                'swimmer_id',
                'first_name',
                'last_name',
                'skill_level',
                'age',
                'has_special_needs',
            },
            "swimmers",
        )
        _reject_duplicate_keys(df, ['swimmer_id'], "swimmers")
        for row_number, (_, row) in enumerate(df.iterrows(), start=2):
            swimmer = Swimmer(
                swimmer_id=_required_int(
                    row['swimmer_id'], 'swimmer_id', row_number, minimum=1
                ),
                first_name=_required_text(row['first_name'], 'first_name', row_number),
                last_name=_required_text(row['last_name'], 'last_name', row_number),
                swimmer_type_id=self._coerce_swimmer_type_id(row.get('swimmer_type_id')),
                skill_level=_required_int(
                    row['skill_level'],
                    'skill_level',
                    row_number,
                    minimum=DATA_VALIDATION['min_skill_level'],
                    maximum=DATA_VALIDATION['max_skill_level'],
                ),
                age=_required_float(
                    row['age'],
                    'age',
                    row_number,
                    minimum=DATA_VALIDATION['min_age'],
                    maximum=DATA_VALIDATION['max_age'],
                ),
                has_special_needs=_coerce_bool(
                    row['has_special_needs'], 'has_special_needs', row_number
                ),
                notes=(
                    str(row.get('notes')).strip()
                    if _has_value(row.get('notes'))
                    else ''
                ),
                pair_id=_optional_positive_int(
                    row.get('pair_id'), 'pair_id', row_number
                ),
            )
            self.swimmers[swimmer.swimmer_id] = swimmer

    def _load_classes(self) -> None:
        """Load class templates from CSV."""
        self._load_classes_from_path(os.path.join(self.generated_dir, 'classes.csv'))

    def _load_classes_from_path(self, filepath) -> None:
        df = self._read_csv(str(filepath), "classes")
        _require_columns(
            df,
            {'class_id', 'day_of_week', 'start_time', 'end_time'},
            "classes",
        )
        _reject_duplicate_keys(df, ['class_id'], "classes")
        self.fixed_roster_mode_requested = (
            'swimmer_1_id' in df.columns or 'swimmer_2_id' in df.columns
        )
        for row_number, (_, row) in enumerate(df.iterrows(), start=2):
            instructor_id, resolution_flags = _class_instructor_id(
                self.instructors, row, row_number
            )
            cls = Class(
                class_id=_required_int(
                    row['class_id'], 'class_id', row_number, minimum=1
                ),
                day_of_week=_normalize_day(
                    _required_text(row['day_of_week'], 'day_of_week', row_number)
                ),
                start_time=_normalize_time(
                    _required_text(row['start_time'], 'start_time', row_number)
                ),
                end_time=_normalize_time(
                    _required_text(row['end_time'], 'end_time', row_number)
                ),
                instructor_id=instructor_id,
                swimmer_1_id=_optional_positive_int(
                    row.get('swimmer_1_id'), 'swimmer_1_id', row_number
                ),
                swimmer_2_id=_optional_positive_int(
                    row.get('swimmer_2_id'), 'swimmer_2_id', row_number
                ),
            )
            self.classes[cls.class_id] = cls
            if resolution_flags:
                self.class_resolution_flags[cls.class_id] = list(resolution_flags)

    def _load_historical_pairings(self) -> None:
        """Load historical swimmer-instructor pairings."""
        self._load_historical_pairings_from_path(
            os.path.join(self.generated_dir, 'historical_pairings.csv')
        )

    def _load_historical_pairings_from_path(self, filepath) -> None:
        df = self._read_csv(str(filepath), "historical pairings")
        _require_columns(
            df,
            {'swimmer_id', 'instructor_id', 'session', 'num_sessions'},
            "historical pairings",
        )
        _reject_duplicate_keys(df, ['swimmer_id'], "historical pairings")
        for row_number, (_, row) in enumerate(df.iterrows(), start=2):
            pairing = HistoricalPairing(
                swimmer_id=_required_int(
                    row['swimmer_id'], 'swimmer_id', row_number, minimum=1
                ),
                instructor_id=_required_int(
                    row['instructor_id'], 'instructor_id', row_number, minimum=1
                ),
                session=_required_text(row['session'], 'session', row_number),
                num_sessions=_required_int(
                    row['num_sessions'], 'num_sessions', row_number, minimum=0
                ),
            )
            self.historical_pairings.append(pairing)

    # -------------------------------------------------------------------------
    # Validation
    # -------------------------------------------------------------------------

    def _validate_data(self) -> None:
        """Validate loaded data for referential integrity."""
        errors = []

        for instructor in self.instructors.values():
            if instructor.primary_color_id not in self.personality_colors:
                errors.append(
                    f"Instructor {instructor.instructor_id} has invalid primary_color_id: "
                    f"{instructor.primary_color_id}"
                )
            if instructor.secondary_color_id not in self.personality_colors:
                errors.append(
                    f"Instructor {instructor.instructor_id} has invalid secondary_color_id: "
                    f"{instructor.secondary_color_id}"
                )
            if instructor.primary_style_id not in self.instructor_styles:
                errors.append(
                    f"Instructor {instructor.instructor_id} has invalid primary_style_id: "
                    f"{instructor.primary_style_id}"
                )
            if instructor.secondary_style_id not in self.instructor_styles:
                errors.append(
                    f"Instructor {instructor.instructor_id} has invalid secondary_style_id: "
                    f"{instructor.secondary_style_id}"
                )

        for swimmer in self.swimmers.values():
            if swimmer.swimmer_type_id not in self.swimmer_types:
                errors.append(
                    f"Swimmer {swimmer.swimmer_id} has invalid swimmer_type_id: "
                    f"{swimmer.swimmer_type_id}"
                )
            if not math.isfinite(swimmer.age) or not (
                DATA_VALIDATION['min_age'] <= swimmer.age <= DATA_VALIDATION['max_age']
            ):
                errors.append(
                    f"Swimmer {swimmer.swimmer_id} has invalid age: {swimmer.age}"
                )
            if not (
                DATA_VALIDATION['min_skill_level']
                <= swimmer.skill_level
                <= DATA_VALIDATION['max_skill_level']
            ):
                errors.append(
                    f"Swimmer {swimmer.swimmer_id} has invalid skill_level: "
                    f"{swimmer.skill_level}"
                )

        pair_groups: Dict[int, List[Swimmer]] = {}
        for swimmer in self.swimmers.values():
            if swimmer.pair_id is not None:
                pair_groups.setdefault(swimmer.pair_id, []).append(swimmer)
        for pair_id, pair_members in pair_groups.items():
            if len(pair_members) != 2:
                errors.append(
                    f"Pair {pair_id} has {len(pair_members)} swimmers (expected exactly 2)"
                )
                continue
            swimmer_1, swimmer_2 = pair_members
            level_diff = abs(swimmer_1.skill_level - swimmer_2.skill_level)
            age_diff = abs(swimmer_1.age - swimmer_2.age)
            if level_diff > PAIRING_CONSTRAINTS['max_level_diff']:
                errors.append(
                    f"Pair {pair_id} exceeds maximum skill-level difference: "
                    f"{level_diff} > {PAIRING_CONSTRAINTS['max_level_diff']}"
                )
            if age_diff > PAIRING_CONSTRAINTS['max_age_diff']:
                errors.append(
                    f"Pair {pair_id} exceeds maximum age difference: "
                    f"{age_diff:g} > {PAIRING_CONSTRAINTS['max_age_diff']}"
                )

        for cls in self.classes.values():
            if cls.instructor_id is not None and cls.instructor_id not in self.instructors:
                errors.append(
                    f"Class {cls.class_id} has invalid instructor_id: {cls.instructor_id}"
                )
            if cls.swimmer_1_id is not None and cls.swimmer_1_id not in self.swimmers:
                errors.append(
                    f"Class {cls.class_id} has invalid swimmer_1_id: {cls.swimmer_1_id}"
                )
            if cls.swimmer_2_id is not None and cls.swimmer_2_id not in self.swimmers:
                errors.append(
                    f"Class {cls.class_id} has invalid swimmer_2_id: {cls.swimmer_2_id}"
                )
            if cls.swimmer_1_id is not None and cls.swimmer_1_id == cls.swimmer_2_id:
                errors.append(
                    f"Class {cls.class_id} repeats swimmer {cls.swimmer_1_id} in both swimmer slots"
                )

        swimmer_class_counts: Dict[int, int] = {}
        for cls in self.classes.values():
            for swimmer_id in (cls.swimmer_1_id, cls.swimmer_2_id):
                if swimmer_id is None:
                    continue
                swimmer_class_counts[swimmer_id] = swimmer_class_counts.get(swimmer_id, 0) + 1
        for swimmer_id, count in swimmer_class_counts.items():
            if count > 1:
                errors.append(
                    f"Swimmer {swimmer_id} appears in {count} classes (expected at most 1)"
                )

        for pairing in self.historical_pairings:
            if pairing.swimmer_id not in self.swimmers:
                errors.append(
                    f"Historical pairing has invalid swimmer_id: {pairing.swimmer_id}"
                )
            if pairing.instructor_id not in self.instructors:
                errors.append(
                    f"Historical pairing has invalid instructor_id: {pairing.instructor_id}"
                )

        if errors:
            raise ValueError(f"Data validation failed:\n" + "\n".join(errors))

    # -------------------------------------------------------------------------
    # Accessor Methods
    # -------------------------------------------------------------------------

    def get_instructor(self, instructor_id: int) -> Optional[Instructor]:
        return self.instructors.get(instructor_id)

    def get_swimmer(self, swimmer_id: int) -> Optional[Swimmer]:
        return self.swimmers.get(swimmer_id)

    def get_all_swimmers(self) -> List[Swimmer]:
        return list(self.swimmers.values())

    def get_all_instructors(self) -> List[Instructor]:
        return list(self.instructors.values())

    def uses_fixed_class_rosters(self) -> bool:
        return self.fixed_roster_mode_requested or any(
            cls.swimmer_1_id is not None or cls.swimmer_2_id is not None
            for cls in self.classes.values()
        )

    def get_fixed_class_entities(self) -> Tuple[List[Tuple[Class, Swimmer]], List[Tuple[Class, Swimmer, Swimmer]]]:
        individuals: List[Tuple[Class, Swimmer]] = []
        pairs: List[Tuple[Class, Swimmer, Swimmer]] = []
        for cls in self.classes.values():
            swimmer_1 = self.swimmers.get(cls.swimmer_1_id) if cls.swimmer_1_id is not None else None
            swimmer_2 = self.swimmers.get(cls.swimmer_2_id) if cls.swimmer_2_id is not None else None
            if swimmer_1 and swimmer_2:
                pairs.append((cls, swimmer_1, swimmer_2))
            elif swimmer_1:
                individuals.append((cls, swimmer_1))
            elif swimmer_2:
                individuals.append((cls, swimmer_2))
        return individuals, pairs

    def get_individual_swimmers(self) -> List[Swimmer]:
        return [s for s in self.swimmers.values() if s.pair_id is None]

    def get_paired_swimmers(self) -> List[Tuple[Swimmer, Swimmer]]:
        pairs_dict: Dict[int, List[Swimmer]] = {}
        for swimmer in self.swimmers.values():
            if swimmer.pair_id is not None:
                if swimmer.pair_id not in pairs_dict:
                    pairs_dict[swimmer.pair_id] = []
                pairs_dict[swimmer.pair_id].append(swimmer)

        pairs = []
        for pair_id, swimmers in pairs_dict.items():
            if len(swimmers) == 2:
                pairs.append((swimmers[0], swimmers[1]))
            elif len(swimmers) > 2:
                raise ValueError(
                    f"Pair {pair_id} has {len(swimmers)} swimmers (expected 2)"
                )
        return pairs

    def get_historical_pairing(self, swimmer_id: int) -> Optional[HistoricalPairing]:
        for pairing in self.historical_pairings:
            if pairing.swimmer_id == swimmer_id:
                return pairing
        return None

    def get_style_code(self, style_id: int) -> Optional[str]:
        style = self.instructor_styles.get(style_id)
        return style.style_code if style else None

    def get_color_name(self, color_id: int) -> Optional[str]:
        color = self.personality_colors.get(color_id)
        return color.color_name if color else None

    def get_style_name(self, style_id: int) -> Optional[str]:
        style = self.instructor_styles.get(style_id)
        return style.style_name if style else None

    def get_swimmer_type_name(self, swimmer_type_id: int) -> Optional[str]:
        swimmer_type = self.swimmer_types.get(swimmer_type_id)
        return swimmer_type.swimmer_type_name if swimmer_type else None

    def get_ranking_tables(self) -> Dict:
        """Return ranking tables for scorer initialization."""
        return {
            'color': self.color_rankings,
            'style': self.style_rankings
        }

    def get_reference_tables(self) -> Dict:
        """Return reference tables for explanation generation."""
        return {
            'colors': self.personality_colors,
            'styles': self.instructor_styles,
            'swimmer_types': self.swimmer_types
        }
