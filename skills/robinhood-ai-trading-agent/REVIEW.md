> Historical review/checkpoint. Current scope and controls are in [REVIEW-3.0.md](REVIEW-3.0.md); learning-only restrictions below describe earlier releases.

# Review and upgrade — October 6, 2026

## Outcome and scope

The supplied ZIP was a Codex skill plus one GARCH calculator, not an autonomous
portfolio-management service. It already had useful investor-policy, research,
thesis, approval and journal guidance. Most financial and operational controls were
prose, with no tests demonstrating that they worked.

This upgrade adds a testable learning toolkit and a shorter skill that routes to
specific procedures. It follows your choices: a long-term core, small day-trading
allocation and a future bounded-autonomy design. Your later clarification governs
this deliverable: **work Codex is for learning only**. No brokerage was connected,
no live account queried, no trades placed, no skill installed and no schedules
created. Sample policy is learning/paper; fictional symbols and prices are used.

## Findings and changes

| Priority | Original finding | Implemented change |
|---|---|---|
| High | GARCH/GJR multi-step forecasts set future shocks to zero, losing expected shock variance | Correct persistence recursion, analytical regression cases |
| High | EGARCH first forecast omitted the observed last innovation; multi-step approximation was misleading | Correct one-step forecast; reject unsupported multi-step EGARCH |
| High | Bad CSV prices silently dropped; empty/invalid holdouts and failed fits could still yield misleading output | Strict finite/positive/time-ordered data, minimum holdout, convergence checks, finite JSON |
| High | Holdout compared a fixed multi-step path rather than updating one-step forecasts with observed returns | Sequential one-step state updates with training-only fit and constant-variance baseline |
| High | Risk, reservation and execution protections existed mainly as instructions | Decimal risk gate, pending-order reservations, sleeve/target caps, persistent atomic intent/signal ledger |
| High | Restart/timeouts/partial fills lacked executable recovery logic | UNKNOWN state blocks submissions; monotone cumulative fills; cancelled partial fills retained; refreshed snapshot required |
| Medium | Core allocation, contributions and tactical ownership were underspecified | Cash-first drift-band planner, separate trim review, core target caps, cross-sleeve protection and flow-adjusted performance |
| Medium | No runnable strategy/replay baseline | Example daily trend and intraday breakout, next-bar entries, friction, gap/ambiguous-stop handling and fixed-rule forward windows |
| Medium | Every-order approval conflicted with your chosen bounded-autonomy design | Policy-hash-bound grants, expiry/revocation, broker-review gate and explicit learning interlock |
| Medium | Original installer deleted the entire existing skill directory | Optional explicit-destination installer refuses overwrite; never invoked for your Codex skills |

The risk gate additionally rejects stale/future quotes, holidays/closed sessions,
early-close cutoff violations, halts, wide spreads, insufficient settled cash,
overselling, invalid increments, excessive limit deviation and loss/drawdown breaches.
Risk-reducing sells are not stopped by entry loss breakers.

## What Reddit and X contributed

The most actionable Reddit theme was execution correctness: real fills, stale state,
restarts and duplicate submissions can overwhelm a sensible signal. Practitioner
accounts in [r/algotrading's paper-to-live discussion](https://www.reddit.com/r/algotrading/comments/1vmdce4/paper_2_live_what_mistakes_did_your_trading_bot/)
describe partial fills, delayed acknowledgements and misleading paper fills. These
are anecdotal engineering leads, not verified performance claims. They informed
the journal/recovery tests and explicit replay limitations.

[A separate slippage discussion](https://www.reddit.com/r/algotrading/comments/1tty2qg/how_do_you_model_slippage_realistically_in_a/)
was discovery evidence for cost sensitivity. No claimed strategy returns, broker
recommendations or promotional links were adopted.

Direct X post URLs returned HTTP 403 through public web access. An accessible
[Thread Reader archive of @ReformedTrader's systematic-trading thread](https://threadreaderapp.com/thread/1234306875379683328.html)
summarizes Robert Carver's ideas about diversification and trading costs. It is an
older third-party archive of X content, not authenticated/current-feed verification.
It informed the decision to prioritize allocation and turnover discipline over
adding many indicators. No X claim was used as a trading signal or proof of an edge.

No Chrome automation, login transfer or social-account access was used. Research
was limited to public web sources; this is not exhaustive Reddit/X coverage.

## Primary-source checks

- The [arch project's forecasting documentation](https://arch.readthedocs.io/en/latest/univariate/forecasting.html)
  explains nonzero expected squared innovations and the limits of analytic
  multi-step forecasting. This supports the corrected numerical recursion.
- [Robinhood's official agent documentation](https://robinhood.com/us/en/support/articles/trading-with-your-agent/)
  lists current tools and approval behavior. The design discovers actual schemas
  and settings at runtime instead of assuming every documented capability exists
  in the user's account. Independent stop orders do not prove native OCO support.
- [Robinhood day-trading guidance](https://robinhood.com/us/en/support/articles/pattern-day-trading/)
  and [FINRA's intraday-margin transition guidance](https://syndication.finra.org/content/understanding-new-intraday-margin-requirements)
  show why the historic PDT threshold should not be hardcoded. The revised
  procedure reads current broker restrictions; the included engine uses no leverage.
- The [SEC's settlement rule](https://www.sec.gov/rules-regulations/2023/02/34-96930)
  supports keeping settlement explicit. Local planning never treats a pending sale
  as cash already available to spend.
- [IRS Publication 550](https://www.irs.gov/publications/p550) supports the need for
  lot/holding-period and cross-account wash-sale review. The package adds guidance,
  not a tax engine or a claim that incomplete account data clear a transaction.

Sources were researched on October 6, 2026, Pacific time. Broker rules and capabilities
must be checked again for any future personal deployment.

## Validation and practical limits

See [VALIDATION.txt](VALIDATION.txt) for the actual test run and command smoke checks.
The suite covers formulas, cash/allocation invariants, stale data, session bounds,
concurrency, restart/duplicate prevention, partial-fill cancellation, authorization
binding and the learning block. All execution cases use local fictional fixtures.

The sample strategies have no demonstrated market edge. Replay assumes full fills
with simplified costs and has no L2 queue/latency model, survivorship-aware market
dataset, dividends or production fill adapter. The fixed-rule forward windows
reset account state; they are not a continuous fund return series. GARCH model
selection reuses its holdout, so a separate untouched test would be needed.

Remaining future work includes a supervised market-data/execution runtime, official
MCP normalization, native protection or monitored exits, broker integration tests,
portfolio covariance/stress analytics, ETF look-through, tax-lot/wash-sale engine
and independently evaluated strategies. These are clearly separated from completed
code. A Boolean capability flag is not evidence that those systems exist.

Local policy and SQLite checks are not a hostile-code security sandbox. A process
that can edit them can alter the controls; a future deployment needs separate host
permissions and broker controls. No “production ready” claim is made.
