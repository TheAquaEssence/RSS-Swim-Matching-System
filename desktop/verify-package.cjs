"use strict";

const fs = require("node:fs");
const path = require("node:path");

const unpacked = path.resolve(process.argv[2] || path.join(__dirname, "..", ".dist", "electron", "win-unpacked"));
const resources = path.join(unpacked, "resources");

const required = [
  "Aqua Essence.exe",
  "LICENSE.electron.txt",
  "LICENSES.chromium.html",
  path.join("resources", "app.asar"),
  path.join("resources", "backend", "aqua-backend.exe"),
  path.join("resources", "LICENSE.aqua-essence.txt"),
  path.join("resources", "THIRD_PARTY_NOTICES.md"),
  path.join("resources", "SBOM.cdx.json"),
  path.join("resources", "licenses", "python-runtime", "LICENSE.txt"),
];

const forbiddenSegments = new Set([
  ".git",
  ".pytest_cache",
  "__pycache__",
  "app_samples",
  "generated",
  "jobs",
  "logs",
  "settings",
  "tests",
]);
const forbiddenNames = new Set(["aqua_essence.db"]);
const forbiddenOperationalFiles = new Set([
  path.join("_internal", "data", "source", "instructors.csv"),
  path.join("_internal", "data", "source", "pairings.csv"),
]);

function walk(directory, relative = "") {
  const results = [];
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const childRelative = path.join(relative, entry.name);
    results.push(childRelative);
    if (entry.isDirectory()) results.push(...walk(path.join(directory, entry.name), childRelative));
  }
  return results;
}

const missing = required.filter((item) => !fs.existsSync(path.join(unpacked, item)));
if (missing.length) throw new Error(`Packaged application is missing: ${missing.join(", ")}`);

const backend = path.join(resources, "backend");
const forbidden = walk(backend).filter((item) => {
  const segments = item.split(path.sep);
  return segments.some((segment) => forbiddenSegments.has(segment)) ||
    forbiddenNames.has(path.basename(item)) || forbiddenOperationalFiles.has(item);
});
if (forbidden.length) throw new Error(`Forbidden packaged paths: ${forbidden.join(", ")}`);

const electronLicense = fs.readFileSync(path.join(unpacked, "LICENSE.electron.txt"), "utf8");
if (!electronLicense.includes("Copyright (c) Electron contributors")) {
  throw new Error("Electron's version-matched license was not found in the package");
}
const chromiumNotices = fs.statSync(path.join(unpacked, "LICENSES.chromium.html"));
if (chromiumNotices.size < 100_000) throw new Error("Chromium notices file is unexpectedly small");

const sbom = JSON.parse(fs.readFileSync(path.join(resources, "SBOM.cdx.json"), "utf8"));
if (sbom.bomFormat !== "CycloneDX" || sbom.specVersion !== "1.6") {
  throw new Error("Packaged SBOM is not CycloneDX 1.6");
}
const pythonComponents = sbom.components.filter((component) =>
  component.properties?.some((property) => property.name === "aqua:boundary" &&
    property.value.startsWith("Python"))
);
for (const component of pythonComponents) {
  const licensePointers = component.properties.filter((item) => item.name === "aqua:license-file");
  if (!licensePointers.length) throw new Error(`SBOM component lacks a license file: ${component.name}`);
  for (const property of licensePointers) {
    if (!fs.existsSync(path.join(resources, property.value))) {
      throw new Error(`SBOM license file is missing: ${property.value}`);
    }
  }
}
if (pythonComponents.length < 31) throw new Error("Packaged SBOM has an incomplete Python inventory");

console.log(`Verified packaged application: ${unpacked}`);
console.log(`Backend entries inspected: ${walk(backend).length}`);
console.log(`Chromium notices: ${chromiumNotices.size} bytes`);
console.log(`SBOM components: ${sbom.components.length}`);
