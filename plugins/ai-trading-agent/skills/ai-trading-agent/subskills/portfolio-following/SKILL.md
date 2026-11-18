---
name: portfolio-following
description: Refresh public investor disclosures and attributed recommendations, compare disclosed allocations, and prepare source-aware follower targets and rebalance proposals. Use for following public portfolios or long-only inverse recommendation strategies.
---

# Public portfolio following

Refresh on demand. Do not create a recurring monitor unless the user asks for one.
Resolve package resources two directories above this subskill. Parent broker-handoff
instructions still apply; research and proposed trades are not brokerage orders.

## Find the right portfolio

Read the [source catalog](../../profiles/portfolio-followers-v1.json) and
[source interpretation](../../references/portfolio-follower-sources.md).
Treat this dated catalog as discovery: verify new filings and reporting-manager
changes during each refresh. An Autopilot listing identifies a popular strategy;
it does not supply its proprietary weights or demonstrate investing success.
Use accessible primary filings and first-party holdings, without an Autopilot account.
Keep inaccessible allocations unavailable rather than reconstructing them from marketing.

Attribute Pelosi-family transactions to the disclosed owner, and distinguish Donald
Trump from family members or political-theme funds. Berkshire, Scion, Renaissance,
Point72 and similar filings describe reporting managers, not named individuals'
personal portfolios. Taleb's association with Universa does not expose either his
personal holdings or the firm's full hedge book. Do not turn public commentary,
13F notice filings, confidential treatment, or a missing filing into trades.

## Refresh and retain evidence

1. Check the latest available primary document and its amendments. Retain source URL,
   accession or transaction identity, portfolio date, publication date, retrieval time,
   owner/manager, currency and value units. Show both holdings date and filing date.
2. Reuse compatible retained captures where useful, but partial fetching is optional.
   Validate identity, freshness, and complete amendments before reusing data. Keep
   compact captures/checkpoints outside the skill; do not copy an investor's historical
   filing into a new date or assume another host has the same cache.
3. Normalize supplied records with the [disclosure adapters](../../references/portfolio-disclosure-inputs.md).
   Preserve source ranges and unknown quantities. Ordinary 13F holdings omit shorts,
   many assets and cash; weights of disclosed eligible securities are not total wealth
   weights. Report excluded options and unmapped securities alongside the denominator.
4. Compare source identities and revisions with the previous capture. Separate new
   disclosures, corrections, withdrawals and unchanged records. On first refresh,
   label the result a baseline, not a stream of newly executed transactions. A failed
   refresh must preserve the last good capture and visibly retain its old date.

For historical evaluation, decisions can use only information published and available
at that decision time. Filing delays cannot be removed by assigning the transaction
or quarter-end date as the signal date. Document incomplete history and survivorship.

## Construct a follower proposal

Use the [target and rebalance calculations](../../references/portfolio-follower-calculations.md)
and [fictional example](../../examples/portfolio-following.json). Specify each followed
source, sleeve budget, stale-source treatment, instrument eligibility, concentration
cap and chosen weighting rule. Missing sizing information permits an illustrative
percentage proposal, not invented funded positions.

For long-only Reverse Cramer, an attributable qualifying sell recommendation is a
candidate long signal; a buy recommendation reduces or exits the corresponding
follower position. Never open a short under this rule. Recommendation qualification,
expiry and position sizing are declared policy choices, not evidence of predictive value.

Aggregate identical securities and expose residual cash. Review issuer exposure
across share classes separately; the helper caps security IDs, not issuer groups.
Do not apply whole-portfolio
sales to holdings outside the follower scope, or liquidate a sleeve merely because
its source is stale, partial or unavailable. Do not treat amount-range midpoints as
actual political-trade quantities or treat reported options as common-stock holdings.

Present dated source allocations separately from the proposed follower portfolio.
Show proposed buys/sells, remaining cash, costs and unresolved tax/settlement inputs.
Explain any differences caused by caps, excluded instruments, rounding or unavailable
sources. Actual broker capability and the user's existing trading instructions govern
execution through the parent [broker handoff](../../references/broker-integration.md).

## Report the refresh

Give a compact source table with owner/manager, holdings or trade date, publication
date, allocation denominator, freshness and source links. Show newly disclosed changes
and proposal differences only when established; disclose stale or missing sources.
Do not describe popularity, a partial 13F replica, or an inverse-commentary rule as
proof of skill, risk-adjusted outperformance, or replication of an app's live portfolio.
