window.AquaUi = window.AquaUi || {
  escapeHtml(str) {
    if (str == null) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  },

  normalizeConfidence(conf) {
    if (conf == null) return null;
    if (conf <= 1 && conf > 0) return conf * 100;
    return conf;
  },

  formatConfidence(value) {
    const normalized = window.AquaUi.normalizeConfidence(value);
    if (typeof normalized !== "number") return "n/a";
    return `${normalized.toFixed(2)}%`;
  },
};
