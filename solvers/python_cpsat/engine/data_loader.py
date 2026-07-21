"""
Data loading module for CP-SAT v2 Swimmer-Instructor Matching System.

Loads all CSV input files and creates domain objects.
Uses ranking tables (not binary compatibility tables).
"""

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import pandas as pd

from core.swimmer_types import coerce_swimmer_type_id


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


def _optional_int(value) -> Optional[int]:
    """Return int(value) when the cell has data, otherwise None."""
    if not _has_value(value):
        return None
    return int(value)


def _class_instructor_id(instructors: dict, row) -> Tuple[Optional[int], List[str]]:
    """Resolve class instructor from either generated or partner export schema."""
    if 'instructor_id' in row.index and _has_value(row['instructor_id']):
        return int(row['instructor_id']), []
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

        # Load entities from individual paths
        df = pd.read_csv(instructors_path)
        for _, row in df.iterrows():
            instructor = Instructor(
                instructor_id=int(row['instructor_id']),
                first_name=row['first_name'],
                last_name=row['last_name'],
                primary_color_id=int(row['primary_color_id']),
                secondary_color_id=int(row['secondary_color_id']),
                primary_style_id=int(row['primary_style_id']),
                secondary_style_id=int(row['secondary_style_id']),
                is_team_captain=bool(row['is_team_captain']),
                can_teach_NL=bool(row['can_teach_NL']),
                can_teach_babies=bool(row['can_teach_babies']),
                can_teach_adults=bool(row['can_teach_adults']),
                can_teach_adapted=bool(row['can_teach_adapted'])
            )
            loader.instructors[instructor.instructor_id] = instructor

        df = pd.read_csv(swimmers_path)
        for _, row in df.iterrows():
            pair_id = None
            if pd.notna(row['pair_id']) and row['pair_id'] != '':
                pair_id = int(row['pair_id'])
            swimmer = Swimmer(
                swimmer_id=int(row['swimmer_id']),
                first_name=row['first_name'],
                last_name=row['last_name'],
                swimmer_type_id=loader._coerce_swimmer_type_id(row.get('swimmer_type_id')),
                skill_level=int(row['skill_level']),
                age=float(row['age']),
                has_special_needs=bool(row['has_special_needs']),
                notes=str(row['notes']) if pd.notna(row['notes']) else '',
                pair_id=pair_id
            )
            loader.swimmers[swimmer.swimmer_id] = swimmer

        df = pd.read_csv(classes_path)
        loader.fixed_roster_mode_requested = (
            'swimmer_1_id' in df.columns or 'swimmer_2_id' in df.columns
        )
        for _, row in df.iterrows():
            instructor_id, resolution_flags = _class_instructor_id(loader.instructors, row)
            c = Class(
                class_id=int(row['class_id']),
                day_of_week=_normalize_day(str(row['day_of_week'])),
                start_time=_normalize_time(str(row['start_time'])),
                end_time=_normalize_time(str(row['end_time'])),
                instructor_id=instructor_id,
                swimmer_1_id=_optional_int(row['swimmer_1_id']) if 'swimmer_1_id' in row.index else None,
                swimmer_2_id=_optional_int(row['swimmer_2_id']) if 'swimmer_2_id' in row.index else None,
            )
            loader.classes[c.class_id] = c
            if resolution_flags:
                loader.class_resolution_flags[c.class_id] = list(resolution_flags)

        if historical_path:
            df = pd.read_csv(historical_path)
            for _, row in df.iterrows():
                pairing = HistoricalPairing(
                    swimmer_id=int(row['swimmer_id']),
                    instructor_id=int(row['instructor_id']),
                    session=row['session'],
                    num_sessions=int(row['num_sessions'])
                )
                loader.historical_pairings.append(pairing)

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
        for _, row in colors_df.iterrows():
            color = PersonalityColor(
                color_id=int(row['color_id']),
                color_name=row['color_name'],
                traits=row['traits']
            )
            self.personality_colors[color.color_id] = color

        styles_df = self._read_csv(os.path.join(self.source_dir, 'instructor_styles.csv'), "instructor styles reference table")
        for _, row in styles_df.iterrows():
            style = InstructorStyle(
                style_id=int(row['style_id']),
                style_code=row['style_code'],
                style_name=row['style_name'],
                traits=row['traits'],
                expertise_area=row['expertise_area']
            )
            self.instructor_styles[style.style_id] = style

        types_df = self._read_csv(os.path.join(self.source_dir, 'swimmer_types.csv'), "swimmer types reference table")
        for _, row in types_df.iterrows():
            swimmer_type = SwimmerType(
                swimmer_type_id=int(row['swimmer_type_id']),
                swimmer_type_name=row['swimmer_type_name']
            )
            self.swimmer_types[swimmer_type.swimmer_type_id] = swimmer_type

    def _load_ranking_tables(self) -> None:
        """Load color and style ranking matrices (v2 format)."""
        color_rank_df = self._read_csv(
            os.path.join(self.source_dir, 'swimmer_type_color_rankings.csv'),
            "swimmer type-color rankings"
        )
        for _, row in color_rank_df.iterrows():
            key = (int(row['swimmer_type_id']), int(row['color_id']))
            self.color_rankings[key] = int(row['rank'])

        style_rank_df = self._read_csv(
            os.path.join(self.source_dir, 'swimmer_type_style_rankings.csv'),
            "swimmer type-style rankings"
        )
        for _, row in style_rank_df.iterrows():
            key = (int(row['swimmer_type_id']), int(row['style_id']))
            self.style_rankings[key] = int(row['rank'])

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
        df = self._read_csv(os.path.join(self.generated_dir, 'instructors.csv'), "instructors")
        for _, row in df.iterrows():
            instructor = Instructor(
                instructor_id=int(row['instructor_id']),
                first_name=row['first_name'],
                last_name=row['last_name'],
                primary_color_id=int(row['primary_color_id']),
                secondary_color_id=int(row['secondary_color_id']),
                primary_style_id=int(row['primary_style_id']),
                secondary_style_id=int(row['secondary_style_id']),
                is_team_captain=bool(row['is_team_captain']),
                can_teach_NL=bool(row['can_teach_NL']),
                can_teach_babies=bool(row['can_teach_babies']),
                can_teach_adults=bool(row['can_teach_adults']),
                can_teach_adapted=bool(row['can_teach_adapted'])
            )
            self.instructors[instructor.instructor_id] = instructor

    def _load_swimmers(self) -> None:
        """Load swimmers from CSV."""
        df = self._read_csv(os.path.join(self.generated_dir, 'swimmers.csv'), "swimmers")
        for _, row in df.iterrows():
            pair_id = None
            if pd.notna(row['pair_id']) and row['pair_id'] != '':
                pair_id = int(row['pair_id'])

            swimmer = Swimmer(
                swimmer_id=int(row['swimmer_id']),
                first_name=row['first_name'],
                last_name=row['last_name'],
                swimmer_type_id=self._coerce_swimmer_type_id(row.get('swimmer_type_id')),
                skill_level=int(row['skill_level']),
                age=float(row['age']),
                has_special_needs=bool(row['has_special_needs']),
                notes=str(row['notes']) if pd.notna(row['notes']) else '',
                pair_id=pair_id
            )
            self.swimmers[swimmer.swimmer_id] = swimmer

    def _load_classes(self) -> None:
        """Load class templates from CSV."""
        df = self._read_csv(os.path.join(self.generated_dir, 'classes.csv'), "classes")
        self.fixed_roster_mode_requested = (
            'swimmer_1_id' in df.columns or 'swimmer_2_id' in df.columns
        )
        for _, row in df.iterrows():
            instructor_id, resolution_flags = _class_instructor_id(self.instructors, row)
            cls = Class(
                class_id=int(row['class_id']),
                day_of_week=_normalize_day(str(row['day_of_week'])),
                start_time=_normalize_time(str(row['start_time'])),
                end_time=_normalize_time(str(row['end_time'])),
                instructor_id=instructor_id,
                swimmer_1_id=_optional_int(row['swimmer_1_id']) if 'swimmer_1_id' in row.index else None,
                swimmer_2_id=_optional_int(row['swimmer_2_id']) if 'swimmer_2_id' in row.index else None,
            )
            self.classes[cls.class_id] = cls
            if resolution_flags:
                self.class_resolution_flags[cls.class_id] = list(resolution_flags)

    def _load_historical_pairings(self) -> None:
        """Load historical swimmer-instructor pairings."""
        df = self._read_csv(os.path.join(self.generated_dir, 'historical_pairings.csv'), "historical pairings")
        for _, row in df.iterrows():
            pairing = HistoricalPairing(
                swimmer_id=int(row['swimmer_id']),
                instructor_id=int(row['instructor_id']),
                session=row['session'],
                num_sessions=int(row['num_sessions'])
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
