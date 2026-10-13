const fs = require("fs");
const path = require("path");

const HELPER_NAMES = [
  "linkedin_digest_candidates.js",
  "linkedin_feed_reset.js",
  "linkedin_feed_scroll.js",
  "linkedin_connections_candidates.js",
  "linkedin_messages_candidates.js"
];
const SEARCH_HELPERS = ["linkedin_search_candidates.js", "linkedin_feed_scroll.js"];
const ORCHESTRATOR_NAME = "linkedin_scan_orchestrator.js";
const DELIVERY_NAME = "linkedin_digest_delivery.js";

function appleScriptString(value) {
  return `"${value.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
}

function buildSearchManifest(scriptsDir, options) {
  const queries = options.linkedin_queries;
  const bands = options.linkedin_bands_per_query || 3;
  if (!Array.isArray(queries) || queries.length < 1 || queries.length > 3
      || queries.some((q) => typeof q !== "string" || !q.trim() || q.length > 160)
      || new Set(queries).size !== queries.length || !Number.isInteger(bands) || bands < 3 || queries.length * bands > 10) {
    throw new Error("invalid_search_configuration");
  }
  const lines = [
    'tell application "Google Chrome"',
    "set automationWindow to missing value", "try",
    `set searchJs to read (POSIX file ${appleScriptString(path.join(scriptsDir, SEARCH_HELPERS[0]))})`,
    `set scrollJs to read (POSIX file ${appleScriptString(path.join(scriptsDir, SEARCH_HELPERS[1]))})`,
    "set automationWindow to make new window", "set automationTab to active tab of automationWindow",
    'set searchTransport to ""'
  ];
  for (const query of queries) {
    const url = `https://www.linkedin.com/search/results/content/?keywords=${encodeURIComponent(query)}&datePosted=%22past-week%22`;
    lines.push(
      `set URL of automationTab to ${appleScriptString(url)}`, "delay 8",
      `repeat with bandIndex from 1 to ${bands}`,
      "set bandResult to execute automationTab javascript searchJs",
      'if bandResult is missing value then error "search_payload_missing"',
      'if bandResult does not contain "\\"ok\\":true" then error "search_page_unavailable"',
      'set searchTransport to searchTransport & linefeed & "<<<LINKEDIN_BAND>>>" & linefeed & bandResult',
      "set scrollResult to execute automationTab javascript scrollJs", "delay 3", "end repeat"
    );
  }
  if (options.include_connections_updates === true) {
    lines.push(
      'set URL of automationTab to "https://www.linkedin.com/feed/"', "delay 8",
      "repeat with networkBandIndex from 1 to 3",
      "set bandResult to execute automationTab javascript searchJs",
      'if bandResult is missing value then error "network_payload_missing"',
      'if bandResult does not contain "\\"ok\\":true" then error "network_page_unavailable"',
      'set searchTransport to searchTransport & linefeed & "<<<LINKEDIN_BAND>>>" & linefeed & bandResult',
      "set scrollResult to execute automationTab javascript scrollJs", "delay 3", "end repeat"
    );
  }
  lines.push(
    'set finalResult to searchTransport & linefeed & "<<<LINKEDIN_DONE>>>"',
    "close automationWindow", "return finalResult", "on error errMsg number errNum", "try",
    "if automationWindow is not missing value then close automationWindow", "end try",
    "error errMsg number errNum", "end try", "end tell"
  );
  return lines;
}

function buildManifest(scriptsDir, options = {}) {
  if (options.linkedin_mode === "search") return buildSearchManifest(scriptsDir, options);
  if (options.linkedin_mode && options.linkedin_mode !== "feed") throw new Error("invalid_linkedin_mode");
  const helperPath = (name) => appleScriptString(path.join(scriptsDir, name));
  return [
    'tell application "Google Chrome"',
    "set automationWindow to missing value",
    "try",
    `set feedJs to read (POSIX file ${helperPath("linkedin_digest_candidates.js")})`,
    `set resetJs to read (POSIX file ${helperPath("linkedin_feed_reset.js")})`,
    `set scrollJs to read (POSIX file ${helperPath("linkedin_feed_scroll.js")})`,
    `set connectionsJs to read (POSIX file ${helperPath("linkedin_connections_candidates.js")})`,
    `set messagesJs to read (POSIX file ${helperPath("linkedin_messages_candidates.js")})`,
    "set automationWindow to make new window",
    "set automationTab to active tab of automationWindow",
    'set URL of automationTab to "https://www.linkedin.com/feed/"',
    "delay 8",
    "set resetResult to execute automationTab javascript resetJs",
    'set feedTransport to ""',
    "repeat with bandIndex from 1 to 10",
    "set bandResult to execute automationTab javascript feedJs",
    "if bandResult is not missing value then",
    'if bandResult is not "" then set feedTransport to feedTransport & linefeed & "<<<LINKEDIN_BAND>>>" & linefeed & bandResult',
    "end if",
    "set scrollResult to execute automationTab javascript scrollJs",
    "delay 3",
    "end repeat",
    'set URL of automationTab to "https://www.linkedin.com/mynetwork/invite-connect/connections/"',
    "delay 7",
    "set connectionsResult to execute automationTab javascript connectionsJs",
    'if connectionsResult is missing value then set connectionsResult to "{\\"schemaVersion\\":1,\\"payloadType\\":\\"linkedin_connections_candidates\\",\\"ok\\":false,\\"items\\":[],\\"error\\":\\"missing value\\"}"',
    'if connectionsResult is "" then set connectionsResult to "{\\"schemaVersion\\":1,\\"payloadType\\":\\"linkedin_connections_candidates\\",\\"ok\\":false,\\"items\\":[],\\"error\\":\\"empty value\\"}"',
    'set URL of automationTab to "https://www.linkedin.com/messaging/"',
    "delay 7",
    "set messagesResult to execute automationTab javascript messagesJs",
    'if messagesResult is missing value then set messagesResult to "{\\"schemaVersion\\":1,\\"payloadType\\":\\"linkedin_messages_candidates\\",\\"ok\\":false,\\"threads\\":[],\\"error\\":\\"missing value\\"}"',
    'if messagesResult is "" then set messagesResult to "{\\"schemaVersion\\":1,\\"payloadType\\":\\"linkedin_messages_candidates\\",\\"ok\\":false,\\"threads\\":[],\\"error\\":\\"empty value\\"}"',
    'set finalResult to feedTransport & linefeed & "<<<LINKEDIN_CONNECTIONS>>>" & linefeed & connectionsResult & linefeed & "<<<LINKEDIN_MESSAGES>>>" & linefeed & messagesResult & linefeed & "<<<LINKEDIN_DONE>>>"',
    "close automationWindow",
    "return finalResult",
    "on error errMsg number errNum",
    "try",
    "if automationWindow is not missing value then close automationWindow",
    "end try",
    "error errMsg number errNum",
    "end try",
    "end tell"
  ];
}

function materialize(destinationDir, options = {}) {
  fs.mkdirSync(destinationDir, { recursive: true });
  for (const helper of new Set([...HELPER_NAMES, ...SEARCH_HELPERS])) {
    const source = path.join(__dirname, helper);
    const destination = path.join(destinationDir, helper);
    if (!fs.existsSync(source)) throw new Error(`Missing bundled helper: ${helper}`);
    if (path.resolve(source) !== path.resolve(destination)) fs.copyFileSync(source, destination);
  }
  const orchestratorSource = path.join(__dirname, ORCHESTRATOR_NAME);
  const orchestratorDestination = path.join(destinationDir, ORCHESTRATOR_NAME);
  if (!fs.existsSync(orchestratorSource)) {
    throw new Error(`Missing bundled orchestrator: ${ORCHESTRATOR_NAME}`);
  }
  if (path.resolve(orchestratorSource) !== path.resolve(orchestratorDestination)) {
    fs.copyFileSync(orchestratorSource, orchestratorDestination);
  }
  const deliverySource = path.join(__dirname, DELIVERY_NAME);
  const deliveryDestination = path.join(destinationDir, DELIVERY_NAME);
  if (path.resolve(deliverySource) !== path.resolve(deliveryDestination)) {
    fs.copyFileSync(deliverySource, deliveryDestination);
  }

  const manifestPath = path.join(destinationDir, "linkedin_scan_applescript_lines.json");
  const lines = buildManifest(path.resolve(destinationDir), options);
  fs.writeFileSync(manifestPath, `${JSON.stringify(lines, null, 2)}\n`, "utf8");
  return { manifestPath, lines };
}

if (require.main === module) {
  const destination = process.argv[2];
  if (!destination) {
    console.error("Usage: node materialize_linkedin_scan_transport.js <destination-directory>");
    process.exit(2);
  }
  const options = process.argv[3] ? JSON.parse(fs.readFileSync(process.argv[3], "utf8")).content.discovery : {};
  const result = materialize(path.resolve(destination), options);
  console.log(JSON.stringify({
    ok: true,
    manifestPath: result.manifestPath,
    lines: result.lines.length,
    helpers: HELPER_NAMES.length,
    orchestrator: ORCHESTRATOR_NAME
  }));
}

module.exports = { HELPER_NAMES, SEARCH_HELPERS, ORCHESTRATOR_NAME, DELIVERY_NAME, buildManifest, materialize };
