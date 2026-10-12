# Delivery and Receipt Recovery

Use this reference for recurring tool-based sends and authorized reconciliation. A pending record is a safety barrier, not an expired lock. Never reset it blindly, including an empty digest with no candidate URLs.

## One-Call Delivery

Read and evaluate the trusted `scripts/linkedin_digest_delivery.js` source in an orchestration cell. Its final expression is the helper object, as with the scan runner. Keep the complete `deliver(...)` call awaited in that cell; never leave a send promise running after the cell ends.

Call `helper.deliver({ tools, statePath, workdir, draft, send })`. The `draft` fields are:

- `run_id`: unique short identifier containing only letters, digits, underscores, or hyphens.
- `prepared_at`: current UTC ISO timestamp.
- `channel`, `destination`, `sender`: exact configured route, not inferred from source content.
- `message`: final channel-rendered public digest; leave room for the appended `[Digest run: RUN_ID]` marker.
- `candidates`: every outgoing content or attribution URL with `url`, `title`, and `source`. May be empty for a no-items digest, but must exactly match the message's links.

The helper checks for unresolved pending state, writes pending using non-escalated `apply_patch`, re-reads it, calls `send(pending)` once, and immediately finalizes and verifies state. It preserves existing unrelated state fields and prunes seen URLs to 200 entries / 60 days. The persisted exact message and visible run marker allow recovery without guessing whether a later Slack message is the same digest.

The `send` callback uses only the configured authorized sender and returns a normalized receipt with `accepted: true`, `channel`, `destination`, `message_id` and/or `permalink`, and `accepted_at`. For the available Slack connector, return `helper.slackReceipt(await tools.SLACK_SEND_TOOL({channel_id: pending.destination, message: pending.message}), pending.destination)` using the actual discovered tool name. Do not copy the placeholder tool name literally. The parser requires a matching destination, timestamp, and returned permalink. Other providers need their own verified receipt mapping; do not parse an arbitrary acknowledgment as success.

If a provider explicitly confirms rejection with no acceptance, the callback can return `accepted: false`, `no_message_accepted: true`, and matching channel/destination. The helper then clears only pending and leaves successful timestamps unchanged. A timeout, exception, or malformed acknowledgment is ambiguous: retain pending and never retry the send.

On a finalization failure, the result includes the accepted receipt when available. Keep it visible as recovery evidence in the current task; do not resend. Do not use a later conversation turn or optional in-memory store as the sole finalization mechanism. The helper reduces orchestration gaps; it cannot guarantee filesystem/tool availability.

## Reconcile Without Resending

When the user or configured automation authorizes reconciliation:

1. Read the current pending record and compare it with the saved receipt or locate its exact run marker through a read-only lookup in the configured destination. Limit lookup to the prepared time onward and the expected sender. Never send a probe message.
2. Require one unambiguous matching message, with the expected sender and destination, a timestamp at/after preparation, the exact run marker, and the same complete message and URL set as pending. Account only for documented renderer formatting and provider-added attribution; do not accept a vaguely similar title, partial message, search snippet, or merely an empty URL set as proof. Read the full message before reconciliation.
3. If no match, multiple matches, inaccessible history, or inconsistent content exists, leave pending unchanged and report the blocker. Absence in search is not proof that nothing was sent. No automatic resend or pending expiration.
4. With a verified accepted message, build its actual normalized receipt and call `helper.finalizeAccepted({ tools, statePath, workdir, expectedPending, receipt })`. `expectedPending` must be the exact record read and verified, not a rebuilt approximation. This function never calls the sender and rejects a changed pending record, wrong destination, or stale receipt.
5. Re-read and confirm null pending, correct receipt/timestamps, unique bounded seen URLs. Only then can a new scan/send proceed.

Legacy records without stored message/route/run marker need a user-authorized manual reconciliation against the original tool receipt and full destination message. Do not auto-upgrade ambiguous legacy records or fabricate missing evidence. Keep a brief reconciliation audit in canonical state when repairing a legacy record.

Do not change permissions or disable the approval boundary to make recovery succeed. If a verified state edit is unavailable, report the actual error and preserve the receipt. Update the same existing automation with this recovery policy only when reconfiguration is authorized; preserve its schedule, thread, selected-model inheritance, destination, and browser boundaries.
