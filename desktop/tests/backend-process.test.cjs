"use strict";

const assert = require("node:assert/strict");
const { EventEmitter } = require("node:events");
const test = require("node:test");
const {
  BackendProcessController,
  TOKEN_ENV,
  TOKEN_HEADER,
  generateLaunchToken,
  redactText,
  resolveBackendCommand,
} = require("../backend-process.cjs");

class FakeChild extends EventEmitter {
  constructor() {
    super();
    this.stdout = new EventEmitter();
    this.stderr = new EventEmitter();
    this.exitCode = null;
    this.signalCode = null;
    this.kills = [];
  }

  kill(signal) {
    this.kills.push(signal);
    return true;
  }

  exit(code = 0, signal = null) {
    this.exitCode = code;
    this.signalCode = signal;
    this.emit("exit", code, signal);
  }
}

test("launch token is strong and redaction removes all occurrences", () => {
  const first = generateLaunchToken();
  const second = generateLaunchToken();
  assert.notEqual(first, second);
  assert.match(first, /^[A-Za-z0-9_-]{43}$/);
  assert.equal(redactText(`before ${first} middle ${first}`, [first]), "before [REDACTED] middle [REDACTED]");
});

test("source command resolution retains the configured Python and start.py contract", () => {
  const command = resolveBackendCommand({
    repositoryRoot: "C:/source/aqua",
    pythonExecutable: "C:/Python/python-test.exe",
    platform: "win32",
  });
  assert.equal(command.command, "C:/Python/python-test.exe");
  assert.deepEqual(command.prefixArgs, ["-u", "C:\\source\\aqua\\start.py"]);
  assert.equal(command.cwd, "C:\\source\\aqua");
});

test("packaged Windows command resolves the bundled executable without Python", () => {
  let checkedPath;
  const command = resolveBackendCommand({
    isPackaged: true,
    resourcesPath: "C:/Program Files/Aqua/resources",
    environment: { AQUA_PYTHON_EXECUTABLE: "must-not-be-used.exe" },
    platform: "win32",
    pathExists(candidate) {
      checkedPath = candidate;
      return true;
    },
  });
  assert.equal(checkedPath, "C:\\Program Files\\Aqua\\resources\\backend\\aqua-backend.exe");
  assert.equal(command.command, checkedPath);
  assert.deepEqual(command.prefixArgs, []);
  assert.equal(command.cwd, "C:\\Program Files\\Aqua\\resources\\backend");
});

test("missing packaged executable fails before port selection or spawn without exposing its path", async () => {
  let portSelected = false;
  let spawned = false;
  const resourcesPath = "C:/private/install/resources";
  const controller = new BackendProcessController({
    isPackaged: true,
    resourcesPath,
    userDataPath: "C:/private/user-data",
    platform: "win32",
    pathExists: () => false,
    portProvider: async () => {
      portSelected = true;
      return 45678;
    },
    spawn: () => {
      spawned = true;
      return new FakeChild();
    },
    fetch: async () => { throw new Error("not used"); },
  });
  await assert.rejects(controller.start(), (error) => {
    assert.match(error.message, /bundled backend executable is missing/i);
    assert.match(error.message, /resources\/backend directory/i);
    assert.equal(error.message.includes(resourcesPath), false);
    return true;
  });
  assert.equal(portSelected, false);
  assert.equal(spawned, false);
});

test("packaged backend receives userData and shuts down through the authenticated API", async () => {
  const child = new FakeChild();
  let spawnCall;
  const requests = [];
  const controller = new BackendProcessController({
    isPackaged: true,
    resourcesPath: "C:/Program Files/Aqua/resources",
    userDataPath: "C:/Users/Person/AppData/Roaming/Aqua",
    platform: "win32",
    pathExists: () => true,
    portProvider: async () => 45678,
    spawn(command, args, options) {
      spawnCall = { command, args, options };
      return child;
    },
    fetch: async (url, options = {}) => {
      requests.push({ url, options });
      if (url.endsWith("/api/shutdown")) queueMicrotask(() => child.exit(0));
      return { ok: true, json: async () => ({ ok: true, status: "ready" }) };
    },
  });

  await controller.start();
  await controller.stop();

  assert.equal(spawnCall.command, "C:\\Program Files\\Aqua\\resources\\backend\\aqua-backend.exe");
  assert.deepEqual(spawnCall.args, [
    "--port", "45678", "--no-browser", "--data-dir",
    "C:\\Users\\Person\\AppData\\Roaming\\Aqua",
  ]);
  assert.equal(spawnCall.options.env.AQUA_APP_DATA_DIR, "C:\\Users\\Person\\AppData\\Roaming\\Aqua");
  assert.equal(spawnCall.options.env[TOKEN_ENV], controller.launchToken);
  assert.equal(spawnCall.command.includes("python"), false);
  const shutdown = requests.find(({ url }) => url.endsWith("/api/shutdown"));
  assert.equal(shutdown.options.headers[TOKEN_HEADER], controller.launchToken);
  assert.equal(shutdown.url.includes(controller.launchToken), false);
});

test("backend starts on loopback with token only in child environment", async () => {
  const child = new FakeChild();
  let spawnCall;
  const requests = [];
  const controller = new BackendProcessController({
    repositoryRoot: "C:/source/aqua",
    userDataPath: "C:/private/user-data",
    pythonExecutable: "python-test",
    environment: { SAFE_PARENT_VALUE: "yes" },
    portProvider: async () => 45678,
    spawn(command, args, options) {
      spawnCall = { command, args, options };
      return child;
    },
    fetch: async (url, options = {}) => {
      requests.push({ url, options });
      return { ok: true, json: async () => ({ ok: true, status: "ready" }) };
    },
  });

  await controller.start();
  assert.equal(controller.baseUrl, "http://127.0.0.1:45678");
  assert.equal(spawnCall.command, "python-test");
  assert.deepEqual(spawnCall.args.slice(-5), [
    "--port", "45678", "--no-browser", "--data-dir", "C:\\private\\user-data",
  ]);
  assert.equal(spawnCall.options.cwd, "C:\\source\\aqua");
  assert.equal(spawnCall.options.detached, false);
  assert.equal(spawnCall.options.env.AQUA_APP_DATA_DIR, "C:\\private\\user-data");
  assert.equal(spawnCall.options.env[TOKEN_ENV], controller.launchToken);
  assert.equal(spawnCall.args.join(" ").includes(controller.launchToken), false);
  assert.equal(requests[0].url, "http://127.0.0.1:45678/api/ready");
  assert.equal(requests[0].options.headers, undefined);
});

test("graceful shutdown authenticates with a header and waits for exit", async () => {
  const child = new FakeChild();
  const requests = [];
  const controller = new BackendProcessController({
    repositoryRoot: "/source/aqua",
    userDataPath: "/private/user-data",
    portProvider: async () => 34567,
    spawn: () => child,
    fetch: async (url, options = {}) => {
      requests.push({ url, options });
      if (url.endsWith("/api/shutdown")) queueMicrotask(() => child.exit(0));
      return { ok: true, json: async () => ({ ok: true, status: "ready" }) };
    },
  });
  await controller.start();
  await controller.stop();

  const shutdown = requests.find(({ url }) => url.endsWith("/api/shutdown"));
  assert.equal(shutdown.options.method, "POST");
  assert.equal(shutdown.options.headers[TOKEN_HEADER], controller.launchToken);
  assert.equal(shutdown.url.includes(controller.launchToken), false);
  assert.deepEqual(child.kills, []);
});

test("shutdown escalates from terminate to kill on bounded deadlines", async () => {
  const child = new FakeChild();
  child.kill = function kill(signal) {
    this.kills.push(signal);
    if (signal === "SIGKILL") queueMicrotask(() => this.exit(null, signal));
    return true;
  };
  const controller = new BackendProcessController({
    repositoryRoot: "/source/aqua",
    userDataPath: "/private/user-data",
    portProvider: async () => 34567,
    spawn: () => child,
    fetch: async (url) => {
      if (url.endsWith("/api/shutdown")) throw new Error("host unavailable");
      return { ok: true, json: async () => ({ ok: true, status: "ready" }) };
    },
    shutdownTimeoutMs: 5,
    terminateTimeoutMs: 5,
  });
  await controller.start();
  await controller.stop();
  assert.deepEqual(child.kills, ["SIGTERM", "SIGKILL"]);
});

test("startup diagnostics redact the token and application paths", async () => {
  const child = new FakeChild();
  const controller = new BackendProcessController({
    repositoryRoot: "/source/aqua",
    userDataPath: "/private/user-data",
    portProvider: async () => 34567,
    spawn: () => {
      queueMicrotask(() => {
        child.stderr.emit("data", `${controller.userDataPath} ${controller.launchToken} ${controller.repositoryRoot}`);
        child.exit(2);
      });
      return child;
    },
    fetch: async () => { throw new Error("unavailable"); },
  });
  await assert.rejects(controller.start(), (error) => {
    assert.equal(error.message.includes(controller.launchToken), false);
    assert.equal(error.message.includes("/private/user-data"), false);
    assert.equal(error.message.includes("/source/aqua"), false);
    assert.match(error.message, /\[REDACTED\]/);
    return true;
  });
});

test("an executable launch error becomes a bounded startup error", async () => {
  const child = new FakeChild();
  const controller = new BackendProcessController({
    repositoryRoot: "/source/aqua",
    userDataPath: "/private/user-data",
    portProvider: async () => 34567,
    spawn: () => {
      queueMicrotask(() => child.emit("error", new Error("executable not found")));
      return child;
    },
    fetch: async () => { throw new Error("unavailable"); },
  });
  await assert.rejects(controller.start(), /could not be launched/);
});
