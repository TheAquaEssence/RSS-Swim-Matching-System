// Profile and review-details drawer. Owns drawer state, profile rendering,
// review-flag presentation, and delegated result-table interactions.
(() => {
  "use strict";

  const esc = window.AquaUi.escapeHtml;
  let drawerOpen = false;
  let latestMatchResult = null;
  let lastDrawerTrigger = null;

  const FLAG_SEVERITY_ORDER = { none: 0, info: 1, review: 2, urgent: 3 };
  const FLAG_SEVERITY_LABELS = {
    none: "Clear",
    info: "Info",
    review: "Review",
    urgent: "Urgent",
  };
  const FLAG_TITLE_OVERRIDES = {
    non_response_swimmer_type: "Default swimmer type used",
    default_instructor_profile: "Default instructor profile used",
  };

  function setDrawerContent(contentNode) {
    const content = document.getElementById("drawer-content");
    if (!content || !contentNode) return;
    content.replaceChildren(contentNode);
  }

  function openDrawer(type, contentNode) {
    const drawer = document.getElementById("profile-drawer");
    const backdrop = document.getElementById("drawer-backdrop");
    const header = document.getElementById("drawer-header");
    const title = document.getElementById("drawer-title");
    if (!drawer || !backdrop || !header || !title) return;

    const drawerModes = {
      swimmer: { theme: "swimmer-theme", title: "🏊 Swimmer Profile" },
      instructor: { theme: "instructor-theme", title: "🎓 Instructor Profile" },
      review: { theme: "review-theme", title: "Review Details" },
    };
    const mode = drawerModes[type] || drawerModes.review;
    lastDrawerTrigger = document.activeElement instanceof HTMLElement ? document.activeElement : null;

    header.className = "drawer-header";
    header.classList.add(mode.theme);
    title.textContent = mode.title;
    setDrawerContent(contentNode);
    backdrop.classList.add("open");
    drawer.classList.add("open");
    backdrop.setAttribute("aria-hidden", "false");
    drawer.setAttribute("aria-hidden", "false");
    drawerOpen = true;
    document.getElementById("drawer-close")?.focus();
  }

  function closeDrawer() {
    const drawer = document.getElementById("profile-drawer");
    const backdrop = document.getElementById("drawer-backdrop");
    if (drawer) drawer.classList.remove("open");
    if (backdrop) backdrop.classList.remove("open");
    drawer?.setAttribute("aria-hidden", "true");
    backdrop?.setAttribute("aria-hidden", "true");
    drawerOpen = false;
    if (lastDrawerTrigger?.isConnected) lastDrawerTrigger.focus();
    lastDrawerTrigger = null;
  }

  function createDiv(className, text) {
    const el = document.createElement("div");
    if (className) el.className = className;
    if (text != null) el.textContent = String(text);
    return el;
  }

  function createProfileField(label, value) {
    const field = createDiv("profile-field");
    field.append(createDiv("profile-field-label", label));
    field.append(createDiv("profile-field-value", value));
    return field;
  }

  function createSectionTitle(text) {
    return createDiv("profile-section-title", text);
  }

  function createDrawerMessage(message) {
    return createDiv("drawer-error", message);
  }

  function resolveFlagTitle(code, fallbackTitle) {
    if (code && FLAG_TITLE_OVERRIDES[code]) return FLAG_TITLE_OVERRIDES[code];
    return fallbackTitle || code || "Review flag";
  }

  function normalizeFlags(item) {
    if (!item) return [];
    if (Array.isArray(item.flags)) {
      return item.flags.map((flag) => ({
        code: flag.code || "",
        title: resolveFlagTitle(flag.code || "", flag.title || ""),
        description: flag.description || "",
        severity: flag.severity || item.review_severity || "none",
        review_action: flag.review_action || item.review_action || "",
        review_action_label: flag.review_action_label || item.review_action || "",
      }));
    }
    if (!Array.isArray(item.flag_codes) || item.flag_codes.length === 0) return [];
    return item.flag_codes.map((code) => ({
      code,
      title: resolveFlagTitle(code, code.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())),
      description: item.flag_summary || "",
      severity: item.review_severity || "review",
      review_action: item.review_action || "",
      review_action_label: item.review_action || "",
    }));
  }

  function getHighestFlagSeverity(flags, fallback = "none") {
    let highest = fallback || "none";
    flags.forEach((flag) => {
      const severity = flag.severity || "none";
      if ((FLAG_SEVERITY_ORDER[severity] ?? 0) > (FLAG_SEVERITY_ORDER[highest] ?? 0)) highest = severity;
    });
    return highest;
  }

  function renderReviewText(item) {
    const flags = normalizeFlags(item);
    if (flags.length === 0) return '<span class="review-text review-text-none">\u2014</span>';
    const severity = getHighestFlagSeverity(flags, item.review_severity);
    const label = FLAG_SEVERITY_LABELS[severity] || "Review";
    return `<span class="review-text review-text-${esc(severity)}">${esc(label)}<span class="review-chevron" aria-hidden="true"> \u203a</span></span>`;
  }

  function formatPercent(value, digits = 1) {
    if (typeof value !== "number") return value == null || value === "" ? "" : String(value);
    return `${value.toFixed(digits)}%`;
  }

  function formatAge(age) {
    if (typeof age !== "number") return age == null ? "?" : String(age);
    const totalMonths = Math.round(age * 12);
    const years = Math.floor(totalMonths / 12);
    const months = totalMonths % 12;
    if (years === 0) return `${totalMonths} mo`;
    if (months === 0) return years === 1 ? "1 yr" : `${years} yrs`;
    return `${years} yr ${months} mo`;
  }

  function matchSwimmerNames(match) {
    if (!match) return "";
    if (match.type === "pair") {
      const first = match.swimmer_1_name ?? match.swimmer_1_id ?? "?";
      const second = match.swimmer_2_name ?? match.swimmer_2_id ?? "?";
      return `${first}, ${second}`;
    }
    return String(match.swimmer_name ?? match.swimmer_id ?? "?");
  }

  function appendReviewFields(fragment, fields) {
    fields.forEach(([label, value]) => {
      if (value !== undefined && value !== null && value !== "") fragment.append(createProfileField(label, value));
    });
  }

  function renderReviewDetails(kind, item) {
    const fragment = document.createDocumentFragment();
    const flags = normalizeFlags(item);
    if (kind === "match") {
      fragment.append(createSectionTitle("Assignment"));
      appendReviewFields(fragment, [
        ["Instructor", item.instructor_name || item.instructor_id || "?"],
        ["Swimmer(s)", matchSwimmerNames(item)],
        ["Class Type", item.type || "?"],
        ["Match Type", item.match_type || "?"],
        ["Compatibility", formatPercent(item.compatibility_score)],
        ["Confidence", formatPercent(item.confidence, 0)],
        ["Reason", item.reason || item.reason_summary || ""],
      ]);
      if (item.explanation) {
        fragment.append(createSectionTitle("Explanation"));
        fragment.append(createDiv("profile-notes", item.explanation));
      }
    } else {
      const bestMatch = item.best_available_instructor_name
        ? `${item.best_available_instructor_name} (${formatPercent(item.best_available_score)})`
        : "";
      fragment.append(createSectionTitle("Unassigned Swimmer"));
      appendReviewFields(fragment, [
        ["Swimmer", item.swimmer_name || item.swimmer_id || "?"],
        ["Skill Level", item.skill_level || "?"],
        ["Age", formatAge(item.age)],
        ["Special Needs", item.has_special_needs ? "Yes" : "No"],
        ["Reason", item.reason || ""],
        ["Best Legal Match", bestMatch],
        ["Auto-Assign Threshold", formatPercent(item.min_auto_assign_score)],
      ]);
    }

    fragment.append(createSectionTitle("Review Flags"));
    if (flags.length === 0) {
      fragment.append(createDiv("drawer-error", "No review flags for this row."));
      return fragment;
    }
    flags.forEach((flag) => {
      const severity = flag.severity || "none";
      const card = createDiv(`flag-card flag-${severity}`);
      const header = createDiv("flag-card-header");
      header.append(createDiv("flag-card-title", flag.title || flag.code || "Review flag"));
      header.append(createDiv("flag-card-severity", FLAG_SEVERITY_LABELS[severity] || severity));
      card.append(header);
      if (flag.description) card.append(createDiv("flag-card-description", flag.description));
      if (flag.review_action_label) card.append(createDiv("flag-card-action", `Action: ${flag.review_action_label}`));
      if (flag.code) card.append(createDiv("flag-card-code", flag.code));
      fragment.append(card);
    });
    return fragment;
  }

  function showReviewDetails(kind, index) {
    const collection = kind === "unassigned" ? latestMatchResult?.unassigned : latestMatchResult?.matches;
    const item = Array.isArray(collection) ? collection[index] : null;
    if (item) openDrawer("review", renderReviewDetails(kind, item));
  }

  function renderSwimmerProfile(profile) {
    const fragment = document.createDocumentFragment();
    fragment.append(createProfileField("Name", profile.name));
    fragment.append(createProfileField("Age", formatAge(profile.age)));
    fragment.append(createProfileField("Type", profile.swimmer_type_name || "Type " + profile.swimmer_type_id));
    fragment.append(createProfileField("Skill Level", profile.skill_level));
    fragment.append(createProfileField("Special Needs", profile.has_special_needs ? "Yes" : "No"));
    fragment.append(createProfileField("Pair ID", profile.pair_id != null ? "#" + profile.pair_id : "None"));
    fragment.append(createSectionTitle("Notes"));
    fragment.append(createDiv("profile-notes", profile.notes ? String(profile.notes) : "No notes"));
    return fragment;
  }

  function renderInstructorProfile(profile) {
    function cert(label, value) {
      const badge = document.createElement("span");
      badge.className = "profile-cert " + (value ? "yes" : "no");
      badge.textContent = (value ? "\u2705" : "\u274C") + " " + label;
      return badge;
    }
    const certs = createDiv();
    certs.append(cert("Adapted", profile.can_teach_adapted));
    certs.append(cert("Adults", profile.can_teach_adults));
    certs.append(cert("Babies", profile.can_teach_babies));
    certs.append(cert("NL", profile.can_teach_NL));
    const fragment = document.createDocumentFragment();
    fragment.append(createProfileField("Name", profile.name));
    fragment.append(createProfileField("Team Captain", profile.is_team_captain ? "Yes" : "No"));
    fragment.append(createSectionTitle("Colors"));
    fragment.append(createProfileField("Primary", profile.primary_color_name || "Color " + profile.primary_color_id));
    fragment.append(createProfileField("Secondary", profile.secondary_color_name || "Color " + profile.secondary_color_id));
    fragment.append(createSectionTitle("Styles"));
    fragment.append(createProfileField("Primary", profile.primary_style_name || "Style " + profile.primary_style_id));
    fragment.append(createProfileField("Secondary", profile.secondary_style_name || "Style " + profile.secondary_style_id));
    fragment.append(createSectionTitle("Certifications"));
    fragment.append(certs);
    return fragment;
  }

  async function fetchAndShowProfile(type, id) {
    openDrawer(type, createDrawerMessage("Loading profile\u2026"));
    try {
      const response = await fetch("/api/profile/" + type + "/" + id, { cache: "no-store" });
      const data = await response.json();
      if (!data.ok || !data.profile) {
        setDrawerContent(createDrawerMessage(data.error || "Profile not found"));
        return;
      }
      setDrawerContent(type === "swimmer" ? renderSwimmerProfile(data.profile) : renderInstructorProfile(data.profile));
    } catch {
      setDrawerContent(createDrawerMessage("Failed to load profile"));
    }
  }

  function wireTableInteractions(tableId) {
    const table = document.getElementById(tableId);
    if (!table) return;
    table.addEventListener("click", (event) => {
      const link = event.target.closest(".profile-link");
      if (link) {
        if (link.dataset.type && link.dataset.id) fetchAndShowProfile(link.dataset.type, link.dataset.id);
        return;
      }
      const row = event.target.closest("tr[data-review-kind]");
      if (row) showReviewDetails(row.dataset.reviewKind, Number(row.dataset.reviewIndex));
    });
    table.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      if (event.target.closest(".profile-link")) return;
      const row = event.target.closest("tr[data-review-kind]");
      if (!row) return;
      event.preventDefault();
      showReviewDetails(row.dataset.reviewKind, Number(row.dataset.reviewIndex));
    });
  }

  function wireProfileDrawer() {
    document.getElementById("drawer-close")?.addEventListener("click", closeDrawer);
    document.getElementById("drawer-backdrop")?.addEventListener("click", closeDrawer);
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && drawerOpen) closeDrawer();
    });
    wireTableInteractions("results-table");
    wireTableInteractions("unassigned-table");
  }

  function setLatestMatchResult(result) {
    latestMatchResult = result;
  }

  window.AquaProfileDrawer = Object.freeze({
    wireProfileDrawer,
    setLatestMatchResult,
    normalizeFlags,
    getHighestFlagSeverity,
    renderReviewText,
    formatAge,
    matchSwimmerNames,
  });
})();
