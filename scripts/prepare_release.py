"""Validate a release tag and generate deterministic release assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SEMVER_TAG = re.compile(r"^v\d+\.\d+\.\d+$")


def canonical_version(root: Path = ROOT) -> str:
    package = json.loads((root / "desktop" / "package.json").read_text(encoding="utf-8"))
    version = package.get("version")
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("desktop/package.json does not contain a semantic version")
    return version


def validate_version_contract(tag: str, root: Path = ROOT) -> str:
    if not SEMVER_TAG.fullmatch(tag):
        raise ValueError("release tag must use vMAJOR.MINOR.PATCH")
    version = canonical_version(root)
    if tag != f"v{version}":
        raise ValueError(f"release tag {tag} does not match application version {version}")

    server_text = (root / "backend" / "server.py").read_text(encoding="utf-8")
    health_versions = set(re.findall(r'"version"\s*:\s*"(\d+\.\d+\.\d+)"', server_text))
    if health_versions != {version}:
        raise ValueError(
            "backend health version does not match the canonical application version: "
            f"{sorted(health_versions)}"
        )
    return version


def changelog_notes(version: str, root: Path = ROOT) -> str:
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    heading = re.compile(rf"^## {re.escape(version)}(?:\s+—[^\n]*)?$", re.MULTILINE)
    match = heading.search(changelog)
    if match is None:
        raise ValueError(f"CHANGELOG.md has no release section for {version}")
    next_heading = re.search(r"^## ", changelog[match.end() :], re.MULTILINE)
    end = match.end() + next_heading.start() if next_heading else len(changelog)
    notes = changelog[match.end() : end].strip()
    if not notes:
        raise ValueError(f"CHANGELOG.md release section for {version} is empty")
    return notes + "\n"


def installer_paths(artifacts_dir: Path, version: str) -> list[Path]:
    installers = sorted(artifacts_dir.glob(f"Aqua-Essence-Setup-{version}-*.exe"))
    if len(installers) != 1 or not installers[0].is_file():
        raise ValueError(
            f"expected exactly one Aqua Essence {version} installer, found {len(installers)}"
        )
    return installers


def checksum_lines(paths: list[Path]) -> str:
    lines = []
    for path in paths:
        digest = hashlib.sha256(path.read_bytes()).hexdigest().upper()
        lines.append(f"{digest}  {path.name}")
    return "\n".join(lines) + "\n"


def prepare(
    *,
    tag: str,
    artifacts_dir: Path,
    notes_output: Path,
    checksums_output: Path,
    root: Path = ROOT,
) -> None:
    version = validate_version_contract(tag, root)
    installers = installer_paths(artifacts_dir, version)
    notes_output.parent.mkdir(parents=True, exist_ok=True)
    checksums_output.parent.mkdir(parents=True, exist_ok=True)
    notes_output.write_text(changelog_notes(version, root), encoding="utf-8")
    checksums_output.write_text(checksum_lines(installers), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--artifacts-dir", type=Path, required=True)
    parser.add_argument("--notes-output", type=Path, required=True)
    parser.add_argument("--checksums-output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        prepare(
            tag=args.tag,
            artifacts_dir=args.artifacts_dir.resolve(),
            notes_output=args.notes_output.resolve(),
            checksums_output=args.checksums_output.resolve(),
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
