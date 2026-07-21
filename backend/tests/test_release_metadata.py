from __future__ import annotations

import importlib.util
from pathlib import Path, PurePosixPath

from scripts import generate_third_party_notices as notices


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "generate_release_metadata",
    ROOT / "packaging" / "pyinstaller" / "generate_release_metadata.py",
)
assert SPEC and SPEC.loader
release_metadata = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release_metadata)


class FakeDistribution:
    version = "1.0"
    files = [
        PurePosixPath("example-1.0.dist-info/METADATA"),
        PurePosixPath("example-1.0.dist-info/licenses/LICENSE.txt"),
        PurePosixPath("example/data/NOTICE"),
    ]

    def __init__(self, root: Path) -> None:
        self.root = root

    def locate_file(self, package_path: PurePosixPath) -> Path:
        return self.root / Path(*package_path.parts)


def test_license_file_discovery_includes_notices_and_license_directories(tmp_path: Path) -> None:
    distribution = FakeDistribution(tmp_path)
    for package_path in distribution.files:
        path = distribution.locate_file(package_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("test", encoding="utf-8")

    found = release_metadata._license_files(distribution)

    assert [relative.as_posix() for _, relative in found] == [
        "example-1.0.dist-info/licenses/LICENSE.txt",
        "example/data/NOTICE",
    ]


def test_sbom_covers_every_inventoried_component() -> None:
    entries = notices.build_inventory()
    python_files = {
        entry.name: [f"licenses/python/{entry.name}-{entry.version}/LICENSE"]
        for entry in entries
        if entry.ecosystem.startswith("Python")
    }

    sbom = release_metadata.build_sbom(
        entries, python_files, "licenses/python-runtime/LICENSE.txt"
    )
    components = sbom["components"]

    assert sbom["bomFormat"] == "CycloneDX"
    assert sbom["specVersion"] == "1.6"
    assert len(components) == len(entries) + 1
    assert {component["name"] for component in components} >= {
        entry.name for entry in entries
    }
