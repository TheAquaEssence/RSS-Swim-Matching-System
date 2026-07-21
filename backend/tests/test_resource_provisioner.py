from pathlib import Path

from backend.services.resource_provisioner import (
    DEFAULT_RESOURCE_FILES,
    provision_default_resource_files,
    provision_resource_for_edit,
)


def test_bundled_resource_is_copied_outside_read_only_app(tmp_path):
    app_root = tmp_path / "application"
    app_data_root = tmp_path / "user-data"
    source = app_root / "data" / "source" / "personality_colors.csv"
    source.parent.mkdir(parents=True)
    source.write_text("color_id,color_name\n1,Red\n", encoding="utf-8")

    destination = provision_resource_for_edit(
        source,
        app_root=app_root,
        app_data_root=app_data_root,
        writable_resources_root=app_data_root / "resources",
    )

    assert destination == app_data_root / "resources" / "data" / "source" / source.name
    assert destination.read_bytes() == source.read_bytes()
    assert destination != source


def test_existing_writable_copy_is_never_overwritten(tmp_path):
    app_root = tmp_path / "application"
    app_data_root = tmp_path / "user-data"
    source = app_root / "data" / "source" / "swimmer_types.csv"
    source.parent.mkdir(parents=True)
    source.write_text("bundled", encoding="utf-8")

    destination = provision_resource_for_edit(
        source,
        app_root=app_root,
        app_data_root=app_data_root,
        writable_resources_root=app_data_root / "resources",
    )
    destination.write_text("user edit", encoding="utf-8")

    second_result = provision_resource_for_edit(
        source,
        app_root=app_root,
        app_data_root=app_data_root,
        writable_resources_root=app_data_root / "resources",
    )

    assert second_result == destination
    assert destination.read_text(encoding="utf-8") == "user edit"


def test_external_user_file_remains_in_place(tmp_path):
    app_root = tmp_path / "application"
    app_data_root = tmp_path / "user-data"
    external = tmp_path / "imports" / "instructors.csv"
    external.parent.mkdir()
    external.write_text("external", encoding="utf-8")

    result = provision_resource_for_edit(
        external,
        app_root=app_root,
        app_data_root=app_data_root,
        writable_resources_root=app_data_root / "resources",
    )

    assert result == external.resolve()
    assert not (app_data_root / "resources").exists()


def test_source_development_keeps_legacy_relative_defaults(tmp_path):
    defaults = provision_default_resource_files(
        app_root=tmp_path,
        app_data_root=tmp_path,
        writable_resources_root=tmp_path / "resources",
    )

    assert defaults == DEFAULT_RESOURCE_FILES
    assert not (tmp_path / "resources").exists()


def test_packaged_demo_files_are_provisioned_from_canonical_layout(tmp_path):
    app_root = tmp_path / "application"
    app_data_root = tmp_path / "user-data"
    for relative_path in DEFAULT_RESOURCE_FILES.values():
        if relative_path:
            source = app_root / relative_path
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("header\nvalue\n", encoding="utf-8")

    defaults = provision_default_resource_files(
        app_root=app_root,
        app_data_root=app_data_root,
        writable_resources_root=app_data_root / "resources",
    )

    assert defaults["classes"] == ""
    for key in ("swimmers", "instructors", "historical_pairings"):
        provisioned = Path(defaults[key])
        assert provisioned.is_relative_to(
            app_data_root / "resources" / "examples" / "demo" / "matching"
        )
        assert provisioned.is_file()
