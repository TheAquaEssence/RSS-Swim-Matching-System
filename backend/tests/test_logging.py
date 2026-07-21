import json
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import backend.server as server
from core.aqua_logging import reset_logging_state


def _make_generate_env(tmp_path):
    jobs_dir = tmp_path / "jobs"
    solvers_dir = tmp_path / "solvers"
    solver_dir = solvers_dir / "python_cpsat"
    solver_dir.mkdir(parents=True)
    jobs_dir.mkdir()

    (solver_dir / "solver_wrapper.py").write_text("# fake solver\n", encoding="utf-8")

    classes_path = tmp_path / "classes.csv"
    classes_path.write_text("class_id\n1\n", encoding="utf-8")

    test_settings = server.make_default_settings()
    test_settings["last_selected_files"]["classes"] = str(classes_path)
    return jobs_dir, solvers_dir, test_settings


def _read_records(log_root: Path):
    component_dir = log_root / "backend.server"
    records = []
    for path in sorted(component_dir.glob("*.jsonl*")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
    return records


def test_generate_writes_correlated_request_and_job_logs(tmp_path, monkeypatch):
    log_root = tmp_path / "logs"
    monkeypatch.setenv("AQUA_LOG_DIR", str(log_root))
    reset_logging_state()
    server._logger = None

    jobs_dir, solvers_dir, test_settings = _make_generate_env(tmp_path)

    def fake_run_solver(executable, request_path, output_path):
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
                    "matches": [],
                    "unassigned": [],
                }
            ),
            encoding="utf-8",
        )
        (output_path.parent / "profiles.json").write_text(
            json.dumps({"swimmers": {}, "instructors": {}}),
            encoding="utf-8",
        )

    services = server.create_application_services(
        initial_settings=test_settings,
        persist_settings=False,
    )
    with patch.object(services.paths, "solvers_dir", solvers_dir), \
         patch.object(services.paths, "jobs_dir", jobs_dir), \
         patch("backend.server.generate_job_id", return_value="job_test"), \
         patch("backend.server.run_solver", side_effect=fake_run_solver), \
         patch("backend.server.save_settings"):
        with TestClient(server.create_app(services)) as client:
            response = client.post("/api/generate")

    assert response.status_code == 200
    records = _read_records(log_root)
    request_started = next(record for record in records if record["event"] == "request_started" and record["route"] == "/api/generate")
    generate_started = next(record for record in records if record["event"] == "generate_started")
    generate_completed = next(record for record in records if record["event"] == "generate_completed")
    request_completed = next(record for record in records if record["event"] == "request_completed" and record["route"] == "/api/generate")

    assert generate_started["job_id"] == "job_test"
    assert generate_completed["job_id"] == "job_test"
    assert request_completed["job_id"] == "job_test"
    assert generate_completed["solver_id"] == "python_cpsat"
    assert request_started["request_id"] == generate_started["request_id"] == generate_completed["request_id"] == request_completed["request_id"]
