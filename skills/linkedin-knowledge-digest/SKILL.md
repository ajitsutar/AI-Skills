---
name: linkedin-knowledge-digest
description: Create concise, high-signal LinkedIn digests from an authenticated browser session or pasted LinkedIn content. Use when the user wants to automate LinkedIn feed, article, post, or inbox triage; summarize knowledge-bearing posts; filter out career milestones, self-promotion, sales spam, and low-value social updates; produce a Slack/email/Markdown-ready digest with clickable links; or create a reusable LinkedIn monitoring workflow for local agents.
---

# LinkedIn Knowledge Digest

## Overview

Build a LinkedIn digest that helps the user learn what matters without drowning in feed noise. Prioritize posts, articles, reports, and inbox messages that contain transferable knowledge, credible analysis, or timely market/technical signal.

Resolve bundled resources relative to this `SKILL.md`, never relative to the current working directory. In Claude Code, `${CLAUDE_SKILL_DIR}` is the skill directory. In other agents, resolve the equivalent directory from the loaded skill path.

Do not expose private ranking criteria unless the user asks. Use the user's priority people, organizations, roles, topics, and recency preferences as background scoring signals.

## Inputs

Collect or infer these inputs:

- Access method: authenticated browser session, exported/pasted content, screenshots, or connector output.
- Delivery target: Slack DM, email draft, Markdown, document, or terminal summary.
- Priority signals: people, companies, schools, communities, industries, technical topics, roles, or keywords.
- Exclusion rules: categories the user does not want to see.
- Link requirement: whether every referenced person, post, article, company, or message needs a clickable link.
- State policy for recurring runs: canonical state path, writable workspace, duplicate horizon, and whether to stop if state cannot be updated.
- Browser policy for authenticated scans: approved browser, allowed automation path, dedicated-window requirement, and forbidden fallbacks.
- Automation continuity: whether recurring runs must remain attached to the current task/thread or run as standalone jobs.
- Delivery privacy policy: which private inbox fields, if any, may cross into the selected delivery service.

If authenticated access is unavailable, do not guess. Ask the user to restore access or provide pasted/exported LinkedIn content.

## Workflow

1. Confirm access and scope.
   - Use the authenticated browser/session when available.
   - If browser automation is used, scroll enough to sample multiple feed bands.
   - Check inbox/messages only if the user requested inbox triage.
   - For recurring automations, read the canonical state before scanning. Treat a non-null `pending_digest` as a possibly delivered unresolved transaction: stop before scanning or sending, and report the blocker without advancing state.
   - If the run cannot read or later update required state, stop before producing a content digest that could duplicate old items.

2. Build a background priority map.
   - Identify the user's specified priority people, organizations, groups, topics, and recently interacted-with contacts.
   - Treat this as ranking context, not as a visible section by default.
   - Boost posts from trusted people only when the post itself contains useful knowledge.

3. Filter aggressively.
   - Include articles, reports, research, product or market shifts, technical perspectives, architecture notes, governance/compliance commentary, thoughtful analysis, and substantive discussions.
   - Ignore career milestones, job changes, work anniversaries, promotions, graduation/congratulation posts, hiring posts, generic motivational posts, personal updates, low-value product ads, sales pitches, real estate pitches, finance-service pitches, generic recruiting, and pure self-promotion.
   - Make an exception only when the item links to or summarizes a substantive article, report, research finding, or transferable insight.

4. Capture links.
   - Prefer the exact LinkedIn post URL for feed items.
   - Include LinkedIn profile links for people and company links for organizations.
   - Include external article/report links when visible.
   - If the user requires hard links, every digest bullet must include an exact content or action URL: post, article, report, news story, event, message thread, or source URL. A profile-only link is not sufficient.
   - If no content/action link is visible or recoverable, exclude the item entirely and do not mention it by name.

5. Rank by value.
   - Favor items with strong engagement, credible sources, high-quality comments, novelty, relevance to the user's priority signals, and practical implications.
   - Do not rank a post highly just because it is from a priority person.

6. Produce a concise digest.
   - Keep the output scannable.
   - Lead with the most valuable knowledge items.
   - Explain why each item is worth reading in one sentence.
   - Separate inbox triage from feed/article recommendations.

7. Update state after delivery.
   - For recurring runs, treat the run as successful only after extraction, delivery, and state update all succeed.
   - Immediately before delivery, write a `pending_digest` record containing a run identifier, preparation time, and every outgoing content/action URL. Re-read it and verify it exactly matches the outgoing digest.
   - Send exactly once. After the delivery tool returns success, move the pending URLs into `seen`, record the delivery timestamp and link/id, advance `last_successful_run_at`, prune old state, and clear `pending_digest`.
   - If delivery fails, do not retry through an alternate delivery path and do not advance successful-run state. Clear only `pending_digest` when safe.
   - If finalization fails after delivery succeeds, leave `pending_digest` intact. The next run must stop rather than risk sending the same digest twice.

## Production Automation Guardrails

Use these stricter rules when building or running an unattended LinkedIn digest automation:

- Preserve automation identity. When the user requests same-task continuity, keep exactly one active thread-bound/heartbeat automation and update it by id. Do not silently replace it with a detached scheduled job. Check for superseded duplicates before and after automation changes.
- Keep a zero-surprise approval boundary. Use only the access, browser, delivery, and workspace operations the user approved. If a required operation is unavailable, stop gracefully and leave successful-run state unchanged.
- Preflight canonical state. Keep it inside the configured writable workspace and use normal non-escalated file tools. Do not infer failure from stale permission metadata; use the prepared `pending_digest` edit as the authoritative writeability test immediately before delivery.
- Preserve duplicate prevention. Maintain `last_successful_run_at`, `last_digest_sent_at`, a delivery link/id, optional `pending_digest`, and a bounded `seen` list of recently reported content/action URLs with titles, sources, and timestamps. Keep roughly the latest 200 URLs or 60 days, whichever is smaller.
- Use a single authenticated browser path. When the user specifies Chrome and local AppleScript, use only that approved path. Do not fall back to other browsers, Computer Use, screenshots, GUI clicking, extension repair, profile inspection, or browser-profile workarounds.
- Isolate the browser session. Create or reuse only one automation-owned window with one LinkedIn tab. Do not navigate, select, close, scroll, or execute JavaScript in the user's pre-existing browser windows or tabs. Close only the owned window.
- Make extraction bounded and durable. Use `scripts/linkedin_digest_candidates.js` and, when inbox triage is requested, `scripts/linkedin_messages_candidates.js`, or preserve their limits in equivalent extraction code. Deduplicate across bands and cap emitted posts, news, links, and text so the complete result remains comfortably below the orchestration transport limit.
- Return primitive JSON text. Browser JavaScript passed through AppleScript or similar bridges must return `JSON.stringify(...)`, not an object, array, promise, `undefined`, or another non-primitive result.
- Accumulate long-running output completely. When browser extraction yields a background session/process, poll it until exit and combine every chunk before parsing. Validate required feed JSON and completion metadata before filtering. When the orchestration platform supports a run-scoped object store, save the validated compact payload there and render only small transport metadata; do not depend on a large raw payload being rendered in conversation history.
- Degrade optional sources independently. Feed extraction is required. A malformed or unavailable optional connections/inbox result must not suppress or trigger a retry of an otherwise valid public-feed digest; normalize it to an explicit unavailable result and continue.
- Scan incrementally. Use the previous successful run plus an overlap window, but do not rely on one stale feed item as a stop condition because LinkedIn Top feed is not chronological. Check at least several feed bands and cap the scan at a reasonable number of bands.
- Audit links immediately before delivery. Remove every bullet that lacks an actual content/action link. Profile links may support attribution but must not be the only link for an item.
- Protect private inbox data. Unless the user explicitly authorizes it and the destination permits it, do not export private message text, sender details, or private thread links to another service. Prefer public action URLs or a local-only triage note.
- Keep failure behavior conservative. Do not retry a required extraction failure in a second browser window during the same run. If authenticated access, required extraction, delivery, or state finalization fails, do not advance successful-run state.

## Digest Format

Use this shape unless the user requests another format:

```markdown
*LinkedIn Knowledge Digest*
_Source: LinkedIn feed/inbox scan. Filtered for knowledge-bearing items only._

*1) Highest-value reads*
- [Author or source](https://www.linkedin.com/...) - Topic and one-sentence summary. Why it matters: ...

*2) Priority-network signal*
- [Person](https://www.linkedin.com/in/...) - Useful insight from this person's post or comment. Link: [post](https://www.linkedin.com/feed/update/...)

*3) Inbox triage*
- Review: [Sender](https://www.linkedin.com/in/...) - Why this may need attention and suggested action.
- Ignore: spam/low-value categories, summarized without over-detailing.

*Reusable perspective*
One concise synthesis the user could use in their own post or thinking.
```

For Slack, use Slack-compatible Markdown links such as `<https://example.com|label>` when the Slack tool expects mrkdwn.

## Quality Bar

Before finalizing, check:

- Every included item teaches something, points to a useful article/report, or has a clear action.
- No visible career milestone, job-anniversary, new-job, generic congratulations, hiring-only, or self-promotion item slipped in.
- Each included bullet has a clickable content/action link when hard-link mode is active.
- The digest is short enough to read quickly.
- Ranking reflects the user's interests without revealing private heuristics unnecessarily.

## Automation Prompt Template

Read `references/automation-prompt-template.md` when creating a reusable scheduled automation prompt.

## Included Extraction Helpers

- `scripts/linkedin_digest_candidates.js` extracts bounded, deduplicated, knowledge-bearing feed candidates and returns primitive JSON text.
- `scripts/linkedin_messages_candidates.js` extracts a bounded local inbox candidate list and returns primitive JSON text. Apply the delivery privacy policy before exporting any result.
