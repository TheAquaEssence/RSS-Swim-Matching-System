"use strict";

const path = require("node:path");

const EXPORT_TYPES = Object.freeze({
  csv: Object.freeze({ name: "CSV files", fallbackName: "aqua-essence-export.csv" }),
  pdf: Object.freeze({ name: "PDF files", fallbackName: "aqua-essence-report.pdf" }),
});

function safeDownloadName(value) {
  const candidate = typeof value === "string" ? path.basename(value) : "";
  const extension = path.extname(candidate).slice(1).toLowerCase();
  const type = EXPORT_TYPES[extension];
  if (!type) return null;

  let stem = path.basename(candidate, path.extname(candidate))
    .replace(/[<>:"/\\|?*\x00-\x1f]/g, "_")
    .replace(/[. ]+$/g, "")
    .slice(0, 120);
  if (/^(con|prn|aux|nul|com[1-9]|lpt[1-9])$/i.test(stem)) stem = `_${stem}`;
  return {
    extension,
    filename: `${stem || path.basename(type.fallbackName, `.${extension}`)}.${extension}`,
    type,
  };
}

function validSavePath(selectedPath, expectedExtension) {
  return typeof selectedPath === "string"
    && selectedPath.length > 0
    && selectedPath.length <= 32767
    && path.isAbsolute(selectedPath)
    && path.extname(selectedPath).slice(1).toLowerCase() === expectedExtension;
}

function registerDownloadHandler({
  session,
  dialog,
  downloadDirectory,
  getParentWindow = () => null,
}) {
  if (!session || typeof session.on !== "function" || typeof session.removeListener !== "function") {
    throw new TypeError("A valid Electron session implementation is required");
  }
  if (!dialog || typeof dialog.showSaveDialog !== "function") {
    throw new TypeError("A valid Electron dialog implementation is required");
  }
  if (typeof downloadDirectory !== "string" || !path.isAbsolute(downloadDirectory)) {
    throw new TypeError("downloadDirectory must be an absolute path");
  }
  if (typeof getParentWindow !== "function") {
    throw new TypeError("getParentWindow must be a function");
  }

  const onWillDownload = async (_event, item) => {
    const selection = safeDownloadName(item?.getFilename?.());
    if (!selection || typeof item?.pause !== "function" || typeof item?.cancel !== "function") {
      item?.cancel?.();
      return;
    }

    item.pause();
    const options = {
      title: "Save Aqua Essence export",
      defaultPath: path.join(downloadDirectory, selection.filename),
      filters: [{ name: selection.type.name, extensions: [selection.extension] }],
    };

    try {
      const parentWindow = getParentWindow();
      const result = parentWindow
        ? await dialog.showSaveDialog(parentWindow, options)
        : await dialog.showSaveDialog(options);
      if (result?.canceled !== false || !validSavePath(result.filePath, selection.extension)) {
        item.cancel();
        return;
      }
      item.setSavePath(result.filePath);
      item.resume();
    } catch {
      item.cancel();
    }
  };

  session.on("will-download", onWillDownload);
  return function unregisterDownloadHandler() {
    session.removeListener("will-download", onWillDownload);
  };
}

module.exports = Object.freeze({
  registerDownloadHandler,
  safeDownloadName,
  validSavePath,
});
