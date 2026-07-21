# Jackrabbit Extension → Aqua Essence Integration Plan

**Date:** 2026-05-26  
**Status:** Layers 1–2 DONE (`import_jackrabbit_pairings_csv` in `backend/db.py`, frontend upload button + session selector). Layer 3 (extension expansion) not started.  
**Depends on:** the separately versioned [Jackrabbit Exporter](https://github.com/TheAquaEssence/jackrabbit-exporter) extension (bulk HP export complete and working)

> **Repository move (2026-07-21):** The extension source moved out of Aqua
> Essence. This document is a historical integration plan; verify current CSV
> contracts in both repositories before implementing later layers.

---

## Background

The Jackrabbit Exporter browser extension can now perform a single-click bulk export of historical pairings (HP) from the Jackrabbit AllClasses page. It produces `jackrabbit_pairings.csv` with the following columns:

```
swimmer_id, instructor_id, instructor_name, class_slot, session, rss_level, is_historical, student_name
```

Where:
- `swimmer_id` = Jackrabbit student xID (e.g. `"31327570"`)
- `instructor_id` = Jackrabbit class xID (e.g. `"21161992"`) — **not an instructor ID**
- `instructor_name` = instructor last name parsed from class title (e.g. `"Kenaston"`)
- `class_slot` = day + time string (e.g. `"Wednesday 8:30 am"`)
- `session` = session label from Jackrabbit (e.g. `"Spring 2026"`)
- `rss_level` = RSS level parsed from class title (e.g. `"5"`, `"Adult"`)
- `is_historical` = always `"yes"`
- `student_name` = student full name (e.g. `"Michael Casaclang"`)

The solver's `historical_pairings.csv` (produced by `generate_historical_pairings()` in `backend/csv_import.py`) uses **internal solver IDs** that are row-position-based — not Jackrabbit xIDs. This is the core gap to bridge.

---

## The ID Mismatch Problem

| Field | Extension output | Solver expects |
|---|---|---|
| `swimmer_id` | Jackrabbit xID (`"31327570"`) | Internal CSV row ID (`1`, `2`, `3`…) |
| `instructor_id` | Jackrabbit class xID | Internal instructor row ID |

Direct use of the extension's CSV as `historical_pairings.csv` will silently produce zero continuity matches because no swimmer/instructor IDs will align.

**Resolution strategy: match by name, not by ID.** The instructor last name and student full name are both present in the export and are stable across sessions. The backend import endpoint will resolve names → internal IDs at import time.

---

## Integration Layers

### Layer 1 — Backend import endpoint (required) — DONE

Add `POST /api/import_jackrabbit_pairings` to `backend/server.py`.

**Accepts:** multipart file upload of `jackrabbit_pairings.csv`

**Logic:**
1. Read the uploaded CSV
2. Load the current `students.csv` (from the last job or the active file)
3. Load the current `instructors.csv`
4. For each HP row:
   - Resolve `student_name` → internal `swimmer_id` (match on full name, case-insensitive; warn on no-match)
   - Resolve `instructor_name` → internal `instructor_id` (match on last name; warn on ambiguity)
   - Keep `class_slot` and `session` as-is
5. Write resolved rows to `data/historical_pairings.csv` (append mode with deduplication)
6. Return `{ ok: true, imported: N, skipped: M, warnings: [...] }`

**Name matching notes:**
- Student: match `student_name` against `"{First} {Last}"` from `students.csv`
- Instructor: match `instructor_name` (last name only) against `Last Name` column in `instructors.csv`; if multiple instructors share a last name, match further on `class_slot` day
- Log all unresolved rows as warnings — don't silently drop them

**Files to modify:**
- `backend/server.py` — add endpoint
- `backend/csv_import.py` — add `import_jackrabbit_pairings(hp_csv_text, students_csv_text, instructors_csv_text)` helper
- `backend/tests/test_csv_import.py` — add tests for the new helper

---

### Layer 2 — Frontend upload UI — DONE

Add an "Import Historical Pairings" button to the frontend (`frontend/app.js` / `frontend/index.html`) that:
1. Opens a file picker for `jackrabbit_pairings.csv`
2. POSTs to `/api/import_jackrabbit_pairings`
3. Shows a summary: `"Imported 284 pairings (3 skipped — see warnings)"`

This completes the coordinator workflow:
> Export from Jackrabbit (extension) → Import into Aqua Essence (button) → Run solver

**Files to modify:**
- `frontend/index.html` — add upload button in the inputs section
- `frontend/app.js` — add upload handler and response display

---

### Layer 3 — Expand the extension (optional, high value)

The extension currently exports only historical pairings. Two additional export modes would complete the full Jackrabbit → Aqua Essence pipeline without any manual CSV work:

#### 3a. Current enrollment → `classes.csv`

On the AllClasses page (current session), read each class row and emit a row per class:

| Output column | Source |
|---|---|
| `class_name` | Class title (already parsed by `parseClassName()`) |
| `class_slot` | Day + time parsed from title |
| `instructor_id` | Instructor last name (to be resolved by backend) |
| `rss_level` | Parsed from title |
| `capacity` | Read from the Enrolled/Capacity column on AllClasses |
| `session` | Session column |

**Extension change:** add a "Download classes.csv" button (separate from the HP export) that triggers when the user is on the current session's AllClasses page.

#### 3b. Enrolled students → `students.csv`

For each class in the current session, the ClassDetail JSON already gives us:
- `StudentName` (full name)
- `BirthDate`
- `AgeWithMonths`
- `StudentId` (xID, useful as a stable external key)

The backend's `import_students()` in `csv_import.py` already accepts Jackrabbit-format CSVs. The extension just needs to aggregate all students across classes and deduplicate by `StudentId`.

**Extension change:** after the bulk fetch in `scrapeAllClassesBulk()`, also buffer student rows in a `STUDENT_BATCH` alongside the pairing rows. The popup's "Download students.csv" button (already wired up) would then work automatically.

---

## Full Target Workflow (after all layers done)

```
Coordinator opens Jackrabbit → AllClasses (past session)
  ↓ clicks "Export for Aqua Essence"
  ↓ extension bulk-fetches all pairings (~90 s for large session)
  ↓ downloads jackrabbit_pairings.csv

Coordinator opens Aqua Essence app
  ↓ clicks "Import Historical Pairings" → uploads jackrabbit_pairings.csv
  ↓ backend resolves names → IDs, appends to historical_pairings.csv

Coordinator uploads students.csv + instructors.csv (Jackrabbit exports)
  ↓ auto-converted by existing import_students() / import_instructors()

Coordinator clicks "Run Matching"
  ↓ solver uses historical_pairings.csv for continuity
  ↓ result includes continuity matches for returning swimmers
```

No manual CSV editing at any step.

---

## Implementation Order

| Step | Work | Effort |
|---|---|---|
| 1 | `import_jackrabbit_pairings()` helper in `csv_import.py` + tests | Medium |
| 2 | `POST /api/import_jackrabbit_pairings` endpoint in `server.py` | Small |
| 3 | Frontend upload button + response display | Small |
| 4 | Extension: buffer student rows during bulk fetch (Layer 3b) | Small |
| 5 | Extension: classes.csv export mode (Layer 3a) | Medium |

Steps 1–3 are the minimum viable integration. Steps 4–5 are quality-of-life improvements.

---

## Open Questions

1. **Deduplication across sessions:** If the coordinator imports HP from multiple past sessions, the same swimmer-instructor pair may appear multiple times. The solver's continuity phase already handles this (uses most recent pairing). Confirm append+dedupe behaviour in `import_jackrabbit_pairings()`.

2. **xID as stable external key:** Should `swimmer_id` (Jackrabbit xID) be stored in `students.csv` as an extra column (e.g. `jackrabbit_xid`) to make future name-matching more robust? This would allow ID-based matching as a faster fallback once the xID is known on both sides.

3. **Instructor name ambiguity:** If two instructors share the same last name, `instructor_name`-based matching will fail. Mitigation: also match on `class_slot` day (e.g. both named "Smith" but one teaches Monday and one teaches Wednesday).
