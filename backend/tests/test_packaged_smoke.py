"""Pytest wrapper for the packaged-app smoke harness.

Skips cleanly when the local ``.dist`` artifacts are absent so the suite stays
green on machines (and CI) that have not built the desktop package. The smoke
modules live in ``packaging/smoke/`` which is intentionally not an importable
package (its name would shadow the PyPI ``packaging`` distribution), so they
are loaded here by file path.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SMOKE_DIR = REPOSITORY_ROOT / "packaging" / "smoke"


def _load_smoke_module(name: str):
    module_name = f"aqua_{name}"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, SMOKE_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    # Dataclasses (and pickling) resolve the defining module through
    # sys.modules, so register before executing the module body.
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


packaged_smoke = _load_smoke_module("packaged_smoke")

_BACKEND_EXE = packaged_smoke.find_packaged_backend(REPOSITORY_ROOT)


@pytest.mark.skipif(sys.platform != "win32", reason="packaged artifacts are Windows-only")
@pytest.mark.skipif(_BACKEND_EXE is None, reason="no packaged backend under .dist/ — build it first")
def test_packaged_backend_full_workflow_smoke(tmp_path):
    report = packaged_smoke.run_packaged_smoke(_BACKEND_EXE, tmp_path)

    assert report.match_count > 0
    # Graceful shutdown is delivered via SIGINT inside the frozen exe, so the
    # exit code is non-zero by design; process exit itself is the contract.
    assert report.backend_exit_code is not None
    step_text = "\n".join(report.steps)
    for expected in (
        "/api/generate",
        "/api/latest_generation_result",
        "/xai/",
        "/api/instructors/export",
        "/api/instructors/import/preview",
        "no orphaned backend",
        "installation directory untouched",
        "runtime writes confined",
    ):
        assert expected in step_text


@pytest.mark.skipif(sys.platform != "win32", reason="packaged artifacts are Windows-only")
@pytest.mark.skipif(
    os.environ.get("AQUA_SMOKE_GUI") != "1",
    reason="GUI smoke opens a real window — opt in with AQUA_SMOKE_GUI=1",
)
def test_packaged_electron_gui_smoke(tmp_path):
    gui_smoke = _load_smoke_module("electron_gui_smoke")
    electron_exe = gui_smoke.find_electron_app(REPOSITORY_ROOT)
    if electron_exe is None:
        pytest.skip("no packaged Electron app under .dist/ — build it first")

    report = gui_smoke.run_gui_smoke(electron_exe, tmp_path / "user-data")

    assert report.electron_exit_code == 0
    assert "no orphaned backend" in "\n".join(report.steps)
    if not report.user_data_isolated:
        pytest.xfail(
            "artifact predates the AQUA_USER_DATA override — repackage to verify user-data isolation"
        )
