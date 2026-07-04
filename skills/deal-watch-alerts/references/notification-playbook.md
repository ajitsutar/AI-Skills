# Notification Playbook

Use this reference before sending any external alert.

## Notification Gate

Send external notifications only when all are true:

- candidate is fully verified on the selected offer
- price satisfies the configured threshold
- candidate is not a duplicate according to memory and in-thread history
- the user explicitly authorized the configured channel
- the notification body follows channel limits and privacy requirements

If any check fails, report in chat only.

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

Update memory only after a successful external notification. Record:

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

If external notification fails, do not mark the deal as alerted unless the user explicitly says the chat report alone counts as an alert.
