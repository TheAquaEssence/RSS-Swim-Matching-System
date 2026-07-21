import json
import os
import subprocess
import sys
from pathlib import Path


def test_backend_runtime_state_uses_configured_application_data_root(tmp_path):
    app_data_root = tmp_path / "electron-user-data"
    environment = os.environ.copy()
    environment["AQUA_APP_DATA_DIR"] = str(app_data_root)
    script = """
import json
from backend import server
print(json.dumps({
    "app_root": str(server.APP_ROOT),
    "app_data_root": str(server.APP_DATA_ROOT),
    "jobs": str(server.JOBS_DIR),
    "settings": str(server.SETTINGS_PATH),
    "database": str(server.DB_PATH),
    "default_files": server.make_default_settings()["default_files"],
}))
"""

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[2],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    paths = json.loads(completed.stdout.strip())

    assert Path(paths["app_data_root"]) == app_data_root.resolve()
    assert Path(paths["app_root"]) != app_data_root.resolve()
    assert Path(paths["jobs"]) == app_data_root.resolve() / "jobs"
    assert Path(paths["settings"]) == app_data_root.resolve() / "settings" / "user_settings.json"
    assert Path(paths["database"]) == app_data_root.resolve() / "data" / "aqua_essence.db"
    assert Path(paths["jobs"]).is_dir()
    assert Path(paths["settings"]).parent.is_dir()
    assert Path(paths["database"]).is_file()
    for key, selected_path in paths["default_files"].items():
        if key == "classes":
            assert selected_path == ""
            continue
        selected = Path(selected_path)
        assert selected.is_relative_to(app_data_root.resolve())
        assert selected.is_file()
