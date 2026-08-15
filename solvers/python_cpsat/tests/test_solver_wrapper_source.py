from pathlib import Path

from solvers.python_cpsat.solver_wrapper import _result_class_id


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


def test_result_class_id_recovers_only_unambiguous_instructor_assignment():
    class_row = type("ClassRow", (), {"class_id": "00201", "instructor_id": "00301"})()
    assert _result_class_id({"instructor_id": "00301"}, {"row": class_row}) == "00201"

    other_row = type("ClassRow", (), {"class_id": "00202", "instructor_id": "00301"})()
    assert _result_class_id(
        {"instructor_id": "00301"},
        {"first": class_row, "second": other_row},
    ) is None


def test_result_class_id_preserves_explicit_leading_zero_string():
    assert _result_class_id({"class_id": "00021", "instructor_id": "00301"}, {}) == "00021"
