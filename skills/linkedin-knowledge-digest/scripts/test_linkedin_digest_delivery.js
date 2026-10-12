"use strict";

const assert = require("node:assert/strict");
const delivery = require("./linkedin_digest_delivery");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const base = { last_successful_run_at: "2026-10-10T13:00:00Z", pending_digest: null, seen: [] };
const draft = {
  run_id: "li-test-001", prepared_at: "2026-10-12T13:00:00Z", channel: "slack",
  destination: "D0123", sender: "slack_send_message",
  message: "Read [AI evaluation](https://example.org/paper) for methodology and limitations.",
  candidates: [{ url: "https://example.org/paper", title: "AI evaluation", source: "Research lab" }]
};
const receipt = {
  accepted: true, channel: "slack", destination: "D0123", message_id: "1791810001.000000",
  permalink: "https://example.slack.com/archives/D0123/p1791810001000000", accepted_at: "2026-10-12T13:00:01.000Z"
};

function mockTools(state = base, failWrite = 0) {
  let raw = JSON.stringify(state, null, 2) + "\n";
  let writes = 0;
  return {
    state: () => JSON.parse(raw),
    tools: {
      exec_command: async () => ({ exit_code: 0, output: raw }),
      apply_patch: async (patch) => {
        writes += 1;
        if (writes === failWrite) throw new Error("simulated write failure");
        const plus = patch.split("\n").filter((line) => line.startsWith("+")).map((line) => line.slice(1));
        raw = plus.join("\n") + "\n";
        return {};
      }
    }
  };
}

async function testSuccessfulDelivery() {
  const mock = mockTools();
  let sends = 0;
  const result = await delivery.deliver({ tools: mock.tools, statePath: "/workspace/state.json", draft, send: async (pending) => {
    sends += 1;
    assert.deepEqual(mock.state().pending_digest, pending);
    assert.ok(pending.message.endsWith("[Digest run: li-test-001]"));
    return receipt;
  } });
  assert.equal(result.ok, true);
  assert.equal(sends, 1);
  assert.equal(mock.state().pending_digest, null);
  assert.equal(mock.state().seen.length, 1);
  assert.equal(mock.state().last_slack_message_link, receipt.permalink);
  assert.equal(mock.state().last_successful_run_at, receipt.accepted_at);
}

async function testFailureAndRecovery() {
  const mock = mockTools(base, 2);
  let sends = 0;
  const options = { tools: mock.tools, statePath: "/workspace/state.json", draft, send: async () => { sends += 1; return receipt; } };
  const failed = await delivery.deliver(options);
  assert.equal(failed.ok, false);
  assert.equal(failed.accepted, true);
  assert.equal(sends, 1);
  assert.equal(mock.state().last_successful_run_at, base.last_successful_run_at);
  assert.ok(mock.state().pending_digest);
  assert.equal((await delivery.deliver(options)).code, "pending_digest_unresolved");
  assert.equal(sends, 1);
  const expectedPending = mock.state().pending_digest;
  const recovery = await delivery.finalizeAccepted({ ...options, expectedPending, receipt });
  assert.equal(recovery.ok, true);
  assert.equal(mock.state().pending_digest, null);
  assert.equal(sends, 1);
}

async function testNoSendOnPrepareFailureAndAmbiguousSend() {
  const prepareFailure = mockTools(base, 1);
  let sends = 0;
  assert.equal((await delivery.deliver({ tools: prepareFailure.tools, statePath: "/w/state.json", draft, send: async () => { sends += 1; return receipt; } })).ok, false);
  assert.equal(sends, 0);
  const ambiguous = mockTools();
  const result = await delivery.deliver({ tools: ambiguous.tools, statePath: "/w/state.json", draft, send: async () => { sends += 1; throw new Error("timeout"); } });
  assert.equal(result.ok, false);
  assert.equal(result.sendStarted, true);
  assert.ok(ambiguous.state().pending_digest);
  assert.equal(ambiguous.state().last_successful_run_at, base.last_successful_run_at);
  assert.equal(sends, 1);
}

async function testExplicitRejectionAndChangedState() {
  const mock = mockTools();
  const rejected = await delivery.deliver({ tools: mock.tools, statePath: "/w/state.json", draft, send: async () => ({
    accepted: false, no_message_accepted: true, channel: "slack", destination: "D0123"
  }) });
  assert.equal(rejected.code, "delivery_rejected");
  assert.equal(mock.state().pending_digest, null);
  assert.equal(mock.state().last_successful_run_at, base.last_successful_run_at);
  const changed = mockTools();
  let reads = 0;
  const original = changed.tools.exec_command;
  changed.tools.exec_command = async () => {
    reads += 1;
    if (reads === 2) return { exit_code: 0, output: JSON.stringify({ ...base, concurrent: true }) };
    return original();
  };
  let sends = 0;
  const result = await delivery.deliver({ tools: changed.tools, statePath: "/w/state.json", draft, send: async () => { sends += 1; return receipt; } });
  assert.equal(result.code, "state_changed_before_write");
  assert.equal(sends, 0);
}

function testValidationAndRetention() {
  assert.throws(() => delivery.prepareState(base, { ...draft, candidates: [] }), /outgoing_url_mismatch/);
  assert.throws(() => delivery.prepareState(base, { ...draft, message: draft.message + " https://extra.example.org" }), /outgoing_url_mismatch/);
  assert.throws(() => delivery.prepareState(base, { ...draft, candidates: [...draft.candidates, ...draft.candidates] }), /duplicate_candidate_url/);
  const prepared = delivery.prepareState(base, draft);
  assert.throws(() => delivery.finalizeState(prepared, prepared.pending_digest, { ...receipt, destination: "other" }), /receipt_destination_mismatch/);
  assert.throws(() => delivery.finalizeState(prepared, { ...prepared.pending_digest, run_id: "different" }, receipt), /pending_digest_changed/);
  assert.throws(() => delivery.finalizeState(prepared, prepared.pending_digest, { ...receipt, accepted_at: "2026-10-01" }), /invalid_acceptance_time/);
  const seen = Array.from({ length: 220 }, (_, i) => ({ url: `https://example.org/${i}`, reported_at: "2026-10-11T13:00:00Z" }));
  seen.push({ url: "https://example.org/old", reported_at: "2026-01-01T00:00:00Z" });
  const full = { ...prepared, seen: [...seen, ...seen] };
  const result = delivery.finalizeState(full, prepared.pending_digest, receipt);
  assert.equal(result.seen.length, 200);
  assert.equal(new Set(result.seen.map((item) => item.url)).size, 200);
  assert.ok(!result.seen.some((item) => item.url.endsWith("/old")));
  const empty = delivery.prepareState(base, { ...draft, candidates: [], message: "No qualifying reads today." });
  assert.equal(delivery.finalizeState(empty, empty.pending_digest, receipt).pending_digest, null);
  assert.deepEqual(delivery.messageUrls("<https://example.org/paper|Read>\nhttps://example.org/another"), ["https://example.org/another", "https://example.org/paper"]);
}

function testReceiptAndPortableEvaluation() {
  const toolResult = { content: [{ type: "text", text: JSON.stringify({ message_link: receipt.permalink, message_context: { channel_id: receipt.destination, message_ts: receipt.message_id } }) }] };
  assert.deepEqual(delivery.slackReceipt(toolResult, "D0123"), receipt);
  assert.throws(() => delivery.slackReceipt(toolResult, "D9999"), /slack_receipt_invalid/);
  assert.throws(() => delivery.slackReceipt({ isError: true }, "D0123"), /slack_outcome_unconfirmed/);
  const loaded = vm.runInNewContext(fs.readFileSync(path.join(__dirname, "linkedin_digest_delivery.js"), "utf8"));
  assert.equal(typeof loaded.deliver, "function");
}

async function testCopySafePlainUrls() {
  const url = "https://example.org/research/evaluation?model=ai&version=2#limitations";
  const plain = {
    ...draft,
    message: `**Daily AI Reads**\n\n- AI evaluation - Research lab. Methods and limitations.\n${url}`,
    candidates: [{ url, title: "AI evaluation", source: "Research lab" }]
  };
  const mock = mockTools();
  let sends = 0;
  const result = await delivery.deliver({ tools: mock.tools, statePath: "/w/state.json", draft: plain, send: async (pending) => {
    sends += 1;
    assert.ok(pending.message.split("\n").includes(url));
    assert.deepEqual(delivery.messageUrls(pending.message), [url]);
    return receipt;
  } });
  assert.equal(result.ok, true);
  assert.equal(sends, 1);
  assert.equal(mock.state().seen[0].url, url);
  assert.equal(mock.state().pending_digest, null);
  assert.deepEqual(delivery.messageUrls(`[Read article](${url})\n\n\x60\x60\x60\n${url}\n\x60\x60\x60`), [url]);
  assert.deepEqual(delivery.messageUrls(`<${url}|Read article>\n\x60\x60\x60${url}\x60\x60\x60`), [url]);
}

(async () => {
  testValidationAndRetention();
  testReceiptAndPortableEvaluation();
  await testSuccessfulDelivery();
  await testCopySafePlainUrls();
  await testFailureAndRecovery();
  await testNoSendOnPrepareFailureAndAmbiguousSend();
  await testExplicitRejectionAndChangedState();
  console.log("LinkedIn delivery transaction tests passed.");
})().catch((error) => { console.error(error); process.exitCode = 1; });
