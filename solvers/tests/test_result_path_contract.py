from pathlib import Path


SOLVER_WRAPPERS = [
    Path(__file__).resolve().parents[1] / "python_cpsat" / "solver_wrapper.py",
]


def test_all_python_solver_wrappers_normalize_result_paths_to_posix():
    for wrapper in SOLVER_WRAPPERS:
        source = wrapper.read_text(encoding="utf-8")
        assert "Path(os.path.relpath(path, app_root)).as_posix()" in source, wrapper.name
        # Cross-drive fallback: relpath raises ValueError on Windows when the
        # job directory and app_root are on different drives.
        assert "Path(path).resolve().as_posix()" in source, wrapper.name
