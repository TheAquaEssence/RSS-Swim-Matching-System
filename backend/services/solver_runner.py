"""Solver process management, extracted from backend/server.py (Phase 3).

Runs the CP-SAT solver entry script in a separate process (timeout and
crash isolation) and turns its result.json into a validated payload.
Callers supply a logger; this module has no dependency on the server.
"""
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

from backend.solver_worker import SOLVER_WORKER_ARGUMENT
from core.aqua_logging import tail_for_log

SOLVER_TIMEOUT_SECONDS = 300
TERMINATION_GRACE_SECONDS = 2.0


class SolverProcessRegistry:
    """Track solver children so host shutdown cannot leave them orphaned."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._processes: set[subprocess.Popen] = set()

    def add(self, process: subprocess.Popen) -> None:
        with self._lock:
            self._processes.add(process)

    def discard(self, process: subprocess.Popen) -> None:
        with self._lock:
            self._processes.discard(process)

    def terminate_all(self, logger, grace_seconds: float = TERMINATION_GRACE_SECONDS) -> None:
        """Terminate active children, escalating to kill after a short grace period."""

        with self._lock:
            processes = tuple(self._processes)

        for process in processes:
            if process.poll() is None:
                process.terminate()

        deadline = time.monotonic() + grace_seconds
        for process in processes:
            if process.poll() is not None:
                self.discard(process)
                continue
            try:
                process.wait(timeout=max(0.0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                logger.warning(
                    "Solver ignored graceful termination; forcing exit",
                    extra={"event": "solver_subprocess_forced_termination"},
                )
                process.kill()
                process.wait()
            finally:
                self.discard(process)


ACTIVE_SOLVER_PROCESSES = SolverProcessRegistry()


def _stop_process(process: subprocess.Popen, logger) -> tuple[bytes, bytes]:
    """Stop one child and collect its output without leaving a zombie process."""

    process.terminate()
    try:
        return process.communicate(timeout=TERMINATION_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        logger.warning(
            "Solver ignored graceful termination; forcing exit",
            extra={"event": "solver_subprocess_forced_termination"},
        )
        process.kill()
        return process.communicate()


def build_solver_command(
    executable: Path,
    request_path: Path,
    result_path: Path,
    *,
    frozen: bool | None = None,
    python_executable: str | None = None,
) -> list[str]:
    """Build the shell-free solver command for source or frozen execution.

    In source mode, ``executable`` is the production ``solver_wrapper.py``.
    A frozen backend has no independent Python interpreter or wrapper script,
    so it spawns its own executable in the worker mode handled by ``start.py``.
    Optional overrides keep both branches directly testable.
    """

    runtime_executable = python_executable or sys.executable
    frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    if frozen:
        return [
            runtime_executable,
            SOLVER_WORKER_ARGUMENT,
            str(request_path),
            str(result_path),
        ]
    return [runtime_executable, str(executable), str(request_path), str(result_path)]


def run_solver(executable: Path, request_path: Path, result_path: Path, logger) -> None:
    """Run the Python solver entry point in an isolated child process."""
    cmd = build_solver_command(executable, request_path, result_path)

    started = time.perf_counter()
    logger.info("Launching solver subprocess", extra={"event": "solver_subprocess_started"})

    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    ACTIVE_SOLVER_PROCESSES.add(process)
    try:
        stdout, stderr = process.communicate(timeout=SOLVER_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as exc:
        stdout, stderr = _stop_process(process, logger)
        combined = "\n".join(filter(None, [
            stdout.decode(errors="replace").strip() if stdout else "",
            stderr.decode(errors="replace").strip() if stderr else "",
        ]))
        logger.error("Solver subprocess timed out", extra={
            "event": "solver_subprocess_timeout",
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "subprocess_output_tail": tail_for_log(combined),
        })
        raise RuntimeError("Solver timed out") from exc
    finally:
        ACTIVE_SOLVER_PROCESSES.discard(process)

    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    if process.returncode != 0:
        stderr = stderr.decode(errors="replace").strip()
        stdout = stdout.decode(errors="replace").strip()
        logger.error("Solver subprocess failed", extra={
            "event": "solver_subprocess_failed",
            "duration_ms": duration_ms,
            "subprocess_output_tail": tail_for_log("\n".join(filter(None, [stderr, stdout]))),
        })
        raise RuntimeError("Solver execution failed")

    logger.info("Solver subprocess completed", extra={
        "event": "solver_subprocess_completed",
        "duration_ms": duration_ms,
    })


def read_solver_result(result_path: Path, logger) -> str:
    try:
        result_text = result_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        logger.error("Missing result.json after solver run", extra={"event": "solver_result_missing"})
        raise RuntimeError("Solver produced no result.json") from exc
    except (OSError, UnicodeError) as exc:
        logger.error("Failed to read result.json", extra={
            "event": "solver_result_read_failed",
            "exception": str(exc),
        })
        raise RuntimeError("Failed to read result.json") from exc

    if not result_text.strip():
        logger.error("Solver produced empty result.json", extra={"event": "solver_result_empty"})
        raise RuntimeError("Solver produced empty result.json")
    return result_text


def parse_and_validate_solver_result(result_text: str, logger) -> dict:
    try:
        result = json.loads(result_text)
    except json.JSONDecodeError as exc:
        logger.error("Invalid JSON in result.json", extra={"event": "solver_result_invalid_json", "exception": str(exc)})
        raise RuntimeError("Solver produced invalid result.json") from exc

    if not isinstance(result, dict) or not isinstance(result.get("ok"), bool):
        raise RuntimeError("Solver produced invalid result.json")

    if result["ok"]:
        try:
            if not isinstance(result.get("result_files"), dict):
                raise ValueError("result_files must be an object")
            if not isinstance(result.get("matches"), list):
                raise ValueError("matches must be an array")
            if not isinstance(result.get("unassigned"), list):
                raise ValueError("unassigned must be an array")
        except ValueError as exc:
            raise RuntimeError("Solver produced invalid result.json") from exc
    else:
        error = result.get("error")
        if not isinstance(error, str) or not error.strip():
            raise RuntimeError("Solver produced invalid result.json")

    return result
