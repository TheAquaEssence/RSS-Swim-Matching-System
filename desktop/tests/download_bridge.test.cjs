"use strict";

const assert = require("node:assert/strict");
const { EventEmitter } = require("node:events");
const path = require("node:path");
const test = require("node:test");

const {
  registerDownloadHandler,
  safeDownloadName,
  validSavePath,
} = require("../download_bridge.cjs");

function createHarness({ filename = "classes_filled.csv", result, parentWindow = null } = {}) {
  const session = new EventEmitter();
  const calls = [];
  const actions = [];
  const item = {
    getFilename: () => filename,
    pause: () => actions.push("pause"),
    cancel: () => actions.push("cancel"),
    setSavePath: (value) => actions.push(["save", value]),
    resume: () => actions.push("resume"),
  };
  const dialog = {
    async showSaveDialog(...args) {
      calls.push(args);
      return result;
    },
  };
  const unregister = registerDownloadHandler({
    session,
    dialog,
    downloadDirectory: path.resolve("downloads"),
    getParentWindow: () => parentWindow,
  });
  return { actions, calls, item, session, unregister };
}

async function emitDownload(harness) {
  const [handler] = harness.session.listeners("will-download");
  await handler({}, harness.item);
}

test("sanitizes suggested basenames and accepts only current CSV/PDF exports", () => {
  assert.deepEqual(safeDownloadName("../unsafe:name.csv"), {
    extension: "csv",
    filename: "unsafe_name.csv",
    type: { name: "CSV files", fallbackName: "aqua-essence-export.csv" },
  });
  assert.equal(safeDownloadName("matching_report.pdf").filename, "matching_report.pdf");
  assert.equal(safeDownloadName("CON.csv").filename, "_CON.csv");
  assert.equal(safeDownloadName("archive.zip"), null);
  assert.equal(safeDownloadName("report.pdf.exe"), null);
});

test("prompts with a safe default path and resumes an approved CSV download", async () => {
  const selected = path.resolve("chosen", "instructors.csv");
  const parentWindow = { name: "main" };
  const harness = createHarness({
    filename: "..\\instructors:2026.csv",
    result: { canceled: false, filePath: selected },
    parentWindow,
  });
  await emitDownload(harness);

  assert.deepEqual(harness.actions, ["pause", ["save", selected], "resume"]);
  assert.equal(harness.calls[0][0], parentWindow);
  assert.equal(harness.calls[0][1].defaultPath, path.resolve("downloads", "instructors_2026.csv"));
  assert.deepEqual(harness.calls[0][1].filters, [{ name: "CSV files", extensions: ["csv"] }]);
});

test("cancels on user cancellation, invalid paths, unsupported types, and dialog failure", async () => {
  for (const options of [
    { result: { canceled: true } },
    { result: { canceled: false, filePath: path.resolve("report.pdf") } },
    { filename: "data.json", result: { canceled: false, filePath: path.resolve("data.json") } },
  ]) {
    const harness = createHarness(options);
    await emitDownload(harness);
    assert.equal(harness.actions.at(-1), "cancel");
    assert.equal(harness.actions.includes("resume"), false);
  }

  const harness = createHarness();
  harness.session.removeAllListeners("will-download");
  registerDownloadHandler({
    session: harness.session,
    dialog: { showSaveDialog: async () => { throw new Error("private path"); } },
    downloadDirectory: path.resolve("downloads"),
  });
  await emitDownload(harness);
  assert.deepEqual(harness.actions, ["pause", "cancel"]);
});

test("removes the narrow session handler and validates dependencies", () => {
  const harness = createHarness({ result: { canceled: true } });
  assert.equal(harness.session.listenerCount("will-download"), 1);
  harness.unregister();
  assert.equal(harness.session.listenerCount("will-download"), 0);

  const dialog = { showSaveDialog: async () => ({ canceled: true }) };
  const session = new EventEmitter();
  assert.throws(() => registerDownloadHandler({ session: {}, dialog, downloadDirectory: path.resolve("d") }), /session/);
  assert.throws(() => registerDownloadHandler({ session, dialog: {}, downloadDirectory: path.resolve("d") }), /dialog/);
  assert.throws(() => registerDownloadHandler({ session, dialog, downloadDirectory: "relative" }), /downloadDirectory/);
});

test("save-path validation requires an absolute path with the expected extension", () => {
  assert.equal(validSavePath(path.resolve("export.csv"), "csv"), true);
  assert.equal(validSavePath(path.resolve("export.pdf"), "csv"), false);
  assert.equal(validSavePath("export.csv", "csv"), false);
});
