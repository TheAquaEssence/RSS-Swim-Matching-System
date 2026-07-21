from pathlib import Path


SOLVER_WRAPPER = Path(__file__).resolve().parents[1] / "solver_wrapper.py"


def test_solver_wrapper_uses_request_app_root_and_not_fixed_dirname_walk():
    source = SOLVER_WRAPPER.read_text(encoding="utf-8")
    assert 'request.get("app_root")' in source
    assert 'os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(request_path))))' not in source


def test_solver_wrapper_normalizes_result_file_paths_to_posix():
    source = SOLVER_WRAPPER.read_text(encoding="utf-8")
    assert "Path(os.path.relpath(path, app_root)).as_posix()" in source
    # Cross-drive fallback: relpath raises ValueError on Windows when the
    # job directory and app_root are on different drives.
    assert "Path(path).resolve().as_posix()" in source
    assert '"classes_filled": _to_contract_path(output_csv_path, app_root)' in source
