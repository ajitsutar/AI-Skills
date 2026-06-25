# Automation Prompt Template

Use this template when creating a scheduled LinkedIn digest automation. Replace bracketed placeholders with user-specific values. Keep private details in the user's automation configuration, not in the public skill.

```text
Review my authenticated LinkedIn account and produce a concise priority digest, then send or draft it to [DELIVERY_TARGET].

State and duplicate-prevention policy:
- Use [CANONICAL_STATE_PATH] as the canonical state file. Read it before scanning.
- Store `last_successful_run_at`, `last_digest_sent_at`, a delivery link or message id when available, and a bounded `seen` list of recently reported content/action URLs with titles, sources, and `reported_at` timestamps.
- Keep roughly the latest 200 URLs or 60 days, whichever is smaller.
- If the state file cannot be read or updated without approval, do not send a content digest that could duplicate prior items. Send only a concise block notice when [DELIVERY_TARGET] is already available without approval; otherwise leave a local/chat note.
- Update state only after delivery succeeds. If extraction, delivery, or state update fails, do not advance `last_successful_run_at`.

Authenticated browser policy:
- Use only [APPROVED_BROWSER_AND_AUTOMATION_PATH] for LinkedIn access. Do not use unapproved browsers, browser profiles, Computer Use, screenshots, GUI clicking, extension repair, or other fallbacks.
- Use exactly one automation-owned browser window with one LinkedIn tab. Do not navigate, select, close, scroll, or execute JavaScript in the user's pre-existing browser windows or tabs.
- Close only the automation-owned window when the run finishes or fails.

Incremental scan policy:
- Scan from the top of the feed, with a [OVERLAP_WINDOW] overlap before the previous successful run.
- LinkedIn Top feed is not chronological, so do not stop on one stale post. Check at least several feed bands and cap the run at [MAX_FEED_BANDS] feed bands.
- Skip any content/action URL already present in `seen` unless there is clearly new high-value discussion or a newly linked article/report not previously reported.

Use these background priority signals when ranking items: [PRIORITY_PEOPLE_OR_GROUPS], [PRIORITY_ORGANIZATIONS], [TOPICS_OF_INTEREST], and [RECENT_INTERACTION_SIGNALS]. Treat these only as ranking context. Do not display a separate priority list unless there is an actual substantive post, article, report, or inbox item worth summarizing.

Only include items that provide knowledge or perspective I likely would not already know: important articles, reports, research, market or product shifts, technical or architectural perspectives, governance or compliance points, industry trends, or thoughtful analysis with transferable insight.

Explicitly ignore posts about someone starting a new job, changing jobs, celebrating N years at a job, work anniversaries, promotions, graduation or congratulation posts, hiring announcements, personal milestones, generic motivational posts, and self-promotion. Also ignore low-value product ads, lead-gen posts, real estate pitches, finance-service pitches, generic recruiting, and sales spam. Make an exception only when the post links to or summarizes a substantive article, report, research item, or clear transferable insight.

Hard link rule: every digest bullet must contain a clickable link to the actual content/action being summarized: exact LinkedIn post URL, article URL, report URL, news story URL, event URL, message/thread URL, or other source/action URL. A profile link may be included as supporting context but is never sufficient by itself. If no actual content/action link can be captured, exclude the item and do not mention it by name.

Produce three concise sections:
1. Highest-value reads.
2. Priority-network signal.
3. Inbox triage, if inbox access is in scope.

For each item, include the source, topic, engagement or credibility signal when visible, why it matters, and the suggested action. If authenticated LinkedIn access is unavailable, notify me that access needs to be restored instead of guessing.

Before sending, perform a final link audit and remove every bullet that lacks an actual content/action link. After successful delivery, update canonical state with the delivery timestamp, delivery link/id when available, and every included content/action URL.
```
