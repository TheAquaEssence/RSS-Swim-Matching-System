"""Security regression tests for backend/server.py."""
import json
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import backend.server as server


# ── C2: Job IDs must be cryptographically random ──────────────────────────

def test_job_id_is_hex_and_unpredictable():
    id1 = server.generate_job_id()
    id2 = server.generate_job_id()
    assert re.fullmatch(r"job_[0-9a-f]{32}", id1), f"Bad format: {id1}"
    assert id1 != id2, "Two consecutive job IDs must differ"


# ── M7: Atomic settings write ─────────────────────────────────────────────

def test_save_settings_is_atomic(tmp_path):
    """After save, no .tmp file should remain and content should be valid."""
    settings_path = tmp_path / "user_settings.json"
    with patch("backend.server.SETTINGS_PATH", settings_path):
        server.save_settings({"use_db_instructors": True})
    assert settings_path.exists()
    assert not list(tmp_path.glob("*.tmp")), "Temp file should be cleaned up"
    data = json.loads(settings_path.read_text())
    assert data["use_db_instructors"] is True


# ── M1: Path traversal blocked by is_relative_to ─────────────────────────

def test_path_traversal_prefix_collision():
    """A sibling dir whose name starts with the target dir name must be blocked."""
    # 'jobs_extra' starts with 'jobs' but is NOT relative to 'jobs'
    target = Path("/app/jobs_extra/secret.json").resolve()
    base = Path("/app/jobs").resolve()
    assert not target.is_relative_to(base)


def test_parse_port_env_accepts_valid_port(monkeypatch):
    monkeypatch.setenv("PORT", "9012")
    assert server.parse_port_env() == 9012


def test_parse_port_env_rejects_invalid_port(monkeypatch):
    monkeypatch.setenv("PORT", "70000")
    with pytest.raises(ValueError, match="^PORT must be an integer between 0 and 65535$"):
        server.parse_port_env()


def test_zero_port_requests_ephemeral_port(monkeypatch):
    monkeypatch.setenv("PORT", "0")
    monkeypatch.setattr(server, "reserve_ephemeral_port", lambda: 9123)
    assert server.find_listen_port() == 9123


def test_find_listen_port_falls_back_to_ephemeral(monkeypatch):
    monkeypatch.setattr(server, "get_candidate_ports", lambda: [8787, 8788])
    monkeypatch.setattr(server, "reserve_ephemeral_port", lambda: 9123)

    class BusySocket:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def connect_ex(self, address):
            return 0

    monkeypatch.setattr(server.socket, "socket", lambda *args, **kwargs: BusySocket())
    assert server.find_listen_port() == 9123


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


def test_generate_handles_result_json_disappearing_before_read(client, tmp_path):
    jobs_dir, solvers_dir, test_settings = _make_generate_env(tmp_path)
    result_path = jobs_dir / "job_test" / "result.json"
    original_read_text = server.Path.read_text

    def fake_run_solver(executable, request_path, output_path):
        output_path.write_text('{"ok": true}', encoding="utf-8")

    def flaky_read_text(self, *args, **kwargs):
        if self == result_path:
            if self.exists():
                self.unlink()
            raise FileNotFoundError(self)
        return original_read_text(self, *args, **kwargs)

    with patch.object(server.application_services.paths, "solvers_dir", solvers_dir), \
         patch.object(server.application_services.paths, "jobs_dir", jobs_dir), \
         patch("backend.server.generate_job_id", return_value="job_test"), \
         patch("backend.server.run_solver", side_effect=fake_run_solver), \
         patch("backend.server.save_settings"), \
         patch.object(server.application_services.state, "settings", test_settings), \
         patch.object(server.Path, "read_text", autospec=True, side_effect=flaky_read_text):
        resp = client.post("/api/generate")

    assert resp.status_code == 500
    assert resp.json() == {"ok": False, "error": "Solver produced no result.json", "error_kind": "solver_failed"}


def test_build_request_json_includes_explicit_app_root():
    payload = json.loads(server.build_request_json(server.make_default_settings(), "job_test"))
    assert payload["app_root"] == server.APP_ROOT.as_posix()


def test_generate_still_rejects_empty_result_json(client, tmp_path):
    jobs_dir, solvers_dir, test_settings = _make_generate_env(tmp_path)

    def fake_run_solver(executable, request_path, output_path):
        output_path.write_text(" \n", encoding="utf-8")

    with patch.object(server.application_services.paths, "solvers_dir", solvers_dir), \
         patch.object(server.application_services.paths, "jobs_dir", jobs_dir), \
         patch("backend.server.generate_job_id", return_value="job_test"), \
         patch("backend.server.run_solver", side_effect=fake_run_solver), \
         patch("backend.server.save_settings"), \
         patch.object(server.application_services.state, "settings", test_settings):
        resp = client.post("/api/generate")

    assert resp.status_code == 500
    assert resp.json() == {"ok": False, "error": "Solver produced empty result.json", "error_kind": "solver_failed"}


def test_generate_rejects_invalid_solver_result_json(client, tmp_path):
    jobs_dir, solvers_dir, test_settings = _make_generate_env(tmp_path)

    def fake_run_solver(executable, request_path, output_path):
        output_path.write_text("{not valid json", encoding="utf-8")

    with patch.object(server.application_services.paths, "solvers_dir", solvers_dir), \
         patch.object(server.application_services.paths, "jobs_dir", jobs_dir), \
         patch("backend.server.generate_job_id", return_value="job_test"), \
         patch("backend.server.run_solver", side_effect=fake_run_solver), \
         patch("backend.server.save_settings"), \
         patch.object(server.application_services.state, "settings", test_settings):
        resp = client.post("/api/generate")

    assert resp.status_code == 500
    assert resp.json() == {"ok": False, "error": "Solver produced invalid result.json", "error_kind": "solver_failed"}


def test_generate_rejects_solver_result_missing_required_fields(client, tmp_path):
    jobs_dir, solvers_dir, test_settings = _make_generate_env(tmp_path)

    def fake_run_solver(executable, request_path, output_path):
        output_path.write_text(json.dumps({"ok": True, "summary": {}, "matches": []}), encoding="utf-8")

    with patch.object(server.application_services.paths, "solvers_dir", solvers_dir), \
         patch.object(server.application_services.paths, "jobs_dir", jobs_dir), \
         patch("backend.server.generate_job_id", return_value="job_test"), \
         patch("backend.server.run_solver", side_effect=fake_run_solver), \
         patch("backend.server.save_settings"), \
         patch.object(server.application_services.state, "settings", test_settings):
        resp = client.post("/api/generate")

    assert resp.status_code == 500
    assert resp.json() == {"ok": False, "error": "Solver produced invalid result.json", "error_kind": "solver_failed"}


def test_run_solver_hides_stderr_exit_code_and_paths():
    with patch(
        "backend.services.solver_runner.subprocess.run",
        return_value=SimpleNamespace(
            returncode=7,
            stdout=b"traceback in stdout",
            stderr=b"boom from C:\\secret\\solver.py",
        ),
    ):
        with pytest.raises(RuntimeError, match="^Solver execution failed$"):
            server.run_solver(Path("solver.py"), Path("request.json"), Path("result.json"))


def test_generate_hides_missing_solver_path(client, tmp_path):
    jobs_dir, solvers_dir, test_settings = _make_generate_env(tmp_path)
    (solvers_dir / "python_cpsat" / "solver_wrapper.py").unlink()

    with patch.object(server.application_services.paths, "solvers_dir", solvers_dir), \
         patch.object(server.application_services.paths, "jobs_dir", jobs_dir), \
         patch("backend.server.generate_job_id", return_value="job_test"), \
         patch("backend.server.save_settings"), \
         patch.object(server.application_services.state, "settings", test_settings):
        resp = client.post("/api/generate")

    assert resp.status_code == 500
    assert resp.json() == {"ok": False, "error": "Solver is unavailable"}


def test_generate_rejects_when_generation_already_in_progress(client, tmp_path):
    jobs_dir, solvers_dir, test_settings = _make_generate_env(tmp_path)

    with patch.object(server.application_services.paths, "solvers_dir", solvers_dir), \
         patch.object(server.application_services.paths, "jobs_dir", jobs_dir), \
         patch("backend.server.save_settings"), \
         patch.object(server.application_services.state, "settings", test_settings), \
         patch.object(server.application_services.state, "generate_in_progress", True):
        resp = client.post("/api/generate")

    assert resp.status_code == 429
    assert resp.headers["Retry-After"] == "1"
    assert resp.json() == {
        "ok": False,
        "error": "Generate is rate-limited. Please wait and try again.",
    }


def test_generate_rejects_requests_inside_cooldown_window(client, tmp_path):
    jobs_dir, solvers_dir, test_settings = _make_generate_env(tmp_path)

    with patch.object(server.application_services.paths, "solvers_dir", solvers_dir), \
         patch.object(server.application_services.paths, "jobs_dir", jobs_dir), \
         patch("backend.server.save_settings"), \
         patch.object(server.application_services.state, "settings", test_settings), \
         patch("backend.server.time.monotonic", return_value=100.0), \
         patch.object(server.application_services.state, "last_generate_started_at", 97.2), \
         patch.object(server.application_services.state, "generate_in_progress", False):
        resp = client.post("/api/generate")

    assert resp.status_code == 429
    assert resp.headers["Retry-After"] == "3"
    assert resp.json() == {
        "ok": False,
        "error": "Generate is rate-limited. Please wait and try again.",
    }


# ── POST /api/launch_dashboard ────────────────────────────────────────────

def test_launch_dashboard_503_when_no_job_run(client):
    """Returns 503 when no solver job has completed yet."""
    with patch.object(server.application_services.state, "last_job_dir", ""):
        resp = client.post("/api/launch_dashboard")
    assert resp.status_code == 503
    assert resp.json()["ok"] is False


def test_launch_dashboard_returns_xai_url(client, tmp_path):
    """After a generate job, returns the /xai/ URL."""
    fake_job_dir = str(tmp_path / "job_abc123")
    with patch.object(server.application_services.state, "last_job_dir", fake_job_dir):
        resp = client.post("/api/launch_dashboard")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["url"].startswith("/xai/")
