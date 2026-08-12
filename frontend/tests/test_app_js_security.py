import re
from pathlib import Path


FRONTEND_DIR = Path(__file__).resolve().parents[1]
APP_JS = FRONTEND_DIR / "app.js"
PROFILE_DRAWER_JS = FRONTEND_DIR / "profile_drawer.js"
SETTINGS_FILES_JS = FRONTEND_DIR / "settings_files.js"
REFERENCE_EDITORS_JS = FRONTEND_DIR / "reference_editors.js"
INSTRUCTOR_DEFAULTS_JS = FRONTEND_DIR / "instructor_defaults.js"
INDEX_HTML = FRONTEND_DIR / "index.html"

STYLESHEET_PATHS = (
    "./styles/base.css",
    "./styles/results.css",
    "./styles/overlays.css",
    "./styles/sessions.css",
    "./styles/instructor-editor.css",
    "./styles/ux-refresh.css",
    "./styles/workspace.css",
    "./styles/matching-workspace.css",
    "./styles/interaction-workspace.css",
)


def _extract_function(source: str, name: str, next_name: str) -> str:
    pattern = rf"(?:async\s+)?function {name}\(.*?\) \{{(.*?)\n\s*\}}\n\n\s*(?:async\s+)?function {next_name}\("
    match = re.search(pattern, source, re.S)
    assert match, f"Could not extract function {name}"
    return match.group(1)


def test_open_drawer_uses_node_content_not_innerhtml():
    source = PROFILE_DRAWER_JS.read_text(encoding="utf-8")
    assert "function openDrawer(type, contentNode)" in source
    assert "content.replaceChildren(contentNode);" in source

    open_drawer_body = _extract_function(source, "openDrawer", "closeDrawer")
    assert "innerHTML" not in open_drawer_body


def test_fetch_and_show_profile_uses_safe_drawer_helpers():
    source = PROFILE_DRAWER_JS.read_text(encoding="utf-8")
    fetch_body = _extract_function(source, "fetchAndShowProfile", "wireTableInteractions")

    assert 'openDrawer(type, createDrawerMessage("Loading profile' in fetch_body
    assert "setDrawerContent(createDrawerMessage(data.error || \"Profile not found\"));" in fetch_body
    assert "setDrawerContent(type === \"swimmer\" ? renderSwimmerProfile(data.profile) : renderInstructorProfile(data.profile));" in fetch_body
    assert "innerHTML" not in fetch_body


def test_main_frontend_uses_shared_ui_utils():
    source = APP_JS.read_text(encoding="utf-8")
    assert "const esc = window.AquaUi.escapeHtml;" in source
    assert "const formatConfidence = window.AquaUi.formatConfidence;" in source
    assert "function esc(" not in source
    assert "function formatConfidence(" not in source


def test_profile_drawer_exposes_frozen_namespace_for_generate_flow():
    source = PROFILE_DRAWER_JS.read_text(encoding="utf-8")
    assert '"use strict";' in source
    assert "window.AquaProfileDrawer = Object.freeze({" in source
    for member in (
        "wireProfileDrawer",
        "setLatestMatchResult",
        "normalizeFlags",
        "getHighestFlagSeverity",
        "renderReviewText",
        "formatAge",
        "matchSwimmerNames",
    ):
        assert f"    {member}," in source
    assert source.count("window.AquaProfileDrawer =") == 1


def test_profile_drawer_script_loads_before_generate_flow_and_app():
    source = INDEX_HTML.read_text(encoding="utf-8")
    shared_index = source.index('<script src="./shared/ui_utils.js"></script>')
    drawer_index = source.index('<script src="./profile_drawer.js"></script>')
    generate_index = source.index('<script src="./generate_flow.js"></script>')
    app_index = source.index('<script src="./app.js"></script>')
    assert shared_index < drawer_index < generate_index < app_index


def test_feature_stylesheets_load_in_cascade_order():
    source = INDEX_HTML.read_text(encoding="utf-8")
    positions = [
        source.index(f'<link rel="stylesheet" href="{path}" />')
        for path in STYLESHEET_PATHS
    ]

    assert positions == sorted(positions)
    assert "./styles.css" not in source
    for path in STYLESHEET_PATHS:
        assert (FRONTEND_DIR / path.removeprefix("./")).is_file()


def test_primary_navigation_integrates_explainability_without_duplicate_action():
    html = INDEX_HTML.read_text(encoding="utf-8")
    app_source = APP_JS.read_text(encoding="utf-8")
    generate_source = (FRONTEND_DIR / "generate_flow.js").read_text(encoding="utf-8")

    assert 'nav class="product-nav" aria-label="Primary navigation"' in html
    assert 'id="matchingNavLink" href="#matchingView" aria-current="page"' in html
    assert '<span>Matching</span>' in html
    assert 'id="resultsNavLink" href="#results-section"' in html
    assert 'aria-disabled="true" aria-describedby="resultsNavHint"' in html
    assert 'id="explainabilityNavLink" href="/xai/"' in html
    assert 'aria-disabled="true" aria-describedby="explainabilityNavHint"' in html
    assert 'id="dataSettingsNavLink" href="#advancedSection"' in html
    assert 'id="xaiDashboardButton"' not in html
    assert 'setExplainabilityAvailable(true);' in generate_source
    assert 'fetch("/api/launch_dashboard"' not in generate_source
    assert 'explainabilityLink.getAttribute("aria-disabled") === "true"' in app_source


def test_desktop_workspace_shell_is_shared_and_accessible():
    html = INDEX_HTML.read_text(encoding="utf-8")
    workspace_css = (FRONTEND_DIR / "styles" / "workspace.css").read_text(encoding="utf-8")

    assert 'class="skip-link" href="#main-content"' in html
    assert 'class="app-shell"' in html
    assert 'class="app-sidebar" aria-label="Application sidebar"' in html
    assert 'class="app-workspace"' in html
    assert 'class="app-main" id="main-content"' in html
    assert "grid-template-columns: var(--workspace-sidebar-width) minmax(0, 1fr)" in workspace_css
    assert "min-width: 980px" in workspace_css


def test_stage_two_uses_distinct_matching_results_and_data_views():
    html = INDEX_HTML.read_text(encoding="utf-8")
    app_source = APP_JS.read_text(encoding="utf-8")
    generate_source = (FRONTEND_DIR / "generate_flow.js").read_text(encoding="utf-8")

    assert 'id="matchingView" data-workspace-view="matching"' in html
    assert 'id="results-section" data-workspace-view="results" hidden' in html
    assert 'id="dataSettingsView" data-workspace-view="data" hidden' in html
    assert 'id="advancedSection" class="data-settings-details" open' in html
    assert "function showWorkspaceView(" in app_source
    assert 'showWorkspaceView("results");' in generate_source
    assert "function setResultsAvailable(" in app_source


def test_stage_two_results_filters_are_wired_without_changing_result_contract():
    html = INDEX_HTML.read_text(encoding="utf-8")
    source = (FRONTEND_DIR / "generate_flow.js").read_text(encoding="utf-8")

    assert 'id="resultsSearchInput"' in html
    assert 'id="resultsReviewFilter"' in html
    assert 'id="resultsFilterSummary" aria-live="polite"' in html
    assert "function applyResultsFilters()" in source
    assert "function wireResultsFilters()" in source
    assert "row.dataset.reviewSeverity = severity;" in source
    assert "wireResultsFilters();" in source


def test_stage_four_unifies_secondary_workflows_and_drawer_accessibility():
    html = INDEX_HTML.read_text(encoding="utf-8")
    drawer_source = PROFILE_DRAWER_JS.read_text(encoding="utf-8")
    interaction_css = (FRONTEND_DIR / "styles" / "interaction-workspace.css").read_text(encoding="utf-8")

    assert 'href="./styles/interaction-workspace.css"' in html
    assert 'id="profile-drawer" class="profile-drawer" role="dialog" aria-modal="true"' in html
    assert 'aria-labelledby="drawer-title" aria-hidden="true"' in html
    assert 'drawer.setAttribute("aria-hidden", "false");' in drawer_source
    assert 'if (lastDrawerTrigger?.isConnected) lastDrawerTrigger.focus();' in drawer_source
    assert ".rankings-editor-modal[open]" in interaction_css
    assert ".session-selector-panel" in interaction_css


def test_stage_four_session_selector_exposes_expansion_state():
    html = INDEX_HTML.read_text(encoding="utf-8")
    source = (FRONTEND_DIR / "session_selector.js").read_text(encoding="utf-8")

    assert 'aria-expanded="false" aria-controls="historicalSessionsPanel"' in html
    assert 'aria-label="Search historical sessions"' in html
    assert 'header.setAttribute("role", "button");' in source
    assert 'header.setAttribute("aria-expanded", isLatest ? "true" : "false");' in source
    assert 'toggleBtn.setAttribute("aria-expanded", open ? "false" : "true");' in source
    assert 'e.key !== "Enter" && e.key !== " "' in source


def test_app_delegates_profile_drawer_and_drops_its_state():
    source = APP_JS.read_text(encoding="utf-8")
    assert source.count("window.AquaProfileDrawer.wireProfileDrawer();") == 1
    assert "let drawerOpen" not in source
    assert "let latestMatchResult" not in source
    assert "function openDrawer(" not in source
    assert "function normalizeFlags(" not in source
    assert "function fetchAndShowProfile(" not in source
    assert "function wireProfileClicks(" not in source


def test_server_lifecycle_uses_heartbeat_watchdog_not_pagehide_shutdown():
    source = APP_JS.read_text(encoding="utf-8")
    assert "async function sendUserInterfaceHeartbeat()" in source
    assert "setInterval(() => void sendUserInterfaceHeartbeat(), 10000);" in source
    assert 'await fetch("/api/heartbeat"' in source
    assert 'window.addEventListener("pagehide", requestHostShutdownOnPageExit);' not in source


def test_rankings_editor_wires_load_save_and_edit_buttons():
    source = REFERENCE_EDITORS_JS.read_text(encoding="utf-8")
    assert 'postJson("/api/rankings_editor/load", { purpose })' in source
    assert 'await postJson("/api/rankings_editor/save", {' in source
    assert 'getRequiredElement("swimmerTypeColorRankingsEditButton")' in source
    assert 'getRequiredElement("swimmerTypeStyleRankingsEditButton")' in source
    assert 'Adding a new ${rankingsEditorState.item_singular} inserts it at rank #1 for every swimmer type.' in source


def test_rankings_editor_supports_arrow_buttons_and_delete():
    source = REFERENCE_EDITORS_JS.read_text(encoding="utf-8")
    assert "function moveRankingsEditorItemByOffset(" in source
    assert "function deleteRankingsEditorItem(" in source
    assert 'moveUp.textContent = "\\u2191";' in source
    assert 'moveDown.textContent = "\\u2193";' in source


def test_rankings_editor_preserves_list_scroll_position_on_rerender():
    source = REFERENCE_EDITORS_JS.read_text(encoding="utf-8")
    assert "let rankingsEditorListScrollTop = 0;" in source
    assert "rankingsEditorListScrollTop = list.scrollTop;" in source
    assert "list.scrollTop = rankingsEditorListScrollTop;" in source


def test_reference_editor_wires_load_save_and_manage_buttons():
    source = REFERENCE_EDITORS_JS.read_text(encoding="utf-8")
    assert 'postJson("/api/reference_table/load", { purpose })' in source
    assert 'await postJson("/api/reference_table/save", {' in source
    assert 'getRequiredElement("personalityColorsManageButton")' in source
    assert 'getRequiredElement("instructorStylesManageButton")' in source
    assert 'getRequiredElement("swimmerTypesManageButton")' in source
    assert "function openReferenceEditorForm(" in source
    assert 'editButton.textContent = "\\u270E";' in source
    assert 'removeButton.textContent = "\\u00D7";' in source
    assert "function deleteReferenceEditorItem(" in source
    assert 'style_code: "Style code e.g DIA"' in source
    assert 'const error = getReferenceEditorElement("reference-editor-form-error");' in source
    assert 'document.getElementById("reference-editor-form-close")' in source


def test_reference_editor_form_validation_uses_popup_error_region():
    source = REFERENCE_EDITORS_JS.read_text(encoding="utf-8")
    form_body = _extract_function(source, "applyReferenceEditorFormChanges", "openReferenceEditor")

    assert "setReferenceEditorFormError(" in source
    assert 'setReferenceEditorFormError(`Enter a ${referenceEditorState.item_singular} name first.`);' in form_body
    assert 'setReferenceEditorFormError(`That ${referenceEditorState.item_singular} already exists.`);' in form_body
    assert 'setReferenceEditorFormError(`Could not find that ${referenceEditorState.item_singular}.`);' in form_body
    assert "setReferenceEditorError(" not in form_body


def test_reference_editors_script_loads_between_shared_utils_and_app():
    source = INDEX_HTML.read_text(encoding="utf-8")
    shared_index = source.index('<script src="./shared/ui_utils.js"></script>')
    editor_index = source.index('<script src="./reference_editors.js"></script>')
    app_index = source.index('<script src="./app.js"></script>')
    assert shared_index < editor_index < app_index


def test_reference_editors_exposes_only_frozen_initializer_namespace():
    source = REFERENCE_EDITORS_JS.read_text(encoding="utf-8")
    assert source.startswith("(() => {")
    assert "function wireReferenceEditors({ postJson: injectedPostJson, getFileNameFromPath: injectedGetFileNameFromPath, refreshUi })" in source
    assert "postJson = injectedPostJson;" in source
    assert "getFileNameFromPath = injectedGetFileNameFromPath;" in source
    assert "refreshUiFromHost = refreshUi;" in source
    assert "window.AquaReferenceEditors = Object.freeze({ wireReferenceEditors });" in source
    assert source.count("window.AquaReferenceEditors") == 1


def test_app_initializes_reference_editors_once_after_generic_file_wiring():
    source = APP_JS.read_text(encoding="utf-8")
    settings_source = SETTINGS_FILES_JS.read_text(encoding="utf-8")
    initializer = "window.AquaReferenceEditors.wireReferenceEditors({"
    assert source.count(initializer) == 1

    generic_wiring = [
        '["swimmer_type_color_rankings", "swimmerTypeColorRankingsBrowseButton", "swimmerTypeColorRankingsResetButton"]',
        '["swimmer_type_style_rankings", "swimmerTypeStyleRankingsBrowseButton", "swimmerTypeStyleRankingsResetButton"]',
        '["personality_colors", "personalityColorsBrowseButton", "personalityColorsResetButton"]',
        '["instructor_styles", "instructorStylesBrowseButton", "instructorStylesResetButton"]',
        '["swimmer_types", "swimmerTypesBrowseButton", "swimmerTypesResetButton"]',
    ]
    for statement in generic_wiring:
        assert settings_source.count(statement) == 1
    assert source.index("settingsFiles.wireSettingsFiles({ setGenerateEnabled });") < source.index(initializer)


def test_instructor_defaults_exposes_only_frozen_initializer_namespace():
    source = INSTRUCTOR_DEFAULTS_JS.read_text(encoding="utf-8")
    assert '"use strict";' in source
    assert "function wireInstructorDefaults({" in source
    assert "window.AquaInstructorDefaults = Object.freeze({ wireInstructorDefaults, loadInstructorDefaults });" in source
    assert source.count("window.AquaInstructorDefaults =") == 1


def test_instructor_defaults_module_owns_both_editors():
    source = INSTRUCTOR_DEFAULTS_JS.read_text(encoding="utf-8")
    assert 'postJson("/api/instructor_defaults", { profile })' in source
    assert 'postJson("/api/settings/default_instructor_profile", { profile })' in source
    assert 'postJson("/api/instructor_style_color_editor/load", {})' in source
    assert 'postJson("/api/instructor_style_color_editor/save", { updates })' in source
    assert "function renderInstructorStyleColorEditor(" in source
    assert "function applyInstructorDefaultsProfile(" in source
    assert "const DEFAULT_INSTRUCTOR_APP_PROFILE = {" in source
    assert "can_teach_NL: true" in source
    assert "can_teach_babies: false" in source
    assert "can_teach_adults: false" in source
    assert "can_teach_adapted: false" in source


def test_instructor_defaults_script_loads_before_app():
    source = INDEX_HTML.read_text(encoding="utf-8")
    shared_index = source.index('<script src="./shared/ui_utils.js"></script>')
    module_index = source.index('<script src="./instructor_defaults.js"></script>')
    app_index = source.index('<script src="./app.js"></script>')
    assert shared_index < module_index < app_index


def test_app_wires_instructor_defaults_before_first_refresh():
    source = APP_JS.read_text(encoding="utf-8")
    settings_source = SETTINGS_FILES_JS.read_text(encoding="utf-8")
    initializer = "window.AquaInstructorDefaults.wireInstructorDefaults({"
    delegation = "await window.AquaInstructorDefaults.loadInstructorDefaults(settings);"
    assert source.count(initializer) == 1
    assert settings_source.count(delegation) == 1
    # Wiring injects the helpers before refreshUiFromHost first delegates to
    # the module during initializeUserInterface().
    assert source.index(initializer) < source.index("await Promise.all([")


def test_app_no_longer_contains_instructor_defaults_state_or_functions():
    source = APP_JS.read_text(encoding="utf-8")
    assert "let instructorDefaultAppProfile" not in source
    assert "let instructorStyleColorEditorState" not in source
    assert "const DEFAULT_INSTRUCTOR_APP_PROFILE" not in source
    assert "function applyInstructorDefaultsProfile(" not in source
    assert "function collectInstructorDefaultsProfile(" not in source
    assert "function saveInstructorDefaultsProfile(" not in source
    assert "function renderInstructorStyleColorEditor(" not in source
    assert "function openInstructorStyleColorEditor(" not in source
    assert "function buildInlineSelect(" not in source
    assert 'document.getElementById("instructor-defaults-close")' not in source
    assert 'document.getElementById("instructor-style-color-editor-close")' not in source
    assert "async function loadReferenceTableOptions(" not in source
    assert "async function loadReferenceTableOptions(" in SETTINGS_FILES_JS.read_text(encoding="utf-8")


def test_app_no_longer_contains_reference_editor_state_or_functions():
    source = APP_JS.read_text(encoding="utf-8")
    assert "let rankingsEditorState" not in source
    assert "let referenceEditorState" not in source
    assert "HIDDEN_SWIMMER_TYPE_NAME" not in source
    assert "function getRankingsEditorElement(" not in source
    assert "function saveReferenceEditor(" not in source
    assert 'document.getElementById("rankings-editor-close")' not in source
    assert 'document.getElementById("reference-editor-close")' not in source


def test_settings_files_exposes_frozen_namespace_and_owns_file_workflows():
    source = SETTINGS_FILES_JS.read_text(encoding="utf-8")
    assert source.startswith("(() => {")
    assert '"use strict";' in source
    assert "window.AquaSettingsFiles = Object.freeze({" in source
    for member in (
        "wireSettingsFiles",
        "getFileNameFromPath",
        "getSettingsFromHost",
        "postJson",
        "loadReferenceTableOptions",
        "refreshUiFromHost",
    ):
        assert f"    {member}," in source
    assert 'window.AquaDesktop?.dialogs?.openInputFile' in source
    assert 'selected_path: selected.path' in source
    assert 'postJson("/api/pick_file", { purpose: purposeKey })' in source
    assert 'wireAction("/api/clear_file", "classes", "classesClearButton");' in source
    assert 'fetch("/api/settings/use_db_instructors"' in source


def test_settings_files_script_loads_before_consumers_and_app():
    source = INDEX_HTML.read_text(encoding="utf-8")
    module_index = source.index('<script src="./settings_files.js"></script>')
    instructor_index = source.index('<script src="./instructor_editor.js"></script>')
    generate_index = source.index('<script src="./generate_flow.js"></script>')
    app_index = source.index('<script src="./app.js"></script>')
    assert module_index < instructor_index < app_index
    assert module_index < generate_index < app_index


def test_app_delegates_settings_files_and_drops_file_state_and_helpers():
    source = APP_JS.read_text(encoding="utf-8")
    assert source.count("settingsFiles.wireSettingsFiles({ setGenerateEnabled });") == 1
    assert "let isFilePickerBusy" not in source
    assert "function safePickFile(" not in source
    assert "function renderOneFile(" not in source
    assert "function wireBrowse(" not in source
    assert "function wireReset(" not in source
    assert "function wireClear(" not in source
    assert 'fetch("/api/settings/use_db_instructors"' not in source
