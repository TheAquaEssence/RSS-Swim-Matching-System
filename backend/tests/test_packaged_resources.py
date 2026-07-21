from pathlib import Path

from core.resource_paths import resolve_resource_root


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_resource_root_is_repository_root_in_source_checkout():
    assert resolve_resource_root() == REPOSITORY_ROOT


def test_resource_root_uses_pyinstaller_bundle_directory(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setattr("sys._MEIPASS", str(tmp_path), raising=False)

    assert resolve_resource_root() == tmp_path.resolve()


def test_pyinstaller_contract_includes_only_redistributable_data():
    spec = (REPOSITORY_ROOT / "packaging" / "pyinstaller" / "aqua-backend.spec").read_text(
        encoding="utf-8"
    )

    for required in ("frontend", "data/source", "examples/demo", "solvers/python_cpsat"):
        assert required in spec
    for private_or_runtime in ("instructors.csv", "pairings.csv", '"pytest"', '"faker"'):
        assert private_or_runtime in spec
    assert 'collect_dynamic_libs("ortools")' in spec
    assert '"backend.solver_worker"' in spec
    assert '"solvers.python_cpsat.solver_wrapper"' in spec


def test_packaging_dependency_is_pinned():
    requirements = (REPOSITORY_ROOT / "requirements-packaging.txt").read_text(encoding="utf-8")
    assert "PyInstaller==6.21.0" in requirements
    assert "-r requirements-runtime-lock.txt" in requirements


def test_backend_build_generates_release_metadata_before_pyinstaller():
    build_script = (
        REPOSITORY_ROOT / "packaging" / "pyinstaller" / "build_backend.ps1"
    ).read_text(encoding="utf-8")

    assert build_script.index("generate_release_metadata.py") < build_script.index("-m PyInstaller")
