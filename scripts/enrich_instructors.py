#!/usr/bin/env python3
"""
scripts/enrich_instructors.py

Merges ActiveStaff1.xlsx (Name, Position, Jackrabbit Staff ID) with
Matching Key.xlsx (instructor personality colours + teaching styles) and
writes the final instructors CSV consumed by the Aqua Essence solver.

IMPORTANT: instructor_id in the output equals the Jackrabbit Staff ID from
ActiveStaff1.xlsx — it is NOT auto-incremented.

Usage:
    python scripts/enrich_instructors.py \\
        --active-staff "path/to/ActiveStaff1.xlsx" \\
        --matching-key "path/to/Matching Key.xlsx" \\
        --output data/source/instructors.csv

    # Force a full rewrite (discards manual edits to source=0 rows):
    python scripts/enrich_instructors.py ... --no-merge

Name matching pipeline (tried in order, stops at first hit):
    1. Exact full-name match (whitespace-normalised)
    2. Same last name + first name is a prefix of the other (>=3 chars)
    3. Same last name + first names are in the same nickname group (nicknames.json)
    4. First name exact/prefix/nickname match + last name edit-distance <= 2

Merge mode (default ON):
    Rows already at profile_source=0 in the existing output are kept as-is.
    Only unresolved rows (source=1 or source=2) are re-attempted.
    Use --no-merge to overwrite everything.

Output columns:
    instructor_id, first_name, last_name,
    primary_color_id, secondary_color_id, primary_style_id, secondary_style_id,
    is_team_captain, can_teach_babies, can_teach_adults, can_teach_adapted,
    used_default_profile, profile_source
"""

import argparse
import csv
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------

INTERNAL_HEADERS = [
    "instructor_id",
    "first_name",
    "last_name",
    "primary_color_id",
    "secondary_color_id",
    "primary_style_id",
    "secondary_style_id",
    "is_team_captain",
    "can_teach_babies",
    "can_teach_adults",
    "can_teach_adapted",
    "used_default_profile",
    "profile_source",
]

# profile_source values
SRC_COMPLETE  = 0  # all four profile fields filled
SRC_NOT_FOUND = 1  # name not found in Matching Key
SRC_PARTIAL   = 2  # found but one or more fields blank / TBD

PROFILE_SOURCE_LEGEND = {
    SRC_COMPLETE:  "Complete profile from Matching Key (all colour + style fields filled)",
    SRC_NOT_FOUND: "Name not found in Matching Key — all profile fields left blank",
    SRC_PARTIAL:   "Found in Matching Key but one or more fields were blank / TBD",
}

# ---------------------------------------------------------------------------
# Lookup tables
# ---------------------------------------------------------------------------

ARGB_TO_COLOR_ID: dict[str, int] = {
    "FF00B0F0": 1,  # Blue
    "FFFFC000": 2,  # Orange
    "FF92D050": 3,  # Green
    "FFFFFF00": 4,  # Gold
}

STYLE_NAME_TO_ID: dict[str, int] = {
    "new rss/babies": 1,
    "high energy": 2,
    "technique driven": 3,
    "adapted": 4,
    "soft-spoken": 5,
    "do-it-alls": 6,
}

VALID_POSITIONS = [
    "Instructor Team Captain",
    "Instructor",
    "Youth Leader",
    "Aquafit Instructor",
    "Coach",
]
_POSITIONS_SORTED = sorted(VALID_POSITIONS, key=len, reverse=True)

# ---------------------------------------------------------------------------
# xlsx parsing helpers  (stdlib only — no openpyxl)
# ---------------------------------------------------------------------------


def _col_letter_to_idx(letters: str) -> int:
    idx = 0
    for ch in letters.upper():
        idx = idx * 26 + (ord(ch) - ord("A") + 1)
    return idx - 1


def _cell_ref_to_row_col(ref: str) -> tuple[int, int]:
    m = re.match(r"([A-Za-z]+)(\d+)", ref)
    if not m:
        raise ValueError(f"Invalid cell ref: {ref!r}")
    return int(m.group(2)) - 1, _col_letter_to_idx(m.group(1))


def _ns_prefix(root: ET.Element) -> str:
    if "}" in root.tag:
        return "{" + root.tag.split("}")[0].lstrip("{") + "}"
    return ""


def _read_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    try:
        data = zf.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ET.fromstring(data)
    p = _ns_prefix(root)
    return ["".join((t.text or "") for t in si.iter(f"{p}t")) for si in root.iter(f"{p}si")]


def _read_fill_argbs(zf: zipfile.ZipFile) -> dict[int, str]:
    try:
        data = zf.read("xl/styles.xml")
    except KeyError:
        return {}
    root = ET.fromstring(data)
    p = _ns_prefix(root)
    fills_el = root.find(f"{p}fills")
    if fills_el is None:
        return {}
    result: dict[int, str] = {}
    for idx, fill in enumerate(fills_el):
        pattern = fill.find(f"{p}patternFill")
        if pattern is None:
            continue
        fg = pattern.find(f"{p}fgColor")
        if fg is None:
            continue
        rgb = fg.get("rgb") or fg.get("theme")
        if rgb and len(rgb) == 8:
            result[idx] = rgb.upper()
    return result


def _read_xf_fill_ids(zf: zipfile.ZipFile) -> dict[int, int]:
    try:
        data = zf.read("xl/styles.xml")
    except KeyError:
        return {}
    root = ET.fromstring(data)
    p = _ns_prefix(root)
    cell_xfs = root.find(f"{p}cellXfs")
    if cell_xfs is None:
        return {}
    return {idx: int(xf.get("fillId")) for idx, xf in enumerate(cell_xfs) if xf.get("fillId") is not None}


class _Sheet:
    def __init__(self) -> None:
        self._cells: dict[tuple[int, int], dict] = {}

    def get_value(self, row: int, col: int, default: str = "") -> str:
        c = self._cells.get((row, col))
        return c["value"] if c else default

    def get_style_idx(self, row: int, col: int) -> int | None:
        c = self._cells.get((row, col))
        return c["style_idx"] if c else None

    def max_row(self) -> int:
        return max((r for r, _ in self._cells), default=-1)


def _parse_sheet(zf: zipfile.ZipFile, sheet_path: str, shared_strings: list[str]) -> _Sheet:
    root = ET.fromstring(zf.read(sheet_path))
    p = _ns_prefix(root)
    sheet = _Sheet()
    for c_el in root.iter(f"{p}c"):
        ref = c_el.get("r", "")
        if not ref:
            continue
        try:
            row_idx, col_idx = _cell_ref_to_row_col(ref)
        except ValueError:
            continue
        cell_type = c_el.get("t", "")
        style_raw = c_el.get("s")
        v_el = c_el.find(f"{p}v")
        is_el = c_el.find(f"{p}is")
        if cell_type == "s":
            raw = v_el.text if v_el is not None else ""
            try:
                value = shared_strings[int(raw)] if raw is not None else ""
            except (IndexError, ValueError):
                value = raw or ""
        elif cell_type == "inlineStr":
            t_el = is_el.find(f"{p}t") if is_el is not None else None
            value = t_el.text if t_el is not None else ""
        else:
            value = v_el.text if v_el is not None else ""
        sheet._cells[(row_idx, col_idx)] = {
            "value": (value or "").strip(),
            "style_idx": int(style_raw) if style_raw is not None else None,
        }
    return sheet


def _sheet_paths(zf: zipfile.ZipFile) -> list[str]:
    return sorted(
        (n for n in zf.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml", n)),
        key=lambda s: int(re.search(r"\d+", s).group()),
    )


def _open_xlsx(path: Path):
    zf = zipfile.ZipFile(path)
    return zf, _read_shared_strings(zf), _read_fill_argbs(zf), _read_xf_fill_ids(zf)


# ---------------------------------------------------------------------------
# Position normalisation
# ---------------------------------------------------------------------------


def _normalize_position(raw: str) -> str:
    cleaned = " ".join(raw.strip().split())
    lower = cleaned.lower()
    for pos in _POSITIONS_SORTED:
        if lower.startswith(pos.lower()):
            return pos
    return cleaned


# ---------------------------------------------------------------------------
# Name normalisation
# ---------------------------------------------------------------------------


def _norm(name: str) -> str:
    """Collapse whitespace and lower-case."""
    return " ".join(name.strip().split()).lower()


def _split_name(name: str) -> tuple[str, str]:
    """Return (first, last) normalised. last may be multi-word."""
    parts = _norm(name).split()
    return (parts[0], " ".join(parts[1:])) if len(parts) >= 2 else (parts[0] if parts else "", "")


# ---------------------------------------------------------------------------
# Nickname groups
# ---------------------------------------------------------------------------


def _load_nickname_index(nicknames_path: Path) -> dict[str, frozenset[str]]:
    """
    Load nicknames.json and return a dict mapping each name (lower) to
    the frozenset of all equivalent names in its group.
    """
    if not nicknames_path.exists():
        return {}
    with open(nicknames_path, encoding="utf-8") as f:
        groups: list[list[str]] = json.load(f)
    index: dict[str, frozenset[str]] = {}
    for group in groups:
        fs = frozenset(n.lower() for n in group)
        for name in fs:
            index[name] = fs
    return index


# ---------------------------------------------------------------------------
# Edit distance (Levenshtein) — stdlib only
# ---------------------------------------------------------------------------


def _levenshtein(a: str, b: str) -> int:
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            curr.append(min(prev[j] + (ca != cb), curr[j] + 1, prev[j + 1] + 1))
        prev = curr
    return prev[-1]


# ---------------------------------------------------------------------------
# Cascading name match
# ---------------------------------------------------------------------------


def _match_profile(
    inst_name: str,
    profiles: dict[str, dict],
    nickname_idx: dict[str, frozenset[str]],
) -> tuple[dict | None, str, str]:
    """
    Try to match inst_name to a profile using four strategies in order.
    Returns (profile, matched_key, method_label) or (None, "", "").
    method_label is one of: "exact", "prefix", "nickname", "edit_dist",
    "nickname+edit_dist", "prefix+edit_dist".
    """
    norm_name = _norm(inst_name)

    # 1. Exact
    if norm_name in profiles:
        return profiles[norm_name], norm_name, "exact"

    inst_first, inst_last = _split_name(inst_name)
    if not inst_last:
        return None, "", ""

    inst_group = nickname_idx.get(inst_first, frozenset({inst_first}))

    def _first_compat(key_first: str) -> str:
        """Return match method for first-name comparison, or '' if incompatible."""
        if inst_first == key_first:
            return "exact_first"
        key_group = nickname_idx.get(key_first, frozenset({key_first}))
        if inst_group & key_group:
            return "nickname"
        shared = min(len(inst_first), len(key_first))
        if shared >= 3 and (inst_first.startswith(key_first) or key_first.startswith(inst_first)):
            return "prefix"
        return ""

    same_last:  list[tuple[str, str]]       = []  # (key, first_method)
    close_last: list[tuple[str, str, int]]  = []  # (key, first_method, dist)

    for key in profiles:
        key_first, key_last = _split_name(key)
        fm = _first_compat(key_first)
        if not fm:
            continue
        if key_last == inst_last:
            same_last.append((key, fm))
        else:
            d = _levenshtein(inst_last, key_last)
            if d <= 2:
                close_last.append((key, fm, d))

    # 2 & 3. Same last name, fuzzy first (prefix or nickname)
    fuzzy_first = [(k, m) for k, m in same_last if m != "exact_first"]
    if len(fuzzy_first) == 1:
        key, fm = fuzzy_first[0]
        return profiles[key], key, fm  # "prefix" or "nickname"

    # 4. Close last name — prefer closest distance, then fewest candidates
    close_last.sort(key=lambda x: x[2])
    if close_last:
        # Unambiguous at the closest distance level
        best_dist = close_last[0][2]
        at_best = [(k, m, d) for k, m, d in close_last if d == best_dist]
        if len(at_best) == 1:
            key, fm, _ = at_best[0]
            suffix = "+edit_dist" if fm != "exact_first" else ""
            method = ("edit_dist" if fm == "exact_first" else fm + "+edit_dist")
            return profiles[key], key, method

    return None, "", ""


# ---------------------------------------------------------------------------
# Parse ActiveStaff1.xlsx
# ---------------------------------------------------------------------------


def _parse_active_staff(path: Path) -> list[dict]:
    zf, shared_strings, _, _ = _open_xlsx(path)
    sheet = _parse_sheet(zf, _sheet_paths(zf)[0], shared_strings)

    # Locate header row
    header_row = None
    for r in range(10):
        for c in range(10):
            if "name" in sheet.get_value(r, c).lower():
                header_row = r
                break
        if header_row is not None:
            break
    if header_row is None:
        raise ValueError("ActiveStaff1.xlsx: cannot locate header row")

    col_name = col_position = col_staff_id = None
    for c in range(10):
        v = sheet.get_value(header_row, c).lower()
        if "name" in v and "position" not in v:
            col_name = c
        elif "position" in v:
            col_position = c
        elif "staff" in v or "id" in v:
            col_staff_id = c
    col_name     = col_name     if col_name     is not None else 0
    col_position = col_position if col_position is not None else 1
    col_staff_id = col_staff_id if col_staff_id is not None else 2

    results: list[dict] = []
    r = header_row + 1
    while r <= sheet.max_row():
        name = sheet.get_value(r, col_name)
        if name:
            parts = name.strip().split()
            results.append({
                "name": name.strip(),
                "first_name": parts[0] if parts else name,
                "last_name": " ".join(parts[1:]) if len(parts) > 1 else "",
                "position": _normalize_position(sheet.get_value(r, col_position)),
                "staff_id": sheet.get_value(r, col_staff_id).strip(),
            })
        r += 1

    return results


# ---------------------------------------------------------------------------
# Parse Matching Key.xlsx
# ---------------------------------------------------------------------------


def _parse_matching_key(path: Path) -> dict[str, dict]:
    """
    Return {normalised_name: {primary_color_id, secondary_color_id,
                               primary_style_id, secondary_style_id}}.
    Columns (0-based): E(4)=name, F(5)=primary colour, G(6)=secondary colour,
                       H(7)=primary style, I(8)=secondary style.
    """
    zf, shared_strings, fill_argbs, xf_fill_ids = _open_xlsx(path)
    sheet = _parse_sheet(zf, _sheet_paths(zf)[0], shared_strings)

    def style_to_argb(si) -> str:
        if si is None:
            return ""
        return fill_argbs.get(xf_fill_ids.get(si, -1), "")

    def argb_to_cid(argb: str) -> str:
        cid = ARGB_TO_COLOR_ID.get(argb.upper(), 0)
        return str(cid) if cid else ""

    def style_sid(raw: str) -> str:
        cleaned = raw.strip().lower()
        if not cleaned or cleaned == "tbd":
            return ""
        sid = STYLE_NAME_TO_ID.get(cleaned, 0)
        return str(sid) if sid else ""

    result: dict[str, dict] = {}
    skip = {"instructor", "name", "instructors", "staff", "instructor profiles",
            "team captains", ""}
    for r in range(sheet.max_row() + 1):
        name = sheet.get_value(r, 4)
        if _norm(name) in skip:
            continue
        result[_norm(name)] = {
            "primary_color_id":   argb_to_cid(style_to_argb(sheet.get_style_idx(r, 5))),
            "secondary_color_id": argb_to_cid(style_to_argb(sheet.get_style_idx(r, 6))),
            "primary_style_id":   style_sid(sheet.get_value(r, 7)),
            "secondary_style_id": style_sid(sheet.get_value(r, 8)),
        }

    return result


# ---------------------------------------------------------------------------
# Row builder
# ---------------------------------------------------------------------------


def _build_row(instructor: dict, profile: dict | None) -> dict:
    is_tc = 1 if "Team Captain" in instructor["position"] else 0

    if profile is None:
        prim_cid = sec_cid = prim_sid = sec_sid = ""
        used_default  = 1
        profile_source = SRC_NOT_FOUND
    else:
        prim_cid  = profile.get("primary_color_id", "")
        sec_cid   = profile.get("secondary_color_id", "")
        prim_sid  = profile.get("primary_style_id", "")
        sec_sid   = profile.get("secondary_style_id", "")
        all_filled = all([prim_cid, sec_cid, prim_sid, sec_sid])
        used_default   = 0 if all_filled else 1
        profile_source = SRC_COMPLETE if all_filled else SRC_PARTIAL

    return {
        "instructor_id":     instructor["staff_id"],
        "first_name":        instructor["first_name"],
        "last_name":         instructor["last_name"],
        "primary_color_id":  prim_cid,
        "secondary_color_id": sec_cid,
        "primary_style_id":  prim_sid,
        "secondary_style_id": sec_sid,
        "is_team_captain":   is_tc,
        "can_teach_babies":  is_tc,
        "can_teach_adults":  is_tc,
        "can_teach_adapted": is_tc,
        "used_default_profile": used_default,
        "profile_source":    profile_source,
    }


# ---------------------------------------------------------------------------
# Merge helper — read existing output
# ---------------------------------------------------------------------------


def _load_existing(output_path: Path) -> dict[str, dict]:
    """
    Return {instructor_id: row_dict} for rows already at source=0 in the
    existing output CSV.  Empty dict if the file doesn't exist yet.
    """
    if not output_path.exists():
        return {}
    with open(output_path, newline="", encoding="utf-8") as f:
        return {
            r["instructor_id"]: r
            for r in csv.DictReader(f)
            if r.get("profile_source") == str(SRC_COMPLETE)
        }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge ActiveStaff + Matching Key -> instructors.csv"
    )
    parser.add_argument("--active-staff", required=True, metavar="XLSX")
    parser.add_argument("--matching-key", required=True, metavar="XLSX")
    parser.add_argument("--output",       required=True, metavar="CSV")
    parser.add_argument(
        "--no-merge",
        action="store_true",
        help="Overwrite all rows, including manually-filled source=0 entries",
    )
    args = parser.parse_args()

    active_staff_path = Path(args.active_staff)
    matching_key_path = Path(args.matching_key)
    output_path       = Path(args.output)
    nicknames_path    = Path(__file__).parent / "nicknames.json"

    print(f"Reading active staff:  {active_staff_path}")
    instructors = _parse_active_staff(active_staff_path)
    print(f"  -> {len(instructors)} instructors")

    print(f"Reading matching key:  {matching_key_path}")
    profiles = _parse_matching_key(matching_key_path)
    print(f"  -> {len(profiles)} profiles in Matching Key")

    nickname_idx = _load_nickname_index(nicknames_path)
    print(f"  -> {len(nickname_idx)} nickname entries loaded from {nicknames_path.name}")

    merge_mode = not args.no_merge
    preserved: dict[str, dict] = {}
    if merge_mode:
        preserved = _load_existing(output_path)
        if preserved:
            print(f"  -> merge mode: preserving {len(preserved)} source=0 rows from existing output")

    rows: list[dict] = []
    by_source: dict[int, list[str]] = {SRC_COMPLETE: [], SRC_NOT_FOUND: [], SRC_PARTIAL: []}
    fuzzy_log: list[tuple[str, str, str]] = []  # (staff_name, matched_key, method)
    preserved_count = 0

    for inst in instructors:
        sid = inst["staff_id"]

        # Keep manually-completed rows unchanged
        if sid in preserved:
            rows.append(preserved[sid])
            by_source[SRC_COMPLETE].append(inst["name"])
            preserved_count += 1
            continue

        profile, matched_key, method = _match_profile(inst["name"], profiles, nickname_idx)

        if method not in ("", "exact") and profile is not None:
            fuzzy_log.append((inst["name"], matched_key, method))

        row = _build_row(inst, profile)
        rows.append(row)
        by_source[row["profile_source"]].append(inst["name"])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=INTERNAL_HEADERS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote {len(rows)} rows -> {output_path}")
    if preserved_count:
        print(f"  (preserved {preserved_count} already-complete rows unchanged)")

    if fuzzy_log:
        print(f"\nFuzzy matches ({len(fuzzy_log)}) — please verify:")
        for staff_name, key, method in fuzzy_log:
            print(f"  [{method}]  '{staff_name}'  ->  '{key}'")

    print("\nprofile_source legend:")
    for code, desc in PROFILE_SOURCE_LEGEND.items():
        names = by_source[code]
        print(f"  {code} = {desc}")
        print(f"      Count: {len(names)}")
        if names and code != SRC_COMPLETE:
            for name in names:
                print(f"        - {name}")

    print("\nDone. Review can_teach_* columns before production use.")


if __name__ == "__main__":
    main()
