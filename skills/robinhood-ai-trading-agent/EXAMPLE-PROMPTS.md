# 50 example prompts: beginner to advanced

These examples match skill version **3.3.0**. Documentation updated October 8, 2026.

Start any prompt with: **Use the robinhood-ai-trading-agent skill.** Replace the
bracketed placeholders with your own inputs. The examples are requests you can
choose and adapt, not additional skill rules or trading authorization. Research
and paper workflows do not require live trading; live-execution examples depend
on verified broker capabilities and applicable authorization.

The current execution helpers support long-only, whole-share US stocks and
nonleveraged ETFs using regular-session DAY limit orders. Options, shorting,
fractional orders, and extended-hours trading require additional validated
adapters. An active chat does not provide guaranteed execution latency or
monitoring after it closes. See the [skill](SKILL.md) and
[personal setup guide](references/personal-setup.md) for operating requirements.

- [1–10: Getting started](#getting-started)
- [11–20: Stock research](#stock-research)
- [21–30: Portfolio management](#portfolio-management)
- [31–40: Swing and day trading](#swing-and-day-trading)
- [41–50: Quantitative analysis and execution controls](#quantitative-analysis-and-execution-controls)

## Getting started

### 1. Teach me the basics

> I’m new to investing. Explain how this skill approaches long-term investing, swing trading, and day trading. Walk me through a fictional example of each and explain the risks in plain English.

### 2. Check my installation

> Verify the installed skill version, supporting files, Python dependencies, and available helpers. Run the appropriate installation diagnostics and explain anything missing. Do not connect a brokerage account.

### 3. Create my paper workspace

> Initialize a new paper-trading workspace at [DIRECTORY]. Keep its policy, research, and trading records separate from the installed skill. Show me how to check its health and resume it later.

### 4. Understand my investor profile

> Interview me about my goals, time horizon, cash needs, experience, and tolerance for losses. Turn my answers into a draft investor policy and identify any conflicting objectives.

### 5. Research a $500 starting portfolio

> I have $500 and a five-year horizon. Research durable businesses with undervaluation and growth potential. Compare individual stocks with a diversified ETF alternative, account for whole-share constraints, and explain when retaining cash makes sense.

### 6. Read a company’s financial statements

> Use [COMPANY] to teach me how revenue, earnings, operating cash flow, free cash flow, debt, and share dilution connect. Use dated filings and explain why reported profit can differ from cash generation.

### 7. Compare a stock with an ETF

> Compare buying [STOCK] with buying [ETF] for a long-term portfolio. Evaluate the company’s business and valuation, and the fund’s holdings, fees, tracking, concentration, and liquidity using appropriate criteria for each.

### 8. Review my existing holdings

> Review this portfolio: [HOLDINGS, QUANTITIES, AND CASH]. Explain concentration, overlapping exposures, liquidity needs, and obvious information gaps. Give me a prioritized research checklist before suggesting changes.

### 9. Build my first watchlist

> Create a research watchlist around [INDUSTRIES OR THEMES]. For each company, record the investment hypothesis, valuation questions, evidence still needed, possible catalysts, and what would invalidate the thesis.

### 10. Run a complete fictional exercise

> Run the bundled learning examples and walk me through the results. Explain which numbers are fictional, which controls were actually exercised, and why passing software tests does not demonstrate a profitable strategy.

## Stock research

### 11. Configure my research universe

> Use the current S&P 500 as my starting research universe, excluding [EXCLUSIONS]. Record the constituent source and snapshot date. Keep this research universe separate from anything authorized for execution.

### 12. Find undervalued, durable businesses

> Research up to 10 genuinely undervalued S&P 500 companies suitable for a three-to-five-year investor with moderate risk tolerance. Apply the full research pipeline. Return fewer if necessary, and separate Eligible candidates from Watch and Speculative names.

### 13. Make valuation comparisons fair

> Compare [TICKERS] against suitable industry peers using consistent dates and metric definitions. Explain why each valuation measure is appropriate, and flag comparisons distorted by different business models or accounting.

### 14. Normalize earnings and cash flow

> Build a reported-to-normalized earnings and free-cash-flow bridge for [COMPANY]. Examine restructuring, acquisitions, stock compensation, working capital, capital expenditure, and claimed synergies. Separate documented adjustments from assumptions.

### 15. Investigate a possible value trap

> [COMPANY] looks cheap. Investigate whether its discount reflects opportunity or deterioration. Examine debt maturities, cash conversion, dilution, competitive position, capital allocation, and the durability of earnings.

### 16. Build a valuation range

> Develop bear, base, and bull valuation scenarios for [COMPANY]. Make growth, margins, reinvestment, and valuation assumptions explicit. Show which assumptions matter most and what evidence would change the conclusion.

### 17. Evaluate analyst evidence critically

> Review analyst evidence for [COMPANY]: consensus, target median, dispersion, estimate revisions, coverage count, and freshness. Distinguish independent business evidence from analyst opinion, and do not treat target upside as intrinsic value.

### 18. Apply consistent event checks

> Review [WATCHLIST] for upcoming earnings, dividends, regulatory decisions, and other material events. Distinguish entry-only blackouts from a prohibition on holding through events. Verify release versus call dates and uncertain windows. For long holds, specify near-term coverage and rolling reviews without claiming that distant events are known.

### 19. Research social and ownership signals

> Investigate the bullish and bearish arguments about [COMPANY] on Reddit and publicly accessible X posts. Verify material claims against primary sources. If insider or politician activity is cited, distinguish transaction types, disclosure delays, and economic significance.

### 20. Reconcile two conflicting stock screens

> Compare these two screens: [RESULT A] and [RESULT B]. Reconcile skill version, model/settings, tools/data access, prior context, universe, cutoff, holding period, price adjustments, latest primary financial periods, peer/metric definitions, coverage, event policy, and ranking rules. Separate factual errors from judgment differences; do not infer model quality from one pair of lists.

## Portfolio management

### 21. Design portfolio sleeves

> Draft a portfolio policy for [CAPITAL] with a long-term core, a smaller swing-trading sleeve, an intraday sleeve, and a cash reserve. Propose allocations and risk limits based on my objectives; leave them as a draft for review.

### 22. Rebalance using new contributions

> Given [HOLDINGS], [TARGET WEIGHTS], and a new contribution of [AMOUNT], propose a cash-first rebalance. Use drift bands to avoid unnecessary turnover and explain which imbalances still require attention.

### 23. Plan a withdrawal

> I need [AMOUNT] on [DATE]. Review my portfolio and propose how to raise the cash while considering settlement, liquidity, concentration, tax lots, and the effect on my long-term allocation. Do not submit orders.

### 24. Prevent conflicts between strategies

> Audit ownership across my core, swing, and intraday sleeves, including open orders and reserved quantities. Flag overlapping symbols or unclear ownership. Ensure a tactical exit cannot accidentally sell my long-term holdings.

### 25. Look through my ETFs

> Analyze underlying exposure across [STOCKS AND ETFS]. Aggregate company, sector, and theme concentration, including overlapping funds and multiple share classes. Identify anything that prevents a complete diversification assessment.

### 26. Stress-test the portfolio

> Stress-test [PORTFOLIO] against a broad market decline, a sector shock, and company-specific gaps. Use aligned historical returns for covariance where available, state scenario assumptions, and identify the largest contributors to loss.

### 27. Measure actual investment performance

> Calculate performance from [VALUATIONS, DEPOSITS, WITHDRAWALS, AND TRADES]. Separate investment gains from external cash flows. Compare each sleeve with an appropriate benchmark at comparable exposure and net of recorded costs.

### 28. Review tax-aware sale alternatives

> Using my supplied cost-basis records, compare lot-selection proposals for selling [POSITION]. Estimate realized gains or losses and flag possible wash-sale issues, including missing outside-account information. Present alternatives without placing trades.

### 29. Run a monthly portfolio review

> Review the last month’s allocation drift, thesis changes, turnover, costs, benchmark performance, and risk-limit usage. Recommend what to investigate, hold, rebalance, or stop doing. Present policy changes for review rather than applying them.

### 30. Challenge my investment thesis

> Act as a skeptical reviewer of my thesis for [COMPANY]. Construct the strongest evidence-based bear case, identify unsupported assumptions, compare credible alternatives, and explain what would justify buying, waiting, or taking no action.

## Swing and day trading

### 31. Prepare a day-trading morning brief

> Prepare today’s intraday brief for [WATCHLIST]. Check the trading calendar, session hours, catalysts, scheduled events, liquidity, spreads, and available data freshness. Identify which names deserve attention and which should be excluded.

### 32. Build a separate intraday universe

> Build an intraday watchlist using [LIQUIDITY, PRICE, AND SPREAD CRITERIA]. Keep it separate from my core holdings. Do not use undervaluation or S&P 500 membership as an entry signal, and disclose any missing real-time data.

### 33. Evaluate an opening-range breakout

> Evaluate the bundled opening-range-breakout setup for [SYMBOL] using completed intraday bars. Show the configured opening range, trigger, invalidation, stop, target, and time exit. Label the result as research or paper unless its strategy version is live-promoted.

### 34. Avoid entering before confirmation

> Review this possible breakout: [DATA OR CHART CONTEXT]. Determine whether the setup is confirmed by completed bars or depends on an unfinished candle. Show which entry conditions remain unmet and when the correct decision is to wait.

### 35. Calculate realistic trade economics

> For this proposed paper trade—[ENTRY, STOP, TARGET, AND CAPITAL]—calculate whole-share size, estimated loss, net reward-to-risk after costs, and remaining sleeve capacity. Include spread, slippage assumptions, pending exposure, and the possibility of sizing to zero.

### 36. Research a swing-trading setup

> Find suitable candidates in [UNIVERSE] for a [HOLDING PERIOD] hold and exit. Support my actual interval, whether a same-session day trade, 90 calendar days, 18 months, or 10 years or longer. Resolve the entry/exit clock and route to the appropriate strategy. Review relevant fundamentals or completed-bar signals, event exposure, horizon-specific outcomes, costs, portfolio fit, and exit coverage. Return fewer candidates if the evidence is incomplete; do not place orders.

### 37. Handle a losing trading session

> Review today’s trades, marked positions, and pending orders against my approved loss and exposure limits. Determine whether new entries must stop. Explain which authorized risk reductions remain possible and preserve existing protective coverage.

### 38. Run a supervised paper session

> Run a paper intraday session for [WATCHLIST] while this chat remains active. Use registered setup rules, completed bars, realistic fill assumptions, a trade journal, and explicit session-health checks. Stop when required data or supervision is unavailable.

### 39. Perform the closing reconciliation

> Run an end-of-day reconciliation. Identify unresolved orders, partial fills, residual intraday positions, reserved quantities, and protective coverage. Produce a handoff for anything unresolved without reclassifying a losing day trade as a long-term investment.

### 40. Debrief my trading behavior

> Review my last [NUMBER] trades by setup and sleeve. Analyze expectancy, win rate, average win and loss, drawdown, costs, slippage, and rule deviations. Separate evidence of poor execution from evidence that the strategy itself may lack an edge.

## Quantitative analysis and execution controls

### 41. Run an evidenced GARCH analysis

> Run the bundled GARCH(1,1) helper on audited historical prices for [SYMBOL]. Obtain enough history for the default training and holdout requirements. Report data counts, convergence, holdout QLIKE versus baseline, forecast horizon, and actual sizing eligibility.

### 42. Compare volatility models

> Compare GARCH, GJR-GARCH, and eligible one-period EGARCH forecasts on the same audited series. Use consistent holdouts and report all variants tried. Recommend a sizing input only if validation supports it; keep volatility separate from expected returns.

### 43. Audit market data before modeling

> Audit [PRICE FILE] for timestamp order, duplicates, missing sessions, timezone errors, price basis, splits, dividends, and large jumps. Investigate discontinuities rather than deleting genuine event moves, and bind the audit to the exact input file.

### 44. Backtest without hidden optimism

> Replay the opening-range-breakout baseline on [INTRADAY DATA] using chronological evaluation, completed-bar decisions, and realistic costs and fill assumptions. Explain any ambiguous stop/target ordering and identify information that the historical bars cannot establish.

### 45. Evaluate strategy promotion

> Assess whether strategy version [VERSION] deserves promotion using its development, validation, untouched test, and forward-paper results. Review all variants tried, benchmarks, costs, drawdowns, and operational deviations. Apply my approved criteria without promoting it automatically.

### 46. Audit live readiness

> Using an already authorized broker connection, perform a read-only live-readiness assessment. Verify account eligibility, actual tool schemas, restrictions, settled cash, configurable intraday cash reserves in dollars and/or equity percentage, order support, native protection, partial-fill handling, and time-exit coverage. List concrete blockers without changing broker settings.

### 47. Prepare and execute one approved order

> Prepare an approval-mode order proposal for [SYMBOL, SIDE, QUANTITY, LIMIT PRICE, AND SLEEVE]. Present the exact order and complete the required risk checks. Submit only after my explicit approval, refresh the necessary inputs before submission, and reconcile any uncertain outcome before considering another request.

### 48. Operate under a bounded mandate

> During this supervised session, operate within my existing approved mandate [MANDATE REFERENCE]. Verify its scope, expiry, strategy versions, capital limits, and broker capabilities. Execute only qualifying authorized orders; return exceptions for review and stop new entries if supervision or required evidence fails.

### 49. Recover from an interrupted execution

> The previous session ended after an order submission with an uncertain result. Reconcile the durable ledger against broker orders, fills, positions, and protection before taking further action. Prevent duplicate submissions and require explicit restart if the session lease expired.

### 50. Stop automation and hand off safely

> Activate the local kill switch to block new automated exposure. Reconcile open orders and positions, identify any unprotected or unresolved risk, and prepare a clear human handoff. Do not assume revoking authorization cancels broker orders or removes the need to manage existing positions.
