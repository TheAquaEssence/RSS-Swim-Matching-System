"use strict";

const path = require("node:path");
const { BackendProcessController, TOKEN_HEADER, redactText } = require("./backend-process.cjs");

function resolveUserDataOverride(environment = process.env) {
  // Automated packaged-app smoke runs point the shell at a disposable
  // directory instead of the real per-user profile. The override must be an
  // explicit absolute path; anything else is ignored so a stray or malformed
  // environment value can never redirect user data somewhere surprising.
  const override = environment.AQUA_USER_DATA;
  if (typeof override !== "string") return null;
  const trimmed = override.trim();
  if (trimmed === "" || !path.isAbsolute(trimmed)) return null;
  const resolved = path.resolve(trimmed);
  if (resolved === path.parse(resolved).root) return null;
  return resolved;
}

function isAllowedExternalUrl(rawUrl) {
  try {
    const url = new URL(rawUrl);
    return url.protocol === "https:"
      && url.hostname === "github.com"
      && url.port === ""
      && url.username === ""
      && url.password === ""
      && (
        url.pathname === "/TheAquaEssence/AquaEssence"
        || url.pathname.startsWith("/TheAquaEssence/AquaEssence/")
      );
  } catch {
    return false;
  }
}

function isSameOrigin(rawUrl, origin) {
  try {
    return new URL(rawUrl).origin === origin;
  } catch {
    return false;
  }
}

function addCapabilityHeader(details, callback, origin, launchToken) {
  if (!isSameOrigin(details.url, origin)) {
    callback({ requestHeaders: details.requestHeaders });
    return;
  }
  callback({
    requestHeaders: {
      ...details.requestHeaders,
      [TOKEN_HEADER]: launchToken,
    },
  });
}

function installNavigationPolicy(window, shell, origin) {
  window.webContents.setWindowOpenHandler(({ url }) => {
    if (!isSameOrigin(url, origin) && isAllowedExternalUrl(url)) {
      void shell.openExternal(url);
    }
    return { action: "deny" };
  });
  window.webContents.on("will-navigate", (event, url) => {
    if (isSameOrigin(url, origin)) return;
    event.preventDefault();
    if (isAllowedExternalUrl(url)) void shell.openExternal(url);
  });
}

function createDesktopRuntime(electron, options = {}) {
  const { app, BrowserWindow, dialog, session, shell } = electron;
  const repositoryRoot = path.resolve(options.repositoryRoot || path.join(__dirname, ".."));
  let backend = null;
  let mainWindow = null;
  let quitting = false;

  async function start() {
    backend = options.backend || new BackendProcessController({
      repositoryRoot,
      userDataPath: app.getPath("userData"),
      isPackaged: app.isPackaged,
      resourcesPath: options.resourcesPath || process.resourcesPath,
    });
    try {
      await backend.start();
    } catch (error) {
      const safeMessage = redactText(error?.message || "Unknown startup failure", [
        backend.launchToken,
        app.getPath("userData"),
        repositoryRoot,
      ]);
      dialog.showErrorBox(
        "Aqua Essence could not start",
        `${safeMessage}\n\n${app.isPackaged
          ? "Reinstall the application if its bundled backend files are missing or damaged."
          : "Check that the supported Python runtime and project dependencies are installed."}`,
      );
      quitting = true;
      app.exit(1);
      return null;
    }

    const origin = new URL(backend.baseUrl).origin;
    const registerDialogHandlers = options.registerDialogHandlers
      || require("./dialog_bridge.cjs").registerDialogHandlers;
    registerDialogHandlers({
      ipcMain: electron.ipcMain,
      dialog,
      getParentWindow: () => mainWindow,
    });
    const registerDownloadHandler = options.registerDownloadHandler
      || require("./download_bridge.cjs").registerDownloadHandler;
    registerDownloadHandler({
      session: session.defaultSession,
      dialog,
      downloadDirectory: app.getPath("downloads"),
      getParentWindow: () => mainWindow,
    });
    session.defaultSession.webRequest.onBeforeSendHeaders(
      { urls: [`${origin}/*`] },
      (details, callback) => addCapabilityHeader(details, callback, origin, backend.launchToken),
    );

    mainWindow = new BrowserWindow({
      width: 1440,
      height: 960,
      minWidth: 1000,
      minHeight: 700,
      show: false,
      backgroundColor: "#f4f7fb",
      webPreferences: {
        preload: path.join(__dirname, "preload.cjs"),
        nodeIntegration: false,
        contextIsolation: true,
        sandbox: true,
      },
    });
    installNavigationPolicy(mainWindow, shell, origin);
    mainWindow.on("closed", () => {
      mainWindow = null;
    });
    mainWindow.once("ready-to-show", () => mainWindow?.show());
    await mainWindow.loadURL(`${origin}/`);
    return mainWindow;
  }

  async function shutdownAndExit(exitCode = 0) {
    if (quitting) return;
    quitting = true;
    try {
      await backend?.stop();
    } finally {
      app.exit(exitCode);
    }
  }

  function registerLifecycle() {
    app.whenReady().then(start);
    app.on("before-quit", (event) => {
      if (quitting) return;
      event.preventDefault();
      void shutdownAndExit(0);
    });
    app.on("window-all-closed", () => void shutdownAndExit(0));
    app.on("activate", () => {
      if (!mainWindow && !quitting) void start();
    });
  }

  return { registerLifecycle, shutdownAndExit, start };
}

function bootstrap() {
  // Electron is loaded lazily so helper behavior can be tested with plain Node.
  const electron = require("electron");
  const userDataOverride = resolveUserDataOverride();
  if (userDataOverride) electron.app.setPath("userData", userDataOverride);
  const runtime = createDesktopRuntime(electron);
  runtime.registerLifecycle();
}

// Electron >=30 loads the entry file through the ESM translator, so
// `require.main === module` is false when running as the app entry. Detect the
// Electron main process directly; plain-Node test requires still skip bootstrap.
if (require.main === module || (process.versions.electron && process.type === "browser")) bootstrap();

module.exports = {
  addCapabilityHeader,
  resolveUserDataOverride,
  createDesktopRuntime,
  installNavigationPolicy,
  isAllowedExternalUrl,
  isSameOrigin,
};
