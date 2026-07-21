"""Profile reader module for swimmer and instructor CSV data.

Reads swimmer/instructor CSVs, resolves foreign-key IDs to human-readable
names using reference CSVs, and can write a combined profiles.json file.
"""

import json
from pathlib import Path
from typing import Any, Optional, Union

import pandas as pd

from core.swimmer_types import coerce_swimmer_type_id


def _load_lookup(path: Optional[Union[str, Path]], key_col: str, value_col: str) -> dict:
    """Load a reference CSV and return a dict mapping key_col -> value_col."""
    if path is None:
        return {}
    path = Path(path)
    if not path.exists():
        return {}
    df = pd.read_csv(path)
    return dict(zip(df[key_col], df[value_col]))


def _safe_int_or_none(val: Any) -> Optional[int]:
    """Convert a value to int, or return None if empty/NaN."""
    if pd.isna(val) or val == "" or val == "nan":
        return None
    return int(float(val))


def _safe_int(val: Any) -> int:
    """Convert a value to int."""
    return int(float(val))


def _safe_bool(val: Any) -> bool:
    """Convert a 0/1 value to bool."""
    return bool(int(float(val)))


def build_profiles(
    swimmers_path: Union[str, Path],
    instructors_path: Union[str, Path],
    colors_path: Optional[Union[str, Path]] = None,
    styles_path: Optional[Union[str, Path]] = None,
    types_path: Optional[Union[str, Path]] = None,
) -> dict:
    """Build swimmer and instructor profile dicts from CSV files.

    Foreign-key IDs are resolved to human-readable names using the reference
    CSVs. If a reference CSV is not provided or missing, fallback strings
    like "Type {id}", "Color {id}", "Style {id}" are used.

    Returns:
        dict with "swimmers" and "instructors" keys, each a dict keyed by
        string ID (e.g. {"swimmers": {"101": {...}, "102": {...}}, ...}).
    """
    # Load reference lookups
    type_lookup = _load_lookup(types_path, "swimmer_type_id", "swimmer_type_name")
    color_lookup = _load_lookup(colors_path, "color_id", "color_name")
    style_lookup = _load_lookup(styles_path, "style_id", "style_name")

    # Build swimmer profiles
    swimmers_df = pd.read_csv(swimmers_path)
    swimmers = {}
    type_lookup = {int(key): value for key, value in type_lookup.items()}
    for _, row in swimmers_df.iterrows():
        type_id = coerce_swimmer_type_id(row.get("swimmer_type_id"), type_lookup)
        if type_id is None:
            type_id = _safe_int(row["swimmer_type_id"])
        sid = str(_safe_int(row["swimmer_id"]))
        swimmers[sid] = {
            "swimmer_id": _safe_int(row["swimmer_id"]),
            "first_name": str(row["first_name"]),
            "last_name": str(row["last_name"]),
            "name": f"{row['first_name']} {row['last_name']}",
            "swimmer_type_id": type_id,
            "swimmer_type_name": type_lookup.get(type_id, f"Type {type_id}"),
            "skill_level": _safe_int(row["skill_level"]),
            "age": float(row["age"]),
            "has_special_needs": _safe_bool(row["has_special_needs"]),
            "notes": str(row["notes"]) if not pd.isna(row["notes"]) else "",
            "pair_id": _safe_int_or_none(row["pair_id"]),
        }

    # Build instructor profiles
    instructors_df = pd.read_csv(instructors_path)
    instructors = {}
    for _, row in instructors_df.iterrows():
        pc_id = _safe_int(row["primary_color_id"])
        sc_id = _safe_int(row["secondary_color_id"])
        ps_id = _safe_int(row["primary_style_id"])
        ss_id = _safe_int(row["secondary_style_id"])
        iid = str(_safe_int(row["instructor_id"]))
        instructors[iid] = {
            "instructor_id": _safe_int(row["instructor_id"]),
            "first_name": str(row["first_name"]),
            "last_name": str(row["last_name"]),
            "name": f"{row['first_name']} {row['last_name']}",
            "primary_color_id": pc_id,
            "primary_color_name": color_lookup.get(pc_id, f"Color {pc_id}"),
            "secondary_color_id": sc_id,
            "secondary_color_name": color_lookup.get(sc_id, f"Color {sc_id}"),
            "primary_style_id": ps_id,
            "primary_style_name": style_lookup.get(ps_id, f"Style {ps_id}"),
            "secondary_style_id": ss_id,
            "secondary_style_name": style_lookup.get(ss_id, f"Style {ss_id}"),
            "is_team_captain": _safe_bool(row["is_team_captain"]),
            "can_teach_NL": _safe_bool(row["can_teach_NL"]),
            "can_teach_babies": _safe_bool(row["can_teach_babies"]),
            "can_teach_adults": _safe_bool(row["can_teach_adults"]),
            "can_teach_adapted": _safe_bool(row["can_teach_adapted"]),
        }

    return {"swimmers": swimmers, "instructors": instructors}


def write_profiles_json(
    output_path: Union[str, Path],
    swimmers_path: Union[str, Path],
    instructors_path: Union[str, Path],
    colors_path: Optional[Union[str, Path]] = None,
    styles_path: Optional[Union[str, Path]] = None,
    types_path: Optional[Union[str, Path]] = None,
) -> str:
    """Build profiles and write them to a JSON file.

    Creates parent directories if they don't exist.

    Returns:
        The absolute path to the written JSON file as a string.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    profiles = build_profiles(
        swimmers_path=swimmers_path,
        instructors_path=instructors_path,
        colors_path=colors_path,
        styles_path=styles_path,
        types_path=types_path,
    )

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(profiles, f, indent=2)

    return str(output_path.resolve())
