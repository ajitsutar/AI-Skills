---
name: linkedin-knowledge-digest
description: Create concise, high-signal LinkedIn digests from an authenticated browser session or pasted LinkedIn content. Use when the user wants to automate LinkedIn feed, article, post, or inbox triage; summarize knowledge-bearing posts; filter out career milestones, self-promotion, sales spam, and low-value social updates; produce a Slack/email/Markdown-ready digest with clickable links; or create a reusable LinkedIn monitoring workflow for Codex, Claude Code, OpenClaw, or similar local agents.
---

# LinkedIn Knowledge Digest

## Overview

Build a LinkedIn digest that helps the user learn what matters without drowning in feed noise. Prioritize posts, articles, reports, and inbox messages that contain transferable knowledge, credible analysis, or timely market/technical signal.

Do not expose private ranking criteria unless the user asks. Use the user's priority people, organizations, roles, topics, and recency preferences as background scoring signals.

## Inputs

Collect or infer these inputs:

- Access method: authenticated browser session, exported/pasted content, screenshots, or connector output.
- Delivery target: Slack DM, email draft, Markdown, document, or terminal summary.
- Priority signals: people, companies, schools, communities, industries, technical topics, roles, or keywords.
- Exclusion rules: categories the user does not want to see.
- Link requirement: whether every referenced person, post, article, company, or message needs a clickable link.

If authenticated access is unavailable, do not guess. Ask the user to restore access or provide pasted/exported LinkedIn content.

## Workflow

1. Confirm access and scope.
   - Use the authenticated browser/session when available.
   - If browser automation is used, scroll enough to sample multiple feed bands.
   - Check inbox/messages only if the user requested inbox triage.

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
   - If a link is visible or obtainable, do not mention the item without a clickable link.

5. Rank by value.
   - Favor items with strong engagement, credible sources, high-quality comments, novelty, relevance to the user's priority signals, and practical implications.
   - Do not rank a post highly just because it is from a priority person.

6. Produce a concise digest.
   - Keep the output scannable.
   - Lead with the most valuable knowledge items.
   - Explain why each item is worth reading in one sentence.
   - Separate inbox triage from feed/article recommendations.

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
- Each named person, company, post, article, or message has a clickable link when available.
- The digest is short enough to read quickly.
- Ranking reflects the user's interests without revealing private heuristics unnecessarily.

## Automation Prompt Template

Read `references/automation-prompt-template.md` when creating a reusable scheduled automation prompt.
