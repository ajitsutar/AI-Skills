# LinkedIn-Wide Discovery

Use `content.discovery.linkedin_mode: "search"` when the user wants articles from LinkedIn overall, rather than their home feed. The bounded native search finds posts linking to articles and LinkedIn essays, not just items from their connections. LinkedIn may personalize results; never claim exhaustive or unbiased platform coverage.

Set one to three distinct `linkedin_queries` (at most 160 characters each), at least three `linkedin_bands_per_query`, and at most ten search bands total. The preset uses the native past-week search filter; narrower source-age windows are enforced at review. Change that preset during setup for a longer requested search horizon rather than silently claiming wider coverage.

At setup, pass the workspace config as the materializer's optional second CLI argument:

```text
node scripts/materialize_linkedin_scan_transport.js /chosen/workspace/scripts /chosen/workspace/digest-config.json
node /chosen/workspace/scripts/validate_linkedin_scan_transport.js /chosen/workspace/scripts/linkedin_scan_applescript_lines.json
```

Run the materialized orchestrator with `discoveryMode: config.content.discovery.linkedin_mode`, `searchQueries: config.content.discovery.linkedin_queries`, `maxSourceAgeDays: config.content.max_source_age_days`, and `includeConnectionsUpdates: config.content.discovery.include_connections_updates === true`, in addition to its existing paths, tools, time and focus arguments. A configuration/manifest mismatch fails before Chrome. Do not rewrite the manifest during scheduled execution.

Every query must return at least three validated sequential bands and the transport must have its completion marker. Unrecognized result layout, access restriction, malformed required payload, incomplete query coverage, or oversize transport is a failure, not evidence that no worthwhile articles exist. Respect the existing single-window, no-retry, approval and access boundaries.

## Separate Connections Updates

Users can set `connections_priority_organizations` to their schools and former employers. Pass this list as `priorityOrganizations` to the runner. Apply the small ranking boost only to verified first-degree updates whose visible actor affiliation supports the match. Do not infer affiliation from a company mentioned in an article body; unknown affiliation receives no boost. This private preference never overrides quality or appears as a standalone list in delivery.

Keep the reusable skill's default list empty. Store each user's actual affiliations only in their local configuration, never in published skill instructions, examples, fixtures, or automation templates. Do not assume the skill author's schools or employers apply to another user.

`include_connections_updates: true` adds three bounded feed bands in the same owned window and tab. This is only for the separate connections-update section; it does not replace broad article searches. Do not read the connections list or inbox. Require an explicit first-degree actor label, not a familiar name or matching organization.

These updates are not restricted to AI. Select meaningful professional insights, research, engineering, industry developments, policy or analysis. Exclude promotions, job changes, job posts, self-promotional articles, generic advice, bragging, outings and social-event recaps. Keyword filters are only initial screening; perform editorial review. A public post can qualify with a substantive insight and exact content link, but do not export restricted-audience content. If audience is unknown, only recommend an independently verified public source and omit the unverified post's personal text.

Search candidates have `discovery: "linkedin_search"`; verified connection candidates have `discovery: "connections_updates"` and `connectionDegree: 1`. Do not infer that a first-degree connection is a public audience. Use `publicAudience` plus source verification. Neither stream reads private messages.

Search discoveries use the configured source-age window, not the last successful run. Connection updates retain the feed overlap window. Both use the same seen URLs and story deduplication. Unknown dates require verification before delivery. Separate the sections in the digest and rank by evidence and significance, not familiarity, popularity, or AI keywords alone. Respect `content.max_items` across the whole digest; the default is three recommendations, not three per section.
