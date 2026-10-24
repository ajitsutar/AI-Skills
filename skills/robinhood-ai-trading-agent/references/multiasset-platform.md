# Multi-asset research, paper testing and production qualification

Version 5.0 provides reusable research and paper-accounting components across
equities/ETFs, vanilla options, linear futures, funded FX, fixed bonds and spot
crypto. **The package is not a certified production trading service.** Live
capability belongs to the actual native host/broker, whose observed schemas,
account capabilities and operational evidence must support the requested task.
These research distinctions create no additional permission or approval gates.

## Choose the applicable component

| Need | Implemented component | Boundary |
|---|---|---|
| Equity selection, technical/fundamental/sentiment evidence | Existing research workflow and [analysis contracts](analysis-contracts.md) | Source truth, actual forecast calibration and predictive validity remain separate evidence. |
| American/European vanilla option value and implied volatility | [Derivatives toolkit](derivatives-toolkit.md) | Constant continuous dividend yield, finite CRR tree; no discrete dividend, exotic, stochastic-volatility or option-on-future model. |
| Bond value, clean/dirty bridge, accrued interest | Derivatives toolkit and existing `risk.bond` | Supplied complete fixed noncallable cashflows, declared day-count/discount conventions. No universal schedule or credit/default engine. |
| Linear futures variation | Derivatives toolkit; [paper ledger](paper-exchange.md) | Explicit multiplier, settlement and rounding assumptions; no physical delivery, automatic roll or exchange portfolio-margin engine. |
| FX forward and currency accounting | Derivatives toolkit; funded conversion/translation in paper ledger | Covered-interest forward is not a spot forecast. No leveraged FX, swaps, cross-currency basis or broker connectivity inferred. |
| Spot crypto paper positions | Paper ledger | Explicit quantity/tick/pair units and funded cash; no staking, lending, perpetual funding or custody service. |
| Multi-asset scenario risk | Existing `risk.scenarios`, factor and portfolio tools | Model P&L and continuous weights are not executable quotes or reconciled collateral. |
| GBM paths, trend derivatives and fixed-pair normalization | [Time-series tools](time-series-toolkit.md) | Supplied assumptions; no ARMA, cointegration or validated arbitrage. |
| Order-event accounting and failure scenarios | Paper ledger | Hypothetical supplied fills, explicit cancellation/settlement/expiry, no actual broker or queue simulation. |
| Assess whole-system evidence | [Platform readiness](platform-readiness.md) | Checks submitted catalog completeness only; cannot authenticate receipts, certify production or grant/deny trade authority. |

`quant_workbench.py` routes `derivatives.calculate`, `paper.replay`,
`platform.assess` and `timeseries.run` using `inputs.document`. All operation parameters are explicit;
the workbench checks currency consistency where applicable and binds operation
information cutoffs to the frozen contract. Projected bond cashflows and generated
GBM paths can be future-dated; observed settlements cannot. A successful outer `COMPUTED` status means the
helper executed: retain the inner status, assumptions, missing evidence and limits.
For example, a computed platform report may correctly report every scope UNVERIFIED.

## Production scope is asset-, host- and strategy-specific

An instrument's mathematical model, a paper replay and a live adapter are separate
capabilities. A stock-research pass cannot qualify futures settlement, options
assignment or crypto custody. A generic supported flag cannot qualify every order
type, session, instrument variant or account. Preserve the actual request's scope.

Before describing a deployment as production-ready, the relevant evidence should
cover the exact code/runtime, permitted data and availability, instrument conventions,
native order identity/lifecycle/recovery, reconciliation, monitoring/response, and
strategy-specific forward outcomes. Use the platform assessor to organize this
evidence, then independently review its underlying artifacts. File hashes establish
identity, not truth or actual test execution. Do not manufacture receipts or use
fictional tests as actual host qualification. No universal paper duration, Sharpe
threshold or profitable outcome is promised.

Order retries, submission, cancel/replace and execution authorization remain with
the native host/broker. The historical `execution_ledger.py` and
`guarded_execution.py` compatibility functions are intentionally retired/read-only
handoffs; do not treat their names as an operating order-management service and
do not restore a second skill-owned execution authority. See
[broker integration](broker-integration.md).

## Robinhood documentation context

The [Robinhood agent documentation](https://robinhood.com/us/en/support/articles/trading-with-your-agent/),
reviewed October 23, 2026, describes long equities, options and crypto orders and
states that agents cannot place multi-leg options orders. That does not verify any
particular connected account. Futures availability in another Robinhood product
does not establish agent-tool support. FX and bond research calculations likewise
do not establish tradability through Robinhood. Discover actual current tools and
capabilities rather than hardcoding permanent assumptions from this dated note.
No alternative broker, credentials, account changes or live order is authorized
by a research or software-development request.

## Useful prompts

- “Research this equity universe for my stated horizon using the permitted files;
  freeze source vintages, definitions, calculations and uncertainty.”
- “Price this vanilla option under the explicit exercise/dividend conventions.
  Show tree convergence and implied-volatility solver status, not a trade quote.”
- “Replay this hypothetical multi-asset event packet. Reconcile cash, receivables,
  variation margin, positions and FX; preserve every rejected or unsupported event.”
- “Assess this native host for [asset, instrument, order, session, strategy].
  Separate research, paper and live evidence, and show missing or contradictory
  receipts. Do not place orders or call a complete catalog production certification.”
- “Compare the same frozen packet and package in independent model contexts;
  retain first responses and calculation differences without sharing answers.”

Expanded data coverage, realistic fill calibration, trained models, empirical alpha,
always-on service operation and actual broker qualification require their own
work and evidence. Adding formulas does not close these dependencies.

Time-series scenario and diagnostic calculations are in
[time-series-toolkit.md](time-series-toolkit.md), routed as `timeseries.run` with
`inputs.document`. The nested operation cutoff must not exceed the workbench
contract cutoff; generated future GBM paths remain hypothetical scenarios.
