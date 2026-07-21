"""Narrow repository interface over the SQLite persistence layer.

Routers and services depend on this one object instead of importing the
~20 free functions in ``backend.db`` individually. The class is the single
sanctioned database entry point for the application; ``backend.db`` remains
the implementation module (admin scripts may still call it directly).

Limitation carried over from ``backend.db``: the connection path is a
module-level global there, so the most recently constructed repository
determines the process-wide database. There is exactly one database per
process today; making ``backend.db`` connection-scoped is a later refactor
that can now happen behind this interface without touching consumers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from backend import db


class SqliteRepository:
    """All database operations used by the FastAPI application."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        db.init_db(db_path)

    # -- Sessions / historical pairings --------------------------------------

    def save_session_pairings(self, matches: list[dict], label: str, **kwargs) -> int:
        return db.save_session_pairings(matches, label, **kwargs)

    def load_historical_pairings_csv(self, **kwargs) -> str:
        return db.load_historical_pairings_csv(**kwargs)

    def import_jackrabbit_pairings_csv(
        self, csv_text: str, imported_by: Optional[str] = None
    ) -> dict:
        return db.import_jackrabbit_pairings_csv(csv_text, imported_by=imported_by)

    def list_sessions_with_counts(self) -> list[dict]:
        return db.list_sessions_with_counts()

    def rename_session(self, session_id: int, new_label: str) -> Optional[dict]:
        return db.rename_session(session_id, new_label)

    def delete_session(self, session_id: int) -> bool:
        return db.delete_session(session_id)

    # -- Instructors ----------------------------------------------------------

    def list_instructors(self, needs_update_only: bool = False) -> list[dict]:
        return db.list_instructors(needs_update_only=needs_update_only)

    def get_instructor(self, instructor_id: str) -> Optional[dict]:
        return db.get_instructor(instructor_id)

    def update_instructor(
        self, instructor_id: str, fields: dict, *, updated_by: Optional[str] = None
    ) -> Optional[dict]:
        return db.update_instructor(instructor_id, fields, updated_by=updated_by)

    def count_instructors(self) -> int:
        return db.count_instructors()

    def instructor_stats(self) -> dict:
        return db.instructor_stats()

    def export_instructors_csv(self, **kwargs: Any) -> str:
        return db.export_instructors_csv(**kwargs)

    def export_instructors_solver_csv(self) -> str:
        return db.export_instructors_solver_csv()

    # -- Instructor imports ----------------------------------------------------

    def import_instructors_csv(self, csv_path: Path) -> int:
        return db.import_instructors_csv(csv_path)

    def preview_instructors_import(self, csv_text: str, **kwargs: Any) -> dict:
        return db.preview_instructors_import(csv_text, **kwargs)

    def apply_instructors_import(
        self, csv_text: str, accepted_ids: list, **kwargs: Any
    ) -> dict:
        return db.apply_instructors_import(csv_text, accepted_ids, **kwargs)

    def last_instructor_import(self) -> Optional[dict]:
        return db.last_instructor_import()

    def undo_instructors_import(self, history_id: Optional[int] = None) -> dict:
        return db.undo_instructors_import(history_id)
