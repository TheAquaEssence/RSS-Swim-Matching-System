# Improvement Backlog — 2026-06-10

> **Historical backlog:** Many items were subsequently completed or
> superseded during backend modularization and Electron migration. This file
> preserves the original rationale; GitHub issues and the current migration
> checklist are the authoritative trackers.

A prioritized list of bugs, improvements, and features for the Aqua Essence app,
informed by a codebase review and direct feedback from the company coordinator
(the day-to-day user). Each item is written to be **self-contained** so a
single item or batch can be used directly as an implementation brief.

**Coordinator feedback driving priorities** (from their email):
- They value the Jackrabbit exporter and want the workflow usable by more than
  one person ("we're always looking to scale and not have just one person
  being able to do things").
- They want instructor profiles in the app to **document staffing needs over
  time** — e.g. "hire more blue/golds".
- They run **multiple sessions concurrently**, so session selection for
  historical pairings is a daily-use feature.

**Already fixed (do not redo):** the session selector "(0 selected)" bug —
`renderSessionMeta()` ran before the checkbox list was built, and the selected-
session collector skipped rows hidden by the search filter. Fixed in commit
`86dc7c8` on `dev`.

## Status (2026-06-12)

All of Batches A–C and D1–D4 are **DONE** on `dev`. Only **D5** remains.

| Item | Commit |
|------|--------|
| A1 historical-pairings pre-validation | `ec560e4` |
| A2 static asset no-cache | `09cdb21` |
| A3 session label dedupe + rename/delete admin | `cb338e6` |
| A4 point to Manage Instructors when DB is source | `386d628` |
| B1 staffing overview | `2a400a2` (+ style follow-ups) |
| B2 persist session selection | `2f21644` |
| B3 refresh sessions after upload | `7e68d14` |
| B4 operator-name attribution | `774cd8c` |
| C1 data-sources summary | `207fae4` |
| C2 curated generate failures | `1e8a033` |
| C3 sortable instructor table + completeness | `74d17d3` |
| C4 import review full profile | `09c59c6` |
| D1 server.py → routers | `6500202` |
| D2 app.js → feature modules | `d17323b` |
| D3 CI + ruff + pinned deps | `042dbdf` |
| D4 docs refresh | this change |

---

## Batch A — Bugs & correctness (do these first)

### A1. Friendly pre-validation when DB history doesn't match the selected swimmer/class files
**Problem:** When selected historical sessions reference swimmers or
instructors that don't exist in the currently selected `swimmers.csv` /
`instructors.csv`, the solver fails with a wall of raw errors
("Historical pairing has invalid swimmer_id: 15319687" repeated hundreds of
times) and the UI shows only "Solver execution failed". This is guaranteed to
happen for the coordinator: the DB holds real Jackrabbit IDs while a test run
may use sample files, and old sessions reference swimmers who have left.
**What to do:** Historical pairings are *history*, not constraints — unknown
IDs should be skipped with a summary warning, not fail the run. In
`backend/server.py`'s generate flow (where `historical_pairings_db.csv` is
written from `_db_load_historical_csv`), filter pairings against the swimmer
and instructor IDs present in the resolved input files, and surface a friendly
warning in the response (e.g. "412 of 18,543 historical pairings reference
swimmers/instructors not in your selected files and were ignored"). Show the
warning in the frontend result area (`frontend/app.js`). Keep a hard error only
if *zero* pairings survive and the user explicitly selected sessions.
**Verify:** run generate with sample files + real DB sessions selected — it
should succeed with a warning instead of failing.

### A2. Static asset cache staleness
**Problem:** `frontend/app.js` / `styles.css` are served by FastAPI
`StaticFiles` with no cache-busting. After an app update, browsers keep
executing the old JS (this bit us repeatedly during development — features
"missing" until a hard reload).
**What to do:** In `backend/server.py`, either add a
`Cache-Control: no-cache` (ETag revalidation) header for `/app.js`,
`/styles.css`, `/index.html` via the existing middleware, or inject a version
query string (`app.js?v=<startup-timestamp>`) into `index.html` at serve time.
Cheapest reliable option: `no-cache` headers on the static mount — files are
small and local.
**Verify:** edit app.js, restart server, plain reload picks up the change.

### A3. Solver-saved sessions accumulate duplicate labels
**Problem:** `backend/db.py: save_session_pairings()` always INSERTs a new
`sessions` row, so re-running the solver and saving with the same label (e.g.
"Spring 2026") creates duplicate sessions, which then clutter the session
selector and double-count history. (The Jackrabbit import path already reuses
sessions by label — `import_jackrabbit_pairings_csv` — solver saves should
behave consistently.)
**What to do:** Decide and implement one consistent rule: either
reuse-by-label like the Jackrabbit path (replace that session's pairings), or
keep separate rows but make labels unique ("Spring 2026 (run 2)"). Add a small
session admin capability while there: rename and delete a session
(`DELETE /api/sessions/{id}`, `PATCH /api/sessions/{id}`), exposed via a small
kebab/menu per session row in the selector panel (`frontend/app.js`,
`frontend/index.html`). Deleting a session must delete its pairings.
**Verify:** backend tests in `backend/tests/test_db.py` + UI check.

### A4. Two competing instructor editors confuse the source of truth
**Problem:** "Edit styles and colors" (file-based, edits the selected
instructors CSV via `backend/instructor_source_editor.py`) and "Manage
instructors" (DB-based) overlap. With the new "Use database instructors"
toggle, the file editor is a footgun: edits there do nothing when the DB is
the solver source.
**What to do:** When `use_db_instructors` is on, hide the "Edit styles and
colors" button (partially done — verify) AND add a one-line pointer to Manage
Instructors in its place. Longer-term (separate decision): retire the file
editor entirely once the coordinator confirms the DB workflow, and delete
`instructor_source_editor.py` + its modal. For now just make the UI
unambiguous about which editor is live.

---

## Batch B — Coordinator-driven features

### B1. Staffing analytics: color/style distribution report
**Why:** Coordinator: instructor profiles "would allow me to document our
staffing needs over time. Like hire more blue/golds etc."
**What to do:** Add a "Staffing overview" view (a section in the Manage
Instructors modal, or a small card on the main page) showing, from the
instructors DB: count of instructors per personality color, per style, and
per capability (babies/adults/adapted/captain), plus % of profiles complete.
Bonus: contrast supply against demand — swimmer type counts from the selected
swimmers file × the color/style rankings (`core/scoring`) to highlight
under-served swimmer types ("you have 2 Blue instructors but Blue is the top
color for 40% of current swimmers"). Keep it read-only and simple — a table
or bar list, no charting library needed. Endpoint: `GET /api/instructors/stats`
in `backend/server.py` reading via `backend/db.py`.

### B2. Persist the coordinator's session selection
**Why:** They run multiple active sessions and will curate the selection;
today it resets to "all selected" on every page load.
**What to do:** Save the selected session IDs in `settings/user_settings.json`
(e.g. `selected_session_ids: [...] | null` where null = all) via a debounced
POST when checkboxes change; restore on load. New sessions imported later
should default to selected (so history grows by default), i.e. store the
*deselected* IDs instead if that's simpler. Files: `frontend/app.js` (session
selector IIFE), `backend/server.py` (settings plumbing — follow the
`use_db_instructors` pattern from commit `40e8b90`).

### B3. Refresh the session list after a Jackrabbit pairings upload
**Why:** After "Upload pairings CSV", the session selector still shows the old
list until a page reload.
**What to do:** In `frontend/app.js`, after a successful
`/api/import_jackrabbit_pairings` upload, re-fetch `/api/sessions` and
re-render the selector (expose the selector's `loadSessions()` or emit a
custom event). Show which sessions were just added in the upload's meta line
(the endpoint already returns `sessions`).

### B4. Multi-user readiness: change attribution
**Why:** Coordinator explicitly wants more than one person operating the
system. There's no record of *who* changed an instructor or imported a file.
**What to do (lightweight, no auth system):** Add an optional "operator name"
field stored in localStorage and sent with mutating requests
(instructor PATCH, import apply/undo, pairings import). Record it in
`instructor_import_history` and a new `updated_by` column on `instructors`.
Show "last updated by X · date" in the instructor edit form. Skip
login/passwords — this is attribution, not security (app runs on a trusted
LAN). Files: `backend/db.py`, `backend/server.py`, `frontend/app.js`.

---

## Batch C — UX & flow polish

### C1. Data-sources summary on the main screen
**Problem:** The "Required input" card is file-centric, but two inputs
(instructors, history) can now come from the database. The mental model of
"what will this run actually use?" requires reading three different rows.
**What to do:** Add a compact one-line summary just above the Generate button:
"Will match using: classes.csv · swimmers.csv · instructors (database, 97) ·
history (134 sessions)". Update it from the same state that drives
`setGenerateEnabled()` in `frontend/app.js`.

### C2. Friendlier generate-failure presentation
**Problem:** Most solver failures dump raw text into the output box. Some
failures already get curated explanations (instructor-name mismatch, unknown
class) — extend that pattern.
**What to do:** In `frontend/app.js` (the generate error rendering around the
`renderImportDiagnosticsHtml` / error-explanation helpers), add curated
explanations for the most common remaining failures: data-validation walls
(supersede via A1), missing/empty input files, and solver timeout. Always
collapse the raw error behind a "show details" disclosure rather than dumping
it.

### C3. Manage Instructors table: sorting and completeness counter
**What to do:** Clickable column headers for Name and Profile status
(asc/desc) in `renderInstructorEditor()` (`frontend/app.js`), and show
"X of Y profiles complete (Z%)" in the meta line — supports the coordinator's
documentation goal. Keep it dependency-free (simple array sort).

### C4. Import review: show new instructors' full profile
**Problem:** In the import review modal, "New" rows show only capability
badges, not the incoming colors/styles.
**What to do:** In `renderInstructorImportReview()` (`frontend/app.js`), list
the new instructor's resolved color/style names (reuse
`instructorImportFieldValueLabel`) under the capability badges so the user
confirms the full incoming profile, not just capabilities.

---

## Batch D — Engineering health (no behavior change)

### D1. Split `backend/server.py` into routers — completed
Generation, instructors, sessions, and settings/files now use explicit router
modules and service dependencies.

### D2. Split `frontend/app.js` into modules — completed
Generation, instructor editing/defaults, sessions, profiles, references, and
settings/files use explicit vanilla JavaScript modules.

### D3. CI + lint + pinned deps — completed
CI runs Ruff and all active Python tests. Runtime, development, and packaging
dependencies are separated and pinned.

### D4. Update stale docs — completed 2026-07-18
Current guidance now uses `backend/`, the single Python CP-SAT solver, and
`python start.py`. Dated audit/change records carry historical notices rather
than presenting their removed components as current. See
`docs/privacy-and-data-retention.md` for operational-data and release rules.

### D5. Historical test gaps — completed
Focused coverage exists for data-loader failures, age boundaries, and data
generation.

---

## Suggested order

1. **A1 + A2** (correctness the coordinator will hit immediately)
2. **B2 + B3** (session workflow — their highest-praise feature)
3. **A3 + A4** (consistency cleanups)
4. **B1** (staffing analytics — high delight, standalone)
5. **C1–C4** (polish, each tiny)
6. **B4**, then **D1–D5** (engineering, anytime)

Conventions for implementing these items: backend tests live in
`backend/tests/`; run `python -m pytest backend/tests/ -q`; commit per item
with Conventional Commits, **no Co-Authored-By lines**; verify UI changes in
the browser via the `fastapi` launch config before committing.
