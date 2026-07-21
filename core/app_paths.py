"""Application resource and writable-data path resolution.

The source tree (or packaged application directory) contains read-only
resources such as the frontend, solver, and reference tables. Runtime state
belongs under one separately configurable directory so a desktop host can
point Aqua Essence at Electron's ``userData`` directory.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

APP_DATA_ENV = "AQUA_APP_DATA_DIR"


@dataclass(frozen=True)
class AppDataPaths:
    """All application-managed writable locations."""

    root: Path
    jobs: Path
    settings: Path
    database: Path
    logs: Path
    resources: Path


def resolve_app_data_root(
    resource_root: Path,
    *,
    environ: Mapping[str, str] | None = None,
) -> Path:
    """Return the writable application-data root.

    ``AQUA_APP_DATA_DIR`` is the desktop/runtime contract. Source development
    retains the repository root as its default for backward compatibility;
    packaged hosts must provide their platform-specific writable directory.
    """

    environment = os.environ if environ is None else environ
    override = environment.get(APP_DATA_ENV, "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path(resource_root).expanduser().resolve()


def build_app_data_paths(
    resource_root: Path,
    *,
    environ: Mapping[str, str] | None = None,
) -> AppDataPaths:
    """Build the complete writable layout from the single root setting."""

    root = resolve_app_data_root(resource_root, environ=environ)
    return AppDataPaths(
        root=root,
        jobs=root / "jobs",
        settings=root / "settings" / "user_settings.json",
        database=root / "data" / "aqua_essence.db",
        logs=root / "logs",
        resources=root / "resources",
    )
