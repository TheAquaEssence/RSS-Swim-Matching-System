"""Opt-in GUI-level smoke for the packaged Electron shell (Windows only).

Launches ``Aqua Essence.exe`` from the unpacked build with a disposable
user-data directory (``AQUA_USER_DATA`` — honored by desktop/main.cjs), waits
for the bundled backend child to come up, then closes the shell gracefully and
verifies that neither the Electron process nor any backend/solver child
survives. No UI driver is involved; the window is never interacted with.

This is deliberately opt-in (it opens a real desktop window):

    python packaging/smoke/electron_gui_smoke.py

or via pytest with AQUA_SMOKE_GUI=1 (see backend/tests/test_packaged_smoke.py).

Note: builds produced before desktop/main.cjs learned AQUA_USER_DATA ignore
the override and use the real per-user profile; the report's
``user_data_isolated`` flag records whether the disposable directory was
actually honored so callers can keep that checklist item open.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from core.aqua_logging import configure_component_logger  # noqa: E402

_SMOKE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SMOKE_DIR))
from packaged_smoke import (  # noqa: E402
    BACKEND_IMAGE_NAME,
    ELECTRON_IMAGE_NAME,
    SmokeFailure,
    list_image_pids,
)
sys.path.remove(str(_SMOKE_DIR))

ELECTRON_APP_CANDIDATE = Path(".dist/electron/win-unpacked") / ELECTRON_IMAGE_NAME
BACKEND_START_TIMEOUT_SECONDS = 90.0
SHUTDOWN_TIMEOUT_SECONDS = 30.0

LOGGER = configure_component_logger("packaging_smoke")


@dataclass
class GuiSmokeReport:
    steps: list[str] = field(default_factory=list)
    backend_started_seconds: float = 0.0
    user_data_isolated: bool = False
    electron_exit_code: int | None = None

    def record(self, step: str) -> None:
        self.steps.append(step)
        LOGGER.info("GUI smoke step passed", extra={"event": "gui_smoke_step", "route": step})

    def summary(self) -> str:
        lines = [
            "packaged Electron GUI smoke",
            *(f"  ok: {step}" for step in self.steps),
            f"  backend child up after {self.backend_started_seconds:.1f}s",
            f"  disposable user-data honored: {self.user_data_isolated}",
            f"  Electron exit code={self.electron_exit_code}",
        ]
        return "\n".join(lines)


def find_electron_app(repository_root: Path | None = None) -> Path | None:
    path = (repository_root or _REPOSITORY_ROOT) / ELECTRON_APP_CANDIDATE
    return path if path.is_file() else None


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def _graceful_close(process: subprocess.Popen) -> None:
    """Ask the shell to quit via WM_CLOSE (taskkill without /F)."""

    subprocess.run(
        ["taskkill", "/PID", str(process.pid)],
        capture_output=True,
        timeout=15,
    )


def run_gui_smoke(electron_executable: Path, user_data_dir: Path) -> GuiSmokeReport:
    _require(sys.platform == "win32", "the GUI smoke is Windows-only")
    electron_executable = electron_executable.resolve()
    report = GuiSmokeReport()
    user_data_dir.mkdir(parents=True, exist_ok=True)

    backend_pids_before = list_image_pids(BACKEND_IMAGE_NAME)
    environment = os.environ.copy()
    environment["AQUA_USER_DATA"] = str(user_data_dir)

    process = subprocess.Popen(
        [str(electron_executable)],
        cwd=electron_executable.parent,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        report.record("Electron shell launched with a disposable user-data directory")

        started = time.monotonic()
        backend_pids_new: set[int] = set()
        while time.monotonic() - started < BACKEND_START_TIMEOUT_SECONDS:
            _require(
                process.poll() is None,
                f"Electron exited before its backend child started (exit code {process.returncode})",
            )
            backend_pids_new = list_image_pids(BACKEND_IMAGE_NAME) - backend_pids_before
            if backend_pids_new:
                break
            time.sleep(0.5)
        _require(bool(backend_pids_new), "no bundled backend child appeared before the timeout")
        report.backend_started_seconds = time.monotonic() - started
        report.record(
            f"bundled backend child started ({len(backend_pids_new)} process(es), "
            f"{report.backend_started_seconds:.1f}s)"
        )

        # Older artifacts predate the AQUA_USER_DATA override; record whether
        # runtime state actually landed in the disposable directory.
        settings_deadline = time.monotonic() + 15.0
        settings_path = user_data_dir / "settings" / "user_settings.json"
        while time.monotonic() < settings_deadline and not settings_path.is_file():
            time.sleep(0.5)
        report.user_data_isolated = settings_path.is_file()
        if report.user_data_isolated:
            report.record("runtime state written under the disposable user-data directory")
    finally:
        if process.poll() is None:
            _graceful_close(process)
            try:
                process.wait(timeout=SHUTDOWN_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                    capture_output=True,
                    timeout=15,
                )
                process.wait(timeout=15)
                raise SmokeFailure("Electron ignored the graceful close request")

    report.electron_exit_code = process.returncode
    report.record(f"graceful window close (exit code {report.electron_exit_code})")

    deadline = time.monotonic() + 10.0
    leftover = list_image_pids(BACKEND_IMAGE_NAME) - backend_pids_before
    while leftover and time.monotonic() < deadline:
        time.sleep(0.5)
        leftover = list_image_pids(BACKEND_IMAGE_NAME) - backend_pids_before
    if leftover:
        for pid in leftover:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=15)
        raise SmokeFailure(
            f"{len(leftover)} backend/solver process(es) survived the Electron shutdown"
        )
    report.record("no orphaned backend or solver-worker processes")
    return report


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    electron_executable = Path(arguments[0]) if arguments else find_electron_app()
    if electron_executable is None or not electron_executable.is_file():
        print("gui-smoke: packaged Electron app not found under .dist/ — build it first", file=sys.stderr)
        return 2

    import tempfile

    with tempfile.TemporaryDirectory(prefix="aqua-gui-smoke-") as scratch:
        try:
            report = run_gui_smoke(electron_executable, Path(scratch) / "user-data")
        except SmokeFailure as failure:
            print(f"gui-smoke: FAILED — {failure}", file=sys.stderr)
            return 1
    print(report.summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
