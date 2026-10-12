"use strict";

const LinkedInDigestDelivery = (() => {
  const clone = (value) => JSON.parse(JSON.stringify(value));
  const same = (left, right) => JSON.stringify(left) === JSON.stringify(right);
  const quote = (value) => `'${String(value).replace(/'/g, `'\\''`)}'`;

  function check(condition, code) {
    if (!condition) throw new Error(code);
  }

  function messageUrls(message) {
    const urls = [];
    let remaining = message.replace(/\[[^\]\n]*\]\((https?:\/\/[^\s]+?)\)(?=[\s.,;!?]|$)/g, (_, url) => {
      urls.push(url);
      return "";
    });
    remaining = remaining.replace(/<(https?:\/\/[^>|]+)(?:\|[^>]+)?>/g, (_, url) => {
      urls.push(url);
      return "";
    });
    remaining = remaining.replace(/```(?:[a-zA-Z0-9_-]+\n)?([\s\S]*?)```/g, (_, code) => code);
    urls.push(...(remaining.match(/https?:\/\/[^\s<>]+/g) || []));
    return [...new Set(urls)].sort();
  }

  function validatePending(pending) {
    check(pending && /^[a-zA-Z0-9_-]{4,80}$/.test(pending.run_id), "invalid_run_id");
    check(Number.isFinite(Date.parse(pending.prepared_at)), "invalid_prepared_time");
    for (const field of ["channel", "destination", "sender", "message"]) {
      check(typeof pending[field] === "string" && pending[field].trim(), `invalid_${field}`);
    }
    check(pending.channel !== "local", "draft_cannot_send");
    check(pending.message.endsWith(`[Digest run: ${pending.run_id}]`), "run_marker_missing");
    check(Array.isArray(pending.candidates), "invalid_candidates");
    const urls = pending.candidates.map((item) => {
      check(item && typeof item.url === "string" && /^https?:\/\/[^\s<>]+$/.test(item.url), "invalid_candidate_url");
      check(typeof item.title === "string" && item.title.trim() && typeof item.source === "string" && item.source.trim(), "invalid_candidate_metadata");
      return item.url;
    });
    check(new Set(urls).size === urls.length, "duplicate_candidate_url");
    check(same([...urls].sort(), messageUrls(pending.message)), "outgoing_url_mismatch");
  }

  function prepareState(state, draft) {
    check(!state.pending_digest, "pending_digest_unresolved");
    const pending = clone(draft);
    pending.message = `${pending.message.trim()}\n\n[Digest run: ${pending.run_id}]`;
    validatePending(pending);
    return { ...clone(state), pending_digest: pending };
  }

  function finalizeState(state, expectedPending, receipt) {
    check(same(state.pending_digest, expectedPending), "pending_digest_changed");
    validatePending(expectedPending);
    check(receipt?.accepted === true, "acceptance_not_confirmed");
    check(receipt.channel === expectedPending.channel && receipt.destination === expectedPending.destination, "receipt_destination_mismatch");
    const acceptedMs = Date.parse(receipt.accepted_at);
    check(Number.isFinite(acceptedMs) && acceptedMs >= Date.parse(expectedPending.prepared_at), "invalid_acceptance_time");
    check(Boolean(receipt.message_id || receipt.permalink), "receipt_identifier_missing");
    check(!state.last_digest_sent_at || acceptedMs >= Date.parse(state.last_digest_sent_at), "receipt_older_than_state");
    check(Array.isArray(state.seen || []), "invalid_seen");
    const seen = [
      ...expectedPending.candidates.map((item) => ({ ...item, reported_at: receipt.accepted_at })),
      ...(state.seen || [])
    ].filter((item) => typeof item.url === "string" && Date.parse(item.reported_at) >= acceptedMs - 60 * 86400000)
      .sort((a, b) => Date.parse(b.reported_at) - Date.parse(a.reported_at));
    const unique = new Set();
    const result = {
      ...clone(state),
      last_successful_run_at: receipt.accepted_at,
      last_digest_sent_at: receipt.accepted_at,
      last_delivery: {
        channel: receipt.channel,
        destination: receipt.destination,
        message_id: receipt.message_id || null,
        permalink: receipt.permalink || null,
        accepted_at: receipt.accepted_at,
        status: "accepted",
        run_id: expectedPending.run_id
      },
      pending_digest: null,
      seen: seen.filter((item) => {
        if (unique.has(item.url)) return false;
        unique.add(item.url);
        return true;
      }).slice(0, 200)
    };
    if (receipt.channel === "slack" && receipt.permalink) result.last_slack_message_link = receipt.permalink;
    return result;
  }

  async function readState({ tools, statePath, workdir }) {
    check(typeof statePath === "string" && !/[\r\n]/.test(statePath), "invalid_state_path");
    const read = await tools.exec_command({ cmd: `cat ${quote(statePath)}`, workdir, max_output_tokens: 30000, yield_time_ms: 10000 });
    check(read.exit_code === 0, "state_read_failed");
    const state = JSON.parse(read.output);
    check(state && typeof state === "object" && !Array.isArray(state), "invalid_state");
    return { raw: read.output, state };
  }

  async function writeVerified(options, before, after) {
    const fresh = await readState(options);
    check(fresh.raw === before.raw, "state_changed_before_write");
    const lines = (value, prefix) => value.trimEnd().split("\n").map((line) => prefix + line).join("\n");
    const patch = `*** Begin Patch\n*** Update File: ${options.statePath}\n@@\n${lines(before.raw, "-")}\n${lines(JSON.stringify(after, null, 2), "+")}\n*** End Patch`;
    // Verify the file even when a tool's acknowledgment is missing or ambiguous.
    try { await options.tools.apply_patch(patch); } catch { /* Re-read below. */ }
    const verified = await readState(options);
    check(same(verified.state, after), "state_write_not_verified");
    return verified;
  }

  async function finalizeAccepted(options) {
    const before = await readState(options);
    const after = finalizeState(before.state, options.expectedPending, options.receipt);
    await writeVerified(options, before, after);
    return { ok: true, receipt: options.receipt, seenCount: after.seen.length, pending: null };
  }

  async function deliver(options) {
    let receipt = null;
    let sendStarted = false;
    try {
      check(typeof options.send === "function", "sender_unavailable");
      const before = await readState(options);
      const prepared = prepareState(before.state, options.draft);
      await writeVerified(options, before, prepared);
      const pending = prepared.pending_digest;
      sendStarted = true;
      receipt = await options.send(clone(pending));
      if (receipt?.accepted === false && receipt.no_message_accepted === true) {
        check(receipt.channel === pending.channel && receipt.destination === pending.destination, "receipt_destination_mismatch");
        const failed = await readState(options);
        check(same(failed.state.pending_digest, pending), "pending_digest_changed");
        await writeVerified(options, failed, { ...failed.state, pending_digest: null });
        return { ok: false, code: "delivery_rejected", sendStarted, accepted: false, pending: null };
      }
      // Send and finalization stay in the same orchestration call; never resend here.
      const finalized = await finalizeAccepted({ ...options, expectedPending: pending, receipt });
      return { ...finalized, runId: pending.run_id };
    } catch (error) {
      return {
        ok: false,
        code: error.message || "delivery_failed",
        sendStarted,
        accepted: receipt?.accepted === true,
        receipt,
        action: sendStarted ? "reconcile_pending_without_resending" : "inspect_state_without_sending"
      };
    }
  }

  function slackReceipt(result, destination) {
    check(!result?.isError, "slack_outcome_unconfirmed");
    let payload;
    for (const item of result?.content || []) {
      if (item.type !== "text") continue;
      try {
        const parsed = JSON.parse(item.text);
        if (parsed.message_link && parsed.message_context) payload = parsed;
      } catch { /* Ignore non-receipt text blocks. */ }
    }
    const context = payload?.message_context;
    check(context?.channel_id === destination && /^\d+\.\d{6}$/.test(context.message_ts), "slack_receipt_invalid");
    const suffix = `/archives/${destination}/p${context.message_ts.replace(".", "")}`;
    check(/^https:\/\/[a-z0-9.-]+\.slack\.com\//i.test(payload.message_link) && payload.message_link.endsWith(suffix), "slack_permalink_mismatch");
    return {
      accepted: true,
      channel: "slack",
      destination,
      message_id: context.message_ts,
      permalink: payload.message_link,
      accepted_at: new Date(Math.floor(Number(context.message_ts) * 1000)).toISOString()
    };
  }

  return { deliver, finalizeAccepted, finalizeState, messageUrls, prepareState, slackReceipt };
})();

if (typeof module !== "undefined" && module.exports) module.exports = LinkedInDigestDelivery;
LinkedInDigestDelivery;
