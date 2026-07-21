"""Helpers for reading tabular partner exports from CSV or Excel workbooks."""

from __future__ import annotations

import csv
import io
from pathlib import Path
from tempfile import NamedTemporaryFile
from zipfile import ZipFile
import xml.etree.ElementTree as ET


_NS_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_NS_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_WORKBOOK_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def _column_index(cell_ref: str) -> int:
    letters = []
    for char in cell_ref:
        if char.isalpha():
            letters.append(char.upper())
        else:
            break

    index = 0
    for char in letters:
        index = index * 26 + (ord(char) - ord("A") + 1)
    return max(index - 1, 0)


def _shared_strings(archive: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []

    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    values: list[str] = []
    for item in root.findall(f"{_NS_MAIN}si"):
        text_parts = [node.text or "" for node in item.iter(f"{_NS_MAIN}t")]
        values.append("".join(text_parts))
    return values


def _first_sheet_target(archive: ZipFile) -> str:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    rel_map = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels.findall(f"{_NS_REL}Relationship")
    }

    sheets = workbook.find(f"{_NS_MAIN}sheets")
    if sheets is None or len(sheets) == 0:
        raise ValueError("Workbook has no sheets")

    first_sheet = sheets[0]
    rel_id = first_sheet.attrib.get(_WORKBOOK_REL)
    if not rel_id or rel_id not in rel_map:
        raise ValueError("Workbook sheet relationship is missing")

    target = rel_map[rel_id].lstrip("/")
    return target if target.startswith("xl/") else f"xl/{target}"


def _cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    value_node = cell.find(f"{_NS_MAIN}v")
    inline_node = cell.find(f"{_NS_MAIN}is")

    if cell_type == "s" and value_node is not None and value_node.text is not None:
        index = int(value_node.text)
        return shared_strings[index] if 0 <= index < len(shared_strings) else value_node.text

    if cell_type == "inlineStr" and inline_node is not None:
        parts = [node.text or "" for node in inline_node.iter(f"{_NS_MAIN}t")]
        return "".join(parts)

    if value_node is not None and value_node.text is not None:
        return value_node.text

    return ""


def _xlsx_to_csv_text(path: Path) -> str:
    with ZipFile(path) as archive:
        shared = _shared_strings(archive)
        sheet_path = _first_sheet_target(archive)
        sheet = ET.fromstring(archive.read(sheet_path))
        sheet_data = sheet.find(f"{_NS_MAIN}sheetData")
        if sheet_data is None:
            return ""

        rows: list[list[str]] = []
        max_columns = 0
        for row in sheet_data.findall(f"{_NS_MAIN}row"):
            values: dict[int, str] = {}
            for cell in row.findall(f"{_NS_MAIN}c"):
                ref = cell.attrib.get("r", "")
                col_idx = _column_index(ref)
                values[col_idx] = _cell_value(cell, shared)
                max_columns = max(max_columns, col_idx + 1)
            rows.append(values)

        output = io.StringIO()
        writer = csv.writer(output, lineterminator="\n")
        for row in rows:
            writer.writerow([row.get(index, "") for index in range(max_columns)])
        return output.getvalue()


def xlsx_bytes_to_csv_text(data: bytes) -> str:
    """Return CSV text from in-memory .xlsx/.xlsm bytes (e.g. an upload)."""
    return _xlsx_to_csv_text(io.BytesIO(data))


def read_tabular_file_text(path_like: str | Path) -> str:
    """Return a CSV-like text representation of a CSV or workbook file."""
    path = Path(path_like)
    suffix = path.suffix.lower()

    if suffix == ".csv":
        return path.read_text(encoding="utf-8-sig")
    if suffix in {".xlsx", ".xlsm"}:
        return _xlsx_to_csv_text(path)

    raise ValueError(f"Unsupported file type: {path.suffix or '<none>'}")


def _col_name(index: int) -> str:
    value = ""
    current = index + 1
    while current:
        current, rem = divmod(current - 1, 26)
        value = chr(ord("A") + rem) + value
    return value


def _worksheet_xml_from_csv_text(csv_text: str) -> bytes:
    rows = list(csv.reader(io.StringIO(csv_text)))
    root = ET.Element(f"{_NS_MAIN}worksheet")
    sheet_data = ET.SubElement(root, f"{_NS_MAIN}sheetData")

    for row_index, row in enumerate(rows, start=1):
        row_node = ET.SubElement(sheet_data, f"{_NS_MAIN}row", {"r": str(row_index)})
        for col_index, value in enumerate(row, start=1):
            if value == "":
                continue
            cell_ref = f"{_col_name(col_index - 1)}{row_index}"
            cell_node = ET.SubElement(
                row_node,
                f"{_NS_MAIN}c",
                {"r": cell_ref, "t": "inlineStr"},
            )
            inline_str = ET.SubElement(cell_node, f"{_NS_MAIN}is")
            text_node = ET.SubElement(inline_str, f"{_NS_MAIN}t")
            text_node.text = str(value)

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _write_xlsx_like_file(path: Path, csv_text: str) -> None:
    with ZipFile(path, "r") as archive:
        sheet_path = _first_sheet_target(archive)
        replacement_xml = _worksheet_xml_from_csv_text(csv_text)
        preserved_entries = [
            (info, archive.read(info.filename))
            for info in archive.infolist()
            if info.filename != sheet_path
        ]
        with NamedTemporaryFile(delete=False, suffix=path.suffix) as temp_handle:
            temp_path = Path(temp_handle.name)

    try:
        with ZipFile(temp_path, "w") as rewritten:
            for info, data in preserved_entries:
                rewritten.writestr(info, data)
            rewritten.writestr(sheet_path, replacement_xml)
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def write_tabular_file_text(path_like: str | Path, csv_text: str) -> None:
    """Write CSV-like text back to a CSV or workbook file."""
    path = Path(path_like)
    suffix = path.suffix.lower()

    if suffix == ".csv":
        path.write_text(csv_text, encoding="utf-8", newline="")
        return
    if suffix in {".xlsx", ".xlsm"}:
        _write_xlsx_like_file(path, csv_text)
        return

    raise ValueError(f"Unsupported file type: {path.suffix or '<none>'}")
