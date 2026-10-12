---
name: linkedin-knowledge-digest
description: Find high-quality AI articles, research, and analysis from LinkedIn or supplied content and produce a concise daily reading digest with direct source links. Use for LinkedIn knowledge monitoring, feed/article triage, or configurable delivery through available authorized Slack, WhatsApp, SMS/iMessage, email, or local tools. Broader topics and local-only inbox triage are optional.
---

# LinkedIn Knowledge Digest

## Overview

Build a reading list, not a recap of social activity. Default to high-quality AI articles, research papers, engineering reports, and thoughtful analysis with direct links to the actual sources. Favor evidence, useful technical detail, and clear implications over popularity. Preserve a user's explicitly chosen broader topic scope.

Resolve bundled resources relative to the directory containing this `SKILL.md`, never relative to the current working directory.

For redistribution or an origin review, see [LICENSE](LICENSE),
[provenance](PROVENANCE.md) and [third-party notices](THIRD-PARTY-NOTICES.md).

Do not expose private ranking criteria unless the user asks. Use the user's priority people, organizations, roles, topics, and recency preferences as background scoring signals.

## Inputs

Collect or infer these inputs:

- Access method: authenticated browser session, exported/pasted content, screenshots, or connector output.
- Content focus: AI by default, specific AI topics, or a broader knowledge digest; desired item count and source-age window.
- Delivery configuration: channel, draft/send mode, exact recipient or destination, available authorized sender, and length limits. Slack is one option, not a dependency or implicit default.
- Priority signals: people, companies, schools, communities, industries, technical topics, roles, or keywords.
- Exclusion rules: categories the user does not want to see.
- Link requirement: whether every referenced person, post, article, company, or message needs a clickable link.
- State policy for recurring runs: canonical state path, writable workspace, duplicate horizon, and whether to stop if state cannot be updated.
- Browser policy for authenticated scans: approved browser, allowed automation path, dedicated-window requirement, and forbidden fallbacks.
- LinkedIn access status: whether the user has an approved LinkedIn developer application and the exact read scopes granted to it.
- Automation continuity: whether recurring runs must remain attached to the current task/thread or run as standalone jobs.
- Delivery privacy policy: which private inbox fields, if any, may cross into the selected delivery service.

If authenticated access is unavailable, do not guess. Ask the user to restore access or provide pasted/exported LinkedIn content.

Read [article-quality.md](references/article-quality.md) for AI source selection and verification. Read [delivery-configuration.md](references/delivery-configuration.md) when setting up, changing, or using a delivery channel. Keep user preferences and recipient identifiers outside the public skill. A skill update alone does not authorize changing a live schedule, recipient, channel, or sending a test message.

## Access Strategy

Prefer access methods in this order:

1. An official LinkedIn API for which the user's application has the required approved read scope and the intended use is permitted.
2. User-provided exports, pasted posts, saved links, or other content the user is authorized to process.
3. Browser extraction only when the user has separately confirmed that LinkedIn permits the automation for this account and use case.

OpenID Connect `profile` and `email` scopes identify the authenticated member; they do not provide the member's home feed or inbox. Publishing access such as `w_member_social` also does not grant read access. Do not represent restricted member, organization, messaging, compliance, or marketing APIs as generally available. Verify the application's granted products and scopes before selecting an API route.

Do not recommend headless Chrome as a way to conceal or bypass website automation. Headless mode still performs automated access and normally requires a separate browser process and isolated user-data directory. Use it only for an authorized test or integration where LinkedIn permits the access and the user does not need the already-running Chrome session.

## Workflow

1. Confirm access and scope.
   - Resolve the user's content and delivery preferences. For send mode, preflight the configured sender and destination before scanning; do not collect a digest for an unavailable channel or silently choose another one.
   - Use the authenticated browser/session when available.
   - If browser automation is used, scroll enough to sample multiple feed bands.
   - Check inbox/messages only if the user requested inbox triage.
   - For recurring automations, read the canonical state before scanning. Treat a non-null `pending_digest` as possibly delivered: stop new scans/sends. When receipt reconciliation is authorized, follow [delivery-recovery.md](references/delivery-recovery.md); otherwise report the blocker without advancing state. Never clear pending merely because it is old or has zero URLs.
   - If the run cannot read or later update required state, stop before producing a content digest that could duplicate old items.

2. Build a background priority map.
   - Identify the user's specified priority people, organizations, groups, topics, and recently interacted-with contacts.
   - Treat this as ranking context, not as a visible section by default.
   - Boost posts from trusted people only when the post itself contains useful knowledge.

3. Filter aggressively.
   - In AI mode, select AI research, model evaluations, engineering/architecture, data, safety/governance, and consequential product or market analysis. A generic AI keyword is not enough; the linked source must carry the substance.
   - Include articles, reports, research, product or market shifts, technical perspectives, architecture notes, governance/compliance commentary, thoughtful analysis, and substantive discussions.
   - Ignore career milestones, job changes, work anniversaries, promotions, graduation/congratulation posts, hiring posts, generic motivational posts, personal updates, low-value product ads, sales pitches, real estate pitches, finance-service pitches, generic recruiting, and pure self-promotion.
   - Make an exception only when the item links to or summarizes a substantive article, report, research finding, or transferable insight.

4. Capture links.
   - Prefer the direct article, paper, report, or technical source URL over the LinkedIn share. Keep the share as optional attribution, not the main reading link.
   - Open candidate source links through an approved read path and assess the source itself. Record its title, publisher/author, date, and what was actually accessible; never imply an unread article was reviewed.
   - Every recommendation must include an exact public content URL. A substantive LinkedIn article or essay can qualify when it contains the insight itself; profiles, company homepages, and private message threads cannot substitute for a reading link.
   - Deduplicate multiple shares of the same source and multiple articles repeating the same announcement. Verify redirects/canonical links before using them; do not invent or shorten URLs.
   - If no content/action link is visible or recoverable, exclude the item entirely and do not mention it by name.

5. Rank by value.
   - Rank by AI/topic relevance, strength of evidence, source credibility, novelty, and practical implications, in that order. Engagement and priority-network membership are secondary tie-breakers, never proof of quality.
   - The scan runner accepts `contentFocus: "ai"` (default) or `"general"`. Its keyword/evidence hints are only a shortlist, not source verification; apply the article-quality reference before selecting final items.
   - Do not rank a post highly just because it is from a priority person.

6. Produce a concise digest.
   - Default to at most five reads, fewer when quality or channel length demands it. Do not fill a quota with weak links.
   - Lead each item with its linked article title and source. Add the main finding and why it is worth reading, with an important caveat when needed.
   - Render for the configured channel and `delivery.link_format`. For copy-safe `plain_url` output, put each complete URL on its own line after the article title or takeaway, including on Slack. For SMS, prefer one or two complete linked items over truncating URLs or sending extra messages without authorization.
   - Separate inbox triage from feed/article recommendations.

7. Update state after delivery.
   - Draft mode never calls a sender or advances delivery/seen state. Send mode uses the configured channel's sender, not a hard-coded Slack tool. Record acceptance accurately; provider acceptance is not proof of recipient delivery or reading.
   - For recurring runs, treat the run as successful only after extraction, delivery, and state update all succeed.
   - Immediately before delivery, write a `pending_digest` record containing a run identifier, preparation time, channel, exact destination, sender identifier, and every outgoing URL (including any optional attribution links). Re-read it and verify it exactly matches the final channel-rendered message.
   - Send exactly once. After the delivery tool returns success, move the pending URLs into `seen`, record the delivery timestamp and link/id, advance `last_successful_run_at`, prune old state, and clear `pending_digest`.
   - If delivery fails, do not retry through an alternate delivery path and do not advance successful-run state. Clear `pending_digest` only when the delivery tool proves that no message was accepted; retain it when the outcome is ambiguous.
   - If finalization fails after delivery succeeds, leave `pending_digest` intact. The next run must stop rather than risk sending the same digest twice.
   - For tool-based delivery, use `scripts/linkedin_digest_delivery.js` to prepare, verify, send once, and finalize within one orchestration call. It stores the exact outgoing message and a unique run marker for evidence-based reconciliation. Read [delivery-recovery.md](references/delivery-recovery.md) for the call contract and recovery checks.

## Production Automation Guardrails

Use these stricter rules when building or running an unattended LinkedIn digest automation:

- Preserve automation identity. When the user requests same-task continuity, keep exactly one active thread-bound/heartbeat automation and update it by id. Do not silently replace it with a detached scheduled job. Check for superseded duplicates before and after automation changes.
- Require single-flight execution. Configure the scheduler to allow at most one active run for each canonical state file and to skip, rather than overlap, a new trigger while that run is active. If the scheduler cannot guarantee non-overlap, do not enable unattended delivery; limit the workflow to a user-supervised one-shot run.
- Keep a zero-surprise approval boundary. Use only the access, browser, delivery, and workspace operations the user approved. If a required operation is unavailable, stop gracefully and leave successful-run state unchanged.
- Preflight canonical state. Keep it inside the configured writable workspace and use normal non-escalated file tools. Do not infer failure from stale permission metadata; use the prepared `pending_digest` edit as the authoritative writeability test immediately before delivery.
- Preserve duplicate prevention. Maintain `last_successful_run_at`, `last_digest_sent_at`, channel-neutral `last_delivery` metadata (channel, destination, message id or permalink, acceptance time), optional `pending_digest`, and a bounded `seen` list of recently reported URLs with titles, sources, and timestamps. Keep roughly the latest 200 URLs or 60 days, whichever is smaller. Preserve legacy state fields when updating existing deployments; do not require a Slack permalink for other channels.
- Use a single authenticated browser path. When the user specifies Chrome and local AppleScript, use only that approved path. Do not fall back to other browsers, Computer Use, screenshots, GUI clicking, extension repair, profile inspection, or browser-profile workarounds.
- Isolate the browser session. Launch one new automation-owned window at the start of each run and keep one LinkedIn tab in that window. Do not navigate, select, close, scroll, or execute JavaScript in the user's pre-existing browser windows or tabs. Close only the owned window.
- Respect service and access boundaries. Do not bypass CAPTCHA, rate limits, authentication checkpoints, bot detection, account restrictions, or LinkedIn access controls. Stop and hand control back to the user when a checkpoint requires their action.
- Keep AppleScript static and small. Never inline, interpolate, escape, or embed JavaScript source inside generated AppleScript. Materialize the scan transport once with `scripts/materialize_linkedin_scan_transport.js`; it copies the helper files into the automation workspace and writes a tested JSON array of complete AppleScript source lines with absolute runtime paths.
- Execute the materialized AppleScript manifest verbatim. Pass each stored line as its own `osascript -e` argument under the approved `tell application "Google Chrome"` prefix. Do not regenerate or rewrite AppleScript in an automation run. Validate the manifest with `scripts/validate_linkedin_scan_transport.js` after materialization and whenever its helpers change.
- Use `scripts/linkedin_scan_orchestrator.js` for Codex browser runs. Load and evaluate it inside the same orchestration cell that launches and polls `osascript`, then render only its compact result. It reads state before opening Chrome, validates all required feed payloads, degrades optional sources independently, applies state and recency filtering, and removes private inbox details from its output.
- Make extraction bounded and durable. Use `scripts/linkedin_digest_candidates.js` and, when inbox triage is requested, `scripts/linkedin_messages_candidates.js`, or preserve their limits in equivalent extraction code. Deduplicate across bands and cap emitted posts, news, links, and text so the complete result remains comfortably below the orchestration transport limit.
- Treat each feed candidate's `contentUrls` as a collection. Do not assume the feed helper returns a singular `postUrl`; select and audit the exact substantive content URL from `contentUrls`.
- Return primitive JSON text. Browser JavaScript passed through AppleScript or similar bridges must return `JSON.stringify(...)`, not an object, array, promise, `undefined`, or another non-primitive result.
- Accumulate long-running output completely. When browser extraction yields a background session/process, poll it until exit and combine every chunk before parsing. Validate required feed JSON and completion metadata before filtering. Keep parsing and compaction in that same orchestration cell and render only the compact public candidate summary. A run-scoped object store may be used as an optional cache, but later steps must never depend on retrieving it; cross-cell object stores are not a transaction boundary.
- Degrade optional sources independently. Feed extraction is required. A malformed or unavailable optional connections/inbox result must not suppress or trigger a retry of an otherwise valid public-feed digest; normalize it to an explicit unavailable result and continue.
- Scan incrementally. Use the previous successful run plus an overlap window, but do not rely on one stale feed item as a stop condition because LinkedIn Top feed is not chronological. Check at least several feed bands and cap the scan at a reasonable number of bands.
- Audit links immediately before delivery. Remove every bullet that lacks an actual content/action link. Profile links may support attribution but must not be the only link for an item.
- Protect private inbox data. Unless the user explicitly authorizes it and the destination permits it, do not export private message text, sender details, or private thread links to another service. Prefer public action URLs or a local-only triage note.
- Keep failure behavior conservative. Do not retry a required extraction failure in a second browser window during the same run. If authenticated access, required extraction, delivery, or state finalization fails, do not advance successful-run state.

## Digest Format

Use this channel-neutral draft shape unless the user requests another format. Example placeholders below are not source evidence or outgoing links:

```markdown
**Daily AI Reads - [date]**

**Worth reading**
- [Actual article title](https://example.org/replace-with-verified-source) - Publisher/author, publication date. Main finding and why it matters. Caveat or abstract-only label when applicable.

**Additional perspective** (optional; no duplicate reads)
- [Substantive essay title](https://example.org/replace-with-verified-essay) - Source and a useful contrasting perspective.

**Inbox** (only when requested)
No qualifying public linked item.
```

Use Markdown links for local/email drafts, Slack mrkdwn when required, and full plain URLs for WhatsApp and SMS/iMessage. The configured `delivery.link_format` takes precedence; see the delivery reference for preserving literal URLs when a Slack connector shortens link labels. Never send the template placeholders. Omit empty optional sections; if nothing meets the quality bar, say so briefly without padding the digest. An existing user-specified section layout takes precedence.

## Quality Bar

Before finalizing, check:

- Every included item teaches something, points to a useful article/report, or has a clear action.
- AI is the default focus, and direct source links are visible in every reading recommendation.
- Source claims were checked against accessible content; preprints, vendor claims, and abstract-only access are labeled when material. Engagement did not substitute for evidence.
- No visible career milestone, job-anniversary, new-job, generic congratulations, hiring-only, or self-promotion item slipped in.
- Each included bullet has a complete exact public content link after channel rendering, and duplicate stories are collapsed.
- The digest is short enough to read quickly.
- Ranking reflects the user's interests without revealing private heuristics unnecessarily.
- The selected destination and sender are configured, available, and authorized; no credentials, private inbox details, or unapproved fallback channels are used.

## Automation Prompt Template

Read `references/automation-prompt-template.md` when creating a reusable scheduled automation prompt.

## Included Extraction Helpers

- `scripts/linkedin_digest_candidates.js` extracts bounded, deduplicated, knowledge-bearing feed candidates and returns primitive JSON text with a validated-page flag and cumulative feed-band count.
- `scripts/linkedin_messages_candidates.js` extracts a bounded local inbox candidate list and returns primitive JSON text. Apply the delivery privacy policy before exporting any result.
- `scripts/linkedin_connections_candidates.js` extracts a bounded recent-connections list for private ranking context.
- `scripts/linkedin_feed_reset.js` and `scripts/linkedin_feed_scroll.js` reset the bounded feed session and advance one feed band while returning primitive JSON text.
- `scripts/materialize_linkedin_scan_transport.js` copies the helpers into the automation workspace and creates the static AppleScript manifest used by recurring runs.
- `scripts/validate_linkedin_scan_transport.js` verifies window isolation, cleanup paths, helper availability, and the no-inline-JavaScript invariant.
- `scripts/linkedin_scan_orchestrator.js` performs state preflight, manifest execution, complete chunk collection, transport validation, public-candidate compaction, and privacy-safe optional-source degradation in one orchestration call.
- `scripts/linkedin_digest_delivery.js` performs verified prepared-state edits, single-attempt delivery, receipt validation, finalization, and receipt-only recovery without a resend.
