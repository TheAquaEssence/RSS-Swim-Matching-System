import pytest
from unittest.mock import MagicMock, patch
from frontend.xai_dashboard.what_if import WhatIfEngine


@pytest.fixture
def mock_data_manager():
    dm = MagicMock()
    dm.all_instructors.return_value = [
        {"instructor_id": 10, "name": "Coach A", "primary_color_id": 1,
         "secondary_color_id": 2, "primary_style_id": 1, "primary_style_name": "Motivational",
         "secondary_style_id": 3},
        {"instructor_id": 11, "name": "Coach B", "primary_color_id": 3,
         "secondary_color_id": 4, "primary_style_id": 6, "primary_style_name": "Do-It-Alls",
         "secondary_style_id": 2},
    ]
    dm.get_swimmer.return_value = {
        "swimmer_id": 1, "name": "Alice", "swimmer_type_id": 2,
        "skill_level": 3, "age": 7, "has_special_needs": False
    }
    dm.get_instructor.return_value = {
        "instructor_id": 10, "name": "Coach A", "primary_color_id": 1,
        "secondary_color_id": 2, "primary_style_id": 1, "primary_style_name": "Motivational",
        "secondary_style_id": 3
    }
    return dm


class TestSwapExplorer:
    def test_swap_returns_ranked_alternatives(self, mock_data_manager):
        engine = WhatIfEngine(mock_data_manager, source_dir="data/source")
        result = engine.swap_explore(swimmer_id=1, current_instructor_id=10)
        assert "current" in result
        assert "alternatives" in result
        assert isinstance(result["alternatives"], list)

    def test_swap_current_score_present(self, mock_data_manager):
        engine = WhatIfEngine(mock_data_manager, source_dir="data/source")
        result = engine.swap_explore(swimmer_id=1, current_instructor_id=10)
        assert "score" in result["current"]
        assert "instructor_name" in result["current"]

    def test_swap_alternatives_sorted_descending(self, mock_data_manager):
        engine = WhatIfEngine(mock_data_manager, source_dir="data/source")
        result = engine.swap_explore(swimmer_id=1, current_instructor_id=10)
        scores = [a["score"] for a in result["alternatives"]]
        assert scores == sorted(scores, reverse=True)


class TestWeightTuner:
    def test_tune_returns_rescored_matches(self, mock_data_manager):
        mock_data_manager.matches = [
            {"type": "individual", "swimmer_id": 1, "instructor_id": 10,
             "compatibility_score": 75.0, "confidence": 80.0}
        ]
        engine = WhatIfEngine(mock_data_manager, source_dir="data/source")
        result = engine.tune_weights(weights={"color_vs_style": 0.7})
        assert len(result) == 1
        assert "original_score" in result[0]
        assert "tuned_score" in result[0]


class TestConstraintRelaxer:
    def test_relax_returns_new_eligible(self, mock_data_manager):
        engine = WhatIfEngine(mock_data_manager, source_dir="data/source")
        result = engine.relax_constraint(swimmer_id=1, constraint="adapted")
        assert "eligible_instructors" in result
        assert isinstance(result["eligible_instructors"], list)
