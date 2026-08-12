# Automation Prompt Template

Use this template when creating a scheduled LinkedIn digest automation. Replace bracketed placeholders with user-specific values. Keep private details in the user's automation configuration, not in the public skill.

```text
Review my authenticated LinkedIn account and produce a concise priority digest, then send or draft it to [DELIVERY_TARGET].

Scheduling and task-continuity policy:
- [CONTINUITY_POLICY: for example, continue in this same task using one existing heartbeat/thread-bound automation, or run as a standalone job].
- When same-task continuity is required, update the existing automation by id. Do not create a duplicate or convert it to a detached job as a workaround for permissions, state, browser, or delivery limitations.
- Before and after changing the automation, inspect the automation registry for matching ids/names and verify the intended record is active and targets the correct task/project.

Approval and failure policy:
- Use only [APPROVED_OPERATIONS]. Do not request escalation or switch to an unapproved browser, delivery service, filesystem location, or automation type.
- If a required action is unavailable under this policy, stop gracefully, leave successful-run state unchanged, and send only [APPROVED_BLOCKER_NOTIFICATION].

State and duplicate-prevention policy:
- Use [CANONICAL_STATE_PATH] as the canonical state file. Read it before scanning.
- Store `last_successful_run_at`, `last_digest_sent_at`, a delivery link or message id when available, optional `pending_digest`, and a bounded `seen` list of recently reported content/action URLs with titles, sources, and `reported_at` timestamps.
- Keep roughly the latest 200 URLs or 60 days, whichever is smaller.
- Reading and updating a canonical state file inside a writable workspace is explicitly allowed when normal non-escalated Codex filesystem tools are available. Do not classify workspace state reads/writes as browser shell commands or approval-gated actions.
- Use `apply_patch` or another non-escalated workspace file edit for state updates. Do not use shell redirection, escalated shell writes, or out-of-workspace state writes.
- If `pending_digest` is non-null at the start of a run, treat its URLs as possibly already delivered. Stop before scanning/sending and report the unresolved transaction through the approved blocker channel.
- Immediately before delivery, use one non-escalated state edit to set `pending_digest` to the run id, preparation time, and every outgoing URL with title/source. Re-read the file and verify it exactly matches the outgoing digest. This prepared-state edit is the writeability test; do not create a separate probe file.
- Send exactly once. After delivery succeeds, move pending URLs into `seen`, record the returned delivery link/id and time, advance successful timestamps, prune state, and clear `pending_digest`. Re-read and verify the finalized state.
- If delivery fails, do not retry through another tool and do not advance successful timestamps; clear only `pending_digest` when safe. If finalization fails after delivery succeeds, leave `pending_digest` intact so the next run cannot duplicate the digest.

Authenticated browser policy:
- Use only [APPROVED_BROWSER_AND_AUTOMATION_PATH] for LinkedIn access. Do not use unapproved browsers, browser profiles, Computer Use, screenshots, GUI clicking, extension repair, or other fallbacks.
- Scope any approved-command-only restriction to Chrome/browser automation commands. It must not block non-escalated workspace file reads or `apply_patch` edits for the canonical state file.
- Use exactly one automation-owned browser window with one LinkedIn tab. Do not navigate, select, close, scroll, or execute JavaScript in the user's pre-existing browser windows or tabs.
- Close only the automation-owned window when the run finishes or fails.

Durable extraction transport:
- Use the bounded helper `scripts/linkedin_digest_candidates.js` for feed bands and `scripts/linkedin_messages_candidates.js` when inbox triage is in scope, or preserve their limits in equivalent code. Deduplicate across bands; cap posts, news, content URLs, and text; and keep the complete payload below [MAX_TRANSPORT_BYTES].
- Every browser JavaScript expression passed through AppleScript or another bridge must return primitive JSON text via `JSON.stringify(...)`. Never return an object, array, promise, `undefined`, or another non-primitive result.
- If the browser command continues in a background session/process, poll it until exit and append every output chunk. Parse and validate the complete JSON result before filtering. When a run-scoped object store is available, save the validated compact payload there and render only exit status, byte count, feed-band count, and candidate counts. Do not print the raw extraction payload into conversation history.
- Required failures include a nonzero browser exit, invalid top-level/required-feed JSON, missing completion metadata, an oversized payload, or fewer than [MIN_FEED_BANDS] successfully inspected feed bands. Do not open a second browser window or rerun the scan after a required failure in the same automation run.
- Treat connections and inbox as optional ranking/context sources. Normalize a missing or malformed optional source to `{ok:false, items:[]}` and continue with valid public-feed sections.

Incremental scan policy:
- Scan from the top of the feed, with a [OVERLAP_WINDOW] overlap before the previous successful run.
- LinkedIn Top feed is not chronological, so do not stop on one stale post. Check at least several feed bands and cap the run at [MAX_FEED_BANDS] feed bands.
- Skip any content/action URL already present in `seen` unless there is clearly new high-value discussion or a newly linked article/report not previously reported.
- Also skip URLs in `pending_digest`. Reject older feed items outside the incremental window even when they are absent from `seen`.

Use these background priority signals when ranking items: [PRIORITY_PEOPLE_OR_GROUPS], [PRIORITY_ORGANIZATIONS], [TOPICS_OF_INTEREST], and [RECENT_INTERACTION_SIGNALS]. Treat these only as ranking context. Do not display a separate priority list unless there is an actual substantive post, article, report, or inbox item worth summarizing.

Only include items that provide knowledge or perspective I likely would not already know: important articles, reports, research, market or product shifts, technical or architectural perspectives, governance or compliance points, industry trends, or thoughtful analysis with transferable insight.

Explicitly ignore posts about someone starting a new job, changing jobs, celebrating N years at a job, work anniversaries, promotions, graduation or congratulation posts, hiring announcements, personal milestones, generic motivational posts, and self-promotion. Also ignore low-value product ads, lead-gen posts, real estate pitches, finance-service pitches, generic recruiting, and sales spam. Make an exception only when the post links to or summarizes a substantive article, report, research item, or clear transferable insight.

Hard link rule: every digest bullet must contain a clickable link to the actual content/action being summarized: exact LinkedIn post URL, article URL, report URL, news story URL, event URL, message/thread URL, or other source/action URL. A profile link may be included as supporting context but is never sufficient by itself. If no actual content/action link can be captured, exclude the item and do not mention it by name.

Private inbox policy:
- Scan inbox content locally only unless the user explicitly authorizes export and the destination allows it.
- Do not send private message text, private sender details, or private thread URLs to [DELIVERY_TARGET]. Include only a clearly public, non-sensitive action URL that independently satisfies the content rules; otherwise use a short no-qualifying-item line.

Produce three concise sections:
1. Highest-value reads.
2. Priority-network signal.
3. Inbox triage, if inbox access is in scope.

For each item, include the source, topic, engagement or credibility signal when visible, why it matters, and the suggested action. If authenticated LinkedIn access is unavailable, notify me that access needs to be restored instead of guessing.

Before sending, perform a final link audit and remove every bullet that lacks an actual content/action link. Then execute the prepared-state, single-delivery, and finalization transaction above.
```
