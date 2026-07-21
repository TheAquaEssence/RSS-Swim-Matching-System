// Default instructor profile modal + instructor style/color file editor —
// extracted from app.js. IIFE-owned: only window.AquaInstructorDefaults is
// exposed; app.js injects its helpers via wireInstructorDefaults() and calls
// loadInstructorDefaults() from refreshUiFromHost().
(() => {
  "use strict";

  let postJson = null;
  let getSettingsFromHost = null;
  let getFileNameFromPath = null;
  let loadReferenceTableOptions = null;
  let esc = null;

  let instructorDefaultAppProfile = null;
  let instructorStyleColorEditorState = null;

  const DEFAULT_INSTRUCTOR_APP_PROFILE = {
    primary_color_id: 1,
    secondary_color_id: 2,
    primary_style_id: 6,
    secondary_style_id: 5,
    is_team_captain: false,
    can_teach_NL: true,
    can_teach_babies: true,
    can_teach_adults: true,
    can_teach_adapted: true,
  };

  function setInstructorDefaultsMeta(message, isError = false) {
    ["instructorDefaultsMeta", "instructorDefaultsModalMeta"].forEach((id) => {
      const meta = document.getElementById(id);
      if (!meta) return;
      meta.classList.remove("missing", "valid");
      if (isError) meta.classList.add("missing");
      else meta.classList.add("valid");
      meta.textContent = message;
    });
  }

  function populateSelectOptions(selectId, options, selectedValue) {
    const select = document.getElementById(selectId);
    if (!select) return;
    select.innerHTML = "";
    const normalizedOptions = Array.isArray(options) ? [...options] : [];
    const selectedNumber = Number(selectedValue);
    if (
      Number.isFinite(selectedNumber) &&
      selectedNumber > 0 &&
      !normalizedOptions.some((option) => Number(option?.id) === selectedNumber)
    ) {
      normalizedOptions.unshift({ id: selectedNumber, name: `ID ${selectedNumber}` });
    }
    if (normalizedOptions.length === 0) {
      normalizedOptions.push({ id: selectedNumber > 0 ? selectedNumber : 0, name: "No options loaded" });
    }
    normalizedOptions.forEach((option) => {
      const el = document.createElement("option");
      el.value = String(option.id);
      el.textContent = `${option.name} (${option.id})`;
      if (Number(option.id) === Number(selectedValue)) {
        el.selected = true;
      }
      select.appendChild(el);
    });
  }

  function applyInstructorDefaultsProfile(profile, data) {
    if (!profile) return;
    instructorDefaultAppProfile = data?.app_defaults || instructorDefaultAppProfile || { ...DEFAULT_INSTRUCTOR_APP_PROFILE };
    populateSelectOptions("defaultInstructorPrimaryColor", data?.colors, profile.primary_color_id);
    populateSelectOptions("defaultInstructorSecondaryColor", data?.colors, profile.secondary_color_id);
    populateSelectOptions("defaultInstructorPrimaryStyle", data?.styles, profile.primary_style_id);
    populateSelectOptions("defaultInstructorSecondaryStyle", data?.styles, profile.secondary_style_id);

    const checkboxMap = {
      defaultInstructorCanTeachNL: profile.can_teach_NL,
      defaultInstructorCanTeachBabies: profile.can_teach_babies,
      defaultInstructorCanTeachAdults: profile.can_teach_adults,
      defaultInstructorCanTeachAdapted: profile.can_teach_adapted,
      defaultInstructorTeamCaptain: profile.is_team_captain,
    };
    Object.entries(checkboxMap).forEach(([id, value]) => {
      const input = document.getElementById(id);
      if (input) input.checked = Boolean(value);
    });
  }

  function collectInstructorDefaultsProfile() {
    const getNumber = (id) => Number(document.getElementById(id)?.value || 0);
    const getChecked = (id) => Boolean(document.getElementById(id)?.checked);
    return {
      primary_color_id: getNumber("defaultInstructorPrimaryColor"),
      secondary_color_id: getNumber("defaultInstructorSecondaryColor"),
      primary_style_id: getNumber("defaultInstructorPrimaryStyle"),
      secondary_style_id: getNumber("defaultInstructorSecondaryStyle"),
      can_teach_NL: getChecked("defaultInstructorCanTeachNL"),
      can_teach_babies: getChecked("defaultInstructorCanTeachBabies"),
      can_teach_adults: getChecked("defaultInstructorCanTeachAdults"),
      can_teach_adapted: getChecked("defaultInstructorCanTeachAdapted"),
      is_team_captain: getChecked("defaultInstructorTeamCaptain"),
    };
  }

  async function saveInstructorDefaultsProfile(profile) {
    try {
      return await postJson("/api/instructor_defaults", { profile });
    } catch (primaryError) {
      try {
        return await postJson("/api/settings/default_instructor_profile", { profile });
      } catch (fallbackError) {
        const primaryMessage = String(primaryError?.message || primaryError || "");
        const fallbackMessage = String(fallbackError?.message || fallbackError || "");
        const routeMissing =
          primaryMessage.includes("Request failed: /api/instructor_defaults") ||
          fallbackMessage.includes("Request failed: /api/settings/default_instructor_profile");
        if (routeMissing) {
          throw new Error(
            "The desktop backend needs to be rebuilt and restarted before instructor default saving is available."
          );
        }
        throw new Error(
          [primaryMessage, fallbackMessage].filter(Boolean).join(" | ")
        );
      }
    }
  }

  async function loadInstructorDefaults(settingsFromHost = null) {
    const settings = settingsFromHost || await getSettingsFromHost();
    const fallbackProfile = settings?.default_instructor_profile || { ...DEFAULT_INSTRUCTOR_APP_PROFILE };
    instructorDefaultAppProfile = settings?.app_default_instructor_profile || instructorDefaultAppProfile || { ...DEFAULT_INSTRUCTOR_APP_PROFILE };

    try {
      const response = await fetch("/api/instructor_defaults", { cache: "no-store" });
      const data = await response.json();
      if (
        response.ok &&
        data?.ok &&
        Array.isArray(data?.colors) &&
        data.colors.length > 0 &&
        Array.isArray(data?.styles) &&
        data.styles.length > 0
      ) {
        applyInstructorDefaultsProfile(data.profile, data);
        setInstructorDefaultsMeta("Default instructor profile loaded.");
        return;
      }
    } catch {
      // Fall through to resilient loaders below.
    }

    try {
      const [colors, styles] = await Promise.all([
        loadReferenceTableOptions("personality_colors", "color_name"),
        loadReferenceTableOptions("instructor_styles", "style_name"),
      ]);
      applyInstructorDefaultsProfile(fallbackProfile, {
        app_defaults: instructorDefaultAppProfile,
        colors,
        styles,
      });
      setInstructorDefaultsMeta("Default instructor profile loaded.");
    } catch (e) {
      applyInstructorDefaultsProfile(fallbackProfile, {
        app_defaults: instructorDefaultAppProfile,
        colors: [],
        styles: [],
      });
      setInstructorDefaultsMeta(`Could not fully load instructor defaults: ${String(e)}`, true);
    }
  }

  function openInstructorDefaultsModal() {
    const modal = document.getElementById("instructor-defaults-modal");
    if (modal) modal.showModal();
  }

  function closeInstructorDefaultsModal() {
    const modal = document.getElementById("instructor-defaults-modal");
    if (modal?.open) modal.close();
  }

  function setInstructorStyleColorEditorError(message) {
    const error = document.getElementById("instructor-style-color-editor-error");
    if (!error) return;
    if (message) {
      error.textContent = message;
      error.classList.remove("hidden");
    } else {
      error.textContent = "";
      error.classList.add("hidden");
    }
  }

  function setInstructorStyleColorEditorMeta(message) {
    const meta = document.getElementById("instructor-style-color-editor-meta");
    if (meta) meta.textContent = message;
  }

  function buildInlineSelect(options, selectedValue, onChange) {
    const select = document.createElement("select");
    select.className = "instructor-style-color-editor-select";
    const normalizedOptions = Array.isArray(options) ? options : [];
    normalizedOptions.forEach((option) => {
      const element = document.createElement("option");
      element.value = String(option.id);
      element.textContent = `${option.name} (${option.id})`;
      if (Number(option.id) === Number(selectedValue)) {
        element.selected = true;
      }
      select.appendChild(element);
    });
    select.addEventListener("change", () => onChange(Number(select.value || 0)));
    return select;
  }

  function renderInstructorStyleColorEditor() {
    const body = document.getElementById("instructor-style-color-editor-body");
    if (!body || !instructorStyleColorEditorState) return;

    const query = String(instructorStyleColorEditorState.query || "").trim().toLowerCase();
    const rows = (instructorStyleColorEditorState.rows || []).filter((row) => {
      if (!query) return true;
      const haystack = `${row.name || ""} ${row.position || ""}`.toLowerCase();
      return haystack.includes(query);
    });

    body.innerHTML = "";
    if (rows.length === 0) {
      const emptyRow = document.createElement("tr");
      emptyRow.innerHTML = '<td colspan="6" class="instructor-style-color-editor-empty">No instructors match this filter.</td>';
      body.appendChild(emptyRow);
    } else {
      rows.forEach((row) => {
        const tr = document.createElement("tr");
        const nameCell = document.createElement("td");
        const nameWrapper = document.createElement("div");
        nameWrapper.className = "instructor-style-color-editor-name";
        nameWrapper.textContent = row.name || "Unnamed instructor";
        nameCell.appendChild(nameWrapper);
        if (row.used_default_profile) {
          const badge = document.createElement("div");
          badge.className = "instructor-style-color-editor-badge";
          badge.textContent = "Using defaults";
          nameCell.appendChild(badge);
        }
        tr.appendChild(nameCell);

        const positionCell = document.createElement("td");
        positionCell.textContent = row.position || "Instructor";
        tr.appendChild(positionCell);

        const primaryColorCell = document.createElement("td");
        primaryColorCell.appendChild(buildInlineSelect(instructorStyleColorEditorState.colors, row.primary_color_id, (value) => {
          row.primary_color_id = value;
        }));
        tr.appendChild(primaryColorCell);

        const secondaryColorCell = document.createElement("td");
        secondaryColorCell.appendChild(buildInlineSelect(instructorStyleColorEditorState.colors, row.secondary_color_id, (value) => {
          row.secondary_color_id = value;
        }));
        tr.appendChild(secondaryColorCell);

        const primaryStyleCell = document.createElement("td");
        primaryStyleCell.appendChild(buildInlineSelect(instructorStyleColorEditorState.styles, row.primary_style_id, (value) => {
          row.primary_style_id = value;
        }));
        tr.appendChild(primaryStyleCell);

        const secondaryStyleCell = document.createElement("td");
        secondaryStyleCell.appendChild(buildInlineSelect(instructorStyleColorEditorState.styles, row.secondary_style_id, (value) => {
          row.secondary_style_id = value;
        }));
        tr.appendChild(secondaryStyleCell);

        body.appendChild(tr);
      });
    }

    const totalCount = instructorStyleColorEditorState.rows.length;
    const sourceFile = instructorStyleColorEditorState.source_file_name || getFileNameFromPath(instructorStyleColorEditorState.source_path || "");
    setInstructorStyleColorEditorMeta(
      `${rows.length} of ${totalCount} instructor row(s) shown from ${sourceFile || "the selected file"}`
    );
  }

  async function openInstructorStyleColorEditor() {
    const modal = document.getElementById("instructor-style-color-editor-modal");
    if (!modal) return;
    setInstructorStyleColorEditorError("");
    setInstructorStyleColorEditorMeta("Loading instructor file...");

    const result = await postJson("/api/instructor_style_color_editor/load", {});
    instructorStyleColorEditorState = {
      rows: Array.isArray(result?.instructors) ? result.instructors : [],
      colors: Array.isArray(result?.colors) ? result.colors : [],
      styles: Array.isArray(result?.styles) ? result.styles : [],
      query: "",
      source_path: result?.source_path || "",
      source_file_name: result?.source_file_name || "",
    };

    const search = document.getElementById("instructor-style-color-editor-search");
    if (search) search.value = "";
    renderInstructorStyleColorEditor();
    modal.showModal();
  }

  function closeInstructorStyleColorEditor() {
    const modal = document.getElementById("instructor-style-color-editor-modal");
    if (modal?.open) modal.close();
    setInstructorStyleColorEditorError("");
  }

  async function saveInstructorStyleColorEditor() {
    if (!instructorStyleColorEditorState) return;
    const updates = instructorStyleColorEditorState.rows.map((row) => ({
      source_row_number: row.source_row_number,
      primary_color_id: Number(row.primary_color_id || 0),
      secondary_color_id: Number(row.secondary_color_id || 0),
      primary_style_id: Number(row.primary_style_id || 0),
      secondary_style_id: Number(row.secondary_style_id || 0),
    }));
    const result = await postJson("/api/instructor_style_color_editor/save", { updates });
    instructorStyleColorEditorState = {
      rows: Array.isArray(result?.instructors) ? result.instructors : [],
      colors: Array.isArray(result?.colors) ? result.colors : [],
      styles: Array.isArray(result?.styles) ? result.styles : [],
      query: String(document.getElementById("instructor-style-color-editor-search")?.value || ""),
      source_path: result?.source_path || "",
      source_file_name: result?.source_file_name || "",
    };
    setInstructorStyleColorEditorError("");
    renderInstructorStyleColorEditor();
  }

  function wireInstructorDefaults({
    postJson: injectedPostJson,
    getSettingsFromHost: injectedGetSettingsFromHost,
    getFileNameFromPath: injectedGetFileNameFromPath,
    loadReferenceTableOptions: injectedLoadReferenceTableOptions,
    esc: injectedEsc,
  }) {
    postJson = injectedPostJson;
    getSettingsFromHost = injectedGetSettingsFromHost;
    getFileNameFromPath = injectedGetFileNameFromPath;
    loadReferenceTableOptions = injectedLoadReferenceTableOptions;
    esc = injectedEsc;

    const instructorsStylesColorsEditButton = document.getElementById("instructorsStylesColorsEditButton");
    if (instructorsStylesColorsEditButton) {
      instructorsStylesColorsEditButton.addEventListener("click", async () => {
        instructorsStylesColorsEditButton.disabled = true;
        try {
          await openInstructorStyleColorEditor();
        } catch (e) {
          const output = document.getElementById("output");
          if (output) {
            output.classList.remove("hidden");
            output.innerHTML = `<div class="status-error"><span class="status-icon" aria-hidden="true">✗</span><span>${esc(String(e))}</span></div>`;
          }
        } finally {
          instructorsStylesColorsEditButton.disabled = false;
        }
      });
    }

    const defaultInstructorEditButton = document.getElementById("defaultInstructorEditButton");
    if (defaultInstructorEditButton) {
      defaultInstructorEditButton.addEventListener("click", openInstructorDefaultsModal);
    }

    const saveInstructorDefaultsButton = document.getElementById("saveInstructorDefaultsButton");
    if (saveInstructorDefaultsButton) {
      saveInstructorDefaultsButton.addEventListener("click", async () => {
        saveInstructorDefaultsButton.disabled = true;
        try {
          const result = await saveInstructorDefaultsProfile(collectInstructorDefaultsProfile());
          applyInstructorDefaultsProfile(result.profile, result);
          setInstructorDefaultsMeta("Saved default instructor profile.");
        } catch (e) {
          setInstructorDefaultsMeta(`Could not save instructor defaults: ${String(e)}`, true);
        } finally {
          saveInstructorDefaultsButton.disabled = false;
        }
      });
    }

    const resetInstructorDefaultsButton = document.getElementById("resetInstructorDefaultsButton");
    if (resetInstructorDefaultsButton) {
      resetInstructorDefaultsButton.addEventListener("click", async () => {
        if (!instructorDefaultAppProfile) {
          await loadInstructorDefaults();
          if (!instructorDefaultAppProfile) return;
        }
        applyInstructorDefaultsProfile(instructorDefaultAppProfile, { app_defaults: instructorDefaultAppProfile });
        try {
          const result = await saveInstructorDefaultsProfile(instructorDefaultAppProfile);
          applyInstructorDefaultsProfile(result.profile, result);
          setInstructorDefaultsMeta("Reset default instructor profile to app defaults.");
        } catch (e) {
          setInstructorDefaultsMeta(`Could not reset instructor defaults: ${String(e)}`, true);
        }
      });
    }

    const instructorDefaultsClose = document.getElementById("instructor-defaults-close");
    const instructorDefaultsCancel = document.getElementById("instructorDefaultsCancelButton");
    const instructorStyleColorEditorClose = document.getElementById("instructor-style-color-editor-close");
    const instructorStyleColorEditorCancel = document.getElementById("instructor-style-color-editor-cancel");
    const instructorStyleColorEditorSave = document.getElementById("instructor-style-color-editor-save");
    const instructorStyleColorEditorSearch = document.getElementById("instructor-style-color-editor-search");
    const instructorDefaultsDialog = document.getElementById("instructor-defaults-modal");
    const instructorStyleColorEditorDialog = document.getElementById("instructor-style-color-editor-modal");
    if (instructorDefaultsDialog) {
      instructorDefaultsDialog.addEventListener("cancel", (e) => { e.preventDefault(); closeInstructorDefaultsModal(); });
    }
    if (instructorStyleColorEditorDialog) {
      instructorStyleColorEditorDialog.addEventListener("cancel", (e) => { e.preventDefault(); closeInstructorStyleColorEditor(); });
    }
    if (instructorDefaultsClose) instructorDefaultsClose.addEventListener("click", closeInstructorDefaultsModal);
    if (instructorDefaultsCancel) instructorDefaultsCancel.addEventListener("click", closeInstructorDefaultsModal);
    if (instructorStyleColorEditorClose) instructorStyleColorEditorClose.addEventListener("click", closeInstructorStyleColorEditor);
    if (instructorStyleColorEditorCancel) instructorStyleColorEditorCancel.addEventListener("click", closeInstructorStyleColorEditor);

    if (instructorStyleColorEditorSearch) {
      instructorStyleColorEditorSearch.addEventListener("input", () => {
        if (!instructorStyleColorEditorState) return;
        instructorStyleColorEditorState.query = instructorStyleColorEditorSearch.value || "";
        renderInstructorStyleColorEditor();
      });
    }
    if (instructorStyleColorEditorSave) {
      instructorStyleColorEditorSave.addEventListener("click", async () => {
        instructorStyleColorEditorSave.disabled = true;
        try {
          await saveInstructorStyleColorEditor();
        } catch (e) {
          setInstructorStyleColorEditorError(String(e));
        } finally {
          instructorStyleColorEditorSave.disabled = false;
        }
      });
    }
  }

  window.AquaInstructorDefaults = Object.freeze({ wireInstructorDefaults, loadInstructorDefaults });
})();
