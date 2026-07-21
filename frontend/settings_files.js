(() => {
  "use strict";

  let isFilePickerBusy = false;
  let updateGenerateEnabled = null;

  function getRequiredElement(elementId) {
    const element = document.getElementById(elementId);
    if (!element) throw new Error(`Missing element with id="${elementId}"`);
    return element;
  }

  function getFileNameFromPath(pathOrEmpty) {
    if (!pathOrEmpty) return "no file selected";
    const normalized = String(pathOrEmpty).replaceAll("\\", "/");
    const parts = normalized.split("/");
    return parts[parts.length - 1] || normalized;
  }

  async function getSettingsFromHost() {
    const response = await fetch("/api/settings", { cache: "no-store" });
    if (!response.ok) throw new Error("Failed to load /api/settings");
    return await response.json();
  }

  async function postJson(url, body) {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    });
    if (!response.ok) {
      const responseBody = await response.json().catch(() => ({}));
      throw new Error(responseBody?.error || `Request failed: ${url}`);
    }
    return await response.json().catch(() => ({}));
  }

  async function safePickFile(purposeKey) {
    if (isFilePickerBusy) return { ok: false, busy: true };
    isFilePickerBusy = true;
    try {
      const nativeOpenInputFile = window.AquaDesktop?.dialogs?.openInputFile;
      if (typeof nativeOpenInputFile === "function") {
        const selected = await nativeOpenInputFile(purposeKey);
        if (selected?.cancelled) return { ok: false, cancelled: true };
        if (typeof selected?.path !== "string") return { ok: false, error: "Invalid native dialog response" };
        return await postJson("/api/pick_file", { purpose: purposeKey, selected_path: selected.path }) ?? {};
      }
      return await postJson("/api/pick_file", { purpose: purposeKey }) ?? {};
    } catch (error) {
      return { ok: false, error: String(error) };
    } finally {
      isFilePickerBusy = false;
    }
  }

  function renderOneFile(settings, key, metaElementId, browseButtonId) {
    const selectedPath = settings?.last_selected_files?.[key] ?? "";
    const fileName = getFileNameFromPath(selectedPath);
    const meta = getRequiredElement(metaElementId);
    const browseButton = getRequiredElement(browseButtonId);
    const isClasses = key === "classes";
    const isHistoricalPairings = key === "historical_pairings";

    meta.classList.remove("missing", "valid");
    if (!selectedPath) {
      if (isClasses) {
        meta.classList.add("missing");
        meta.textContent = "Required (not selected)";
      } else {
        meta.classList.add(isHistoricalPairings ? "valid" : "missing");
        meta.textContent = "No file selected";
      }
    } else {
      meta.classList.add("valid");
      meta.textContent = `Selected file: ${fileName}`;
    }
    browseButton.textContent = selectedPath ? "Change file" : "Select file";

    if (key !== "instructors") return;
    const usingDb = Boolean(settings?.use_db_instructors);
    if (usingDb) {
      meta.classList.remove("missing");
      meta.classList.add("valid");
      meta.textContent = "Source: app database — the selected file is ignored while this is on.";
    }
    document.getElementById("instructorsStylesColorsEditButton")?.classList.toggle("hidden", usingDb || !selectedPath);
    document.getElementById("instructorsDbEditorHint")?.classList.toggle("hidden", !usingDb);
    const toggle = document.getElementById("useDbInstructorsToggle");
    if (toggle) toggle.checked = usingDb;
    const browse = document.getElementById("instructorsBrowseButton");
    const reset = document.getElementById("instructorsResetButton");
    if (browse) browse.disabled = usingDb;
    if (reset) reset.disabled = usingDb;
  }

  async function loadReferenceTableOptions(purpose, labelField) {
    const result = await postJson("/api/reference_table/load", { purpose });
    const items = Array.isArray(result?.items) ? result.items : [];
    return items
      .map((item) => ({
        id: Number(item?.id),
        name: String(item?.fields?.[labelField] || item?.id || ""),
      }))
      .filter((item) => Number.isFinite(item.id) && item.id > 0);
  }

  async function refreshUiFromHost(existingSettings = null) {
    const settings = existingSettings ?? await getSettingsFromHost();
    renderOneFile(settings, "classes", "classesFileMeta", "classesBrowseButton");
    renderOneFile(settings, "swimmers", "swimmersFileMeta", "swimmersBrowseButton");
    renderOneFile(settings, "instructors", "instructorsFileMeta", "instructorsBrowseButton");
    renderOneFile(settings, "swimmer_type_color_rankings", "swimmerTypeColorRankingsFileMeta", "swimmerTypeColorRankingsBrowseButton");
    renderOneFile(settings, "swimmer_type_style_rankings", "swimmerTypeStyleRankingsFileMeta", "swimmerTypeStyleRankingsBrowseButton");
    renderOneFile(settings, "personality_colors", "personalityColorsFileMeta", "personalityColorsBrowseButton");
    renderOneFile(settings, "instructor_styles", "instructorStylesFileMeta", "instructorStylesBrowseButton");
    renderOneFile(settings, "swimmer_types", "swimmerTypesFileMeta", "swimmerTypesBrowseButton");
    await window.AquaInstructorDefaults.loadInstructorDefaults(settings);
    updateGenerateEnabled(settings);
    return settings;
  }

  function wireBrowse(purposeKey, buttonId) {
    getRequiredElement(buttonId).addEventListener("click", async () => {
      const output = document.getElementById("output");
      const result = await safePickFile(purposeKey);
      if (result?.busy || result?.cancelled) return;
      if (!result?.ok && output) {
        output.textContent = `Pick failed for "${purposeKey}".\n\n${JSON.stringify(result, null, 2)}`;
      }
      await refreshUiFromHost();
    });
  }

  function wireAction(url, purposeKey, buttonId) {
    getRequiredElement(buttonId).addEventListener("click", async () => {
      const output = document.getElementById("output");
      const result = await postJson(url, { purpose: purposeKey });
      if (!result?.ok && output) {
        output.textContent = `Action failed: ${url}\n\n${JSON.stringify(result, null, 2)}`;
      }
      await refreshUiFromHost();
    });
  }

  function wireFileControls() {
    wireBrowse("classes", "classesBrowseButton");
    wireAction("/api/clear_file", "classes", "classesClearButton");
    wireBrowse("swimmers", "swimmersBrowseButton");
    wireAction("/api/clear_file", "swimmers", "swimmersResetButton");
    wireBrowse("instructors", "instructorsBrowseButton");
    wireAction("/api/clear_file", "instructors", "instructorsResetButton");

    for (const [purpose, browseId, resetId] of [
      ["swimmer_type_color_rankings", "swimmerTypeColorRankingsBrowseButton", "swimmerTypeColorRankingsResetButton"],
      ["swimmer_type_style_rankings", "swimmerTypeStyleRankingsBrowseButton", "swimmerTypeStyleRankingsResetButton"],
      ["personality_colors", "personalityColorsBrowseButton", "personalityColorsResetButton"],
      ["instructor_styles", "instructorStylesBrowseButton", "instructorStylesResetButton"],
      ["swimmer_types", "swimmerTypesBrowseButton", "swimmerTypesResetButton"],
    ]) {
      wireBrowse(purpose, browseId);
      wireAction("/api/reset_file", purpose, resetId);
    }
  }

  function wireInstructorsSourceToggle() {
    const toggle = document.getElementById("useDbInstructorsToggle");
    if (!toggle) return;
    toggle.addEventListener("change", async () => {
      const enabled = toggle.checked;
      toggle.disabled = true;
      try {
        const response = await fetch("/api/settings/use_db_instructors", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ enabled }),
          cache: "no-store",
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || !data?.ok) {
          toggle.checked = !enabled;
          const meta = document.getElementById("instructorsFileMeta");
          if (meta) {
            meta.classList.remove("valid");
            meta.classList.add("missing");
            meta.textContent = data?.error || "Could not update the instructors source.";
          }
          return;
        }
        await refreshUiFromHost();
      } finally {
        toggle.disabled = false;
      }
    });
  }

  function wireSettingsFiles({ setGenerateEnabled }) {
    updateGenerateEnabled = setGenerateEnabled;
    wireFileControls();
    wireInstructorsSourceToggle();
  }

  window.AquaSettingsFiles = Object.freeze({
    wireSettingsFiles,
    getFileNameFromPath,
    getSettingsFromHost,
    postJson,
    loadReferenceTableOptions,
    refreshUiFromHost,
  });
})();
