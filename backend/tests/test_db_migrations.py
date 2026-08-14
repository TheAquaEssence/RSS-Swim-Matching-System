"""Focused tests for the SQLite schema-version contract."""

import sqlite3

import pytest

from backend import db


def _schema_version(path) -> int:
    with sqlite3.connect(str(path)) as con:
        return int(con.execute("PRAGMA user_version").fetchone()[0])


def test_fresh_database_reaches_current_schema_version(tmp_path):
    path = tmp_path / "fresh.db"

    db.init_db(path)

    assert _schema_version(path) == db.CURRENT_SCHEMA_VERSION
    with sqlite3.connect(str(path)) as con:
        tables = {
            row[0]
            for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {"instructors", "sessions", "pairings", "instructor_import_history"} <= tables


def test_unversioned_database_upgrades_without_losing_data(tmp_path):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(str(path)) as con:
        con.execute(
            "CREATE TABLE instructors ("
            "instructor_id TEXT PRIMARY KEY, first_name TEXT NOT NULL, "
            "last_name TEXT NOT NULL DEFAULT '', primary_color_id INTEGER, "
            "secondary_color_id INTEGER, primary_style_id INTEGER, "
            "secondary_style_id INTEGER, is_team_captain INTEGER NOT NULL DEFAULT 0, "
            "can_teach_babies INTEGER NOT NULL DEFAULT 0, "
            "can_teach_adults INTEGER NOT NULL DEFAULT 0, "
            "can_teach_adapted INTEGER NOT NULL DEFAULT 0, "
            "used_default_profile INTEGER NOT NULL DEFAULT 1, "
            "profile_source INTEGER NOT NULL DEFAULT 1, updated_at TEXT)"
        )
        con.execute(
            "INSERT INTO instructors (instructor_id, first_name) VALUES ('legacy-1', 'Ada')"
        )

    db.init_db(path)

    assert _schema_version(path) == db.CURRENT_SCHEMA_VERSION
    with sqlite3.connect(str(path)) as con:
        con.row_factory = sqlite3.Row
        instructor = con.execute(
            "SELECT first_name, updated_by FROM instructors WHERE instructor_id = 'legacy-1'"
        ).fetchone()
        session_columns = {
            row[1] for row in con.execute("PRAGMA table_info(sessions)")
        }
    assert dict(instructor) == {"first_name": "Ada", "updated_by": None}
    assert "imported_by" in session_columns


def test_repeat_initialization_does_not_change_version_or_data(tmp_path):
    path = tmp_path / "repeat.db"
    db.init_db(path)
    with sqlite3.connect(str(path)) as con:
        con.execute(
            "INSERT INTO instructors (instructor_id, first_name) VALUES ('1', 'Grace')"
        )

    db.init_db(path)

    assert _schema_version(path) == db.CURRENT_SCHEMA_VERSION
    with sqlite3.connect(str(path)) as con:
        assert con.execute(
            "SELECT first_name FROM instructors WHERE instructor_id = '1'"
        ).fetchone()[0] == "Grace"


def test_schema_3_upgrades_pairing_ids_to_text_and_is_restart_safe(tmp_path):
    path = tmp_path / "schema-2.db"
    with sqlite3.connect(str(path)) as con:
        con.execute(
            "CREATE TABLE sessions ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, label TEXT NOT NULL, "
            "imported_at TEXT NOT NULL, imported_by TEXT)"
        )
        con.execute(
            "CREATE TABLE pairings ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "session_id INTEGER NOT NULL REFERENCES sessions(id), "
            "swimmer_id INTEGER NOT NULL, instructor_id INTEGER NOT NULL, "
            "class_slot TEXT, source TEXT NOT NULL DEFAULT 'solver')"
        )
        con.execute(
            "INSERT INTO sessions (id, label, imported_at) "
            "VALUES (7, 'Synthetic Legacy Session', '2026-01-01T00:00:00+00:00')"
        )
        con.execute(
            "INSERT INTO pairings "
            "(id, session_id, swimmer_id, instructor_id, class_slot, source) "
            "VALUES (11, 7, 101, 301, 'Monday 16:00', 'solver')"
        )
        con.execute("PRAGMA user_version = 2")

    db.init_db(path)
    db.init_db(path)

    assert _schema_version(path) == db.CURRENT_SCHEMA_VERSION
    with sqlite3.connect(str(path)) as con:
        con.row_factory = sqlite3.Row
        column_types = {
            row["name"]: row["type"] for row in con.execute("PRAGMA table_info(pairings)")
        }
        pairing = con.execute(
            "SELECT id, session_id, swimmer_id, instructor_id, class_id, class_slot, source "
            "FROM pairings"
        ).fetchone()
        indexes = {
            row[0]
            for row in con.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'index' AND tbl_name = 'pairings'"
            )
        }

    assert column_types["swimmer_id"] == "TEXT"
    assert column_types["instructor_id"] == "TEXT"
    assert column_types["class_id"] == "TEXT"
    assert dict(pairing) == {
        "id": 11,
        "session_id": 7,
        "swimmer_id": "101",
        "instructor_id": "301",
        "class_id": None,
        "class_slot": "Monday 16:00",
        "source": "solver",
    }
    assert {
        "idx_pairings_swimmer",
        "idx_pairings_instructor",
        "idx_pairings_session",
        "idx_pairings_unique",
    } <= indexes


def test_future_schema_version_is_rejected_without_modification(tmp_path):
    path = tmp_path / "future.db"
    future_version = db.CURRENT_SCHEMA_VERSION + 7
    with sqlite3.connect(str(path)) as con:
        con.execute("CREATE TABLE future_only (value TEXT)")
        con.execute("INSERT INTO future_only VALUES ('preserve me')")
        con.execute(f"PRAGMA user_version = {future_version}")

    with pytest.raises(db.DatabaseSchemaVersionError, match="newer"):
        db.init_db(path)

    assert _schema_version(path) == future_version
    with sqlite3.connect(str(path)) as con:
        assert con.execute("SELECT value FROM future_only").fetchone()[0] == "preserve me"
        assert con.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'instructors'"
        ).fetchone()[0] == 0


def test_failed_migration_rolls_back_schema_and_version(tmp_path, monkeypatch):
    path = tmp_path / "failed.db"
    db.init_db(path)

    def failing_migration(con):
        con.execute("CREATE TABLE must_be_rolled_back (value TEXT)")
        raise RuntimeError("simulated migration failure")

    monkeypatch.setattr(db, "_MIGRATIONS", (*db._MIGRATIONS, failing_migration))
    monkeypatch.setattr(db, "CURRENT_SCHEMA_VERSION", db.CURRENT_SCHEMA_VERSION + 1)

    with pytest.raises(RuntimeError, match="simulated migration failure"):
        db.init_db(path)

    assert _schema_version(path) == db.CURRENT_SCHEMA_VERSION - 1
    with sqlite3.connect(str(path)) as con:
        assert con.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type = 'table' AND name = 'must_be_rolled_back'"
        ).fetchone()[0] == 0
