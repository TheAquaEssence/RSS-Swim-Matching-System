"use strict";

const assert = require("node:assert/strict");
const { EventEmitter } = require("node:events");
const test = require("node:test");
const path = require("node:path");
const {
  addCapabilityHeader,
  createDesktopRuntime,
  installNavigationPolicy,
  isAllowedExternalUrl,
  isSameOrigin,
  resolveUserDataOverride,
} = require("../main.cjs");

test("user-data override accepts only explicit absolute non-root paths", () => {
  const absolute = path.join(__dirname, "smoke-user-data");
  assert.equal(resolveUserDataOverride({ AQUA_USER_DATA: absolute }), path.resolve(absolute));
  assert.equal(resolveUserDataOverride({ AQUA_USER_DATA: `  ${absolute}  ` }), path.resolve(absolute));
  assert.equal(resolveUserDataOverride({}), null);
  assert.equal(resolveUserDataOverride({ AQUA_USER_DATA: "" }), null);
  assert.equal(resolveUserDataOverride({ AQUA_USER_DATA: "   " }), null);
  assert.equal(resolveUserDataOverride({ AQUA_USER_DATA: "relative/dir" }), null);
  const root = path.parse(path.resolve(__dirname)).root;
  assert.equal(resolveUserDataOverride({ AQUA_USER_DATA: root }), null);
});

test("URL policy accepts only allowlisted repository links and exact backend origin", () => {
  assert.equal(isAllowedExternalUrl("https://github.com/TheAquaEssence/AquaEssence"), true);
  assert.equal(isAllowedExternalUrl("https://github.com/TheAquaEssence/AquaEssence/issues/1"), true);
  assert.equal(isAllowedExternalUrl("https://example.org/help"), false);
  assert.equal(isAllowedExternalUrl("http://github.com/TheAquaEssence/AquaEssence"), false);
  assert.equal(isAllowedExternalUrl("https://github.com/TheAquaEssence/AquaEssence-evil"), false);
  assert.equal(isAllowedExternalUrl("https://github.com@evil.test/TheAquaEssence/AquaEssence"), false);
  assert.equal(isAllowedExternalUrl("file:///private/data"), false);
  assert.equal(isAllowedExternalUrl("javascript:alert(1)"), false);
  assert.equal(isSameOrigin("http://127.0.0.1:8787/api/settings", "http://127.0.0.1:8787"), true);
  assert.equal(isSameOrigin("http://127.0.0.1:8788/", "http://127.0.0.1:8787"), false);
  assert.equal(isSameOrigin("http://127.0.0.1:8787.evil.test/", "http://127.0.0.1:8787"), false);
});

test("capability header is injected only for exact same-origin requests", () => {
  let result;
  addCapabilityHeader(
    { url: "http://127.0.0.1:8787/api/settings", requestHeaders: { Accept: "application/json" } },
    (value) => { result = value; },
    "http://127.0.0.1:8787",
    "secret-token",
  );
  assert.equal(result.requestHeaders["X-Aqua-Launch-Token"], "secret-token");

  addCapabilityHeader(
    { url: "https://example.org/", requestHeaders: { Accept: "text/html" } },
    (value) => { result = value; },
    "http://127.0.0.1:8787",
    "secret-token",
  );
  assert.equal(result.requestHeaders["X-Aqua-Launch-Token"], undefined);
});

test("navigation policy denies new windows and sends validated external URLs to the OS", async () => {
  const webContents = new EventEmitter();
  let windowHandler;
  webContents.setWindowOpenHandler = (handler) => { windowHandler = handler; };
  const opened = [];
  installNavigationPolicy({ webContents }, { openExternal: async (url) => opened.push(url) }, "http://127.0.0.1:8787");

  assert.deepEqual(windowHandler({ url: "https://github.com/TheAquaEssence/AquaEssence/issues" }), { action: "deny" });
  assert.deepEqual(windowHandler({ url: "https://example.org/help" }), { action: "deny" });
  assert.deepEqual(windowHandler({ url: "file:///private/data" }), { action: "deny" });
  let prevented = false;
  let sameOriginPrevented = false;
  webContents.emit(
    "will-navigate",
    { preventDefault: () => { sameOriginPrevented = true; } },
    "http://127.0.0.1:8787/xai/",
  );
  webContents.emit("will-navigate", { preventDefault: () => { prevented = true; } }, "https://example.org/docs");
  webContents.emit("will-navigate", { preventDefault: () => { prevented = true; } }, "https://github.com/TheAquaEssence/AquaEssence");
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(prevented, true);
  assert.equal(sameOriginPrevented, false);
  assert.deepEqual(opened, [
    "https://github.com/TheAquaEssence/AquaEssence/issues",
    "https://github.com/TheAquaEssence/AquaEssence",
  ]);
});

test("runtime waits for backend readiness before creating a hardened window", async () => {
  const order = [];
  const backend = {
    baseUrl: "http://127.0.0.1:45678",
    launchToken: "launch-secret",
    async start() { order.push("backend-ready"); },
    async stop() { order.push("backend-stopped"); },
  };
  class FakeWindow extends EventEmitter {
    constructor(options) {
      super();
      order.push("window-created");
      this.options = options;
      this.webContents = new EventEmitter();
      this.webContents.setWindowOpenHandler = () => {};
      FakeWindow.instance = this;
    }
    async loadURL(url) { this.url = url; order.push("url-loaded"); }
    show() { order.push("window-shown"); }
  }
  const electron = {
    app: {
      getPath: (name) => name === "downloads" ? "/downloads" : "/user-data",
      exit: (code) => order.push(`exit-${code}`),
    },
    BrowserWindow: FakeWindow,
    dialog: { showErrorBox() {} },
    ipcMain: {},
    session: { defaultSession: { webRequest: { onBeforeSendHeaders: () => order.push("auth-installed") } } },
    shell: { openExternal: async () => {} },
  };
  const runtime = createDesktopRuntime(electron, {
    backend,
    repositoryRoot: "/source",
    registerDialogHandlers: () => order.push("dialogs-installed"),
    registerDownloadHandler: () => order.push("downloads-installed"),
  });
  await runtime.start();

  assert.ok(order.indexOf("backend-ready") < order.indexOf("window-created"));
  assert.equal(FakeWindow.instance.url, "http://127.0.0.1:45678/");
  assert.deepEqual(FakeWindow.instance.options.webPreferences, {
    preload: require("node:path").join(__dirname, "..", "preload.cjs"),
    nodeIntegration: false,
    contextIsolation: true,
    sandbox: true,
  });
  FakeWindow.instance.emit("ready-to-show");
  assert.equal(order.at(-1), "window-shown");
  await runtime.shutdownAndExit();
  assert.deepEqual(order.slice(-2), ["backend-stopped", "exit-0"]);
});
