"""Generate the release dependency inventory in THIRD_PARTY_NOTICES.md.

The inventory is deliberately derived from checked-in, pinned dependency
metadata.  It never scans the developer's environment, where test tools and
unrelated packages would make the result non-reproducible.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from urllib.parse import quote
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_REQUIREMENTS = ROOT / "requirements.txt"
RUNTIME_LOCK = ROOT / "requirements-runtime-lock.txt"
DEV_REQUIREMENTS = ROOT / "requirements-dev.txt"
DESKTOP_PACKAGE = ROOT / "desktop" / "package.json"
DESKTOP_LOCK = ROOT / "desktop" / "package-lock.json"
OUTPUT = ROOT / "THIRD_PARTY_NOTICES.md"

PIN_RE = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s;]+)$")


@dataclass(frozen=True)
class PackageMetadata:
    license: str
    source: str
    notice: str


@dataclass(frozen=True)
class InventoryEntry:
    ecosystem: str
    name: str
    version: str
    license: str
    source: str
    notice: str


# Reviewed SPDX expressions for the complete resolved Python runtime graph.
# Wheel metadata is inconsistent for older projects, so these values are kept
# explicit and the build separately proves that every installed distribution
# contributes its actual LICENSE/COPYING/NOTICE files to the package.
PYTHON_LICENSES = {
    "absl-py": "Apache-2.0",
    "annotated-doc": "MIT",
    "annotated-types": "MIT",
    "anyio": "MIT",
    "charset-normalizer": "MIT",
    "click": "BSD-3-Clause",
    "colorama": "BSD-3-Clause",
    "fastapi": "MIT",
    "h11": "MIT",
    "idna": "BSD-3-Clause",
    "immutabledict": "MIT",
    "jinja2": "BSD-3-Clause",
    "markupsafe": "BSD-3-Clause",
    "numpy": "BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0",
    "ortools": "Apache-2.0",
    "pandas": "BSD-3-Clause",
    "pillow": "MIT-CMU",
    "protobuf": "BSD-3-Clause",
    "pydantic": "MIT",
    "pydantic-core": "MIT",
    "python-dateutil": "BSD-3-Clause OR Apache-2.0",
    "python-multipart": "Apache-2.0",
    "pytz": "MIT",
    "reportlab": "BSD-3-Clause",
    "six": "MIT",
    "starlette": "BSD-3-Clause",
    "typing-extensions": "PSF-2.0",
    "typing-inspection": "MIT",
    "tzdata": "Apache-2.0",
    "uvicorn": "BSD-3-Clause",
}

ELECTRON_METADATA = PackageMetadata(
    "MIT",
    "https://github.com/electron/electron",
    "Electron `LICENSE` and `LICENSES.chromium.html`",
)

DEV_ONLY = frozenset({"pytest", "httpx", "faker", "ruff"})

# Browser assets vendored into frontend/ so the packaged app works offline.
# Versions are pinned here and verified against the checked-in files.
VENDORED_WEB_ASSETS = [
    (
        "chart.js",
        "4.5.1",
        PackageMetadata(
            "MIT",
            "https://github.com/chartjs/Chart.js",
            "`frontend/xai_dashboard/static/vendor/chartjs/LICENSE.md`",
        ),
        "frontend/xai_dashboard/static/vendor/chartjs/LICENSE.md",
    ),
    (
        "@fontsource/outfit",
        "5.3.0",
        PackageMetadata(
            "OFL-1.1",
            "https://github.com/fontsource/font-files",
            "`frontend/vendor/fonts/outfit/LICENSE`",
        ),
        "frontend/vendor/fonts/outfit/LICENSE",
    ),
    (
        "@fontsource/jetbrains-mono",
        "5.3.0",
        PackageMetadata(
            "OFL-1.1",
            "https://github.com/fontsource/font-files",
            "`frontend/vendor/fonts/jetbrains-mono/LICENSE`",
        ),
        "frontend/vendor/fonts/jetbrains-mono/LICENSE",
    ),
]


def canonical_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_pinned_requirements(path: Path) -> dict[str, str]:
    packages: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.split("#", 1)[0].strip()
        if not line or line.startswith("-r "):
            continue
        match = PIN_RE.fullmatch(line)
        if not match:
            raise ValueError(f"{path.name}:{line_number} is not an exact name==version pin: {line}")
        name, version = match.groups()
        canonical = canonical_name(name)
        if canonical in packages:
            raise ValueError(f"{path.name} contains duplicate package {canonical}")
        packages[canonical] = version
    return packages


def python_inventory() -> list[InventoryEntry]:
    direct = parse_pinned_requirements(RUNTIME_REQUIREMENTS)
    pinned = parse_pinned_requirements(RUNTIME_LOCK)
    direct_mismatches = sorted(
        name for name, version in direct.items() if pinned.get(name) != version
    )
    if direct_mismatches:
        raise ValueError(
            "runtime lock does not preserve direct requirement pins: "
            f"{direct_mismatches}"
        )
    unknown = sorted(set(pinned) - set(PYTHON_LICENSES))
    stale = sorted(set(PYTHON_LICENSES) - set(pinned))
    if unknown or stale:
        raise ValueError(
            "runtime Python license metadata is out of sync; "
            f"missing metadata={unknown}, stale metadata={stale}"
        )
    leaked = sorted(DEV_ONLY.intersection(pinned))
    if leaked:
        raise ValueError(f"development-only packages appear in runtime requirements: {leaked}")
    return [
        InventoryEntry(
            "Python direct" if name in direct else "Python transitive",
            name,
            version,
            PYTHON_LICENSES[name],
            f"https://pypi.org/project/{quote(name)}/{quote(version)}/",
            f"`licenses/python/{name}-{version}/`",
        )
        for name, version in sorted(pinned.items())
    ]


def electron_inventory() -> list[InventoryEntry]:
    package = json.loads(DESKTOP_PACKAGE.read_text(encoding="utf-8"))
    lock = json.loads(DESKTOP_LOCK.read_text(encoding="utf-8"))
    version = package.get("devDependencies", {}).get("electron")
    if not version or not re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", version):
        raise ValueError("desktop/package.json must pin Electron to an exact version")

    locked = lock.get("packages", {}).get("node_modules/electron", {})
    if locked.get("version") != version:
        raise ValueError("Electron package and lock versions do not match")
    if locked.get("license") != ELECTRON_METADATA.license:
        raise ValueError("Electron lockfile license differs from reviewed metadata")

    # Electron is a devDependency because it is the desktop build tool, but the
    # Electron binary itself is shipped. Its npm download/extraction dependencies
    # are install-time tools and are not part of the packaged application.
    entries = [
        InventoryEntry(
            "Desktop runtime",
            "electron",
            version,
            ELECTRON_METADATA.license,
            ELECTRON_METADATA.source,
            ELECTRON_METADATA.notice,
        )
    ]
    packages = lock.get("packages", {})
    pending = list(package.get("dependencies", {}))
    seen: set[str] = set()
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        locked_package = packages.get(f"node_modules/{name}")
        if not locked_package:
            raise ValueError(f"desktop runtime dependency {name} is missing from package-lock.json")
        locked_version = locked_package.get("version")
        declared_version = package.get("dependencies", {}).get(name)
        if declared_version and declared_version != locked_version:
            raise ValueError(f"desktop dependency {name} must use its exact locked version")
        license_name = locked_package.get("license")
        if not locked_version or not license_name:
            raise ValueError(f"desktop runtime dependency {name} lacks version/license metadata")
        entries.append(
            InventoryEntry(
                "Desktop runtime",
                name,
                locked_version,
                license_name,
                f"https://www.npmjs.com/package/{quote(name, safe='@')}/v/{locked_version}",
                f"license file from packaged npm module `{name}`",
            )
        )
        pending.extend(locked_package.get("dependencies", {}))
    return entries


def vendored_web_inventory() -> list[InventoryEntry]:
    entries = []
    for name, version, metadata, license_path in VENDORED_WEB_ASSETS:
        if not (ROOT / license_path).is_file():
            raise ValueError(f"vendored asset {name} is missing its license file: {license_path}")
        entries.append(
            InventoryEntry("Vendored web asset", name, version, metadata.license,
                           metadata.source, metadata.notice)
        )
    chart_js = ROOT / "frontend" / "xai_dashboard" / "static" / "vendor" / "chartjs" / "chart.umd.min.js"
    chart_version = next(
        (entry[1] for entry in VENDORED_WEB_ASSETS if entry[0] == "chart.js"), None
    )
    if f'version="{chart_version}"' not in chart_js.read_text(encoding="utf-8"):
        raise ValueError(
            f"vendored chart.umd.min.js does not match pinned Chart.js version {chart_version}"
        )
    return entries


def build_inventory() -> list[InventoryEntry]:
    return python_inventory() + vendored_web_inventory() + electron_inventory()


def render(entries: list[InventoryEntry]) -> str:
    rows = [
        f"| {entry.ecosystem} | `{entry.name}` | `{entry.version}` | "
        f"{entry.license} | [source]({entry.source}) | {entry.notice} |"
        for entry in entries
    ]
    table = "\n".join(rows)
    return f"""# Third-Party Notices

This report identifies the software distributed with Aqua Essence, including the
fully resolved Python runtime graph. It is generated from `requirements.txt`,
`requirements-runtime-lock.txt`, `desktop/package.json`,
`desktop/package-lock.json`, and the pinned vendored web assets under
`frontend/vendor/` and `frontend/xai_dashboard/static/vendor/`; do not edit the
table manually. Aqua Essence itself is
MIT-licensed under the repository's `LICENSE` file.

| Boundary | Package | Pinned version | License | Homepage/source | Required notice pointer |
| --- | --- | --- | --- | --- | --- |
{table}

## Distribution obligations

- Preserve this project's `LICENSE` in source and binary releases.
- Preserve each Python wheel's license file when its code or native libraries are
  collected into the backend executable. Apache-2.0 packages also require any
  upstream `NOTICE` file that is present in the artifact being redistributed.
- Electron is MIT-licensed, but its binary embeds Chromium, Node.js, and other
  components. Ship Electron's version-matched `LICENSE` and
  `LICENSES.chromium.html` beside the desktop executable; the latter is the
  authoritative component-by-component notice bundle and must not be replaced by
  this short report.
- Preserve ReportLab's license and the individual license files for any ReportLab
  fonts actually collected into the backend bundle (including Bitstream Vera or
  DarkGarden when present).
- OR-Tools contains compiled native code. Preserve the license material delivered
  in its wheel and verify the final frozen application for additional native
  notices before publishing.
- PyInstaller is a build-time tool, not an application runtime dependency. Its
  GPL bootloader exception permits distributing an unmodified,
  PyInstaller-generated application under this project's license. PyInstaller
  itself remains GPL-licensed; review its `COPYING.txt` before modifying its
  bootloader or redistributing the build tool. Record the pinned PyInstaller
  version in build metadata before the first release.

## Scope and artifact verification

`requirements-runtime-lock.txt` is the reproducible Python dependency boundary for
the Windows/Python 3.14 package. Every backend build validates the installed
versions against that lock, creates `SBOM.cdx.json`, and copies every license,
copying, and notice file exposed by those installed distributions into
`licenses/python/`. Package verification rejects a missing SBOM, component, or
license directory. Python's own license is bundled separately because the frozen
application distributes the interpreter and standard library.

The Electron npm package is included even though it is a `devDependency`, because
its binary becomes the desktop runtime. Its npm download/extraction helpers are
not shipped in the packaged application and are excluded. Python packages from
`requirements-dev.txt` (including pytest, HTTPX, Faker, and Ruff) are also excluded.

Regenerate with:

```console
python scripts/generate_third_party_notices.py
```

CI/release verification can check for drift without modifying files:

```console
python scripts/generate_third_party_notices.py --check
```
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the report is stale")
    args = parser.parse_args(argv)

    try:
        content = render(build_inventory())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"third-party notice generation failed: {exc}", file=sys.stderr)
        return 2

    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != content:
            print(f"{OUTPUT.relative_to(ROOT)} is stale; regenerate it", file=sys.stderr)
            return 1
        print(f"{OUTPUT.relative_to(ROOT)} is current")
        return 0

    OUTPUT.write_text(content, encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
