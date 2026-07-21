import pytest
import json
import tempfile
import os
from frontend.xai_dashboard.data_manager import DataManager

@pytest.fixture
def sample_result():
    return {
        "ok": True,
        "summary": {"classes": 3, "assigned_swimmers": 5, "unassigned_swimmers": 1, "avg_confidence": 72.5},
        "matches": [
            {"type": "individual", "swimmer_id": 1, "swimmer_name": "Alice", "instructor_id": 10,
             "instructor_name": "Coach A", "confidence": 85.0, "compatibility_score": 78.5,
             "reason": "Compatibility match", "continuity_dispute": False},
            {"type": "pair", "swimmer_1_id": 2, "swimmer_1_name": "Bob", "swimmer_2_id": 3,
             "swimmer_2_name": "Carol", "instructor_id": 11, "instructor_name": "Coach B",
             "confidence": 45.0, "compatibility_score": 55.0, "reason": "Pair match",
             "continuity_dispute": True},
        ],
        "unassigned": [
            {"swimmer_id": 4, "swimmer_name": "Dave", "reason": "No eligible instructors"}
        ],
        "result_files": {"profiles": "profiles.json"}
    }

@pytest.fixture
def sample_profiles():
    return {
        "swimmers": {
            "1": {"swimmer_id": 1, "name": "Alice", "age": 7, "swimmer_type_id": 2,
                  "swimmer_type_name": "Fearless", "skill_level": 3, "has_special_needs": False,
                  "notes": "", "pair_id": None},
            "2": {"swimmer_id": 2, "name": "Bob", "age": 8, "swimmer_type_id": 1,
                  "swimmer_type_name": "Cautious", "skill_level": 4, "has_special_needs": False,
                  "notes": "", "pair_id": 1},
            "3": {"swimmer_id": 3, "name": "Carol", "age": 9, "swimmer_type_id": 1,
                  "swimmer_type_name": "Cautious", "skill_level": 4, "has_special_needs": False,
                  "notes": "", "pair_id": 1},
        },
        "instructors": {
            "10": {"instructor_id": 10, "name": "Coach A", "primary_color_id": 1,
                   "primary_color_name": "Blue", "secondary_color_id": 2, "secondary_color_name": "Orange",
                   "primary_style_id": 1, "primary_style_name": "Motivational",
                   "secondary_style_id": 3, "secondary_style_name": "Technique",
                   "is_team_captain": False, "can_teach_adapted": True, "can_teach_adults": False,
                   "can_teach_babies": False, "can_teach_NL": True},
            "11": {"instructor_id": 11, "name": "Coach B", "primary_color_id": 3,
                   "primary_color_name": "Green", "secondary_color_id": 4, "secondary_color_name": "Red",
                   "primary_style_id": 2, "primary_style_name": "Patient",
                   "secondary_style_id": 5, "secondary_style_name": "Playful",
                   "is_team_captain": True, "can_teach_adapted": False, "can_teach_adults": True,
                   "can_teach_babies": True, "can_teach_NL": False},
        }
    }

@pytest.fixture
def data_dir(sample_result, sample_profiles, tmp_path):
    result_path = tmp_path / "result.json"
    profiles_path = tmp_path / "profiles.json"
    result_path.write_text(json.dumps(sample_result))
    profiles_path.write_text(json.dumps(sample_profiles))
    return tmp_path

class TestDataManager:
    def test_load_from_directory(self, data_dir):
        dm = DataManager(str(data_dir))
        assert dm.summary["classes"] == 3
        assert len(dm.matches) == 2
        assert len(dm.unassigned) == 1

    def test_get_match_by_index(self, data_dir):
        dm = DataManager(str(data_dir))
        m = dm.get_match(0)
        assert m["swimmer_name"] == "Alice"

    def test_get_match_out_of_range(self, data_dir):
        dm = DataManager(str(data_dir))
        assert dm.get_match(99) is None

    def test_get_swimmer_profile(self, data_dir):
        dm = DataManager(str(data_dir))
        p = dm.get_swimmer(1)
        assert p["name"] == "Alice"

    def test_get_instructor_profile(self, data_dir):
        dm = DataManager(str(data_dir))
        p = dm.get_instructor(10)
        assert p["name"] == "Coach A"

    def test_missing_profile_returns_none(self, data_dir):
        dm = DataManager(str(data_dir))
        assert dm.get_swimmer(999) is None
        assert dm.get_instructor(999) is None

    def test_flagged_matches(self, data_dir):
        dm = DataManager(str(data_dir))
        flagged = dm.get_flagged_matches(threshold=50)
        assert len(flagged) == 1
        assert flagged[0]["confidence"] == 45.0

    def test_all_instructors(self, data_dir):
        dm = DataManager(str(data_dir))
        instructors = dm.all_instructors()
        assert len(instructors) == 2

    def test_confidence_distribution_buckets(self, data_dir):
        dm = DataManager(str(data_dir))
        dist = dm.get_confidence_distribution()
        assert len(dist["buckets"]) == 10
        assert len(dist["counts"]) == 10
        assert sum(dist["counts"]) == len(dm.matches)

    def test_type_breakdown(self, data_dir):
        dm = DataManager(str(data_dir))
        breakdown = dm.get_type_breakdown()
        assert "continuity" in breakdown
        assert "compatibility" in breakdown
        assert "individual" in breakdown
        assert "pair" in breakdown
        total_format = breakdown["individual"] + breakdown["pair"]
        assert total_format == len(dm.matches)

    def test_flagged_matches_with_reasons(self, data_dir):
        dm = DataManager(str(data_dir))
        flagged = dm.get_flagged_matches_with_reasons(threshold=50)
        assert isinstance(flagged, list)
        for f in flagged:
            assert "idx" in f
            assert "swimmer_name" in f
            assert "flag_reason" in f

    def test_flagged_includes_low_confidence(self, data_dir):
        """Test with a match that has confidence < 50."""
        dm = DataManager(str(data_dir))
        flagged = dm.get_flagged_matches_with_reasons(threshold=50)
        assert len(flagged) >= 1
        assert any("low confidence" in f["flag_reason"].lower() for f in flagged)

    def test_flagged_includes_review_flags_even_with_high_confidence(self, tmp_path, sample_profiles):
        result = {
            "ok": True,
            "summary": {"classes": 1, "assigned_swimmers": 1, "unassigned_swimmers": 0, "avg_confidence": 90.0},
            "matches": [
                {
                    "type": "individual",
                    "match_type": "continuity",
                    "swimmer_id": 1,
                    "swimmer_name": "Hannah Sullivan",
                    "instructor_id": 11,
                    "instructor_name": "Savannah Wilkerson",
                    "confidence": 90.0,
                    "compatibility_score": 90.0,
                    "reason": "Continuity: 1 session(s) together",
                    "flag_codes": [
                        "continuity_overrides_adapted_capability",
                        "manual_policy_review_required",
                    ],
                    "review_severity": "urgent",
                }
            ],
            "unassigned": [],
        }
        (tmp_path / "result.json").write_text(json.dumps(result))
        (tmp_path / "profiles.json").write_text(json.dumps(sample_profiles))

        dm = DataManager(str(tmp_path))

        flagged = dm.get_flagged_matches_with_reasons(threshold=50)
        assert len(flagged) == 1
        assert flagged[0]["review_severity"] == "urgent"
        assert "Adapted capability override" in flagged[0]["flag_reason"]
        assert "Manual policy review required" in flagged[0]["flag_reason"]
