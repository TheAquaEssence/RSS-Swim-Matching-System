// Historical-pairings session selector and Jackrabbit pairings upload —
// extracted from app.js (D2). Classic script: shares the global scope;
// both init functions are called from initializeUserInterface() in app.js.

// Historical pairings — session selector (DB-first; collapsible by year)
function initSessionSelector() {
    const toggleBtn  = document.getElementById("historicalSessionsToggle");
    const panel      = document.getElementById("historicalSessionsPanel");
    const list       = document.getElementById("historicalSessionsList");
    const metaEl     = document.getElementById("historicalDbMeta");
    const selectAll  = document.getElementById("historicalSelectAll");
    const selectNone = document.getElementById("historicalSelectNone");
    const searchEl   = document.getElementById("historicalSessionSearch");

    let _sessions = []; // [{id, label, pairing_count, imported_at}]
    let _deselected = new Set(); // session ids unchecked by the user (persisted)
    let _persistTimer = null;

    // Persist the curated selection as *deselected* ids so sessions imported
    // later default to selected (history grows by default). Debounced.
    function persistSelection() {
      if (_persistTimer) clearTimeout(_persistTimer);
      _persistTimer = setTimeout(() => {
        _persistTimer = null;
        if (!list) return;
        _deselected = new Set(
          [...list.querySelectorAll(".session-selector-checkbox")]
            .filter((cb) => !cb.checked)
            .map((cb) => parseInt(cb.value, 10)),
        );
        fetch("/api/settings/deselected_session_ids", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ids: [..._deselected] }),
          cache: "no-store",
        }).catch(() => { /* persistence is best-effort */ });
      }, 400);
    }

    function sessionYear(s) {
      const m = s.label.match(/\b(20\d{2})\b/);
      if (m) return m[1];
      return s.imported_at ? s.imported_at.slice(0, 4) : "Unknown";
    }

    async function loadSessions() {
      try {
        const [resp, settingsResp] = await Promise.all([
          fetch("/api/sessions", { cache: "no-store" }),
          fetch("/api/settings", { cache: "no-store" }).catch(() => null),
        ]);
        const data = await resp.json();
        if (!data.ok || !data.sessions) {
          if (metaEl) metaEl.textContent = "Database not available. Historical pairings disabled.";
          return;
        }
        _sessions = data.sessions;
        try {
          const saved = (await settingsResp?.json())?.deselected_session_ids;
          if (Array.isArray(saved)) {
            // Drop ids of sessions that no longer exist
            const known = new Set(_sessions.map((s) => s.id));
            _deselected = new Set(saved.filter((id) => known.has(id)));
          }
        } catch { /* fall back to all-selected */ }
        renderSessionList();   // build the checkboxes first —
        renderSessionMeta();   // the meta line counts them
      } catch {
        if (metaEl) metaEl.textContent = "Could not reach server.";
      }
    }

    function renderSessionMeta() {
      if (!metaEl || !_sessions.length) {
        if (metaEl) metaEl.textContent = "No sessions in database yet.";
        return;
      }
      const total   = _sessions.reduce((s, r) => s + (r.pairing_count || 0), 0);
      const checked = getCheckedIds().length;
      metaEl.textContent =
        `Database: ${total.toLocaleString()} pairings · ${_sessions.length} sessions` +
        (checked < _sessions.length ? ` (${checked} selected)` : " (all selected)");
      renderDataSourcesSummary();
    }

    // Update year header checkbox to reflect children state (checked / indeterminate / unchecked)
    function syncYearCheckbox(yearCb, body) {
      const boxes = [...body.querySelectorAll("input[type=checkbox]")];
      const checked = boxes.filter((b) => b.checked).length;
      yearCb.checked       = checked === boxes.length;
      yearCb.indeterminate = checked > 0 && checked < boxes.length;
    }

    function renderSessionList() {
      if (!list) return;
      list.innerHTML = "";

      // Group sessions by year, sorted ascending; within each year sort alphabetically
      const sorted = [..._sessions].sort((a, b) => {
        const ya = sessionYear(a), yb = sessionYear(b);
        if (ya !== yb) return ya.localeCompare(yb);
        return a.label.localeCompare(b.label);
      });

      const byYear = new Map();
      sorted.forEach((s) => {
        const yr = sessionYear(s);
        if (!byYear.has(yr)) byYear.set(yr, []);
        byYear.get(yr).push(s);
      });

      const years = [...byYear.keys()];
      const latestYear = years[years.length - 1]; // expand only the most recent year

      years.forEach((yr) => {
        const sessions = byYear.get(yr);
        const totalPairings = sessions.reduce((n, s) => n + (s.pairing_count || 0), 0);
        const isLatest = yr === latestYear;

        // ── Year group container ──
        const group = document.createElement("div");
        group.className = "session-year-group";
        group.dataset.year = yr;

        // ── Year header row ──
        const header = document.createElement("div");
        header.className = "session-year-header";
        header.tabIndex = 0;
        header.setAttribute("role", "button");
        header.setAttribute("aria-expanded", isLatest ? "true" : "false");

        const yearCb = document.createElement("input");
        yearCb.type      = "checkbox";
        yearCb.className = "session-year-cb";
        yearCb.checked   = true;

        const yearLabel = document.createElement("span");
        yearLabel.className   = "session-year-label";
        yearLabel.textContent = yr;

        const yearMeta = document.createElement("span");
        yearMeta.className   = "session-year-meta";
        yearMeta.textContent = `${sessions.length} sessions · ${totalPairings.toLocaleString()} pairings`;

        const arrow = document.createElement("span");
        arrow.className = "session-year-arrow";
        if (isLatest) arrow.classList.add("open");

        header.appendChild(yearCb);
        header.appendChild(yearLabel);
        header.appendChild(yearMeta);
        header.appendChild(arrow);

        // ── Year body (session rows) ──
        const body = document.createElement("div");
        body.className = "session-year-body" + (isLatest ? "" : " hidden");
        body.id = `historical-session-year-${yr.replace(/[^a-zA-Z0-9_-]/g, "-")}`;
        header.setAttribute("aria-controls", body.id);

        sessions.forEach((s) => {
          const row = document.createElement("label");
          row.className    = "session-selector-row";
          row.dataset.label = s.label.toLowerCase();

          const cb = document.createElement("input");
          cb.type      = "checkbox";
          cb.className = "session-selector-checkbox";
          cb.value     = String(s.id);
          cb.checked   = !_deselected.has(s.id);
          cb.addEventListener("change", () => {
            syncYearCheckbox(yearCb, body);
            renderSessionMeta();
            persistSelection();
          });

          const name = document.createElement("span");
          name.className   = "session-selector-name";
          name.textContent = s.label;

          const count = document.createElement("span");
          count.className   = "session-selector-count";
          count.textContent = (s.pairing_count || 0).toLocaleString();

          const renameBtn = document.createElement("button");
          renameBtn.type        = "button";
          renameBtn.className   = "session-row-action";
          renameBtn.textContent = "✎";
          renameBtn.title       = "Rename session";
          renameBtn.setAttribute("aria-label", `Rename session ${s.label}`);
          renameBtn.addEventListener("click", async (e) => {
            e.preventDefault();
            e.stopPropagation();
            const newLabel = window.prompt("Rename session:", s.label);
            if (newLabel === null || !newLabel.trim() || newLabel.trim() === s.label) return;
            try {
              const resp = await fetch(`/api/sessions/${s.id}`, {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ label: newLabel.trim() }),
                cache: "no-store",
              });
              const data = await resp.json().catch(() => ({}));
              if (!resp.ok || !data.ok) {
                window.alert(data.error || "Could not rename session.");
                return;
              }
              await loadSessions();
            } catch {
              window.alert("Could not reach server.");
            }
          });

          const deleteBtn = document.createElement("button");
          deleteBtn.type        = "button";
          deleteBtn.className   = "session-row-action session-row-action-delete";
          deleteBtn.textContent = "✕";
          deleteBtn.title       = "Delete session";
          deleteBtn.setAttribute("aria-label", `Delete session ${s.label}`);
          deleteBtn.addEventListener("click", async (e) => {
            e.preventDefault();
            e.stopPropagation();
            const n = (s.pairing_count || 0).toLocaleString();
            if (!window.confirm(`Delete session "${s.label}" and its ${n} pairing(s)? This cannot be undone.`)) return;
            try {
              const resp = await fetch(`/api/sessions/${s.id}`, { method: "DELETE", cache: "no-store" });
              const data = await resp.json().catch(() => ({}));
              if (!resp.ok || !data.ok) {
                window.alert(data.error || "Could not delete session.");
                return;
              }
              await loadSessions();
            } catch {
              window.alert("Could not reach server.");
            }
          });

          row.appendChild(cb);
          row.appendChild(name);
          row.appendChild(count);
          row.appendChild(renameBtn);
          row.appendChild(deleteBtn);
          body.appendChild(row);
        });

        // Year checkbox toggles all children
        yearCb.addEventListener("change", () => {
          body.querySelectorAll("input[type=checkbox]").forEach((cb) => {
            cb.checked = yearCb.checked;
          });
          yearCb.indeterminate = false;
          renderSessionMeta();
          persistSelection();
        });

        // Header click (not on the checkbox) collapses/expands body
        const toggleYear = () => {
          const collapsed = body.classList.toggle("hidden");
          arrow.classList.toggle("open", !collapsed);
          header.setAttribute("aria-expanded", collapsed ? "false" : "true");
        };
        header.addEventListener("click", (e) => {
          if (e.target === yearCb) return; // handled by checkbox itself
          toggleYear();
        });
        header.addEventListener("keydown", (e) => {
          if (e.target === yearCb || (e.key !== "Enter" && e.key !== " ")) return;
          e.preventDefault();
          toggleYear();
        });

        syncYearCheckbox(yearCb, body);
        group.appendChild(header);
        group.appendChild(body);
        list.appendChild(group);
      });

      applyFilter();
    }

    function applyFilter() {
      if (!list) return;
      const q = (searchEl?.value || "").trim().toLowerCase();

      list.querySelectorAll(".session-year-group").forEach((group) => {
        let anyVisible = false;
        group.querySelectorAll(".session-selector-row").forEach((row) => {
          const match = !q || (row.dataset.label || "").includes(q);
          row.style.display = match ? "" : "none";
          if (match) anyVisible = true;
        });
        // Show/hide the whole year group; auto-expand body when search is active
        group.style.display = anyVisible ? "" : "none";
        if (q && anyVisible) {
          const body = group.querySelector(".session-year-body");
          body?.classList.remove("hidden");
          const arrow = group.querySelector(".session-year-arrow");
          if (arrow) arrow.classList.add("open");
          group.querySelector(".session-year-header")?.setAttribute("aria-expanded", "true");
        }
      });
    }

    function getCheckedIds() {
      // Checkbox state is the source of truth — a session stays selected even
      // when the search filter is currently hiding its row.
      if (!list) return [];
      return [...list.querySelectorAll(".session-selector-checkbox")]
        .filter((cb) => cb.checked)
        .map((cb) => parseInt(cb.value, 10));
    }

    if (toggleBtn && panel) {
      toggleBtn.addEventListener("click", () => {
        const open = !panel.classList.contains("hidden");
        panel.classList.toggle("hidden", open);
        toggleBtn.textContent = open ? "Choose sessions" : "Hide sessions";
        toggleBtn.setAttribute("aria-expanded", open ? "false" : "true");
        if (!open) searchEl?.focus();
      });
    }

    if (searchEl) {
      searchEl.addEventListener("input", () => { applyFilter(); renderSessionMeta(); });
    }

    if (selectAll) {
      selectAll.addEventListener("click", () => {
        list.querySelectorAll(".session-selector-row").forEach((row) => {
          if (row.style.display !== "none") {
            const cb = row.querySelector("input[type=checkbox]");
            if (cb) cb.checked = true;
          }
        });
        list.querySelectorAll(".session-year-group").forEach((group) => {
          const yearCb = group.querySelector(".session-year-cb");
          const body   = group.querySelector(".session-year-body");
          if (yearCb && body) syncYearCheckbox(yearCb, body);
        });
        renderSessionMeta();
        persistSelection();
      });
    }

    if (selectNone) {
      selectNone.addEventListener("click", () => {
        list.querySelectorAll(".session-selector-row").forEach((row) => {
          if (row.style.display !== "none") {
            const cb = row.querySelector("input[type=checkbox]");
            if (cb) cb.checked = false;
          }
        });
        list.querySelectorAll(".session-year-group").forEach((group) => {
          const yearCb = group.querySelector(".session-year-cb");
          const body   = group.querySelector(".session-year-body");
          if (yearCb && body) syncYearCheckbox(yearCb, body);
        });
        renderSessionMeta();
        persistSelection();
      });
    }

    // Let other components (e.g. the Jackrabbit upload) refresh the list
    window._reloadSessions = loadSessions;

    window._getSessionSummary = () => ({
      total: _sessions.length,
      selected: getCheckedIds().length,
    });

    window._getSelectedSessionIds = () => {
      // All sessions checked (the default) → null = "use all sessions", so
      // the backend treats it as default history rather than an explicit
      // selection (an explicit selection hard-errors when no pairings match
      // the selected files; the default degrades to a warning instead).
      if (!list) return null;
      const boxCount = list.querySelectorAll(".session-selector-checkbox").length;
      const ids = getCheckedIds();
      return boxCount > 0 && ids.length === boxCount ? null : ids;
    };
    loadSessions();
}

// Jackrabbit pairings CSV upload → POST /api/import_jackrabbit_pairings
function initJackrabbitPairingsUpload() {
    const btn      = getElementByIdOrThrow("jackrabbitImportButton");
    const input    = getElementByIdOrThrow("jackrabbitPairingsFileInput");
    const metaEl   = getElementByIdOrThrow("jackrabbitImportMeta");

    btn.addEventListener("click", () => input.click());

    input.addEventListener("change", async () => {
      const file = input.files[0];
      if (!file) return;
      input.value = "";  // allow re-selecting the same file

      btn.disabled  = true;
      btn.textContent = "Uploading…";
      metaEl.textContent = `Uploading ${file.name}…`;

      try {
        const form = new FormData();
        form.append("file", file);
        const operator = getOperatorName();
        if (operator) form.append("operator", operator);
        const res  = await fetch("/api/import_jackrabbit_pairings", { method: "POST", body: form });
        const data = await res.json();

        if (data.ok) {
          const sessions = (data.sessions || []).join(", ") || "none";
          metaEl.textContent =
            `Imported ${data.imported} pairing(s), ${data.skipped} skipped. ` +
            `Sessions: ${sessions}`;
          // Refresh the session selector so new sessions appear without a reload
          window._reloadSessions?.();
        } else {
          metaEl.textContent = `Error: ${data.error || "Unknown error"}`;
        }
      } catch (err) {
        metaEl.textContent = `Upload failed: ${err.message}`;
      } finally {
        btn.disabled    = false;
        btn.textContent = "Upload pairings CSV";
      }
    });
}
