"""C2: categorized generate failures (error_kind) for curated UI rendering."""
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import backend.server as server


@pytest.fixture
def client():
    return TestClient(server.app)


@pytest.fixture(autouse=True)
def reset_generate_rate_limit(monkeypatch):
    monkeypatch.setattr(server.application_services.state, "generate_in_progress", False)
    monkeypatch.setattr(server.application_services.state, "last_generate_started_at", float("-inf"))


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


def _generate_patches(jobs_dir, solvers_dir, test_settings):
    return (
        patch.object(server.application_services.paths, "solvers_dir", solvers_dir),
        patch.object(server.application_services.paths, "jobs_dir", jobs_dir),
        patch("backend.server.generate_job_id", return_value="job_test"),
        patch("backend.server.save_settings"),
        patch.object(server.application_services.state, "settings", test_settings),
    )


def test_run_solver_timeout_raises_distinct_message():
    process = type("Process", (), {})()
    process.communicate = lambda timeout=None: (
        (_ for _ in ()).throw(subprocess.TimeoutExpired(cmd="solver", timeout=timeout))
        if timeout == 300 else (b"", b"")
    )
    process.terminate = lambda: None
    process.kill = lambda: None
    process.returncode = None
    with patch("backend.services.solver_runner.subprocess.Popen", return_value=process):
        with pytest.raises(RuntimeError, match="^Solver timed out$"):
            server.run_solver(Path("solver.py"), Path("request.json"), Path("result.json"))


def test_generate_timeout_returns_solver_timeout_kind(client, tmp_path):
    jobs_dir, solvers_dir, test_settings = _make_generate_env(tmp_path)

    patches = _generate_patches(jobs_dir, solvers_dir, test_settings)
    with patches[0], patches[1], patches[2], patches[3], patches[4], \
         patch("backend.server.run_solver", side_effect=RuntimeError("Solver timed out")):
        resp = client.post("/api/generate")

    assert resp.status_code == 500
    assert resp.json() == {"ok": False, "error": "Solver timed out", "error_kind": "solver_timeout"}


def test_generate_solver_crash_returns_solver_failed_kind(client, tmp_path):
    jobs_dir, solvers_dir, test_settings = _make_generate_env(tmp_path)

    patches = _generate_patches(jobs_dir, solvers_dir, test_settings)
    with patches[0], patches[1], patches[2], patches[3], patches[4], \
         patch("backend.server.run_solver", side_effect=RuntimeError("Solver execution failed")):
        resp = client.post("/api/generate")

    assert resp.status_code == 500
    assert resp.json() == {"ok": False, "error": "Solver execution failed", "error_kind": "solver_failed"}


def test_generate_missing_input_file_returns_400(client, tmp_path):
    # validate_and_fixup normally swaps a vanished selection back to the
    # default file; bypass it to exercise the race where the file disappears
    # after validation but before the solver run.
    jobs_dir, solvers_dir, test_settings = _make_generate_env(tmp_path)
    test_settings["last_selected_files"]["swimmers"] = str(tmp_path / "gone_swimmers.csv")

    patches = _generate_patches(jobs_dir, solvers_dir, test_settings)
    with patches[0], patches[1], patches[2], patches[3], patches[4], \
         patch("backend.server.validate_and_fixup", lambda s: None):
        with TestClient(server.create_app(server.application_services)) as isolated_client:
            resp = isolated_client.post("/api/generate")

    assert resp.status_code == 400
    body = resp.json()
    assert body["ok"] is False
    assert body["error_kind"] == "missing_input_file"
    assert "gone_swimmers.csv" in body["error"]


def test_generate_empty_input_file_returns_400(client, tmp_path):
    jobs_dir, solvers_dir, test_settings = _make_generate_env(tmp_path)
    empty_classes = tmp_path / "empty_classes.csv"
    empty_classes.write_text("class_id,name\n", encoding="utf-8")  # header only
    test_settings["last_selected_files"]["classes"] = str(empty_classes)

    patches = _generate_patches(jobs_dir, solvers_dir, test_settings)
    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        resp = client.post("/api/generate")

    assert resp.status_code == 400
    body = resp.json()
    assert body["ok"] is False
    assert body["error_kind"] == "empty_input_file"
    assert "empty_classes.csv" in body["error"]
