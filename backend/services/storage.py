"""Path resolution, settings persistence, and copy-on-write storage rules.

The service is a pure function of its configured roots: it never reads
``backend.server`` globals, so hosts and tests can bind it to any layout.
CSV file helpers live here too because they are plain storage primitives.
"""

from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from backend.services.resource_provisioner import (
    DEFAULT_RESOURCE_FILES,
    LEGACY_RESOURCE_FILES,
    provision_resource_for_edit,
)


def read_csv_file(path: Path) -> tuple[list[str], list[dict]]:
    """Return (headers, rows) from a CSV file."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        rows = [dict(row) for row in reader]
    return list(headers), rows


def write_csv_file(path: Path, headers: list[str], rows: list[dict]) -> None:
    """Write rows to a CSV file, creating parent dirs as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


@dataclass(frozen=True)
class StorageService:
    """Owns the path and storage rules for one application layout."""

    app_root: Path
    app_data_root: Path
    writable_resources_dir: Path
    settings_path: Path
    default_file_paths: Mapping[str, str]

    # -- Path resolution ----------------------------------------------------

    def resolve_from_root(self, p: str) -> Path:
        if not p:
            return Path()
        # Settings and requests may carry Windows-style separators; treat them
        # as separators on every platform.
        path = Path(p.replace("\\", "/"))
        return path if path.is_absolute() else (self.app_root / path).resolve()

    def file_exists_from_root(self, p: str) -> bool:
        if not p:
            return False
        return self.resolve_from_root(p).exists()

    def normalize_path_for_request(self, p: str) -> str:
        if not p:
            return ""
        abs_path = self.resolve_from_root(p)
        try:
            rel = abs_path.relative_to(self.app_root)
            return rel.as_posix()
        except ValueError:
            return abs_path.as_posix()

    def is_repo_sample_or_generated_path(self, path: Path) -> bool:
        for base in (
            self.app_root / "examples" / "demo" / "matching",
            self.app_root / "data" / "generated",
        ):
            try:
                path.resolve().relative_to(base.resolve())
                return True
            except ValueError:
                continue
        return False

    # -- Settings persistence -----------------------------------------------

    def read_settings_payload(self) -> dict:
        """Return the parsed settings JSON. Raises on missing/invalid file."""
        return json.loads(self.settings_path.read_text(encoding="utf-8"))

    def save_settings(self, settings: dict) -> None:
        """Atomically persist settings: write to .tmp, then os.replace."""
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(settings, indent=2).encode("utf-8")
        tmp_path = self.settings_path.with_suffix(".tmp")
        tmp_path.write_bytes(data)
        os.replace(str(tmp_path), str(self.settings_path))

    # -- Bundled-resource rules ---------------------------------------------

    def migrate_bundled_default_path(self, key: str, raw_path: str) -> str:
        """Map an old bundled default to its provisioned writable equivalent."""
        if not raw_path:
            return raw_path
        legacy_path = LEGACY_RESOURCE_FILES.get(key, "")
        if legacy_path:
            legacy_source = (self.app_root / legacy_path).resolve()
            candidate = self.resolve_from_root(raw_path)
            if raw_path == legacy_path or candidate == legacy_source:
                return self.default_file_paths[key]
        if self.app_data_root == self.app_root:
            return raw_path
        bundled_path = DEFAULT_RESOURCE_FILES.get(key, "")
        if not bundled_path:
            return raw_path
        bundled_source = (self.app_root / bundled_path).resolve()
        candidate = self.resolve_from_root(raw_path)
        if raw_path == bundled_path or candidate == bundled_source:
            return self.default_file_paths[key]
        return raw_path

    def provision_for_edit(self, source: Path) -> Path:
        """Copy a bundled resource to the writable tree before editing.

        External user-selected files are returned unchanged; see
        resource_provisioner.provision_resource_for_edit for the full rules.
        """
        return provision_resource_for_edit(
            source,
            app_root=self.app_root,
            app_data_root=self.app_data_root,
            writable_resources_root=self.writable_resources_dir,
        )
