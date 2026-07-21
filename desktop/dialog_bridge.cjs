"use strict";

const path = require("node:path");

const { DIALOG_CHANNELS, INPUT_FILE_PURPOSES } = require("./ipc_contract.cjs");

function requirePurpose(value) {
  if (typeof value !== "string" || !Object.hasOwn(INPUT_FILE_PURPOSES, value)) {
    throw new TypeError("Unsupported input-file purpose");
  }
  return value;
}

function validateSelectedPath(selectedPath, allowedExtensions) {
  if (typeof selectedPath !== "string" || selectedPath.length === 0 || selectedPath.length > 32767) {
    throw new Error("Native dialog returned an invalid file selection");
  }
  const extension = path.extname(selectedPath).slice(1).toLowerCase();
  if (!path.isAbsolute(selectedPath) || !allowedExtensions.includes(extension)) {
    throw new Error("Native dialog returned an invalid file selection");
  }
  return selectedPath;
}

function registerDialogHandlers({ ipcMain, dialog, getParentWindow = () => null }) {
  if (!ipcMain || typeof ipcMain.handle !== "function" || typeof ipcMain.removeHandler !== "function") {
    throw new TypeError("A valid Electron ipcMain implementation is required");
  }
  if (!dialog || typeof dialog.showOpenDialog !== "function") {
    throw new TypeError("A valid Electron dialog implementation is required");
  }
  if (typeof getParentWindow !== "function") {
    throw new TypeError("getParentWindow must be a function");
  }

  ipcMain.handle(DIALOG_CHANNELS.OPEN_INPUT_FILE, async (_event, purposeValue) => {
    const purpose = requirePurpose(purposeValue);
    const config = INPUT_FILE_PURPOSES[purpose];
    const options = {
      title: config.title,
      properties: ["openFile"],
      filters: [{
        name: config.extensions.length === 1 ? "CSV files" : "CSV or Excel files",
        extensions: [...config.extensions],
      }],
    };
    const parentWindow = getParentWindow();
    const result = parentWindow
      ? await dialog.showOpenDialog(parentWindow, options)
      : await dialog.showOpenDialog(options);

    if (!result || result.canceled === true || !Array.isArray(result.filePaths) || result.filePaths.length === 0) {
      return { cancelled: true };
    }
    if (result.filePaths.length !== 1) {
      throw new Error("Native dialog returned an invalid file selection");
    }

    return {
      cancelled: false,
      path: validateSelectedPath(result.filePaths[0], config.extensions),
    };
  });

  return function unregisterDialogHandlers() {
    ipcMain.removeHandler(DIALOG_CHANNELS.OPEN_INPUT_FILE);
  };
}

module.exports = Object.freeze({
  registerDialogHandlers,
});
