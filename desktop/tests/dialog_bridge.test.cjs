"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");
const test = require("node:test");

const { registerDialogHandlers } = require("../dialog_bridge.cjs");
const { DIALOG_CHANNELS } = require("../ipc_contract.cjs");

function createHarness(result, parentWindow = null) {
  const handlers = new Map();
  const removed = [];
  const calls = [];
  const ipcMain = {
    handle(channel, handler) {
      handlers.set(channel, handler);
    },
    removeHandler(channel) {
      removed.push(channel);
      handlers.delete(channel);
    },
  };
  const dialog = {
    async showOpenDialog(...args) {
      calls.push(args);
      return result;
    },
  };
  const unregister = registerDialogHandlers({ ipcMain, dialog, getParentWindow: () => parentWindow });
  return { calls, handlers, removed, unregister };
}

test("registers one narrow open-file handler and removes it cleanly", () => {
  const harness = createHarness({ canceled: true, filePaths: [] });
  assert.deepEqual([...harness.handlers.keys()], [DIALOG_CHANNELS.OPEN_INPUT_FILE]);
  harness.unregister();
  assert.deepEqual(harness.removed, [DIALOG_CHANNELS.OPEN_INPUT_FILE]);
  assert.equal(harness.handlers.size, 0);
});

test("rejects every purpose outside the explicit whitelist before opening a dialog", async () => {
  const harness = createHarness({ canceled: true, filePaths: [] });
  const handler = harness.handlers.get(DIALOG_CHANNELS.OPEN_INPUT_FILE);
  for (const value of [undefined, null, "", "historical_pairings", "../classes", {}, ["classes"]]) {
    await assert.rejects(handler({}, value), /Unsupported input-file purpose/);
  }
  assert.equal(harness.calls.length, 0);
});

test("opens a single-file tabular dialog attached to the application window", async () => {
  const selectedPath = path.resolve("fixtures", "classes.xlsx");
  const parentWindow = { name: "main" };
  const harness = createHarness({ canceled: false, filePaths: [selectedPath] }, parentWindow);
  const handler = harness.handlers.get(DIALOG_CHANNELS.OPEN_INPUT_FILE);

  assert.deepEqual(await handler({}, "classes"), { cancelled: false, path: selectedPath });
  assert.equal(harness.calls.length, 1);
  assert.equal(harness.calls[0][0], parentWindow);
  assert.deepEqual(harness.calls[0][1].properties, ["openFile"]);
  assert.deepEqual(harness.calls[0][1].filters[0].extensions, ["csv", "xlsx", "xlsm"]);
});

test("cancellation returns no path", async () => {
  const harness = createHarness({ canceled: true, filePaths: [path.resolve("ignored.csv")] });
  const handler = harness.handlers.get(DIALOG_CHANNELS.OPEN_INPUT_FILE);
  assert.deepEqual(await handler({}, "swimmers"), { cancelled: true });
});

test("reference purposes allow CSV only", async () => {
  const selectedPath = path.resolve("fixtures", "colors.csv");
  const harness = createHarness({ canceled: false, filePaths: [selectedPath] });
  const handler = harness.handlers.get(DIALOG_CHANNELS.OPEN_INPUT_FILE);
  assert.deepEqual(await handler({}, "personality_colors"), { cancelled: false, path: selectedPath });
  assert.deepEqual(harness.calls[0][0].filters, [{ name: "CSV files", extensions: ["csv"] }]);

  const invalidHarness = createHarness({ canceled: false, filePaths: [path.resolve("colors.xlsx")] });
  await assert.rejects(
    invalidHarness.handlers.get(DIALOG_CHANNELS.OPEN_INPUT_FILE)({}, "personality_colors"),
    /invalid file selection/,
  );
});

test("rejects unexpected extensions, relative paths, and multiple selections", async () => {
  for (const result of [
    { canceled: false, filePaths: [path.resolve("notes.txt")] },
    { canceled: false, filePaths: ["classes.csv"] },
    { canceled: false, filePaths: [path.resolve("one.csv"), path.resolve("two.csv")] },
  ]) {
    const harness = createHarness(result);
    const handler = harness.handlers.get(DIALOG_CHANNELS.OPEN_INPUT_FILE);
    await assert.rejects(handler({}, "classes"), /invalid file selection/);
  }
});

test("validates registration dependencies", () => {
  const ipcMain = { handle() {}, removeHandler() {} };
  const dialog = { async showOpenDialog() {} };
  assert.throws(() => registerDialogHandlers({ ipcMain: {}, dialog }), /ipcMain/);
  assert.throws(() => registerDialogHandlers({ ipcMain, dialog: {} }), /dialog/);
  assert.throws(() => registerDialogHandlers({ ipcMain, dialog, getParentWindow: 1 }), /getParentWindow/);
});
