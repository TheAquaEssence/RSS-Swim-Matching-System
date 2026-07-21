"""Direct tests for backend/services/repository.py."""
import subprocess
import sys
from pathlib import Path

from backend.services.repository import SqliteRepository


def make_repository(tmp_path) -> SqliteRepository:
    return SqliteRepository(tmp_path / "data" / "aqua_essence.db")


def test_constructor_initializes_schema(tmp_path):
    repository = make_repository(tmp_path)
    assert repository.db_path.exists()
    assert repository.list_sessions_with_counts() == []
    assert repository.count_instructors() == 0


def test_session_roundtrip(tmp_path):
    repository = make_repository(tmp_path)
    matches = [
        {"swimmer_id": 101, "instructor_id": 7},
        {"swimmer_id": 102, "instructor_id": 7},
    ]
    session_id = repository.save_session_pairings(matches, "Winter 2026")

    sessions = repository.list_sessions_with_counts()
    assert [s["id"] for s in sessions] == [session_id]
    assert sessions[0]["label"] == "Winter 2026"
    assert sessions[0]["pairing_count"] == 2

    csv_text = repository.load_historical_pairings_csv()
    assert "101" in csv_text and "102" in csv_text

    renamed = repository.rename_session(session_id, "Winter 2026 v2")
    assert renamed is not None and renamed["label"] == "Winter 2026 v2"
    assert repository.delete_session(session_id) is True
    assert repository.list_sessions_with_counts() == []


def test_instructor_roundtrip(tmp_path):
    repository = make_repository(tmp_path)
    csv_path = tmp_path / "instructors.csv"
    csv_path.write_text(
        "instructor_id,first_name,last_name,primary_color_id,secondary_color_id,"
        "primary_style_id,secondary_style_id,is_team_captain,can_teach_babies,"
        "can_teach_adults,can_teach_adapted\n"
        "I1,Alex,Rivera,1,2,6,5,0,1,1,1\n",
        encoding="utf-8",
    )
    assert repository.import_instructors_csv(csv_path) == 1
    assert repository.count_instructors() == 1

    instructor = repository.get_instructor("I1")
    assert instructor is not None and instructor["first_name"] == "Alex"

    updated = repository.update_instructor("I1", {"first_name": "Alexis"})
    assert updated is not None and updated["first_name"] == "Alexis"
    assert repository.list_instructors()[0]["first_name"] == "Alexis"
    assert "Alexis" in repository.export_instructors_solver_csv()


def test_repository_module_does_not_import_server():
    """Routers depend on the repository; it must not drag in the host."""
    code = (
        "import sys; import backend.services.repository; "
        "sys.exit(1 if 'backend.server' in sys.modules else 0)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(Path(__file__).resolve().parents[2]),
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr.decode()
