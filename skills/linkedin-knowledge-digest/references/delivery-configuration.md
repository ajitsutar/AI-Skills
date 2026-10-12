# Configurable Delivery

The skill prepares content and uses tools already available to the agent. It does not bundle messaging credentials or guarantee that any particular channel is connected. Slack is optional. Do not install providers, collect secrets in chat, change recipients, or send setup/test messages merely to enable a channel.

## Resolve Preferences

Use the current explicit request, then the user's saved workspace configuration, then the defaults below. Keep existing approved delivery settings unless the user asks to change them. With no configured destination, default to a local draft and ask for channel and recipient only when sending is requested. If unattended setup lacks those answers, report a blocker without guessing.

Store preferences in a user-chosen workspace JSON file, separate from skill source and transaction state. This is an agent-read configuration contract, not an automatic provider integration. Resolve it before calling the runner and pass `content.focus` as `contentFocus` (`ai` or `general`). Other preferences guide source review and rendering after extraction.

Example local draft configuration:

```json
{
  "schema_version": 1,
  "content": {
    "focus": "ai",
    "topics": ["AI research", "applied AI engineering", "AI governance"],
    "max_items": 5,
    "max_source_age_days": 7,
    "allow_older_foundational": false,
    "expand_beyond_linkedin": false
  },
  "delivery": {
    "channel": "local",
    "mode": "draft",
    "target": null,
    "sender": null,
    "max_chars": null,
    "link_format": "linked_title"
  }
}
```

Accept `channel` values `slack`, `whatsapp`, `sms`, `imessage`, `email`, `local`, or `custom`. Accept `mode` values `draft` or `send`. Reject unknown values, invalid types, non-positive item/age/length limits, and unresolved placeholders before enabling unattended delivery. `target` is an exact destination identifier understood by the sender; `sender` identifies a real available tool/connector/provider, never an API key. Secrets remain in the host's credential store. For `custom`, also record the authorized renderer/format and success-receipt contract. The local channel supports draft mode only.

For example, configure WhatsApp with a verified WhatsApp recipient and an available WhatsApp sender; configure SMS with a verified SMS destination and an SMS-capable sender. The same phone number does not make those services interchangeable. "Send to me" still requires resolving the user's exact destination, not copying another installation's contact.

Optional discovery preferences belong under `content.discovery`, independently of delivery. When public expansion is enabled, use the configured official `public_publishers` and `primary_indexes`, an explicit `restrict_public_publishers` boundary, and the separately configured `allow_linkedin_discovered_external` exception. A restricted list must be nonempty and its indexes must belong to verified allowed publishers. Positive `max_candidates`, `max_source_reads`, and `target_max_per_publisher` limits bound work; `recover_public_source_links` and `report_coverage_limitations` control source recovery and coverage notes. Read `article-quality.md` for the selection procedure. Do not treat enabling discovery as authorization to change the delivery route or to bypass a failed required LinkedIn scan.

`delivery.link_format` supports `linked_title` (the default for rich-text channels) and `plain_url`. Use `plain_url` when the user wants links to survive copying into plain-text editors: show each article title as text and put its complete source URL on a separate line. Do not hide the only URL behind a title or shorten it. WhatsApp and SMS/iMessage always use full plain URLs. Include the visible URLs in the character budget and final transaction audit.

Some Slack connectors shorten even explicit URL labels during Markdown conversion. For copy-safe Slack output on those connectors, retain a clickable title or `Read article` link and repeat the exact full URL in a fenced plain-text block on its own line. The literal copy is deliberate, not a second recommendation; audit the unique URL set. Verify the delivered representation with a read-only message read when available. Do not assume bare URLs or Markdown links labeled with the full URL remain visible unchanged, and do not resend automatically when formatting verification fails.

## Channel Contract

| Channel | Required capability | Rendering |
| --- | --- | --- |
| Slack | Authorized connector and exact DM/channel destination | Use the sender's expected mrkdwn; `<URL|article title>` when supported. |
| WhatsApp | Authorized WhatsApp tool or approved provider, verified recipient, and any provider-required outbound consent/template configuration | Short title/takeaway plus the full plain source URL. Do not use Slack link syntax. |
| SMS | Authorized SMS-capable provider or configured local Messages workflow, verified destination | Default to one or two concise items with full plain URLs; use the configured character budget and sender-reported segment limits. |
| iMessage | Authorized local Messages tool/workflow or compatible sender and verified recipient | Concise text plus full plain URLs. Do not silently switch to SMS. |
| Email | Authorized email tool and exact recipient; drafts may remain local | Subject, concise linked reading list, and plain-text URLs when rich links are unsupported. |
| Local | No external sender | Return a Markdown draft in the current conversation, or save only to a user-requested path. |
| Custom | User-selected available sender, exact destination, known format and receipt semantics | Preserve exact links and the same privacy and transaction guarantees. |

Use an applicable installed channel skill when one is available (for example, a local Messages skill). Its presence alone does not authorize changing this digest's configured channel. Check the actual sender's capabilities and current service requirements at setup; do not assume WhatsApp, SMS, and iMessage share limits or receipts. Do not switch browser paths to reach a messaging service.

## Preflight and Render

1. Resolve channel, mode, exact target, and sender. In send mode, confirm the sender is available within the user's approval boundary before a costly scan. Missing channel support is a setup blocker, not permission to fall back to Slack.
2. Read existing canonical state; any non-null `pending_digest`, including legacy records without a channel, blocks a new send. Changing channels does not clear pending transactions or reset seen URLs.
3. Render only selected public articles. Never export private inbox text, private sender details, private thread URLs, or private ranking signals just because a different destination was selected.
4. Fit the configured length budget by shortening prose and dropping the lowest-ranked whole items. Never truncate URLs or silently use a URL shortener. SMS may bill multiple segments; do not promise one segment from character count alone. If even one complete link cannot fit, stop with a concise blocker.
5. Default to a single digest message. Multiple messages/recipients need explicit configuration and a delivery plan recording each part/destination and its URLs before sending. Do not fan out implicitly. When tooling cannot safely track partial outcomes, use separate configured automations/state files or a single destination instead.
6. Audit the final rendered message: every recommendation links to the actual source, no placeholders, and pending URLs match all outgoing content/attribution URLs exactly. Drafts do not create pending records, call senders, or advance seen/success timestamps.

## Channel-Neutral Transaction

For each configured destination, use the skill's prepare/send/finalize protocol. `pending_digest` includes `run_id`, `prepared_at`, `channel`, `destination`, `sender`, and `candidates` containing every outgoing URL with title/source. Send once using that sender. Retain pending state on an ambiguous result; no retries via another tool, service, or recipient.

After explicit provider acceptance, record `last_delivery` with `channel`, `destination`, `message_id` and/or `permalink` when available, `accepted_at`, and `status: "accepted"`. Do not invent a Slack-style permalink for SMS or WhatsApp. A sender that provides explicit acceptance but no id can record a null id and its actual receipt type; a sender with no trustworthy success signal is unsuitable for unattended delivery. Distinguish provider acceptance from delivered/read status.

Move all pending URLs into `seen`, set successful timestamps, prune according to the existing retention policy, and clear pending in one verified state edit. If finalization fails, retain pending and stop future runs until reconciled. If the sender explicitly proves nothing was accepted, clear only pending and leave successful timestamps unchanged.

Keep legacy fields such as `last_slack_message_link` intact when using a different channel; update them only for a corresponding Slack receipt. Never overwrite canonical state during a skill update. Existing automation prompts may hard-code Slack and runtime helper paths: change those only as part of an authorized automation reconfiguration, preserving schedule, continuity, model inheritance, browser restrictions, and unresolved transactions.
