from pathlib import Path
import json

from fastapi.testclient import TestClient

import backend.server as server


def test_legacy_bundled_setting_migrates_to_provisioned_default(tmp_path, monkeypatch):
    app_root = tmp_path / "read-only-app"
    app_data_root = tmp_path / "user-data"
    provisioned = app_data_root / "resources" / "data" / "source" / "personality_colors.csv"
    provisioned.parent.mkdir(parents=True)
    provisioned.write_text("color_id,color_name,traits\n1,Red,Original\n", encoding="utf-8")
    settings_path = tmp_path / "legacy-settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "default_files": {"personality_colors": "data/source/personality_colors.csv"},
                "last_selected_files": {"personality_colors": "data/source/personality_colors.csv"},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(server, "APP_ROOT", app_root)
    monkeypatch.setattr(server, "APP_DATA_ROOT", app_data_root)
    monkeypatch.setattr(server, "SETTINGS_PATH", settings_path)
    monkeypatch.setitem(server.DEFAULT_FILE_PATHS, "personality_colors", provisioned.as_posix())

    loaded = server.load_settings()

    assert loaded["default_files"]["personality_colors"] == provisioned.as_posix()
    assert loaded["last_selected_files"]["personality_colors"] == provisioned.as_posix()


def test_reference_save_copy_on_writes_bundled_file(tmp_path, monkeypatch):
    app_root = tmp_path / "read-only-app"
    app_data_root = tmp_path / "user-data"
    source = app_root / "data" / "source" / "personality_colors.csv"
    source.parent.mkdir(parents=True)
    original = "color_id,color_name,traits\n1,Red,Original\n"
    source.write_text(original, encoding="utf-8")

    monkeypatch.setattr(server, "APP_ROOT", app_root)
    monkeypatch.setattr(server, "APP_DATA_ROOT", app_data_root)
    monkeypatch.setattr(server, "WRITABLE_RESOURCES_DIR", app_data_root / "resources")
    state = server.application_services.state
    with state.settings_lock:
        state.settings["default_files"]["personality_colors"] = str(source)
        state.settings["last_selected_files"]["personality_colors"] = str(source)

    response = TestClient(server.app).post(
        "/api/reference_table/save",
        json={
            "purpose": "personality_colors",
            "items": [
                {"id": "1", "fields": {"color_name": "Red", "traits": "Edited"}},
            ],
        },
    )

    assert response.status_code == 200
    assert source.read_text(encoding="utf-8") == original
    with state.settings_lock:
        selected = Path(state.settings["last_selected_files"]["personality_colors"])
    assert selected.is_relative_to(app_data_root)
    assert "Edited" in selected.read_text(encoding="utf-8")
