"use strict";

const assert = require("node:assert/strict");
const Module = require("node:module");
const path = require("node:path");
const test = require("node:test");

const { DIALOG_CHANNELS } = require("../ipc_contract.cjs");

test("preload exposes only a frozen dialog API and never exposes ipcRenderer", async () => {
  const invocations = [];
  let exposedName;
  let exposedApi;
  const electronMock = {
    contextBridge: {
      exposeInMainWorld(name, api) {
        exposedName = name;
        exposedApi = api;
      },
    },
    ipcRenderer: {
      async invoke(...args) {
        invocations.push(args);
        return { cancelled: false, path: path.resolve("fixtures", "classes.csv"), ignored: "value" };
      },
    },
  };

  const originalLoad = Module._load;
  Module._load = function loadWithElectronMock(request, parent, isMain) {
    if (request === "electron") return electronMock;
    return originalLoad.call(this, request, parent, isMain);
  };
  try {
    delete require.cache[require.resolve("../preload.cjs")];
    require("../preload.cjs");
  } finally {
    Module._load = originalLoad;
  }

  assert.equal(exposedName, "AquaDesktop");
  assert.deepEqual(Object.keys(exposedApi), ["dialogs"]);
  assert.deepEqual(Object.keys(exposedApi.dialogs), ["openInputFile"]);
  assert.equal(Object.isFrozen(exposedApi), true);
  assert.equal(Object.isFrozen(exposedApi.dialogs), true);
  assert.equal(exposedApi.ipcRenderer, undefined);

  const result = await exposedApi.dialogs.openInputFile("classes");
  assert.deepEqual(invocations, [[DIALOG_CHANNELS.OPEN_INPUT_FILE, "classes"]]);
  assert.deepEqual(result, { cancelled: false, path: path.resolve("fixtures", "classes.csv") });
  assert.equal(Object.isFrozen(result), true);
  assert.equal(result.ignored, undefined);
});

test("preload normalizes cancellation without returning a path", async () => {
  let exposedApi;
  const electronMock = {
    contextBridge: { exposeInMainWorld(_name, api) { exposedApi = api; } },
    ipcRenderer: { async invoke() { return { cancelled: true, path: "must-not-escape" }; } },
  };
  const originalLoad = Module._load;
  Module._load = function loadWithElectronMock(request, parent, isMain) {
    if (request === "electron") return electronMock;
    return originalLoad.call(this, request, parent, isMain);
  };
  try {
    delete require.cache[require.resolve("../preload.cjs")];
    require("../preload.cjs");
  } finally {
    Module._load = originalLoad;
  }

  assert.deepEqual(await exposedApi.dialogs.openInputFile("classes"), { cancelled: true });
});
