"""Direct tests for backend/services/storage.py (no server import needed)."""
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.services.storage import StorageService, read_csv_file, write_csv_file


def make_service(tmp_path, *, separate_data_root=True, default_file_paths=None):
    app_root = tmp_path / "app"
    app_root.mkdir(exist_ok=True)
    app_data_root = (tmp_path / "user-data") if separate_data_root else app_root
    app_data_root.mkdir(exist_ok=True)
    return StorageService(
        app_root=app_root,
        app_data_root=app_data_root,
        writable_resources_dir=app_data_root / "resources",
        settings_path=app_data_root / "settings" / "user_settings.json",
        default_file_paths=default_file_paths or {},
    )


# -- Path resolution ---------------------------------------------------------

def test_resolve_from_root_empty_and_absolute_and_relative(tmp_path):
    service = make_service(tmp_path)
    assert service.resolve_from_root("") == Path()
    absolute = tmp_path / "elsewhere" / "file.csv"
    assert service.resolve_from_root(str(absolute)) == absolute
    assert (
        service.resolve_from_root("data/x.csv")
        == (service.app_root / "data" / "x.csv").resolve()
    )


def test_file_exists_from_root(tmp_path):
    service = make_service(tmp_path)
    assert not service.file_exists_from_root("")
    assert not service.file_exists_from_root("data/missing.csv")
    target = service.app_root / "data" / "present.csv"
    target.parent.mkdir(parents=True)
    target.write_text("a\n", encoding="utf-8")
    assert service.file_exists_from_root("data/present.csv")


def test_normalize_path_for_request(tmp_path):
    service = make_service(tmp_path)
    assert service.normalize_path_for_request("") == ""
    assert service.normalize_path_for_request("data\\x.csv") == "data/x.csv"
    outside = (tmp_path / "outside.csv").resolve()
    assert service.normalize_path_for_request(str(outside)) == outside.as_posix()


def test_is_repo_sample_or_generated_path(tmp_path):
    service = make_service(tmp_path)
    assert service.is_repo_sample_or_generated_path(
        service.app_root / "examples" / "demo" / "matching" / "swimmers.csv"
    )
    assert service.is_repo_sample_or_generated_path(
        service.app_root / "data" / "generated" / "swimmers.csv"
    )
    assert not service.is_repo_sample_or_generated_path(
        service.app_root / "data" / "source" / "swimmers.csv"
    )


# -- Settings persistence ----------------------------------------------------

def test_save_settings_is_atomic_and_roundtrips(tmp_path):
    service = make_service(tmp_path)
    service.save_settings({"use_db_instructors": True})
    assert service.settings_path.exists()
    assert not list(service.settings_path.parent.glob("*.tmp"))
    assert service.read_settings_payload() == {"use_db_instructors": True}


def test_interrupted_settings_replace_preserves_last_complete_file(tmp_path):
    service = make_service(tmp_path)
    original = {"use_db_instructors": False}
    service.save_settings(original)

    with patch.object(os, "replace", side_effect=OSError("simulated interruption")):
        with pytest.raises(OSError, match="simulated interruption"):
            service.save_settings({"use_db_instructors": True})

    assert service.read_settings_payload() == original


def test_read_settings_payload_raises_on_missing_or_invalid(tmp_path):
    service = make_service(tmp_path)
    with pytest.raises(OSError):
        service.read_settings_payload()
    service.settings_path.parent.mkdir(parents=True)
    service.settings_path.write_text("not json", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        service.read_settings_payload()


# -- Bundled-resource rules --------------------------------------------------

def test_migrate_bundled_default_path_maps_legacy_to_provisioned(tmp_path):
    provisioned = tmp_path / "user-data" / "resources" / "data" / "source" / "personality_colors.csv"
    service = make_service(
        tmp_path,
        default_file_paths={"personality_colors": provisioned.as_posix()},
    )
    legacy = "data/source/personality_colors.csv"
    assert (
        service.migrate_bundled_default_path("personality_colors", legacy)
        == provisioned.as_posix()
    )
    # Unrelated external selections are preserved.
    external = (tmp_path / "custom.csv").as_posix()
    assert service.migrate_bundled_default_path("personality_colors", external) == external
    # Empty stays empty.
    assert service.migrate_bundled_default_path("personality_colors", "") == ""


def test_migrate_bundled_default_path_noop_in_source_development(tmp_path):
    service = make_service(tmp_path, separate_data_root=False)
    legacy = "data/source/personality_colors.csv"
    assert service.migrate_bundled_default_path("personality_colors", legacy) == legacy


def test_migrate_retired_app_sample_path_to_demo_default(tmp_path):
    replacement = "examples/demo/matching/swimmers.csv"
    service = make_service(
        tmp_path,
        separate_data_root=False,
        default_file_paths={"swimmers": replacement},
    )

    assert (
        service.migrate_bundled_default_path(
            "swimmers", "data/app_samples/swimmers.csv"
        )
        == replacement
    )


def test_provision_for_edit_copies_bundled_and_keeps_external(tmp_path):
    service = make_service(tmp_path)
    bundled = service.app_root / "data" / "source" / "personality_colors.csv"
    bundled.parent.mkdir(parents=True)
    bundled.write_text("color_id,color_name\n1,Red\n", encoding="utf-8")

    destination = service.provision_for_edit(bundled)
    assert destination != bundled
    assert destination.is_relative_to(service.writable_resources_dir)
    assert destination.read_text(encoding="utf-8") == bundled.read_text(encoding="utf-8")

    external = tmp_path / "external.csv"
    external.write_text("a\n", encoding="utf-8")
    assert service.provision_for_edit(external) == external.resolve()


# -- CSV helpers -------------------------------------------------------------

def test_csv_roundtrip_creates_parent_dirs(tmp_path):
    path = tmp_path / "nested" / "table.csv"
    write_csv_file(path, ["id", "name"], [{"id": "1", "name": "Red", "extra": "dropped"}])
    headers, rows = read_csv_file(path)
    assert headers == ["id", "name"]
    assert rows == [{"id": "1", "name": "Red"}]


# -- Isolation ---------------------------------------------------------------

def test_storage_module_does_not_import_server():
    """The service must stay usable without pulling in the whole host."""
    code = (
        "import sys; import backend.services.storage; "
        "sys.exit(1 if 'backend.server' in sys.modules else 0)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(Path(__file__).resolve().parents[2]),
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr.decode()
