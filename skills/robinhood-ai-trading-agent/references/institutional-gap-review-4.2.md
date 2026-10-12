# Institutional capability review for 4.2

Reviewed October 11, 2026 against the shipped workflows and executable helpers.
This is a capability and evidence inventory, not a certification of performance
or a claim of parity with Goldman Sachs. The useful target is rigorous,
reproducible research and controlled implementation within the available data and
broker scope. Adding methods cannot establish investment skill by itself.

Scope update, October 12, 2026: fractional quantity-limit planning and execution
gates now cover small-dollar budgets and per-occurrence recurring proposals. See
the [fractional-share contract](fractional-shares.md). This extends implementation
granularity; it does not add a live broker certification, native dollar-order
adapter or recurring scheduler.

## What is already implemented

| Area | Existing capability | What remains distinct |
|---|---|---|
| Research control | Versioned VQM profiles, universe and issuer mapping, mandate locks, source hashes, immutable bundles, replay and cross-model comparison | Agreement on frozen inputs does not validate independent acquisition or returns |
| Financial evidence | SEC acquisition/extraction, date-aware normalization, bank/REIT adapters, source correction overlays, coverage backlog | Reviewer acceptance, sector supplements, unavailable facts and complete historical vintages |
| Risk and construction | GARCH/EGARCH/GJR-GARCH workflow, covariance analytics, constrained continuous allocation, empirical tail loss, exposure/look-through and scenarios | Model calibration, realistic horizon covariance, integer/tax-lot optimization, full broker margin models |
| Statistical validation | Purged expanding folds, HAC, block bootstrap, Holm adjustment, PSR/DSR diagnostics, factor attribution and promotion evidence checks | A complete trial registry, untouched real outcomes and sufficient forward evidence |
| Simulation and costs | Period portfolio simulator, supported completed-bar strategy simulator, capacity constraints and implementation-shortfall decomposition | Tick/order-book replay, queue priority, empirical impact/borrow calibration and venue-quality measurement |
| Operations | Settled-cash planning, cash ladders, idempotent intent ledger, reconciliation, session/kill controls and monitoring | Resilient always-on services, licensed feeds, tested recovery infrastructure and production broker support |
| Fractional implementation | Decimal quantity-grid sizing, conservative fee/cash reserves, recurring occurrence identities and observed symbol/tool capability gates | Native dollar-market orders, broker recurring schedules, sub-dollar Sell All exceptions and fractional historical fill-model validation |
| Accounting | Flow-timed TWR, XIRR, Brinson attribution, tax-lot suggestions and potential wash-sale flags | Audited NAV, comprehensive tax treatment, multi-account completeness and fund administration |
| News and analyst evidence added in 4.2 | Configured news acquisition, deterministic language triage, reviewed guidance comparisons and observed-cohort analyst arithmetic | Exhaustive report access, trained/calibrated sentiment alpha and independently measured analyst skill |

Tests in `tests/test_quant_workbench.py`, the existing research/risk suites and the
new release suites exercise software contracts and selected formulas. Use the
release test receipt to establish what actually passed; this inventory is not a
test run. No unit-test count or model-overlap percentage is a profitability result.
The shared strategy's [validation protocol](shared-strategy-validation.md) explicitly
records its unvalidated investment status. Strong Buy remains disabled.

## Highest-value work and completion criteria

The order below follows dependencies. Treat each as an independently reviewable
project rather than declaring all investment methods supported after adding prose.

| Priority | Work | Measurable completion criteria |
|---|---|---|
| Now: source integrity | News/guidance and analyst coverage without false all-source claims | Retained live access receipts; inaccessible sources disclosed; duplicate/revision/date cases tested; original report versus excerpt distinguished; frozen replay reproducible |
| Next: causal research data | Dated security master, universe membership, delistings, corporate actions, financial and estimate vintages | A declared historical interval has explicit coverage; entity/action reconciliation passes; no future availability enters formation; retained raw versions and data-use rights permit replay |
| Next: strategy evidence | Evaluate the frozen profile and each proposed news/analyst signal against simple baselines | Preregistered horizon/entry/cost/benchmark and thresholds; complete tested-variant registry; untouched chronological evaluation; dependence-aware uncertainty and cost/parameter sensitivity; no threshold changes after seeing results |
| Next: economic calibration | Map validated features to horizon-specific net excess returns and uncertainty | Out-of-sample calibration artifact with data/profile hashes; rejection outside validated horizon/universe; stability and uncertainty reported; scores and target upside never substituted for returns |
| Next: sentiment quality | Validate extraction/relevance/event classification before using language features in investing | Adjudicated multilingual/sector sample with separate entity, timestamp, negation, numerical-guidance and event labels; precision/recall and abstention by case; frozen model/version; subsequent causal return study kept separate |
| Next: execution realism | Collect paper/live-authorized execution observations and compare with simulation | Decision/arrival/order/fill timestamps reconcile; spreads, delays, fees, partial/unfilled and opportunity costs retained; no OHLC-touch guaranteed fills; impact/capacity scenarios appropriate to account and instrument |
| Then: portfolio robustness | Extend only where the mandate needs it | Estimator sensitivity, binding constraints and passive baseline reported; any multi-period/integer/tax-lot or tail-hedge extension independently tested with relevant data, infeasibility and accounting cases |
| Before unattended use: operations | Build and drill durable monitoring and recovery | Freshness/availability budgets and ownership declared; disconnect, duplicate, partial-fill, stale-feed, restart and kill-switch drills pass with journal reconciliation; broker capabilities and actual authorization verified |
| Ongoing: governance | Maintain a model/strategy inventory with owners and limits | Version, purpose, permitted use, independent validation status, exceptions, drift triggers, rollback and retirement evidence retained; champion/challenger decisions use new paper outcomes |

Required sample sizes, evaluation intervals and thresholds must follow a declared
statistical design and intended horizon. Do not manufacture universal cutoffs or
call overlapping stock observations independent. If data are missing, retain the
gap and make a narrower claim. A latest-price scan is not a point-in-time historical
database. New website breadth does not fix survivorship or revision bias.

## Concrete build order for the two largest gaps

1. **Define the historical data contract before buying or collecting more data.**
   Start with the existing frozen US-equity profile and one declared horizon.
   Specify dates, historical membership, delistings, prices/total-return conventions,
   corporate actions, issuer IDs, financial concepts and information cutoffs.
   Inventory which features need analyst-estimate or news vintages. Do not demand
   every optional dataset to begin a narrower valid experiment.
2. **Build a coverage table, then acquire only missing evidence.** Original SEC
   filings and amendments can support historical accounting reconstruction; use
   accession and acceptance times, not today's latest value assigned to every past
   date. SEC's current aggregate endpoints require cutoff-aware selection and do
   not themselves certify complete point-in-time normalization. For macro features,
   ALFRED/FRED's real-time periods explicitly expose data vintages. Exchange history,
   delisted returns and complete analyst histories must be verified separately;
   free current websites do not establish historical coverage. Evaluate a licensed
   historical provider only against the missing-field contract and data-use rights.
   [SEC APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces),
   [FRED/ALFRED real-time periods](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html).
3. **Archive new observations prospectively.** Preserve immutable payloads,
   acquisition receipts, timestamps, semantic field definitions and content hashes
   in the existing local research library. Never overwrite a prior vintage.
   The new news helper performs one pass and retains first observation/revisions;
   regular unattended collection requires an explicitly configured schedule and
   operational ownership, which this release does not create. Historical studies
   may use a verified archival dissemination time, but must retain today's retrieval
   time and must not fabricate a historical local observation. Production-latency
   replay requires actual recorded delivery times.
4. **Preregister one experiment.** Lock universe, features, weights, formation and
   holding clock, rebalance/exit rules, account constraints, benchmarks, cost model,
   variants and acceptance criteria before inspecting evaluation outcomes. The
   existing validation, simulator and promotion helpers perform parts of this;
   the real dataset and evidence of a profitable strategy remain to be supplied.
   Test the existing baseline first. Evaluate news and analyst features as separate
   challengers, not as discretionary edits to whichever backtest loses money.
5. **Evaluate chronologically with conservative implementation.** Form signals only
   from admissible inputs; transact after their availability. Include spreads,
   commissions/fees where applicable, slippage, delay, unfilled/partial orders,
   liquidity, corporate actions, dividends, and borrow/funding for any authorized
   strategy needing them. Stress costs and missed fills. Use horizon-appropriate
   passive/cash/factor baselines and risk-adjusted comparisons, with drawdown,
   turnover, capacity, serial dependence and uncertainty reported. Insufficient
   history or unresolved survivor bias means exploratory results, not validation.
6. **Forward paper test without retuning.** Record intended orders, actual observable
   quotes and paper-fill assumptions, then reconcile realized implementation against
   the backtest. Promotion needs both statistical and operational evidence. A month
   of paper operation can reveal engineering defects but cannot validate a one-year
   or five-year return forecast. Failed evidence can mean abandoning a strategy;
   it is not automatically a code bug to optimize away.

These steps are a build and evaluation plan, not completed historical acquisition
or a scheduled collector. No fixed spend, purchased dataset or statistically
adequate test duration can be inferred until the coverage audit and power/design
requirements are known. All-free research can begin with a narrower proven dataset;
paid data should address a measured gap, not be treated as a guarantee of alpha.

## Important scope boundaries

Free RSS, public news pages and SEC feeds support research and measured polling.
They do not supply a complete low-latency news firehose, exchange colocated
execution or predictable event-to-order latency. A feed's polling interval is not
an end-to-end latency guarantee. News-dependent operation needs measured delivery,
clock and coverage properties before a promotion claim. Failures mean unknown
coverage, not an assertion that no material news exists.

The allocator already handles supplied costs, borrow requirements, liquidity and
scenario constraints. It is not a full multi-period stochastic controller or
mixed-integer tax optimizer. Risk helpers already cover selected options, bonds,
futures and FX scenarios; they are not American/exotic derivatives pricing,
counterparty/XVA, cleared-margin or full credit-default engines. Existing explicit
unsupported statuses are preferable to relabeling an instrument to make it pass.
Develop these extensions only for an actual authorized mandate and verified data.

GS Quant's public documentation covers data, security mapping, pricing/risk,
portfolios and scenarios. Its backtesting documentation also distinguishes strategy
description from the calculation engine and states that examples require sessions
and relevant entitlements. Its availability does not grant this skill Goldman data,
models, infrastructure or trading capabilities. An optional future adapter needs
rights, credentials supplied through the appropriate system, reproducible inputs,
independent price/risk reconciliation and dependency/license review; do not install
or connect it merely to claim institutional branding.
[GS Quant overview](https://developer.gs.com/docs/gsquant/),
[GS Quant backtesting](https://developer.gs.com/docs/gsquant/pricing-and-risk/backtesting/).

The Federal Reserve's April 2026 SR 26-2 supersedes SR 11-7 and emphasizes model-risk
management proportionate to use and risk. Its governance principles are a useful
reference here, not a statement that a personal skill is a regulated bank or has
satisfied bank supervisory requirements. Keep implementation verification,
independent model validation and ongoing performance monitoring separate.
[Federal Reserve SR 26-2](https://www.federalreserve.gov/supervisionreg/srletters/SR2602.htm).

## Release-level acceptance and honest claims

Before a new release, rerun relevant unit/replay tests, preserve the public ranking
profile unless an explicit new strategy is chosen, and verify package hashes and
self-contained paths. Record source probes separately from mocked parser tests.
For cross-model verification compare actual independently executed artifacts on a
frozen contract; compare fresh evidence decisions separately from arithmetic.

Report three distinct statuses: **software implemented/tested**, **investment
effectiveness empirically validated**, and **external data/operational dependency
available**. A feature can satisfy one and fail the others. The current package can
assist a disciplined research process; professional-grade performance, universal
coverage and replacement of an investment manager remain unestablished.
