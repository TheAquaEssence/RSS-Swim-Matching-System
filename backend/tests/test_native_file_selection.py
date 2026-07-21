"""Desktop-native file selection persists through the existing settings API."""

from fastapi.testclient import TestClient

import backend.server as server


def test_native_selected_path_is_persisted_without_opening_backend_picker(tmp_path, monkeypatch):
    selected = tmp_path / "classes.xlsx"
    selected.write_bytes(b"selected by Electron")

    def fail_if_called():
        raise AssertionError("backend picker must remain a browser-only fallback")

    monkeypatch.setattr(server, "pick_csv_file_win32", fail_if_called)
    with TestClient(server.create_app(server.application_services)) as client:
        response = client.post(
            "/api/pick_file",
            json={"purpose": "classes", "selected_path": str(selected)},
        )

        assert response.status_code == 200
        assert response.json() == {"ok": True}
        settings = client.get("/api/settings").json()
        assert settings["last_selected_files"]["classes"] == str(selected.resolve())


def test_native_selected_path_rejects_missing_and_unsupported_files(tmp_path):
    with TestClient(server.app) as client:
        for selected in (tmp_path / "missing.csv", tmp_path / "notes.txt"):
            if selected.suffix == ".txt":
                selected.write_text("not tabular", encoding="utf-8")
            response = client.post(
                "/api/pick_file",
                json={"purpose": "classes", "selected_path": str(selected)},
            )
            assert response.status_code == 400
            assert response.json() == {"ok": False, "error": "Invalid selected file"}


def test_native_reference_selection_accepts_csv_only(tmp_path):
    workbook = tmp_path / "colors.xlsx"
    workbook.write_bytes(b"not accepted for a CSV reference table")
    response = TestClient(server.app).post(
        "/api/pick_file",
        json={"purpose": "personality_colors", "selected_path": str(workbook)},
    )
    assert response.status_code == 400
    assert response.json() == {"ok": False, "error": "Invalid selected file"}


def test_native_selected_path_still_requires_whitelisted_purpose(tmp_path):
    selected = tmp_path / "classes.csv"
    selected.write_text("id\n", encoding="utf-8")
    response = TestClient(server.app).post(
        "/api/pick_file", json={"purpose": "../classes", "selected_path": str(selected)}
    )
    assert response.status_code == 400
    assert response.json()["error"] == "Invalid purpose"
