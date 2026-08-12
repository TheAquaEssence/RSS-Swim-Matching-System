const THEME_KEY = "aqua_theme"; // "dark" | "light"
const LAST_PDF_KEY = "aqua_last_pdf_url";
const LAST_FILLED_CLASSES_KEY = "aqua_last_filled_classes_url";

// Operator name — lightweight change attribution (no auth; app runs on a trusted LAN).
// Stored per-browser and sent with mutating requests so the DB records who changed what.
const OPERATOR_NAME_KEY = "aqua_operator_name";

function getOperatorName() {
  try {
    return (localStorage.getItem(OPERATOR_NAME_KEY) || "").trim();
  } catch {
    return "";
  }
}
const esc = window.AquaUi.escapeHtml;
const formatConfidence = window.AquaUi.formatConfidence;

function setExplainabilityAvailable(isAvailable) {
  const link = document.getElementById("explainabilityNavLink");
  if (!link) return;
  link.setAttribute("aria-disabled", String(!Boolean(isAvailable)));
}

function wireProductNavigation() {
  const link = document.getElementById("explainabilityNavLink");
  if (link) {
    link.addEventListener("click", (event) => {
      if (link.getAttribute("aria-disabled") === "true") event.preventDefault();
    });
  }

  const dataSettingsLink = document.getElementById("dataSettingsNavLink");
  const advancedSection = document.getElementById("advancedSection");
  if (!dataSettingsLink || !advancedSection) return;

  const showDataSettings = () => {
    advancedSection.open = true;
    const headerHeight = document.querySelector(".app-header")?.getBoundingClientRect().height || 0;
    const targetTop = window.scrollY + advancedSection.getBoundingClientRect().top - headerHeight - 20;
    window.scrollTo({ top: Math.max(0, targetTop), behavior: "smooth" });
  };

  dataSettingsLink.addEventListener("click", (event) => {
    event.preventDefault();
    window.history.replaceState(null, "", "#advancedSection");
    showDataSettings();
  });

  if (window.location.hash === "#advancedSection") {
    // Let the browser finish its native hash jump before applying the sticky-header offset.
    window.setTimeout(showDataSettings, 100);
  }
}

function setReopenPdfButton(pdfUrl) {
  const btn = document.getElementById("reopenPdfButton");
  if (!btn) return;

  if (pdfUrl) {
    btn.classList.remove("hidden");
    btn.onclick = () => downloadFile(pdfUrl, "matching_report.pdf");
  } else {
    btn.classList.add("hidden");
    btn.onclick = null;
  }
}

function downloadFile(url, filename) {
  if (!url) return;
  const anchor = document.createElement("a");
  anchor.href = url;
  let suggestedName = filename || "";
  if (!suggestedName) {
    try {
      suggestedName = decodeURIComponent(new URL(url, window.location.href).pathname.split("/").pop() || "");
    } catch {
      suggestedName = "";
    }
  }
  if (/^[^/\\]+\.(csv|pdf)$/i.test(suggestedName)) anchor.download = suggestedName;
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

async function loadLastPdfFromStorage() {
  const url = localStorage.getItem(LAST_PDF_KEY) || "";
  if (!url) return;
  try {
    const res = await fetch(url, { method: "HEAD", cache: "no-store" });
    if (res.ok) setReopenPdfButton(url);
    else localStorage.removeItem(LAST_PDF_KEY);
  } catch {
    localStorage.removeItem(LAST_PDF_KEY);
  }
}

async function loadLastFilledClassesFromStorage() {
  const url = localStorage.getItem(LAST_FILLED_CLASSES_KEY) || "";
  if (!url) return;
  try {
    const res = await fetch(url, { method: "HEAD", cache: "no-store" });
    if (res.ok) setDownloadFilledClassesButton(url);
    else localStorage.removeItem(LAST_FILLED_CLASSES_KEY);
  } catch {
    localStorage.removeItem(LAST_FILLED_CLASSES_KEY);
  }
}

function applyTheme(theme) {
  const t = theme === "light" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", t);

  const text = document.getElementById("themeText");
  if (text) text.textContent = t === "light" ? "Dark mode" : "Light mode";

  const toggle = document.getElementById("themeToggle");
  if (toggle) toggle.setAttribute("aria-label", t === "light" ? "Switch to dark mode" : "Switch to light mode");
}

function loadInitialTheme() {
  const saved = localStorage.getItem(THEME_KEY);
  if (saved === "light" || saved === "dark") return saved;

  // default to OS preference
  const prefersLight = window.matchMedia?.("(prefers-color-scheme: light)")?.matches;
  return prefersLight ? "light" : "dark";
}

function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme") || "dark";
  const next = current === "light" ? "dark" : "light";
  localStorage.setItem(THEME_KEY, next);
  applyTheme(next);
}

async function updateHostStatusIndicator() {
  const statusDot = getElementByIdOrThrow("hostStatusDot");
  const statusText = getElementByIdOrThrow("hostStatusText");

  try {
    const response = await fetch("/api/health", { cache: "no-store" });
    if (response.ok) {
      statusDot.style.background = "";
      statusDot.classList.add("online");
      statusText.textContent = "Host: online";
      return;
    }
    statusDot.classList.remove("online");
    statusDot.style.background = "var(--danger)";
    statusText.textContent = "Host: error";
  } catch {
    statusDot.classList.remove("online");
    statusDot.style.background = "var(--danger)";
    statusText.textContent = "Host: offline";
  }
}

function getElementByIdOrThrow(element_id) {
  const element = document.getElementById(element_id);
  if (!element) throw new Error(`Missing element with id="${element_id}"`);
  return element;
}

async function loadLatestGeneratedResult() {
  try {
    const response = await fetch("/api/latest_generation_result", { cache: "no-store" });
    if (!response.ok) return;

    const result = await response.json().catch(() => null);
    if (!result?.ok || !result?.has_result || !result.summary) return;

    const output = document.getElementById("output");
    const s = result.summary ?? {};
    const diagnosticsHtml = renderImportDiagnosticsHtml(result.import_diagnostics);
    const warningsHtml = renderGenerateWarningsHtml(result.warnings);
    if (output) {
      if (diagnosticsHtml || warningsHtml) {
        const assigned = s.assigned_swimmers ?? "?";
        const classes = s.classes ?? "?";
        output.classList.remove("hidden");
        output.innerHTML =
          `<div class="status-success"><span class="status-icon" aria-hidden="true">\u2713</span><span>${esc(String(assigned))} swimmers matched across ${esc(String(classes))} classes</span></div>` +
          diagnosticsHtml +
          warningsHtml;
      } else {
        output.innerHTML = "";
        output.classList.add("hidden");
      }
    }

    renderResults(result);

    const rf = result.result_files ?? {};
    if (rf.pdf) {
      localStorage.setItem(LAST_PDF_KEY, rf.pdf);
      setReopenPdfButton(rf.pdf);
    }
    if (rf.filled_classes_export) {
      localStorage.setItem(LAST_FILLED_CLASSES_KEY, rf.filled_classes_export);
      setDownloadFilledClassesButton(rf.filled_classes_export);
    }
  } catch {
    // Leave the page in its normal empty state if no previous result is available.
  }
}

function setDownloadFilledClassesButton(fileUrl) {
  const btn = document.getElementById("downloadFilledClassesButton");
  if (!btn) return;

  if (fileUrl) {
    btn.classList.remove("hidden");
    btn.onclick = () => downloadFile(fileUrl);
  } else {
    btn.classList.add("hidden");
    btn.onclick = null;
  }
}

async function initializeUserInterface() {
  const settingsFiles = window.AquaSettingsFiles;

  wireProductNavigation();
  window.AquaProfileDrawer.wireProfileDrawer();
  settingsFiles.wireSettingsFiles({ setGenerateEnabled });

  // Instructor defaults + style/color editor (see instructor_defaults.js).
  // Wired before the first refreshUiFromHost call, which delegates
  // loadInstructorDefaults() to this module.
  window.AquaInstructorDefaults.wireInstructorDefaults({
    postJson: settingsFiles.postJson,
    getSettingsFromHost: settingsFiles.getSettingsFromHost,
    getFileNameFromPath: settingsFiles.getFileNameFromPath,
    loadReferenceTableOptions: settingsFiles.loadReferenceTableOptions,
    esc,
  });

  const settings = await settingsFiles.getSettingsFromHost();
  await Promise.all([
    settingsFiles.refreshUiFromHost(settings),
    loadLatestGeneratedResult(),
  ]);
  loadLastPdfFromStorage();
  loadLastFilledClassesFromStorage();

  // Historical pairings — session selector (see session_selector.js)
  initSessionSelector();

  // Operator name (change attribution) — persisted per-browser
  (() => {
    const input = document.getElementById("operatorNameInput");
    if (!input) return;
    input.value = getOperatorName();
    input.addEventListener("input", () => {
      try {
        localStorage.setItem(OPERATOR_NAME_KEY, input.value.trim());
      } catch { /* private mode — attribution just won't persist */ }
    });
  })();

  // Jackrabbit pairings CSV upload (see session_selector.js)
  initJackrabbitPairingsUpload();

  window.AquaReferenceEditors.wireReferenceEditors({
    postJson: settingsFiles.postJson,
    getFileNameFromPath: settingsFiles.getFileNameFromPath,
    refreshUi: settingsFiles.refreshUiFromHost,
  });
  // Manage Instructors editor + import review wiring (see instructor_editor.js)
  wireInstructorEditor();

  // Generate button (see generate_flow.js)
  wireGenerateFlow();


}

async function sendUserInterfaceHeartbeat() {
  try {
    await fetch("/api/heartbeat", { method: "POST", cache: "no-store" });
  } catch {
    // ignore
  }
}


document.addEventListener("DOMContentLoaded", () => {
  // set theme ASAP
  applyTheme(loadInitialTheme());

  const themeToggle = document.getElementById("themeToggle");
  if (themeToggle) themeToggle.addEventListener("click", toggleTheme);

  // Do NOT call POST /api/shutdown from pagehide: that event fires on any
  // same-tab navigation (including to /xai/), which kills the server.
  // The heartbeat watchdog handles server lifecycle instead.
  void sendUserInterfaceHeartbeat();
  void updateHostStatusIndicator();
  setInterval(() => void sendUserInterfaceHeartbeat(), 10000);
  setInterval(() => void updateHostStatusIndicator(), 5000);

  void initializeUserInterface().catch((e) => {
    getElementByIdOrThrow("output").textContent = String(e);
  });
});
