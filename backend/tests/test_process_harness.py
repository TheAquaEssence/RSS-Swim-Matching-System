import socket
from pathlib import Path

import pytest

from backend.process_harness import LOOPBACK_HOST, BackendProcessHarness, BackendStartError


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _runtime_tree_state() -> dict[str, tuple[int, int]]:
    candidates = [
        REPOSITORY_ROOT / "data" / "aqua_essence.db",
        REPOSITORY_ROOT / "settings",
        REPOSITORY_ROOT / "jobs",
        REPOSITORY_ROOT / "logs",
    ]
    state = {}
    for candidate in candidates:
        if candidate.is_file():
            stat = candidate.stat()
            state[str(candidate.relative_to(REPOSITORY_ROOT))] = (stat.st_mtime_ns, stat.st_size)
        elif candidate.is_dir():
            for path in candidate.rglob("*"):
                if path.is_file():
                    stat = path.stat()
                    state[str(path.relative_to(REPOSITORY_ROOT))] = (stat.st_mtime_ns, stat.st_size)
    return state


def test_real_backend_process_start_readiness_auth_restart_and_shutdown(tmp_path):
    app_data_dir = tmp_path / "desktop-user-data"
    harness = BackendProcessHarness(app_data_dir, repository_root=REPOSITORY_ROOT)
    source_runtime_state = _runtime_tree_state()

    try:
        harness.start()
        first_pid = harness.process.pid
        first_token = harness.launch_token

        assert harness.request("/api/ready", authenticated=False).json() == {
            "ok": True,
            "status": "ready",
        }
        assert harness.request("/api/settings", authenticated=False).status == 401
        assert harness.request("/api/settings").status == 200
        assert harness.launch_token not in harness.captured_output

        harness.restart()
        assert harness.process.pid != first_pid
        assert harness.launch_token != first_token
        assert harness.port is not None
        assert harness.request("/api/ready", authenticated=False).status == 200
    finally:
        harness.stop()

    assert harness.process.poll() is not None
    assert (app_data_dir / "data" / "aqua_essence.db").is_file()
    assert (app_data_dir / "settings" / "user_settings.json").is_file()
    assert (app_data_dir / "jobs").is_dir()
    assert (app_data_dir / "logs").is_dir()
    assert _runtime_tree_state() == source_runtime_state


def test_start_failure_includes_child_diagnostics_without_exposing_token(tmp_path):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
        occupied.bind((LOOPBACK_HOST, 0))
        occupied.listen()
        port = occupied.getsockname()[1]
        harness = BackendProcessHarness(
            tmp_path / "failed-launch-data",
            repository_root=REPOSITORY_ROOT,
            requested_port=port,
            startup_timeout=5,
        )

        with pytest.raises(BackendStartError) as captured:
            harness.start()

    error = captured.value
    assert error.exit_code is not None
    assert error.output
    assert "Backend output:" in str(error)
    assert harness.launch_token not in error.output
    assert harness.launch_token not in str(error)
    harness.stop()


def test_packaged_launch_command_uses_executable_without_system_python(tmp_path):
    executable = tmp_path / "package" / "aqua-backend.exe"
    harness = BackendProcessHarness(
        tmp_path / "user-data",
        backend_executable=executable,
    )

    command, working_directory = harness._build_launch_command(45678)

    assert command == [
        str(executable.resolve()),
        "--port",
        "45678",
        "--no-browser",
        "--data-dir",
        str((tmp_path / "user-data").resolve()),
    ]
    assert working_directory == executable.resolve().parent
