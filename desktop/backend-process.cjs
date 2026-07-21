"use strict";

const { spawn: defaultSpawn } = require("node:child_process");
const crypto = require("node:crypto");
const fs = require("node:fs");
const net = require("node:net");
const path = require("node:path");

const LOOPBACK_HOST = "127.0.0.1";
const TOKEN_ENV = "AQUA_LAUNCH_TOKEN";
const TOKEN_HEADER = "X-Aqua-Launch-Token";
const DEFAULT_STARTUP_TIMEOUT_MS = 30_000;
const DEFAULT_SHUTDOWN_TIMEOUT_MS = 12_000;
const DEFAULT_TERMINATE_TIMEOUT_MS = 2_000;
const MAX_DIAGNOSTIC_CHARS = 12_000;

class BackendStartError extends Error {
  constructor(message, diagnostics = "") {
    super(diagnostics ? `${message}\n\nBackend diagnostics:\n${diagnostics}` : message);
    this.name = "BackendStartError";
    this.diagnostics = diagnostics;
  }
}

function generateLaunchToken() {
  return crypto.randomBytes(32).toString("base64url");
}

function reserveLoopbackPort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.once("error", reject);
    server.listen(0, LOOPBACK_HOST, () => {
      const address = server.address();
      const port = address && typeof address === "object" ? address.port : null;
      server.close((error) => {
        if (error) reject(error);
        else if (port === null) reject(new Error("Could not reserve a loopback port"));
        else resolve(port);
      });
    });
  });
}

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function withTimeout(promise, milliseconds) {
  let timer;
  return Promise.race([
    promise,
    new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error("Timed out")), milliseconds);
    }),
  ]).finally(() => clearTimeout(timer));
}

function waitForExit(child) {
  if (child.exitCode !== null || child.signalCode !== null) {
    return Promise.resolve({ code: child.exitCode, signal: child.signalCode });
  }
  return new Promise((resolve) => {
    child.once("exit", (code, signal) => resolve({ code, signal }));
  });
}

function redactText(value, secrets) {
  let redacted = String(value || "");
  for (const secret of secrets) {
    if (secret) redacted = redacted.split(String(secret)).join("[REDACTED]");
  }
  return redacted;
}

function defaultPythonExecutable(environment = process.env, platform = process.platform) {
  if (environment.AQUA_PYTHON_EXECUTABLE) return environment.AQUA_PYTHON_EXECUTABLE;
  return platform === "win32" ? "python.exe" : "python3";
}

function resolveBackendCommand(options = {}) {
  const environment = options.environment || process.env;
  const platform = options.platform || process.platform;
  if (options.isPackaged) {
    if (!options.resourcesPath) {
      throw new BackendStartError(
        "The packaged backend location is unavailable.",
        "Electron did not provide its application resources directory.",
      );
    }
    const executableName = platform === "win32" ? "aqua-backend.exe" : "aqua-backend";
    const command = path.resolve(options.resourcesPath, "backend", executableName);
    const pathExists = options.pathExists || fs.existsSync;
    if (!pathExists(command)) {
      throw new BackendStartError(
        "The bundled backend executable is missing.",
        `Expected ${executableName} in the application's resources/backend directory. Reinstall the application.`,
      );
    }
    return { command, prefixArgs: [], cwd: path.dirname(command) };
  }

  if (!options.repositoryRoot) {
    throw new TypeError("repositoryRoot is required in source mode");
  }
  const repositoryRoot = path.resolve(options.repositoryRoot);
  return {
    command: options.pythonExecutable || defaultPythonExecutable(environment, platform),
    prefixArgs: ["-u", path.join(repositoryRoot, "start.py")],
    cwd: repositoryRoot,
  };
}

class BackendProcessController {
  constructor(options) {
    if (!options || !options.userDataPath || (!options.isPackaged && !options.repositoryRoot)) {
      throw new TypeError("userDataPath and a source repositoryRoot are required");
    }
    this.repositoryRoot = options.repositoryRoot ? path.resolve(options.repositoryRoot) : null;
    this.userDataPath = path.resolve(options.userDataPath);
    this.pythonExecutable = options.pythonExecutable || defaultPythonExecutable(options.environment);
    this.isPackaged = Boolean(options.isPackaged);
    this.resourcesPath = options.resourcesPath;
    this.platform = options.platform || process.platform;
    this.pathExists = options.pathExists || fs.existsSync;
    this.commandResolver = options.commandResolver || resolveBackendCommand;
    this.environment = options.environment || process.env;
    this.spawn = options.spawn || defaultSpawn;
    this.fetch = options.fetch || globalThis.fetch;
    this.portProvider = options.portProvider || reserveLoopbackPort;
    this.startupTimeoutMs = options.startupTimeoutMs || DEFAULT_STARTUP_TIMEOUT_MS;
    this.shutdownTimeoutMs = options.shutdownTimeoutMs || DEFAULT_SHUTDOWN_TIMEOUT_MS;
    this.terminateTimeoutMs = options.terminateTimeoutMs || DEFAULT_TERMINATE_TIMEOUT_MS;
    this.child = null;
    this.port = null;
    this.baseUrl = null;
    this.launchToken = null;
    this.output = "";
    this._spawnError = null;
    this._stopPromise = null;
    this.launchCommand = null;
  }

  _recordOutput(chunk) {
    this.output = (this.output + String(chunk)).slice(-MAX_DIAGNOSTIC_CHARS);
  }

  _diagnostics() {
    const output = redactText(this.output, [
      this.launchToken,
      this.userDataPath,
      this.repositoryRoot,
      this.resourcesPath,
      this.launchCommand?.command,
      this.launchCommand?.cwd,
    ]);
    return output.trim() || "No backend output was captured.";
  }

  async start() {
    if (this.child && this.child.exitCode === null && this.child.signalCode === null) {
      throw new Error("Backend is already running");
    }
    if (typeof this.fetch !== "function") {
      throw new Error("A Fetch API implementation is required");
    }

    this.output = "";
    this._spawnError = null;
    this.launchCommand = this.commandResolver({
      isPackaged: this.isPackaged,
      resourcesPath: this.resourcesPath,
      repositoryRoot: this.repositoryRoot,
      pythonExecutable: this.pythonExecutable,
      environment: this.environment,
      platform: this.platform,
      pathExists: this.pathExists,
    });
    this.port = await this.portProvider();
    this.baseUrl = `http://${LOOPBACK_HOST}:${this.port}`;
    this.launchToken = generateLaunchToken();
    const environment = {
      ...this.environment,
      AQUA_APP_DATA_DIR: this.userDataPath,
      [TOKEN_ENV]: this.launchToken,
      PYTHONDONTWRITEBYTECODE: "1",
    };
    const args = [
      ...this.launchCommand.prefixArgs,
      "--port",
      String(this.port),
      "--no-browser",
      "--data-dir",
      this.userDataPath,
    ];

    this.child = this.spawn(this.launchCommand.command, args, {
      cwd: this.launchCommand.cwd,
      env: environment,
      detached: false,
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
    });
    this.child.stdout?.on("data", (chunk) => this._recordOutput(chunk));
    this.child.stderr?.on("data", (chunk) => this._recordOutput(chunk));
    this.child.once("error", (error) => {
      this._spawnError = error;
      this._recordOutput(error?.message || "The backend process could not be launched.");
    });

    const deadline = Date.now() + this.startupTimeoutMs;
    while (Date.now() < deadline) {
      if (this._spawnError) {
        throw new BackendStartError("The local backend process could not be launched.", this._diagnostics());
      }
      if (this.child.exitCode !== null || this.child.signalCode !== null) {
        throw new BackendStartError(
          `The local backend exited before it became ready (exit code ${this.child.exitCode ?? "unknown"}).`,
          this._diagnostics(),
        );
      }
      try {
        const response = await this.fetch(`${this.baseUrl}/api/ready`, {
          cache: "no-store",
          signal: AbortSignal.timeout(750),
        });
        if (response.ok) {
          const payload = await response.json();
          if (payload && payload.ok === true && payload.status === "ready") return this;
        }
      } catch {
        // Connection failures are expected while uvicorn is starting.
      }
      await delay(75);
    }

    await this._terminateBounded();
    throw new BackendStartError(
      "The local backend did not become ready before the startup timeout.",
      this._diagnostics(),
    );
  }

  async stop() {
    if (this._stopPromise) return this._stopPromise;
    this._stopPromise = this._stop().finally(() => {
      this._stopPromise = null;
    });
    return this._stopPromise;
  }

  async _stop() {
    const child = this.child;
    if (!child || child.exitCode !== null || child.signalCode !== null) return;
    try {
      await this.fetch(`${this.baseUrl}/api/shutdown`, {
        method: "POST",
        headers: { [TOKEN_HEADER]: this.launchToken },
        signal: AbortSignal.timeout(2_000),
      });
    } catch {
      // The host may close the connection while processing shutdown.
    }
    try {
      await withTimeout(waitForExit(child), this.shutdownTimeoutMs);
    } catch {
      await this._terminateBounded();
    }
  }

  async _terminateBounded() {
    const child = this.child;
    if (!child || child.exitCode !== null || child.signalCode !== null) return;
    try {
      child.kill("SIGTERM");
    } catch {
      return;
    }
    try {
      await withTimeout(waitForExit(child), this.terminateTimeoutMs);
    } catch {
      try {
        child.kill("SIGKILL");
      } catch {
        return;
      }
      try {
        await withTimeout(waitForExit(child), this.terminateTimeoutMs);
      } catch {
        // There is no stronger portable action available to the parent process.
      }
    }
  }
}

module.exports = {
  BackendProcessController,
  BackendStartError,
  LOOPBACK_HOST,
  TOKEN_ENV,
  TOKEN_HEADER,
  defaultPythonExecutable,
  generateLaunchToken,
  redactText,
  resolveBackendCommand,
  reserveLoopbackPort,
};
