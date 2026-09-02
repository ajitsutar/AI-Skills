const fs = require("fs");
const path = require("path");

const {
  HELPER_NAMES,
  ORCHESTRATOR_NAME
} = require("./materialize_linkedin_scan_transport");

const manifestPath = process.argv[2];
if (!manifestPath) {
  console.error("Usage: node validate_linkedin_scan_transport.js <manifest-path>");
  process.exit(2);
}

const lines = JSON.parse(fs.readFileSync(path.resolve(manifestPath), "utf8"));
const failures = [];
if (!Array.isArray(lines) || lines.length < 20) failures.push("missing AppleScript lines");
if (lines[0] !== 'tell application "Google Chrome"') failures.push("wrong approved prefix");
if (lines.filter((line) => line === "set automationWindow to make new window").length !== 1) {
  failures.push("runner must create exactly one window");
}
if (!lines.includes("close automationWindow")) failures.push("success path does not close window");
if (!lines.includes("if automationWindow is not missing value then close automationWindow")) {
  failures.push("failure path does not close window");
}
if (lines.some((line) => /javascript\s+"/.test(line))) {
  failures.push("JavaScript must be loaded from files, never inlined into AppleScript");
}
if (!lines.includes("repeat with bandIndex from 1 to 10")) {
  failures.push("runner must inspect ten bounded feed bands");
}

for (const helper of HELPER_NAMES) {
  const loadLine = lines.find((line) => line.includes(`POSIX file`) && line.includes(helper));
  if (!loadLine) {
    failures.push(`missing helper load: ${helper}`);
    continue;
  }
  const match = loadLine.match(/POSIX file "((?:\\.|[^"])*)"/);
  const helperPath = match?.[1]?.replace(/\\"/g, '"').replace(/\\\\/g, "\\");
  if (!helperPath || !fs.existsSync(helperPath)) failures.push(`helper not found: ${helper}`);
}

const orchestratorPath = path.join(path.dirname(path.resolve(manifestPath)), ORCHESTRATOR_NAME);
if (!fs.existsSync(orchestratorPath)) failures.push(`orchestrator not found: ${ORCHESTRATOR_NAME}`);

if (failures.length) {
  console.error(failures.join("\n"));
  process.exit(1);
}

console.log(JSON.stringify({
  ok: true,
  manifestPath: path.resolve(manifestPath),
  lines: lines.length,
  helpers: HELPER_NAMES.length,
  orchestrator: ORCHESTRATOR_NAME,
  approvedPrefix: lines[0]
}));
