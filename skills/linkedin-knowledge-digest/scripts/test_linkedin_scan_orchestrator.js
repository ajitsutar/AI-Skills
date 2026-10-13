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
  DELIVERY_NAME,
  buildManifest,
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
    'set value to "Reader\'s digest"',
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
    assert.equal(fs.existsSync(path.join(destination, DELIVERY_NAME)), true);
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
    items: [{ profile: "https://www.linkedin.com/in/ada", text: "Ada Lovelace Example University" }]
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
    priorityOrganizations: ["Example University"]
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

function testAiFocusAndEvidenceRanking() {
  const parsed = orchestrator.parseMarkedTransport(rawTransport([
    band(1, { posts: [
      { author: "Familiar Example University Author", text: "1h AI is changing everything about enterprise software!", engagement: "900,000 reactions", contentUrls: ["https://www.linkedin.com/posts/viral-ai"] },
      { author: "Research Lab", text: "2h Machine learning evaluation with reproducible baselines and limitations.", engagement: "3 reactions", contentUrls: ["https://www.linkedin.com/posts/paper-share", "https://example.com/paper"] },
      { author: "Cloud Team", text: "1h Database architecture report with detailed benchmarks.", contentUrls: ["https://example.com/database"] },
      { author: "Recruiter", text: "1h Hiring AI research engineers. Apply now!", contentUrls: ["https://example.com/jobs"] }
    ] }),
    band(2), band(3)
  ]));
  const input = { transport: parsed, state: { seen: [] }, currentTimeIso: "2026-10-12T13:00:00Z", priorityOrganizations: ["Example University"] };
  const ai = orchestrator.buildCompactSummary(input);
  assert.equal(ai.contentFocus, "ai");
  assert.equal(ai.candidates.length, 2);
  assert.equal(ai.candidates[0].source, "Research Lab");
  assert.equal(ai.candidates[0].aiRelevant, true);
  assert.equal(ai.candidates[0].evidenceHint, true);
  assert.deepEqual(ai.candidates[0].contentUrls, ["https://example.com/paper", "https://www.linkedin.com/posts/paper-share"]);
  const general = orchestrator.buildCompactSummary({ ...input, contentFocus: "general" });
  assert.equal(general.candidates.length, 3);
  assert.ok(general.candidates.some((item) => item.source === "Cloud Team" && !item.aiRelevant));
  assert.throws(() => orchestrator.buildCompactSummary({ ...input, contentFocus: "typo" }), /invalid_content_focus/);
}

function testFreshShareSurvivesStaleDuplicateAndSeenSources() {
  const article = "https://example.com/ai-paper";
  const seen = "https://example.com/prior-report";
  const parsed = orchestrator.parseMarkedTransport(rawTransport([
    band(1, { posts: [{ author: "Old Share", text: "4w AI research paper evaluation.", contentUrls: [article] }] }),
    band(2, { posts: [{ author: "New Share", text: "1h AI research paper evaluation.", contentUrls: [article, seen, "https://www.linkedin.com/in/author"] }] }),
    band(3, { posts: [{ author: "Duplicate", text: "2h AI research paper evaluation.", contentUrls: [article] }] })
  ]));
  const result = orchestrator.buildCompactSummary({
    transport: parsed,
    state: { last_successful_run_at: "2026-10-11T13:00:00Z", seen: [{ url: seen }] },
    currentTimeIso: "2026-10-12T13:00:00Z"
  });
  assert.equal(result.candidates.length, 1);
  assert.equal(result.candidates[0].source, "New Share");
  assert.deepEqual(result.candidates[0].contentUrls, [article]);
}

async function testInvalidFocusStopsBeforeBrowser() {
  let calls = 0;
  const result = await orchestrator.run({
    tools: { exec_command: async () => { calls += 1; } },
    contentFocus: "invalid"
  });
  assert.equal(result.ok, false);
  assert.equal(result.code, "invalid_content_focus");
  assert.equal(calls, 0);
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
  testSearchMode();
  testUserConfiguredConnectionPriority();
  testSearchExtraction();
  testManifestCommand();
  testTransportParsingAndOptionalDegradation();
  testMaterializationIncludesOrchestrator();
  testCompactSummaryIsPublicAndStateAware();
  testRunsWithoutBrowserUrlGlobal();
  testAiFocusAndEvidenceRanking();
  testFreshShareSurvivesStaleDuplicateAndSeenSources();
  await testInvalidFocusStopsBeforeBrowser();
  await testRunCollectsAllChunksWithoutStore();
  await testPendingStopsBeforeBrowser();
  console.log("LinkedIn scan orchestrator tests passed.");
}

function testSearchMode() {
  const queries = ["AI research", "LLM engineering", "AI safety"];
  const lines = buildManifest("/workspace/scripts", { linkedin_mode: "search", linkedin_queries: queries });
  assert.equal(lines.filter((line) => line === "set automationWindow to make new window").length, 1);
  assert.ok(!lines.some((line) => /https:\/\/www.linkedin.com\/(feed|mynetwork|messaging)\//.test(line)));
  assert.ok(lines.every((line) => !/javascript\s+"/.test(line)));
  const bands = queries.flatMap((query) => [1, 2, 3].map((n) => ({
    ...band(n), payloadType: "linkedin_search_band", query,
    completionMetadata: { pageValidated: true, searchBandsInspected: n },
    posts: n === 1 ? [{ author: "Example University Research", text: "3d AI research benchmark paper with methodology and limitations.", contentUrls: ["https://example.com/paper"] }] : []
  })));
  const options = { discoveryMode: "search", searchQueries: queries };
  const transport = orchestrator.parseMarkedTransport(rawTransport(bands), options);
  assert.equal(transport.ok, true);
  assert.equal(transport.searchBandsInspected, 9);
  const summary = orchestrator.buildCompactSummary({
    transport, state: { last_successful_run_at: "2026-10-12T13:00:00Z", seen: [] },
    currentTimeIso: "2026-10-13T13:00:00Z", discoveryMode: "search", maxSourceAgeDays: 7,
    priorityOrganizations: ["Example University"]
  });
  assert.equal(summary.candidates.length, 1);
  assert.equal(summary.candidates[0].priorityNetwork, false);
  assert.equal(summary.candidates[0].discovery, "linkedin_search");
  assert.equal(summary.optionalSources.connectionsOk, false);
  const network = [1, 2, 3].map((n) => ({
    ...band(n), payloadType: "linkedin_network_band", query: "",
    completionMetadata: { pageValidated: true, searchBandsInspected: n },
    posts: n === 1 ? [{ author: "Connection", connectionDegree: 1, publicAudience: true, text: "1h Database architecture report and technical security analysis.", contentUrls: ["https://example.com/database"] }] : []
  }));
  const combined = orchestrator.parseMarkedTransport(rawTransport([...bands, ...network]), { ...options, includeConnectionsUpdates: true });
  assert.equal(combined.ok, true);
  const generalConnection = orchestrator.buildCompactSummary({ transport: combined, state: { seen: [] }, currentTimeIso: "2026-10-13T13:00:00Z", discoveryMode: "search" });
  assert.ok(generalConnection.candidates.some((c) => c.kind === "connection_update" && !c.aiRelevant));
  assert.equal(orchestrator.parseMarkedTransport(rawTransport(bands), { ...options, includeConnectionsUpdates: true }).ok, false);
  assert.equal(orchestrator.parseMarkedTransport(rawTransport(bands.slice(0, 8)), options).ok, false);
  assert.equal(orchestrator.parseMarkedTransport(rawTransport(bands), { ...options, searchQueries: ["other"] }).ok, false);
  assert.equal(orchestrator.parseMarkedTransport(rawTransport(bands)).ok, false);
  assert.throws(() => buildManifest("/tmp", { linkedin_mode: "search", linkedin_queries: [] }), /invalid_search_configuration/);
}

function testUserConfiguredConnectionPriority() {
  const post = (author, affiliationContext, overrides = {}) => ({
    author, affiliationContext, connectionDegree: 1, publicAudience: true,
    text: "1h Database architecture report with measured performance and limitations.",
    contentUrls: [`https://example.com/${author.toLowerCase()}`], ...overrides
  });
  const transport = {
    bands: [{ payloadType: "linkedin_network_band", posts: [
      post("Alumna", "Alumna, Example University"),
      post("FormerColleague", "Engineer at Example Systems"),
      post("MentionOnly", "Independent engineer", { text: "1h Database architecture report about Example University." }),
      post("Substring", "Example UniversityPress"),
      post("NotConnected", "Example University", { connectionDegree: 2 })
    ] }, { payloadType: "linkedin_search_band", query: "AI research", posts: [
      post("SearchAuthor", "Example University", { text: "1h AI research evaluation with methodology and limitations." })
    ] }]
  };
  const input = { transport, state: { seen: [] }, currentTimeIso: "2026-10-13T13:00:00Z", discoveryMode: "search" };
  const configured = orchestrator.buildCompactSummary({ ...input, priorityOrganizations: ["Example University", "Example Systems"] });
  assert.deepEqual(configured.candidates.filter((item) => item.priorityNetwork).map((item) => item.source).sort(), ["Alumna", "FormerColleague"]);
  assert.ok(!configured.candidates.some((item) => item.source === "NotConnected"));
  assert.ok(orchestrator.buildCompactSummary(input).candidates.every((item) => !item.priorityNetwork));
}

function testSearchExtraction() {
  const source = fs.readFileSync(path.join(__dirname, "linkedin_search_candidates.js"), "utf8");
  const makeNode = (index) => ({
    innerText: `Research Author 3d Visible to anyone AI research evaluation ${"methodology limitations ".repeat(50)}`,
    getAttribute: () => "",
    querySelector: (selector) => selector.startsWith('[aria-label') ? null : ({ innerText: "Research Author" }),
    querySelectorAll: (selector) => selector === "a[href]" ? [
      { href: `https://example.com/paper-${index}`, innerText: "Paper" },
      { href: "https://www.linkedin.com/in/person", innerText: "Person" },
      { href: "https://www.linkedin.com/messaging/thread/private", innerText: "Private" }
    ] : []
  });
  let nodes = Array.from({ length: 40 }, (_, i) => makeNode(i));
  const main = { innerText: "Search results", querySelectorAll: () => nodes };
  const context = vm.createContext({ URL, TextEncoder, window: {}, location: { href: "https://www.linkedin.com/search/results/content/?keywords=AI" }, document: { querySelector: () => main } });
  const first = JSON.parse(vm.runInContext(source, context));
  assert.equal(first.ok, true);
  assert.ok(first.posts.length > 0 && first.posts.length <= 4);
  assert.ok(first.posts.every((post) => post.text.length <= 900 && post.contentUrls.length === 1 && post.publicAudience));
  assert.ok(Buffer.byteLength(JSON.stringify(first)) < 6000);
  const second = JSON.parse(vm.runInContext(source, context));
  assert.equal(second.completionMetadata.searchBandsInspected, 2);
  assert.ok(!second.posts.some((post) => first.posts.some((prior) => prior.contentUrls[0] === post.contentUrls[0])));
  nodes = [];
  assert.equal(JSON.parse(vm.runInContext(source, context)).error, "linkedin_search_layout_unrecognized");
  main.innerText = "No results found";
  assert.equal(JSON.parse(vm.runInContext(source, context)).ok, true);
  context.location.href = "https://www.linkedin.com/checkpoint/";
  assert.equal(JSON.parse(vm.runInContext(source, context)).ok, false);
  context.location.href = "https://www.linkedin.com/feed/";
  main.innerText = "Feed";
  nodes = [makeNode(100)];
  assert.equal(JSON.parse(vm.runInContext(source, context)).posts.length, 0);
  nodes[0].querySelector = (selector) => ({ innerText: selector.includes('__meta') ? "Research Author 1st" : "Research Author" });
  const connection = JSON.parse(vm.runInContext(source, context));
  assert.equal(connection.payloadType, "linkedin_network_band");
  assert.equal(connection.posts[0].connectionDegree, 1);
  nodes[0].innerText = "1st Proud to announce my promotion and company outing with our research team! This is a sufficiently long promotional post.";
  assert.equal(JSON.parse(vm.runInContext(source, context)).posts.length, 0);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
