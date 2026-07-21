from pathlib import Path

from core.app_paths import APP_DATA_ENV, build_app_data_paths, resolve_app_data_root


def test_source_development_defaults_to_resource_root(tmp_path):
    resource_root = tmp_path / "workspace"

    assert resolve_app_data_root(resource_root, environ={}) == resource_root.resolve()


def test_environment_override_selects_separate_writable_root(tmp_path):
    resource_root = tmp_path / "read-only-app"
    data_root = tmp_path / "writable-data"

    resolved = resolve_app_data_root(
        resource_root,
        environ={APP_DATA_ENV: str(data_root)},
    )

    assert resolved == data_root.resolve()
    assert resolved != resource_root.resolve()


def test_all_managed_writable_paths_derive_from_one_root(tmp_path):
    data_root = tmp_path / "electron-user-data"

    paths = build_app_data_paths(
        tmp_path / "read-only-app",
        environ={APP_DATA_ENV: str(data_root)},
    )

    assert paths.root == data_root.resolve()
    assert paths.jobs == paths.root / "jobs"
    assert paths.settings == paths.root / "settings" / "user_settings.json"
    assert paths.database == paths.root / "data" / "aqua_essence.db"
    assert paths.logs == paths.root / "logs"
    assert paths.resources == paths.root / "resources"
    for path in (paths.jobs, paths.settings, paths.database, paths.logs, paths.resources):
        assert path.is_relative_to(paths.root)


def test_blank_override_uses_resource_root(tmp_path):
    resource_root = Path(tmp_path) / "workspace"

    assert resolve_app_data_root(
        resource_root,
        environ={APP_DATA_ENV: "   "},
    ) == resource_root.resolve()
