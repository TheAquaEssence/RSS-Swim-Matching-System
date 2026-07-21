"""Persistent SQLite store for instructors and historical pairings.

Schema:
  instructors — one row per active instructor (keyed by Jackrabbit Staff ID)
  sessions    — one row per solver run or Jackrabbit import
  pairings    — one row per swimmer↔instructor pairing

The solver still receives flat CSVs as input; this module acts as the
persistence and accumulation layer.
"""
from __future__ import annotations

import csv
import difflib
import io
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


_INITIAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS instructors (
    instructor_id        TEXT    PRIMARY KEY,
    first_name           TEXT    NOT NULL,
    last_name            TEXT    NOT NULL DEFAULT '',
    primary_color_id     INTEGER,
    secondary_color_id   INTEGER,
    primary_style_id     INTEGER,
    secondary_style_id   INTEGER,
    is_team_captain      INTEGER NOT NULL DEFAULT 0,
    can_teach_babies     INTEGER NOT NULL DEFAULT 0,
    can_teach_adults     INTEGER NOT NULL DEFAULT 0,
    can_teach_adapted    INTEGER NOT NULL DEFAULT 0,
    used_default_profile INTEGER NOT NULL DEFAULT 1,
    profile_source       INTEGER NOT NULL DEFAULT 1,
    updated_at           TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    label       TEXT    NOT NULL,
    imported_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS pairings (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    INTEGER NOT NULL REFERENCES sessions(id),
    swimmer_id    INTEGER NOT NULL,
    instructor_id INTEGER NOT NULL,
    class_slot    TEXT,
    source        TEXT    NOT NULL DEFAULT 'solver'
);

CREATE TABLE IF NOT EXISTS instructor_import_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    imported_at TEXT    NOT NULL,
    summary     TEXT    NOT NULL,
    snapshot    TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pairings_swimmer    ON pairings(swimmer_id);
CREATE INDEX IF NOT EXISTS idx_pairings_instructor ON pairings(instructor_id);
CREATE INDEX IF NOT EXISTS idx_pairings_session    ON pairings(session_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_pairings_unique
    ON pairings(session_id, swimmer_id, instructor_id);
"""

# Columns the caller is allowed to update via update_instructor()
_INSTRUCTOR_EDITABLE = frozenset({
    "first_name", "last_name",
    "primary_color_id", "secondary_color_id",
    "primary_style_id", "secondary_style_id",
    "is_team_captain", "can_teach_babies", "can_teach_adults", "can_teach_adapted",
})

# All four profile fields must be non-null/non-empty for profile to be complete
_PROFILE_FIELDS = ("primary_color_id", "secondary_color_id", "primary_style_id", "secondary_style_id")

_HISTORICAL_PAIRINGS_HEADERS = ["swimmer_id", "instructor_id", "session", "num_sessions"]

_db_lock = threading.Lock()
_db_path: Optional[Path] = None


class DatabaseSchemaVersionError(RuntimeError):
    """Raised when a database was created by a newer application version."""


def _execute_sql_script(con: sqlite3.Connection, script: str) -> None:
    """Execute this module's static DDL without ``executescript`` auto-commits."""
    for statement in script.split(";"):
        if statement.strip():
            con.execute(statement)


def _migration_1_initial_schema(con: sqlite3.Connection) -> None:
    """Create the original, pre-attribution schema."""
    _execute_sql_script(con, _INITIAL_SCHEMA)


def _add_column_if_missing(
    con: sqlite3.Connection, table: str, column: str, declaration: str
) -> None:
    columns = {row[1] for row in con.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")


def _migration_2_operator_attribution(con: sqlite3.Connection) -> None:
    """Add optional operator attribution to persisted edits and imports."""
    for table, column, declaration in (
        ("instructors", "updated_by", "TEXT"),
        ("sessions", "imported_by", "TEXT"),
        ("instructor_import_history", "imported_by", "TEXT"),
    ):
        _add_column_if_missing(con, table, column, declaration)


# Position in this tuple is the schema version. Never reorder or rewrite a
# released migration; append a new callable and increment the version instead.
_MIGRATIONS = (
    _migration_1_initial_schema,
    _migration_2_operator_attribution,
)
CURRENT_SCHEMA_VERSION = len(_MIGRATIONS)


def init_db(path: Path) -> None:
    """Upgrade ``path`` to the current schema and select it for this process.

    Version zero represents both a new SQLite file and databases created
    before explicit schema versioning. Each migration commits independently,
    so a failed step rolls back and startup can safely retry it. A database
    from a newer application is rejected without modification.
    """
    global _db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    with _db_lock, sqlite3.connect(str(path), check_same_thread=False) as con:
        con.execute("PRAGMA foreign_keys = ON")
        current_version = int(con.execute("PRAGMA user_version").fetchone()[0])
        if current_version > CURRENT_SCHEMA_VERSION:
            raise DatabaseSchemaVersionError(
                "Database schema version "
                f"{current_version} is newer than this application supports "
                f"({CURRENT_SCHEMA_VERSION}). Install a compatible newer version "
                "of Aqua Essence; the database was not modified."
            )

        for target_version in range(current_version + 1, CURRENT_SCHEMA_VERSION + 1):
            try:
                con.execute("BEGIN IMMEDIATE")
                _MIGRATIONS[target_version - 1](con)
                con.execute(f"PRAGMA user_version = {target_version}")
                con.commit()
            except Exception:
                con.rollback()
                raise

    _db_path = path


def _connect() -> sqlite3.Connection:
    if _db_path is None:
        raise RuntimeError("db.init_db() has not been called")
    con = sqlite3.connect(str(_db_path), check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def save_session_pairings(
    matches: list[dict],
    label: str,
    source: str = "solver",
    imported_by: Optional[str] = None,
) -> int:
    """Persist a list of match dicts as a session.

    Reuses an existing session by label (replacing its pairings) so that
    re-running the solver with the same label doesn't accumulate duplicate
    sessions — consistent with the Jackrabbit import path.

    Handles both individual matches (swimmer_id) and pair matches
    (swimmer_1_id / swimmer_2_id).

    Returns the session_id.
    """
    now = datetime.now(timezone.utc).isoformat()
    rows: list[tuple] = []

    for m in matches:
        instr_id = m.get("instructor_id")
        if not instr_id:
            continue
        class_slot = m.get("class_slot") or m.get("day_of_week") or None

        s1 = m.get("swimmer_id") or m.get("swimmer_1_id")
        if s1:
            rows.append((int(s1), int(instr_id), class_slot, source))

        s2 = m.get("swimmer_2_id")
        if s2:
            rows.append((int(s2), int(instr_id), class_slot, source))

    with _db_lock, _connect() as con:
        existing = con.execute(
            "SELECT id FROM sessions WHERE label = ?", (label,)
        ).fetchone()
        if existing:
            session_id = existing["id"]
            con.execute("DELETE FROM pairings WHERE session_id = ?", (session_id,))
            con.execute(
                "UPDATE sessions SET imported_at = ?, imported_by = ? WHERE id = ?",
                (now, imported_by, session_id),
            )
        else:
            cur = con.execute(
                "INSERT INTO sessions (label, imported_at, imported_by) VALUES (?, ?, ?)",
                (label, now, imported_by),
            )
            session_id = cur.lastrowid
        con.executemany(
            "INSERT INTO pairings (session_id, swimmer_id, instructor_id, class_slot, source) "
            "VALUES (?, ?, ?, ?, ?)",
            [(session_id, swimmer, instr, slot, src) for swimmer, instr, slot, src in rows],
        )
        con.commit()

    return session_id


def load_historical_pairings_csv(
    lookback_sessions: Optional[int] = None,
    session_ids: Optional[list[int]] = None,
) -> str:
    """Return a historical_pairings.csv-compatible CSV string from the DB.

    Aggregates num_sessions per swimmer↔instructor pair (the same format the
    solver expects).

    Priority:
      session_ids     — if given, filter to exactly these session IDs
      lookback_sessions — if given (and session_ids is None), the N most recent sessions
      (neither)       — all sessions
    """
    with _connect() as con:
        if session_ids is not None:
            if not session_ids:
                # Explicit empty list → no sessions → return headers only
                rows = []
            else:
                placeholders = ",".join("?" * len(session_ids))
                rows = con.execute(
                    f"""
                    SELECT p.swimmer_id, p.instructor_id, s.label AS session, COUNT(*) AS num_sessions
                    FROM pairings p
                    JOIN sessions s ON s.id = p.session_id
                    WHERE p.session_id IN ({placeholders})
                    GROUP BY p.swimmer_id, p.instructor_id, s.label
                    ORDER BY p.swimmer_id
                    """,
                    session_ids,
                ).fetchall()
        elif lookback_sessions is not None and lookback_sessions > 0:
            rows = con.execute(
                """
                SELECT p.swimmer_id, p.instructor_id, s.label AS session, COUNT(*) AS num_sessions
                FROM pairings p
                JOIN sessions s ON s.id = p.session_id
                WHERE p.session_id IN (
                    SELECT id FROM sessions ORDER BY id DESC LIMIT ?
                )
                GROUP BY p.swimmer_id, p.instructor_id, s.label
                ORDER BY p.swimmer_id
                """,
                (lookback_sessions,),
            ).fetchall()
        else:
            rows = con.execute(
                """
                SELECT p.swimmer_id, p.instructor_id, s.label AS session, COUNT(*) AS num_sessions
                FROM pairings p
                JOIN sessions s ON s.id = p.session_id
                GROUP BY p.swimmer_id, p.instructor_id, s.label
                ORDER BY p.swimmer_id
                """,
            ).fetchall()

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=_HISTORICAL_PAIRINGS_HEADERS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({
            "swimmer_id":    row["swimmer_id"],
            "instructor_id": row["instructor_id"],
            "session":       row["session"],
            "num_sessions":  row["num_sessions"],
        })
    return output.getvalue()


def import_pairings_csv(
    csv_text: str,
    label: str,
    source: str = "jackrabbit_import",
    imported_by: Optional[str] = None,
) -> int:
    """Import a historical_pairings.csv-formatted CSV into the DB.

    Expected columns: swimmer_id, instructor_id (session and num_sessions optional).
    Returns the new session_id.
    """
    reader = csv.DictReader(io.StringIO(csv_text))
    required = {"swimmer_id", "instructor_id"}
    missing = required - set(reader.fieldnames or [])
    if missing:
        raise ValueError(f"CSV is missing required columns: {sorted(missing)}")

    matches: list[dict] = []
    for row in reader:
        try:
            matches.append({
                "swimmer_id":    row["swimmer_id"].strip(),
                "instructor_id": row["instructor_id"].strip(),
            })
        except (KeyError, AttributeError):
            continue

    return save_session_pairings(matches, label=label, source=source, imported_by=imported_by)


def import_jackrabbit_pairings_csv(csv_text: str, imported_by: Optional[str] = None) -> dict:
    """Import a Jackrabbit extension pairings CSV into the DB.

    Input columns (from the browser extension):
        swimmer_id, instructor_id, session   (required)
        class_id, class_name, status         (optional — stored / ignored)

    Behaviour:
    - Deduplicates by (swimmer_id, instructor_id, session) in memory.
    - Groups by the Jackrabbit session label (e.g. "Winter 2025").
    - Each unique session label is matched to an existing sessions row
      (by label + source='jackrabbit_import') or a new one is created.
    - INSERT OR IGNORE prevents duplicates on re-upload of the same CSV.
    - Rows missing swimmer_id, instructor_id, or session are skipped.

    Returns {"imported": int, "skipped": int, "sessions": list[str]}.
    """
    reader = csv.DictReader(io.StringIO(csv_text))
    fieldnames = set(reader.fieldnames or [])
    required = {"swimmer_id", "instructor_id", "session"}
    missing = required - fieldnames
    if missing:
        raise ValueError(f"CSV missing required columns: {sorted(missing)}")

    # Parse + deduplicate in memory
    seen: set[tuple] = set()
    by_session: dict[str, list[tuple]] = {}  # session_label -> [(swimmer_id, instructor_id, class_name)]
    skipped = 0

    for row in reader:
        sid   = row.get("swimmer_id",    "").strip()
        iid   = row.get("instructor_id", "").strip()
        sess  = row.get("session",       "").strip()
        cname = row.get("class_name",    "").strip()

        if not sid or not iid or not sess:
            skipped += 1
            continue

        try:
            int(sid); int(iid)          # must be numeric xIDs
        except ValueError:
            skipped += 1
            continue

        key = (sid, iid, sess)
        if key in seen:
            skipped += 1
            continue
        seen.add(key)
        by_session.setdefault(sess, []).append((sid, iid, cname))

    imported = 0
    session_labels: list[str] = []
    now = datetime.now(timezone.utc).isoformat()

    with _db_lock, _connect() as con:
        for sess_label, pairs in by_session.items():
            # Find existing session for this Jackrabbit label, or create one
            existing = con.execute(
                "SELECT id FROM sessions WHERE label = ?", (sess_label,)
            ).fetchone()
            if existing:
                session_id = existing["id"]
            else:
                cur = con.execute(
                    "INSERT INTO sessions (label, imported_at, imported_by) VALUES (?, ?, ?)",
                    (sess_label, now, imported_by),
                )
                session_id = cur.lastrowid

            for swimmer_id, instructor_id, class_name in pairs:
                try:
                    con.execute(
                        "INSERT OR IGNORE INTO pairings "
                        "(session_id, swimmer_id, instructor_id, class_slot, source) "
                        "VALUES (?, ?, ?, ?, 'jackrabbit_import')",
                        (session_id, int(swimmer_id), int(instructor_id), class_name or None),
                    )
                    imported += con.execute("SELECT changes()").fetchone()[0]
                except Exception:
                    skipped += 1

            session_labels.append(sess_label)
        con.commit()

    return {"imported": imported, "skipped": skipped, "sessions": session_labels}


def list_sessions() -> list[dict]:
    """Return all sessions ordered newest-first."""
    with _connect() as con:
        rows = con.execute(
            "SELECT id, label, imported_at FROM sessions ORDER BY id DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def list_sessions_with_counts() -> list[dict]:
    """Return all sessions ordered newest-first, each with a pairing_count field."""
    with _connect() as con:
        rows = con.execute(
            """
            SELECT s.id, s.label, s.imported_at, COUNT(p.id) AS pairing_count
            FROM sessions s
            LEFT JOIN pairings p ON p.session_id = s.id
            GROUP BY s.id
            ORDER BY s.id DESC
            """
        ).fetchall()
    return [dict(r) for r in rows]


def rename_session(session_id: int, new_label: str) -> Optional[dict]:
    """Rename a session. Returns the updated row, or None if it doesn't exist.

    Raises ValueError when the label is empty or already used by another
    session (labels are the dedupe key for solver saves and imports).
    """
    label = (new_label or "").strip()
    if not label:
        raise ValueError("Session label cannot be empty")

    with _db_lock, _connect() as con:
        row = con.execute(
            "SELECT id FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if row is None:
            return None
        clash = con.execute(
            "SELECT id FROM sessions WHERE label = ? AND id != ?", (label, session_id)
        ).fetchone()
        if clash:
            raise ValueError(f"Another session is already named '{label}'")
        con.execute("UPDATE sessions SET label = ? WHERE id = ?", (label, session_id))
        con.commit()
        updated = con.execute(
            "SELECT id, label, imported_at FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
    return dict(updated)


def delete_session(session_id: int) -> bool:
    """Delete a session and all of its pairings. Returns False if not found."""
    with _db_lock, _connect() as con:
        row = con.execute(
            "SELECT id FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if row is None:
            return False
        con.execute("DELETE FROM pairings WHERE session_id = ?", (session_id,))
        con.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        con.commit()
    return True


# ---------------------------------------------------------------------------
# Instructor CRUD
# ---------------------------------------------------------------------------


def _instructor_row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    # Expose a convenience flag for the frontend
    d["needs_update"] = bool(d.get("profile_source", 1) != 0)
    return d


def _int_or_none(val: Any) -> Optional[int]:
    v = str(val or "").strip()
    try:
        return int(v) if v else None
    except ValueError:
        return None


def _bool_int(val: Any) -> int:
    v = str(val or "").strip()
    return 1 if v in ("1", "true", "True", "yes") else 0


# Fields compared/written by the CSV import (derived fields are recomputed)
_IMPORT_NAME_FIELDS = ("first_name", "last_name")
_IMPORT_BOOL_FIELDS = ("is_team_captain", "can_teach_babies", "can_teach_adults", "can_teach_adapted")
_IMPORT_FIELDS = _IMPORT_NAME_FIELDS + _PROFILE_FIELDS + _IMPORT_BOOL_FIELDS

# Human-friendly CSV headers accepted for the profile id columns
_PROFILE_FIELD_ALIASES = {
    "primary_color_id":   ("primary_color_id", "primary_color"),
    "secondary_color_id": ("secondary_color_id", "secondary_color"),
    "primary_style_id":   ("primary_style_id", "primary_style"),
    "secondary_style_id": ("secondary_style_id", "secondary_style"),
}

_CAPABILITY_TRUE_VALUES = {"1", "true", "t", "yes", "y", "x"}
_CAPABILITY_FALSE_VALUES = {"0", "false", "f", "no", "n", ""}


def _parse_capability(value: Any, field: str, row_num: int, warnings: list[str]) -> int:
    """Parse X/blank, T/F, True/False, Yes/No, or 1/0 into 1/0."""
    v = str(value or "").strip().lower()
    if v in _CAPABILITY_TRUE_VALUES:
        return 1
    if v in _CAPABILITY_FALSE_VALUES:
        return 0
    warnings.append(f"Row {row_num}: unrecognized {field} value {str(value).strip()!r} — treated as No")
    return 0


def _resolve_reference_value(
    raw: Any,
    lookup: Optional[dict],
    field: str,
    row_num: int,
    warnings: list[str],
) -> Optional[int]:
    """
    Resolve a color/style cell into an id. Accepts a numeric id or a name.
    `lookup` maps lowercase name → (id, canonical_name). Misspellings within
    fuzzy-match range are accepted with a confirmation warning.
    """
    v = str(raw or "").strip()
    if not v:
        return None
    try:
        return int(v)
    except ValueError:
        pass
    label = field.removesuffix("_id")  # match the human CSV header, e.g. primary_color
    if not lookup:
        warnings.append(f"Row {row_num}: {label} {v!r} could not be resolved (no reference data loaded) — left empty")
        return None
    key = " ".join(v.split()).lower()
    if key in lookup:
        return lookup[key][0]
    close = difflib.get_close_matches(key, lookup.keys(), n=1, cutoff=0.7)
    if close:
        ref_id, canonical = lookup[close[0]]
        warnings.append(f"Row {row_num}: {label} {v!r} interpreted as '{canonical}' — please confirm")
        return ref_id
    known = ", ".join(sorted(canonical for _, canonical in lookup.values()))
    warnings.append(f"Row {row_num}: {label} {v!r} is not a known name (known: {known}) — left empty")
    return None


def _derived_profile_fields(row: dict) -> tuple[int, int]:
    """Return (used_default_profile, profile_source) derived from the four profile fields."""
    filled = [row.get(f) not in (None, "", 0) for f in _PROFILE_FIELDS]
    if all(filled):
        return 0, 0
    return 1, (2 if any(filled) else 1)


def parse_instructors_csv_text(
    csv_text: str,
    color_lookup: Optional[dict] = None,
    style_lookup: Optional[dict] = None,
) -> tuple[list[dict], list[str]]:
    """
    Parse instructors CSV text into normalized row dicts.
    Returns (rows, warnings). Raises ValueError on missing required columns.
    Duplicate instructor_id rows are collapsed (last row wins, with a warning).

    Accepts both machine and human-friendly formats:
    - capability columns: 1/0, True/False, T/F, Yes/No, X/blank
    - color/style columns: numeric ids or names (headers primary_color_id or
      primary_color, etc.); lookups map lowercase name → (id, canonical_name)
    """
    reader = csv.DictReader(io.StringIO(csv_text.lstrip('﻿')))
    required = {"instructor_id", "first_name"}
    missing = required - set(reader.fieldnames or [])
    if missing:
        raise ValueError(f"Instructor CSV is missing columns: {sorted(missing)}")

    lookups = {
        "primary_color_id": color_lookup, "secondary_color_id": color_lookup,
        "primary_style_id": style_lookup, "secondary_style_id": style_lookup,
    }

    warnings: list[str] = []
    by_id: dict[str, dict] = {}
    for row_num, r in enumerate(reader, start=2):
        iid = str(r.get("instructor_id") or "").strip()
        if not iid:
            warnings.append(f"Row {row_num}: skipped — missing instructor_id")
            continue
        if iid in by_id:
            warnings.append(f"Row {row_num}: duplicate instructor_id {iid} — later row replaces earlier one")

        row: dict[str, Any] = {"instructor_id": iid}
        for f in _IMPORT_NAME_FIELDS:
            row[f] = str(r.get(f) or "").strip()
        for f in _PROFILE_FIELDS:
            raw = next((r[alias] for alias in _PROFILE_FIELD_ALIASES[f] if alias in r), None)
            row[f] = _resolve_reference_value(raw, lookups[f], f, row_num, warnings)
        for f in _IMPORT_BOOL_FIELDS:
            row[f] = _parse_capability(r.get(f), f, row_num, warnings)
        by_id[iid] = row

    return list(by_id.values()), warnings


def preview_instructors_import(
    csv_text: str,
    color_lookup: Optional[dict] = None,
    style_lookup: Optional[dict] = None,
) -> dict:
    """
    Compare an instructors CSV against the current DB without writing anything.
    Returns a diff payload:
      new        — rows whose instructor_id is not in the DB
      changed    — rows that differ, with field-level old/new values
      unchanged  — count of identical rows
      missing_from_csv — instructors in the DB but absent from the CSV (never deleted)
      warnings   — parse warnings (skipped/duplicate rows, name interpretations)
    """
    rows, warnings = parse_instructors_csv_text(csv_text, color_lookup, style_lookup)
    existing = {i["instructor_id"]: i for i in list_instructors()}

    new_rows: list[dict] = []
    changed: list[dict] = []
    unchanged = 0
    seen_ids: set[str] = set()

    for row in rows:
        seen_ids.add(row["instructor_id"])
        current = existing.get(row["instructor_id"])
        if current is None:
            new_rows.append(dict(row))
            continue
        changes = []
        for f in _IMPORT_FIELDS:
            old_val = current.get(f)
            new_val = row.get(f)
            if f in _IMPORT_NAME_FIELDS:
                old_val = str(old_val or "").strip()
            elif f in _IMPORT_BOOL_FIELDS:
                old_val = 1 if old_val else 0
            if old_val != new_val:
                changes.append({"field": f, "old": old_val, "new": new_val})
        if changes:
            changed.append(
                {
                    "instructor_id": row["instructor_id"],
                    "name": " ".join(p for p in (row["first_name"], row["last_name"]) if p),
                    "current_name": " ".join(
                        p for p in (str(current.get("first_name") or "").strip(),
                                    str(current.get("last_name") or "").strip()) if p
                    ),
                    "changes": changes,
                }
            )
        else:
            unchanged += 1

    missing_from_csv = [
        {
            "instructor_id": iid,
            "name": " ".join(
                p for p in (str(inst.get("first_name") or "").strip(),
                            str(inst.get("last_name") or "").strip()) if p
            ),
        }
        for iid, inst in existing.items()
        if iid not in seen_ids
    ]

    return {
        "new": new_rows,
        "changed": changed,
        "unchanged": unchanged,
        "missing_from_csv": missing_from_csv,
        "total_rows": len(rows),
        "warnings": warnings,
    }


def apply_instructors_import(
    csv_text: str,
    accepted: list,
    color_lookup: Optional[dict] = None,
    style_lookup: Optional[dict] = None,
    imported_by: Optional[str] = None,
) -> dict:
    """
    Upsert only the accepted instructor rows from the CSV into the DB.

    Each entry in `accepted` is either:
      - a plain instructor_id string — take the full CSV row, or
      - {"instructor_id": "...", "fields": ["last_name", ...]} — for existing
        instructors, take only those fields from the CSV and keep the rest of
        the DB row as-is. An empty/unknown field list means nothing to apply.

    used_default_profile and profile_source are recomputed from the merged
    profile fields (CSV values for those columns are ignored).

    Before writing, the previous state of every affected row is snapshotted
    into instructor_import_history so the import can be undone.
    Returns {"created": n, "updated": n, "history_id": id}.
    """
    rows, _ = parse_instructors_csv_text(csv_text, color_lookup, style_lookup)
    rows_by_id = {r["instructor_id"]: r for r in rows}

    requested: dict[str, Optional[list[str]]] = {}
    for entry in accepted:
        if isinstance(entry, dict):
            iid = str(entry.get("instructor_id", "")).strip()
            fields = entry.get("fields")
            fields = [f for f in fields if f in _IMPORT_FIELDS] if isinstance(fields, list) else None
        else:
            iid = str(entry).strip()
            fields = None
        if iid:
            requested[iid] = fields

    now = datetime.now(timezone.utc).isoformat()
    created = updated = 0
    created_ids: list[str] = []
    previous_rows: list[dict] = []

    with _db_lock, _connect() as con:
        existing_ids = {
            r["instructor_id"] for r in con.execute("SELECT instructor_id FROM instructors").fetchall()
        }
        for iid, fields in requested.items():
            row = rows_by_id.get(iid)
            if row is None:
                continue
            if fields is not None and not fields:
                continue  # explicit empty selection — nothing to apply
            if iid in existing_ids:
                before = con.execute(
                    "SELECT * FROM instructors WHERE instructor_id = ?", (iid,)
                ).fetchone()
                previous_rows.append(dict(before))
            else:
                created_ids.append(iid)
            if fields is not None and iid in existing_ids:
                existing = con.execute(
                    "SELECT * FROM instructors WHERE instructor_id = ?", (iid,)
                ).fetchone()
                merged = {f: existing[f] for f in _IMPORT_FIELDS}
                merged["instructor_id"] = iid
                for f in fields:
                    merged[f] = row[f]
                row = merged
            used_default, profile_source = _derived_profile_fields(row)
            con.execute(
                """
                INSERT INTO instructors (
                    instructor_id, first_name, last_name,
                    primary_color_id, secondary_color_id,
                    primary_style_id, secondary_style_id,
                    is_team_captain, can_teach_babies, can_teach_adults, can_teach_adapted,
                    used_default_profile, profile_source, updated_at, updated_by
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(instructor_id) DO UPDATE SET
                    first_name           = excluded.first_name,
                    last_name            = excluded.last_name,
                    primary_color_id     = excluded.primary_color_id,
                    secondary_color_id   = excluded.secondary_color_id,
                    primary_style_id     = excluded.primary_style_id,
                    secondary_style_id   = excluded.secondary_style_id,
                    is_team_captain      = excluded.is_team_captain,
                    can_teach_babies     = excluded.can_teach_babies,
                    can_teach_adults     = excluded.can_teach_adults,
                    can_teach_adapted    = excluded.can_teach_adapted,
                    used_default_profile = excluded.used_default_profile,
                    profile_source       = excluded.profile_source,
                    updated_at           = excluded.updated_at,
                    updated_by           = excluded.updated_by
                """,
                (
                    row["instructor_id"],
                    row["first_name"],
                    row["last_name"],
                    row["primary_color_id"],
                    row["secondary_color_id"],
                    row["primary_style_id"],
                    row["secondary_style_id"],
                    row["is_team_captain"],
                    row["can_teach_babies"],
                    row["can_teach_adults"],
                    row["can_teach_adapted"],
                    used_default,
                    profile_source,
                    now,
                    imported_by,
                ),
            )
            if row["instructor_id"] in existing_ids:
                updated += 1
            else:
                created += 1

        history_id = None
        if created or updated:
            summary = f"{created} added, {updated} updated"
            snapshot = json.dumps({"created_ids": created_ids, "previous_rows": previous_rows})
            cur = con.execute(
                "INSERT INTO instructor_import_history (imported_at, summary, snapshot, imported_by) "
                "VALUES (?,?,?,?)",
                (now, summary, snapshot, imported_by),
            )
            history_id = cur.lastrowid
            # keep only the most recent imports
            con.execute(
                "DELETE FROM instructor_import_history WHERE id NOT IN "
                "(SELECT id FROM instructor_import_history ORDER BY id DESC LIMIT 10)"
            )
        con.commit()

    return {"created": created, "updated": updated, "history_id": history_id}


def last_instructor_import() -> Optional[dict]:
    """Return {id, imported_at, summary, imported_by} for the most recent undoable import, or None."""
    with _connect() as con:
        row = con.execute(
            "SELECT id, imported_at, summary, imported_by FROM instructor_import_history "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def undo_instructors_import(history_id: Optional[int] = None) -> dict:
    """
    Revert an instructor import: rows it created are deleted, rows it changed
    are restored to their snapshotted state. Defaults to the most recent
    import. The history entry is consumed (an undo cannot itself be undone).
    Returns {"restored": n, "removed": n, "summary": str}.
    """
    with _db_lock, _connect() as con:
        if history_id is None:
            row = con.execute(
                "SELECT * FROM instructor_import_history ORDER BY id DESC LIMIT 1"
            ).fetchone()
        else:
            row = con.execute(
                "SELECT * FROM instructor_import_history WHERE id = ?", (int(history_id),)
            ).fetchone()
        if row is None:
            raise ValueError("No import to undo")

        snapshot = json.loads(row["snapshot"])
        created_ids = snapshot.get("created_ids", [])
        previous_rows = snapshot.get("previous_rows", [])

        removed = 0
        for iid in created_ids:
            cur = con.execute("DELETE FROM instructors WHERE instructor_id = ?", (str(iid),))
            removed += cur.rowcount
        for prev in previous_rows:
            con.execute(
                """
                INSERT INTO instructors (
                    instructor_id, first_name, last_name,
                    primary_color_id, secondary_color_id,
                    primary_style_id, secondary_style_id,
                    is_team_captain, can_teach_babies, can_teach_adults, can_teach_adapted,
                    used_default_profile, profile_source, updated_at, updated_by
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(instructor_id) DO UPDATE SET
                    first_name           = excluded.first_name,
                    last_name            = excluded.last_name,
                    primary_color_id     = excluded.primary_color_id,
                    secondary_color_id   = excluded.secondary_color_id,
                    primary_style_id     = excluded.primary_style_id,
                    secondary_style_id   = excluded.secondary_style_id,
                    is_team_captain      = excluded.is_team_captain,
                    can_teach_babies     = excluded.can_teach_babies,
                    can_teach_adults     = excluded.can_teach_adults,
                    can_teach_adapted    = excluded.can_teach_adapted,
                    used_default_profile = excluded.used_default_profile,
                    profile_source       = excluded.profile_source,
                    updated_at           = excluded.updated_at,
                    updated_by           = excluded.updated_by
                """,
                (
                    prev["instructor_id"],
                    prev.get("first_name", ""),
                    prev.get("last_name", ""),
                    prev.get("primary_color_id"),
                    prev.get("secondary_color_id"),
                    prev.get("primary_style_id"),
                    prev.get("secondary_style_id"),
                    prev.get("is_team_captain", 0),
                    prev.get("can_teach_babies", 0),
                    prev.get("can_teach_adults", 0),
                    prev.get("can_teach_adapted", 0),
                    prev.get("used_default_profile", 1),
                    prev.get("profile_source", 1),
                    prev.get("updated_at"),
                    prev.get("updated_by"),
                ),
            )
        con.execute("DELETE FROM instructor_import_history WHERE id = ?", (row["id"],))
        con.commit()

    return {"restored": len(previous_rows), "removed": removed, "summary": row["summary"]}


def import_instructors_csv(csv_path: Path) -> int:
    """
    Load (or reload) instructors from the enriched CSV produced by
    scripts/enrich_instructors.py.  Uses UPSERT so re-runs are safe.
    Returns the number of rows upserted.
    """
    required = {"instructor_id", "first_name"}
    count = 0
    now = datetime.now(timezone.utc).isoformat()

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Instructor CSV is missing columns: {sorted(missing)}")

        rows = list(reader)

    with _db_lock, _connect() as con:
        for r in rows:
            con.execute(
                """
                INSERT INTO instructors (
                    instructor_id, first_name, last_name,
                    primary_color_id, secondary_color_id,
                    primary_style_id, secondary_style_id,
                    is_team_captain, can_teach_babies, can_teach_adults, can_teach_adapted,
                    used_default_profile, profile_source, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(instructor_id) DO UPDATE SET
                    first_name           = excluded.first_name,
                    last_name            = excluded.last_name,
                    primary_color_id     = excluded.primary_color_id,
                    secondary_color_id   = excluded.secondary_color_id,
                    primary_style_id     = excluded.primary_style_id,
                    secondary_style_id   = excluded.secondary_style_id,
                    is_team_captain      = excluded.is_team_captain,
                    can_teach_babies     = excluded.can_teach_babies,
                    can_teach_adults     = excluded.can_teach_adults,
                    can_teach_adapted    = excluded.can_teach_adapted,
                    used_default_profile = excluded.used_default_profile,
                    profile_source       = excluded.profile_source,
                    updated_at           = excluded.updated_at
                """,
                (
                    r["instructor_id"].strip(),
                    r.get("first_name", "").strip(),
                    r.get("last_name", "").strip(),
                    _int_or_none(r.get("primary_color_id", "")),
                    _int_or_none(r.get("secondary_color_id", "")),
                    _int_or_none(r.get("primary_style_id", "")),
                    _int_or_none(r.get("secondary_style_id", "")),
                    _bool_int(r.get("is_team_captain", "0")),
                    _bool_int(r.get("can_teach_babies", "0")),
                    _bool_int(r.get("can_teach_adults", "0")),
                    _bool_int(r.get("can_teach_adapted", "0")),
                    _bool_int(r.get("used_default_profile", "1")),
                    int(r.get("profile_source", "1") or "1"),
                    now,
                ),
            )
            count += 1
        con.commit()

    return count


def list_instructors(needs_update_only: bool = False) -> list[dict]:
    """Return all instructors, optionally filtered to those needing a profile update."""
    with _connect() as con:
        if needs_update_only:
            rows = con.execute(
                "SELECT * FROM instructors WHERE profile_source != 0 ORDER BY last_name, first_name"
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM instructors ORDER BY last_name, first_name"
            ).fetchall()
    return [_instructor_row_to_dict(r) for r in rows]


def get_instructor(instructor_id: str) -> Optional[dict]:
    """Return a single instructor dict or None if not found."""
    with _connect() as con:
        row = con.execute(
            "SELECT * FROM instructors WHERE instructor_id = ?", (str(instructor_id),)
        ).fetchone()
    return _instructor_row_to_dict(row) if row else None


def update_instructor(
    instructor_id: str,
    fields: dict[str, Any],
    updated_by: Optional[str] = None,
) -> Optional[dict]:
    """
    Update editable fields on an instructor row.
    Automatically recalculates used_default_profile and profile_source from
    the four profile fields after the update. updated_by records who made the
    change (None when no operator name was provided).
    Returns the updated instructor dict, or None if not found.
    """
    # Filter to allowed fields only
    allowed = {k: v for k, v in fields.items() if k in _INSTRUCTOR_EDITABLE}
    if not allowed:
        return get_instructor(instructor_id)

    now = datetime.now(timezone.utc).isoformat()

    with _db_lock, _connect() as con:
        # Check exists
        existing = con.execute(
            "SELECT * FROM instructors WHERE instructor_id = ?", (str(instructor_id),)
        ).fetchone()
        if existing is None:
            return None

        # Build merged state to recalculate derived fields
        merged = dict(existing)
        merged.update(allowed)

        all_filled = all(
            merged.get(f) not in (None, "", 0)
            for f in _PROFILE_FIELDS
        )
        used_default  = 0 if all_filled else 1
        profile_source = 0 if all_filled else (
            2 if any(merged.get(f) not in (None, "", 0) for f in _PROFILE_FIELDS)
            else 1
        )

        # Apply update
        set_clause = ", ".join(f"{k} = ?" for k in allowed)
        values = list(allowed.values())
        con.execute(
            f"UPDATE instructors SET {set_clause}, "
            f"used_default_profile = ?, profile_source = ?, updated_at = ?, updated_by = ? "
            f"WHERE instructor_id = ?",
            values + [used_default, profile_source, now, updated_by, str(instructor_id)],
        )
        con.commit()

    return get_instructor(instructor_id)


def export_instructors_solver_csv() -> str:
    """
    Return instructors as CSV in the solver's expected format (includes the
    can_teach_NL column, which the DB does not track — defaulted to 1).
    """
    headers = [
        "instructor_id", "first_name", "last_name",
        "primary_color_id", "secondary_color_id", "primary_style_id", "secondary_style_id",
        "is_team_captain", "can_teach_NL", "can_teach_babies", "can_teach_adults", "can_teach_adapted",
        "used_default_profile",
    ]
    rows = list_instructors()
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=headers, lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow({**r, "can_teach_NL": 1})
    return out.getvalue()


def count_instructors() -> int:
    """Return the number of instructors in the DB."""
    with _connect() as con:
        row = con.execute("SELECT COUNT(*) AS n FROM instructors").fetchone()
    return int(row["n"])


def instructor_stats() -> dict:
    """Aggregate staffing counts for the staffing overview.

    Returns totals, profile completeness, capability counts, and per-id
    color/style distributions (primary and secondary counted separately;
    id None means the field is unset).
    """
    def _distribution(con: sqlite3.Connection, primary_col: str, secondary_col: str) -> list[dict]:
        counts: dict[Optional[int], dict] = {}
        for col, key in ((primary_col, "primary"), (secondary_col, "secondary")):
            for row in con.execute(
                f"SELECT {col} AS id, COUNT(*) AS n FROM instructors GROUP BY {col}"
            ):
                entry = counts.setdefault(row["id"], {"id": row["id"], "primary": 0, "secondary": 0})
                entry[key] = row["n"]
        # Unset ids last, otherwise by id for a stable order
        return sorted(counts.values(), key=lambda e: (e["id"] is None, e["id"] or 0))

    with _connect() as con:
        totals = con.execute(
            "SELECT COUNT(*) AS total, "
            "COALESCE(SUM(CASE WHEN profile_source = 0 THEN 1 ELSE 0 END), 0) AS complete, "
            "COALESCE(SUM(can_teach_babies), 0)  AS babies, "
            "COALESCE(SUM(can_teach_adults), 0)  AS adults, "
            "COALESCE(SUM(can_teach_adapted), 0) AS adapted, "
            "COALESCE(SUM(is_team_captain), 0)   AS captains "
            "FROM instructors"
        ).fetchone()
        colors = _distribution(con, "primary_color_id", "secondary_color_id")
        styles = _distribution(con, "primary_style_id", "secondary_style_id")

    return {
        "total": totals["total"],
        "complete": totals["complete"],
        "capabilities": {
            "can_teach_babies":  totals["babies"],
            "can_teach_adults":  totals["adults"],
            "can_teach_adapted": totals["adapted"],
            "is_team_captain":   totals["captains"],
        },
        "colors": colors,
        "styles": styles,
    }


def export_instructors_csv(
    needs_update_only: bool = False,
    name_query: str = "",
    color_names: Optional[dict] = None,
    style_names: Optional[dict] = None,
) -> str:
    """
    Return a human-friendly CSV of instructors for editing in a spreadsheet:
    - capability columns use 'X' (can teach) / blank (can't)
    - color/style columns contain names when id→name maps are provided
      (falling back to the raw id), under primary_color/primary_style headers
    - derived columns (used_default_profile) are omitted

    Optional filters mirror the Manage Instructors view: needs_update_only
    keeps incomplete profiles, name_query is a case-insensitive substring
    match on "first last". The import parser accepts everything this emits.
    """
    headers = [
        "instructor_id", "first_name", "last_name",
        "primary_color", "secondary_color", "primary_style", "secondary_style",
        "is_team_captain", "can_teach_babies", "can_teach_adults", "can_teach_adapted",
    ]
    rows = list_instructors(needs_update_only=needs_update_only)
    q = str(name_query or "").strip().lower()
    if q:
        rows = [r for r in rows if q in f"{r.get('first_name', '')} {r.get('last_name', '')}".lower()]

    def ref_name(value, names):
        if value in (None, ""):
            return ""
        if names:
            return names.get(int(value), str(value))
        return str(value)

    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=headers, lineterminator="\n")
    writer.writeheader()
    for r in rows:
        writer.writerow({
            "instructor_id": r["instructor_id"],
            "first_name": r.get("first_name", ""),
            "last_name": r.get("last_name", ""),
            "primary_color": ref_name(r.get("primary_color_id"), color_names),
            "secondary_color": ref_name(r.get("secondary_color_id"), color_names),
            "primary_style": ref_name(r.get("primary_style_id"), style_names),
            "secondary_style": ref_name(r.get("secondary_style_id"), style_names),
            "is_team_captain": "X" if r.get("is_team_captain") else "",
            "can_teach_babies": "X" if r.get("can_teach_babies") else "",
            "can_teach_adults": "X" if r.get("can_teach_adults") else "",
            "can_teach_adapted": "X" if r.get("can_teach_adapted") else "",
        })
    return out.getvalue()
