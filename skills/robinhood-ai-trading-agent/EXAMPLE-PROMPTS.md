# Example prompts: learning, investing, trading and quantitative research

<!-- Generated from references/example-prompts.json with scripts/release_docs.py. -->

175 examples across 24 workflows, from first-time investing to quantitative research.

Start any prompt with **Use the robinhood-ai-trading-agent skill.** Replace
bracketed inputs with your own data. Choose a section below; you do not need to
read or run the entire catalog. Examples describe requests you can make, not
additional investment rules or permission to trade.

Research and paper calculations are broader than live execution support.
Research and risk diagnostics are advisory. User-requested execution belongs
to native host/broker tools. Some advanced examples produce a research plan or a gap
assessment because the required data, model or validated adapter is absent.
Read the linked workflow for each section and the [README](README.md) for scope.

## Choose a workflow

| Workflow | Audience | Examples |
|---|---|---:|
| [Getting started and learning](#getting-started-and-learning) | Beginner | 7 |
| [Research mandates and stock universes](#research-mandates-and-stock-universes) | Beginner to advanced | 6 |
| [Stock discovery and reproducible ranking](#stock-discovery-and-reproducible-ranking) | Intermediate to quant | 7 |
| [Business analysis, valuation and value traps](#business-analysis-valuation-and-value-traps) | Intermediate to expert | 8 |
| [Holding periods, catalysts and event risk](#holding-periods-catalysts-and-event-risk) | Intermediate | 6 |
| [News, sentiment and between-quarter guidance](#news-sentiment-and-between-quarter-guidance) | Intermediate to quant | 8 |
| [Analyst reports, consensus and financial information](#analyst-reports-consensus-and-financial-information) | Intermediate to expert | 8 |
| [Social hypotheses, ownership and disclosure context](#social-hypotheses-ownership-and-disclosure-context) | Intermediate | 5 |
| [Portfolio planning and investor decisions](#portfolio-planning-and-investor-decisions) | Beginner to expert | 8 |
| [Fractional shares and recurring contributions](#fractional-shares-and-recurring-contributions) | Beginner to quant; execution depends on verified broker support | 6 |
| [Quantitative portfolio construction](#quantitative-portfolio-construction) | Quant | 8 |
| [Volatility forecasting and portfolio risk](#volatility-forecasting-and-portfolio-risk) | Advanced to quant | 7 |
| [Market-data quality and financial normalization](#market-data-quality-and-financial-normalization) | Advanced to quant | 8 |
| [Statistical research and model validation](#statistical-research-and-model-validation) | Quant | 8 |
| [Backtesting and paper-validation design](#backtesting-and-paper-validation-design) | Advanced to quant | 7 |
| [Multi-asset research, pricing and hedging](#multi-asset-research-pricing-and-hedging) | Advanced to quant; research scope | 9 |
| [Cash, settlement and funding](#cash-settlement-and-funding) | Intermediate to quant | 6 |
| [Performance accounting, execution costs and attribution](#performance-accounting-execution-costs-and-attribution) | Intermediate to quant | 8 |
| [Day trading and supervised paper sessions](#day-trading-and-supervised-paper-sessions) | Intermediate to expert | 7 |
| [Recommendations and requested market handoffs](#recommendations-and-requested-market-handoffs) | All levels; actual broker support and user authorization required | 9 |
| [Host integration and observed outcomes](#host-integration-and-observed-outcomes) | Expert; broker and authorization dependent | 10 |
| [Saved research and incremental refresh](#saved-research-and-incremental-refresh) | All levels | 6 |
| [Cross-model reproducibility and audits](#cross-model-reproducibility-and-audits) | Advanced to quant | 6 |
| [Institutional research workflows and capability development](#institutional-research-workflows-and-capability-development) | Expert to quant | 7 |

## Getting started and learning

**Audience:** Beginner. Guides: [personal setup](references/personal-setup.md), [small account research](references/small-account-research.md).

### 1. Check what is available

> Check the installed skill, package integrity, Python dependencies, data access and broker capabilities. Explain which workflows I can use now and which need additional inputs or services.

### 2. Understand recommendations and handoff

> Explain which investment research and quantitative calculations this skill performs, how its optional handoff preserves my requested order, and which operations belong to the connected host and broker. There are no local execution modes or gates to activate.

### 3. Create a research workspace

> Create a research workspace at [DIRECTORY] for source archives, reports and a private observed-outcome journal. Keep it outside the installed skill; do not create an execution policy or approval ledger.

### 4. Describe my investment preferences

> Help me describe objectives, horizon, contributions, cash needs and losses I want considered. Keep these as research context and distinguish my actual instructions from illustrative preferences.

### 5. Research a small starting portfolio

> I have [AMOUNT] to invest for [HORIZON]. Compare individual stocks with a diversified ETF approach, account for affordable share sizes and costs, and explain what evidence supports each choice.

### 6. Learn to read financial statements

> Use [COMPANY] to explain how revenue, margins, earnings, cash flow, capital spending, debt and share dilution connect. Use dated primary evidence and show why profit can differ from cash generation.

### 7. Run the fictional exercises

> Run the bundled learning exercises and explain the resulting analytical findings. Separate fictional investment numbers, software behavior and evidence that would be needed for real investing.


## Research mandates and stock universes

**Audience:** Beginner to advanced. Guides: [research handoff](references/research-handoff.md), [research campaign](references/research-campaign.md), [holding period planning](references/holding-period-planning.md).

### 8. Screen the full US market

> Start a stock screen across all US exchange-listed stocks, including ADRs. Preserve every membership and data-retrieval outcome, separate security-type and liquidity exclusions, and disclose unresolved coverage.

### 9. Use an explicit S&P 500 universe

> Use the current S&P 500 as the research universe for [HORIZON]. Verify its constituents and multiple share classes, identify unique issuers and freeze the dated membership evidence.

### 10. Define a custom universe

> Use [WATCHLIST OR UNIVERSE FILE] with [EXCLUSIONS]. Validate identifiers, duplicates, listing status, currencies and ADR/share-class relationships. Treat universe membership as a research definition, not order permission.

### 11. Ignore previous preferences for one run

> Research [REQUEST] using only this prompt and the skill's stated defaults. Lock an explicit mandate and show the inferred assumptions. Do not inherit earlier stock lists, event rules or personal preferences.

### 12. Resolve an arbitrary holding period

> Interpret [HOLDING PERIOD] precisely, including calendar versus trading days, entry window, fixed or rolling exit and early-exit rules. Route the request to intraday, swing or long-term research as appropriate.

### 13. Audit partial coverage

> Audit this whole-market scan: [BUNDLE]. Reconcile attempted, retrieved, scored, excluded and reviewed securities and issuers. Identify failures that could change the ranking before calling any list final.


## Stock discovery and reproducible ranking

**Audience:** Intermediate to quant. Guides: [research campaign](references/research-campaign.md), [shared default strategy](references/shared-default-strategy.md), [model independent research](references/model-independent-research.md).

### 14. Run a fresh fundamental screen

> Run the shared public research profile on [UNIVERSE] for [HORIZON] using fresh inputs. Produce the computed research queue with full coverage and provenance, then review candidates in its prescribed order.

### 15. Look for undervalued growth

> Research [NUMBER] undervalued companies with durable growth potential in [UNIVERSE] for [HORIZON]. Distinguish numerical research priority, valuation evidence and buy eligibility; return fewer supported choices when necessary.

### 16. Explain the factors behind a rank

> Explain the Value, Quality and Momentum contributions for [TICKERS] using the saved profile and inputs. Show peer comparisons, signed yields, missing fields and the sensitivity of close ranks without changing the official score.

### 17. Run the strict filing-based route

> Build a filing-derived research snapshot for [UNIVERSE] using consistent accounting definitions and information cutoffs. Run the strict normalizer and scorer; report missing evidence rather than mixing vendor and filing factors.

### 18. Recover missing data

> Create and work through a field-level recovery backlog for [SNAPSHOT]. Use issuer filings and supplements, preserve source bytes and distinguish unsupported normalization from genuinely unavailable facts.

### 19. Correct stale vendor financials

> Investigate stale financial inputs in [SNAPSHOT]. Prepare a source-backed correction overlay with periods, units and accounting basis, retain the original, and rerank the full snapshot after accepted corrections.

### 20. Check recommendation language

> Audit [REPORT] against its actual research evidence. Separate research candidates from reviewed selections and identify unsupported Strong Buy, full-universe, return or confidence claims.


## Business analysis, valuation and value traps

**Audience:** Intermediate to expert. Guides: [screening and value traps](references/screening-and-value-traps.md), [financial normalization](references/financial-normalization.md).

### 21. Compare suitable peers

> Compare [TICKERS] against appropriate industry peers using aligned dates and metric definitions. Explain which valuation measures fit each business and which comparisons are distorted by accounting or business mix.

### 22. Normalize earnings and cash flow

> Build a reported-to-normalized earnings and free-cash-flow bridge for [COMPANY]. Examine restructuring, stock compensation, acquisitions, working capital and capex; separate evidence from assumptions and recurring costs.

### 23. Challenge a cheap-looking stock

> Investigate whether [COMPANY] is undervalued or a value trap. Review debt maturities, cash conversion, dilution, competitive position, capital allocation and what must change for the discount to close.

### 24. Model acquisition synergies

> Review [ACQUISITION THESIS]. Reconcile pre-tax and after-tax synergies, timing, integration costs, financing and dilution. Compare full, delayed, partial and failed execution scenarios.

### 25. Use the bank accounting route

> Analyze [BANK HOLDING COMPANY] using the skill's supported bank normalization and primary evidence. Reconcile tangible common equity, capital and credit-quality definitions at the correct listed-entity scope.

### 26. Use the REIT accounting route

> Analyze [REIT]. Reconcile common unadjusted Nareit FFO to GAAP, distinguish FFO from AFFO and adjusted figures, and evaluate leverage, distributions and property risks with the appropriate definitions.

### 27. Review commodity and cyclical exposure

> Analyze [CYCLICAL COMPANY] across a plausible cycle. Identify commodity, volume, capex and financing drivers, distinguish producer from customer exposure, and avoid treating historical equity beta as the thesis.

### 28. Build scenario valuations

> Develop bear, central and bull valuation scenarios for [COMPANY] at my actual exit horizon. Make growth, margins, reinvestment, dilution and exit valuation assumptions explicit, with failure modes and sensitivity.


## Holding periods, catalysts and event risk

**Audience:** Intermediate. Guides: [holding period planning](references/holding-period-planning.md), [screening and value traps](references/screening-and-value-traps.md).

### 29. Plan a forced exit

> Research [UNIVERSE] for a hold ending on [DATE]. Evaluate catalysts and outcomes before that date, specify the latest entry, and compare after-cost scenarios with the cash alternative.

### 30. Evaluate a flexible long-term hold

> Review [COMPANY OR PORTFOLIO] for a flexible [HORIZON] holding period. Define thesis-review and invalidation conditions, near-term event coverage and a rolling review plan rather than inventing a distant event calendar.

### 31. Allow earnings with explicit risk

> Review [WATCHLIST] for [HORIZON], allowing holdings through earnings. Disclose event dates, gap risk and scenario sensitivity without inventing an entry blackout.

### 32. Avoid holding through specified events

> Research [WATCHLIST] subject to no holdings through [EVENT TYPE]. Verify event dates and uncertainty windows, distinguish earnings release from conference call, and show which positions cannot meet my exit contract.

### 33. Compare cash at the same horizon

> Compare this proposal [RESEARCH RECORD] with an appropriately dated cash or Treasury benchmark over the same holding period, using consistent return, fee and tax assumptions.

### 34. Challenge a short-horizon target claim

> Audit the claim that [COMPANY] can reach [TARGET] within [SHORT HORIZON]. Check whether the evidence is a longer-term analyst target, a dated catalyst or a validated forecast, and state what remains unsupported.


## News, sentiment and between-quarter guidance

**Audience:** Intermediate to quant. Guides: [news and guidance](references/news-and-guidance.md).

### 35. Discover relevant news sources

> Find suitable public news, issuer and industry sources for [COMPANIES]. Search beyond a fixed website list, open the actual pages, identify original publishers and record accessible, partial, blocked and missing coverage.

### 36. Configure a free news watchlist

> Prepare a news-watch configuration for [WATCHLIST] using verified issuer feeds, exchange notices and relevant public news or macro feeds. Check each endpoint and its permitted polling frequency; do not schedule future runs.

### 37. Run one incremental news check

> Run one news-collection pass using [CONFIG] and [EXISTING STATE]. Preserve raw receipts, first observations, revisions and backoff. Distinguish new information, unchanged feeds, cached context and failed sources.

### 38. Analyze news language reproducibly

> Apply the bundled deterministic sentiment triage to [NEWS ARCHIVE] at [CUTOFF]. Show issuer matching, negation, mixed language and duplicate clusters, and distinguish language tone from expected stock returns.

### 39. Check post-earnings business updates

> For [COMPANY], examine developments since its latest results: guidance, preliminary numbers, investor-day presentations, business updates, financing and material current reports. Explain whether earlier research needs revalidation.

### 40. Compare two guidance disclosures

> Compare [OLD GUIDANCE] and [NEW GUIDANCE] using retained primary evidence. Match metric, fiscal period, units, currency and accounting basis; calculate range and midpoint changes and identify withdrawals or noncomparable disclosures.

### 41. Review a trading halt

> Review the latest exchange status for [SYMBOL]. Distinguish halt event time from a feed dateline and quote resumption from trade resumption. Explain current exchange/broker restrictions as external facts, not new skill gates.

### 42. Test news data quality

> Audit [NEWS ARCHIVE] for late arrivals, future timestamps, revised stories with old datelines, syndication, ambiguous company names and source outages. Replay the same inputs and verify the triage output matches.


## Analyst reports, consensus and financial information

**Audience:** Intermediate to expert. Guides: [analyst research](references/analyst-research.md).

### 43. Build a stock information map

> Build an information coverage map for [COMPANY]: financials, valuation, guidance, forecasts, catalysts, ownership, capital allocation and material risks. Dynamically find relevant finance sites and retain source dates, lineage and access gaps.

### 44. Find accessible analyst research

> Locate publicly accessible analyst reports and attributed research excerpts for [COMPANY], including credible opposing views. Distinguish a full report, a quoted recommendation, commentary, a snippet and a paywall.

### 45. Calculate forward target consensus

> Review forward [52-WEEK OR 12-MONTH] analyst targets for [COMPANY]. Match horizon, currency, share basis and original issue dates, then calculate the observed cohort's mean, median, range and IQR with independent-firm counts.

### 46. Reconcile different website targets

> Compare consensus targets reported by [PROVIDERS]. Trace upstream data sources, population, as-of dates and definitions. Keep overlapping provider pools separate rather than averaging their averages.

### 47. Review analyst track records

> Assess the analysts covering [COMPANY]. Find sourced success rates, average returns, sample counts, periods, benchmarks and holding rules; report missing definitions and distinguish provider-reported records from independently reproduced performance.

### 48. Assess reputation and incentives

> Evaluate [ANALYST OR AUTHOR]'s role, sector expertise, methodology, corrections and disclosed conflicts. Distinguish verifiable experience from firm prestige, followers or a few visible winning calls.

### 49. Compare revisions without mixing metrics

> Review dated rating changes, target changes and EPS/revenue estimate revisions for [COMPANY]. Match firms, fiscal periods, currency and accounting basis, and separate genuine revisions from initiations or changed coverage.

### 50. Separate fair value from price targets

> Compare [INTRINSIC FAIR-VALUE ESTIMATE], forward analyst targets and the historical 52-week trading range for [COMPANY]. Explain their different meanings and why none alone establishes a probability of achieving my desired return.


## Social hypotheses, ownership and disclosure context

**Audience:** Intermediate. Guides: [research and validation](references/research-and-validation.md), [screening and value traps](references/screening-and-value-traps.md).

### 51. Research competing public narratives

> Investigate bullish and bearish arguments about [COMPANY] on Reddit and accessible X posts. Deduplicate repeated claims, identify promotional interests and verify material facts with primary sources.

### 52. Interpret insider transactions

> Review [INSIDER FILINGS] for [COMPANY]. Distinguish discretionary purchases/sales from awards, option exercises and tax withholding, including filing footnotes, amendments and transaction versus disclosure dates.

### 53. Assess ownership changes carefully

> Review [INSTITUTIONAL OWNERSHIP REPORTS] for [COMPANY]. Identify reporting periods, filing delays, amendments and entity scope, and explain what the data cannot establish about current positions.

### 54. Challenge a political-trading claim

> Investigate [PUBLIC CLAIM ABOUT A DISCLOSED TRADE]. Verify the original disclosure, transaction range, timing and amendments, and distinguish evidence from speculation about motive or future returns.

### 55. Review short-interest and options narratives

> Check [SHORT-SQUEEZE OR OPTIONS-FLOW THESIS] using accessible dated evidence. Distinguish short interest, borrow conditions and options activity, including delays and unknown positioning, without treating a popular narrative as an entry signal.


## Portfolio planning and investor decisions

**Audience:** Beginner to expert. Guides: [portfolio management](references/portfolio-management.md), [institutional manager](references/institutional-manager.md).

### 56. Critique my current investments

> Review [HOLDINGS, CASH AND RECURRING CONTRIBUTIONS] for [HORIZON]. Assess issuer, sector and theme concentration, overlapping funds, employer exposure and the effect of future contributions before proposing changes.

### 57. Manage employer-stock concentration

> Review [CURRENT EMPLOYER STOCK] and [NET VESTING SCHEDULE]. Account for shares withheld or sold for taxes, separate employment and investment exposure, and compare diversification paths without assuming gross grants are spendable cash.

### 58. Compare portfolio allocations

> Compare core, swing, intraday and cash allocations for [CAPITAL AND OBJECTIVES]. Explain concentration and loss scenarios without imposing sample weights or approval requirements on my account.

### 59. Rebalance with contributions

> Use [HOLDINGS], [TARGETS] and a new contribution of [AMOUNT] to propose a cash-first rebalance. Apply drift bands and show residual imbalances, turnover and transaction constraints.

### 60. Plan a withdrawal

> I need [AMOUNT] on [DATE]. Compare ways to raise the cash given settlement, liquidity, tax lots, concentration and long-term allocation effects. Produce a proposal without placing orders.

### 61. Look through funds and share classes

> Analyze the combined issuer, sector and theme exposures in [STOCKS AND FUNDS]. Include overlapping holdings, multiple share classes and missing holdings data, then identify the main concentration risks.

### 62. Compare funds for a portfolio role

> Compare [FUNDS] for [ROLE AND HORIZON]. Evaluate holdings, diversification, fees, liquidity, tracking, distribution and tax considerations using appropriate fund evidence.

### 63. Review tax-aware sale alternatives

> Using [LOT RECORDS], compare lot-selection proposals for selling [POSITION]. Estimate gains/losses and flag possible wash-sale issues, including uncertainty from other accounts and future purchases.


## Fractional shares and recurring contributions

**Audience:** Beginner to quant; execution depends on verified broker support. Guides: [fractional shares](references/fractional-shares.md), [portfolio management](references/portfolio-management.md), [execution handoff](references/execution-handoff.md).

### 64. Invest a small dollar budget

> Prepare an allocation and host handoff for [SECURITIES] using the full [DOLLAR BUDGET]. Preserve native dollar instructions where supported; explain fractional quantities, estimated costs and final-debit uncertainty without imposing whole-share or template cash restrictions.

### 65. Plan one recurring contribution

> For [CONTRIBUTION OCCURRENCE], calculate [DOLLAR AMOUNTS PER SECURITY] using fractional shares. Show rounding and any user-requested reserve. Produce the requested handoff without creating an unrequested future schedule or a local approval ticket.

### 66. Compare fractional and whole-share implementation

> Apply [TARGET WEIGHTS] to [HOLDINGS AND NEW CASH] in fractional and whole-share planning modes. Compare allocation drift, fees, feasible trades and leftover cash. Clearly label any offline increment assumptions and identify the broker evidence still needed for execution.

### 67. Validate fractional execution capabilities

> Inspect actual connected schemas and symbol tradability for [FRACTIONAL PROPOSALS]. Explain precision, minimums, quantity/notional semantics and fill reporting. Preserve requested native dollar-market instructions where supported rather than silently changing the order basis.

### 68. Interpret fractional partial fills

> Review [FRACTIONAL ORDER AND CUMULATIVE FILLS] against observed broker records. Preserve exact filled and remaining quantities, explain actual fees and residual cash, and distinguish cumulative updates from new fills.

### 69. Analyze a small tactical position

> Calculate hypothetical fractional sizes for [ENTRY, STOP, TARGET, CASH AND LOSS SCENARIOS]. Show sensitivity to gaps and costs. Treat the calculation as advice; do not require protective orders or a volatility model before the host handoff.


## Quantitative portfolio construction

**Audience:** Quant. Guides: [quant workbench](references/quant-workbench.md), [institutional manager](references/institutional-manager.md).

### 70. Construct a constrained allocation

> Run the allocation helper on [ASSETS, COVARIANCE AND MANDATE]. Enforce issuer/group, gross/net, cash, turnover, liquidity, volatility and scenario limits; show binding constraints and compare with a simple baseline.

### 71. Investigate infeasibility

> Diagnose why [ALLOCATION INPUT] is infeasible. Identify conflicting constraints and show possible policy changes for review without silently relaxing limits or reporting an invalid allocation.

### 72. Validate a return calibration

> Audit [EXPECTED-RETURN CALIBRATION] before using it in portfolio construction. Check matching horizon and return units, training/test chronology, retained evidence and all variants; reject factor scores or analyst upside substituted for expected returns.

### 73. Stress covariance assumptions

> Recompute [PORTFOLIO PROPOSAL] under declared alternative covariance and scenario inputs. Compare weight stability, concentration and risk sensitivity; distinguish supplied assumptions from estimated or validated parameters.

### 74. Evaluate costs and capacity

> Construct or compare allocations using [TURNOVER COSTS, IMPACT ASSUMPTIONS AND CAPACITY LIMITS]. Show how proposed weights change and where the portfolio exceeds plausible tradable size.

### 75. Translate weights into feasible proposals

> Review [CONTINUOUS TARGET WEIGHTS] against capital, share sizes, current holdings, unsettled cash, tax lots and broker capabilities. Identify rounding and implementation gaps rather than treating solver weights as executable orders.

### 76. Constrain benchmark tracking risk

> Construct [PORTFOLIO] with the declared benchmark weights and tracking-volatility constraint. Compare it with the minimum-risk proposal and identify which active exposures consume the risk budget.

### 77. Evaluate signed research weights

> Evaluate [RESEARCH ALLOCATION] with explicit signed bounds, gross/net limits and supplied borrow availability and costs. Flag missing evidence and keep the result separate from unsupported live short-selling execution.


## Volatility forecasting and portfolio risk

**Audience:** Advanced to quant. Guides: [garch volatility](references/garch-volatility.md), [quant workbench](references/quant-workbench.md), [portfolio management](references/portfolio-management.md).

### 78. Run evidenced GARCH

> Run the bundled GARCH(1,1) workflow on audited prices for [SYMBOL]. Report data counts, convergence, training/holdout separation, QLIKE against the baseline, forecast horizon and actual sizing eligibility.

### 79. Compare asymmetric volatility models

> Compare GARCH, GJR-GARCH and supported EGARCH forecasts on the same audited data and holdout. Record all variants, respect forecast-horizon limitations and separate volatility forecasts from direction.

### 80. Use volatility as advice

> Explain how [VOLATILITY RESULT] changes the risk interpretation of [ALLOCATION]. Compare it with simpler realized-volatility and stress estimates, disclose missing evidence and keep every diagnostic advisory rather than an execution gate.

### 81. Estimate historical tail losses

> Calculate empirical VaR, expected shortfall and drawdown for [RETURN SERIES] at [CONFIDENCE LEVEL]. State frequency, sample size, missing data and why historical tail estimates may miss future gaps.

### 82. Run portfolio stress scenarios

> Stress [PORTFOLIO] under market, sector, issuer, rate, volatility and currency shocks appropriate to its instruments. Include every position and report loss concentrations, assumptions and unsupported pricing cases.

### 83. Assess a risk-model breach

> Apply the monitoring helper to [OBSERVATIONS] with limits fixed before the result. Review stale data, coverage, realized versus forecast risk, costs and reconciliation errors without automatically retuning models or raising limits.

### 84. Estimate covariance and component risk

> Estimate aligned-return covariance and component risk for [PORTFOLIO]. Review sample coverage, asset ordering and documented shrinkage settings, then show sensitivity without claiming an unimplemented estimator was run.


## Market-data quality and financial normalization

**Audience:** Advanced to quant. Guides: [data and analytics](references/data-and-analytics.md), [financial normalization](references/financial-normalization.md), [quant workbench](references/quant-workbench.md).

### 85. Audit prices before modeling

> Audit [PRICE FILE] for timestamp order, duplicates, missing sessions, timezones, price basis and large jumps. Investigate splits, dividends and real event moves instead of deleting inconvenient returns.

### 86. Check action and share-basis consistency

> Reconcile [PRICE AND CORPORATE-ACTION FILES] with share counts and financial per-share metrics. Identify adjusted versus execution prices, ADR ratios and action dates that could distort ranking or backtests.

### 87. Extract cutoff-admissible SEC facts

> Use verified CIKs and my configured SEC contact identity to obtain primary financial data for [COMPANIES]. Preserve source bytes and extract only facts admissible at [CUTOFF], retaining amendments and accounting context.

### 88. Resolve normalization failures

> Run strict normalization on [EVIDENCE RECORDS]. Explain missing concepts, periods, units, entity scope or source acceptance, and prepare a precise recovery backlog instead of imputing favorable values.

### 89. Compare alternative data providers

> Compare [PROVIDER SNAPSHOTS] for the same securities and cutoff. Reconcile field definitions, fiscal periods, timestamps, price adjustments and missingness, then document which differences could change the result.

### 90. Design a historical-vintage audit

> Audit [HISTORICAL DATASET] for membership changes, delistings, restatements, estimate revisions and publication availability. Identify which dates can support point-in-time research and which remain exploratory.

### 91. Reconstruct trailing financial flows

> Reconstruct [TTM METRICS] from dated annual and interim filings. Avoid double-counting YTD periods, check fiscal calendars and amendments, and retain the source and calculation for each normalized value.

### 92. Audit earnings-yield arithmetic

> Audit [VALUATION SNAPSHOT] for mismatched price/EPS dates, trailing versus forward definitions, negative earnings and inconsistent share counts. Show which comparisons remain valid and which require correction.


## Statistical research and model validation

**Audience:** Quant. Guides: [quant research](references/quant-research.md), [quant workbench](references/quant-workbench.md), [research and validation](references/research-and-validation.md).

### 93. Create causal validation folds

> Build purged expanding-window folds from [SAMPLES WITH FEATURE-AVAILABILITY AND LABEL-END TIMES]. Specify training size, test size and embargo; verify that overlapping outcomes and future features do not leak across splits.

### 94. Measure uncertainty with serial dependence

> Run HAC inference and a seeded block bootstrap on [ALIGNED NET-EXCESS RETURNS]. Declare lag and block choices before evaluating results, and compare uncertainty with a naive independent-observation assumption.

### 95. Control multiple testing

> Use the full trial registry [REGISTRY] to apply the supported multiple-testing and qualified Sharpe diagnostics. Report all attempted variants, their dependence assumptions and anything that prevents a valid adjusted claim.

### 96. Attribute returns to factors

> Regress [EXCESS RETURNS] on [ALIGNED FACTORS] using the supported factor/HAC workflow. Show exposure, residual performance and uncertainty without interpreting correlation as a causal edge.

### 97. Preregister a strategy experiment

> Write a research contract for [STRATEGY]: universe, horizon, signal, costs, benchmark, variants, untouched evaluation window and acceptance criteria. Identify data and statistical-design gaps before running it.

### 98. Review strategy evidence

> Evaluate [STRATEGY VERSION] using retained development, validation, untouched-test and forward observations. Recompute the chosen quantitative criteria, inspect data/code hashes and all variants, and explain confidence and limitations without creating a live-promotion requirement.

### 99. Test sensitivity without hindsight

> Evaluate [FROZEN STRATEGY] against prespecified neighboring parameters, delayed fills, missed trades and worse costs. Keep all outcomes and distinguish robustness analysis from selecting a new winner on the test set.

### 100. Evaluate a challenger model

> Compare [CHAMPION] and [CHALLENGER] on the same frozen contract and genuinely new paper observations. Separate implementation agreement, forecast calibration, net performance and operational changes before recommending replacement.


## Backtesting and paper-validation design

**Audience:** Advanced to quant. Guides: [quant workbench](references/quant-workbench.md), [research and validation](references/research-and-validation.md), [strategy playbook](references/strategy-playbook.md).

### 101. Replay a period portfolio

> Run the portfolio simulator on [CAUSAL DECISIONS AND TOTAL RETURNS], including cash, benchmark, tradability, costs, impact and trade-value capacity. Verify that decisions precede returns and explain simulator limitations.

### 102. Backtest the intraday baseline

> Replay the supported opening-range-breakout setup on [INTRADAY DATA]. Use completed-bar decisions, costs and conservative fills; disclose stop/target ordering ambiguity and facts the bars cannot establish.

### 103. Compare daily and intraday engines

> Choose the appropriate bundled simulator for [STRATEGY AND DATA]. Explain which settlement, fill, latency and portfolio behaviors it models and which require separate paper observations.

### 104. Compare after-cost benchmarks

> Compare [BACKTEST] with cash and suitable passive benchmarks at comparable exposure. Report net returns, drawdowns, turnover and cost stress rather than choosing a winner solely by gross return or Sharpe.

### 105. Design a forward-paper study

> Create a forward-paper protocol for [FROZEN STRATEGY]. Specify decision/quote/fill observations, performance and operational criteria, and the independent evidence needed before considering live use.

### 106. Audit an impressive backtest

> Review [BACKTEST BUNDLE] for survivor bias, revised data, look-ahead, trial selection, unrealistic fills, omitted costs and overlapping labels. Identify what can be reproduced and what cannot support the performance claim.

### 107. Run the daily trend baseline

> Run the bundled daily SMA research baseline on [AUDITED DAILY DATA]. Use its actual chronological rules and costs, compare it with a passive baseline and explain why a successful replay does not establish a profitable strategy.


## Multi-asset research, pricing and hedging

**Audience:** Advanced to quant; research scope. Guides: [multi asset playbook](references/multi-asset-playbook.md), [quant workbench](references/quant-workbench.md).

### 108. Choose the supported instrument route

> Review [INSTRUMENT LIST] and map each position to the skill's supported research, pricing and risk functions. Identify required data and unsupported live execution rather than representing derivatives as shares.

### 109. Price a European option scenario

> Use the supported European option model with [SPOT, STRIKE, MATURITY, VOLATILITY, RATE AND DIVIDEND ASSUMPTIONS]. Calculate price and sensitivities, check parity where applicable and disclose model limitations.

### 110. Identify unsupported option assumptions

> Assess [OPTION OR HEDGE] for exercise style, payoff, settlement and volatility assumptions. Explain whether the bundled European model applies and what is missing for American or exotic structures.

### 111. Analyze a fixed bond

> Price [NONCALLABLE FIXED CASH FLOWS] using the supplied zero curve and spread. Evaluate rate/spread scenarios and explain why callable, prepayable or credit-default features need additional models.

### 112. Stress futures exposure

> Evaluate [FUTURES POSITIONS] with explicit contract multipliers, currencies and price shocks, including negative-price cases when relevant. Separate scenario P&L from actual margin and settlement requirements.

### 113. Stress foreign-currency exposure

> Evaluate [POSITIONS AND FX SHOCKS] in [BASE CURRENCY]. Reconcile currency conversion, contract units and collateral assumptions, and identify missing exposures.

### 114. Compare hedge scenarios

> Compare [HEDGE CANDIDATES] under common portfolio shocks and stated costs. Show basis risk, scenario protection, residual exposure and pricing or execution capabilities that remain unavailable.

### 115. Build a multi-asset mandate

> Draft a mandate for [ASSETS AND OBJECTIVES] with explicit permitted instruments, leverage, liquidity, collateral, risk budgets and benchmarks. Keep research capabilities separate from verified broker execution support.

### 116. Stress illiquid commitments

> Stress [PRIVATE-ASSET COMMITMENTS AND DISTRIBUTION ASSUMPTIONS] through the cash-ladder and cash-flow tools. Evaluate funding gaps and XIRR sensitivity while distinguishing assumed cash flows from an independently valued private asset.


## Cash, settlement and funding

**Audience:** Intermediate to quant. Guides: [settled cash planning](references/settled-cash-planning.md), [quant workbench](references/quant-workbench.md).

### 117. Compare a cash buffer

> Model [DAY-TRADING PLAN] with an optional reserve of [DOLLARS OR PERCENT OF EQUITY]. Compare settlement paths and available cash under observed account conventions; present the buffer as advice, not a skill-imposed trade gate.

### 118. Plan staggered cash usage

> Given [POSITIONS, EXPECTED TRADES AND CASH], compare settlement-aware trading schedules. Use current broker availability and calendars rather than assuming alternating groups of stocks automatically avoid funding gaps.

### 119. Build a currency cash ladder

> Run the cash-ladder helper on [SETTLED BALANCES, RESERVATIONS AND CONFIRMED EVENTS]. Enforce currency-specific floors and identify when liabilities exceed available funds.

### 120. Analyze reservations and debits

> Analyze [ORDER RESERVATIONS AND DEBITS] for double counting and account cash-flow differences. Match confirmed events, retain source evidence and explain unknown outcomes. This is accounting analysis, not a local execution lock.

### 121. Review a funding shortfall

> Review [CASH-LADDER RESULT] for a settlement or collateral shortfall. Distinguish confirmed credits from expected sales and propose feasible timing or size changes without assuming unavailable cash can be spent.

### 122. Check a withdrawal against trading

> Combine [WITHDRAWAL PLAN] and [TRADING PLAN] to assess settled-cash availability, reserved amounts and liquidity floors through [DATE]. Show conflicts before any order or withdrawal proposal.


## Performance accounting, execution costs and attribution

**Audience:** Intermediate to quant. Guides: [portfolio management](references/portfolio-management.md), [quant workbench](references/quant-workbench.md).

### 123. Measure investment performance

> Calculate time-weighted performance from [VALUATIONS AND EXTERNAL FLOWS]. Separate deposits and withdrawals from investment P&L and disclose missing valuations or timing ambiguity.

### 124. Calculate my money-weighted return

> Compute XIRR from [DATED CONTRIBUTIONS, DISTRIBUTIONS AND TERMINAL VALUE]. Check signs and whether the cash-flow pattern supports the conventional calculation; compare it with time-weighted return.

### 125. Explain active return

> Run the supported Brinson attribution using [BEGINNING PORTFOLIO/BENCHMARK GROUP WEIGHTS AND RETURNS]. Include cash and reconcile allocation, selection and interaction effects to the active result.

### 126. Measure execution shortfall

> Decompose [ORDER AND FILL RECORDS] using decision, arrival and terminal prices. Include fees, partial fills and unfilled opportunity cost, and compare buys and sells with the correct signs.

### 127. Review results by sleeve

> Compare core, swing and intraday performance from [JOURNAL]. Use appropriate benchmarks, flow treatment and net costs, and distinguish investment effects from execution problems or policy deviations.

### 128. Challenge a win-rate claim

> Review [TRADE HISTORY] using average win/loss, expectancy, drawdown, costs, exposure and uncertainty. Explain why win rate alone does not establish a profitable or scalable strategy.

### 129. Reconcile the cash ledger

> Reconcile [OPENING CASH, TRADES, DIVIDENDS, FEES AND EXTERNAL FLOWS] with [BROKER CASH]. Identify discrepancies and unconfirmed events before calculating spendable cash or investment performance.

### 130. Compare tax-lot proposals

> Compare the supported FIFO, HIFO and specific-lot proposals for [SALE AND COST-BASIS RECORDS]. Show gain/loss differences and potential wash-sale flags, with unresolved outside-account information retained.


## Day trading and supervised paper sessions

**Audience:** Intermediate to expert. Guides: [short term trading](references/short-term-trading.md), [strategy playbook](references/strategy-playbook.md).

### 131. Prepare a session brief

> Prepare an intraday brief for [WATCHLIST]. Verify session times, current catalysts, earnings, halts, liquidity, spreads and data freshness; disclose missing inputs before identifying setups.

### 132. Build an intraday watchlist

> Start from the configured stock universe and apply [PRICE, LIQUIDITY AND SPREAD FILTERS] to build a tactical watchlist. Separate membership, tradability and entry-signal qualification.

### 133. Analyze an opening-range setup

> Evaluate the opening-range-breakout research example for [SYMBOL] using completed bars. Report range, trigger, invalidation, reference exits, costs and evidence limitations. The simulated rules are not execution conditions.

### 134. Reject premature confirmation

> Review [CHART OR BAR DATA] for a possible breakout. Distinguish completed from unfinished candles, dated quotes and missing event evidence. Explain how these limitations affect the research conclusion without imposing an execution pause.

### 135. Size a paper trade after costs

> For [ENTRY, STOP, TARGET AND CAPITAL], calculate affordable whole-share size, planned loss and net reward/risk. Include pending exposure, spread/slippage assumptions and the possibility that valid size is zero.

### 136. Run a supervised paper session

> Simulate a research session for [WATCHLIST] from available completed bars. Use declared setup rules, conservative fills and a journal. Report missing observations and the limits of the simulation without implying a background service or imposing execution conditions.

### 137. Handle losses and closing risk

> Review today's marked positions, trades and pending orders. Explain realized/unrealized losses, gap and closing risk, and possible responses as advice. Report the actual host/broker state without imposing a new-entry stop or requiring a monitoring lease.


## Recommendations and requested market handoffs

**Audience:** All levels; actual broker support and user authorization required. Guides: [execution handoff](references/execution-handoff.md), [fractional shares](references/fractional-shares.md).

### 138. Recommend and hand off one allocation

> Research [UNIVERSE] for [HORIZON] and recommend how to invest the full [BUDGET]. I also instruct the connected host to place those purchases at market. Preserve that instruction without adding skill approvals, grants, tickets, volatility conditions or price-drift thresholds; state recommendation uncertainty honestly.

### 139. Use my existing order instruction

> Prepare the host handoff for [EXISTING ORDER INSTRUCTION]. Preserve the requested amounts and order type without asking again because research prices or quote timestamps changed.

### 140. Keep market-price uncertainty informational

> For [MARKET ORDER REQUEST], state the research as-of and explain possible market-price and fee differences. I accept that uncertainty; do not pause or request reapproval based on price movement, spreads or quote age.

### 141. Preserve a native dollar amount

> Prepare [DOLLAR ALLOCATION] for a host that supports native dollar-market instructions. Preserve the amount and explain whether the broker estimates shares from a recent trade price, so final debit may differ. Do not silently round to whole shares.

### 142. Preserve an explicit limit instruction

> Prepare a handoff for [SYMBOL, SIDE, QUANTITY AND USER-SPECIFIED LIMIT]. Preserve my supplied limit exactly; the skill should not replace it with a market order or invent a new price condition.

### 143. Keep research findings advisory

> Explain the concentration, earnings, volatility, spread and liquidity risks of [ORDER REQUEST], then preserve my existing host instruction. Do not turn any research finding or sample allocation constraint into an execution veto.

### 144. Compare stock choices for a small amount

> Give me [NUMBER] alternative stocks, each suitable for investing the full [BUDGET] for [HORIZON]. Compare dated catalysts, valuation, evidence and downside. Treat them as alternatives rather than splitting the amount unless I ask.

### 145. Handle a recurring request clearly

> Prepare the requested fractional contribution [AMOUNTS AND SECURITIES] and distinguish one occurrence from a broker-native recurring schedule. Preserve any scheduling instruction I actually gave; do not claim a local calculation installed a schedule.

### 146. Explain a broker rejection

> Interpret [ACTUAL BROKER RESPONSE] and separate the broker or platform requirement from this skill. Report exactly what happened without inventing a local live policy or readiness checklist.


## Host integration and observed outcomes

**Audience:** Expert; broker and authorization dependent. Guides: [execution handoff](references/execution-handoff.md), [host execution integration](references/host-execution-integration.md), [broker integration](references/broker-integration.md).

### 147. Inspect actual connected tools

> Inspect the available broker tool schemas for [REQUEST]. Explain supported market/share/dollar/limit inputs and actual broker requirements without creating a skill capability gate or inventing unavailable tools.

### 148. Prepare a pure handoff

> Pass [ORDER DETAILS] through execution_handoff.handoff or its CLI. Verify that it preserves the supplied order, needs no runtime policy, grants or evidence, and makes no broker network call.

### 149. Compare exact payloads

> Compare [REQUESTED ORDER PAYLOAD] with [HOST HANDOFF]. Identify changes to side, amount, quantity, type, account routing or time-in-force. Do not equate a correctly formatted payload with a submitted or filled order.

### 150. Explain an empty connector response

> The connector returned an empty object for [ORDER]. Interpret available JSON-RPC errors, MCP isError, content and structured content without assuming acceptance or rejection. Keep credentials and private identifiers out of the report; actual broker reconciliation belongs to the host.

### 151. Interpret known partial fills

> Explain [PARTIAL FILL RECORDS], including cumulative quantity, average price, actual fees, remaining quantity and total spent. Report unknowns without creating a local reservation gate or changing other requested orders.

### 152. Review historical order evidence

> Review [BROKER HISTORY EXPORT] for account/status/date scope, pagination and missing pages. Distinguish a lack of matching evidence from proof that no order exists. Make no broker writes for this review.

### 153. Record observed outcomes privately

> Create a private factual journal of [HOST/BROKER RESPONSES]. Distinguish requested, submitted, accepted, partially filled, filled and unknown outcomes; never fabricate broker status from a local identifier.

### 154. Check handoff privacy

> Test the handoff CLI using fictional account and authentication fields. Verify sensitive values are redacted in its display while the in-memory API preserves the host payload. Do not include actual credentials.

### 155. Explain responsibilities

> Explain which parts of [WORKFLOW] are research, optional payload formatting, host submission, broker acceptance, monitoring and accounting. Identify actual unsupported host features without describing them as skill policy restrictions.

### 156. Audit legacy migration

> Review an older package installation for obsolete execution instructions. Use the current handoff and advisory references; do not reactivate policy.json, grants, tickets, monitoring leases or old live-readiness modules. Preserve private historical data unless I explicitly request its removal.


## Saved research and incremental refresh

**Audience:** All levels. Guides: [research memory](references/research-memory.md), [research handoff](references/research-handoff.md).

### 157. Save a reusable research campaign

> Save [COMPLETED RESEARCH] in a local immutable library with source evidence, mandate, full-universe coverage, inputs, decisions and replay results. Keep private records outside the distributable skill.

### 158. Refresh without repeating everything

> Refresh [SAVED CAMPAIGN] for [NEW CUTOFF]. Verify its manifest, reuse unchanged primary evidence after revalidation, refresh changing prices/news/events and rerank the full eligible universe.

### 159. Resume an incomplete full-market scan

> Resume [RESEARCH ARCHIVE] from its actual outstanding acquisition and evidence backlog. Preserve successful work, retry appropriately and report whether remaining gaps can change the research or final-selection result.

### 160. Detect changed assumptions

> Compare the prior and current research inputs for [COMPANIES]. Identify changed facts, guidance, events, normalization assumptions and mandate settings, and explain which conclusions must be reconsidered.

### 161. Preserve correction provenance

> Correct [KNOWN RESEARCH ERROR] with supporting source bytes and an explicit audit trail. Preserve the original snapshot and show the effect of rerunning the same calculation and decision contract.

### 162. Create a clean research handoff

> Prepare a portable handoff for [CAMPAIGN] with the actual prompt, contract, data, evidence decisions, coverage and hashes. Keep broker credentials, account identifiers and copyrighted full reports out of the shared package.


## Cross-model reproducibility and audits

**Audience:** Advanced to quant. Guides: [model independent research](references/model-independent-research.md), [quant workbench](references/quant-workbench.md), [research handoff](references/research-handoff.md), [PROVENANCE](PROVENANCE.md), [SOURCES](SOURCES.md), [THIRD PARTY NOTICES](THIRD-PARTY-NOTICES.md).

### 163. Replay a numerical research bundle

> Verify [BUNDLE] and rerun its computations from frozen code, profile, data and parameters. Compare actual outputs using the documented numeric tolerance and exact decision/status checks.

### 164. Compare models on identical inputs

> Prepare a blinded comparison of [MODEL A] and [MODEL B] using the same complete skill, contract and frozen data. Compare numerical results, exclusions and decisions separately from explanation quality.

### 165. Explain different stock lists

> Reconcile [RESULT A] and [RESULT B] across universe, cutoff, horizon, profile, data freshness, coverage, prior preferences and review decisions. Distinguish candidate overlap from buy-eligibility agreement.

### 166. Compare independent data acquisition

> Have each authorized research environment acquire fresh evidence for [SAME MANDATE]. Compare data lineage and coverage before comparing picks; do not label this the same experiment as frozen-input replay.

### 167. Audit a final-selection claim

> Run the handoff and report checks on [RESEARCH RESULT]. Verify saved release/index evidence, ranking-relevant acquisition failures, review order and unresolved primary or horizon requirements.

### 168. Review method provenance

> Review [METHOD OR SCRIPT] for its actual mathematical assumptions, implementation provenance, dependencies and attributed sources. Distinguish original integration code from imported libraries and data-use rights.


## Institutional research workflows and capability development

**Audience:** Expert to quant. Guides: [institutional manager](references/institutional-manager.md), [institutional gap review 4.2](references/institutional-gap-review-4.2.md).

### 169. Run a manager-style review

> Review [PORTFOLIO AND MANDATE] across data quality, theses, construction, risk, costs, accounting and operations. Prioritize unresolved decisions and distinguish analysis support from custody or audited fund administration.

### 170. Audit institutional readiness

> Assess this deployment against the skill's current capability inventory. Separate implemented/tested software, empirically validated investment effectiveness and available data or operational dependencies.

### 171. Plan a point-in-time research database

> Design a coverage-first historical-data plan for [STRATEGY AND HORIZON]. Identify which public records can be reconstructed, which observations must be archived prospectively and which gaps may require licensed data.

### 172. Design a sentiment validation study

> Plan an adjudicated test of issuer matching, timestamp handling, negation and material-event classification for [NEWS DATA]. Separate extraction accuracy from a later causal, after-cost return study.

### 173. Design an analyst-skill study

> Specify the recommendation ledger, price history, entry/exit rules, benchmark and bias controls needed to measure analyst performance independently. Audit available data before trusting provider rankings or constructing weights.

### 174. Review host operational evidence

> Review a host-provided offline failure drill for empty responses, disconnects, partial fills and restarts. Distinguish observed behavior from untested claims. Do not create local execution gates or claim this skill controls the host.

### 175. Maintain the documentation

> Review the latest implemented capabilities, update the README as a current usage guide and refresh the example-prompt catalog without a fixed count. Regenerate the examples and run the documentation release check before packaging.

## Keeping this catalog current

Examples are reviewed against the current capabilities and regenerated for
every package update. There is no fixed count: add distinct useful workflows,
revise changed behavior and remove claims the skill cannot support. See the
[maintenance procedure](references/maintaining-the-skill.md).
