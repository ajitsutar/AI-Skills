#!/usr/bin/env node
"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const vm = require("node:vm");
const orchestrator = require("./linkedin_scan_orchestrator");
const {
  ORCHESTRATOR_NAME,
  materialize
} = require("./materialize_linkedin_scan_transport");

function band(index, overrides = {}) {
  return {
    schemaVersion: 1,
    payloadType: "linkedin_digest_band",
    ok: true,
    completionMetadata: { feedBandsInspected: index, pageValidated: true },
    posts: [],
    news: [],
    ...overrides
  };
}

function rawTransport(bands, connections = "{bad", messages = "") {
  const chunks = bands.map((value) => `<<<LINKEDIN_BAND>>>\n${JSON.stringify(value)}`);
  chunks.push(`<<<LINKEDIN_CONNECTIONS>>>\n${connections}`);
  chunks.push(`<<<LINKEDIN_MESSAGES>>>\n${messages}`);
  chunks.push("<<<LINKEDIN_DONE>>>");
  return chunks.join("\n");
}

function testManifestCommand() {
  const command = orchestrator.buildOsaScriptCommand([
    'tell application "Google Chrome"',
    'set value to "Ajit\'s digest"',
    "end tell"
  ]);
  assert.ok(command.startsWith(`osascript -e 'tell application "Google Chrome"'`));
  assert.ok(command.includes(`'\\''`));
  assert.equal(/[|;&<>]/.test(command), false);
}

function testTransportParsingAndOptionalDegradation() {
  const parsed = orchestrator.parseMarkedTransport(rawTransport([
    band(1),
    band(2),
    band(3)
  ]));
  assert.equal(parsed.ok, true);
  assert.equal(parsed.feedBandsInspected, 3);
  assert.equal(parsed.connections.ok, false);
  assert.equal(parsed.messages.ok, false);
}

function testMaterializationIncludesOrchestrator() {
  const destination = fs.mkdtempSync(path.join(os.tmpdir(), "linkedin-scan-"));
  try {
    const result = materialize(destination);
    assert.equal(fs.existsSync(result.manifestPath), true);
    assert.equal(fs.existsSync(path.join(destination, ORCHESTRATOR_NAME)), true);
  } finally {
    fs.rmSync(destination, { recursive: true, force: true });
  }
}

function testCompactSummaryIsPublicAndStateAware() {
  const external = "https://example.com/report?utm_source=linkedin";
  const seen = "https://www.linkedin.com/news/story/already-seen-1/";
  const parsed = orchestrator.parseMarkedTransport(rawTransport([
    band(1, {
      posts: [{
        author: "Ada Lovelace",
        contentUrls: [external],
        text: "Feed post Ada Lovelace • 2d • AI architecture research report for enterprise security teams.",
        engagement: "240 reactions"
      }]
    }),
    band(2, { news: [{ text: "AI market report", href: seen }] }),
    band(3)
  ], JSON.stringify({
    ok: true,
    items: [{ profile: "https://www.linkedin.com/in/ada", text: "Ada Lovelace Oracle" }]
  }), JSON.stringify({
    ok: true,
    threads: [{ href: "https://www.linkedin.com/messaging/thread/private", text: "private message" }]
  })));

  const summary = orchestrator.buildCompactSummary({
    transport: parsed,
    state: {
      last_successful_run_at: "2026-08-28T09:00:00Z",
      pending_digest: null,
      seen: [{ url: seen }]
    },
    currentTimeIso: "2026-09-02T13:00:00Z",
    priorityOrganizations: ["Oracle"]
  });
  assert.equal(summary.ok, true);
  assert.equal(summary.candidates.length, 1);
  assert.deepEqual(summary.candidates[0].contentUrls, ["https://example.com/report"]);
  assert.equal(summary.candidates[0].priorityNetwork, true);
  assert.deepEqual(summary.inbox.publicActionUrls, []);
  assert.equal(JSON.stringify(summary).includes("private message"), false);
  assert.equal(JSON.stringify(summary).includes("/messaging/thread/"), false);
}

function testRunsWithoutBrowserUrlGlobal() {
  const source = fs.readFileSync(path.join(__dirname, "linkedin_scan_orchestrator.js"), "utf8");
  const isolated = vm.runInNewContext(source, {
    module: { exports: {} },
    console,
    decodeURIComponent,
    JSON,
    Math,
    RegExp,
    Set,
    String,
    Date
  });
  assert.equal(
    isolated.normalizeContentUrl("https://www.linkedin.com/news/story/test-123/?trk=feed"),
    "https://www.linkedin.com/news/story/test-123"
  );
  assert.equal(
    isolated.normalizeContentUrl("https://example.com/report?utm_source=linkedin&id=7"),
    "https://example.com/report?id=7"
  );
}

async function testRunCollectsAllChunksWithoutStore() {
  const manifest = ['tell application "Google Chrome"', "end tell"];
  const raw = rawTransport([band(1), band(2), band(3)], JSON.stringify({ ok: true, items: [] }), JSON.stringify({ ok: true, threads: [] }));
  const calls = [];
  const tools = {
    exec_command: async (args) => {
      calls.push(args);
      if (args.cmd.includes("state.json")) {
        return { exit_code: 0, output: JSON.stringify({ pending_digest: null, seen: [] }) };
      }
      if (args.cmd.includes("manifest.json")) {
        return { exit_code: 0, output: JSON.stringify(manifest) };
      }
      return { session_id: 77, output: raw.slice(0, 90) };
    },
    write_stdin: async (args) => {
      calls.push(args);
      return { exit_code: 0, output: raw.slice(90) };
    }
  };
  const result = await orchestrator.run({
    tools,
    manifestPath: "/workspace/manifest.json",
    statePath: "/workspace/state.json",
    workdir: "/workspace",
    currentTimeIso: "2026-09-02T13:00:00Z"
  });
  assert.equal(result.ok, true);
  assert.equal(result.scan.feedBandsInspected, 3);
  assert.ok(calls[2].cmd.startsWith(`osascript -e 'tell application "Google Chrome"'`));
  assert.equal(calls[3].session_id, 77);
  assert.equal("raw" in result, false);
}

async function testPendingStopsBeforeBrowser() {
  let calls = 0;
  const result = await orchestrator.run({
    tools: {
      exec_command: async () => {
        calls += 1;
        return { exit_code: 0, output: JSON.stringify({ pending_digest: { run_id: "prior" } }) };
      }
    },
    manifestPath: "/workspace/manifest.json",
    statePath: "/workspace/state.json",
    workdir: "/workspace",
    currentTimeIso: "2026-09-02T13:00:00Z"
  });
  assert.equal(result.ok, false);
  assert.equal(result.code, "pending_digest_unresolved");
  assert.equal(calls, 1);
}

async function main() {
  testManifestCommand();
  testTransportParsingAndOptionalDegradation();
  testMaterializationIncludesOrchestrator();
  testCompactSummaryIsPublicAndStateAware();
  testRunsWithoutBrowserUrlGlobal();
  await testRunCollectsAllChunksWithoutStore();
  await testPendingStopsBeforeBrowser();
  console.log("LinkedIn scan orchestrator tests passed.");
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
