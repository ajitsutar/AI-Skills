# Quantitative capabilities and limits

Use this guide to scope a research request and identify missing data or models.
It describes the current implementation, not a release review or test report.
Research findings are advisory; native host and broker tools own execution.

| Workflow | Available methods | Inputs or capabilities that remain external |
|---|---|---|
| Reproducible research | VQM profiles, universe and issuer mapping, frozen inputs, hashes, replay and comparison | Source coverage, comparable acquisition cutoffs and economic interpretation |
| Financial evidence | SEC acquisition/extraction, normalization, bank/REIT adapters and correction overlays | Filing interpretation, sector supplements, missing facts and historical vintages |
| Risk and construction | GARCH families, covariance analysis, constrained continuous allocation, tail loss and scenarios | Calibration, horizon-appropriate inputs, comprehensive integer/tax-lot and margin optimization |
| Strategy evaluation | Chronological folds, purging, HAC, block bootstrap, Holm, Sharpe diagnostics and factor attribution | Complete trial records, untouched outcomes and sufficient forward evidence |
| Simulation and costs | Portfolio and completed-bar simulations, capacity assumptions and execution-shortfall analysis | Tick/order-book replay, queue priority and empirical impact/borrow calibration |
| News and analysts | Configured feeds, deterministic text triage, guidance comparison and observed-cohort arithmetic | Exhaustive publisher access, calibrated sentiment alpha and independently measured analyst skill |
| Portfolio accounting | Cash ladders, TWR, XIRR, attribution, tax-lot suggestions and potential wash-sale flags | Audited NAV, comprehensive taxes, complete multi-account records and fund administration |
| Order handoff | Preserve requested market, dollar or fractional intent; explain observed outcomes | Native authentication, supported order schemas, actual execution and order-state handling |

## Historical data and strategy evidence

For a historical study, define security identifiers, membership intervals, delistings,
corporate actions, financial vintages, publication availability, retrieval times and
data-use rights. Today's constituents and restated fundamentals do not establish a
point-in-time historical database. Quantify missing coverage rather than backdating
current downloads or silently using survivors only.

Freeze the universe, signals, horizon, rebalance/exit rules, cost model, benchmarks,
variants and assessment criteria before examining evaluation outcomes. Compare
simple baselines under the same assumptions and include failed variants. Account
for serial dependence, overlapping labels, multiple testing and missed or partial
fills. See [research methods](research-methods.md), [strategy evaluation](strategy-evaluation.md)
and [quant methods](quant-research.md).

Keep three claims separate: a method is implemented, its investment effectiveness
is supported by empirical evidence, and its external data/infrastructure is available.
Software tests or model agreement establish neither alpha nor future returns.
The package has no calibrated Strong Buy classifier or demonstrated universal alpha.

## External scope

Public news polling is not an exchange-quality low-latency feed. Accessible headlines
are not complete reports. Record missing sources and measured timing rather than
claiming all-source access or guaranteed event-to-order latency.

The allocator is not a comprehensive multi-period tax optimizer. Supported option,
bond, futures and FX scenarios do not imply full exotic-option, counterparty/XVA,
credit-default or broker-margin engines. Match the implemented method and supplied
inputs to the instrument; explain unsupported cases without inventing calculations.

Independent host services provide authentication, custody, order submission,
reconciliation, monitoring and recovery. The skill does not create an always-on
execution service or impose policy, ticket, spread, volatility or funding gates.
See [host integration](host-execution-integration.md).
