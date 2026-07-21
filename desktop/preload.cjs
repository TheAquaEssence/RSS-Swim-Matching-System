"use strict";

const { contextBridge, ipcRenderer } = require("electron");

// Sandboxed Electron preload scripts cannot require local CommonJS modules.
// Keep this narrow channel name in the single-file preload and verify it
// against ipc_contract.cjs in the preload unit test.
const OPEN_INPUT_FILE_CHANNEL = "aqua:dialog:open-input-file";

async function openInputFile(purpose) {
  if (typeof purpose !== "string") throw new TypeError("purpose must be a string");
  const result = await ipcRenderer.invoke(OPEN_INPUT_FILE_CHANNEL, purpose);
  if (!result || result.cancelled === true) return Object.freeze({ cancelled: true });
  if (typeof result.path !== "string") throw new Error("Invalid native dialog response");
  return Object.freeze({ cancelled: false, path: result.path });
}

const dialogs = Object.freeze({ openInputFile });
contextBridge.exposeInMainWorld("AquaDesktop", Object.freeze({ dialogs }));
