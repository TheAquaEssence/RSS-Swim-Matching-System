# 2026-04-21 App Updates

> **Historical change record:** Paths identify components as they existed when
> each change was made. The current backend is `backend/` (FastAPI);
> `backend2/`, the C++ host, and legacy solvers have since been removed.

This document records the April 21, 2026 update pass across the matching system, the desktop C++ host, the frontend, the real-data import path, and the XAI dashboard.

## 1. Runtime direction

### Decision
Moving forward, the maintained app runtime is the desktop C++ host:
- `backend/AquaEssenceHost.cpp`
- `AquaEssence.exe`

The browser UI and XAI dashboard frontend are still shared frontend code, but backend behavior now needs to exist on the C++ host path to matter in the live app.

### Result
- The desktop app is the authoritative runtime.
- Backend features previously added only to the Python host were ported to the C++ host where needed.

## 2. Default swimmer type for missing or new swimmers

### Goal
Implement a safe default swimmer type for swimmers with no submitted survey type.

### What changed
- Added `Non-Response / Unknown` to shipped reference data:
  - `data/source/swimmer_types.csv`
  - `data/source/swimmer_type_color_rankings.csv`
  - `data/source/swimmer_type_style_rankings.csv`
  - `data/app_samples/swimmer_types.csv`
  - `data/app_samples/swimmer_type_color_rankings.csv`
  - `data/app_samples/swimmer_type_style_rankings.csv`
- Added shared swimmer type helpers/constants:
  - `core/swimmer_types.py`
- Defaulted blank, `0`, and invalid swimmer type values to the non-response type during import/load/normalization:
  - `backend2/csv_import.py`
  - `backend2/desktop_host_pipeline.py`
  - `core/profiles/profile_reader.py`
  - `solvers/python_cpsat/engine/data_loader.py`
  - `solvers/graph_based/data_loader.py`
  - `solvers/greedy/data_loader.py`
  - `solvers/greedy_based/data_loader.py`
  - `solvers/cpp_exact/solver_main.cpp`
- Added the generated-result review flag:
  - `non_response_swimmer_type`

### Result
- New swimmers and swimmers with missing type data now default to `Non-Response / Unknown`.
- Generated results can flag those assignments for review.
- The user-facing review label for this flag now reads `Default swimmer type used` in both the home page and XAI.

## 3. Default instructor profile

### Goal
Give the system an editable default instructor profile for missing instructor traits, similar to the swimmer non-response fallback.

### What changed
- Added a persisted `default_instructor_profile` to settings.
- Added C++ desktop-host support for:
  - loading default instructor profile
  - saving default instructor profile
  - resetting to app defaults
- Added frontend UI for editing:
  - primary color
  - secondary color
  - primary style
  - secondary style
  - team captain
  - NL / babies / adults / adapted teaching booleans
- Added a result review flag for instructors using the fallback profile:
  - `default_instructor_profile`

### Files
- `backend/AquaEssenceHost.cpp`
- `frontend/index.html`
- `frontend/app.js`
- `frontend/styles.css`
- `core/flag_vocabulary.json`

### Result
- Missing instructor attributes now default consistently.
- Matches using those defaults are reviewable.

## 4. Real-data import support for Excel and partner exports

### Goal
Make the app work with the real exported files:
- `classes.xlsx`
- `Students.xlsx`
- `ActiveStaff.xlsx`

### What changed
- Added workbook reading/writing helpers:
  - `backend2/spreadsheet_import.py`
- Added partner export conversion support:
  - `backend2/csv_import.py`
- Added a desktop-host prep/annotation helper used by the C++ app:
  - `backend2/desktop_host_pipeline.py`
- Updated the C++ host generate path to call the helper script before and after solve:
  - input preparation
  - normalization
  - result annotation
- Updated file pickers to allow Excel files as well as CSV:
  - `backend/AquaEssenceHost.cpp`

### Result
- The desktop app can now work with the real workbook exports directly.
- The C++ app converts those files into solver-ready internal CSVs at generate time.

## 5. Historical pairings fallback

### Goal
Avoid accidentally using fake sample continuity when generating from real partner data.

### What changed
- When real imported data is used and no real historical pairings file is provided, the app now generates an empty history file for the job instead of silently using the sample history.

### Files
- `backend2/desktop_host_pipeline.py`
- `backend/AquaEssenceHost.cpp`

### Result
- Real-data generations without a real history source no longer inherit fake continuity.

## 6. Instructor source file editing from the UI

### Goal
Allow coordinators to edit instructor styles/colors directly against the selected instructor source file from the app UI.

### What changed
- Added a new button to the `instructors.csv` row:
  - `Edit styles and colors`
- This button appears before `Change file`.
- Added a popup editor listing instructors from the currently selected source file.
- The popup allows editing:
  - primary color
  - secondary color
  - primary style
  - secondary style

### Files
- `frontend/index.html`
- `frontend/app.js`
- `frontend/styles.css`
- `backend/AquaEssenceHost.cpp`
- `backend2/instructor_source_editor.py`

### Result
- Coordinators can manage instructor style/color assignments without leaving the app.

## 7. Instructor position filtering for real staff files

### Goal
Only treat teaching roles as solver instructors when using the real `ActiveStaff` export.

### Allowed editable/importable positions
- `Instructor`
- `Instructor Team Captain`
- `Youth Leader`
- `Aquafit Instructor`
- `Coach`

### What changed
- Added an extendable instructor position enum/schema:
  - `backend2/instructor_source_schema.py`
- The import and source editor paths now filter by `Position` when present.

### Result
- Non-teaching rows such as customer service and office roles are excluded from the instructor pool.
- The role list is centralized and easy to extend later.

## 8. New standard for the instructor source file

### New expected instructor profile columns
The instructor source file is now expected to support these columns:
- `primary_color_id`
- `secondary_color_id`
- `primary_style_id`
- `secondary_style_id`
- `is_team_captain`
- `can_teach_NL`
- `can_teach_babies`
- `can_teach_adults`
- `can_teach_adapted`
- `used_default_profile`

### Moving-forward standard
This is now the standard instructor source structure the app expects moving forward.

### Legacy compatibility behavior
To support older instructor files and partner exports:
- if those columns are missing, the app dynamically appends them to the end of the source file
- if those columns already exist, the app keeps them
- blank values in those columns are filled from the current default instructor profile
- non-blank valid values are preserved

### Important detail
For real partner workbooks, the app determines the real last header column and appends the new columns after the existing exported fields. This is how `ActiveStaff.xlsx` is upgraded in place while still remaining compatible with the export format.

### Files
- `backend2/instructor_source_editor.py`
- `backend2/csv_import.py`
- `backend2/instructor_source_schema.py`
- `backend2/spreadsheet_import.py`

### Result
- Legacy instructor files continue to work.
- Real instructor exports can now store persistent style/color/certification data.

## 9. Instructor import behavior

### What changed
- `ActiveStaff` import now:
  - prefers the explicit source profile columns if they exist
  - falls back to the default instructor profile only where values are missing or invalid
  - marks `used_default_profile = 1` when any fallback was needed
- Internal instructor normalization also fills missing/invalid fields from defaults and tracks that usage.

### Result
- Imported instructors are no longer forced to all share the same generic default profile if source values are already available.

## 10. Solver/result flagging consistency

### What changed
- Generated matches now carry review flags for:
  - non-response swimmer types
  - defaulted instructor profiles
- The desktop host annotates result JSON after solve so the live app sees those flags even if the solver output itself is minimal.

### Files
- `backend2/desktop_host_pipeline.py`
- `backend/AquaEssenceHost.cpp`
- `solvers/python_cpsat/engine/phase3_explainability.py`

### Result
- Review flags are more consistent across the live desktop flow.

## 11. XAI dashboard fixes and alignment

### Goal
Bring XAI into alignment with the home-page review system and eliminate stale/incorrect flagged-match behavior.

### What changed
- Updated XAI flagged-match logic so it respects:
  - `flag_codes`
  - `flags`
  - `review_severity`
  - `flag_summary`
- Fixed stale-data and asset-caching issues.
- Added client-side fallback flagged-match derivation from the loaded match objects.
- Added a `Review Flags` section to the XAI detail view.
- Updated XAI and home-page review rendering so `non_response_swimmer_type` displays as `Default swimmer type used`, including for older generated result files that still carry the previous wording.
- Adjusted the XAI top area layout so the title bar and tab bar use a stacked header-shell layout instead of visually colliding.
- Reduced the tab-row height and tightened the Overview / Match Explorer footprint after the initial header-shell fix.
- Bumped the XAI asset version again so the newer header/tab styling is actually fetched by the browser.
- Ported the needed logic into the C++ host path as well so the desktop app behavior stays aligned.

### Files
- `frontend/xai_dashboard/data_manager.py`
- `frontend/xai_dashboard/static/dashboard.js`
- `frontend/xai_dashboard/static/dashboard.css`
- `frontend/xai_dashboard/templates/index.html`
- `backend2/xai_router.py`
- `backend/AquaEssenceHost.cpp`

### Result
- XAI flagged matches now match the home page review logic much more closely.
- The XAI header and tab bar no longer need to fight for the same top offset.
- The top navigation consumes less vertical space than the earlier XAI layout revisions.

## 12. Frontend modal and popup fixes

### What changed
- Fixed startup dialogs that were showing while closed.
- Fixed nested `Edit item` dialog visibility.
- Fixed modal vertical centering.
- Fixed tall dialog overflow behavior.
- Fixed the new instructor style/color table header so it is fully opaque while scrolling.

### Files
- `frontend/styles.css`

### Result
- Dialogs behave properly on startup and while editing.

## 13. Default instructor profile UI reshaping

### What changed
- The default instructor profile now appears as its own row in Advanced Inputs.
- The row uses a single `Edit` button.
- Clicking `Edit` opens the dedicated popup editor.
- The primary action button label is now `Save` instead of `Save defaults`.

### Files
- `frontend/index.html`
- `frontend/app.js`
- `frontend/styles.css`

### Result
- The instructor-default UI now matches the style of the rest of the advanced-input controls.

## 14. Real-data generate diagnostics

### Goal
Make real-data import losses visible in the UI so low-match results are not mistaken for solver failures.

### What changed
- The desktop input-prep helper now records import diagnostics:
  - source row counts
  - imported row counts
  - skipped row counts
  - warning samples
- it also records unresolved instructor names referenced by classes before the solver runs
- The C++ host includes those diagnostics in the generate response.
- The frontend now shows an `Import check` warning block when generation used a workbook/export that produced a small imported subset.
- The generate error UI now shows a friendly instructor-mismatch message instead of dumping raw JSON first.
- When classes reference missing instructor names, the app now shows up to three names and then summarizes the rest as `and X more`.

### Files
- `backend2/desktop_host_pipeline.py`
- `backend/AquaEssenceHost.cpp`
- `frontend/app.js`
- `frontend/styles.css`

### Result
- If a real file only imports a few active rows, the app now tells the user directly.
- If classes reference instructors not found in the selected instructor file, the app now explains that clearly and points the user to the likely fix.

## 15. Fixed-roster matching workflow for the client process

### Goal
Match the client’s real workflow where swimmers are already enrolled in class spots before instructor matching begins.

### What changed
- The app now treats the imported class roster as fixed instead of freely moving swimmers across open slots.
- `Students.xlsx` now carries the swimmer’s registered class through import.
- The desktop prep pipeline builds rostered internal class rows with:
  - blank instructor assignment
  - fixed swimmer membership per class
- The CP-SAT path now detects fixed-roster inputs and switches into instructor-assignment mode for those rostered classes.
- Output generation now maps assignments back to `class_id` so results stay attached to the original class row.

### Files
- `backend2/csv_import.py`
- `backend2/desktop_host_pipeline.py`
- `solvers/python_cpsat/engine/data_loader.py`
- `solvers/python_cpsat/engine/fixed_class_workflow.py`
- `solvers/python_cpsat/engine/phase3_explainability.py`
- `solvers/python_cpsat/solver_wrapper.py`

### Result
- Swimmers stay in their already-selected classes.
- The solver now focuses on assigning the best instructor to each existing class roster.
- This starter version currently supports up to two registered swimmers per class row.

## 16. Student special-needs import rule

### Current behavior
For the real `Students` export, special-needs status now comes from explicit student fields rather than from the `Notes` count.

### Rule
- `Special Needs` and `Disabilities` are now what determine `has_special_needs`
- `Notes` is no longer used as the deciding special-needs signal
- `Current Classes` is imported and used for the fixed-roster workflow

### Files
- `backend2/csv_import.py`

### Result
- A swimmer is now marked special-needs based on the real exported special-needs fields instead of an inferred note count.

## 17. Real-data example discovered during testing

### Current observed counts from the provided files
- `classes.xlsx` imported `8` classes
- `ActiveStaff.xlsx` imported `108` instructors
- `Students.xlsx` contained `5` student rows total
- only `2` of those students were marked `Active`

### Why the generate looked small
Because only `2` swimmers imported, the solver produced:
- `1` pair match
- `0` unassigned swimmers

That result was consistent with the input data, not a CP-SAT failure.

## 18. Verification and tests

### Added or updated automated coverage
- `backend2/tests/test_csv_import.py`
- `backend2/tests/test_generate_non_response_flag.py`
- `backend2/tests/test_instructor_source_editor.py`
- `core/profiles/tests/test_profile_reader.py`
- `frontend/xai_dashboard/tests/test_app.py`
- `frontend/xai_dashboard/tests/test_dashboard_js_security.py`
- `frontend/xai_dashboard/tests/test_data_manager.py`
- `frontend/xai_dashboard/tests/test_heartbeat_shutdown.py`
- `solvers/python_cpsat/engine/tests/test_data_loader.py`
- `solvers/python_cpsat/engine/tests/test_explainability.py`

### Verification completed during this update cycle
- import/XAI/instructor-source test slices passed
- targeted Python regression runs passed
- `py_compile` passed for the edited Python files and helper scripts

### Notes
- Some runtime checks for the desktop app still require rebuilding `AquaEssence.exe` locally because `cmake` was not available in every shell context.

## 19. Home-page result persistence after visiting XAI

### Goal
Keep the most recent generated results visible on the home page after navigating into XAI and then returning home.

### Problem
The home page kept generated results only in in-memory frontend state. Opening XAI in the same tab navigated away from the home page, and returning home caused the page to reload without restoring the last result table.

### What changed
- Added a C++ desktop-host endpoint:
  - `/api/latest_generation_result`
- The endpoint reads the last successful job's `result.json`, validates it, and reattaches `import_diagnostics` from `prepared_settings.json` when available.
- The home page now requests that endpoint during startup and restores:
  - the generated matches table
  - the unassigned table
  - the XAI button state
  - the PDF and generated CSV actions
  - the import-check banner when applicable

### Files
- `backend/AquaEssenceHost.cpp`
- `frontend/app.js`

### Result
- After generating once, the user can open XAI and return home without needing to regenerate immediately.

## 20. Filled classes export

### Goal
Let coordinators download the original selected classes source file with instructor names filled back into its instructor column.

### What changed
- Added a new home-page action button:
  - `Download filled classes CSV`
- After solve, the desktop helper now:
  - reads the originally selected classes source file
  - finds the `Instructors` column
  - maps generated matches back to original class rows
  - writes a filled export using the original source format
- If the source classes file was Excel, the filled export stays Excel.
- If the source classes file was CSV, the filled export stays CSV.

### Files
- `frontend/index.html`
- `frontend/app.js`
- `backend2/desktop_host_pipeline.py`

### Result
- Users can download a version of the original classes file with matched instructor names inserted directly into the exported schedule structure.

## 21. Required-input and advanced-input UI restructuring

### What changed
- `swimmers.csv` and `instructors.csv` were moved under `classes.csv` in `Required input`.
- Their action buttons now use `Clear` instead of `Reset`.
- `historical_pairings.csv` was moved back under `Advanced inputs (optional)`.
- Empty `historical_pairings.csv` now displays `No file selected` instead of looking required.
- The Advanced Inputs subtitle was updated to reflect that it contains history, reference tables, and defaults.

### Files
- `frontend/index.html`
- `frontend/app.js`

### Result
- The main file-picking flow better matches what the user actually needs before generating.
- Optional history now looks optional in the UI.

## 22. Removal of entity sample defaults in the desktop host

### Goal
Stop the app from silently falling back to the shipped sample swimmer, instructor, and history files.

### What changed
- Removed built-in sample defaults for:
  - `swimmers`
  - `instructors`
  - `historical_pairings`
- Updated settings fixup so old sample selections for those keys are cleared out during desktop-host startup/settings validation.
- Updated the checked-in user settings template so those three paths start blank.

### Files
- `backend/AquaEssenceHost.cpp`
- `backend/settings/user_settings.json`

### Result
- Those three inputs now stay blank until the user selects real files.
- Clear really means clear instead of snapping back to sample data.

## 23. Swimmer-type editor visibility rule

### Goal
Keep the `Non-Response / Unknown` fallback type available to the system without showing it in the normal `Edit Swimmer Types` popup.

### What changed
- The `Edit Swimmer Types` reference editor now hides `Non-Response / Unknown` from its visible list.
- That hide rule applies only to the swimmer-type editor itself.
- The same swimmer type remains visible everywhere else it is still needed, including:
  - swimmer-type color rankings
  - swimmer-type style rankings
  - flags and review details
  - import/default logic
- The hidden row is preserved in the underlying CSV save path rather than being deleted.

### Files
- `frontend/app.js`

### Result
- Coordinators no longer see the fallback type in the regular swimmer-type editor, but the app still retains it as the system default.

## 24. Pre-assigned instructor matching improvements

### Goal
Make pre-filled instructor names from the selected classes file resolve more realistically against the real staff export, including abbreviated last names.

### What changed
- Class instructor name resolution now checks:
  - exact full-name match first
  - then first name plus abbreviated last-name fallback such as `Mitchell M.` or `Rishona H.`
- When multiple instructors match the same pre-assigned name:
  - one instructor is chosen deterministically
  - the match is flagged for review with:
    - `pre_assigned_instructor_name_ambiguous`
- The home-page generate error wording was updated so unresolved class instructors are described as names that could not be matched, rather than implying the instructor record does not exist.
- The instructor precheck helper used by the desktop app now mirrors the same exact-name and abbreviated-name matching logic before deciding a class instructor is missing.

### Files
- `solvers/python_cpsat/engine/data_loader.py`
- `solvers/python_cpsat/engine/phase3_explainability.py`
- `backend2/desktop_host_pipeline.py`
- `frontend/app.js`
- `core/flag_vocabulary.json`

### Result
- Real class exports that use shortened instructor names now resolve more often without blocking generation.
- Ambiguous pre-assigned names are surfaced as reviewable matches instead of causing a hard stop.

## 25. Real staff position matching improvements

### Goal
Stop valid teaching staff from being dropped when Jackrabbit exports compound `Position` titles such as `Instructor Office Staff`.

### What changed
- The editable/importable instructor-position logic now accepts:
  - exact teaching-role values
  - compound values that start with an allowed teaching role
- This now covers real exported values such as:
  - `Instructor Office Staff`
  - `Instructor Team Captain Office Staff`
- The change was made in the shared instructor-position schema so it applies consistently to:
  - instructor import
  - instructor source editing
  - downstream validation logic

### Files
- `backend2/instructor_source_schema.py`
- `backend2/csv_import.py`
- `backend2/instructor_source_editor.py`
- `backend2/tests/test_csv_import.py`

### Result
- Valid teaching staff in the real `ActiveStaff` export are no longer skipped simply because extra role words appear after the core teaching title.

## 26. Fixed-roster matching consistency and class-name normalization

### Goal
Keep the app in the client’s fixed-roster workflow consistently, and recover more real class registrations from the Jackrabbit exports.

### What changed
- Fixed-roster mode now stays enabled whenever roster columns exist in the prepared class file, even if no class rows end up filled yet.
- This prevents the desktop app from silently falling back to the older free-matching mode when roster matching is sparse.
- Registered class matching in the prep pipeline now normalizes class names before matching by:
  - removing leading labels such as `(Fill 8pm First)`
  - removing trailing numeric schedule ids such as `(560)`
  - normalizing whitespace
  - normalizing slash spacing
  - checking comma-separated registered class lists part-by-part instead of treating the whole cell as one exact string
- Real-data prep no longer hard-fails when more than two swimmers resolve to the same class row.
- Those overflow swimmers now stay unassigned and are flagged with:
  - `registered_class_full`
- Their unassigned reason now explains that the class matched the selected classes file but already hit the current 2-swimmer class-row limit.

### Files
- `backend2/desktop_host_pipeline.py`
- `solvers/python_cpsat/engine/data_loader.py`
- `core/flag_vocabulary.json`
- `backend2/tests/test_desktop_host_pipeline.py`
- `solvers/python_cpsat/engine/tests/test_data_loader_class_schema.py`

### Result
- The app now stays in the intended fixed-roster workflow instead of jumping back to free matching.
- Real registrations now recover substantially more rostered class matches from the selected classes file.
- Overflowed classes become reviewable unassigned cases instead of breaking generation.

## 27. Import-check wording polish

### Goal
Make the `Import check` text clearer when class rows are split during import.

### What changed
- The classes summary wording now explicitly says:
  - `imported X internal class row(s) from Y source row(s)`
- This replaces the more confusing `imported X of Y row(s)` phrasing for classes only.

### Files
- `frontend/app.js`

### Result
- Users can now immediately see that the classes importer expanded some source rows into multiple internal class rows rather than incorrectly assuming the counts are contradictory.

## 28. Instructor editor button visibility

### Goal
Only show the instructor `Edit styles and colors` button when an instructor file is actually selected.

### What changed
- The instructor editor button now starts hidden.
- It becomes visible only when the selected instructor file path is non-empty.
- The visibility is tied into the same file-row rendering logic used by the rest of the home-page file selectors, so it updates automatically after select/change/clear actions.

### Files
- `frontend/index.html`
- `frontend/app.js`

### Result
- The home page no longer suggests the instructor style/color editor is usable before an instructor source file has been chosen.

## 29. Removal of the generated CSV download button

### Goal
Remove the old `Download latest generated CSV` action while keeping the newer filled-classes export flow.

### What changed
- Removed the home-page button:
  - `Download latest generated CSV`
- Removed the frontend-only state and restore logic that existed just for that button:
  - local-storage key for the old generated CSV link
  - startup restore logic for that link
  - result-handling code that showed the button after generate
- The underlying solver output file `classes_filled.csv` was left in place because other internal app flows still use it.
- The newer `Download filled classes CSV` action remains available.

### Files
- `frontend/index.html`
- `frontend/app.js`

### Result
- The home page now exposes only the filled-classes export action instead of two overlapping CSV download actions.

## 30. Notes behavior in matching

### Goal
Clarify how swimmer notes currently affect matching in the live app.

### Current behavior
- Notes are no longer used to decide whether a swimmer is marked special-needs.
- A swimmer is marked special-needs only from the explicit exported student fields:
  - `Special Needs`
  - `Disabilities`
- Notes are still used by the CP-SAT matching logic when the `notes` field contains real text in recognized instruction patterns.

### Recognized notes patterns
- `prefer <instructor name>`
- `always <instructor name>`
- `avoid <instructor name>`
- `no <instructor name>`
- `never <instructor name>`

### Effect on matching
- `prefer` and `always` can increase an instructor's score.
- `avoid`, `no`, and `never` can block an instructor from being chosen.
- The real `Students.xlsx` export usually provides `Notes` as a numeric count rather than real note text, so that count alone does not influence matching.

### Files
- `backend2/csv_import.py`
- `solvers/python_cpsat/engine/notes_parser.py`
- `solvers/python_cpsat/engine/phase1_continuity.py`
- `solvers/python_cpsat/engine/phase2_cpsat.py`
- `solvers/python_cpsat/engine/fixed_class_workflow.py`

### Result
- Matching only reacts to real structured note text, not to the presence of a note count by itself.

## 31. Light-mode output/status styling

### Goal
Improve readability inside the home-page output/status rectangle when the app is in light mode.

### What changed
- Added light-theme styling overrides for the `#output` panel so it uses a darker translucent surface with high-contrast text.
- Tuned the status palette within that panel for the main runtime states:
  - generating
  - success
  - warning / import check
  - error
- Adjusted the warning icon/title, spinner, and error-details surface so they read more clearly against the light-mode output background.

### Files
- `frontend/styles.css`

### Result
- The light-mode output panel now keeps `Generating matching...`, success summaries, import-check warnings, and error content readable instead of falling into low-contrast dark-on-gray combinations.

## 32. Files changed in this update cycle

- `backend/AquaEssenceHost.cpp`
- `backend2/csv_import.py`
- `backend2/desktop_host_pipeline.py`
- `backend2/instructor_source_editor.py`
- `backend2/instructor_source_schema.py`
- `backend2/server.py`
- `backend2/spreadsheet_import.py`
- `backend2/tests/test_csv_import.py`
- `backend2/tests/test_desktop_host_pipeline.py`
- `backend2/tests/test_generate_non_response_flag.py`
- `backend2/tests/test_instructor_source_editor.py`
- `backend2/xai_router.py`
- `core/flag_vocabulary.json`
- `core/profiles/profile_reader.py`
- `core/profiles/tests/test_profile_reader.py`
- `core/swimmer_types.py`
- `data/app_samples/swimmer_type_color_rankings.csv`
- `data/app_samples/swimmer_type_style_rankings.csv`
- `data/app_samples/swimmer_types.csv`
- `data/source/swimmer_type_color_rankings.csv`
- `data/source/swimmer_type_style_rankings.csv`
- `data/source/swimmer_types.csv`
- `data_generation/generate_reference_data.py`
- `frontend/app.js`
- `frontend/index.html`
- `frontend/styles.css`
- `frontend/xai_dashboard/data_manager.py`
- `frontend/xai_dashboard/static/dashboard.css`
- `frontend/xai_dashboard/static/dashboard.js`
- `frontend/xai_dashboard/templates/index.html`
- `frontend/xai_dashboard/tests/test_app.py`
- `frontend/xai_dashboard/tests/test_dashboard_js_security.py`
- `frontend/xai_dashboard/tests/test_data_manager.py`
- `frontend/xai_dashboard/tests/test_heartbeat_shutdown.py`
- `solvers/cpp_exact/solver_main.cpp`
- `solvers/graph_based/data_loader.py`
- `solvers/greedy/data_loader.py`
- `solvers/greedy_based/data_loader.py`
- `solvers/python_cpsat/engine/data_loader.py`
- `solvers/python_cpsat/engine/fixed_class_workflow.py`
- `solvers/python_cpsat/engine/phase3_explainability.py`
- `solvers/python_cpsat/engine/tests/test_data_loader.py`
- `solvers/python_cpsat/engine/tests/test_data_loader_class_schema.py`
- `solvers/python_cpsat/engine/tests/test_explainability.py`
- `solvers/python_cpsat/solver_wrapper.py`
- `backend/settings/user_settings.json`

## 33. User-visible outcomes

- Missing swimmer types now default to `Non-Response / Unknown`.
- Missing instructor traits now default to the saved default instructor profile.
- Matches using either fallback can be flagged for review.
- The review label shown to users now says `Default swimmer type used` instead of `Missing swimmer type`.
- The desktop C++ app now supports the newer backend features that were previously Python-only.
- Real workbook exports can be used directly.
- The live workflow now supports fixed class rosters, where swimmers stay in their already-enrolled classes and only instructor assignment is optimized.
- Instructor source files can now be edited from the UI for styles and colors.
- Instructor source files now support persistent appended profile columns.
- Legacy instructor files are upgraded dynamically when needed.
- The original selected classes file can now be downloaded again with filled instructor names.
- Startup popup issues are fixed.
- Rankings/reference dialogs open correctly and stay centered.
- `Non-Response / Unknown` is hidden in the normal swimmer-type editor while still remaining available to the rest of the system.
- XAI review visibility is aligned more closely with the home page.
- XAI’s top header and tab row now use a safer stacked layout with refreshed assets.
- Returning home after opening XAI no longer forces an immediate regenerate just to see the last result again.
- Generate now surfaces import diagnostics when a workbook only contributes a small number of usable rows.
- Generate now shows friendlier instructor-name mismatch errors, including up to three missing names before summarizing the rest.
- Pre-filled class instructor names such as `Mitchell M.` or `Rishona H.` can now resolve against the selected staff file when the underlying full-name record exists.
- Compound teaching-role positions such as `Instructor Office Staff` and `Instructor Team Captain Office Staff` now import correctly as instructors.
- The app now stays in fixed-roster mode consistently when working from student registrations instead of silently falling back to free matching.
- Registered class-name matching now recovers more real Jackrabbit registrations by normalizing schedule labels, trailing ids, spacing, and comma-separated class lists.
- Class rows that already exceed the current 2-swimmer class-row limit now produce reviewable unassigned swimmers instead of aborting generation.
- The classes import summary now explains internal class-row expansion more clearly.
- The instructor `Edit styles and colors` button only appears after an instructor file is selected.
- The older `Download latest generated CSV` action has been removed, leaving the clearer filled-classes export flow.
- Notes only affect matching when they contain real recognized instruction text; a note count by itself does not make a swimmer special-needs and does not influence matching.
- The home-page output/status panel now uses a tuned light-mode palette so generating, success, warning, and error states remain readable.
- `swimmers.csv` and `instructors.csv` now sit in Required input, while `historical_pairings.csv` is back in Advanced input and clearly looks optional when empty.
- The desktop app no longer silently reselects sample swimmers, instructors, or historical pairings after those files are cleared.
