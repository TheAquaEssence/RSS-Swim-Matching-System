"""Tests for the profile reader module."""

import json
import os
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from core.profiles.profile_reader import build_profiles, write_profiles_json


@pytest.fixture
def data_dir(tmp_path):
    """Create temporary CSV files for testing."""
    # swimmer_types.csv
    pd.DataFrame([
        {"swimmer_type_id": 1, "swimmer_type_name": "The Nervous/New"},
        {"swimmer_type_id": 2, "swimmer_type_name": "The Fearless/Energetic"},
        {"swimmer_type_id": 8, "swimmer_type_name": "Non-Response / Unknown"},
    ]).to_csv(tmp_path / "swimmer_types.csv", index=False)

    # personality_colors.csv
    pd.DataFrame([
        {"color_id": 1, "color_name": "Blue", "traits": "Empathetic"},
        {"color_id": 2, "color_name": "Orange", "traits": "Flexible"},
    ]).to_csv(tmp_path / "personality_colors.csv", index=False)

    # instructor_styles.csv
    pd.DataFrame([
        {"style_id": 1, "style_code": "NR", "style_name": "New RSS/Babies",
         "traits": "Bubbly", "expertise_area": "RSS 1-5"},
        {"style_id": 2, "style_code": "HE", "style_name": "High Energy",
         "traits": "Outgoing", "expertise_area": "RSS 1-5"},
    ]).to_csv(tmp_path / "instructor_styles.csv", index=False)

    # swimmers.csv
    pd.DataFrame([
        {"swimmer_id": 101, "first_name": "Alice", "last_name": "Smith",
         "swimmer_type_id": 1, "skill_level": 3, "age": 7.0,
         "has_special_needs": 0, "notes": "afraid of deep water", "pair_id": ""},
        {"swimmer_id": 102, "first_name": "Bob", "last_name": "Jones",
         "swimmer_type_id": 2, "skill_level": 5, "age": 9.5,
         "has_special_needs": 1, "notes": "ADHD", "pair_id": 201},
    ]).to_csv(tmp_path / "swimmers.csv", index=False)

    # instructors.csv
    pd.DataFrame([
        {"instructor_id": 501, "first_name": "Carol", "last_name": "Lee",
         "primary_color_id": 1, "secondary_color_id": 2,
         "primary_style_id": 1, "secondary_style_id": 2,
         "is_team_captain": 1, "can_teach_NL": 0,
         "can_teach_babies": 1, "can_teach_adults": 0, "can_teach_adapted": 1},
    ]).to_csv(tmp_path / "instructors.csv", index=False)

    return tmp_path


class TestBuildSwimmerProfiles:
    """Tests for swimmer profile building."""

    def test_swimmer_fields(self, data_dir):
        profiles = build_profiles(
            swimmers_path=data_dir / "swimmers.csv",
            instructors_path=data_dir / "instructors.csv",
            types_path=data_dir / "swimmer_types.csv",
        )
        swimmer = profiles["swimmers"]["101"]
        assert swimmer["swimmer_id"] == 101
        assert swimmer["first_name"] == "Alice"
        assert swimmer["last_name"] == "Smith"
        assert swimmer["name"] == "Alice Smith"
        assert swimmer["swimmer_type_id"] == 1
        assert swimmer["swimmer_type_name"] == "The Nervous/New"
        assert swimmer["skill_level"] == 3
        assert swimmer["age"] == 7.0
        assert swimmer["has_special_needs"] is False
        assert swimmer["notes"] == "afraid of deep water"

    def test_resolved_type_name(self, data_dir):
        profiles = build_profiles(
            swimmers_path=data_dir / "swimmers.csv",
            instructors_path=data_dir / "instructors.csv",
            types_path=data_dir / "swimmer_types.csv",
        )
        swimmer_bob = profiles["swimmers"]["102"]
        assert swimmer_bob["swimmer_type_name"] == "The Fearless/Energetic"

    def test_pair_id_null(self, data_dir):
        profiles = build_profiles(
            swimmers_path=data_dir / "swimmers.csv",
            instructors_path=data_dir / "instructors.csv",
        )
        alice = profiles["swimmers"]["101"]
        assert alice["pair_id"] is None

    def test_pair_id_int(self, data_dir):
        profiles = build_profiles(
            swimmers_path=data_dir / "swimmers.csv",
            instructors_path=data_dir / "instructors.csv",
        )
        bob = profiles["swimmers"]["102"]
        assert bob["pair_id"] == 201

    def test_has_special_needs_bool(self, data_dir):
        profiles = build_profiles(
            swimmers_path=data_dir / "swimmers.csv",
            instructors_path=data_dir / "instructors.csv",
        )
        assert profiles["swimmers"]["101"]["has_special_needs"] is False
        assert profiles["swimmers"]["102"]["has_special_needs"] is True

    def test_missing_swimmer_type_defaults_to_non_response(self, data_dir):
        pd.DataFrame([
            {"swimmer_id": 103, "first_name": "Cara", "last_name": "Miles",
             "swimmer_type_id": 0, "skill_level": 2, "age": 6.5,
             "has_special_needs": 0, "notes": "", "pair_id": ""},
        ]).to_csv(data_dir / "swimmers_non_response.csv", index=False)

        profiles = build_profiles(
            swimmers_path=data_dir / "swimmers_non_response.csv",
            instructors_path=data_dir / "instructors.csv",
            types_path=data_dir / "swimmer_types.csv",
        )
        swimmer = profiles["swimmers"]["103"]
        assert swimmer["swimmer_type_id"] == 8
        assert swimmer["swimmer_type_name"] == "Non-Response / Unknown"


class TestBuildInstructorProfiles:
    """Tests for instructor profile building."""

    def test_instructor_fields(self, data_dir):
        profiles = build_profiles(
            swimmers_path=data_dir / "swimmers.csv",
            instructors_path=data_dir / "instructors.csv",
            colors_path=data_dir / "personality_colors.csv",
            styles_path=data_dir / "instructor_styles.csv",
        )
        inst = profiles["instructors"]["501"]
        assert inst["instructor_id"] == 501
        assert inst["first_name"] == "Carol"
        assert inst["last_name"] == "Lee"
        assert inst["name"] == "Carol Lee"
        assert inst["primary_color_name"] == "Blue"
        assert inst["secondary_color_name"] == "Orange"
        assert inst["primary_style_name"] == "New RSS/Babies"
        assert inst["secondary_style_name"] == "High Energy"
        assert inst["is_team_captain"] is True
        assert inst["can_teach_NL"] is False
        assert inst["can_teach_babies"] is True
        assert inst["can_teach_adults"] is False
        assert inst["can_teach_adapted"] is True


class TestFallbackResolution:
    """Tests for graceful fallback when reference CSVs are missing."""

    def test_swimmer_type_fallback(self, data_dir):
        profiles = build_profiles(
            swimmers_path=data_dir / "swimmers.csv",
            instructors_path=data_dir / "instructors.csv",
            # types_path not provided
        )
        alice = profiles["swimmers"]["101"]
        assert alice["swimmer_type_name"] == "Type 1"

    def test_color_style_fallback(self, data_dir):
        profiles = build_profiles(
            swimmers_path=data_dir / "swimmers.csv",
            instructors_path=data_dir / "instructors.csv",
            # colors_path and styles_path not provided
        )
        inst = profiles["instructors"]["501"]
        assert inst["primary_color_name"] == "Color 1"
        assert inst["secondary_color_name"] == "Color 2"
        assert inst["primary_style_name"] == "Style 1"
        assert inst["secondary_style_name"] == "Style 2"


class TestWriteProfilesJson:
    """Tests for JSON file writing."""

    def test_writes_valid_json(self, data_dir):
        out = data_dir / "output" / "profiles.json"
        result_path = write_profiles_json(
            output_path=out,
            swimmers_path=data_dir / "swimmers.csv",
            instructors_path=data_dir / "instructors.csv",
        )
        assert Path(result_path).exists()
        with open(result_path) as f:
            data = json.load(f)
        assert "swimmers" in data
        assert "instructors" in data
        assert len(data["swimmers"]) == 2
        assert len(data["instructors"]) == 1

    def test_creates_parent_directories(self, data_dir):
        out = data_dir / "deep" / "nested" / "dir" / "profiles.json"
        result_path = write_profiles_json(
            output_path=out,
            swimmers_path=data_dir / "swimmers.csv",
            instructors_path=data_dir / "instructors.csv",
        )
        assert Path(result_path).exists()
