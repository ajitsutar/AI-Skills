# Automation Prompt Template

Use this template when creating a scheduled LinkedIn digest automation. Replace bracketed placeholders with user-specific values. Keep private details in the user's automation configuration, not in the public skill.

Read `article-quality.md` and `delivery-configuration.md` in this directory before setup. Resolve and validate the user configuration first; do not copy this template over a live automation or migrate its state as part of a skill update. Sending requires a configured, available, authorized sender; drafting does not.

```text
Find high-quality AI articles, papers, reports, and analysis in my authorized LinkedIn sources and produce a concise daily reading digest with direct source links. Use [USER_CONFIG_PATH] for topics, item count, source-age window, channel, draft/send mode, exact destination, sender, and length budget. Preserve explicitly configured broader topics.

Delivery policy:
- Resolve configuration using my current explicit instructions, then saved preferences, then skill defaults. With no configured delivery route, prepare a local draft; never assume Slack.
- Supported channel choices are Slack, WhatsApp, SMS, iMessage, email, local draft, or an explicitly configured custom sender. Support depends on available authorized tools; a phone number alone is not a configured sender.
- In send mode, preflight the configured sender and exact destination before scanning. Missing channel support is a blocker, not permission to use a different service or recipient. Do not send setup/test messages unless requested.
- Use channel-native formatting and the configured `delivery.link_format`. Use direct linked titles where supported by default; for copy-safe `plain_url` output, show each complete URL on its own line, including on Slack. WhatsApp and SMS/iMessage always use full plain URLs. Fit length limits by dropping low-ranked whole items, never by truncating URLs. Do not split or fan out unless explicitly configured and each part/destination can be tracked safely.
- In draft mode, show the draft without a sender call, pending record, or changes to seen/success timestamps. Apply the transaction below only in send mode.

Scheduling and task-continuity policy:
- [CONTINUITY_POLICY: for example, continue in this same task using one existing heartbeat/thread-bound automation, or run as a standalone job].
- Inherit the model and reasoning effort currently selected by the user for this task; do not pin or override them.
- When same-task continuity is required, update the existing automation by id. Do not create a duplicate or convert it to a detached job as a workaround for permissions, state, browser, or delivery limitations.
- Before and after changing the automation, inspect the automation registry for matching ids/names and verify the intended record is active and targets the correct task/project.

Approval and failure policy:
- Use only [APPROVED_OPERATIONS]. Do not request escalation or switch to an unapproved browser, delivery service, filesystem location, or automation type.
- If a required action is unavailable under this policy, stop gracefully, leave successful-run state unchanged, and send only [APPROVED_BLOCKER_NOTIFICATION].

State and duplicate-prevention policy:
- Configure this automation for single-flight execution: at most one active run may use [CANONICAL_STATE_PATH], and a trigger that arrives while a run is active must be skipped rather than overlapped. If the scheduler cannot guarantee that, stop without enabling unattended delivery.
- Use [CANONICAL_STATE_PATH] as the canonical state file. Read it before scanning.
- Store `last_successful_run_at`, `last_digest_sent_at`, channel-neutral `last_delivery` metadata, optional `pending_digest`, and a bounded `seen` list of recently reported URLs with titles, sources, and `reported_at` timestamps. Preserve legacy fields; non-Slack delivery does not require a Slack permalink.
- Keep roughly the latest 200 URLs or 60 days, whichever is smaller.
- Reading and updating a canonical state file inside a writable workspace is allowed when the agent's normal non-escalated filesystem tools are available. Do not classify workspace state reads/writes as browser shell commands or approval-gated actions.
- Use the agent's normal structured file-edit tool for state updates (for example, Edit or Write in Claude Code, or `apply_patch` in Codex). Do not use shell redirection, escalated shell writes, or out-of-workspace state writes.
- If `pending_digest` is non-null at the start of a run, treat its URLs as possibly already delivered. Stop new scans/sends. If [RECEIPT_RECONCILIATION_POLICY] authorizes read-only receipt verification and state finalization, follow `references/delivery-recovery.md`; continue only after one unambiguous matching delivery is finalized. Otherwise report the unresolved transaction. Never expire or blindly clear pending.
- Immediately before delivery, use one non-escalated state edit to set `pending_digest` to the run id, preparation time, channel, destination, sender identifier, and every outgoing URL with title/source. Re-read and verify exact equality with the final channel-rendered message, including optional attribution links. This prepared-state edit is the writeability test; do not create a separate probe file.
- Send exactly once using the configured sender. After explicit acceptance, move pending URLs into `seen`, record `last_delivery` with channel, destination, actual message id/permalink when available, acceptance time, and acceptance status; advance successful timestamps, prune state, and clear pending. Re-read and verify the finalized state. Do not claim recipient delivery/read status from a send acknowledgment.
- If delivery fails, do not retry through another tool and do not advance successful timestamps. Clear `pending_digest` only when the delivery tool proves that no message was accepted; retain it when the outcome is ambiguous. If finalization fails after delivery succeeds, leave `pending_digest` intact so the next run cannot duplicate the digest.
- Prefer `scripts/linkedin_digest_delivery.js` for prepare, verified single-attempt send, and finalization in one awaited orchestration cell. Persist the exact outgoing message and unique visible run marker; keep a returned receipt as recovery evidence if finalization fails. A verified recovery finalizes state only and never resends the old message.

Authenticated browser policy:
- Prefer an official LinkedIn API only when the user's developer application has the exact approved read scope required for this use case. OpenID profile/email and publishing scopes do not provide a personal home feed or inbox. Do not use undocumented endpoints or represent restricted partner APIs as generally available.
- Use only [APPROVED_BROWSER_AND_AUTOMATION_PATH] for LinkedIn access. Do not use unapproved browsers, browser profiles, Computer Use, screenshots, GUI clicking, extension repair, or other fallbacks.
- Scope any approved-command-only restriction to Chrome/browser automation commands. It must not block non-escalated workspace file reads or structured edits for the canonical state file.
- Launch exactly one new automation-owned browser window at the start of each run and keep one LinkedIn tab in it. Do not navigate, select, close, scroll, or execute JavaScript in the user's pre-existing browser windows or tabs.
- Close only the automation-owned window when the run finishes or fails.
- Do not bypass CAPTCHA, rate limits, authentication checkpoints, bot detection, account restrictions, or LinkedIn access controls. Stop for user action when a checkpoint appears.
- During automation setup, run `scripts/materialize_linkedin_scan_transport.js` once to copy the bounded JavaScript helpers into [AUTOMATION_WORKSPACE] and create [SCAN_MANIFEST_PATH]. Validate that manifest with `scripts/validate_linkedin_scan_transport.js`.
- The materialized workspace also contains `scripts/linkedin_scan_orchestrator.js`. For a Codex browser run, read and evaluate that trusted script inside one `functions.exec` cell and call its `run(...)` function with the manifest path, canonical state path, workspace, current time, overlap, byte limit, private priority organizations, and `contentFocus` from configuration (`ai` by default, or `general`). Its evidence hints are a shortlist, not verification of source claims.
- In recurring runs, load the tested JSON array from [SCAN_MANIFEST_PATH] and pass each complete line verbatim as its own `osascript -e` argument. Do not regenerate or rewrite AppleScript in the automation turn.
- Never inline, interpolate, escape, or embed JavaScript source inside AppleScript. Every `execute ... javascript` expression must use JavaScript loaded by AppleScript from a workspace file with `read (POSIX file "...")`.

Durable extraction transport:
- Use the bounded helper `scripts/linkedin_digest_candidates.js` for feed bands and `scripts/linkedin_messages_candidates.js` when inbox triage is in scope, or preserve their limits in equivalent code. Deduplicate across bands; cap posts, news, content URLs, and text; and keep the complete payload below [MAX_TRANSPORT_BYTES].
- Feed candidates expose `contentUrls`, not a singular `postUrl`. Prefer the direct substantive article/paper/report URL from that collection over its LinkedIn share. Verify the source through [APPROVED_PUBLIC_SOURCE_READ_PATH] before recommending it; a share excerpt alone is not an article review. Do not broaden discovery beyond these sources unless configuration explicitly enables that.
- Every browser JavaScript expression passed through AppleScript or another bridge must return primitive JSON text via `JSON.stringify(...)`. Never return an object, array, promise, `undefined`, or another non-primitive result.
- Keep browser launch, background-session polling, full chunk collection, required validation, state-aware filtering, and public-result compaction inside the same orchestration cell. Render the compact summary returned by `linkedin_scan_orchestrator.js`; never render the raw extraction payload.
- Do not require a later cell to retrieve data from a run-scoped object store. Such storage may be an optional cache only. The rendered compact public summary is the durable handoff to filtering and delivery.
- Required failures include a nonzero browser exit, invalid top-level/required-feed JSON, a false validated-page flag, missing or inconsistent cumulative feed-band metadata, an oversized payload, or fewer than [MIN_FEED_BANDS] successfully inspected feed bands. Do not open a second browser window or rerun the scan after a required failure in the same automation run.
- Treat connections and inbox as optional ranking/context sources. Normalize a missing or malformed optional source to `{ok:false, items:[]}` and continue with valid public-feed sections.
- Never export the orchestrator's private source inputs. Its output must contain only optional-source availability flags, an empty or independently public inbox-action list, and bounded public candidates.

Optional public discovery policy:
- Broaden beyond captured LinkedIn sources only when configuration explicitly enables it. Apply the configured publisher allowlist, official indexes, candidate/source-read bounds, and the separate exception for genuinely LinkedIn-discovered external articles described in `references/article-quality.md`.
- Inspect all configured indexes before selecting the final reads; do not stop at the first few eligible articles. Keep the source-age window independent of feed recency, deduplicate by URL and story, and report inaccessible sources or incomplete coverage without equating them with a lack of quality.
- Keep official-source discovery distinct from LinkedIn discovery in the digest. Do not substitute a public sweep for a failed required authenticated scan unless independent operation is explicitly configured.

Incremental scan policy:
- Scan from the top of the feed, with a [OVERLAP_WINDOW] overlap before the previous successful run.
- LinkedIn Top feed is not chronological, so do not stop on one stale post. Check at least several feed bands and cap the run at [MAX_FEED_BANDS] feed bands.
- Skip any content/action URL already present in `seen` unless there is clearly new high-value discussion or a newly linked article/report not previously reported.
- Also skip URLs in `pending_digest`. Reject older feed items outside the incremental window even when they are absent from `seen`.

Use these background priority signals when ranking items: [PRIORITY_PEOPLE_OR_GROUPS], [PRIORITY_ORGANIZATIONS], [TOPICS_OF_INTEREST], and [RECENT_INTERACTION_SIGNALS]. Treat these only as ranking context. Do not display a separate priority list unless there is an actual substantive post, article, report, or inbox item worth summarizing.

Default to AI research, model evaluations, applied AI engineering, architecture, safety/governance, and consequential enterprise/market analysis. Require a substantive accessible source, traceable claims, and a distinct useful finding or perspective. Prefer primary research and detailed technical reports; credible independent analysis may add context. Evidence and usefulness outrank engagement and familiar authors. Broader knowledge items require a configured general focus.

Verify the source title, author/publisher, publication or meaningful update date, and actual accessible content. Label abstract-only access, preprints, and vendor-reported claims when material; never summarize inaccessible articles as if read. Use the configured source-age window (seven days by default), separate from feed recency. Older foundational work is opt-in and must have a current reason to read. Deduplicate by verified source URL and underlying story, not just by LinkedIn share URL. Never invent dates, titles, or canonical links.

Explicitly ignore posts about someone starting a new job, changing jobs, celebrating N years at a job, work anniversaries, promotions, graduation or congratulation posts, hiring announcements, personal milestones, generic motivational posts, and self-promotion. Also ignore low-value product ads, lead-gen posts, real estate pitches, finance-service pitches, generic recruiting, and sales spam. Make an exception only when the post links to or summarizes a substantive article, report, research item, or clear transferable insight.

Hard link rule: every recommendation must include the actual article/paper/report title and its exact public source URL. Link the title in rich-text mode; in `plain_url` mode, display the complete URL on its own line so it survives plain-text copying. A substantive LinkedIn essay can qualify when it contains the insight itself. Profile links, homepages, signup forms, private message/thread URLs, and a share without a verified substantive source are not substitutes. Exclude an item with no qualifying link; do not send placeholders or URL shorteners.

When a Slack connector shortens URL labels, copy-safe output requires a clickable reading link plus a fenced literal copy of the exact URL. Follow the delivery reference, include both representations in the character budget, and audit their unique URL set. Verify the delivered message's literal URLs through an available read-only tool; never automatically resend because formatting verification failed.

Private inbox policy:
- Scan inbox content locally only unless the user explicitly authorizes export and the destination allows it.
- Do not send private message text, private sender details, or private thread URLs to the configured destination, regardless of channel. Include only a clearly public, non-sensitive action URL that independently satisfies the content rules; otherwise use a short no-qualifying-item line.

Produce a concise reading list, preserving any existing user-requested layout:
1. Worth reading: up to five high-quality AI sources, fewer when quality or channel limits demand it.
2. Additional perspective: optional substantive analysis that is not a duplicate of a selected source.
3. Inbox: only if requested, and only public qualifying links or a short no-item line.

For each read, include the linked article title, source, date when known, a grounded takeaway, why it matters, and a material caveat when needed. Engagement is optional and must not stand in for credibility. Omit empty optional sections; do not pad a sparse day with low-quality reads. SMS normally contains one or two complete linked items. If authenticated LinkedIn access is unavailable, notify me instead of guessing or silently switching to broader web research.

Before sending, perform a final link audit and remove every bullet that lacks an actual content/action link. Then execute the prepared-state, single-delivery, and finalization transaction above.
```
