"""Tests for backend/db.py — SQLite historical pairings store."""
import csv
import io
import pytest
from pathlib import Path

from backend.db import (
    init_db,
    save_session_pairings,
    load_historical_pairings_csv,
    import_pairings_csv,
    list_sessions,
    list_sessions_with_counts,
    rename_session,
    delete_session,
)


@pytest.fixture()
def db(tmp_path):
    """Initialise a fresh in-memory-ish DB in a temp directory."""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    yield db_path


# ---------------------------------------------------------------------------
# init_db
# ---------------------------------------------------------------------------

def test_init_db_creates_file(tmp_path):
    db_path = tmp_path / "sub" / "test.db"
    init_db(db_path)
    assert db_path.exists()


def test_init_db_idempotent(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    init_db(db_path)  # calling twice should not raise


# ---------------------------------------------------------------------------
# save_session_pairings
# ---------------------------------------------------------------------------

def test_save_individual_match(db):
    matches = [{"swimmer_id": 1, "instructor_id": 10}]
    session_id = save_session_pairings(matches, label="Spring 2026")
    assert isinstance(session_id, int)
    assert session_id >= 1


def test_save_pair_match(db):
    matches = [{"swimmer_1_id": 2, "swimmer_2_id": 3, "instructor_id": 20}]
    session_id = save_session_pairings(matches, label="Spring 2026")
    csv_text = load_historical_pairings_csv()
    reader = list(csv.DictReader(io.StringIO(csv_text)))
    swimmer_ids = {int(r["swimmer_id"]) for r in reader}
    assert {2, 3} == swimmer_ids


def test_save_skips_missing_instructor(db):
    matches = [{"swimmer_id": 5}]  # no instructor_id
    save_session_pairings(matches, label="bad")
    csv_text = load_historical_pairings_csv()
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    assert rows == []


def test_sessions_accumulate(db):
    save_session_pairings([{"swimmer_id": 1, "instructor_id": 10}], label="S1")
    save_session_pairings([{"swimmer_id": 1, "instructor_id": 10}], label="S2")
    sessions = list_sessions()
    assert len(sessions) == 2


def test_save_same_label_reuses_session_and_replaces_pairings(db):
    sid1 = save_session_pairings([{"swimmer_id": 1, "instructor_id": 10}], label="Spring 2026")
    sid2 = save_session_pairings([{"swimmer_id": 2, "instructor_id": 20}], label="Spring 2026")
    assert sid1 == sid2
    assert len(list_sessions()) == 1
    rows = list(csv.DictReader(io.StringIO(load_historical_pairings_csv())))
    # Old pairings replaced, not accumulated
    assert [(int(r["swimmer_id"]), int(r["instructor_id"])) for r in rows] == [(2, 20)]


# ---------------------------------------------------------------------------
# rename_session / delete_session
# ---------------------------------------------------------------------------

def test_rename_session(db):
    sid = save_session_pairings([{"swimmer_id": 1, "instructor_id": 10}], label="S1")
    updated = rename_session(sid, "Spring 2026")
    assert updated["label"] == "Spring 2026"
    assert [s["label"] for s in list_sessions()] == ["Spring 2026"]


def test_rename_session_not_found(db):
    assert rename_session(999, "X") is None


def test_rename_session_empty_label_raises(db):
    sid = save_session_pairings([{"swimmer_id": 1, "instructor_id": 10}], label="S1")
    with pytest.raises(ValueError, match="empty"):
        rename_session(sid, "   ")


def test_rename_session_duplicate_label_raises(db):
    save_session_pairings([{"swimmer_id": 1, "instructor_id": 10}], label="S1")
    sid2 = save_session_pairings([{"swimmer_id": 2, "instructor_id": 20}], label="S2")
    with pytest.raises(ValueError, match="already"):
        rename_session(sid2, "S1")


def test_delete_session_removes_pairings(db):
    sid = save_session_pairings([{"swimmer_id": 1, "instructor_id": 10}], label="S1")
    save_session_pairings([{"swimmer_id": 2, "instructor_id": 20}], label="S2")
    assert delete_session(sid) is True
    sessions = list_sessions_with_counts()
    assert [s["label"] for s in sessions] == ["S2"]
    rows = list(csv.DictReader(io.StringIO(load_historical_pairings_csv())))
    assert [int(r["swimmer_id"]) for r in rows] == [2]


def test_delete_session_not_found(db):
    assert delete_session(999) is False


# ---------------------------------------------------------------------------
# load_historical_pairings_csv
# ---------------------------------------------------------------------------

def test_load_returns_csv_headers(db):
    save_session_pairings([{"swimmer_id": 1, "instructor_id": 10}], label="S1")
    csv_text = load_historical_pairings_csv()
    reader = csv.DictReader(io.StringIO(csv_text))
    assert set(reader.fieldnames) >= {"swimmer_id", "instructor_id", "session", "num_sessions"}


def test_load_empty_db(db):
    csv_text = load_historical_pairings_csv()
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    assert rows == []


def test_lookback_sessions(db):
    save_session_pairings([{"swimmer_id": 1, "instructor_id": 10}], label="old")
    save_session_pairings([{"swimmer_id": 2, "instructor_id": 20}], label="new")
    csv_text = load_historical_pairings_csv(lookback_sessions=1)
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    assert len(rows) == 1
    assert int(rows[0]["swimmer_id"]) == 2


# ---------------------------------------------------------------------------
# import_pairings_csv
# ---------------------------------------------------------------------------

def test_import_valid_csv(db):
    csv_text = "swimmer_id,instructor_id,session,num_sessions\n1,10,S1,1\n2,20,S1,1\n"
    session_id = import_pairings_csv(csv_text, label="S1")
    assert isinstance(session_id, int)
    rows = list(csv.DictReader(io.StringIO(load_historical_pairings_csv())))
    assert len(rows) == 2


def test_import_missing_column_raises(db):
    csv_text = "swimmer_id,session\n1,S1\n"
    with pytest.raises(ValueError, match="instructor_id"):
        import_pairings_csv(csv_text, label="bad")


def test_import_source_tag(db):
    csv_text = "swimmer_id,instructor_id\n1,10\n"
    import_pairings_csv(csv_text, label="JR", source="jackrabbit_import")
    sessions = list_sessions()
    assert sessions[0]["label"] == "JR"


# ---------------------------------------------------------------------------
# list_sessions
# ---------------------------------------------------------------------------

def test_list_sessions_empty(db):
    assert list_sessions() == []


def test_list_sessions_newest_first(db):
    save_session_pairings([{"swimmer_id": 1, "instructor_id": 10}], label="A")
    save_session_pairings([{"swimmer_id": 2, "instructor_id": 20}], label="B")
    sessions = list_sessions()
    assert sessions[0]["label"] == "B"
    assert sessions[1]["label"] == "A"


# ---------------------------------------------------------------------------
# preview_instructors_import / apply_instructors_import
# ---------------------------------------------------------------------------

from backend.db import (  # noqa: E402
    apply_instructors_import,
    export_instructors_csv,
    get_instructor,
    preview_instructors_import,
)

_INSTRUCTOR_HEADERS = (
    "instructor_id,first_name,last_name,"
    "primary_color_id,secondary_color_id,primary_style_id,secondary_style_id,"
    "is_team_captain,can_teach_babies,can_teach_adults,can_teach_adapted,"
    "used_default_profile"
)


def _instructor_csv(*rows):
    return _INSTRUCTOR_HEADERS + "\n" + "\n".join(rows) + "\n"


def _seed_instructor(csv_row):
    apply_instructors_import(_instructor_csv(csv_row), [csv_row.split(",")[0]])


def test_preview_all_new(db):
    csv_text = _instructor_csv("101,Ada,Lovelace,1,2,3,4,0,1,1,0,0")
    preview = preview_instructors_import(csv_text)
    assert len(preview["new"]) == 1
    assert preview["changed"] == []
    assert preview["unchanged"] == 0
    assert preview["new"][0]["instructor_id"] == "101"


def test_preview_unchanged(db):
    _seed_instructor("101,Ada,Lovelace,1,2,3,4,0,1,1,0,0")
    preview = preview_instructors_import(_instructor_csv("101,Ada,Lovelace,1,2,3,4,0,1,1,0,0"))
    assert preview["new"] == []
    assert preview["changed"] == []
    assert preview["unchanged"] == 1


def test_preview_field_level_changes(db):
    _seed_instructor("101,Ada,Lovelace,1,2,3,4,0,1,1,0,0")
    preview = preview_instructors_import(_instructor_csv("101,Ada,Byron,1,2,3,4,0,1,1,1,0"))
    assert len(preview["changed"]) == 1
    changes = {c["field"]: c for c in preview["changed"][0]["changes"]}
    assert changes["last_name"]["old"] == "Lovelace"
    assert changes["last_name"]["new"] == "Byron"
    assert changes["can_teach_adapted"]["old"] == 0
    assert changes["can_teach_adapted"]["new"] == 1
    assert set(changes) == {"last_name", "can_teach_adapted"}


def test_preview_missing_from_csv(db):
    _seed_instructor("101,Ada,Lovelace,1,2,3,4,0,1,1,0,0")
    _seed_instructor("102,Grace,Hopper,1,2,3,4,0,1,1,0,0")
    preview = preview_instructors_import(_instructor_csv("101,Ada,Lovelace,1,2,3,4,0,1,1,0,0"))
    assert [m["instructor_id"] for m in preview["missing_from_csv"]] == ["102"]


def test_preview_does_not_write(db):
    preview_instructors_import(_instructor_csv("101,Ada,Lovelace,1,2,3,4,0,1,1,0,0"))
    assert get_instructor("101") is None


def test_preview_missing_required_column_raises(db):
    with pytest.raises(ValueError, match="instructor_id"):
        preview_instructors_import("first_name,last_name\nAda,Lovelace\n")


def test_apply_only_accepted_rows(db):
    csv_text = _instructor_csv(
        "101,Ada,Lovelace,1,2,3,4,0,1,1,0,0",
        "102,Grace,Hopper,1,2,3,4,0,1,1,0,0",
    )
    result = apply_instructors_import(csv_text, ["101"])
    assert (result["created"], result["updated"]) == (1, 0)
    assert get_instructor("101") is not None
    assert get_instructor("102") is None


def test_apply_updates_existing(db):
    _seed_instructor("101,Ada,Lovelace,1,2,3,4,0,1,1,0,0")
    result = apply_instructors_import(_instructor_csv("101,Ada,Byron,1,2,3,4,0,1,1,0,0"), ["101"])
    assert (result["created"], result["updated"]) == (0, 1)
    assert get_instructor("101")["last_name"] == "Byron"


def test_apply_recomputes_profile_source(db):
    # Complete profile → profile_source 0 even though CSV has no profile_source column
    apply_instructors_import(_instructor_csv("101,Ada,Lovelace,1,2,3,4,0,1,1,0,1"), ["101"])
    inst = get_instructor("101")
    assert inst["profile_source"] == 0
    assert inst["used_default_profile"] == 0

    # Partially filled profile → profile_source 2
    apply_instructors_import(_instructor_csv("102,Grace,Hopper,1,,3,,0,1,1,0,0"), ["102"])
    inst = get_instructor("102")
    assert inst["profile_source"] == 2
    assert inst["used_default_profile"] == 1


def test_export_then_reimport_roundtrip_is_noop(db):
    _seed_instructor("101,Ada,Lovelace,1,2,3,4,0,1,1,0,0")
    exported = export_instructors_csv()
    preview = preview_instructors_import(exported)
    assert preview["new"] == []
    assert preview["changed"] == []
    assert preview["unchanged"] == 1


def test_duplicate_ids_last_row_wins_with_warning(db):
    csv_text = _instructor_csv(
        "101,Ada,Lovelace,1,2,3,4,0,1,1,0,0",
        "101,Ada,Byron,1,2,3,4,0,1,1,0,0",
    )
    preview = preview_instructors_import(csv_text)
    assert len(preview["new"]) == 1
    assert preview["new"][0]["last_name"] == "Byron"
    assert any("duplicate" in w for w in preview["warnings"])


def test_apply_field_subset_keeps_other_fields(db):
    _seed_instructor("101,Ada,Lovelace,1,2,3,4,0,1,1,0,0")
    csv_text = _instructor_csv("101,Ada,Byron,1,2,3,4,0,1,1,1,0")  # changes last_name + can_teach_adapted
    result = apply_instructors_import(csv_text, [{"instructor_id": "101", "fields": ["last_name"]}])
    assert (result["created"], result["updated"]) == (0, 1)
    inst = get_instructor("101")
    assert inst["last_name"] == "Byron"          # accepted field applied
    assert inst["can_teach_adapted"] == 0        # rejected field kept from DB


def test_apply_empty_field_list_is_noop(db):
    _seed_instructor("101,Ada,Lovelace,1,2,3,4,0,1,1,0,0")
    result = apply_instructors_import(
        _instructor_csv("101,Ada,Byron,1,2,3,4,0,1,1,1,0"),
        [{"instructor_id": "101", "fields": []}],
    )
    assert (result["created"], result["updated"]) == (0, 0)
    assert get_instructor("101")["last_name"] == "Lovelace"


def test_apply_field_subset_unknown_fields_ignored(db):
    _seed_instructor("101,Ada,Lovelace,1,2,3,4,0,1,1,0,0")
    result = apply_instructors_import(
        _instructor_csv("101,Ada,Byron,1,2,3,4,0,1,1,1,0"),
        [{"instructor_id": "101", "fields": ["last_name", "profile_source", "nonsense"]}],
    )
    assert (result["created"], result["updated"]) == (0, 1)
    inst = get_instructor("101")
    assert inst["last_name"] == "Byron"
    assert inst["can_teach_adapted"] == 0


def test_apply_field_subset_recomputes_profile_source(db):
    # Existing partial profile; CSV fills the missing fields — accept only one
    apply_instructors_import(_instructor_csv("101,Ada,Lovelace,1,,3,,0,1,1,0,0"), ["101"])
    assert get_instructor("101")["profile_source"] == 2
    csv_text = _instructor_csv("101,Ada,Lovelace,1,2,3,4,0,1,1,0,0")
    apply_instructors_import(
        csv_text,
        [{"instructor_id": "101", "fields": ["secondary_color_id", "secondary_style_id"]}],
    )
    inst = get_instructor("101")
    assert inst["secondary_color_id"] == 2
    assert inst["secondary_style_id"] == 4
    assert inst["profile_source"] == 0           # now complete
    assert inst["used_default_profile"] == 0


def test_apply_dict_entry_for_new_instructor_takes_full_row(db):
    # fields subset only applies to existing rows; a new instructor gets the whole row
    result = apply_instructors_import(
        _instructor_csv("101,Ada,Lovelace,1,2,3,4,0,1,1,0,0"),
        [{"instructor_id": "101", "fields": ["last_name"]}],
    )
    assert (result["created"], result["updated"]) == (1, 0)
    inst = get_instructor("101")
    assert inst["first_name"] == "Ada"
    assert inst["primary_color_id"] == 1


# ---------------------------------------------------------------------------
# undo_instructors_import
# ---------------------------------------------------------------------------

from backend.db import last_instructor_import, undo_instructors_import  # noqa: E402


def test_apply_records_history(db):
    result = apply_instructors_import(_instructor_csv("101,Ada,Lovelace,1,2,3,4,0,1,1,0,0"), ["101"])
    assert result["history_id"] is not None
    last = last_instructor_import()
    assert last["id"] == result["history_id"]
    assert last["summary"] == "1 added, 0 updated"


def test_noop_apply_records_no_history(db):
    apply_instructors_import(_instructor_csv("101,Ada,Lovelace,1,2,3,4,0,1,1,0,0"), ["nonexistent"])
    assert last_instructor_import() is None


def test_undo_removes_created_rows(db):
    apply_instructors_import(_instructor_csv("101,Ada,Lovelace,1,2,3,4,0,1,1,0,0"), ["101"])
    result = undo_instructors_import()
    assert result == {"restored": 0, "removed": 1, "summary": "1 added, 0 updated"}
    assert get_instructor("101") is None
    assert last_instructor_import() is None  # history entry consumed


def test_undo_restores_changed_rows(db):
    _seed_instructor("101,Ada,Lovelace,1,2,3,4,0,1,1,0,0")
    apply_instructors_import(_instructor_csv("101,Ada,Byron,1,2,3,4,0,1,1,1,0"), ["101"])
    assert get_instructor("101")["last_name"] == "Byron"
    result = undo_instructors_import()
    assert result["restored"] == 1 and result["removed"] == 0
    inst = get_instructor("101")
    assert inst["last_name"] == "Lovelace"
    assert inst["can_teach_adapted"] == 0
    assert inst["profile_source"] == 0  # derived fields restored too


def test_undo_field_subset_restores_full_previous_row(db):
    _seed_instructor("101,Ada,Lovelace,1,2,3,4,0,1,1,0,0")
    apply_instructors_import(
        _instructor_csv("101,Ada,Byron,1,2,3,4,0,1,1,1,0"),
        [{"instructor_id": "101", "fields": ["last_name"]}],
    )
    undo_instructors_import()
    assert get_instructor("101")["last_name"] == "Lovelace"


def test_undo_without_history_raises(db):
    with pytest.raises(ValueError, match="No import to undo"):
        undo_instructors_import()


def test_undo_only_reverts_that_import(db):
    apply_instructors_import(_instructor_csv("101,Ada,Lovelace,1,2,3,4,0,1,1,0,0"), ["101"])
    apply_instructors_import(_instructor_csv("102,Grace,Hopper,1,2,3,4,0,1,1,0,0"), ["102"])
    undo_instructors_import()  # undoes the Grace import only
    assert get_instructor("101") is not None
    assert get_instructor("102") is None
    # the earlier import is now the latest undoable one
    assert last_instructor_import()["summary"] == "1 added, 0 updated"
