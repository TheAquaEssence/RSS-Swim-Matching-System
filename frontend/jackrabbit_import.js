(function () {
  "use strict";

  function getOperatorName() {
    try {
      return (localStorage.getItem("aqua_operator_name") || "").trim();
    } catch {
      return "";
    }
  }

  function setImportStatus(message, kind = "") {
    const status = document.getElementById("jackrabbitImportStatus");
    if (!status) return;
    status.textContent = message;
    status.classList.remove("missing", "valid");
    if (kind) status.classList.add(kind);
  }

  function importSummary(result) {
    const counts = result?.row_counts || {};
    const students = counts["jackrabbit_students.csv"] ?? 0;
    const classes = counts["jackrabbit_classes.csv"] ?? 0;
    const staff = counts["jackrabbit_staff.csv"] ?? 0;
    const history = result?.pairings_imported ?? 0;
    return `Ready: ${students} swimmers, ${classes} classes, ${staff} staff, ${history} historical pairings imported.`;
  }

  function renderImportWarnings(output, warnings) {
    output.replaceChildren();
    output.classList.remove("hidden");
    const heading = document.createElement("p");
    heading.textContent = `Jackrabbit import completed with ${warnings.length} review item(s):`;
    const list = document.createElement("ul");
    for (const warning of warnings) {
      const item = document.createElement("li");
      item.textContent = String(warning);
      list.appendChild(item);
    }
    output.append(heading, list);
  }

  async function uploadJackrabbitBundle(file) {
    const button = document.getElementById("jackrabbitImportButton");
    if (!button) return;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    button.textContent = "Importing…";
    setImportStatus(`Checking ${file.name}…`);

    try {
      if (file.name !== "aqua_essence_jackrabbit_export.json") {
        throw new Error("Choose aqua_essence_jackrabbit_export.json from Jackrabbit Exporter 1.1.0.");
      }
      const form = new FormData();
      form.append("file", file, file.name);
      form.append("operator", getOperatorName());
      const response = await fetch("/api/jackrabbit/import", {
        method: "POST",
        body: form,
        cache: "no-store",
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok || !result?.ok) {
        throw new Error(result?.error || "The Jackrabbit export could not be imported.");
      }

      setImportStatus(importSummary(result), "valid");
      await window.AquaSettingsFiles.refreshUiFromHost();

      const warnings = Array.isArray(result.warnings) ? result.warnings : [];
      const output = document.getElementById("output");
      if (output && warnings.length) {
        renderImportWarnings(output, warnings);
      }
    } catch (error) {
      setImportStatus(error instanceof Error ? error.message : String(error), "missing");
    } finally {
      button.disabled = false;
      button.removeAttribute("aria-busy");
      button.textContent = "Import export";
    }
  }

  function wireJackrabbitImport() {
    const button = document.getElementById("jackrabbitImportButton");
    const input = document.getElementById("jackrabbitImportFileInput");
    if (!button || !input) return;

    button.addEventListener("click", () => input.click());
    input.addEventListener("change", () => {
      const file = input.files?.[0];
      input.value = "";
      if (file) void uploadJackrabbitBundle(file);
    });
  }

  document.addEventListener("DOMContentLoaded", wireJackrabbitImport);
})();
