const fs = require("fs");
const path = require("path");

const HELPER_NAMES = [
  "linkedin_digest_candidates.js",
  "linkedin_feed_reset.js",
  "linkedin_feed_scroll.js",
  "linkedin_connections_candidates.js",
  "linkedin_messages_candidates.js"
];

function appleScriptString(value) {
  return `"${value.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
}

function buildManifest(scriptsDir) {
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

function materialize(destinationDir) {
  fs.mkdirSync(destinationDir, { recursive: true });
  for (const helper of HELPER_NAMES) {
    const source = path.join(__dirname, helper);
    const destination = path.join(destinationDir, helper);
    if (!fs.existsSync(source)) throw new Error(`Missing bundled helper: ${helper}`);
    if (path.resolve(source) !== path.resolve(destination)) fs.copyFileSync(source, destination);
  }

  const manifestPath = path.join(destinationDir, "linkedin_scan_applescript_lines.json");
  const lines = buildManifest(path.resolve(destinationDir));
  fs.writeFileSync(manifestPath, `${JSON.stringify(lines, null, 2)}\n`, "utf8");
  return { manifestPath, lines };
}

if (require.main === module) {
  const destination = process.argv[2];
  if (!destination) {
    console.error("Usage: node materialize_linkedin_scan_transport.js <destination-directory>");
    process.exit(2);
  }
  const result = materialize(path.resolve(destination));
  console.log(JSON.stringify({
    ok: true,
    manifestPath: result.manifestPath,
    lines: result.lines.length,
    helpers: HELPER_NAMES.length
  }));
}

module.exports = { HELPER_NAMES, buildManifest, materialize };
