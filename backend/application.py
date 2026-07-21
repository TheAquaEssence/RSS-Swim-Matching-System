"""Application state and service containers for the FastAPI host."""

from __future__ import annotations

import logging
import math
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from backend.launch_auth import LaunchTokenAuth

if TYPE_CHECKING:
    from backend.services.repository import SqliteRepository


@dataclass
class BackendPaths:
    """Read-only resources and writable runtime paths used by one app."""

    app_root: Path
    ui_dir: Path
    solvers_dir: Path
    app_data_root: Path
    jobs_dir: Path
    settings_path: Path
    database_path: Path
    writable_resources_dir: Path


@dataclass
class ApplicationState:
    """Mutable state owned by one FastAPI application instance."""

    settings: dict
    settings_lock: threading.Lock = field(default_factory=threading.Lock)
    generate_guard_lock: threading.Lock = field(default_factory=threading.Lock)
    last_job_dir: str = ""
    generate_in_progress: bool = False
    last_generate_started_at: float = 0.0
    last_heartbeat: float = field(default_factory=time.monotonic)
    shutdown_event: threading.Event = field(default_factory=threading.Event)
    watchdog_thread: threading.Thread | None = None
    ready: bool = False

    def try_begin_generation(self, rate_limit_seconds: float) -> tuple[bool, int]:
        now = time.monotonic()
        with self.generate_guard_lock:
            if self.generate_in_progress:
                return False, 1
            remaining = rate_limit_seconds - (now - self.last_generate_started_at)
            if remaining > 0:
                return False, max(1, math.ceil(remaining))
            self.generate_in_progress = True
            self.last_generate_started_at = now
            return True, 0

    def finish_generation(self) -> None:
        with self.generate_guard_lock:
            self.generate_in_progress = False


@dataclass(frozen=True)
class ApplicationServices:
    """Explicit dependencies shared by the routes of one application."""

    paths: BackendPaths
    state: ApplicationState
    logger: logging.Logger
    repository: "SqliteRepository"
    launch_auth: LaunchTokenAuth
