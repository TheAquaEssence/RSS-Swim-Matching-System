"""Reusable real-process harness for desktop-host and packaging tests.

The harness intentionally talks to the same ``start.py`` entry point that a
desktop shell will own. It keeps the capability token in the child environment
and request headers, never in command-line arguments or URLs.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.launch_auth import LAUNCH_TOKEN_ENV, LAUNCH_TOKEN_HEADER, generate_launch_token


LOOPBACK_HOST = "127.0.0.1"
DEFAULT_STARTUP_TIMEOUT = 20.0
DEFAULT_SHUTDOWN_TIMEOUT = 12.0
FORCED_TERMINATION_GRACE = 2.0
MAX_CAPTURED_OUTPUT_LINES = 200


class BackendProcessError(RuntimeError):
    """Base error for a backend child that did not meet its lifecycle contract."""


class BackendStartError(BackendProcessError):
    """Raised when the backend exits or never becomes ready."""

    def __init__(self, message: str, *, exit_code: int | None, output: str) -> None:
        self.exit_code = exit_code
        self.output = output
        details = output or "no backend output was captured"
        super().__init__(f"{message} (exit code: {exit_code}).\nBackend output:\n{details}")


@dataclass(frozen=True)
class BackendResponse:
    """Small HTTP response value suitable for assertions in host tests."""

    status: int
    body: bytes

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8"))


def reserve_loopback_port() -> int:
    """Ask the OS for a currently available loopback TCP port."""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind((LOOPBACK_HOST, 0))
        return listener.getsockname()[1]


class BackendProcessHarness:
    """Own one backend subprocess and guarantee bounded teardown.

    ``app_data_dir`` is mandatory so tests cannot accidentally write runtime
    state into the source tree. A harness may be restarted; every start uses a
    newly selected loopback port unless ``requested_port`` is supplied for a
    targeted launch-failure test.
    """

    def __init__(
        self,
        app_data_dir: Path,
        *,
        repository_root: Path | None = None,
        backend_executable: Path | None = None,
        launch_token: str | None = None,
        startup_timeout: float = DEFAULT_STARTUP_TIMEOUT,
        shutdown_timeout: float = DEFAULT_SHUTDOWN_TIMEOUT,
        requested_port: int | None = None,
    ) -> None:
        root = repository_root or Path(__file__).resolve().parents[1]
        self.repository_root = root.resolve()
        self.backend_executable = (
            Path(backend_executable).resolve() if backend_executable is not None else None
        )
        self.app_data_dir = Path(app_data_dir).resolve()
        self._configured_launch_token = launch_token
        self.launch_token = launch_token or ""
        self.startup_timeout = startup_timeout
        self.shutdown_timeout = shutdown_timeout
        self.requested_port = requested_port
        self.port: int | None = None
        self.process: subprocess.Popen[str] | None = None
        self._output: deque[str] = deque(maxlen=MAX_CAPTURED_OUTPUT_LINES)
        self._reader_thread: threading.Thread | None = None

    def _build_launch_command(self, port: int) -> tuple[list[str], Path]:
        arguments = [
            "--port",
            str(port),
            "--no-browser",
            "--data-dir",
            str(self.app_data_dir),
        ]
        if self.backend_executable is not None:
            return [str(self.backend_executable), *arguments], self.backend_executable.parent
        return [
            sys.executable,
            "-u",
            str(self.repository_root / "start.py"),
            *arguments,
        ], self.repository_root

    @property
    def base_url(self) -> str:
        if self.port is None:
            raise BackendProcessError("Backend has not been started")
        return f"http://{LOOPBACK_HOST}:{self.port}"

    @property
    def captured_output(self) -> str:
        output = "".join(self._output).strip()
        return output.replace(self.launch_token, "[REDACTED]") if self.launch_token else output

    def _read_output(self, stream) -> None:
        try:
            for line in iter(stream.readline, ""):
                self._output.append(line)
        finally:
            stream.close()

    def start(self) -> "BackendProcessHarness":
        """Launch the backend and wait until its public readiness probe succeeds."""

        if self.process is not None and self.process.poll() is None:
            raise BackendProcessError("Backend is already running")

        self.app_data_dir.mkdir(parents=True, exist_ok=True)
        self.port = self.requested_port or reserve_loopback_port()
        self.launch_token = self._configured_launch_token or generate_launch_token()
        self._output.clear()

        environment = os.environ.copy()
        environment["AQUA_APP_DATA_DIR"] = str(self.app_data_dir)
        environment[LAUNCH_TOKEN_ENV] = self.launch_token
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        command, working_directory = self._build_launch_command(self.port)
        self.process = subprocess.Popen(
            command,
            cwd=working_directory,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert self.process.stdout is not None
        self._reader_thread = threading.Thread(
            target=self._read_output,
            args=(self.process.stdout,),
            daemon=True,
        )
        self._reader_thread.start()

        deadline = time.monotonic() + self.startup_timeout
        while time.monotonic() < deadline:
            exit_code = self.process.poll()
            if exit_code is not None:
                self._finish_reader()
                raise BackendStartError(
                    "Backend exited before becoming ready",
                    exit_code=exit_code,
                    output=self.captured_output,
                )
            try:
                response = self.request("/api/ready", authenticated=False, timeout=0.5)
                if response.status == 200 and response.json().get("ok") is True:
                    return self
            except (OSError, ValueError, json.JSONDecodeError):
                pass
            time.sleep(0.05)

        self._force_stop()
        raise BackendStartError(
            "Backend did not become ready before the startup timeout",
            exit_code=self.process.returncode,
            output=self.captured_output,
        )

    def request(
        self,
        path: str,
        *,
        method: str = "GET",
        authenticated: bool = True,
        body: bytes | None = None,
        timeout: float = 2.0,
        headers: dict[str, str] | None = None,
    ) -> BackendResponse:
        """Send a loopback request, returning HTTP error responses for assertions."""

        headers = dict(headers or {})
        if authenticated:
            headers[LAUNCH_TOKEN_HEADER] = self.launch_token
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return BackendResponse(response.status, response.read())
        except urllib.error.HTTPError as exc:
            return BackendResponse(exc.code, exc.read())

    def stop(self) -> None:
        """Request graceful shutdown, then terminate and kill on bounded deadlines."""

        process = self.process
        if process is None:
            return
        if process.poll() is None:
            try:
                self.request("/api/shutdown", method="POST", timeout=2.0)
            except OSError:
                pass
            try:
                process.wait(timeout=self.shutdown_timeout)
            except subprocess.TimeoutExpired:
                self._force_stop()
        self._finish_reader()

    def restart(self) -> "BackendProcessHarness":
        """Stop and start the backend again against the same application-data root."""

        self.stop()
        self.process = None
        self.port = None
        return self.start()

    def _force_stop(self) -> None:
        process = self.process
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=FORCED_TERMINATION_GRACE)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=FORCED_TERMINATION_GRACE)
        self._finish_reader()

    def _finish_reader(self) -> None:
        if self._reader_thread is not None:
            self._reader_thread.join(timeout=1.0)

    def __enter__(self) -> "BackendProcessHarness":
        return self.start()

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.stop()
