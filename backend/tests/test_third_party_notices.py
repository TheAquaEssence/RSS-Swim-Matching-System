from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts import generate_third_party_notices as notices


ROOT = Path(__file__).resolve().parents[2]


def test_inventory_matches_all_direct_runtime_pins() -> None:
    pinned = notices.parse_pinned_requirements(ROOT / "requirements.txt")
    python_entries = {
        entry.name: entry.version
        for entry in notices.build_inventory()
        if entry.ecosystem == "Python direct"
    }

    assert python_entries == pinned


def test_inventory_matches_full_transitive_runtime_lock() -> None:
    locked = notices.parse_pinned_requirements(ROOT / "requirements-runtime-lock.txt")
    python_entries = {
        entry.name: entry.version
        for entry in notices.build_inventory()
        if entry.ecosystem.startswith("Python")
    }

    assert python_entries == locked
    assert all("UNKNOWN" not in entry.license for entry in notices.build_inventory())


def test_inventory_excludes_development_only_packages() -> None:
    runtime_pins = notices.parse_pinned_requirements(ROOT / "requirements.txt")
    dev_pins = notices.parse_pinned_requirements(ROOT / "requirements-dev.txt")
    inventoried = {entry.name for entry in notices.build_inventory()}
    dev_extras = set(dev_pins) - set(runtime_pins)

    assert notices.DEV_ONLY.issubset(dev_pins)
    assert inventoried.isdisjoint(dev_extras)


def test_electron_is_the_pinned_shipped_desktop_runtime() -> None:
    electron_entries = [entry for entry in notices.build_inventory() if entry.name == "electron"]

    assert len(electron_entries) == 1
    assert electron_entries[0].version == "43.1.1"
    assert "LICENSES.chromium.html" in electron_entries[0].notice


def test_electron_install_helpers_are_not_shipped_dependencies() -> None:
    inventoried = {entry.name for entry in notices.build_inventory()}

    assert "@electron/get" not in inventoried
    assert "@electron-internal/extract-zip" not in inventoried


def test_unpinned_requirement_is_rejected(tmp_path: Path) -> None:
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("fastapi>=0.135\n", encoding="utf-8")

    with pytest.raises(ValueError, match="not an exact"):
        notices.parse_pinned_requirements(requirements)


def test_committed_report_is_current() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/generate_third_party_notices.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
