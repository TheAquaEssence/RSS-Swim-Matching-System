import json
from pathlib import Path

import pytest

from core.aqua_logging import reset_logging_state
from core.profiles import generate_profiles


def _read_records(log_root: Path):
    component_dir = log_root / "core.profiles.generate_profiles"
    records = []
    for path in sorted(component_dir.glob("*.jsonl*")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
    return records


def _write_csv(path: Path, header: str, row: str):
    path.write_text(f"{header}\n{row}\n", encoding="utf-8")


def test_generate_profiles_logs_success(tmp_path, monkeypatch):
    log_root = tmp_path / "logs"
    monkeypatch.setenv("AQUA_LOG_DIR", str(log_root))
    reset_logging_state()

    swimmers = tmp_path / "swimmers.csv"
    instructors = tmp_path / "instructors.csv"
    _write_csv(swimmers, "swimmer_id,first_name,last_name,swimmer_type_id,skill_level,age,has_special_needs,notes,pair_id", "1,Alice,Smith,1,3,7,0,,")
    _write_csv(instructors, "instructor_id,first_name,last_name,primary_color_id,secondary_color_id,primary_style_id,secondary_style_id,is_team_captain,can_teach_NL,can_teach_babies,can_teach_adults,can_teach_adapted", "10,Coach,One,1,2,1,2,0,1,1,0,1")
    request_path = tmp_path / "request.json"
    request_path.write_text(
        json.dumps(
            {
                "job_id": "job_test",
                "data": {
                    "swimmers": str(swimmers),
                    "instructors": str(instructors),
                    "reference": {},
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(generate_profiles.sys, "argv", ["generate_profiles", str(request_path), str(tmp_path)])
    assert generate_profiles.main() == 0

    records = _read_records(log_root)
    started = next(record for record in records if record["event"] == "profiles_generation_started")
    completed = next(record for record in records if record["event"] == "profiles_generation_completed")
    assert started["job_id"] == "job_test"
    assert completed["job_id"] == "job_test"
    assert (tmp_path / "profiles.json").exists()


def test_generate_profiles_logs_failure(tmp_path, monkeypatch):
    log_root = tmp_path / "logs"
    monkeypatch.setenv("AQUA_LOG_DIR", str(log_root))
    reset_logging_state()

    swimmers = tmp_path / "swimmers.csv"
    instructors = tmp_path / "instructors.csv"
    _write_csv(swimmers, "swimmer_id,first_name,last_name,swimmer_type_id,skill_level,age,has_special_needs,notes,pair_id", "1,Alice,Smith,1,3,7,0,,")
    _write_csv(instructors, "instructor_id,first_name,last_name,primary_color_id,secondary_color_id,primary_style_id,secondary_style_id,is_team_captain,can_teach_NL,can_teach_babies,can_teach_adults,can_teach_adapted", "10,Coach,One,1,2,1,2,0,1,1,0,1")
    request_path = tmp_path / "request.json"
    request_path.write_text(
        json.dumps(
            {
                "job_id": "job_test",
                "data": {
                    "swimmers": str(swimmers),
                    "instructors": str(instructors),
                    "reference": {},
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(generate_profiles.sys, "argv", ["generate_profiles", str(request_path), str(tmp_path)])
    monkeypatch.setattr(generate_profiles, "write_profiles_json", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))

    with pytest.raises(RuntimeError, match="boom"):
        generate_profiles.main()

    failure = next(record for record in _read_records(log_root) if record["event"] == "profiles_generation_failed")
    assert failure["exception_type"] == "RuntimeError"
    assert failure["job_id"] == "job_test"
