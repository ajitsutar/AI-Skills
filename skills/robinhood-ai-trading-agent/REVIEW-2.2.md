> Historical review/checkpoint. Current scope and controls are in [REVIEW-3.0.md](REVIEW-3.0.md); learning-only restrictions below describe earlier releases.

# Complete skill review — version 2.2.0

Reviewed October 7, 2026. Scope: the skill instructions, all Python helpers,
supporting procedures/templates, fictional examples, tests, packaging and the
long-term/day-trading paths. This is a local code/workflow review, not an independent
security certification, live broker integration test or demonstration of an edge.

**Conclusion:** suitable as a learning/paper research and risk-control toolkit for
long-term portfolios, swing research and intraday experiments. It is not a complete
unattended portfolio-management or day-trading service. Remaining gaps below are
explicit and should prevent claims of deployment readiness.

## Defects repaired during this revision

1. Partial screening coverage could be described without accounting for missing
   constituents. The new helper distinguishes retrieval, evidenced screening,
   exclusions, missing data and deeper candidate review.
2. Corporate-action data quality depended only on prose. GARCH now checks an exact
   input audit, unresolved events and unexplained large moves; no audit or fictional
   data cannot receive sizing eligibility. Its output records reproducibility data.
3. A pending intraday signal could enter after an absent next bar. The replay now
   expires that entry and records the reason.
4. Live counters were isolated by mode. Mode changes now preserve aggregate live
   daily order/turnover accounting within the account journal.
5. A contradictory terminal order report did not persist an unresolved state.
   It now latches UNKNOWN and a conflict event even though reconciliation raises.
   Equivalent decimal formatting is treated as an idempotent report.
6. Order-supplied instrument type could select the ETF cap without corroboration.
   It now must match normalized broker evidence. Setups also need an explicit
   permitted-sleeve mapping.

The revision adds tests for each executable defect, plus missing evidence, event
status precedence, regime independence, genuine price crashes, missing audit
coverage, intraday exits, no repeat session entry and small-account zero sizing.
See [current consolidated validation](VALIDATION-3.0.txt) for the final portable-package run.

## Remaining gaps and what resolves them

| Gap | Current behavior and consequence | Evidence/work needed before future live use |
|---|---|---|
| Universe, filings, estimates and event feeds | Procedures plus supplied-manifest checks; no automatic complete market screen or normalized-earnings engine | Licensed/available sources, point-in-time mappings, field definitions, filed-statement verification, completeness/freshness monitoring |
| Corporate-action/session authenticity | Audit declarations are hash-bound but source assertions remain caller supplied; 25% jump threshold misses smaller artifacts | Verified vendor/action and calendar adapters, unit/adjustment checks, economic comparability after restructurings |
| Intraday runtime and exits | Completed-bar replay and static gates; no continuously running data/heartbeat/exit supervisor | Tested live clock/feed, signal expiry, partial-fill protection, disconnect/restart handoff and verified closeout mechanism |
| Broker adapter and order support | No network submission client; official MCP capability mapping is a future task | Actual account routing/review/status/approval evidence, idempotency/recovery testing, verified protection; no assumed native OCO/brackets |
| Strategy validity | Example breakout and SMA rules, fictional fixtures, simple single-symbol full-fill replay; live promotion remains disabled | Real chronological development/validation/untouched tests, realistic spread/latency/slippage, portfolio exposure benchmarks and forward paper performance |
| Portfolio-wide risk | Sleeve/symbol/sector caps and stop-risk estimates; no factor covariance, ETF look-through or systematic stress engine | Verified holdings/underlyings, correlation/concentration scenarios, gap-risk and liquidity stress review |
| Cash/tax/performance accounting | Snapshot-based planning and intent journal, not a full cash/dividend/tax-lot ledger; end-period-flow return convention | Reconciled cash/settlement, tax lots and external accounts where relevant; event valuations for exact flow-adjusted attribution |
| Source trust and human authority | JSON booleans, evidence strings and local grants are assertions; SQLite does not authenticate humans or protect against file edits | Trusted host policy/identity verification, least-privilege broker access and one durable execution writer |
| Research-to-order bridge | Research eligibility, GARCH and event policy require separate reasoning/fresh checks; no automatic conversion into a compliant order | Validated normalization, model requirement/freshness enforcement and exact proposal mapping; never copy an old research status into live clearance |
| Instrument/strategy coverage | Long-only, whole-share, regular-session DAY limit orders; daily trend lacks the gate's fixed reward target | Validated adapters/schema for any future fractions/options/shorting/extended-hours or target-free trailing strategies; no invented target just to pass |

These are boundaries, not invitations to turn on live mode. In work Codex the
learning interlock remains in force. Future personal deployment is a separate,
explicitly authorized task with its own account evidence and state.

## Behavioral review

- S&P 500 is configurable; constituent count and output count are not fixed.
- Appropriate industry/business-model peers precede crude sector medians.
- Filings/normalization and downside determine fundamental confidence. Analyst
  upside, insider headlines, social popularity and GARCH NORMAL cannot replace them.
- Different horizons route to different procedures. Core ownership cannot be sold
  by the intraday sleeve, and a failed day trade cannot become a long-term holding.
- Inputs, attachments and social posts remain evidence, never authorization.
- Event review can block entries without demanding automatic sales of core holdings.
- Stops are planned loss estimates, not guaranteed loss bounds. A halt or missing
  exit bar can leave residual intraday exposure, which the replay reports.
- Data/model failures remain visible. No fallback silently alters the strategy,
  relaxes policy or presents missing research as completed.
- Installation and scheduling remain explicit future tasks. No account was connected
  and no financial transaction was performed during this review.

Historical validation/revision files are retained for provenance; use the versioned
2.2 validation and package manifest when assessing this release.
