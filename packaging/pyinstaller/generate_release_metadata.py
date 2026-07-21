"""Create the license bundle and CycloneDX SBOM for the frozen application."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import uuid
from importlib import metadata
from pathlib import Path, PurePosixPath
from urllib.parse import quote

from packaging.markers import default_environment
from packaging.requirements import Requirement


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import generate_third_party_notices as notices  # noqa: E402


NOTICE_NAMES = re.compile(r"^(?:licen[cs]e|copying|notice)(?:[._-].*)?$", re.IGNORECASE)


def _safe_relative(path: PurePosixPath) -> Path:
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe distribution file path: {path}")
    return Path(*path.parts)


def _license_files(distribution: metadata.Distribution) -> list[tuple[Path, Path]]:
    found: list[tuple[Path, Path]] = []
    for package_path in distribution.files or ():
        raw_relative = PurePosixPath(str(package_path).replace("\\", "/"))
        if "licenses" not in {
            part.lower() for part in raw_relative.parts
        } and not NOTICE_NAMES.match(
            raw_relative.name
        ):
            continue
        relative = _safe_relative(raw_relative)
        source = Path(distribution.locate_file(package_path)).resolve()
        if source.is_file():
            found.append((source, relative))
    return sorted(found, key=lambda pair: pair[1].as_posix().lower())


def _copy_python_licenses(output: Path, locked: dict[str, str]) -> dict[str, list[str]]:
    copied: dict[str, list[str]] = {}
    for name, expected_version in sorted(locked.items()):
        distribution = metadata.distribution(name)
        installed_version = distribution.version
        if installed_version != expected_version:
            raise ValueError(
                f"{name} version mismatch: lock={expected_version}, installed={installed_version}"
            )
        package_licenses = _license_files(distribution)
        if not package_licenses:
            raise ValueError(f"installed distribution {name} exposes no license/notice files")
        destination_root = output / "licenses" / "python" / f"{name}-{expected_version}"
        copied[name] = []
        for source, relative in package_licenses:
            destination = destination_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            copied[name].append(destination.relative_to(output).as_posix())
    return copied


def _installed_dependency_closure(direct: dict[str, str]) -> set[str]:
    environment = default_environment()
    environment["extra"] = ""
    pending = list(direct)
    resolved: set[str] = set()
    while pending:
        requested_name = pending.pop()
        name = notices.canonical_name(requested_name)
        if name in resolved:
            continue
        distribution = metadata.distribution(requested_name)
        resolved.add(name)
        for raw_requirement in distribution.requires or ():
            requirement = Requirement(raw_requirement)
            if requirement.marker is None or requirement.marker.evaluate(environment):
                pending.append(requirement.name)
    return resolved


def _copy_python_license(output: Path) -> str:
    candidates = [Path(sys.base_prefix) / "LICENSE.txt", Path(sys.base_prefix) / "LICENSE"]
    source = next((path for path in candidates if path.is_file()), None)
    if source is None:
        raise ValueError(f"Python license not found under interpreter prefix {sys.base_prefix}")
    destination = output / "licenses" / "python-runtime" / source.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination.relative_to(output).as_posix()


def _purl(entry: notices.InventoryEntry) -> str:
    if entry.ecosystem.startswith("Python"):
        return f"pkg:pypi/{quote(entry.name)}@{quote(entry.version)}"
    return f"pkg:npm/{quote(entry.name, safe='/')}@{quote(entry.version)}"


def _component(entry: notices.InventoryEntry, license_files: list[str]) -> dict[str, object]:
    return {
        "type": "framework" if entry.name == "electron" else "library",
        "bom-ref": _purl(entry),
        "name": entry.name,
        "version": entry.version,
        "purl": _purl(entry),
        "licenses": [{"expression": entry.license}],
        "externalReferences": [{"type": "website", "url": entry.source}],
        "properties": [{"name": "aqua:boundary", "value": entry.ecosystem}]
        + [{"name": "aqua:license-file", "value": path} for path in license_files],
    }


def build_sbom(
    entries: list[notices.InventoryEntry],
    python_license_files: dict[str, list[str]],
    python_runtime_license: str,
) -> dict[str, object]:
    app_version = json.loads((ROOT / "desktop" / "package.json").read_text(encoding="utf-8"))[
        "version"
    ]
    components = []
    for entry in entries:
        paths = python_license_files.get(entry.name, [])
        components.append(_component(entry, paths))
    python_version = ".".join(str(part) for part in sys.version_info[:3])
    components.append(
        {
            "type": "platform",
            "bom-ref": f"pkg:generic/python@{python_version}",
            "name": "CPython",
            "version": python_version,
            "purl": f"pkg:generic/python@{python_version}",
            "licenses": [{"expression": "PSF-2.0"}],
            "externalReferences": [{"type": "website", "url": "https://www.python.org/"}],
            "properties": [
                {"name": "aqua:boundary", "value": "Python runtime"},
                {"name": "aqua:license-file", "value": python_runtime_license},
            ],
        }
    )
    components.sort(key=lambda component: str(component["bom-ref"]))
    identity = "\n".join(str(component["bom-ref"]) for component in components)
    return {
        "$schema": "https://cyclonedx.org/schema/bom-1.6.schema.json",
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, identity)}",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "bom-ref": f"pkg:generic/aqua-essence@{app_version}",
                "name": "Aqua Essence",
                "version": app_version,
                "licenses": [{"expression": "MIT"}],
            }
        },
        "components": components,
    }


def generate(output: Path) -> None:
    locked = notices.parse_pinned_requirements(notices.RUNTIME_LOCK)
    direct = notices.parse_pinned_requirements(notices.RUNTIME_REQUIREMENTS)
    resolved = _installed_dependency_closure(direct)
    if resolved != set(locked):
        raise ValueError(
            "runtime lock differs from the installed dependency closure; "
            f"missing={sorted(resolved - set(locked))}, stale={sorted(set(locked) - resolved)}"
        )
    entries = notices.build_inventory()
    temporary = output.with_name(f"{output.name}.tmp")
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir(parents=True)
    try:
        python_license_files = _copy_python_licenses(temporary, locked)
        python_runtime_license = _copy_python_license(temporary)
        sbom = build_sbom(entries, python_license_files, python_runtime_license)
        (temporary / "SBOM.cdx.json").write_text(
            json.dumps(sbom, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        if output.exists():
            shutil.rmtree(output)
        temporary.replace(output)
    except BaseException:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        generate(arguments.output.resolve())
    except (OSError, ValueError, metadata.PackageNotFoundError) as exc:
        print(f"release metadata generation failed: {exc}", file=sys.stderr)
        return 2
    print(f"release metadata: {arguments.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
