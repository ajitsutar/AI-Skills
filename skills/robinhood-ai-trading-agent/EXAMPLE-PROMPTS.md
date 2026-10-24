# Example prompts: learning, investing, trading and quantitative research

<!-- Generated from references/example-prompts.json with scripts/release_docs.py. -->

250 examples across 35 workflows, from first-time investing to quantitative research.

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
| [News, sentiment and between-quarter guidance](#news-sentiment-and-between-quarter-guidance) | Intermediate to quant | 9 |
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
| [Saved research and incremental refresh](#saved-research-and-incremental-refresh) | All levels | 7 |
| [Cross-model reproducibility and audits](#cross-model-reproducibility-and-audits) | Advanced to quant | 7 |
| [Institutional research workflows and capability development](#institutional-research-workflows-and-capability-development) | Expert to quant | 7 |
| [Traceable report facts](#traceable-report-facts) | Investors, research authors and quantitative reviewers | 3 |
| [Bound inputs and computed reports](#bound-inputs-and-computed-reports) | Research authors, traders and quantitative reviewers | 7 |
| [Request fidelity and accounting alignment](#request-fidelity-and-accounting-alignment) | Investors, portfolio analysts and quantitative reviewers | 19 |
| [Source-bound calculations and evidence meaning](#source-bound-calculations-and-evidence-meaning) | Investor to quant | 10 |
| [Reproducible technical indicators and charts](#reproducible-technical-indicators-and-charts) | Intermediate to quant | 5 |
| [Accounting quality and explicit valuation models](#accounting-quality-and-explicit-valuation-models) | Intermediate to expert | 6 |
| [Evidence-bound sentiment scores and validation](#evidence-bound-sentiment-scores-and-validation) | Intermediate to quant | 5 |
| [Fundamental factors and statistical structure](#fundamental-factors-and-statistical-structure) | Quant | 4 |
| [Explicit multi-asset valuation and settlement research](#explicit-multi-asset-valuation-and-settlement-research) | Quant | 5 |
| [Multi-asset paper accounting and platform evidence](#multi-asset-paper-accounting-and-platform-evidence) | Quant | 5 |
| [Explicit time-series scenarios and diagnostics](#explicit-time-series-scenarios-and-diagnostics) | Quant | 3 |

## Getting started and learning

**Audience:** Beginner. Guides: [personal setup](references/personal-setup.md), [small account research](references/small-account-research.md), [portfolio decision calculations](references/portfolio-decision-calculations.md).

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

### 43. Complete an evidence-backed sentiment review

> Review sentiment for [COMPANY] over [WINDOW] at [CUTOFF]. Preserve deterministic triage labels, record qualitative interpretations with sources using sentiment_review, disclose news, analyst, price/volume, positioning and social coverage, and show contrary evidence without treating unscored language as neutral or a buy signal.


## Analyst reports, consensus and financial information

**Audience:** Intermediate to expert. Guides: [analyst research](references/analyst-research.md).

### 44. Build a stock information map

> Build an information coverage map for [COMPANY]: financials, valuation, guidance, forecasts, catalysts, ownership, capital allocation and material risks. Dynamically find relevant finance sites and retain source dates, lineage and access gaps.

### 45. Find accessible analyst research

> Locate publicly accessible analyst reports and attributed research excerpts for [COMPANY], including credible opposing views. Distinguish a full report, a quoted recommendation, commentary, a snippet and a paywall.

### 46. Calculate forward target consensus

> Review forward [52-WEEK OR 12-MONTH] analyst targets for [COMPANY]. Match horizon, currency, share basis and original issue dates, then calculate the observed cohort's mean, median, range and IQR with independent-firm counts.

### 47. Reconcile different website targets

> Compare consensus targets reported by [PROVIDERS]. Trace upstream data sources, population, as-of dates and definitions. Keep overlapping provider pools separate rather than averaging their averages.

### 48. Review analyst track records

> Assess the analysts covering [COMPANY]. Find sourced success rates, average returns, sample counts, periods, benchmarks and holding rules; report missing definitions and distinguish provider-reported records from independently reproduced performance.

### 49. Assess reputation and incentives

> Evaluate [ANALYST OR AUTHOR]'s role, sector expertise, methodology, corrections and disclosed conflicts. Distinguish verifiable experience from firm prestige, followers or a few visible winning calls.

### 50. Compare revisions without mixing metrics

> Review dated rating changes, target changes and EPS/revenue estimate revisions for [COMPANY]. Match firms, fiscal periods, currency and accounting basis, and separate genuine revisions from initiations or changed coverage.

### 51. Separate fair value from price targets

> Compare [INTRINSIC FAIR-VALUE ESTIMATE], forward analyst targets and the historical 52-week trading range for [COMPANY]. Explain their different meanings and why none alone establishes a probability of achieving my desired return.


## Social hypotheses, ownership and disclosure context

**Audience:** Intermediate. Guides: [research methods](references/research-methods.md), [screening and value traps](references/screening-and-value-traps.md).

### 52. Research competing public narratives

> Investigate bullish and bearish arguments about [COMPANY] on Reddit and accessible X posts. Deduplicate repeated claims, identify promotional interests and verify material facts with primary sources.

### 53. Interpret insider transactions

> Review [INSIDER FILINGS] for [COMPANY]. Distinguish discretionary purchases/sales from awards, option exercises and tax withholding, including filing footnotes, amendments and transaction versus disclosure dates.

### 54. Assess ownership changes carefully

> Review [INSTITUTIONAL OWNERSHIP REPORTS] for [COMPANY]. Identify reporting periods, filing delays, amendments and entity scope, and explain what the data cannot establish about current positions.

### 55. Challenge a political-trading claim

> Investigate [PUBLIC CLAIM ABOUT A DISCLOSED TRADE]. Verify the original disclosure, transaction range, timing and amendments, and distinguish evidence from speculation about motive or future returns.

### 56. Review short-interest and options narratives

> Check [SHORT-SQUEEZE OR OPTIONS-FLOW THESIS] using accessible dated evidence. Distinguish short interest, borrow conditions and options activity, including delays and unknown positioning, without treating a popular narrative as an entry signal.


## Portfolio planning and investor decisions

**Audience:** Beginner to expert. Guides: [portfolio management](references/portfolio-management.md), [institutional manager](references/institutional-manager.md), [portfolio decision calculations](references/portfolio-decision-calculations.md), [planning input roles](references/planning-input-roles.md), [portfolio projection](references/portfolio-projection.md), [planning comparison](references/planning-comparison.md).

### 57. Critique my current investments

> Review [HOLDINGS, CASH AND RECURRING CONTRIBUTIONS] for [HORIZON]. Assess issuer, sector and theme concentration, overlapping funds, employer exposure and the effect of future contributions before proposing changes.

### 58. Manage employer-stock concentration

> Review [CURRENT EMPLOYER STOCK] and [NET VESTING SCHEDULE]. Account for shares withheld or sold for taxes, separate employment and investment exposure, and compare diversification paths without assuming gross grants are spendable cash.

### 59. Compare portfolio allocations

> Compare core, swing, intraday and cash allocations for [CAPITAL AND OBJECTIVES]. Explain concentration and loss scenarios without imposing sample weights or approval requirements on my account.

### 60. Rebalance with contributions

> Use [HOLDINGS], [TARGETS] and a new contribution of [AMOUNT] to propose a cash-first rebalance. Apply drift bands and show residual imbalances, turnover and transaction constraints.

### 61. Plan a withdrawal

> I need [AMOUNT] on [DATE]. Compare ways to raise the cash given settlement, liquidity, tax lots, concentration and long-term allocation effects. Produce a proposal without placing orders.

### 62. Look through funds and share classes

> Analyze the combined issuer, sector and theme exposures in [STOCKS AND FUNDS]. Include overlapping holdings, multiple share classes and missing holdings data, then identify the main concentration risks.

### 63. Compare funds for a portfolio role

> Compare [FUNDS] for [ROLE AND HORIZON]. Evaluate holdings, diversification, fees, liquidity, tracking, distribution and tax considerations using appropriate fund evidence.

### 64. Review tax-aware sale alternatives

> Using [LOT RECORDS], compare lot-selection proposals for selling [POSITION]. Estimate gains/losses and flag possible wash-sale issues, including uncertainty from other accounts and future purchases.


## Fractional shares and recurring contributions

**Audience:** Beginner to quant; execution depends on verified broker support. Guides: [fractional shares](references/fractional-shares.md), [portfolio management](references/portfolio-management.md), [execution handoff](references/execution-handoff.md), [portfolio decision calculations](references/portfolio-decision-calculations.md).

### 65. Invest a small dollar budget

> Prepare an allocation and host handoff for [SECURITIES] using the full [DOLLAR BUDGET]. Preserve native dollar instructions where supported; explain fractional quantities, estimated costs and final-debit uncertainty without imposing whole-share or template cash restrictions.

### 66. Plan one recurring contribution

> For [CONTRIBUTION OCCURRENCE], calculate [DOLLAR AMOUNTS PER SECURITY] using fractional shares. Show rounding and any user-requested reserve, but retain the original per-symbol dollar amounts for a supported native dollar handoff. Label quantity and cash-debit outputs as reference-price estimates, not guaranteed market spending or submitted orders. Keep supplied account, plan and occurrence context with a standalone handoff artifact, using companion context when the broker schema has no matching fields. Produce the requested handoff without creating an unrequested future schedule or a local approval ticket.

### 67. Compare fractional and whole-share implementation

> Apply [TARGET WEIGHTS] to [HOLDINGS AND NEW CASH] in fractional and whole-share planning modes. Compare allocation drift, fees, feasible trades and leftover cash. Clearly label any offline increment assumptions and identify the broker evidence still needed for execution.

### 68. Validate fractional execution capabilities

> Inspect actual connected schemas and symbol tradability for [FRACTIONAL PROPOSALS]. Explain precision, minimums, quantity/notional semantics and fill reporting. Preserve requested native dollar-market instructions where supported rather than silently changing the order basis.

### 69. Interpret fractional partial fills

> Review [FRACTIONAL ORDER AND CUMULATIVE FILLS] against observed broker records. Preserve exact filled and remaining quantities, explain actual fees and residual cash, and distinguish cumulative updates from new fills.

### 70. Analyze a small tactical position

> Calculate hypothetical fractional sizes for [ENTRY, STOP, TARGET, CASH AND LOSS SCENARIOS]. Show sensitivity to gaps and costs. Treat the calculation as advice; do not require protective orders or a volatility model before the host handoff.


## Quantitative portfolio construction

**Audience:** Quant. Guides: [quant workbench](references/quant-workbench.md), [institutional manager](references/institutional-manager.md).

### 71. Construct a constrained allocation

> Run the allocation helper on [ASSETS, COVARIANCE AND MANDATE]. Enforce issuer/group, gross/net, cash, turnover, liquidity, volatility and scenario limits; show binding constraints and compare with a simple baseline.

### 72. Investigate infeasibility

> Diagnose why [ALLOCATION INPUT] is infeasible. Identify conflicting constraints and show possible policy changes for review without silently relaxing limits or reporting an invalid allocation.

### 73. Validate a return calibration

> Audit [EXPECTED-RETURN CALIBRATION] before using it in portfolio construction. Check matching horizon and return units, training/test chronology, retained evidence and all variants; reject factor scores or analyst upside substituted for expected returns.

### 74. Stress covariance assumptions

> Recompute [PORTFOLIO PROPOSAL] under declared alternative covariance and scenario inputs. Compare weight stability, concentration and risk sensitivity; distinguish supplied assumptions from estimated or validated parameters.

### 75. Evaluate costs and capacity

> Construct or compare allocations using [TURNOVER COSTS, IMPACT ASSUMPTIONS AND CAPACITY LIMITS]. Show how proposed weights change and where the portfolio exceeds plausible tradable size.

### 76. Translate weights into feasible proposals

> Review [CONTINUOUS TARGET WEIGHTS] against capital, share sizes, current holdings, unsettled cash, tax lots and broker capabilities. Identify rounding and implementation gaps rather than treating solver weights as executable orders.

### 77. Constrain benchmark tracking risk

> Construct [PORTFOLIO] with the declared benchmark weights and tracking-volatility constraint. Compare it with the minimum-risk proposal and identify which active exposures consume the risk budget.

### 78. Evaluate signed research weights

> Evaluate [RESEARCH ALLOCATION] with explicit signed bounds, gross/net limits and supplied borrow availability and costs. Flag missing evidence and keep the result separate from unsupported live short-selling execution.


## Volatility forecasting and portfolio risk

**Audience:** Advanced to quant. Guides: [garch volatility](references/garch-volatility.md), [quant workbench](references/quant-workbench.md), [portfolio management](references/portfolio-management.md).

### 79. Run evidenced GARCH

> Run the bundled GARCH(1,1) workflow on audited prices for [SYMBOL]. Report data counts, convergence, training/holdout separation, QLIKE against the baseline, forecast horizon and actual sizing eligibility.

### 80. Compare asymmetric volatility models

> Compare GARCH, GJR-GARCH and supported EGARCH forecasts on the same audited data and holdout. Record all variants, respect forecast-horizon limitations and separate volatility forecasts from direction.

### 81. Use volatility as advice

> Explain how [VOLATILITY RESULT] changes the risk interpretation of [ALLOCATION]. Compare it with simpler realized-volatility and stress estimates, disclose missing evidence and keep every diagnostic advisory rather than an execution gate.

### 82. Estimate historical tail losses

> Calculate empirical VaR, expected shortfall and drawdown for [RETURN SERIES] at [CONFIDENCE LEVEL]. Use frequency declared in the request or supplied data, preserving its provenance; state sample size, missing data and why historical tail estimates may miss future gaps.

### 83. Run portfolio stress scenarios

> Stress [PORTFOLIO] under market, sector, issuer, rate, volatility and currency shocks appropriate to its instruments. Include every position and report loss concentrations, assumptions and unsupported pricing cases.

### 84. Assess a risk-model breach

> Apply the monitoring helper to [OBSERVATIONS] with limits fixed before the result. Review stale data, coverage, realized versus forecast risk, costs and reconciliation errors without automatically retuning models or raising limits.

### 85. Estimate covariance and component risk

> Estimate aligned-return covariance and component risk for [PORTFOLIO]. Review sample coverage, asset ordering and documented shrinkage settings, then show sensitivity without claiming an unimplemented estimator was run.


## Market-data quality and financial normalization

**Audience:** Advanced to quant. Guides: [data and analytics](references/data-and-analytics.md), [financial normalization](references/financial-normalization.md), [quant workbench](references/quant-workbench.md).

### 86. Audit prices before modeling

> Audit [PRICE FILE] for timestamp order, duplicates, missing sessions, timezones, price basis and large jumps. Investigate splits, dividends and real event moves instead of deleting inconvenient returns.

### 87. Check action and share-basis consistency

> Reconcile [PRICE AND CORPORATE-ACTION FILES] with share counts and financial per-share metrics. Identify adjusted versus execution prices, ADR ratios and action dates that could distort ranking or backtests.

### 88. Extract cutoff-admissible SEC facts

> Use verified CIKs and my configured SEC contact identity to obtain primary financial data for [COMPANIES]. Preserve source bytes and extract only facts admissible at [CUTOFF], retaining amendments and accounting context.

### 89. Resolve normalization failures

> Run strict normalization on [EVIDENCE RECORDS]. Explain missing concepts, periods, units, entity scope or source acceptance, and prepare a precise recovery backlog instead of imputing favorable values.

### 90. Compare alternative data providers

> Compare [PROVIDER SNAPSHOTS] for the same securities and cutoff. Reconcile field definitions, fiscal periods, timestamps, price adjustments and missingness, then document which differences could change the result.

### 91. Design a historical-vintage audit

> Audit [HISTORICAL DATASET] for membership changes, delistings, restatements, estimate revisions and publication availability. Identify which dates can support point-in-time research and which remain exploratory.

### 92. Reconstruct trailing financial flows

> Reconstruct [TTM METRICS] from dated annual and interim filings. Avoid double-counting YTD periods, check fiscal calendars and amendments, and retain the source and calculation for each normalized value.

### 93. Audit earnings-yield arithmetic

> Audit [VALUATION SNAPSHOT] for mismatched price/EPS dates, trailing versus forward definitions, negative earnings and inconsistent share counts. Show which comparisons remain valid and which require correction.


## Statistical research and model validation

**Audience:** Quant. Guides: [quant research](references/quant-research.md), [quant workbench](references/quant-workbench.md), [research methods](references/research-methods.md).

### 94. Create causal validation folds

> Build purged expanding-window folds from [SAMPLES WITH FEATURE-AVAILABILITY AND LABEL-END TIMES]. Specify training size, test size and embargo; verify that overlapping outcomes and future features do not leak across splits.

### 95. Measure uncertainty with serial dependence

> Run HAC inference and a seeded block bootstrap on [ALIGNED NET-EXCESS RETURNS]. Declare lag and block choices before evaluating results, and compare uncertainty with a naive independent-observation assumption.

### 96. Control multiple testing

> Use the full trial registry [REGISTRY] to apply the supported multiple-testing and qualified Sharpe diagnostics. Report all attempted variants, their dependence assumptions and anything that prevents a valid adjusted claim.

### 97. Attribute returns to factors

> Regress [EXCESS RETURNS] on [ALIGNED FACTORS] using the supported factor/HAC workflow. Show exposure, residual performance and uncertainty without interpreting correlation as a causal edge.

### 98. Preregister a strategy experiment

> Write a research contract for [STRATEGY]: universe, horizon, signal, costs, benchmark, variants, untouched evaluation window and acceptance criteria. Identify data and statistical-design gaps before running it.

### 99. Review strategy evidence

> Evaluate [STRATEGY VERSION] using retained development, validation, untouched-test and forward observations. Recompute the chosen quantitative criteria, inspect data/code hashes and all variants, and explain confidence and limitations without creating a live-promotion requirement.

### 100. Test sensitivity without hindsight

> Evaluate [FROZEN STRATEGY] against prespecified neighboring parameters, delayed fills, missed trades and worse costs. Keep all outcomes and distinguish robustness analysis from selecting a new winner on the test set.

### 101. Evaluate a challenger model

> Compare [CHAMPION] and [CHALLENGER] on the same frozen contract and genuinely new paper observations. Separate implementation agreement, forecast calibration, net performance and operational changes before recommending replacement.


## Backtesting and paper-validation design

**Audience:** Advanced to quant. Guides: [quant workbench](references/quant-workbench.md), [research methods](references/research-methods.md), [strategy playbook](references/strategy-playbook.md).

### 102. Replay a period portfolio

> Run the portfolio simulator on [CAUSAL DECISIONS AND TOTAL RETURNS], including cash, benchmark, tradability, costs, impact and trade-value capacity. Verify that decisions precede returns and explain simulator limitations.

### 103. Backtest the intraday baseline

> Replay the supported opening-range-breakout setup on [INTRADAY DATA]. Use completed-bar decisions, costs and conservative fills; disclose stop/target ordering ambiguity and facts the bars cannot establish.

### 104. Compare daily and intraday engines

> Choose the appropriate bundled simulator for [STRATEGY AND DATA]. Explain which settlement, fill, latency and portfolio behaviors it models and which require separate paper observations.

### 105. Compare after-cost benchmarks

> Compare [BACKTEST] with cash and suitable passive benchmarks at comparable exposure. Report net returns, drawdowns, turnover and cost stress rather than choosing a winner solely by gross return or Sharpe.

### 106. Design a forward-paper study

> Create a forward-paper protocol for [FROZEN STRATEGY]. Specify decision/quote/fill observations, performance and operational criteria, and the independent evidence needed before considering live use.

### 107. Audit an impressive backtest

> Review [BACKTEST BUNDLE] for survivor bias, revised data, look-ahead, trial selection, unrealistic fills, omitted costs and overlapping labels. Identify what can be reproduced and what cannot support the performance claim.

### 108. Run the daily trend baseline

> Run the bundled daily SMA research baseline on [AUDITED DAILY DATA]. Use its actual chronological rules and costs, compare it with a passive baseline and explain why a successful replay does not establish a profitable strategy.


## Multi-asset research, pricing and hedging

**Audience:** Advanced to quant; research scope. Guides: [multi asset playbook](references/multi-asset-playbook.md), [quant workbench](references/quant-workbench.md).

### 109. Choose the supported instrument route

> Review [INSTRUMENT LIST] and map each position to the skill's supported research, pricing and risk functions. Identify required data and unsupported live execution rather than representing derivatives as shares.

### 110. Price a European option scenario

> Use the supported European option model with [SPOT, STRIKE, MATURITY, VOLATILITY, RATE AND DIVIDEND ASSUMPTIONS]. Calculate price and sensitivities, check parity where applicable and disclose model limitations.

### 111. Identify unsupported option assumptions

> Assess [OPTION OR HEDGE] for exercise style, payoff, settlement and volatility assumptions. Explain whether the bundled European model applies and what is missing for American or exotic structures.

### 112. Analyze a fixed bond

> Price [NONCALLABLE FIXED CASH FLOWS] using the supplied zero curve and spread. Evaluate rate/spread scenarios and explain why callable, prepayable or credit-default features need additional models.

### 113. Stress futures exposure

> Evaluate [FUTURES POSITIONS] with explicit contract multipliers, currencies and price shocks, including negative-price cases when relevant. Separate scenario P&L from actual margin and settlement requirements.

### 114. Stress foreign-currency exposure

> Evaluate [POSITIONS AND FX SHOCKS] in [BASE CURRENCY]. Reconcile currency conversion, contract units and collateral assumptions, and identify missing exposures.

### 115. Compare hedge scenarios

> Compare [HEDGE CANDIDATES] under common portfolio shocks and stated costs. Show basis risk, scenario protection, residual exposure and pricing or execution capabilities that remain unavailable.

### 116. Build a multi-asset mandate

> Draft a mandate for [ASSETS AND OBJECTIVES] with explicit permitted instruments, leverage, liquidity, collateral, risk budgets and benchmarks. Keep research capabilities separate from verified broker execution support.

### 117. Stress illiquid commitments

> Stress [PRIVATE-ASSET COMMITMENTS AND DISTRIBUTION ASSUMPTIONS] through the cash-ladder and cash-flow tools. Evaluate funding gaps and XIRR sensitivity while distinguishing assumed cash flows from an independently valued private asset.


## Cash, settlement and funding

**Audience:** Intermediate to quant. Guides: [settled cash planning](references/settled-cash-planning.md), [quant workbench](references/quant-workbench.md), [planning input roles](references/planning-input-roles.md), [portfolio projection](references/portfolio-projection.md), [planning comparison](references/planning-comparison.md).

### 118. Compare a cash buffer

> Model [DAY-TRADING PLAN] with an optional reserve of [DOLLARS OR PERCENT OF EQUITY]. Compare settlement paths and available cash under observed account conventions; present the buffer as advice, not a skill-imposed trade gate.

### 119. Plan staggered cash usage

> Given [POSITIONS, EXPECTED TRADES AND CASH], compare settlement-aware trading schedules. Use current broker availability and calendars rather than assuming alternating groups of stocks automatically avoid funding gaps.

### 120. Build a currency cash ladder

> Run the cash-ladder helper on [SETTLED BALANCES, RESERVATIONS AND CONFIRMED EVENTS]. Enforce currency-specific floors and identify when liabilities exceed available funds.

### 121. Analyze reservations and debits

> Analyze [ORDER RESERVATIONS AND DEBITS] for double counting and account cash-flow differences. Match confirmed events, retain source evidence and explain unknown outcomes. This is accounting analysis, not a local execution lock.

### 122. Review a funding shortfall

> Review [CASH-LADDER RESULT] for a settlement or collateral shortfall. Distinguish confirmed credits from expected sales and propose feasible timing or size changes without assuming unavailable cash can be spent.

### 123. Check a withdrawal against trading

> Combine [WITHDRAWAL PLAN] and [TRADING PLAN] to assess settled-cash availability, reserved amounts and liquidity floors through [DATE]. Show conflicts before any order or withdrawal proposal.


## Performance accounting, execution costs and attribution

**Audience:** Intermediate to quant. Guides: [portfolio management](references/portfolio-management.md), [quant workbench](references/quant-workbench.md), [portfolio decision calculations](references/portfolio-decision-calculations.md).

### 124. Measure investment performance

> Calculate time-weighted performance from [VALUATIONS AND EXTERNAL FLOWS]. Separate deposits and withdrawals from investment P&L and disclose missing valuations or timing ambiguity.

### 125. Calculate my money-weighted return

> Compute XIRR from [DATED CONTRIBUTIONS, DISTRIBUTIONS AND TERMINAL VALUE]. Check signs and whether the cash-flow pattern supports the conventional calculation; compare it with time-weighted return.

### 126. Explain active return

> Run the supported Brinson attribution using [BEGINNING PORTFOLIO/BENCHMARK GROUP WEIGHTS AND RETURNS]. Include cash and reconcile allocation, selection and interaction effects to the active result.

### 127. Measure execution shortfall

> Decompose [ORDER AND FILL RECORDS] using decision, arrival and terminal prices. Include fees, partial fills and unfilled opportunity cost, and compare buys and sells with the correct signs.

### 128. Review results by sleeve

> Compare core, swing and intraday performance from [JOURNAL]. Use appropriate benchmarks, flow treatment and net costs, and distinguish investment effects from execution problems or policy deviations.

### 129. Challenge a win-rate claim

> Review [TRADE HISTORY] using average win/loss, expectancy, drawdown, costs, exposure and uncertainty. Explain why win rate alone does not establish a profitable or scalable strategy.

### 130. Reconcile the cash ledger

> Reconcile [OPENING CASH, TRADES, DIVIDENDS, FEES AND EXTERNAL FLOWS] with [BROKER CASH]. Identify discrepancies and unconfirmed events before calculating spendable cash or investment performance.

### 131. Compare tax-lot proposals

> Compare the supported FIFO, HIFO and specific-lot proposals for [SALE AND COST-BASIS RECORDS]. Show gain/loss differences and potential wash-sale flags, with unresolved outside-account information retained.


## Day trading and supervised paper sessions

**Audience:** Intermediate to expert. Guides: [short term trading](references/short-term-trading.md), [strategy playbook](references/strategy-playbook.md), [portfolio decision calculations](references/portfolio-decision-calculations.md), [planning input roles](references/planning-input-roles.md).

### 132. Prepare a session brief

> Prepare an intraday brief for [WATCHLIST]. Verify session times, current catalysts, earnings, halts, liquidity, spreads and data freshness; disclose missing inputs before identifying setups.

### 133. Build an intraday watchlist

> Start from the configured stock universe and apply [PRICE, LIQUIDITY AND SPREAD FILTERS] to build a tactical watchlist. Separate membership, tradability and entry-signal qualification.

### 134. Analyze an opening-range setup

> Evaluate the opening-range-breakout research example for [SYMBOL] using completed bars. Report range, trigger, invalidation, reference exits, costs and evidence limitations. The simulated rules are not execution conditions.

### 135. Reject premature confirmation

> Review [CHART OR BAR DATA] for a possible breakout. Distinguish completed from unfinished candles, dated quotes and missing event evidence. Explain how these limitations affect the research conclusion without imposing an execution pause.

### 136. Size a paper trade after costs

> For [ENTRY, STOP, TARGET AND CAPITAL], calculate affordable whole-share size, planned loss and net reward/risk. Include pending exposure, spread/slippage assumptions and the possibility that valid size is zero.

### 137. Run a supervised paper session

> Simulate a research session for [WATCHLIST] from available completed bars. Use declared setup rules, conservative fills and a journal. Report missing observations and the limits of the simulation without implying a background service or imposing execution conditions.

### 138. Handle losses and closing risk

> Review today's marked positions, trades and pending orders. Explain realized/unrealized losses, gap and closing risk, and possible responses as advice. Report the actual host/broker state without imposing a new-entry stop or requiring a monitoring lease.


## Recommendations and requested market handoffs

**Audience:** All levels; actual broker support and user authorization required. Guides: [execution handoff](references/execution-handoff.md), [fractional shares](references/fractional-shares.md), [allocation policy](references/allocation-policy.md), [portfolio decision calculations](references/portfolio-decision-calculations.md).

### 139. Recommend and hand off one allocation

> Research [UNIVERSE] for [HORIZON] and recommend how to invest the full [BUDGET]. I also instruct the connected host to place those purchases at market. Preserve that instruction without adding skill approvals, grants, tickets, volatility conditions or price-drift thresholds; state recommendation uncertainty honestly.

### 140. Use my existing order instruction

> Prepare the host handoff for [EXISTING ORDER INSTRUCTION]. Preserve the requested amounts and order type without asking again because research prices or quote timestamps changed.

### 141. Keep market-price uncertainty informational

> For [MARKET ORDER REQUEST], state the research as-of and explain possible market-price and fee differences. I accept that uncertainty; do not pause or request reapproval based on price movement, spreads or quote age.

### 142. Preserve a native dollar amount

> Prepare [DOLLAR ALLOCATION] for a host that supports native dollar-market instructions. Preserve the amount and explain whether the broker estimates shares from a recent trade price, so final debit may differ. Do not silently round to whole shares.

### 143. Preserve an explicit limit instruction

> Prepare a handoff for [SYMBOL, SIDE, QUANTITY AND USER-SPECIFIED LIMIT]. Preserve my supplied limit exactly; the skill should not replace it with a market order or invent a new price condition.

### 144. Keep research findings advisory

> Explain the concentration, earnings, volatility, spread and liquidity risks of [ORDER REQUEST], then preserve my existing host instruction. Do not turn any research finding or sample allocation constraint into an execution veto.

### 145. Compare stock choices for a small amount

> Give me [NUMBER] alternative stocks, each suitable for investing the full [BUDGET] for [HORIZON]. Compare dated catalysts, valuation, evidence and downside. Treat them as alternatives rather than splitting the amount unless I ask.

### 146. Handle a recurring request clearly

> Prepare the requested fractional contribution [AMOUNTS AND SECURITIES] and distinguish one occurrence from a broker-native recurring schedule. Preserve any scheduling instruction I actually gave; do not claim a local calculation installed a schedule.

### 147. Explain a broker rejection

> Interpret [ACTUAL BROKER RESPONSE] and separate the broker or platform requirement from this skill. Report exactly what happened without inventing a local live policy or readiness checklist.


## Host integration and observed outcomes

**Audience:** Expert; broker and authorization dependent. Guides: [execution handoff](references/execution-handoff.md), [host execution integration](references/host-execution-integration.md), [broker integration](references/broker-integration.md).

### 148. Inspect actual connected tools

> Inspect the available broker tool schemas for [REQUEST]. Explain supported market/share/dollar/limit inputs and actual broker requirements without creating a skill capability gate or inventing unavailable tools.

### 149. Prepare a pure handoff

> Pass [ORDER DETAILS] through execution_handoff.handoff or its CLI. Verify that it preserves the supplied order, needs no runtime policy, grants or evidence, and makes no broker network call.

### 150. Compare exact payloads

> Compare [REQUESTED ORDER PAYLOAD] with [HOST HANDOFF]. Identify changes to side, amount, quantity, type, account routing or time-in-force. Do not equate a correctly formatted payload with a submitted or filled order.

### 151. Explain an empty connector response

> The connector returned an empty object for [ORDER]. Interpret available JSON-RPC errors, MCP isError, content and structured content without assuming acceptance or rejection. Keep credentials and private identifiers out of the report; actual broker reconciliation belongs to the host.

### 152. Interpret known partial fills

> Explain [PARTIAL FILL RECORDS], including cumulative quantity, average price, actual fees, remaining quantity and total spent. Report unknowns without creating a local reservation gate or changing other requested orders.

### 153. Review historical order evidence

> Review [BROKER HISTORY EXPORT] for account/status/date scope, pagination and missing pages. Distinguish a lack of matching evidence from proof that no order exists. Make no broker writes for this review.

### 154. Record observed outcomes privately

> Create a private factual journal of [HOST/BROKER RESPONSES]. Distinguish requested, submitted, accepted, partially filled, filled and unknown outcomes; never fabricate broker status from a local identifier.

### 155. Check handoff privacy

> Test the handoff CLI using fictional account and authentication fields. Verify sensitive values are redacted in its display while the in-memory API preserves the host payload. Do not include actual credentials.

### 156. Explain responsibilities

> Explain which parts of [WORKFLOW] are research, optional payload formatting, host submission, broker acceptance, monitoring and accounting. Identify actual unsupported host features without describing them as skill policy restrictions.

### 157. Audit legacy migration

> Review an older package installation for obsolete execution instructions. Use the current handoff and advisory references; do not reactivate policy.json, grants, tickets, monitoring leases or old live-readiness modules. Preserve private historical data unless I explicitly request its removal.


## Saved research and incremental refresh

**Audience:** All levels. Guides: [research memory](references/research-memory.md), [research handoff](references/research-handoff.md).

### 158. Save a reusable research campaign

> Save [COMPLETED RESEARCH] in a local immutable library with source evidence, mandate, full-universe coverage, inputs, decisions and replay results. Keep private records outside the distributable skill.

### 159. Refresh without repeating everything

> Use optional partial fetch for [SUPPLIED PORTABLE CAMPAIGN BUNDLE] at [NEW CUTOFF]. Verify its manifest and current source-index evidence before reusing unchanged statements. Refresh membership, quotes, full history/actions, estimates, news and events; rerank the whole eligible universe. Fall back to fresh acquisition for missing or incompatible evidence and retain original retrieval times and parent hashes.

### 160. Use the same optional partial fetch across models

> Have Codex, Muse or Claude use optional partial fetch with [EXPLICIT PORTABLE BUNDLE] and [CURRENT SOURCE CHECKS]. Use the same skill interface rather than relying on hidden model caches. Keep fresh acquisition as the default without opt-in, disclose fallbacks and label shared reuse as shared acquisition, not an independent research replication.

### 161. Resume an incomplete full-market scan

> Resume [RESEARCH ARCHIVE] from its actual outstanding acquisition and evidence backlog. Preserve successful work, retry appropriately and report whether remaining gaps can change the research or final-selection result.

### 162. Detect changed assumptions

> Compare the prior and current research inputs for [COMPANIES]. Identify changed facts, guidance, events, normalization assumptions and mandate settings, and explain which conclusions must be reconsidered.

### 163. Preserve correction provenance

> Correct [KNOWN RESEARCH ERROR] with supporting source bytes and an explicit audit trail. Preserve the original snapshot and show the effect of rerunning the same calculation and decision contract.

### 164. Create a clean research handoff

> Prepare a portable handoff for [CAMPAIGN] with the actual prompt, contract, data, evidence decisions, coverage and hashes. Keep broker credentials, account identifiers and copyrighted full reports out of the shared package.


## Cross-model reproducibility and audits

**Audience:** Advanced to quant. Guides: [model independent research](references/model-independent-research.md), [quant workbench](references/quant-workbench.md), [research handoff](references/research-handoff.md), [PROVENANCE](PROVENANCE.md), [SOURCES](SOURCES.md), [THIRD PARTY NOTICES](THIRD-PARTY-NOTICES.md).

### 165. Replay a numerical research bundle

> Verify [BUNDLE] and rerun its computations from frozen code, profile, data and parameters. Compare actual outputs using the documented numeric tolerance and exact decision/status checks.

### 166. Compare models on identical inputs

> Prepare a blinded comparison of [MODEL A] and [MODEL B] using the same complete skill, contract and frozen data. Compare numerical results, exclusions and decisions separately from explanation quality.

### 167. Explain different stock lists

> Reconcile [RESULT A] and [RESULT B] across universe, cutoff, horizon, profile, data freshness, coverage, prior preferences and review decisions. Distinguish candidate overlap from buy-eligibility agreement.

### 168. Compare independent data acquisition

> Have each authorized research environment acquire fresh evidence for [SAME MANDATE]. Compare data lineage and coverage before comparing picks; do not label this the same experiment as frozen-input replay.

### 169. Audit a final-selection claim

> Run the handoff and report checks on [RESEARCH RESULT]. Verify saved release/index evidence, ranking-relevant acquisition failures, review order and unresolved primary or horizon requirements.

### 170. Review method provenance

> Review [METHOD OR SCRIPT] for its actual mathematical assumptions, implementation provenance, dependencies and attributed sources. Distinguish original integration code from imported libraries and data-use rights.

### 171. Freeze calculation defaults

> Reconcile [CURRENT REQUEST AND CASE CONTEXT] with [RAW QUANT INPUTS], retaining each material value, unit, frequency, horizon, cost and constraint with its provenance. Preserve explicit inputs even when a file omits them, expose conflicts, then use the helper's operation contract to materialize optional defaults and identify missing required inputs. Record the prepared-input hash and runtime, compute and verify the frozen bundle, and check that the explanation agrees with resolved inputs and actual outputs without inventing data.


## Institutional research workflows and capability development

**Audience:** Expert to quant. Guides: [institutional manager](references/institutional-manager.md), [capabilities and limits](references/capabilities-and-limits.md).

### 172. Run a manager-style review

> Review [PORTFOLIO AND MANDATE] across data quality, theses, construction, risk, costs, accounting and operations. Prioritize unresolved decisions and distinguish analysis support from custody or audited fund administration.

### 173. Audit institutional readiness

> Assess this deployment against the skill's current capability inventory. Separate implemented/tested software, empirically validated investment effectiveness and available data or operational dependencies.

### 174. Plan a point-in-time research database

> Design a coverage-first historical-data plan for [STRATEGY AND HORIZON]. Identify which public records can be reconstructed, which observations must be archived prospectively and which gaps may require licensed data.

### 175. Design a sentiment validation study

> Plan an adjudicated test of issuer matching, timestamp handling, negation and material-event classification for [NEWS DATA]. Separate extraction accuracy from a later causal, after-cost return study.

### 176. Design an analyst-skill study

> Specify the recommendation ledger, price history, entry/exit rules, benchmark and bias controls needed to measure analyst performance independently. Audit available data before trusting provider rankings or constructing weights.

### 177. Review host operational evidence

> Review a host-provided offline failure drill for empty responses, disconnects, partial fills and restarts. Distinguish observed behavior from untested claims. Do not create local execution gates or claim this skill controls the host.

### 178. Maintain the documentation

> Review the latest implemented capabilities, update the README as a current usage guide and refresh the example-prompt catalog without a fixed count. Regenerate the examples and run the documentation release check before packaging.


## Traceable report facts

**Audience:** Investors, research authors and quantitative reviewers. Guides: [report facts](references/report-facts.md).

### 179. Report facts from a quant bundle

> Create a private JSON facts artifact and a readable Markdown report from [QUANT BUNDLE]. Retain source hashes and pointers, computation and nested result status, supported units and denominators, and explicit missing or unknown metadata. Distinguish modeled portfolio equity drawdown from return-series drawdown, and report rejected jobs without stale numeric results. Explain what requires a separate calculation or source check.

### 180. Explain a public VQM queue from retained facts

> Create a private report-facts table from [PUBLIC VQM BUNDLE] and render the supported facts in Markdown. Preserve the actual queue order, score ties, exact score strings, supported factor definitions, source pointers and coverage limitations. Distinguish research rank from investment eligibility and leave unsupported measurement metadata unknown.

### 181. Add declared labels to selected source fields

> Use [CUSTOM BINDINGS] to add selected exact source pointers from [BUNDLE] to a private report-facts artifact. Keep custom metric names, units, basis and horizon explicitly declared and unverified, preserve the built-in facts, and expose missing pointers. Render a readable report without treating custom labels as semantic proof or evaluating expressions.


## Bound inputs and computed reports

**Audience:** Research authors, traders and quantitative reviewers. Guides: [run and report](references/run-and-report.md).

### 182. Run and report explicit quant jobs

> Use [WORKBENCH REQUEST] to compute supported jobs and produce a private quant_report bundle, facts and Markdown report. Retain the original request, actual defaults and computation outcomes, then verify numerical replay and canonical report regeneration. Preserve nested infeasibility or ambiguous-cashflow outcomes without calling them successful investment conclusions.

### 183. Bind calculations to supplied source objects

> For the explicitly selected operations and fields in [REQUEST], bind each complete inputs object to its local file SHA-256 and JSON pointer, then run quant_report. Preserve explicit parameters and report source-selection conflicts. Do not treat a matching hash as proof that a model chose the right object.

### 184. Explain a partially computable campaign

> Run [QUANT REQUEST] with its missing required fields left missing. Report each computed and noncomputed job, resolved optional defaults and retained facts. Distinguish partial calculation coverage from missing source evidence; do not invent observations or silently switch algorithms.

### 185. Report separate analyst cohorts

> Use analyst_report on [STRUCTURED ANALYST RECORDS] and [LOCAL SOURCE ROOT]. Preserve distinct issuer, currency, price-basis and target-horizon cohorts, included and excluded records, provider pools and provider-reported track records. Render pointer-bound facts and state unresolved provider discrepancies without averaging incompatible pools.

### 186. Separate targets from fair value and price history

> Report [ANALYST REQUEST] with supplied fair-value estimates, historical price ranges and source-access records as typed supplemental evidence. Keep them outside forward-target calculations and retain missing fields and evidence limitations. Do not turn reported success rates into an unsupported analyst reputation weight.

### 187. Inspect exact handoff preservation

> Create a private advisory handoff_report from [SOURCE FILE], [SHA256] and [REQUEST POINTER]. Compare [PROPOSED PAYLOAD BINDING] and explain any differences in dollar versus share amounts, order type, time in force or routing. Preserve the selected original payload, omit private details from shared output, and add no execution gate or broker action.

### 188. Distinguish reproducibility from model adherence

> Compare [MODEL OUTPUTS] against their retained quant or analyst reports. Report helper invocation, artifact completeness, numerical replay, source-selection fidelity and narrative agreement separately. Preserve old results and explicitly list missing acquisitions and unsupported custom algorithms instead of declaring them fixed by a successful helper test.


## Request fidelity and accounting alignment

**Audience:** Investors, portfolio analysts and quantitative reviewers. Guides: [research alignment](references/research-alignment.md), [run and report](references/run-and-report.md), [portfolio decision calculations](references/portfolio-decision-calculations.md), [planning input roles](references/planning-input-roles.md), [portfolio projection](references/portfolio-projection.md), [planning comparison](references/planning-comparison.md), [flow normalization](references/flow-normalization.md).

### 189. Audit selected and ignored inputs

> Bind [REQUEST] to its allowed source files and JSON pointers. Distinguish actual account observations, the mandate, scenarios and sample policies; retain selected, unused and conflicting fields. Check record identity and metadata dates before calculating, and explain what the receipt cannot infer about my intent.

### 190. Audit source availability and acquisition coverage

> Inventory [SOURCE PACKET] against its allowlist and byte hashes. Keep missing bytes, unknown security types, confirmed exclusions, publication dates, retrieval dates and unavailable acquisition receipts distinct. Execute applicable retained-source and report checks; do not interpret absent failure records as a verified successful acquisition.

### 191. Preserve a flexible review date

> Review [HOLDING] until [COMPARISON DATE] as an intended horizon, not a forced sale. Use the horizon router, retain an existing entry date if supplied and report event coverage through its actual endpoint. Label any proposed planning deadlines without moving my review date to a prior trading session.

### 192. Audit the requested scoring method

> Compare the requested ranking profile and implementation with [OBSERVED RESEARCH]. Bind both profiles to retained bytes and show method or parameter mismatches. Run the requested supported scorer and preserve its queue; explain that method identity alone does not prove execution, undervaluation or a buy recommendation.

### 193. Size a purchase after explicit costs

> Use the trade-cost contract to calculate [ORDER] against [BUDGET] with the supplied quantity increment, slippage and fee units. Separate quoted notional from after-cost debit and both sides of a round trip. Treat the calculation as an estimate and add no execution permission requirement.

### 194. Find the cash trough at actual withdrawal times

> Use [DATED CASH EVENTS] to calculate the lowest modeled available balance and the largest gap to my planning floor. Preserve actual withdrawal demand times and trade settlement availability; keep future stock grants outside cash funding. Disclose missing confirmations and broker buying-power evidence.

### 195. Project interest with an intermediate withdrawal

> Project [CASH PLAN] using the supplied annual-effective rate and exact event dates. Remove withdrawals when they occur, disclose the day-count basis and reconcile opening cash, flows, interest and ending cash. Do not infer borrowing after an unfunded cash shortfall.

### 196. Reconcile gross vesting, taxes, shares and cash

> Reconcile [RSU GRANTS] into gross shares, shares withheld, shares sold for taxes and net shares. Show future assumed values separately from observed settled sale proceeds, without pooling different dates into current portfolio concentration or treating tax withholding as the final tax liability.

### 197. Reconcile portfolio denominators

> Look through [POSITIONS AND FUNDS], compare declared account equity with identified assets and explicit cash, and show unexplained differences. Label concentration against each denominator. Model supplied contribution-only changes at explicit unchanged marks without assuming that a no-sales example makes concentration permanent.

### 198. Separate session and lifetime performance

> Review [POSITIONS AND TRADES] for session P&L only where prior marks, flows, distributions, fees and session timing support it. Keep cost-basis unrealized P&L separate. Show gross and net trade statistics and decline unsupported attribution of losses to investment versus execution causes.

### 199. Reconcile owner cash without unsupported addbacks

> Build the explicit cash bridge for [FINANCIAL RECORDS]: reported CFO, all capex, maintenance-only cash, growth reinvestment, acquisitions, working capital and SBC treatment. Separate earnings adjustments from cash adjustments and retain missing cash timing or tax evidence as unresolved.

### 200. Distinguish acquisition cash from deal value

> Model [ACQUISITION SCENARIOS] with stated synergy ramps, delays, integration cash and financing tax treatment. Calculate share dilution and incremental cash by year. Compute total deal NPV only from a separately complete acquisition cash-flow contract; do not equate negative interim synergy cash with destruction of deal value.

### 201. Build terminal valuation and reinvestment sensitivities

> Run [VALUATION CONTRACT] with its explicit revenue, margin, shares, debt, exit multiples, capex and working-capital assumptions. Retain terminal share price, dividends, both-side costs, total return and present value as distinct fields. Calculate the declared sensitivities and expose missing interim cash flow or financing assumptions.

### 202. Reconcile splits, dividends and return windows

> Calculate price and non-reinvested total returns from [CORPORATE ACTIONS AND MARKS]. Preserve old/new share basis and dividend dates, and do not claim a requested terminal return when its final mark is missing. Keep provider EPS publication dates attached to their own security and period.

### 203. Test a causal dual moving-average strategy

> Run the explicit dual-SMA long/cash strategy on [COMPLETED DAILY BARS] with my fast/slow windows, next-open delay, costs, capital fraction and terminal policy. Retain every declared variant, pending unfilled orders, both-side fees and marked equity. Check that later data changes cannot change earlier signals or fills.

### 204. Preserve the opening-range baseline

> Run the supported opening-range breakout on [COMPLETED INTRADAY BARS], retaining its strategy identity, opening-bar count, cadence, volume rule, next-open timing, sizing, stops, target and buffered exit. Report the exact parameters and input hash without substituting a different range or enabling shorts.

### 205. Check whether a study contains forward observations

> Assess [PAPER STUDY] against its protocol window, freeze time, decision/outcome availability, data kind and implementation evidence. Keep synthetic, retrospective and inadmissible rows out of the declared forward count. Compare supplied code identities and change records without claiming that matching prose proves fill agreement.

### 206. Check risk and numerical explanations

> Compare [COVARIANCE MATRICES OR HEDGE SCENARIOS] using the supported arithmetic checks. Show individual variance multipliers, ratio changes, every option-expiry payoff and assumed residual hedge sensitivity. Use typed comparisons for numerical statements, retaining unknown units, exact inequality boundaries and declared floating-point tolerances.

### 207. Verify complete model-alignment evidence

> Evaluate [TWO FROZEN MODEL RUNS] on request fidelity, helper invocation, complete artifacts, numerical replay and the final explanation separately. Keep original failed runs, review every new response against the allowed evidence and report remaining gaps. Do not present matching calculations as a guarantee of identical future investment decisions.


## Source-bound calculations and evidence meaning

**Audience:** Investor to quant. Guides: [source bound workflow](references/source-bound-workflow.md), [evidence semantics](references/evidence-semantics.md), [ranking alignment](references/ranking-alignment.md).

### 208. Run research from original fields

> Analyze these supplied files through the source-bound workflow. Bind the calculation inputs to exact source fields, identify unused material inputs, and return the generated report with assumptions and unresolved questions.

### 209. Audit a report projection

> Verify whether this numeric report preserves every canonical fact from its source bundle, including rejections and unknowns. Show any altered, missing or added fields and preserve valid custom facts.

### 210. Reconcile price and earnings identity

> Before comparing these valuation multiples, check security identity, currency, fiscal period, accounting definition and split basis. Distinguish missing metadata from a demonstrated mismatch.

### 211. Handle imprecise catalysts

> The contract renewal is known only to a year and the earnings event only to a month. Compare those ranges with my intended hold without inventing event dates.

### 212. Separate facts from inferred states

> Review the quoted borrow fee, review flag, proposed gold labels and performance residual. Tell me which states are evidenced and which availability, selection, adjudication or causal claims remain unknown.

### 213. Replay the matching scorer

> Identify the scoring profile bound to this retained snapshot, replay only its compatible installed scorer, and distinguish the requested production route from a separately labeled historical diagnostic.

### 214. Compare decisions without false agreement

> Compare these two ranked research outputs on candidates, scores, horizon, preferences and reviewed decisions. Treat dimensions missing on both sides as unknown, not agreement.

### 215. Check numeric conclusions against artifacts

> Use result pointers to verify these stated conclusions against the actual calculation outputs. Preserve the units, denominators, horizons and nested evidence states in the final answer.

### 216. Review after the last cash event

> Reconcile the complete cash path through every deferred purchase and withdrawal. Show unknown intraday settlement ordering and signed shortfalls rather than stopping at an earlier favorable balance.

### 217. Respect an offline research scope

> Analyze only the attached frozen data, with no network acquisition. Run all supported calculations, retain missing source limitations, and separate that offline result from any proposed future data collection.


## Reproducible technical indicators and charts

**Audience:** Intermediate to quant. Guides: [technical toolkit](references/technical-toolkit.md), [analysis contracts](references/analysis-contracts.md).

### 218. Compute a declared indicator set

> Analyze [TICKER] for a [HOLDING PERIOD] using my dated OHLCV file. Compute EMA, RSI, MACD, Bollinger bands, ATR, ADX, stochastic, OBV and Ichimoku with explicit periods, seed conventions, warmup nulls and price-adjustment basis. Retain the frozen calculation and distinguish observations from trade hypotheses.

### 219. Compare session and anchored VWAP

> Using these intraday bars and explicit exchange-session labels, compare session VWAP with VWAP anchored at [TIMESTAMP]. Explain the volume/price basis and do not reconstruct intraday VWAP from daily bars.

### 220. Plot declared levels and candle patterns

> Render an SVG chart from my retained OHLCV bars with moving averages and Bollinger bands. Show the supplied Fibonacci swing and causal support/resistance, report candlestick rule definitions, and label bar-based volume profile as an approximation.

### 221. Replay an indicator hypothesis after costs

> Freeze this indicator hypothesis and parameters before evaluation. Replay close-time signals at subsequent bar opens using supplied costs, preserve missing/warmup periods, and compare with buy-and-hold. Do not choose parameters using the evaluation period.

### 222. Inspect supplied market depth

> Calculate spread and size imbalance from this timestamped depth snapshot. Keep the result separate from historical OHLCV indicators and explain why the snapshot cannot establish executable liquidity or a durable signal.


## Accounting quality and explicit valuation models

**Audience:** Intermediate to expert. Guides: [fundamental toolkit](references/fundamental-toolkit.md), [analysis contracts](references/analysis-contracts.md).

### 223. Compare accounting screen variants

> Using attached comparable annual financials, calculate Piotroski, Altman and Beneish where applicable. Freeze the exact model variants and asset denominators, cite each source fact, and retain missing values and invalid domains instead of filling them.

### 224. Reconcile operating forecasts and DCF

> Build a five-year annual forecast from my explicit operating and financing assumptions. Reconcile income, cash and balance sheets; calculate FCFF and FCFE valuations with the appropriate discount basis and an explicit equity bridge. Report omitted accounting items.

### 225. Solve price-implied cash growth

> Use reverse DCF to solve the constant cash-flow growth implied by [PRICE] under my supplied assumptions. Preserve the growth bracket, terminal cash convention, discount rate and share basis; report failure if the target is outside the bracket.

### 226. Compare three valuation approaches

> Apply dividend discount, residual income and sum-of-parts to these supplied inputs. Keep enterprise value, total equity and per-share value distinct, and show where the business model or evidence makes a method inapplicable.

### 227. Evaluate accounting ratios consistently

> Compute ROIC, PEG, liquidity, interest coverage, margins and DuPont ROE from these statements. State growth units, average-versus-ending balance choices and reasons for any unavailable result.

### 228. Simulate declared valuation assumptions

> Run a seeded Monte Carlo valuation using my explicit triangular discount-rate, terminal-growth and cash-flow-multiplier assumptions. Retain the distributions and seed; label the output as scenario quantiles rather than estimated probabilities.


## Evidence-bound sentiment scores and validation

**Audience:** Intermediate to quant. Guides: [sentiment toolkit](references/sentiment-toolkit.md), [analysis contracts](references/analysis-contracts.md).

### 229. Separate sentiment by company and aspect

> Analyze these retained articles by company and by revenue, earnings, balance sheet, guidance and governance. Bind each score to its exact text span and timestamp; keep ambiguous targets, missing aspects and contradictory evidence visible.

### 230. Measure dated sentiment changes

> Build a sentiment series at these declared cutoffs with explicit source weights, half-life and event deduplication. Use prior observations only for normalization, and keep unknown sentiment separate from neutral or balanced evidence.

### 231. Use an optional local financial classifier

> Check whether my locally supplied, version-pinned sentiment model and runtime are available and permitted for my stated use. Verify model-file hashes and label mapping, infer on bound spans without downloads, and report unavailable components without substituting another model.

### 232. Evaluate sentiment calibration and performance

> Evaluate supplied prediction probabilities against held-out labels, then replay a frozen long/cash sentiment rule over these subsequent return intervals with costs. Report calibration and incremental performance separately; do not infer profitability from classification accuracy.

### 233. Combine declared research signals

> Combine my normalized sentiment, technical and positioning observations using explicit fixed weights and information cutoffs. Report coverage and unavailable features; do not describe the composite as a trained or validated trading policy.


## Fundamental factors and statistical structure

**Audience:** Quant. Guides: [factor toolkit](references/factor-toolkit.md), [analysis contracts](references/analysis-contracts.md).

### 234. Normalize a dated sector cross-section

> Winsorize these point-in-time fundamental metrics within sectors at explicit quantiles and compute population z-scores. Preserve membership dates, missing data, small groups and constant features.

### 235. Attribute returns to Fama French factors

> Fit FF3 and FF5 to my aligned decimal returns and factor observations. Preserve geography and frequency, report per-period alpha, exposures and residual variation, and avoid claiming in-sample attribution is predictive alpha.

### 236. Measure generic style exposure risk

> Using supplied exposures, factor covariance and specific variances, decompose this portfolio variance and residualize scores against declared styles. Distinguish this generic implementation from proprietary Barra data and models.

### 237. Explore fundamental structure without leakage

> Fit PCA and seeded k-means on this training-only fundamental matrix and apply the saved transformation to held-out rows. Report scaling, convergence and stability limitations before treating clusters as economic peers.


## Explicit multi-asset valuation and settlement research

**Audience:** Quant. Guides: [derivatives toolkit](references/derivatives-toolkit.md), [multiasset platform](references/multiasset-platform.md).

### 238. Value a vanilla American option

> Price this supplied vanilla option with explicit exercise style, continuous dividend yield, risk-free rate and CRR steps. Compare increasingly fine grids, retain residual differences, and state unsupported discrete dividends or deliverables.

### 239. Recover model-implied volatility

> Given this observed option premium per underlying unit, solve implied volatility under the supplied model, bracket and price tolerance. Preserve nonconvergence or nonidentifiability; do not substitute a price model or infer realized volatility.

### 240. Separate FX forward from forecast

> Compute the covered-interest forward from these explicitly oriented currency rates and compounding assumptions. Show domestic-per-foreign units, forward points and omitted basis/costs; do not label it a spot forecast.

### 241. Reconcile bond value and accrued interest

> Value my supplied complete fixed noncallable bond cashflows using the explicit yield and ACT365F discount clock. Show dirty value, accrued interest and clean price; state when my actual market convention is unsupported.

### 242. Reconcile futures variation and costs

> Reconcile this linear futures settlement series using the exact multiplier, tick, contract count and currency rounding. Include negative prices and fees, and distinguish variation P&L from funded notional, margin and physical delivery.


## Multi-asset paper accounting and platform evidence

**Audience:** Quant. Guides: [paper exchange](references/paper-exchange.md), [platform readiness](references/platform-readiness.md), [multiasset platform](references/multiasset-platform.md).

### 243. Replay hypothetical multi-asset events

> Replay this paper-only event packet containing equities, bonds, spot crypto, futures and funded FX. Reconcile cash, receivables, positions, fees and currency translation. Do not infer fills from price touches or present the scenario as a broker execution.

### 244. Test cancellation and restart scenarios

> Use these fictional order/fill/cancellation events to test partial fills, cancellation races, duplicate delivery and deterministic full-journal restart. Preserve failures and explain which native-host recovery behaviors remain untested.

### 245. Model explicit option exercise

> Replay my long vanilla option exercise/expiry scenario with exact strike, multiplier, exercise style and deliverable. Reconcile strike cash and underlying shares; do not infer automatic exercise or short assignment.

### 246. Audit production scope by asset class

> Assess the supplied evidence catalog for stocks/ETFs, options, futures, FX, bonds and crypto on my existing native host. Separate research, paper and live coverage. Retain missing and conflicting evidence and never equate mathematical support with broker support.

### 247. Check actual native host support

> Inspect only available read-only native-host capabilities for my requested asset/order/session. Distinguish observed schemas from dated product documentation. Report unsupported or unverified scope without inventing another broker or placing trades.


## Explicit time-series scenarios and diagnostics

**Audience:** Quant. Guides: [time series toolkit](references/time-series-toolkit.md).

### 248. Simulate a declared GBM scenario

> Simulate these supplied GBM assumptions with explicit price basis, measure, drift, volatility, horizon, grid and seed. Distinguish real-world assumptions from risk-neutral pricing, preserve model units and show analytic versus sampled moments. Do not infer a calibrated forecast.

### 249. Measure causal trend derivatives

> Calculate backward price velocity and acceleration on these irregular timestamps with explicit time and value units. Preserve warmup, availability and price-adjustment conventions; do not use future observations or describe finite differences as exact instantaneous derivatives.

### 250. Normalize a fixed pair without leakage

> Fit the supplied fixed-pair OLS relationship using only the frozen training window, then normalize the holdout spread using training residual dispersion. Retain conditioning failures and distinguish spread z-scores from cointegration, arbitrage or executable short trades.

## Keeping this catalog current

Examples are reviewed against the current capabilities and regenerated for
every package update. There is no fixed count: add distinct useful workflows,
revise changed behavior and remove claims the skill cannot support. See the
[maintenance procedure](references/maintaining-the-skill.md).
