# Notification Playbook

Use this reference before sending any external alert.

## Notification Gate

Send external notifications only when all are true:

- candidate is fully verified on the selected offer
- price satisfies the configured threshold
- candidate is not a duplicate according to memory and in-thread history
- the user explicitly authorized the configured channel
- the notification body follows channel limits and privacy requirements
- an atomic memory `claim` succeeded for this canonical offer

If any check fails, report in chat only.

For recurring or potentially concurrent runs, use this sequence with the same memory path, deal JSON, and `--config` on every applicable command:

1. Run `deal_memory.py claim` immediately before sending. Stop when status is `duplicate` or `already_claimed`.
2. Use the returned `deal_key` as the notification provider's idempotency key when supported.
3. Send only through user-authorized channels, tracking the result for each one. One claim protects the complete multi-channel notification transaction.
4. If any channel confirms delivery, run `deal_memory.py commit --claim-id <id>` and record all successful, failed, and skipped channels in the notes. Treat partial delivery as delivered; do not automatically retry failed channels.
5. Run `deal_memory.py release --claim-id <id>` only when every attempted provider proves that no notification was accepted. If any result is ambiguous, retain the claim and stop for manual provider-state review. A claim remains blocking after its advisory expiry; expiration never proves nondelivery.

The compatibility `record` command is safe for a single non-concurrent run, but a separate `check` followed by `record` is not a safe notification gate for recurring workers.

## Chat Report

When a new deal qualifies, start with:

```text
BUY SIGNAL
```

Include:

- item label and verified attributes
- item price and shipping if shown
- condition evidence
- seller/store
- direct buy link
- external notification status
- memory update status

When a duplicate qualifies, use:

```text
Already alerted
```

Then include current price/status, buy link, and "notification skipped as duplicate."

## SMS Email Gateways

Email-to-SMS gateways often mangle links and long strings. Unless the user explicitly permits URLs in SMS:

- do not include URLs, domains, protocols, tracking IDs, or long product IDs
- keep the body under the configured character limit, usually 70 characters
- use plain ASCII
- end with a chat-link cue such as `Link in chat.`

Example:

```text
BUY M3 16 36/512 $1483 Amazon Good. Link in chat.
```

Always post the full direct buy link in chat when sending SMS. Never send an SMS-only alert.

## Email

Use plain text unless the available email tool supports richer bodies and the user requested them. Include the direct buy link in normal email unless the user asks to avoid links.

## Webhook

Use webhooks only when the user provides or configures a destination. Do not expose secrets in reports. Prefer environment variables or connector-managed credentials.

## Memory Update

A pre-send pending claim is a short-lived reservation, not an alert record. Add to `alerts_sent` only after a successful authorized notification. Record:

- stable deal key
- store
- product URL
- item label or model
- selected variant fields
- condition
- seller
- price
- notification date/time
- notes with the verification summary

If every external notification provably fails before acceptance, release the pending claim and do not mark the deal as alerted. If one channel succeeds and another fails, commit once with per-channel status and do not resend automatically. If any provider outcome is unknown, leave the claim in place so a later run fails closed until the user verifies provider state. A configured chat connector counts as delivery only when the host confirms that the chat message was posted; otherwise chat alone counts only when the user explicitly says so.
