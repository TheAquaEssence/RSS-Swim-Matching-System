// Manage Instructors editor, staffing overview, edit form, and CSV import
// review — extracted from app.js (D2). Classic script: shares the global
// scope with app.js; wireInstructorEditor() is called from
// initializeUserInterface() in app.js.

let instructorEditorState = null;   // { instructors, colors, styles, query, incompleteOnly, sortKey, sortDir }
let instructorEditTarget = null;    // single instructor being edited
let instructorImportState = null;   // { csv, new, changed, unchanged, missingFromCsv, warnings, accepted:Set }

// ── Instructor Editor ──────────────────────────────────────────────────────

function setInstructorEditorError(msg) {
  const el = document.getElementById("instructor-editor-error");
  if (!el) return;
  el.textContent = msg || "";
  el.classList.toggle("hidden", !msg);
}

function setInstructorEditFormError(msg) {
  const el = document.getElementById("instructor-edit-form-error");
  if (!el) return;
  el.textContent = msg || "";
  el.classList.toggle("hidden", !msg);
}

function instructorProfileStatusInfo(profileSource) {
  if (profileSource === 0) return { label: "Complete", cls: "instructor-status-complete" };
  if (profileSource === 1) return { label: "Default",  cls: "instructor-status-default" };
  return                         { label: "Partial",   cls: "instructor-status-partial" };
}

function buildCapabilityBadgesHtml(instructor) {
  const caps = [];
  if (instructor.can_teach_babies)  caps.push({ label: "Babies",  cls: "cap-babies"  });
  if (instructor.can_teach_adults)  caps.push({ label: "Adults",  cls: "cap-adults"  });
  if (instructor.can_teach_adapted) caps.push({ label: "Adapted", cls: "cap-adapted" });
  if (instructor.is_team_captain)   caps.push({ label: "Captain", cls: "cap-captain" });
  if (caps.length === 0) return '<span style="color:var(--muted);font-size:12px">None</span>';
  return caps.map((c) => `<span class="cap-badge ${esc(c.cls)}">${esc(c.label)}</span>`).join("");
}

function buildCapabilityToggles(inst) {
  const wrap = document.createElement("div");
  wrap.className = "cap-toggle-wrap";
  const defs = [
    { field: "can_teach_babies",  label: "Babies",  cls: "cap-babies"  },
    { field: "can_teach_adults",  label: "Adults",  cls: "cap-adults"  },
    { field: "can_teach_adapted", label: "Adapted", cls: "cap-adapted" },
    { field: "is_team_captain",   label: "Captain", cls: "cap-captain" },
  ];

  defs.forEach(({ field, label, cls }) => {
    const enabled = Boolean(inst[field]);
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `cap-badge cap-toggle ${cls}`;
    btn.classList.toggle("cap-toggle-off", !enabled);
    btn.textContent = label;
    btn.title = `Turn ${label} ${enabled ? "off" : "on"}`;
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      // Captain implies all capabilities — same rule as the edit form
      const fields = field === "is_team_captain" && !enabled
        ? { is_team_captain: 1, can_teach_babies: 1, can_teach_adults: 1, can_teach_adapted: 1 }
        : { [field]: enabled ? 0 : 1 };
      try {
        const resp = await fetch(`/api/instructors/${encodeURIComponent(inst.instructor_id)}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...fields, operator: getOperatorName() }),
          cache: "no-store",
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok || !data?.ok) throw new Error(data?.error || `HTTP ${resp.status}`);
        const updated = data.instructor;
        if (updated && instructorEditorState) {
          const idx = instructorEditorState.instructors.findIndex(
            (i) => i.instructor_id === updated.instructor_id,
          );
          if (idx >= 0) instructorEditorState.instructors[idx] = updated;
          setInstructorEditorError("");
          renderInstructorEditor();
        }
      } catch (e) {
        setInstructorEditorError(`Could not update ${label} for ${inst.first_name} ${inst.last_name}: ${e.message || e}`);
        btn.disabled = false;
      }
    });
    wrap.appendChild(btn);
  });
  return wrap;
}

async function openInstructorEditor() {
  const modal = document.getElementById("instructor-editor-modal");
  if (!modal) return;

  instructorEditorState = { instructors: [], colors: [], styles: [], query: "", incompleteOnly: false, sortKey: null, sortDir: 1 };
  setInstructorEditorError("");
  restoreLastInstructorImportStatus();
  updateInstructorEditorSolverHint();

  const metaEl = document.getElementById("instructor-editor-meta");
  if (metaEl) metaEl.textContent = "Loading instructors…";

  const searchEl = document.getElementById("instructor-editor-search");
  if (searchEl) searchEl.value = "";

  const toggleBtn = document.getElementById("instructor-editor-incomplete-toggle");
  if (toggleBtn) toggleBtn.classList.remove("button-primary");

  // Staffing overview starts collapsed; it refetches on each open
  const statsPanel = document.getElementById("instructor-staffing-overview");
  if (statsPanel) statsPanel.classList.add("hidden");
  const statsBtn = document.getElementById("instructor-editor-stats-toggle");
  if (statsBtn) statsBtn.classList.remove("button-primary");

  modal.showModal();

  try {
    const [listResp] = await Promise.all([
      fetch("/api/instructors", { cache: "no-store" }).then((r) => r.json()),
      (async () => {
        const [colors, styles] = await Promise.all([
          window.AquaSettingsFiles.loadReferenceTableOptions("personality_colors", "color_name"),
          window.AquaSettingsFiles.loadReferenceTableOptions("instructor_styles", "style_name"),
        ]);
        if (instructorEditorState) {
          instructorEditorState.colors = colors;
          instructorEditorState.styles = styles;
        }
      })(),
    ]);

    if (!listResp?.ok) {
      setInstructorEditorError(listResp?.error || "Failed to load instructors.");
      if (metaEl) metaEl.textContent = "";
      return;
    }
    instructorEditorState.instructors = Array.isArray(listResp.instructors) ? listResp.instructors : [];
    renderInstructorEditor();
  } catch (e) {
    setInstructorEditorError(String(e));
    if (metaEl) metaEl.textContent = "";
  }
}

function closeInstructorEditor() {
  const modal = document.getElementById("instructor-editor-modal");
  if (modal?.open) modal.close();
  setInstructorEditorError("");
}

function renderInstructorEditor() {
  if (!instructorEditorState) return;

  const { instructors, query, incompleteOnly, sortKey, sortDir } = instructorEditorState;
  const q = query.trim().toLowerCase();

  const filtered = instructors.filter((inst) => {
    if (incompleteOnly && !inst.needs_update) return false;
    if (q && !`${inst.first_name} ${inst.last_name}`.toLowerCase().includes(q)) return false;
    return true;
  });

  if (sortKey) {
    // Profile status ranks: Complete (0) < Partial (other) < Default (1)
    const statusRank = (inst) =>
      inst.profile_source === 0 ? 0 : inst.profile_source === 1 ? 2 : 1;
    filtered.sort((a, b) => {
      let cmp;
      if (sortKey === "status") {
        cmp = statusRank(a) - statusRank(b);
      } else {
        cmp = `${a.first_name} ${a.last_name}`.localeCompare(`${b.first_name} ${b.last_name}`);
      }
      if (cmp === 0 && sortKey !== "name") {
        cmp = `${a.first_name} ${a.last_name}`.localeCompare(`${b.first_name} ${b.last_name}`);
      }
      return cmp * sortDir;
    });
  }

  document.querySelectorAll("#instructor-editor-modal .instructor-sort-header").forEach((th) => {
    const arrow = th.querySelector(".instructor-sort-arrow");
    if (arrow) arrow.textContent = th.dataset.sortKey === sortKey ? (sortDir === 1 ? " ▲" : " ▼") : "";
  });

  const metaEl = document.getElementById("instructor-editor-meta");
  if (metaEl) {
    const total = instructors.length;
    const complete = instructors.filter((i) => i.profile_source === 0).length;
    const pct = total ? Math.round((complete / total) * 100) : 0;
    const incomplete = instructors.filter((i) => i.needs_update).length;
    const noCaps = instructors.filter(
      (i) => !i.can_teach_babies && !i.can_teach_adults && !i.can_teach_adapted && !i.is_team_captain,
    ).length;
    const extra = filtered.length !== total ? ` · showing ${filtered.length}` : "";
    metaEl.textContent = `${complete} of ${total} profiles complete (${pct}%) · ${incomplete} incomplete${extra}`;
    if (noCaps) {
      // Own line (still right-aligned via .rankings-editor-meta) so the
      // staffing gap stands out from the completeness counts.
      const noCapsLine = document.createElement("div");
      noCapsLine.textContent = `${noCaps} instructor${noCaps === 1 ? "" : "s"} without any capabilities`;
      metaEl.appendChild(noCapsLine);
    }
  }

  const tbody = document.getElementById("instructor-editor-body");
  if (!tbody) return;
  tbody.innerHTML = "";

  if (filtered.length === 0) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 4;
    td.className = "instructor-style-color-editor-empty";
    td.textContent = q || incompleteOnly ? "No instructors match the current filter." : "No instructors in database.";
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }

  filtered.forEach((inst) => {
    const tr = document.createElement("tr");

    const nameTd = document.createElement("td");
    nameTd.className = "instructor-editor-name";
    nameTd.textContent = `${inst.first_name} ${inst.last_name}`;

    const statusTd = document.createElement("td");
    const { label, cls } = instructorProfileStatusInfo(inst.profile_source);
    const badge = document.createElement("span");
    badge.className = `instructor-status-badge ${cls}`;
    badge.textContent = label;
    statusTd.appendChild(badge);

    const capsTd = document.createElement("td");
    capsTd.appendChild(buildCapabilityToggles(inst));

    const editTd = document.createElement("td");
    editTd.style.textAlign = "right";
    const editBtn = document.createElement("button");
    editBtn.className = "button button-ghost";
    editBtn.style.cssText = "padding:4px 10px;font-size:12px";
    editBtn.textContent = "Edit";
    editBtn.addEventListener("click", () => openInstructorEditForm(inst));
    editTd.appendChild(editBtn);

    tr.append(nameTd, statusTd, capsTd, editTd);
    tbody.appendChild(tr);
  });
}

// ── Staffing overview (B1) ─────────────────────────────────────────────────

async function toggleStaffingOverview() {
  const panel = document.getElementById("instructor-staffing-overview");
  const btn = document.getElementById("instructor-editor-stats-toggle");
  if (!panel) return;
  const opening = panel.classList.contains("hidden");
  panel.classList.toggle("hidden", !opening);
  if (btn) btn.classList.toggle("button-primary", opening);
  if (!opening) return;

  panel.textContent = "Loading staffing overview…";
  try {
    const data = await fetch("/api/instructors/stats", { cache: "no-store" }).then((r) => r.json());
    if (!data?.ok) throw new Error(data?.error || "Failed to load stats");
    renderStaffingOverview(panel, data);
  } catch (e) {
    panel.textContent = `Could not load staffing overview: ${e.message || e}`;
  }
}

// Swatch colors for the four personality colors; anything else falls back
// to the app accent (used for teaching styles, which have no inherent color).
const STAFFING_COLOR_SWATCHES = {
  // Vivid blue, readable on both themes. The legend swatches are neutral
  // gray so this is the only blue in the Personality colors block.
  blue: "#3b82f6",
  orange: "#fb923c",
  green: "#4ade80",
  gold: "#eab308",
};

function staffingSwatchColor(name) {
  return STAFFING_COLOR_SWATCHES[String(name || "").trim().toLowerCase()] || "";
}

function staffingHueAlpha(hex, alpha) {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex || "");
  if (!m) return "";
  const n = parseInt(m[1], 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

function renderStaffingOverview(panel, stats) {
  panel.innerHTML = "";

  const caps = stats.capabilities || {};
  const tiles = document.createElement("div");
  tiles.className = "staffing-overview-tiles";
  const pct = stats.total ? Math.round((stats.complete / stats.total) * 100) : 0;
  [
    { value: stats.total ?? 0, label: "instructors" },
    { value: `${pct}%`, label: "profiles complete" },
    { value: caps.can_teach_babies ?? 0, label: "teach babies" },
    { value: caps.can_teach_adults ?? 0, label: "teach adults" },
    { value: caps.can_teach_adapted ?? 0, label: "teach adapted" },
    { value: caps.is_team_captain ?? 0, label: "team captains" },
  ].forEach(({ value, label }) => {
    const tile = document.createElement("div");
    tile.className = "staffing-overview-tile";
    const num = document.createElement("div");
    num.className = "staffing-overview-tile-value";
    num.textContent = String(value);
    const lab = document.createElement("div");
    lab.className = "staffing-overview-tile-label";
    lab.textContent = label;
    tile.append(num, lab);
    tiles.appendChild(tile);
  });
  panel.appendChild(tiles);

  const cols = document.createElement("div");
  cols.className = "staffing-overview-columns";
  cols.appendChild(buildStaffingDistribution("Personality colors", stats.colors || [], "color"));
  cols.appendChild(buildStaffingDistribution("Teaching styles", stats.styles || [], "style"));
  panel.appendChild(cols);
}

function buildStaffingDistribution(title, entries, kind) {
  const block = document.createElement("div");
  block.className = "staffing-overview-block";

  const heading = document.createElement("div");
  heading.className = "staffing-overview-heading";
  const titleEl = document.createElement("span");
  titleEl.textContent = title;
  const legend = document.createElement("span");
  legend.className = "staffing-overview-legend";
  legend.innerHTML =
    '<span class="staffing-overview-legend-swatch staffing-overview-legend-primary"></span>primary' +
    '<span class="staffing-overview-legend-swatch staffing-overview-legend-secondary"></span>secondary';
  heading.append(titleEl, legend);
  block.appendChild(heading);

  // "(not set)" rows are missing data, not staffing supply: pull them out of
  // the bars (they dwarf the real counts) and report them as a footnote.
  const named = entries.filter((e) => e.name);
  const notSet = entries.find((e) => !e.name);
  named.sort((a, b) => (b.primary || 0) - (a.primary || 0) || (b.secondary || 0) - (a.secondary || 0));

  // Grouped bars on a shared baseline (not stacked): primary and secondary
  // are separate counts, so each gets its own track and the same scale —
  // secondary becomes comparable across rows.
  const max = Math.max(1, ...named.flatMap((e) => [e.primary || 0, e.secondary || 0]));
  named.forEach((e) => {
    const primary = e.primary || 0;
    const secondary = e.secondary || 0;
    const row = document.createElement("div");
    row.className = "staffing-overview-row";
    row.title = `${e.name}: ${primary} primary, ${secondary} secondary`;

    const name = document.createElement("span");
    name.className = "staffing-overview-name";
    const swatchColor = kind === "color" ? staffingSwatchColor(e.name) : "";
    if (swatchColor) {
      const dot = document.createElement("span");
      dot.className = "staffing-overview-dot";
      dot.style.background = swatchColor;
      name.appendChild(dot);
    }
    name.appendChild(document.createTextNode(e.name));

    // Hue carries meaning only for personality colors: primary keeps the
    // true hue, secondary is the same hue faded with a solid outline (so
    // Gold reads as "lighter gold", not olive). Style bars stay neutral.
    const bars = document.createElement("span");
    bars.className = "staffing-overview-bars";
    const makeBar = (value, isSecondary) => {
      const track = document.createElement("span");
      track.className = "staffing-overview-bar";
      const fill = document.createElement("span");
      fill.className = "staffing-overview-bar-fill" +
        (isSecondary ? " staffing-overview-bar-fill-secondary" : "");
      fill.style.width = `${Math.round((value / max) * 100)}%`;
      if (swatchColor) {
        if (isSecondary) {
          fill.style.background = staffingHueAlpha(swatchColor, 0.3);
          fill.style.boxShadow = `inset 0 0 0 1px ${swatchColor}`;
        } else {
          fill.style.background = swatchColor;
        }
      }
      track.appendChild(fill);
      return track;
    };
    bars.append(makeBar(primary, false), makeBar(secondary, true));

    const count = document.createElement("span");
    count.className = "staffing-overview-count";
    const countPrimary = document.createElement("span");
    countPrimary.className = "staffing-overview-count-num";
    countPrimary.textContent = String(primary);
    const countSep = document.createElement("span");
    countSep.className = "staffing-overview-count-sep";
    countSep.textContent = "/";
    const countSecondary = document.createElement("span");
    countSecondary.className = "staffing-overview-count-num staffing-overview-count-secondary";
    countSecondary.textContent = String(secondary);
    count.append(countPrimary, countSep, countSecondary);

    row.append(name, bars, count);
    block.appendChild(row);
  });

  if (notSet && (notSet.primary || 0) > 0) {
    const note = document.createElement("div");
    note.className = "staffing-overview-note";
    note.textContent = `${notSet.primary} instructor${notSet.primary === 1 ? "" : "s"} with no primary ${kind} set`;
    block.appendChild(note);
  }

  if (!named.length && !notSet) {
    const empty = document.createElement("div");
    empty.className = "staffing-overview-empty";
    empty.textContent = "No instructors in database.";
    block.appendChild(empty);
  }
  return block;
}

function populateInstructorEditDropdowns() {
  if (!instructorEditorState) return;
  const { colors, styles } = instructorEditorState;

  function fillSelect(selectId, options) {
    const sel = document.getElementById(selectId);
    if (!sel) return;
    sel.innerHTML =
      '<option value="">(none)</option>' +
      options.map((o) => `<option value="${esc(String(o.id))}">${esc(o.name)}</option>`).join("");
  }

  fillSelect("instructor-edit-primary-color",   colors);
  fillSelect("instructor-edit-secondary-color",  colors);
  fillSelect("instructor-edit-primary-style",    styles);
  fillSelect("instructor-edit-secondary-style",  styles);
}

function openInstructorEditForm(instructor) {
  instructorEditTarget = instructor;
  const modal = document.getElementById("instructor-edit-form-modal");
  if (!modal) return;

  setInstructorEditFormError("");

  const title = document.getElementById("instructor-edit-form-title");
  if (title) title.textContent = `Edit: ${instructor.first_name} ${instructor.last_name}`;

  const subtitle = document.getElementById("instructor-edit-form-subtitle");
  if (subtitle) subtitle.textContent = `ID: ${instructor.instructor_id}`;

  populateInstructorEditDropdowns();

  const setVal     = (id, val) => { const el = document.getElementById(id); if (el) el.value = (val ?? ""); };
  const setChecked = (id, val) => { const el = document.getElementById(id); if (el) el.checked = Boolean(val); };

  setVal("instructor-edit-first-name",      instructor.first_name);
  setVal("instructor-edit-last-name",       instructor.last_name);
  setVal("instructor-edit-primary-color",   instructor.primary_color_id ?? "");
  setVal("instructor-edit-secondary-color", instructor.secondary_color_id ?? "");
  setVal("instructor-edit-primary-style",   instructor.primary_style_id ?? "");
  setVal("instructor-edit-secondary-style", instructor.secondary_style_id ?? "");
  setChecked("instructor-edit-can-teach-babies",  instructor.can_teach_babies);
  setChecked("instructor-edit-can-teach-adults",  instructor.can_teach_adults);
  setChecked("instructor-edit-can-teach-adapted", instructor.can_teach_adapted);
  setChecked("instructor-edit-team-captain",      instructor.is_team_captain);

  const srcHint = document.getElementById("instructor-edit-profile-source-hint");
  if (srcHint) {
    const labels = { 0: "Profile complete", 1: "Using all defaults. Please fill in.", 2: "Partially configured" };
    srcHint.textContent = labels[instructor.profile_source] ?? "";
  }

  const lastUpdated = document.getElementById("instructor-edit-last-updated");
  if (lastUpdated) {
    if (instructor.updated_at) {
      const when = new Date(instructor.updated_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
      lastUpdated.textContent = instructor.updated_by
        ? `Last updated by ${instructor.updated_by} · ${when}`
        : `Last updated ${when}`;
    } else {
      lastUpdated.textContent = "";
    }
  }

  modal.showModal();
}

function closeInstructorEditForm() {
  const modal = document.getElementById("instructor-edit-form-modal");
  if (modal?.open) modal.close();
  setInstructorEditFormError("");
  instructorEditTarget = null;
}

async function saveInstructorEditForm() {
  if (!instructorEditTarget) return;

  const getVal     = (id) => { const el = document.getElementById(id); return el ? el.value : ""; };
  const getChecked = (id) => { const el = document.getElementById(id); return el?.checked ? 1 : 0; };
  const getIntOrNull = (id) => { const v = getVal(id); return v === "" ? null : parseInt(v, 10); };

  const fields = {
    first_name:          getVal("instructor-edit-first-name").trim(),
    last_name:           getVal("instructor-edit-last-name").trim(),
    primary_color_id:    getIntOrNull("instructor-edit-primary-color"),
    secondary_color_id:  getIntOrNull("instructor-edit-secondary-color"),
    primary_style_id:    getIntOrNull("instructor-edit-primary-style"),
    secondary_style_id:  getIntOrNull("instructor-edit-secondary-style"),
    can_teach_babies:    getChecked("instructor-edit-can-teach-babies"),
    can_teach_adults:    getChecked("instructor-edit-can-teach-adults"),
    can_teach_adapted:   getChecked("instructor-edit-can-teach-adapted"),
    is_team_captain:     getChecked("instructor-edit-team-captain"),
  };

  const resp = await fetch(`/api/instructors/${encodeURIComponent(instructorEditTarget.instructor_id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...fields, operator: getOperatorName() }),
    cache: "no-store",
  });

  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data?.error || `Save failed (HTTP ${resp.status})`);
  }

  const result = await resp.json();
  const updated = result?.instructor;

  if (updated && instructorEditorState) {
    const idx = instructorEditorState.instructors.findIndex(
      (i) => i.instructor_id === updated.instructor_id,
    );
    if (idx >= 0) instructorEditorState.instructors[idx] = updated;
    renderInstructorEditor();
  }

  closeInstructorEditForm();
}

// ── Instructor Import Review ───────────────────────────────────────────────

const INSTRUCTOR_IMPORT_FIELD_LABELS = {
  first_name:         "First name",
  last_name:          "Last name",
  primary_color_id:   "Primary color",
  secondary_color_id: "Secondary color",
  primary_style_id:   "Primary style",
  secondary_style_id: "Secondary style",
  is_team_captain:    "Team captain",
  can_teach_babies:   "Can teach babies",
  can_teach_adults:   "Can teach adults",
  can_teach_adapted:  "Can teach adapted",
};

function updateInstructorEditorSolverHint() {
  fetch("/api/settings", { cache: "no-store" })
    .then((r) => r.json())
    .then((s) => {
      const hint = document.getElementById("instructor-editor-solver-hint");
      if (!hint) return;
      const usingDb = Boolean(s?.use_db_instructors);
      hint.classList.toggle("hidden", usingDb);
      hint.textContent = usingDb
        ? ""
        : "Heads-up: matching currently uses the selected instructors.csv file. Turn on “Use database instructors” on the main screen to match with these profiles.";
    })
    .catch(() => {});
}

function setInstructorImportStatus(msg, kind, showUndo) {
  const el = document.getElementById("instructor-import-status");
  const textEl = document.getElementById("instructor-import-status-text");
  if (!el || !textEl) return;
  textEl.textContent = msg || "";
  el.classList.toggle("hidden", !msg);
  el.classList.toggle("instructor-import-status-error", kind === "error");
  el.classList.toggle("instructor-import-status-busy", kind === "busy");
  const undoBtn = document.getElementById("instructor-import-undo-btn");
  if (undoBtn) {
    undoBtn.classList.toggle("hidden", !showUndo);
    undoBtn.textContent = "Undo";
    undoBtn.dataset.confirming = "";
  }
}

async function restoreLastInstructorImportStatus() {
  try {
    const data = await fetch("/api/instructors/import/last", { cache: "no-store" }).then((r) => r.json());
    const last = data?.last_import;
    if (last) {
      const when = new Date(last.imported_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
      const who = last.imported_by ? ` · by ${last.imported_by}` : "";
      setInstructorImportStatus(`Last import: ${last.summary}${who} · ${when}`, "", true);
    } else {
      setInstructorImportStatus("");
    }
  } catch { setInstructorImportStatus(""); }
}

async function undoLastInstructorImport() {
  const resp = await fetch("/api/instructors/import/undo", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
    cache: "no-store",
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok || !data?.ok) {
    setInstructorImportStatus(`Undo failed: ${data?.error || `HTTP ${resp.status}`}`, "error");
    return;
  }

  try {
    const listResp = await fetch("/api/instructors", { cache: "no-store" }).then((r) => r.json());
    if (listResp?.ok && instructorEditorState) {
      instructorEditorState.instructors = Array.isArray(listResp.instructors) ? listResp.instructors : [];
      renderInstructorEditor();
    }
  } catch { /* list refresh is best-effort */ }

  setInstructorImportStatus(
    `Undo complete — restored ${data.restored}, removed ${data.removed} (was: ${data.summary}).`,
  );
}

function setInstructorImportReviewError(msg) {
  const el = document.getElementById("instructor-import-review-error");
  if (!el) return;
  el.textContent = msg || "";
  el.classList.toggle("hidden", !msg);
}

function instructorImportFieldValueLabel(field, value) {
  if (value === null || value === undefined || value === "") return "(none)";
  if (field.startsWith("can_teach") || field === "is_team_captain") return value ? "Yes" : "No";
  if (field.endsWith("_color_id") || field.endsWith("_style_id")) {
    const options = field.includes("color")
      ? instructorEditorState?.colors
      : instructorEditorState?.styles;
    const match = (options || []).find((o) => String(o.id) === String(value));
    return match ? match.name : String(value);
  }
  return String(value);
}

async function openInstructorImportReview(file) {
  setInstructorEditorError("");
  setInstructorImportStatus(`Analyzing ${file.name}…`, "busy");
  let data;
  try {
    const form = new FormData();
    form.append("file", file);
    const resp = await fetch("/api/instructors/import/preview", { method: "POST", body: form });
    data = await resp.json();
    if (!resp.ok || !data?.ok) throw new Error(data?.error || `Preview failed (HTTP ${resp.status})`);
  } catch (e) {
    setInstructorImportStatus(`Import preview failed: ${e.message || e}`, "error");
    return;
  }

  const newRows  = Array.isArray(data.new) ? data.new : [];
  const changed  = Array.isArray(data.changed) ? data.changed : [];

  if (newRows.length === 0 && changed.length === 0) {
    setInstructorImportStatus(`No changes — ${file.name} matches the database (${data.unchanged ?? 0} instructors checked).`);
    return;
  }

  setInstructorImportStatus("");

  instructorImportState = {
    csv: data.csv || "",
    new: newRows,
    changed,
    unchanged: data.unchanged ?? 0,
    missingFromCsv: Array.isArray(data.missing_from_csv) ? data.missing_from_csv : [],
    warnings: Array.isArray(data.warnings) ? data.warnings : [],
    // Everything starts accepted: new rows wholesale, changed rows per-field
    acceptedNew: new Set(newRows.map((r) => String(r.instructor_id))),
    acceptedFields: new Map(
      changed.map((e) => [String(e.instructor_id), new Set((e.changes || []).map((c) => c.field))]),
    ),
    reviewQuery: "",
    sectionsOpen: { changed: true, new: true, missing: false },
  };

  const searchEl = document.getElementById("instructor-import-review-search");
  if (searchEl) searchEl.value = "";

  setInstructorImportReviewError("");
  renderInstructorImportReview();
  document.getElementById("instructor-import-review-modal")?.showModal();
}

function closeInstructorImportReview() {
  const modal = document.getElementById("instructor-import-review-modal");
  if (modal?.open) modal.close();
  setInstructorImportReviewError("");
  instructorImportState = null;
}

function countInstructorImportSelected(state) {
  let count = state.acceptedNew.size;
  state.acceptedFields.forEach((fields) => { if (fields.size > 0) count += 1; });
  return count;
}

function updateInstructorImportMeta() {
  const state = instructorImportState;
  const metaEl = document.getElementById("instructor-import-review-meta");
  if (!state || !metaEl) return;
  const parts = [`${state.new.length} new`, `${state.changed.length} changed`, `${state.unchanged} unchanged`];
  if (state.missingFromCsv.length) parts.push(`${state.missingFromCsv.length} in database but not in CSV (kept as-is)`);
  metaEl.textContent = `${parts.join(" · ")} · ${countInstructorImportSelected(state)} selected`;
}

function renderInstructorImportReview() {
  const state = instructorImportState;
  if (!state) return;

  updateInstructorImportMeta();

  const listEl = document.getElementById("instructor-import-review-list");
  if (!listEl) return;
  listEl.innerHTML = "";

  const q = (state.reviewQuery || "").trim().toLowerCase();
  const matchesQuery = (name, id) =>
    !q || String(name).toLowerCase().includes(q) || String(id).includes(q);

  function makeSection(key, title, shownCount, totalCount) {
    const details = document.createElement("details");
    details.className = "instructor-import-section";
    details.open = state.sectionsOpen[key] !== false;
    details.addEventListener("toggle", () => { state.sectionsOpen[key] = details.open; });
    const summary = document.createElement("summary");
    summary.className = "instructor-import-section-summary";
    summary.textContent = shownCount === totalCount
      ? `${title} (${totalCount})`
      : `${title} (${shownCount} of ${totalCount})`;
    details.appendChild(summary);
    return details;
  }

  function makeRowShell(id, name, badgeLabel, badgeCls) {
    const row = document.createElement("div");
    row.className = "instructor-import-row";

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";

    const body = document.createElement("div");
    body.className = "instructor-import-row-body";

    const header = document.createElement("label");
    header.className = "instructor-import-row-header";
    const nameEl = document.createElement("span");
    nameEl.className = "instructor-editor-name";
    nameEl.textContent = name;
    const badge = document.createElement("span");
    badge.className = `instructor-status-badge ${badgeCls}`;
    badge.textContent = badgeLabel;
    const idEl = document.createElement("span");
    idEl.className = "instructor-import-row-id";
    idEl.textContent = `ID: ${id}`;
    header.append(checkbox, nameEl, badge, idEl);

    body.appendChild(header);
    row.appendChild(body);
    return { row, body, checkbox };
  }

  const changedVisible = state.changed.filter((e) =>
    matchesQuery(e.current_name || e.name || "", e.instructor_id));
  const newVisible = state.new.filter((r) =>
    matchesQuery(`${r.first_name} ${r.last_name}`, r.instructor_id));
  const missingVisible = state.missingFromCsv.filter((m) =>
    matchesQuery(m.name || "", m.instructor_id));

  const changedSection = makeSection("changed", "Changed", changedVisible.length, state.changed.length);
  const newSection = makeSection("new", "New", newVisible.length, state.new.length);
  const missingSection = makeSection(
    "missing", "In database but not in file — kept unchanged",
    missingVisible.length, state.missingFromCsv.length,
  );

  changedVisible.forEach((entry) => {
    const id = String(entry.instructor_id);
    const changes = entry.changes || [];
    const allFields = changes.map((c) => c.field);
    const selected = state.acceptedFields.get(id) || new Set();

    const displayName = entry.current_name || entry.name || `Instructor ${id}`;
    const { row, body, checkbox } = makeRowShell(id, displayName, "Changed", "instructor-status-partial");

    const fieldCheckboxes = [];

    function syncRowVisuals() {
      checkbox.checked = selected.size === allFields.length && allFields.length > 0;
      checkbox.indeterminate = selected.size > 0 && selected.size < allFields.length;
      row.classList.toggle("instructor-import-row-skipped", selected.size === 0);
      updateInstructorImportMeta();
    }

    checkbox.addEventListener("change", () => {
      selected.clear();
      if (checkbox.checked) allFields.forEach((f) => selected.add(f));
      fieldCheckboxes.forEach(({ field, box }) => { box.checked = selected.has(field); });
      syncRowVisuals();
    });

    const details = document.createElement("ul");
    details.className = "instructor-import-changes";
    changes.forEach((change) => {
      const li = document.createElement("li");
      const fieldBox = document.createElement("input");
      fieldBox.type = "checkbox";
      fieldBox.className = "instructor-import-field-checkbox";
      fieldBox.checked = selected.has(change.field);
      fieldBox.addEventListener("change", () => {
        if (fieldBox.checked) selected.add(change.field);
        else selected.delete(change.field);
        li.classList.toggle("instructor-import-change-skipped", !fieldBox.checked);
        syncRowVisuals();
      });
      fieldCheckboxes.push({ field: change.field, box: fieldBox });

      const label = INSTRUCTOR_IMPORT_FIELD_LABELS[change.field] || change.field;
      const fieldEl = document.createElement("span");
      fieldEl.className = "instructor-import-change-field";
      fieldEl.textContent = `${label}: `;
      const oldEl = document.createElement("span");
      oldEl.className = "instructor-import-change-old";
      oldEl.textContent = instructorImportFieldValueLabel(change.field, change.old);
      const arrowEl = document.createElement("span");
      arrowEl.className = "instructor-import-change-arrow";
      arrowEl.textContent = " → ";
      const newEl = document.createElement("span");
      newEl.className = "instructor-import-change-new";
      newEl.textContent = instructorImportFieldValueLabel(change.field, change.new);

      const liLabel = document.createElement("label");
      liLabel.className = "instructor-import-change-label";
      liLabel.append(fieldBox, fieldEl, oldEl, arrowEl, newEl);
      li.classList.toggle("instructor-import-change-skipped", !fieldBox.checked);
      li.appendChild(liLabel);
      details.appendChild(li);
    });

    body.appendChild(details);
    state.acceptedFields.set(id, selected);
    checkbox.checked = selected.size === allFields.length && allFields.length > 0;
    checkbox.indeterminate = selected.size > 0 && selected.size < allFields.length;
    row.classList.toggle("instructor-import-row-skipped", selected.size === 0);
    changedSection.appendChild(row);
  });

  newVisible.forEach((newRow) => {
    const id = String(newRow.instructor_id);
    const name = [newRow.first_name, newRow.last_name].filter(Boolean).join(" ") || `Instructor ${id}`;
    const { row, body, checkbox } = makeRowShell(id, name, "New", "instructor-status-complete");

    checkbox.checked = state.acceptedNew.has(id);
    row.classList.toggle("instructor-import-row-skipped", !checkbox.checked);
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) state.acceptedNew.add(id);
      else state.acceptedNew.delete(id);
      row.classList.toggle("instructor-import-row-skipped", !checkbox.checked);
      updateInstructorImportMeta();
    });

    const caps = document.createElement("div");
    caps.innerHTML = buildCapabilityBadgesHtml(newRow);
    body.appendChild(caps);

    // C4: show the full incoming profile, not just capabilities, so the
    // user confirms colors/styles before accepting a new instructor.
    const profile = document.createElement("ul");
    profile.className = "instructor-import-changes";
    ["primary_color_id", "secondary_color_id", "primary_style_id", "secondary_style_id"].forEach((field) => {
      const li = document.createElement("li");
      const fieldEl = document.createElement("span");
      fieldEl.className = "instructor-import-change-field";
      fieldEl.textContent = `${INSTRUCTOR_IMPORT_FIELD_LABELS[field]}: `;
      const valueEl = document.createElement("span");
      valueEl.className = "instructor-import-change-new";
      valueEl.textContent = instructorImportFieldValueLabel(field, newRow[field]);
      li.append(fieldEl, valueEl);
      profile.appendChild(li);
    });
    body.appendChild(profile);
    newSection.appendChild(row);
  });

  missingVisible.forEach((m) => {
    const row = document.createElement("div");
    row.className = "instructor-import-row instructor-import-row-missing";
    const nameEl = document.createElement("span");
    nameEl.className = "instructor-editor-name";
    nameEl.textContent = m.name || `Instructor ${m.instructor_id}`;
    const idEl = document.createElement("span");
    idEl.className = "instructor-import-row-id";
    idEl.textContent = `ID: ${m.instructor_id}`;
    row.append(nameEl, idEl);
    missingSection.appendChild(row);
  });

  if (state.changed.length) listEl.appendChild(changedSection);
  if (state.new.length) listEl.appendChild(newSection);
  if (state.missingFromCsv.length) listEl.appendChild(missingSection);

  if (q && changedVisible.length === 0 && newVisible.length === 0 && missingVisible.length === 0) {
    const empty = document.createElement("div");
    empty.className = "instructor-import-review-empty";
    empty.textContent = "No instructors match the filter.";
    listEl.appendChild(empty);
  }

  if (state.warnings.length) {
    const warn = document.createElement("div");
    warn.className = "instructor-import-warnings";
    const title = document.createElement("div");
    title.textContent = `${state.warnings.length} warning(s) from the CSV:`;
    warn.appendChild(title);
    const ul = document.createElement("ul");
    state.warnings.slice(0, 20).forEach((w) => {
      const li = document.createElement("li");
      li.textContent = w;
      ul.appendChild(li);
    });
    if (state.warnings.length > 20) {
      const li = document.createElement("li");
      li.textContent = `…and ${state.warnings.length - 20} more`;
      ul.appendChild(li);
    }
    warn.appendChild(ul);
    listEl.appendChild(warn);
  }
}

function setAllInstructorImportRows(accepted) {
  const state = instructorImportState;
  if (!state) return;
  state.acceptedNew = accepted
    ? new Set(state.new.map((r) => String(r.instructor_id)))
    : new Set();
  state.acceptedFields = new Map(
    state.changed.map((e) => [
      String(e.instructor_id),
      accepted ? new Set((e.changes || []).map((c) => c.field)) : new Set(),
    ]),
  );
  renderInstructorImportReview();
}

async function applyInstructorImportReview() {
  const state = instructorImportState;
  if (!state) return;

  const accepted = [];
  state.new.forEach((r) => {
    const id = String(r.instructor_id);
    if (state.acceptedNew.has(id)) accepted.push({ instructor_id: id });
  });
  state.changed.forEach((e) => {
    const id = String(e.instructor_id);
    const fields = state.acceptedFields.get(id);
    if (fields?.size) accepted.push({ instructor_id: id, fields: [...fields] });
  });

  if (accepted.length === 0) {
    setInstructorImportReviewError("Nothing selected — tick at least one change to apply, or cancel.");
    return;
  }

  const resp = await fetch("/api/instructors/import/apply", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ csv: state.csv, accepted_ids: accepted, operator: getOperatorName() }),
    cache: "no-store",
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok || !data?.ok) {
    throw new Error(data?.error || `Import failed (HTTP ${resp.status})`);
  }

  closeInstructorImportReview();

  // Refresh the instructor list behind the review modal
  try {
    const listResp = await fetch("/api/instructors", { cache: "no-store" }).then((r) => r.json());
    if (listResp?.ok && instructorEditorState) {
      instructorEditorState.instructors = Array.isArray(listResp.instructors) ? listResp.instructors : [];
      renderInstructorEditor();
    }
  } catch { /* list refresh is best-effort; import already succeeded */ }

  const when = new Date().toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
  setInstructorImportStatus(
    `Last import: ${data.created ?? 0} added, ${data.updated ?? 0} updated · ${when}`,
    "",
    Boolean(data.history_id),
  );
}

// Event wiring for the Manage Instructors modal, edit form, and import
// review. Called once from initializeUserInterface().
function wireInstructorEditor() {
  const manageInstructorsButton = document.getElementById("manageInstructorsButton");
  if (manageInstructorsButton) {
    manageInstructorsButton.addEventListener("click", openInstructorEditor);
  }

  const instructorsDbEditorHintLink = document.getElementById("instructorsDbEditorHintLink");
  if (instructorsDbEditorHintLink) {
    instructorsDbEditorHintLink.addEventListener("click", openInstructorEditor);
  }

  const instructorEditorDialog = document.getElementById("instructor-editor-modal");
  const instructorEditFormDialog = document.getElementById("instructor-edit-form-modal");
  const instructorEditorClose = document.getElementById("instructor-editor-close");
  const instructorEditorCancel = document.getElementById("instructor-editor-cancel");
  const instructorEditorSearch = document.getElementById("instructor-editor-search");
  const instructorEditorIncompleteToggle = document.getElementById("instructor-editor-incomplete-toggle");
  const instructorEditorExportBtn = document.getElementById("instructor-editor-export-btn");
  const instructorEditFormClose = document.getElementById("instructor-edit-form-close");
  const instructorEditFormCancel = document.getElementById("instructor-edit-form-cancel");
  const instructorEditFormSave = document.getElementById("instructor-edit-form-save");

  if (instructorEditorDialog) {
    instructorEditorDialog.addEventListener("cancel", (e) => { e.preventDefault(); closeInstructorEditor(); });
  }
  if (instructorEditFormDialog) {
    instructorEditFormDialog.addEventListener("cancel", (e) => { e.preventDefault(); closeInstructorEditForm(); });
  }

  if (instructorEditorClose)  instructorEditorClose.addEventListener("click", closeInstructorEditor);
  if (instructorEditorCancel) instructorEditorCancel.addEventListener("click", closeInstructorEditor);
  if (instructorEditorSearch) {
    instructorEditorSearch.addEventListener("input", () => {
      if (!instructorEditorState) return;
      instructorEditorState.query = instructorEditorSearch.value || "";
      renderInstructorEditor();
    });
  }
  if (instructorEditorIncompleteToggle) {
    instructorEditorIncompleteToggle.addEventListener("click", () => {
      if (!instructorEditorState) return;
      instructorEditorState.incompleteOnly = !instructorEditorState.incompleteOnly;
      instructorEditorIncompleteToggle.classList.toggle("button-primary", instructorEditorState.incompleteOnly);
      renderInstructorEditor();
    });
  }

  document.querySelectorAll("#instructor-editor-modal .instructor-sort-header").forEach((th) => {
    const toggleSort = () => {
      if (!instructorEditorState) return;
      const key = th.dataset.sortKey;
      if (instructorEditorState.sortKey === key) {
        instructorEditorState.sortDir = -instructorEditorState.sortDir;
      } else {
        instructorEditorState.sortKey = key;
        instructorEditorState.sortDir = 1;
      }
      renderInstructorEditor();
    };
    th.addEventListener("click", toggleSort);
    th.addEventListener("keydown", (e) => {
      if (e.key !== "Enter" && e.key !== " ") return;
      e.preventDefault();
      toggleSort();
    });
  });
  const instructorEditorStatsToggle = document.getElementById("instructor-editor-stats-toggle");
  if (instructorEditorStatsToggle) {
    instructorEditorStatsToggle.addEventListener("click", toggleStaffingOverview);
  }
  if (instructorEditorExportBtn) {
    instructorEditorExportBtn.addEventListener("click", () => {
      // Export what's on screen: respect the active search / incomplete filters
      const params = new URLSearchParams();
      if (instructorEditorState?.incompleteOnly) params.set("needs_update", "true");
      const q = (instructorEditorState?.query || "").trim();
      if (q) params.set("q", q);
      const suffix = params.toString() ? `?${params.toString()}` : "";
      const date = new Date().toISOString().slice(0, 10);
      downloadFile(`/api/instructors/export${suffix}`, `instructors_${date}.csv`);
    });
  }

  const instructorImportBtn = document.getElementById("instructor-editor-import-btn");
  const instructorImportFileInput = document.getElementById("instructor-import-file-input");
  if (instructorImportBtn && instructorImportFileInput) {
    instructorImportBtn.addEventListener("click", () => instructorImportFileInput.click());
    instructorImportFileInput.addEventListener("change", async () => {
      const file = instructorImportFileInput.files[0];
      if (!file) return;
      instructorImportFileInput.value = "";  // allow re-selecting the same file
      instructorImportBtn.disabled = true;
      try {
        await openInstructorImportReview(file);
      } finally {
        instructorImportBtn.disabled = false;
      }
    });
  }

  const instructorImportUndoBtn = document.getElementById("instructor-import-undo-btn");
  if (instructorImportUndoBtn) {
    instructorImportUndoBtn.addEventListener("click", async () => {
      // Two-click confirm: undo consumes the history entry and can't be re-done
      if (!instructorImportUndoBtn.dataset.confirming) {
        instructorImportUndoBtn.dataset.confirming = "1";
        instructorImportUndoBtn.textContent = "Confirm undo?";
        return;
      }
      instructorImportUndoBtn.disabled = true;
      try {
        await undoLastInstructorImport();
      } finally {
        instructorImportUndoBtn.disabled = false;
        instructorImportUndoBtn.dataset.confirming = "";
        instructorImportUndoBtn.textContent = "Undo";
        instructorImportUndoBtn.classList.add("hidden");
      }
    });
  }

  // Drag & drop a CSV/Excel file anywhere on the Manage Instructors modal
  if (instructorEditorDialog) {
    let dragDepth = 0;
    instructorEditorDialog.addEventListener("dragenter", (e) => {
      if (![...e.dataTransfer?.types || []].includes("Files")) return;
      e.preventDefault();
      dragDepth += 1;
      instructorEditorDialog.classList.add("instructor-editor-dropping");
    });
    instructorEditorDialog.addEventListener("dragover", (e) => {
      if (![...e.dataTransfer?.types || []].includes("Files")) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = "copy";
    });
    instructorEditorDialog.addEventListener("dragleave", () => {
      dragDepth = Math.max(0, dragDepth - 1);
      if (dragDepth === 0) instructorEditorDialog.classList.remove("instructor-editor-dropping");
    });
    instructorEditorDialog.addEventListener("drop", async (e) => {
      e.preventDefault();
      dragDepth = 0;
      instructorEditorDialog.classList.remove("instructor-editor-dropping");
      const file = e.dataTransfer?.files?.[0];
      if (!file) return;
      if (!/\.(csv|xlsx|xlsm)$/i.test(file.name)) {
        setInstructorImportStatus(`"${file.name}" is not a CSV or Excel file.`, "error");
        return;
      }
      await openInstructorImportReview(file);
    });
  }

  const instructorImportReviewDialog = document.getElementById("instructor-import-review-modal");
  if (instructorImportReviewDialog) {
    instructorImportReviewDialog.addEventListener("cancel", (e) => { e.preventDefault(); closeInstructorImportReview(); });
  }
  document.getElementById("instructor-import-review-close")?.addEventListener("click", closeInstructorImportReview);
  document.getElementById("instructor-import-review-cancel")?.addEventListener("click", closeInstructorImportReview);
  const instructorImportReviewSearch = document.getElementById("instructor-import-review-search");
  if (instructorImportReviewSearch) {
    instructorImportReviewSearch.addEventListener("input", () => {
      if (!instructorImportState) return;
      instructorImportState.reviewQuery = instructorImportReviewSearch.value || "";
      renderInstructorImportReview();
    });
  }
  document.getElementById("instructor-import-accept-all")?.addEventListener("click", () => setAllInstructorImportRows(true));
  document.getElementById("instructor-import-skip-all")?.addEventListener("click", () => setAllInstructorImportRows(false));
  const instructorImportApplyBtn = document.getElementById("instructor-import-review-apply");
  if (instructorImportApplyBtn) {
    instructorImportApplyBtn.addEventListener("click", async () => {
      instructorImportApplyBtn.disabled = true;
      try {
        await applyInstructorImportReview();
      } catch (e) {
        setInstructorImportReviewError(String(e.message || e));
      } finally {
        instructorImportApplyBtn.disabled = false;
      }
    });
  }

  if (instructorEditFormClose)  instructorEditFormClose.addEventListener("click", closeInstructorEditForm);
  if (instructorEditFormCancel) instructorEditFormCancel.addEventListener("click", closeInstructorEditForm);

  // Team captain auto-selects all capabilities
  const captainCheckbox = document.getElementById("instructor-edit-team-captain");
  if (captainCheckbox) {
    captainCheckbox.addEventListener("change", () => {
      if (!captainCheckbox.checked) return;
      ["instructor-edit-can-teach-babies",
       "instructor-edit-can-teach-adults",
       "instructor-edit-can-teach-adapted"].forEach((id) => {
        const el = document.getElementById(id);
        if (el) el.checked = true;
      });
    });
  }
  if (instructorEditFormSave) {
    instructorEditFormSave.addEventListener("click", async () => {
      instructorEditFormSave.disabled = true;
      try {
        await saveInstructorEditForm();
      } catch (e) {
        setInstructorEditFormError(String(e));
      } finally {
        instructorEditFormSave.disabled = false;
      }
    });
  }
}
