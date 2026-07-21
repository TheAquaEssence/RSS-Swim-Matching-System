"""Copy bundled editable data into the writable application-data tree."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


DEFAULT_RESOURCE_FILES = {
    "classes": "",
    "swimmers": "examples/demo/matching/swimmers.csv",
    "instructors": "examples/demo/matching/instructors.csv",
    "historical_pairings": "examples/demo/matching/historical_pairings.csv",
    "swimmer_type_color_rankings": "data/source/swimmer_type_color_rankings.csv",
    "swimmer_type_style_rankings": "data/source/swimmer_type_style_rankings.csv",
    "personality_colors": "data/source/personality_colors.csv",
    "instructor_styles": "data/source/instructor_styles.csv",
    "swimmer_types": "data/source/swimmer_types.csv",
}

# Settings written before the public/demo data layout was consolidated may
# still contain these paths. They are migration aliases only: no files should
# be restored under data/app_samples/.
LEGACY_RESOURCE_FILES = {
    "swimmers": "data/app_samples/swimmers.csv",
    "instructors": "data/app_samples/instructors.csv",
    "historical_pairings": "data/app_samples/historical_pairings.csv",
}


def _is_separate_data_root(app_root: Path, app_data_root: Path) -> bool:
    return app_root.resolve() != app_data_root.resolve()


def bundled_resource_destination(
    source: Path,
    *,
    app_root: Path,
    writable_resources_root: Path,
) -> Path:
    """Return the writable mirror path for a resource inside ``app_root``."""

    resolved_source = source.resolve()
    try:
        relative = resolved_source.relative_to(app_root.resolve())
    except ValueError as exc:
        raise ValueError("Only bundled application resources can be provisioned") from exc
    return writable_resources_root.resolve() / relative


def provision_resource_for_edit(
    source: Path,
    *,
    app_root: Path,
    app_data_root: Path,
    writable_resources_root: Path,
) -> Path:
    """Return an editable path, copying a bundled resource only when needed.

    External user-selected files remain in place. Source-development mode also
    preserves its historical in-workspace behavior. In packaged/separate-data
    mode a bundled file is copied once and subsequent calls retain user edits.
    """

    source = source.resolve()
    if not _is_separate_data_root(app_root, app_data_root):
        return source
    if not source.is_relative_to(app_root.resolve()):
        return source
    if not source.is_file():
        raise FileNotFoundError(f"Bundled resource not found: {source}")

    destination = bundled_resource_destination(
        source,
        app_root=app_root,
        writable_resources_root=writable_resources_root,
    )
    if destination.exists():
        return destination

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    try:
        shutil.copy2(source, temporary)
        if not destination.exists():
            os.replace(temporary, destination)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    return destination


def provision_default_resource_files(
    *,
    app_root: Path,
    app_data_root: Path,
    writable_resources_root: Path,
) -> dict[str, str]:
    """Return default setting paths, provisioning editable copies as needed."""

    if not _is_separate_data_root(app_root, app_data_root):
        return dict(DEFAULT_RESOURCE_FILES)

    provisioned: dict[str, str] = {}
    for key, relative_path in DEFAULT_RESOURCE_FILES.items():
        if not relative_path:
            provisioned[key] = ""
            continue
        destination = provision_resource_for_edit(
            app_root / relative_path,
            app_root=app_root,
            app_data_root=app_data_root,
            writable_resources_root=writable_resources_root,
        )
        provisioned[key] = destination.as_posix()
    return provisioned
