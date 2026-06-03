# Automation Prompt Template

Use this template when creating a scheduled LinkedIn digest automation. Replace bracketed placeholders with user-specific values. Keep private details in the user's automation configuration, not in the public skill.

```text
Review my authenticated LinkedIn account and produce a concise priority digest, then send or draft it to [DELIVERY_TARGET].

Use these background priority signals when ranking items: [PRIORITY_PEOPLE_OR_GROUPS], [PRIORITY_ORGANIZATIONS], [TOPICS_OF_INTEREST], and [RECENT_INTERACTION_SIGNALS]. Treat these only as ranking context. Do not display a separate priority list unless there is an actual substantive post, article, report, or inbox item worth summarizing.

Only include items that provide knowledge or perspective I likely would not already know: important articles, reports, research, market or product shifts, technical or architectural perspectives, governance or compliance points, industry trends, or thoughtful analysis with transferable insight.

Explicitly ignore posts about someone starting a new job, changing jobs, celebrating N years at a job, work anniversaries, promotions, graduation or congratulation posts, hiring announcements, personal milestones, generic motivational posts, and self-promotion. Also ignore low-value product ads, lead-gen posts, real estate pitches, finance-service pitches, generic recruiting, and sales spam. Make an exception only when the post links to or summarizes a substantive article, report, research item, or clear transferable insight.

Include clickable links for every referenced LinkedIn person, company, post, article, message thread, or feed item whenever visible or obtainable. Prefer exact LinkedIn post URLs for important feed items rather than linking only to the author's profile.

Produce three concise sections:
1. Highest-value reads.
2. Priority-network signal.
3. Inbox triage, if inbox access is in scope.

For each item, include the source, topic, engagement or credibility signal when visible, why it matters, and the suggested action. If authenticated LinkedIn access is unavailable, notify me that access needs to be restored instead of guessing.
```
