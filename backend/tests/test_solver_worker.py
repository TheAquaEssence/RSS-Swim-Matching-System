import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from backend.services.solver_runner import build_solver_command
from backend.solver_worker import SOLVER_WORKER_ARGUMENT, run_solver_worker


WORKSPACE = Path(__file__).resolve().parents[2]


def test_source_solver_command_retains_wrapper_script_contract():
    command = build_solver_command(
        Path("solvers/python_cpsat/solver_wrapper.py"),
        Path("job/request.json"),
        Path("job/result.json"),
        frozen=False,
        python_executable="python-runtime",
    )

    assert command == [
        "python-runtime",
        str(Path("solvers/python_cpsat/solver_wrapper.py")),
        str(Path("job/request.json")),
        str(Path("job/result.json")),
    ]


def test_frozen_solver_command_self_dispatches_without_wrapper_path():
    command = build_solver_command(
        Path("ignored/solver_wrapper.py"),
        Path("job/request.json"),
        Path("job/result.json"),
        frozen=True,
        python_executable="AquaEssenceBackend.exe",
    )

    assert command == [
        "AquaEssenceBackend.exe",
        SOLVER_WORKER_ARGUMENT,
        str(Path("job/request.json")),
        str(Path("job/result.json")),
    ]


def test_worker_validates_arguments_before_importing_solver():
    with patch.dict(sys.modules, {"solvers.python_cpsat.solver_wrapper": None}):
        assert run_solver_worker([SOLVER_WORKER_ARGUMENT]) == 2


def test_start_worker_dispatch_invokes_production_wrapper_in_subprocess(tmp_path):
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    demo = WORKSPACE / "examples" / "demo" / "matching"
    request_path.write_text(
        json.dumps(
            {
                "job_id": "job_worker_contract",
                "app_root": str(WORKSPACE),
                "data": {
                    "classes": str(demo / "classes.csv"),
                    "swimmers": str(demo / "swimmers.csv"),
                    "instructors": str(demo / "instructors.csv"),
                    # Deliberately omit history/reference paths: the production
                    # wrapper must still dispatch and apply its normal defaults.
                    "historical_pairings": "",
                    "reference": {},
                },
                "config": {"enable_continuity": False},
            }
        ),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["AQUA_LOG_DIR"] = str(tmp_path / "logs")

    completed = subprocess.run(
        [
            sys.executable,
            str(WORKSPACE / "start.py"),
            SOLVER_WORKER_ARGUMENT,
            str(request_path),
            str(result_path),
        ],
        cwd=WORKSPACE,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["ok"] is True
    assert isinstance(result["matches"], list)
    assert isinstance(result["unassigned"], list)
