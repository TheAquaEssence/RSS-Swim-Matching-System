// Generate flow — error/warning/diagnostics rendering, data-sources
// summary, results table, and the Generate button handler — extracted from
// app.js (D2). Classic script: shares the global scope; wireGenerateFlow()
// is called from initializeUserInterface() in app.js.

function renderImportDiagnosticsHtml(diagnostics) {
  if (!diagnostics || typeof diagnostics !== "object") return "";

  const issues = Array.isArray(diagnostics.issues) ? diagnostics.issues.filter(Boolean) : [];
  const partnerImports = diagnostics.partner_imports && typeof diagnostics.partner_imports === "object"
    ? Object.entries(diagnostics.partner_imports)
    : [];

  if (issues.length === 0 && partnerImports.length === 0) return "";

  const summaryItems = partnerImports.map(([key, entry]) => {
    const labelMap = {
      classes: "Classes",
      swimmers: "Swimmers",
      instructors: "Instructors",
    };
    const label = labelMap[key] || key;
    const sourceRows = entry?.source_rows ?? "?";
    const importedRows = entry?.imported_rows ?? "?";
    const skippedRows = entry?.skipped_rows ?? 0;
    if (key === "classes") {
      return `<li><strong>${esc(label)}:</strong> imported ${esc(String(importedRows))} internal class row(s) from ${esc(String(sourceRows))} source row(s)` +
        `${Number(skippedRows) > 0 ? `, skipped ${esc(String(skippedRows))}` : ""}</li>`;
    }
    return `<li><strong>${esc(label)}:</strong> imported ${esc(String(importedRows))} of ${esc(String(sourceRows))} row(s)` +
      `${Number(skippedRows) > 0 ? `, skipped ${esc(String(skippedRows))}` : ""}</li>`;
  }).join("");

  const issueItems = issues.map((message) => `<li>${esc(String(message))}</li>`).join("");
  return (
    '<div class="status-warning">' +
    '<span class="status-icon" aria-hidden="true">\u26A0</span>' +
    '<div class="status-warning-body">' +
    '<div class="status-warning-title">Import check</div>' +
    (summaryItems ? `<ul class="status-warning-list">${summaryItems}</ul>` : "") +
    (issueItems ? `<ul class="status-warning-list">${issueItems}</ul>` : "") +
    '</div>' +
    '</div>'
  );
}

function renderGenerateWarningsHtml(warnings) {
  const items = Array.isArray(warnings) ? warnings.filter(Boolean) : [];
  if (items.length === 0) return "";
  const listItems = items.map((w) => `<li>${esc(String(w))}</li>`).join("");
  return (
    '<div class="status-warning">' +
    '<span class="status-icon" aria-hidden="true">⚠</span>' +
    '<div class="status-warning-body">' +
    '<div class="status-warning-title">Warnings</div>' +
    `<ul class="status-warning-list">${listItems}</ul>` +
    '</div>' +
    '</div>'
  );
}

function extractMissingInstructorName(errorText) {
  const match = String(errorText || "").match(/No instructor found matching '([^']+)'/);
  return match ? match[1] : "";
}

function summarizeMissingInstructorNames(result) {
  const diagnosticsList = Array.isArray(result?.import_diagnostics?.missing_instructors)
    ? result.import_diagnostics.missing_instructors.filter(Boolean)
    : [];

  const names = diagnosticsList.length > 0
    ? diagnosticsList
    : (() => {
        const single = extractMissingInstructorName(result?.error || "");
        return single ? [single] : [];
      })();

  if (names.length === 0) {
    return { names: [], summaryHtml: "" };
  }

  const shown = names.slice(0, 3);
  const extraCount = Math.max(names.length - shown.length, 0);
  const parts = shown.map((name) => `<code>${esc(String(name))}</code>`);
  let summaryHtml = parts.join(", ");
  if (extraCount > 0) {
    summaryHtml += `, and ${esc(String(extraCount))} more`;
  }
  return { names, summaryHtml };
}

function summarizeMissingRegisteredClasses(result) {
  const diagnosticsList = Array.isArray(result?.import_diagnostics?.missing_registered_classes)
    ? result.import_diagnostics.missing_registered_classes.filter(Boolean)
    : [];

  if (diagnosticsList.length === 0) {
    return { names: [], summaryHtml: "" };
  }

  const shown = diagnosticsList.slice(0, 3);
  const extraCount = Math.max(diagnosticsList.length - shown.length, 0);
  const parts = shown.map((name) => `<code>${esc(String(name))}</code>`);
  let summaryHtml = parts.join(", ");
  if (extraCount > 0) {
    summaryHtml += `, and ${esc(String(extraCount))} more`;
  }
  return { names: diagnosticsList, summaryHtml };
}

function renderGenerateErrorHtml(result) {
  const errorText = String(result?.error || "Generate failed.");
  const missingInstructorSummary = summarizeMissingInstructorNames(result);
  const missingRegisteredClassSummary = summarizeMissingRegisteredClasses(result);
  const diagnosticsHtml = renderImportDiagnosticsHtml(result?.import_diagnostics);
  const raw = esc(JSON.stringify(result, null, 2));

  if (missingInstructorSummary.names.length > 0) {
    return (
      `<div class="status-error">` +
      `<span class="status-icon" aria-hidden="true">\u2717</span>` +
      `<div class="status-warning-body">` +
      `<div><strong>We couldn't generate because one or more class instructor names could not be matched to the selected instructor file.</strong></div>` +
      `<div>Missing instructor name${missingInstructorSummary.names.length === 1 ? "" : "s"}: ${missingInstructorSummary.summaryHtml}</div>` +
      `<ul class="status-warning-list">` +
      `<li>The app checks full names first, then falls back to first name plus abbreviated last name such as <code>Mitchell M.</code>.</li>` +
      `<li>Check the instructor name in the selected classes file and make sure it matches the real staff file spelling.</li>` +
      `<li>Make sure that instructor exists in the selected staff file as an active teaching role.</li>` +
      `<li>Only these staff positions are imported as instructors: Instructor, Instructor Team Captain, Youth Leader, Aquafit Instructor, and Coach.</li>` +
      `</ul>` +
      `${diagnosticsHtml}` +
      `<details><summary>Technical details</summary><pre>${raw}</pre></details>` +
      `</div>` +
      `</div>`
    );
  }

  if (missingRegisteredClassSummary.names.length > 0) {
    return (
      `<div class="status-error">` +
      `<span class="status-icon" aria-hidden="true">\u2717</span>` +
      `<div class="status-warning-body">` +
      `<div><strong>We couldn't generate because one or more swimmers are registered in class names that do not exist in the selected classes file.</strong></div>` +
      `<div>Missing class name${missingRegisteredClassSummary.names.length === 1 ? "" : "s"}: ${missingRegisteredClassSummary.summaryHtml}</div>` +
      `<ul class="status-warning-list">` +
      `<li>Check the class name in the students file and make sure it matches the selected classes file exactly.</li>` +
      `<li>Make sure the matching class row exists and is marked active in the selected classes file.</li>` +
      `<li>If the class title changed in Jackrabbit, refresh the students and classes exports so both files use the same class names.</li>` +
      `</ul>` +
      `${diagnosticsHtml}` +
      `<details><summary>Technical details</summary><pre>${raw}</pre></details>` +
      `</div>` +
      `</div>`
    );
  }

  const errorKind = String(result?.error_kind || "");

  if (errorKind === "solver_timeout") {
    return (
      `<div class="status-error">` +
      `<span class="status-icon" aria-hidden="true">\u2717</span>` +
      `<div class="status-warning-body">` +
      `<div><strong>The matching run took too long and was stopped.</strong></div>` +
      `<ul class="status-warning-list">` +
      `<li>Runs are limited to 5 minutes. Very large swimmer or class files, or a lot of selected history, can push past that.</li>` +
      `<li>Try deselecting older historical sessions to shrink the problem, then generate again.</li>` +
      `<li>If it keeps timing out with your normal files, re-run once more \u2014 solve times vary between runs.</li>` +
      `</ul>` +
      `${diagnosticsHtml}` +
      `<details><summary>Technical details</summary><pre>${raw}</pre></details>` +
      `</div>` +
      `</div>`
    );
  }

  if (errorKind === "missing_input_file" || errorKind === "empty_input_file") {
    const tip = errorKind === "missing_input_file"
      ? `<li>The file may have been moved, renamed, or deleted since it was selected. Re-select it in the Required input card.</li>`
      : `<li>The file exists but has no data rows (header only). Re-export it from Jackrabbit, or select a different file in the Required input card.</li>`;
    return (
      `<div class="status-error">` +
      `<span class="status-icon" aria-hidden="true">\u2717</span>` +
      `<div class="status-warning-body">` +
      `<div><strong>${esc(errorText)}</strong></div>` +
      `<ul class="status-warning-list">` +
      tip +
      `</ul>` +
      `${diagnosticsHtml}` +
      `<details><summary>Technical details</summary><pre>${raw}</pre></details>` +
      `</div>` +
      `</div>`
    );
  }

  if (errorKind === "solver_failed") {
    return (
      `<div class="status-error">` +
      `<span class="status-icon" aria-hidden="true">\u2717</span>` +
      `<div class="status-warning-body">` +
      `<div><strong>The matching engine stopped before producing a result.</strong></div>` +
      `<ul class="status-warning-list">` +
      `<li>This is usually a mismatch between the selected files \u2014 make sure classes, swimmers, and instructors come from the same export batch.</li>` +
      `<li>If you just changed file selections, double-check each row in the Required input card.</li>` +
      `<li>The full error is recorded in the app's <code>logs/</code> folder for troubleshooting.</li>` +
      `</ul>` +
      `${diagnosticsHtml}` +
      `<details><summary>Technical details</summary><pre>${raw}</pre></details>` +
      `</div>` +
      `</div>`
    );
  }

  return (
    `<div class="status-error">` +
    `<span class="status-icon" aria-hidden="true">\u2717</span>` +
    `<div class="status-warning-body">` +
    `<div><strong>${esc(errorText)}</strong></div>` +
    `${diagnosticsHtml}` +
    `<details><summary>Technical details</summary><pre>${raw}</pre></details>` +
    `</div>` +
    `</div>`
  );
}

// C1: compact "what will this run actually use?" line above the Generate
// button. Re-rendered whenever the file/settings state changes
// (setGenerateEnabled) and whenever the session selection changes.
let dataSourcesSummarySettings = null;
let dataSourcesDbInstructorCount = null;

function renderDataSourcesSummary() {
  const el = document.getElementById("dataSourcesSummary");
  if (!el) return;
  const settings = dataSourcesSummarySettings;
  if (!settings) { el.classList.add("hidden"); return; }

  const filePart = (key) => {
    const path = settings?.last_selected_files?.[key] ?? "";
    return path
      ? esc(window.AquaSettingsFiles.getFileNameFromPath(path))
      : `<span class="missing">${esc(key)} (not selected)</span>`;
  };

  const parts = [filePart("classes"), filePart("swimmers")];

  if (settings?.use_db_instructors) {
    parts.push(dataSourcesDbInstructorCount === null
      ? "instructors (database)"
      : `instructors (database, ${dataSourcesDbInstructorCount})`);
  } else {
    parts.push(filePart("instructors"));
  }

  const sessions = typeof window._getSessionSummary === "function"
    ? window._getSessionSummary()
    : null;
  if (sessions && sessions.total > 0) {
    parts.push(sessions.selected === sessions.total
      ? `history (${sessions.total} session${sessions.total === 1 ? "" : "s"})`
      : `history (${sessions.selected} of ${sessions.total} sessions)`);
  } else {
    parts.push("history (none)");
  }

  el.innerHTML = `Will match using: ${parts.join('<span class="sep">·</span>')}`;
  el.classList.remove("hidden");
}

function refreshDbInstructorCount(settings) {
  if (!settings?.use_db_instructors) {
    dataSourcesDbInstructorCount = null;
    return;
  }
  fetch("/api/instructors/stats", { cache: "no-store" })
    .then((r) => r.json())
    .then((data) => {
      const total = Number(data?.total);
      dataSourcesDbInstructorCount = data?.ok && Number.isFinite(total) ? total : null;
      renderDataSourcesSummary();
    })
    .catch(() => { /* count is cosmetic — leave it off */ });
}

function setGenerateEnabled(settings) {
  const generateButton = getElementByIdOrThrow("generateButton");
  const classesPath = settings?.last_selected_files?.classes ?? "";
  const swimmersPath = settings?.last_selected_files?.swimmers ?? "";
  const instructorsPath = settings?.last_selected_files?.instructors ?? "";
  const instructorsReady = Boolean(instructorsPath) || Boolean(settings?.use_db_instructors);
  const isReady = Boolean(classesPath && swimmersPath && instructorsReady);
  generateButton.disabled = !isReady;

  const sourceStatus = document.getElementById("sourceValidationStatus");
  if (sourceStatus) {
    sourceStatus.textContent = isReady ? "Sources ready" : "Sources incomplete";
    sourceStatus.classList.toggle("status-badge-ready", isReady);
  }

  const readinessStatus = document.getElementById("runReadinessStatus");
  if (readinessStatus) {
    readinessStatus.textContent = isReady
      ? "All required sources are selected. The run is ready to generate."
      : "Select classes, swimmers, and an instructor source to continue.";
    readinessStatus.classList.toggle("run-status-ready", isReady);
  }

  dataSourcesSummarySettings = settings;
  refreshDbInstructorCount(settings);
  renderDataSourcesSummary();
}

function renderResults(result) {
  const section = document.getElementById("results-section");
  const summary = document.getElementById("results-summary");
  const tbody = document.getElementById("results-body");
  if (!section || !summary || !tbody) return;

  setExplainabilityAvailable(true);
  setResultsAvailable(true);
  window.AquaProfileDrawer.setLatestMatchResult(result);
  const s = result.summary ?? {};
  const avg = formatConfidence(s.avg_confidence);

  summary.innerHTML =
    `<div class="results-stat"><span class="stat-label">Assigned Swimmers</span><span class="stat-value">${s.assigned_swimmers ?? "?"}</span></div>` +
    `<div class="results-stat"><span class="stat-label">Unassigned Swimmers</span><span class="stat-value">${s.unassigned_swimmers ?? "?"}</span></div>` +
    `<div class="results-stat"><span class="stat-label">Classes</span><span class="stat-value">${s.classes ?? "?"}</span></div>` +
    `<div class="results-stat"><span class="stat-label">Empty Classes</span><span class="stat-value">${s.empty_classes ?? "?"}</span></div>` +
    `<div class="results-stat"><span class="stat-label">Avg Confidence</span><span class="stat-value">${avg}</span></div>`;

  tbody.innerHTML = "";
  const matches = result.matches ?? [];
  let needsReviewIndex = 0;
  matches.forEach((m, index) => {
    const row = document.createElement("tr");
    row.classList.add("review-clickable");
    row.dataset.reviewKind = "match";
    row.dataset.reviewIndex = String(index);
    row.tabIndex = 0;
    row.setAttribute("role", "button");
    row.setAttribute("aria-label", `Open review details for ${window.AquaProfileDrawer.matchSwimmerNames(m) || "match"}`);
    const flags = window.AquaProfileDrawer.normalizeFlags(m);
    const severity = window.AquaProfileDrawer.getHighestFlagSeverity(flags, m.review_severity);
    row.dataset.reviewSeverity = severity;
    let swimmers;
    if (m.type === "pair") {
      swimmers =
        `<span class="paired-swimmer-line"><span class="profile-link swimmer-link" data-type="swimmer" data-id="${m.swimmer_1_id}">${esc(m.swimmer_1_name ?? m.swimmer_1_id)}</span></span>` +
        `<span class="paired-swimmer-line"><span class="profile-link swimmer-link" data-type="swimmer" data-id="${m.swimmer_2_id}">${esc(m.swimmer_2_name ?? m.swimmer_2_id)}</span></span>`;
    } else {
      swimmers = `<span class="profile-link swimmer-link" data-type="swimmer" data-id="${m.swimmer_id}">${esc(m.swimmer_name ?? m.swimmer_id ?? "?")}</span>`;
    }
    const conf = typeof m.confidence === "number" ? `${m.confidence.toFixed(0)}%` : "N/A";

    row.innerHTML =
      `<td class="name-cell instructor-cell"><span class="profile-link instructor-link" data-type="instructor" data-id="${m.instructor_id}">${esc(m.instructor_name ?? m.instructor_id ?? "?")}</span></td>` +
      `<td class="name-cell swimmer-cell">${swimmers}</td>` +
      `<td><span class="confidence-badge confidence-${getConfidenceLevel(m.confidence)}">${conf}</span></td>` +
      `<td class="review-text-cell">${window.AquaProfileDrawer.renderReviewText(m)}</td>` +
      `<td class="reason-cell">${esc(m.reason ?? "")}</td>`;

    if (severity !== "none") {
      row.classList.add(`review-row-${severity}`);
    }

    if (m.continuity_dispute) {
      row.classList.add("dispute-flagged");
      const reasonCell = row.querySelector(".reason-cell");
      if (reasonCell) {
        reasonCell.innerHTML = `<span class="dispute-icon" title="Continuity dispute: tiebreaker decision was made">\u26A0</span> ${reasonCell.innerHTML}`;
      }
    }

    if (typeof m.confidence === "number" && m.confidence < 50) {
      row.classList.add("needs-review");
      row.style.setProperty("--row-index", needsReviewIndex++);
    }

    tbody.appendChild(row);
  });

  // Render unassigned swimmers
  const unassignedSection = document.getElementById("unassigned-section");
  const unassignedBody = document.getElementById("unassigned-body");
  const unassigned = result.unassigned ?? [];

  if (unassignedSection && unassignedBody) {
    unassignedBody.innerHTML = "";
    if (unassigned.length > 0) {
      unassigned.forEach((u, index) => {
        const row = document.createElement("tr");
        row.classList.add("review-clickable");
        row.dataset.reviewKind = "unassigned";
        row.dataset.reviewIndex = String(index);
        row.tabIndex = 0;
        row.setAttribute("role", "button");
        row.setAttribute("aria-label", `Open review details for ${u.swimmer_name ?? "unassigned swimmer"}`);
        const flags = window.AquaProfileDrawer.normalizeFlags(u);
        const severity = window.AquaProfileDrawer.getHighestFlagSeverity(flags, u.review_severity);
        row.dataset.reviewSeverity = severity;
        const bestMatch = u.best_available_instructor_name
          ? `${u.best_available_instructor_name} (${typeof u.best_available_score === "number" ? u.best_available_score.toFixed(1) : u.best_available_score}%)`
          : "";
        if (severity !== "none") {
          row.classList.add(`review-row-${severity}`);
        }
        row.innerHTML =
          `<td class="name-cell swimmer-cell"><span class="profile-link swimmer-link" data-type="swimmer" data-id="${u.swimmer_id}">${esc(u.swimmer_name ?? u.swimmer_id ?? "?")}</span></td>` +
          `<td>${u.skill_level ?? "?"}</td>` +
          `<td>${window.AquaProfileDrawer.formatAge(u.age)}</td>` +
          `<td>${u.has_special_needs ? "Yes" : "No"}</td>` +
          `<td>${esc(u.reason ?? "")}</td>` +
          `<td class="review-text-cell">${window.AquaProfileDrawer.renderReviewText(u)}</td>` +
          `<td>${esc(bestMatch)}</td>`;
        unassignedBody.appendChild(row);
      });
      unassignedSection.classList.remove("hidden");
    } else {
      unassignedSection.classList.add("hidden");
    }
  }

  section.classList.remove("hidden");
  applyResultsFilters();
}

function applyResultsFilters() {
  const searchInput = document.getElementById("resultsSearchInput");
  const reviewFilter = document.getElementById("resultsReviewFilter");
  const summary = document.getElementById("resultsFilterSummary");
  const emptyState = document.getElementById("resultsEmptyState");
  const assignmentsTableWrap = document.getElementById("resultsAssignmentsTableWrap");
  const query = String(searchInput?.value || "").trim().toLowerCase();
  const filter = String(reviewFilter?.value || "all");
  const matchRows = Array.from(document.querySelectorAll("#results-body tr"));
  const unassignedRows = Array.from(document.querySelectorAll("#unassigned-body tr"));

  let visibleCount = 0;
  let visibleMatches = 0;
  const rowMatchesSearch = (row) => !query || String(row.textContent || "").toLowerCase().includes(query);

  matchRows.forEach((row) => {
    const severity = row.dataset.reviewSeverity || "none";
    const matchesFilter = filter === "all"
      || (filter === "review" && severity !== "none")
      || (filter === "clear" && severity === "none");
    const isVisible = filter !== "unassigned" && matchesFilter && rowMatchesSearch(row);
    row.hidden = !isVisible;
    if (isVisible) {
      visibleCount += 1;
      visibleMatches += 1;
    }
  });

  let visibleUnassigned = 0;
  unassignedRows.forEach((row) => {
    const matchesFilter = filter === "all"
      || filter === "unassigned"
      || filter === "review";
    const isVisible = filter !== "clear" && matchesFilter && rowMatchesSearch(row);
    row.hidden = !isVisible;
    if (isVisible) {
      visibleCount += 1;
      visibleUnassigned += 1;
    }
  });

  const unassignedSection = document.getElementById("unassigned-section");
  if (unassignedSection) {
    unassignedSection.classList.toggle("hidden", unassignedRows.length === 0 || visibleUnassigned === 0);
  }
  if (assignmentsTableWrap) assignmentsTableWrap.hidden = visibleMatches === 0;

  const totalCount = matchRows.length + unassignedRows.length;
  if (summary) summary.textContent = `${visibleCount} of ${totalCount} result${totalCount === 1 ? "" : "s"}`;
  if (emptyState) emptyState.hidden = visibleCount !== 0;
}

function wireResultsFilters() {
  const searchInput = document.getElementById("resultsSearchInput");
  const reviewFilter = document.getElementById("resultsReviewFilter");
  searchInput?.addEventListener("input", applyResultsFilters);
  reviewFilter?.addEventListener("change", applyResultsFilters);
}

function getConfidenceLevel(conf) {
  if (typeof conf !== "number") return "unknown";
  if (conf >= 85) return "high";
  if (conf >= 70) return "good";
  if (conf >= 50) return "moderate";
  return "low";
}

// Generate button handler. Called once from initializeUserInterface().
function wireGenerateFlow() {
  const output = getElementByIdOrThrow("output");
  const generateButton = getElementByIdOrThrow("generateButton");
  wireResultsFilters();

  generateButton.addEventListener("click", async () => {
    output.classList.remove("hidden");
    output.innerHTML = '<div class="status-generating"><span class="status-spinner" aria-hidden="true"></span><span>Generating matching\u2026</span></div>';

    try {
      const selectedSessionIds = typeof window._getSelectedSessionIds === "function"
        ? window._getSelectedSessionIds()
        : null;
      // Not postJson: error responses carry a JSON body (error, error_kind,
      // import_diagnostics) that the curated error rendering needs.
      const resp = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ selected_session_ids: selectedSessionIds }),
        cache: "no-store",
      });
      const result = await resp.json().catch(() => ({}));
      if (!resp.ok || !result?.ok) {
        output.innerHTML = renderGenerateErrorHtml(result);
        return;
      }

      const s = result.summary ?? {};
      const rf = result.result_files ?? {};
      const assigned = s.assigned_swimmers ?? "?";
      const classes = s.classes ?? "?";
      const diagnosticsHtml = renderImportDiagnosticsHtml(result.import_diagnostics);
      const warningsHtml = renderGenerateWarningsHtml(result.warnings);
      output.innerHTML =
        `<div class="status-success"><span class="status-icon" aria-hidden="true">\u2713</span><span>${esc(String(assigned))} swimmers matched across ${esc(String(classes))} classes</span></div>` +
        diagnosticsHtml +
        warningsHtml;

      if (result.matches || result.summary) {
        renderResults(result);
        showWorkspaceView("results");
        if (!diagnosticsHtml && !warningsHtml) {
          output.classList.add("hidden");
        }
      }

      if (rf.pdf) {
        localStorage.setItem(LAST_PDF_KEY, rf.pdf);
        setReopenPdfButton(rf.pdf);
      }
      if (rf.filled_classes_export) {
        localStorage.setItem(LAST_FILLED_CLASSES_KEY, rf.filled_classes_export);
        setDownloadFilledClassesButton(rf.filled_classes_export);
      }
    } catch (e) {
      output.classList.remove("hidden");
      output.innerHTML = `<div class="status-error"><span class="status-icon" aria-hidden="true">\u2717</span><span>${esc(String(e))}</span></div>`;
    }
  });
}
