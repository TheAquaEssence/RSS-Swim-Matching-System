"""Resolve read-only application resources in source and frozen builds."""

from __future__ import annotations

import sys
from pathlib import Path


def resolve_resource_root() -> Path:
    """Return the root containing bundled frontend, solver, and data assets.

    PyInstaller exposes the onedir bundle's internal resource directory as
    ``sys._MEIPASS``. Source runs continue to use the repository root.
    Runtime state must never be written beneath this path; callers use
    :mod:`core.app_paths` for writable locations.
    """

    if getattr(sys, "frozen", False):
        bundle_root = getattr(sys, "_MEIPASS", None)
        if bundle_root:
            return Path(bundle_root).resolve()
    return Path(__file__).resolve().parents[1]
