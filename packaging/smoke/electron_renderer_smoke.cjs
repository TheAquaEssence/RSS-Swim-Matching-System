"use strict";

// Drives the real packaged Electron renderer through the critical operator
// workflow. Playwright Core contributes no browser binary; Electron's bundled
// Chromium is the browser under test.

const fs = require("node:fs");
const path = require("node:path");
const { createRequire } = require("node:module");

const repositoryRoot = path.resolve(__dirname, "../..");
const requireFromDesktop = createRequire(path.join(repositoryRoot, "desktop", "package.json"));
const { _electron: electron } = requireFromDesktop("playwright-core");

const REPORT_PREFIX = "AQUA_RENDERER_REPORT=";
const DEFAULT_TIMEOUT_MS = 120_000;

function requireFile(filePath, label) {
  if (!path.isAbsolute(filePath) || !fs.statSync(filePath, { throwIfNoEntry: false })?.isFile()) {
    throw new Error(`${label} is missing: ${filePath}`);
  }
}

async function waitForDownloadedFile(filePath) {
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    const stat = fs.statSync(filePath, { throwIfNoEntry: false });
    if (stat?.isFile() && stat.size > 0) return stat.size;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`export was not written: ${filePath}`);
}

async function captureRendererExport(page, buttonSelector) {
  return await page.evaluate(async (selector) => {
    let captured = null;
    const originalClick = HTMLAnchorElement.prototype.click;
    HTMLAnchorElement.prototype.click = function captureClick() {
      captured = { url: this.href, suggestedName: this.download || "" };
    };
    try {
      document.querySelector(selector)?.click();
    } finally {
      HTMLAnchorElement.prototype.click = originalClick;
    }
    if (!captured?.url) throw new Error(`export button did not create a download: ${selector}`);
    const response = await fetch(captured.url, { cache: "no-store" });
    if (!response.ok) throw new Error(`export fetch failed with HTTP ${response.status}`);
    const bytes = Array.from(new Uint8Array(await response.arrayBuffer()));
    return {
      ...captured,
      bytes,
      contentType: response.headers.get("content-type") || "",
    };
  }, buttonSelector);
}

async function runRendererSmoke({ executablePath, userDataPath, artifactsPath }) {
  requireFile(executablePath, "packaged Electron executable");
  fs.mkdirSync(userDataPath, { recursive: true });
  fs.mkdirSync(artifactsPath, { recursive: true });

  const resources = path.join(path.dirname(executablePath), "resources");
  const demoDirectory = path.join(
    resources,
    "backend",
    "_internal",
    "examples",
    "demo",
    "matching",
  );
  const classesPath = path.join(demoDirectory, "classes.csv");
  const instructorsPath = path.join(demoDirectory, "instructors.csv");
  requireFile(classesPath, "bundled demo classes");
  requireFile(instructorsPath, "bundled demo instructors");

  const pdfPath = path.join(artifactsPath, "matching_report.pdf");
  const csvPath = path.join(artifactsPath, "classes_filled.csv");
  const report = {
    steps: [],
    matchCount: 0,
    assignedCount: 0,
    themes: {},
    exportBytes: {},
  };
  const record = (step) => {
    report.steps.push(step);
    process.stdout.write(`renderer-smoke: ok — ${step}\n`);
  };
  const pageErrors = [];
  let electronApplication = null;
  let page = null;

  try {
    electronApplication = await electron.launch({
      executablePath,
      cwd: path.dirname(executablePath),
      env: { ...process.env, AQUA_USER_DATA: userDataPath },
      timeout: DEFAULT_TIMEOUT_MS,
    });
    page = await electronApplication.firstWindow({ timeout: DEFAULT_TIMEOUT_MS });
    page.setDefaultTimeout(DEFAULT_TIMEOUT_MS);
    page.on("pageerror", (error) => pageErrors.push(String(error?.stack || error)));

    await page.locator("#hostStatusText").waitFor({ state: "visible" });
    await page.waitForFunction(
      () => document.getElementById("hostStatusText")?.textContent?.includes("online"),
    );
    report.themes.matching = await page.locator("html").getAttribute("data-theme") || "dark";
    record("packaged renderer reached Host: online");

    const desktopBridgeProbe = await page.evaluate(async () => {
      const openInputFile = window.AquaDesktop?.dialogs?.openInputFile;
      if (typeof openInputFile !== "function") {
        return { available: false, handlerResponded: false };
      }
      try {
        await openInputFile("__renderer_smoke_probe__");
        return { available: true, handlerResponded: false };
      } catch (error) {
        return {
          available: true,
          handlerResponded: String(error).includes("Unsupported input-file purpose"),
        };
      }
    });
    if (!desktopBridgeProbe.available || !desktopBridgeProbe.handlerResponded) {
      throw new Error("native input-file dialog bridge or IPC handler is unavailable");
    }
    record("native input-file dialog bridge and IPC handler responded");

    const selectionResult = await page.evaluate(async (selectedPath) => {
      const response = await fetch("/api/pick_file", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ purpose: "classes", selected_path: selectedPath }),
        cache: "no-store",
      });
      return { status: response.status, body: await response.json().catch(() => ({})) };
    }, classesPath);
    if (selectionResult.status !== 200 || selectionResult.body?.ok !== true) {
      throw new Error(`class selection failed: ${JSON.stringify(selectionResult)}`);
    }
    await page.reload({ waitUntil: "domcontentloaded" });
    await page.waitForFunction(
      () => !document.getElementById("generateButton")?.disabled
        && document.getElementById("classesFileMeta")?.textContent?.includes("classes.csv"),
    );
    record("authenticated renderer selection populated the input settings");

    await page.locator("#generateButton").click();
    await page.locator("#results-section").waitFor({ state: "visible" });
    await page.waitForFunction(() => document.querySelectorAll("#results-body tr").length > 0);
    report.matchCount = await page.locator("#results-body tr").count();
    const summaryValues = await page.locator("#results-summary .stat-value").allTextContents();
    report.assignedCount = Number(summaryValues[0]);
    if (!(report.matchCount > 0) || !(report.assignedCount > 0)) {
      throw new Error(`generation produced invalid renderer counts: ${JSON.stringify(summaryValues)}`);
    }
    await page.screenshot({ path: path.join(artifactsPath, "matching-results.png"), fullPage: true });
    record(`generated and rendered ${report.matchCount} match row(s)`);

    await page.locator("#results-body tr").first().click();
    await page.locator("#profile-drawer.open").waitFor({ state: "visible" });
    const drawerText = (await page.locator("#drawer-content").innerText()).trim();
    if (!drawerText) throw new Error("match review drawer opened without content");
    await page.locator("#drawer-close").click();
    record("opened a rendered match review and profile detail");

    await page.locator("#explainabilityNavLink").click();
    await page.waitForURL(/\/xai\/$/);
    await page.waitForFunction(
      () => document.getElementById("stat-assigned")?.textContent?.trim() !== "—",
    );
    report.themes.explainability = await page.locator("html").getAttribute("data-theme") || "dark";
    if (report.themes.explainability !== report.themes.matching) {
      throw new Error(
        `theme changed between Matching and Explainability: ${JSON.stringify(report.themes)}`,
      );
    }
    const xaiAssigned = Number((await page.locator("#stat-assigned").innerText()).trim());
    if (!(xaiAssigned > 0)) throw new Error(`XAI assigned count is invalid: ${xaiAssigned}`);
    await page.locator('.tab[data-view="explorer"]').click();
    await page.locator("#explorer-table tbody tr").first().waitFor({ state: "visible" });
    await page.screenshot({ path: path.join(artifactsPath, "xai-explorer.png"), fullPage: true });
    record(`loaded XAI overview and Match Explorer in shared ${report.themes.matching} theme`);

    await page.getByRole("link", { name: "Matching", exact: true }).click();
    await page.waitForURL((url) => url.pathname === "/");
    await page.locator("#results-section").waitFor({ state: "visible" });

    await page.locator("#advancedSection > summary").click();
    await page.locator("#manageInstructorsButton").click();
    await page.locator("#instructor-editor-modal").waitFor({ state: "visible" });
    const previewResponsePromise = page.waitForResponse(
      (response) => response.url().includes("/api/instructors/import/preview")
        && response.request().method() === "POST",
    );
    await page.locator("#instructor-import-file-input").setInputFiles(instructorsPath);
    const previewResponse = await previewResponsePromise;
    if (!previewResponse.ok()) {
      throw new Error(`renderer import preview failed with HTTP ${previewResponse.status()}`);
    }
    const preview = await previewResponse.json();
    if (preview?.ok !== true) throw new Error("renderer import preview returned a failed payload");
    await page.screenshot({ path: path.join(artifactsPath, "instructor-import.png"), fullPage: true });
    record("submitted instructor CSV through the renderer import-preview workflow");
    if (await page.locator("#instructor-import-review-modal").getAttribute("open") !== null) {
      await page.locator("#instructor-import-review-cancel").click();
    }
    await page.locator("#instructor-editor-close").click();

    const pdfExport = await captureRendererExport(page, "#reopenPdfButton");
    fs.writeFileSync(pdfPath, Buffer.from(pdfExport.bytes));
    report.exportBytes.pdf = await waitForDownloadedFile(pdfPath);
    if (!fs.readFileSync(pdfPath).subarray(0, 5).equals(Buffer.from("%PDF-"))) {
      throw new Error("renderer PDF export does not have a PDF signature");
    }
    const csvExport = await captureRendererExport(page, "#downloadFilledClassesButton");
    fs.writeFileSync(csvPath, Buffer.from(csvExport.bytes));
    report.exportBytes.csv = await waitForDownloadedFile(csvPath);
    if (!fs.readFileSync(csvPath, "utf8").includes("class_id")) {
      throw new Error("renderer CSV export does not contain the expected header");
    }
    record("resolved and fetched authenticated PDF and CSV exports from renderer controls");

    if (pageErrors.length) {
      throw new Error(`renderer page error(s): ${pageErrors.join("\n")}`);
    }
    return report;
  } catch (error) {
    if (page) {
      await page.screenshot({
        path: path.join(artifactsPath, "failure.png"),
        fullPage: true,
      }).catch(() => {});
    }
    throw error;
  } finally {
    if (electronApplication) await electronApplication.close().catch(() => {});
  }
}

async function main() {
  const rawArguments = process.argv.slice(2);
  if (rawArguments.length !== 3 || rawArguments.some((value) => !value)) {
    throw new Error(
      "usage: node electron_renderer_smoke.cjs <Aqua Essence.exe> <user-data-dir> <artifacts-dir>",
    );
  }
  const [executablePath, userDataPath, artifactsPath] = rawArguments.map((value) =>
    path.resolve(value));
  const report = await runRendererSmoke({ executablePath, userDataPath, artifactsPath });
  process.stdout.write(`${REPORT_PREFIX}${JSON.stringify(report)}\n`);
}

if (require.main === module) {
  main().catch((error) => {
    process.stderr.write(`renderer-smoke: FAILED — ${error?.stack || error}\n`);
    process.exitCode = 1;
  });
}

module.exports = {
  REPORT_PREFIX,
  captureRendererExport,
  runRendererSmoke,
  waitForDownloadedFile,
};
