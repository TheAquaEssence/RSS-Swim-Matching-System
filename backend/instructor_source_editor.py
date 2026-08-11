from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    workspace_root = Path(__file__).resolve().parents[1]
    if str(workspace_root) not in sys.path:
        sys.path.insert(0, str(workspace_root))

from backend.instructor_source_schema import (
    CERTIFICATION_PROFILE_COLUMNS,
    EDITABLE_INSTRUCTOR_POSITION_VALUES,
    SOURCE_PROFILE_COLUMNS,
    STYLE_COLOR_PROFILE_COLUMNS,
    is_editable_instructor_position,
)
from backend.spreadsheet_import import read_tabular_file_text, write_tabular_file_text


DEFAULT_INSTRUCTOR_PROFILE = {
    "primary_color_id": 1,
    "secondary_color_id": 2,
    "primary_style_id": 6,
    "secondary_style_id": 5,
    "is_team_captain": False,
    "can_teach_NL": True,
    "can_teach_babies": False,
    "can_teach_adults": False,
    "can_teach_adapted": False,
}


def _parse_boolish(value, default: bool) -> bool:
    normalized = str(value or "").strip().lower()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"0", "false", "no", "n"}:
        return False
    return default


def _sanitize_default_profile(profile: dict | None) -> dict:
    sanitized = dict(DEFAULT_INSTRUCTOR_PROFILE)
    if not isinstance(profile, dict):
        return sanitized

    for field in STYLE_COLOR_PROFILE_COLUMNS:
        try:
            value = int(profile.get(field, sanitized[field]))
            if value > 0:
                sanitized[field] = value
        except (TypeError, ValueError):
            pass

    for field in CERTIFICATION_PROFILE_COLUMNS:
        sanitized[field] = _parse_boolish(profile.get(field), sanitized[field])
    return sanitized


def _read_table(path: Path) -> tuple[list[str], list[list[str]]]:
    text = read_tabular_file_text(path)
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        raise ValueError("Instructor file is empty")

    headers = list(rows[0])
    while headers and not str(headers[-1]).strip():
        headers.pop()
    if not headers:
        raise ValueError("Instructor file is missing headers")

    data_rows: list[list[str]] = []
    width = len(headers)
    for row in rows[1:]:
        cells = list(row[:width])
        if len(cells) < width:
            cells.extend([""] * (width - len(cells)))
        data_rows.append(cells)
    return headers, data_rows


def _write_table(path: Path, headers: list[str], data_rows: list[list[str]]) -> None:
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(headers)
    writer.writerows(data_rows)
    write_tabular_file_text(path, output.getvalue())


def _row_dict(headers: list[str], row: list[str]) -> dict[str, str]:
    return {header: row[index] if index < len(row) else "" for index, header in enumerate(headers)}


def _ensure_headers(headers: list[str], row: list[str], required_headers: tuple[str, ...] | list[str]) -> None:
    missing = [header for header in required_headers if header not in headers]
    if missing:
        headers.extend(missing)
    if len(row) < len(headers):
        row.extend([""] * (len(headers) - len(row)))


def _normalize_positive_int(value, default: int) -> tuple[int, bool]:
    try:
        parsed = int(str(value or "").strip())
        return (parsed, False) if parsed > 0 else (default, True)
    except (TypeError, ValueError):
        return default, True


def _normalize_bool_string(value, default: bool) -> tuple[str, bool]:
    normalized = str(value or "").strip()
    if normalized.lower() in {"1", "true", "yes", "y"}:
        return "1", False
    if normalized.lower() in {"0", "false", "no", "n"}:
        return "0", False
    return ("1" if default else "0"), True


def _is_internal_instructors_file(headers: list[str]) -> bool:
    return {"instructor_id", "first_name", "last_name"}.issubset(set(headers))


def _is_partner_instructors_file(headers: list[str]) -> bool:
    return {"Name", "Status"}.issubset(set(headers))


def _eligible_partner_row(row_dict: dict[str, str], has_position_column: bool) -> bool:
    if str(row_dict.get("Status", "")).strip().lower() != "active":
        return False
    if has_position_column:
        return is_editable_instructor_position(row_dict.get("Position", ""))
    return _parse_boolish(row_dict.get("Instructor", ""), False)


def _normalize_internal_rows(
    headers: list[str],
    data_rows: list[list[str]],
    default_profile: dict,
) -> tuple[bool, list[dict]]:
    changed = False
    for row in data_rows:
        _ensure_headers(headers, row, SOURCE_PROFILE_COLUMNS)

    index_by_header = {header: index for index, header in enumerate(headers)}
    payload_rows: list[dict] = []
    for row_number, row in enumerate(data_rows, start=2):
        row_changed = False
        used_default_profile = _parse_boolish(row[index_by_header["used_default_profile"]], False)

        for field in STYLE_COLOR_PROFILE_COLUMNS:
            current_index = index_by_header[field]
            parsed_value, did_default = _normalize_positive_int(row[current_index], int(default_profile[field]))
            normalized_value = str(parsed_value)
            if row[current_index] != normalized_value:
                row[current_index] = normalized_value
                row_changed = True
            used_default_profile = used_default_profile or did_default

        for field in CERTIFICATION_PROFILE_COLUMNS:
            current_index = index_by_header[field]
            normalized_value, did_default = _normalize_bool_string(row[current_index], bool(default_profile[field]))
            if row[current_index] != normalized_value:
                row[current_index] = normalized_value
                row_changed = True
            used_default_profile = used_default_profile or did_default

        used_default_value = "1" if used_default_profile else "0"
        if row[index_by_header["used_default_profile"]] != used_default_value:
            row[index_by_header["used_default_profile"]] = used_default_value
            row_changed = True

        changed = changed or row_changed
        payload_rows.append(
            {
                "source_row_number": row_number,
                "instructor_id": row[index_by_header["instructor_id"]],
                "name": " ".join(
                    part for part in [
                        str(row[index_by_header["first_name"]]).strip(),
                        str(row[index_by_header["last_name"]]).strip(),
                    ] if part
                ),
                "position": "Internal instructors file",
                "primary_color_id": int(row[index_by_header["primary_color_id"]] or default_profile["primary_color_id"]),
                "secondary_color_id": int(row[index_by_header["secondary_color_id"]] or default_profile["secondary_color_id"]),
                "primary_style_id": int(row[index_by_header["primary_style_id"]] or default_profile["primary_style_id"]),
                "secondary_style_id": int(row[index_by_header["secondary_style_id"]] or default_profile["secondary_style_id"]),
                "used_default_profile": used_default_profile,
            }
        )

    return changed, payload_rows


def _normalize_partner_rows(
    headers: list[str],
    data_rows: list[list[str]],
    default_profile: dict,
) -> tuple[bool, list[dict]]:
    changed = False
    has_position_column = "Position" in headers
    for row in data_rows:
        _ensure_headers(headers, row, SOURCE_PROFILE_COLUMNS)

    index_by_header = {header: index for index, header in enumerate(headers)}
    payload_rows: list[dict] = []
    for row_number, row in enumerate(data_rows, start=2):
        row_dict = _row_dict(headers, row)
        if not _eligible_partner_row(row_dict, has_position_column):
            continue

        row_changed = False
        used_default_profile = _parse_boolish(row[index_by_header["used_default_profile"]], False)

        for field in STYLE_COLOR_PROFILE_COLUMNS:
            current_index = index_by_header[field]
            parsed_value, did_default = _normalize_positive_int(row[current_index], int(default_profile[field]))
            normalized_value = str(parsed_value)
            if row[current_index] != normalized_value:
                row[current_index] = normalized_value
                row_changed = True
            used_default_profile = used_default_profile or did_default

        for field in CERTIFICATION_PROFILE_COLUMNS:
            current_index = index_by_header[field]
            normalized_value, did_default = _normalize_bool_string(row[current_index], bool(default_profile[field]))
            if row[current_index] != normalized_value:
                row[current_index] = normalized_value
                row_changed = True
            used_default_profile = used_default_profile or did_default

        used_default_value = "1" if used_default_profile else "0"
        if row[index_by_header["used_default_profile"]] != used_default_value:
            row[index_by_header["used_default_profile"]] = used_default_value
            row_changed = True

        changed = changed or row_changed
        payload_rows.append(
            {
                "source_row_number": row_number,
                "name": " ".join(str(row_dict.get("Name", "")).split()),
                "position": " ".join(str(row_dict.get("Position", "")).split()),
                "primary_color_id": int(row[index_by_header["primary_color_id"]] or default_profile["primary_color_id"]),
                "secondary_color_id": int(row[index_by_header["secondary_color_id"]] or default_profile["secondary_color_id"]),
                "primary_style_id": int(row[index_by_header["primary_style_id"]] or default_profile["primary_style_id"]),
                "secondary_style_id": int(row[index_by_header["secondary_style_id"]] or default_profile["secondary_style_id"]),
                "used_default_profile": used_default_profile,
            }
        )

    return changed, payload_rows


def _load_settings(settings_path: Path) -> dict:
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    settings["default_instructor_profile"] = _sanitize_default_profile(settings.get("default_instructor_profile"))
    return settings


def _resolve_path(app_root: Path, workspace_root: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    app_candidate = (app_root / path).resolve()
    if app_candidate.exists():
        return app_candidate
    return (workspace_root / path).resolve()


def _get_selected_path(settings: dict, key: str) -> str:
    return (
        settings.get("last_selected_files", {}).get(key)
        or settings.get("default_files", {}).get(key, "")
    )


def _load_payload(app_root: Path, workspace_root: Path, settings_path: Path) -> dict:
    settings = _load_settings(settings_path)
    source_path_string = _get_selected_path(settings, "instructors")
    if not source_path_string:
        raise ValueError("No instructors file is currently selected")

    source_path = _resolve_path(app_root, workspace_root, source_path_string)
    if not source_path.exists():
        raise ValueError(f"Instructors file not found: {source_path}")

    headers, data_rows = _read_table(source_path)
    default_profile = settings["default_instructor_profile"]

    if _is_internal_instructors_file(headers):
        changed, payload_rows = _normalize_internal_rows(headers, data_rows, default_profile)
        mode = "internal"
    elif _is_partner_instructors_file(headers):
        changed, payload_rows = _normalize_partner_rows(headers, data_rows, default_profile)
        mode = "partner"
    else:
        raise ValueError("Selected instructors file is not a supported internal or partner format")

    if changed:
        _write_table(source_path, headers, data_rows)

    return {
        "ok": True,
        "mode": mode,
        "source_path": str(source_path),
        "source_file_name": source_path.name,
        "editable_count": len(payload_rows),
        "allowed_positions": list(EDITABLE_INSTRUCTOR_POSITION_VALUES),
        "instructors": payload_rows,
    }


def _save_payload(app_root: Path, workspace_root: Path, settings_path: Path, request_path: Path) -> dict:
    settings = _load_settings(settings_path)
    source_path_string = _get_selected_path(settings, "instructors")
    if not source_path_string:
        raise ValueError("No instructors file is currently selected")

    source_path = _resolve_path(app_root, workspace_root, source_path_string)
    if not source_path.exists():
        raise ValueError(f"Instructors file not found: {source_path}")

    request = json.loads(request_path.read_text(encoding="utf-8"))
    updates = request.get("updates", [])
    updates_by_row = {
        int(item["source_row_number"]): item
        for item in updates
        if isinstance(item, dict) and str(item.get("source_row_number", "")).strip()
    }

    headers, data_rows = _read_table(source_path)
    default_profile = settings["default_instructor_profile"]

    if _is_internal_instructors_file(headers):
        changed, payload_rows = _normalize_internal_rows(headers, data_rows, default_profile)
        mode = "internal"
        has_position_column = False
    elif _is_partner_instructors_file(headers):
        changed, payload_rows = _normalize_partner_rows(headers, data_rows, default_profile)
        mode = "partner"
        has_position_column = "Position" in headers
    else:
        raise ValueError("Selected instructors file is not a supported internal or partner format")

    index_by_header = {header: index for index, header in enumerate(headers)}
    for row_number, row in enumerate(data_rows, start=2):
        update = updates_by_row.get(row_number)
        if not update:
            continue

        if mode == "partner":
            row_dict = _row_dict(headers, row)
            if not _eligible_partner_row(row_dict, has_position_column):
                continue

        for field in STYLE_COLOR_PROFILE_COLUMNS:
            current_index = index_by_header[field]
            parsed_value, _ = _normalize_positive_int(update.get(field), int(default_profile[field]))
            normalized_value = str(parsed_value)
            if row[current_index] != normalized_value:
                row[current_index] = normalized_value
                changed = True

        used_default_index = index_by_header["used_default_profile"]
        if row[used_default_index] != "0":
            row[used_default_index] = "0"
            changed = True

    if changed:
        _write_table(source_path, headers, data_rows)

    return _load_payload(app_root, workspace_root, settings_path)


def _write_output(path: Path, payload: dict) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return 0


def main(argv: list[str]) -> int:
    try:
        if len(argv) == 6 and argv[1] == "load":
            _, _, app_root_arg, workspace_root_arg, settings_path_arg, output_path_arg = argv
            payload = _load_payload(Path(app_root_arg), Path(workspace_root_arg), Path(settings_path_arg))
            return _write_output(Path(output_path_arg), payload)

        if len(argv) == 7 and argv[1] == "save":
            _, _, app_root_arg, workspace_root_arg, settings_path_arg, request_path_arg, output_path_arg = argv
            payload = _save_payload(
                Path(app_root_arg),
                Path(workspace_root_arg),
                Path(settings_path_arg),
                Path(request_path_arg),
            )
            return _write_output(Path(output_path_arg), payload)

        if len(argv) >= 2:
            output_path = Path(argv[-1])
            return _write_output(output_path, {"ok": False, "error": "Invalid arguments"})
        return 1
    except Exception as exc:  # pragma: no cover - surfaced to the desktop host
        if len(argv) >= 2:
            try:
                output_path = Path(argv[-1])
                return _write_output(output_path, {"ok": False, "error": str(exc)})
            except Exception:
                return 1
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
