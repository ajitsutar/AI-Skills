# Complete personal-package review — version 3.0.0

Reviewed **October 7, 2026**. Scope: skill instructions, helper source, tests,
templates, references, installation, personal runtime, long-term portfolio and
supervised day-trading paths, recovery and portable packaging. This was a code and
workflow review with local integration tests, not a live brokerage certification.

**Result:** the package is now a portable personal Codex skill with executable
research, risk and supervised execution controls. It is no longer restricted to a
learning-only artifact. It initializes in draft/paper and does not invent account
capabilities, authorizations or profitable strategy results. Installation, account
connection and funded trading were not performed in this work session.

## Requirements implemented

| Requested capability | Implementation and verification |
|---|---|
| Long-term core with small tactical allocation | Separate core/swing/intraday ownership, targets, cash floor, pending exposure and loss caps; configurable illustrative weights |
| Configurable S&P 500 starting universe | Dated frozen universe and coverage manifest; industry/sector comparison; no hardcoded membership count or forced top-N |
| Stronger undervalued-growth analysis | Comparable basis/periods and issuer deduplication; earnings/FCF bridges, dilution/scenarios, balance-sheet/value-trap judgments, analyst dispersion/revisions and event gating |
| GARCH explicitly in the skill | Main skill specification, bundled corrected model, sequential holdout versus baseline, exact input/action audit, reproduced outputs and sizing-only use |
| Portfolio risk/accounting | ETF look-through including shared issuer IDs and explicit fund cash; covariance/component risk, stress, cash and flow-time returns; lot proposals/wash-sale flags |
| Supervised day trading | Actual-session calendar, completed-bar signal recomputation, event windows, liquidity/freshness, native protection semantics, owner/heartbeat lease, time-exit actions and explicit shutdown/handoff |
| Personal broker integration | Observed-schema request builder, nested arguments and exact economic/semantic binding, private routing redaction; authenticated MCP calls made by the personal Codex host |
| Controlled execution | Policy-bound exact grants or mandates, immutable requests, one-time claims, duplicate suppression, durable UNKNOWN states, cumulative partial fills, cancellation/replacement reconciliation |
| Initial broker/public data, optional paid data | Official broker discovery workflow, SEC fact-context retrieval, public adjusted history with session checks, configurable HTTPS JSON provider/header environment |
| Full review | Source/contract review, regression/integration suite, runnable examples, skill-format check, local-link/JSON/source checks, extracted-package tests and manifest/ZIP hashing |

## Material defects closed during the review

1. Older output did not reliably expose GARCH in SKILL.md. It is now explicitly
   routed, executable, versioned and reported with actual run evidence or a skip status.
2. Sector-blind/period-mixed comparisons could exaggerate bargains. Peer calculations
   separate basis and period and deduplicate issuers; financial judgments retain
   normalization, cash support, value-trap and appropriate-industry requirements.
3. A successful model fit could be confused with sizing eligibility. Unreviewed or
   fictional data cannot qualify; required invalid models block live entry. Daily
   volatility is not treated as a five-minute signal or a valuation argument.
4. Signals could survive missing bars or be represented only by a strategy name.
   The replay expires stale entries; personal entry recomputes the current completed-
   bar setup and verifies signal time, stop, target, limit and code/parameter identity.
5. Restart/mode changes could reset attempt budgets or permit repeat setup entries.
   The journal combines live modes and external activity, deduplicates signals and
   enforces per-symbol session entry limits. A cancelled attempt still counts.
6. Caller-supplied projected marks could understate exposure. Personal readiness
   derives holdings/reservations/new exposure from the reconciled broker snapshot.
7. ETF fund labels could be treated as company sectors. Core ETF review now follows
   fund-specific criteria, while actual constituent exposure supplies sector/issuer
   limits. Unknown holdings are not assumed diversified or cash.
8. Broker requests could rely on omitted defaults or lose parameter identity.
   Actual schema binding covers order type, TIF/session, economics and private
   account routing; documented fixed semantics must match. Nested legs are supported.
9. A planned stop could masquerade as protection. Tactical live entries require
   observed native atomic protection, partial-fill quantity tracking and exclusive
   exits; existing stops must match quantity, price and holding-period expiry.
10. Cancellations could release risk on acknowledgement or overwrite a filled parent.
    Separate durable cancellation intents retain reservations until terminal target
    evidence; replacement requires fresh positions/orders and a new exact claim.
11. Terminal contradictions or impossible limit fills could leave further claims
    enabled. Contradictory terminal updates latch UNKNOWN across restart; cumulative
    quantities/average prices are checked, including the approved limit.
12. A stale session could be revived or taken over silently. Session ownership,
    heartbeat, policy hash and expiry are checked; recovery requires reconciliation
    and explicit flat/protected/emergency handoff before restart.
13. Earlier learning-only text contradicted personal scope. Active guides, contracts,
    setup templates and skill metadata now describe personal operation. Earlier
    review files are clearly marked historical; the offline lab remains optional.
14. Legacy schema-2 live claims could bypass new checks. Live claims now require
    schema 3 and full personal readiness; schema 2 remains only a research/paper fixture.

## Validation evidence

See [VALIDATION-3.0.txt](VALIDATION-3.0.txt) for actual commands/results. Tests cover
numerical recursion/holdout, data/action audits, screening classifications,
cash/allocations, source freshness, session/calendar/events, holdings/covariance,
lot/flow calculations, request/schema binding, grants, concurrency, restart,
partial fills, cancellations, signal/economic binding and long-term stock/ETF paths.
Legacy authorization unit tests isolate readiness with a mock; the separate
personal integration tests execute the real readiness functions on fictional data.
No test grant is real authorization, and no broker submission occurred.

The read-only public-data smoke test retrieved SPY's **252 daily sessions for 2024**
and matched the XNYS calendar without missing/unexpected rows. This verified that
adapter's retrieval path, not the data vendor's exhaustive corporate-action accuracy
or GARCH/strategy performance. The output correctly remained action-unreviewed and
ineligible as an execution quote. SEC acquisition requires the user's own contact
identity; its context selection was tested with fixtures. Paid-provider behavior
depends on the user's actual endpoint/schema and credentials.

Skill format, source syntax, JSON/templates, local links, manifest hashes and the
extracted portable archive are checked as part of release verification. The tested
dependencies are recorded separately; an upgrade requires rerunning verification.

## Personal activation checks that cannot be manufactured here

| Required real-world evidence | Package behavior until available |
|---|---|
| Personal broker authentication, eligible account, actual schemas/approval setting | Research/paper; unobserved capability template cannot produce a live request |
| Native atomic protection, partial-fill semantics, expiry and exclusive exits | Tactical live entry blocks; an advanced-tool name alone is insufficient evidence |
| Configured investor policy, symbol/setup scope, applicable human authorization | Draft/paper, no grant or automatic activation |
| Real strategy evaluation and forward-paper observations | No promoted tactical setups; metrics/thresholds alone do not prove a profitable edge |
| Actual bars, quotes, portfolio/fund holdings, event/filing evidence | Missing/stale/ambiguous required inputs block the relevant route |
| Supervised-session/cancel/time-exit drills on the observed broker interface | No claim of validated live behavior; a funded pilot requires its own authorization |

These are deployment dependencies, not completed live tests. There was no brokerage
connector available in this review environment. The package does not ship guessed
MCP schemas, a Robinhood credential wrapper or a fabricated broker sandbox.

## Deliberate scope and remaining limits

- Long-only, whole-share US stocks and supported nonleveraged equity ETFs; regular-
  session DAY limit parent/reduction orders. Child protection uses observed native
  semantics. No options, short selling, leverage, fractional or extended-hours adapter.
- The live tactical signal adapter covers opening-range breakout, unpromoted by
  default. The daily SMA is a research baseline whose live target/exit adapter is
  not supplied. Long-term core execution has its own fundamental/fund workflow.
- Codex is the active supervisor. It cannot promise subsecond reaction, uninterrupted
  observation or action after closure. Broker-native protection is essential;
  gaps/halts can exceed planned losses or prevent a flat close.
- OHLC replay assumes full fills and simplified friction. It is not an order-book
  simulator, continuous multi-asset portfolio backtest or statistical proof. Promotion
  needs independent market/forward evidence and real fill/cost sensitivity.
- Financial-statement interpretation, source authentication, issuer mappings and
  substantially-identical tax treatment require evidence-backed judgment. Tax helpers
  are proposals/flags, not full tax-basis certification across unknown accounts.
- No always-on social scraper, paid subscription, unattended daemon or automatic
  strategy optimizer is included. Schedules and outbound notifications require a
  separate user request and the user's browser/permission rules.
- Local JSON/SQLite controls assume a trusted host. They do not sandbox code that
  can edit them. Broker/host permissions, protected routing storage and one account
  writer remain necessary. A hash establishes file identity, not source authenticity.

## Research provenance

The historical [research review](REVIEW.md) records Reddit execution/slippage
lessons and the limited X access: direct public X URLs failed, so one older third-
party archive was explicitly labeled. No social claim or supplied stock ranking
became a trade signal or verified recommendation. Material broker/model/accounting
claims were checked against primary sources linked in the relevant references.

The personal agents' feedback was treated as critique to evaluate, not as user
authorization or reliable market data. Their ticker selections, quotations and
performance implications were not imported as recommendations.
