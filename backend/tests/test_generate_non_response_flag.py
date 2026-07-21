import json
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import backend.server as server


def _make_env(tmp_path: Path):
    jobs_dir = tmp_path / "jobs"
    solvers_dir = tmp_path / "solvers"
    solver_dir = solvers_dir / "python_cpsat"
    solver_dir.mkdir(parents=True)
    jobs_dir.mkdir()

    (solver_dir / "solver_wrapper.py").write_text("# fake solver\n", encoding="utf-8")

    classes_path = tmp_path / "classes.csv"
    classes_path.write_text("class_id\n1\n", encoding="utf-8")

    swimmers_path = tmp_path / "swimmers.csv"
    swimmers_path.write_text(
        "swimmer_id,first_name,last_name,swimmer_type_id,skill_level,age,has_special_needs,notes,pair_id\n"
        "1,Alice,Smith,0,3,7,0,,\n",
        encoding="utf-8",
    )

    instructors_path = tmp_path / "instructors.csv"
    instructors_path.write_text(
        "instructor_id,first_name,last_name,primary_color_id,secondary_color_id,primary_style_id,secondary_style_id,"
        "is_team_captain,can_teach_NL,can_teach_babies,can_teach_adults,can_teach_adapted\n"
        "10,Coach,One,1,2,1,2,0,1,1,1,1\n",
        encoding="utf-8",
    )

    swimmer_types_path = tmp_path / "swimmer_types.csv"
    swimmer_types_path.write_text(
        "swimmer_type_id,swimmer_type_name\n"
        "1,The Nervous/New\n"
        "8,Non-Response / Unknown\n",
        encoding="utf-8",
    )

    test_settings = server.make_default_settings()
    test_settings["last_selected_files"]["classes"] = str(classes_path)
    test_settings["last_selected_files"]["swimmers"] = str(swimmers_path)
    test_settings["last_selected_files"]["instructors"] = str(instructors_path)
    test_settings["last_selected_files"]["swimmer_types"] = str(swimmer_types_path)
    return jobs_dir, solvers_dir, test_settings


def test_generate_adds_non_response_review_flag(tmp_path):
    jobs_dir, solvers_dir, test_settings = _make_env(tmp_path)

    def fake_run_solver(_executable, _request_path, output_path):
        output_path.write_text(
            json.dumps(
                {
                    "ok": True,
                    "result_files": {"classes_filled": "jobs/job_test/classes_filled.csv"},
                    "summary": {
                        "classes": 1,
                        "assigned_swimmers": 1,
                        "unassigned_swimmers": 0,
                        "avg_confidence": 80.0,
                    },
                    "matches": [
                        {
                            "type": "individual",
                            "swimmer_id": 1,
                            "swimmer_name": "Alice Smith",
                            "instructor_id": 10,
                            "instructor_name": "Coach One",
                            "confidence": 80.0,
                            "compatibility_score": 75.0,
                            "match_type": "compatibility",
                            "reason": "Compatibility (75.0%)",
                        }
                    ],
                    "unassigned": [],
                }
            ),
            encoding="utf-8",
        )

    with patch.object(server.application_services.paths, "solvers_dir", solvers_dir), \
         patch.object(server.application_services.paths, "jobs_dir", jobs_dir), \
         patch("backend.server.generate_job_id", return_value="job_test"), \
         patch("backend.server.run_solver", side_effect=fake_run_solver), \
         patch("backend.server.save_settings"), \
         patch.object(server.application_services.state, "settings", test_settings):
        with TestClient(server.app) as client:
            response = client.post("/api/generate")

    assert response.status_code == 200
    match = response.json()["matches"][0]
    assert "non_response_swimmer_type" in match["flag_codes"]
    assert match["review_action"] == "update_swimmer_type"
    assert match["review_severity"] == "review"


def test_generate_adds_default_instructor_profile_review_flag(tmp_path):
    jobs_dir, solvers_dir, test_settings = _make_env(tmp_path)
    # Use a known non-non-response swimmer_type_id so only default_instructor_profile flag fires
    swimmers_path = Path(test_settings["last_selected_files"]["swimmers"])
    swimmers_path.write_text(
        "swimmer_id,first_name,last_name,swimmer_type_id,skill_level,age,has_special_needs,notes,pair_id\n"
        "1,Alice,Smith,1,3,7,0,,\n",
        encoding="utf-8",
    )
    instructors_path = Path(test_settings["last_selected_files"]["instructors"])
    instructors_path.write_text(
        "instructor_id,first_name,last_name,primary_color_id,secondary_color_id,primary_style_id,secondary_style_id,"
        "is_team_captain,can_teach_NL,can_teach_babies,can_teach_adults,can_teach_adapted\n"
        "10,Coach,One,,,,,0,,,,\n",
        encoding="utf-8",
    )
    test_settings["default_instructor_profile"] = {
        "primary_color_id": 4,
        "secondary_color_id": 3,
        "primary_style_id": 2,
        "secondary_style_id": 1,
        "is_team_captain": False,
        "can_teach_NL": False,
        "can_teach_babies": False,
        "can_teach_adults": True,
        "can_teach_adapted": False,
    }

    def fake_run_solver(_executable, request_path, output_path):
        request_data = json.loads(request_path.read_text(encoding="utf-8"))
        resolved_instructors = Path(request_data["data"]["instructors"])
        if not resolved_instructors.is_absolute():
            resolved_instructors = Path(request_data["app_root"]) / resolved_instructors
        normalized_text = resolved_instructors.read_text(encoding="utf-8")
        assert "used_default_profile" in normalized_text
        assert ",4,3,2,1,0,0,0,1,0,1" in normalized_text.replace("\n", ",")

        output_path.write_text(
            json.dumps(
                {
                    "ok": True,
                    "result_files": {"classes_filled": "jobs/job_test/classes_filled.csv"},
                    "summary": {
                        "classes": 1,
                        "assigned_swimmers": 1,
                        "unassigned_swimmers": 0,
                        "avg_confidence": 80.0,
                    },
                    "matches": [
                        {
                            "type": "individual",
                            "swimmer_id": 1,
                            "swimmer_name": "Alice Smith",
                            "instructor_id": 10,
                            "instructor_name": "Coach One",
                            "confidence": 80.0,
                            "compatibility_score": 75.0,
                            "match_type": "compatibility",
                            "reason": "Compatibility (75.0%)",
                        }
                    ],
                    "unassigned": [],
                }
            ),
            encoding="utf-8",
        )

    with patch.object(server.application_services.paths, "solvers_dir", solvers_dir), \
         patch.object(server.application_services.paths, "jobs_dir", jobs_dir), \
         patch("backend.server.generate_job_id", return_value="job_test"), \
         patch("backend.server.run_solver", side_effect=fake_run_solver), \
         patch("backend.server.save_settings"), \
         patch.object(server.application_services.state, "settings", test_settings), \
         patch.object(server.application_services.state, "last_generate_started_at", 0.0), \
         patch.object(server.application_services.state, "generate_in_progress", False):
        with TestClient(server.app) as client:
            response = client.post("/api/generate")

    assert response.status_code == 200
    match = response.json()["matches"][0]
    assert "default_instructor_profile" in match["flag_codes"]
    assert match["review_action"] == "update_instructor_profile"
    assert match["review_severity"] == "review"
