from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "prepare_release", ROOT / "scripts" / "prepare_release.py"
)
assert SPEC and SPEC.loader
prepare_release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare_release)


def _release_root(tmp_path: Path, *, version: str = "1.2.3") -> Path:
    (tmp_path / "desktop").mkdir()
    (tmp_path / "backend").mkdir()
    (tmp_path / "desktop" / "package.json").write_text(
        json.dumps({"version": version}), encoding="utf-8"
    )
    (tmp_path / "backend" / "server.py").write_text(
        f'return {{"version": "{version}"}}\n', encoding="utf-8"
    )
    (tmp_path / "CHANGELOG.md").write_text(
        f"# Changelog\n\n## Unreleased\n\n## {version} — 2026-07-21\n\n"
        "### Fixed\n\n- Native dialogs.\n\n## 1.0.0 — 2026-01-01\n\n- Earlier.\n",
        encoding="utf-8",
    )
    return tmp_path


def test_prepare_release_generates_versioned_notes_and_checksum(tmp_path: Path) -> None:
    root = _release_root(tmp_path)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    installer = artifacts / "Aqua-Essence-Setup-1.2.3-x64.exe"
    installer.write_bytes(b"installer")
    notes = tmp_path / "out" / "RELEASE_NOTES.md"
    checksums = tmp_path / "out" / "SHA256SUMS"

    prepare_release.prepare(
        tag="v1.2.3",
        artifacts_dir=artifacts,
        notes_output=notes,
        checksums_output=checksums,
        root=root,
    )

    assert notes.read_text(encoding="utf-8") == "### Fixed\n\n- Native dialogs.\n"
    checksum = checksums.read_text(encoding="utf-8")
    assert checksum.endswith("  Aqua-Essence-Setup-1.2.3-x64.exe\n")
    assert len(checksum.split()[0]) == 64


def test_release_contract_rejects_tag_backend_and_installer_mismatches(
    tmp_path: Path,
) -> None:
    root = _release_root(tmp_path)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()

    for tag in ("1.2.3", "v1.2.4"):
        with pytest.raises(ValueError):
            prepare_release.validate_version_contract(tag, root)

    (root / "backend" / "server.py").write_text(
        'return {"version": "9.9.9"}\n', encoding="utf-8"
    )
    with pytest.raises(ValueError):
        prepare_release.validate_version_contract("v1.2.3", root)

    with pytest.raises(ValueError):
        prepare_release.installer_paths(artifacts, "1.2.3")
