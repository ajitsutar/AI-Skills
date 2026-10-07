# Data acquisition and quantitative research

Broker tools supply current quotes, tradability, account state and official order
evidence. Public feeds supply research context; paid data are configurable.
Discover actual schemas for quote/history/financials/SEC/scanner/earnings/analyst
tools. Robinhood's [tool guide](https://robinhood.com/us/en/support/articles/trading-with-your-agent/)
is a discovery aid, not a schema contract. Observe tool batch limits and coverage.

## Acquire and retain

`research_data.py sec-facts <CIK> <output.json>` downloads official SEC companyfacts.
Set SEC_USER_AGENT to your application's contact identity in the environment; do
not invent it or put it in shared reports. The source URL, retrieval time and hash
are retained. See [SEC APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces).
point_in_time_fact requires an exact period/unit and filings available by as_of.
Filing dates alone cannot resolve same-day intraday availability: use an observed
filing publication time or an earlier cutoff. Do not sum quarterly and YTD facts.

```text
python scripts/research_data.py history SPY --start 2023-01-01 --end 2025-01-01 --output-dir <research-folder>
python scripts/research_data.py provider <provider-config.json> <symbol> <output.json>
```

The first example demonstrates data retrieval, not an investment recommendation.
Public history uses yfinance Adj Close with auto_adjust/back_adjust/repair disabled,
preserves invalid rows for rejection, and compares dates with exchange sessions.
End dates are exclusive. The source file reports missing sessions and unreviewed
corporate actions; it is **not automatically a valid price audit**. Verify splits,
spinoffs, mergers and distributions against reliable evidence. Complete the
price-audit manifest tied to the exact CSV before sizing with GARCH. Preserve real
crashes/event returns. No missing-data deletion or synthetic smoothing to improve fit.

Provider configuration supports an HTTPS JSON endpoint and header values from
environment variables. The generic adapter retains raw data; users must map its
actual schema, units, adjustment basis and timestamps. No guessed paid-provider
API, automatic subscription, credential copying or price-to-broker substitution.
Read-only GETs have bounded retries; broker writes never use generic retry logic.

## Universe and comparable numbers

Freeze the requested constituent/security list with source, date and stable issuer
identifiers. Use an accessible licensed index list, actual broker scanner or an
explicit uploaded list. Do not infer complete S&P 500 coverage from a partial
scanner response or hardcode 500/503 securities. Record exclusions and failures in
screen_review's coverage manifest. There is no minimum or maximum shortlist count.

research_analytics.py accepts `{operation, inputs}` JSON. Operations:

- peers: explicit industry/business-model peer_group; positive same-basis,
  same-period metrics; one representative per issuer. Missing/negative multiples
  are not cheap. Review fiscal/TTM dates inside a label and justify peer selection.
- normalization: signed after-tax earnings bridge with tax rate, realization,
  period, rationale and evidence. Uncertain synergies remain scenario assumptions.
- fcf: CFO less positive capex outflow, explicit cash adjustments and separate SBC
  owner-earnings sensitivity. Model recurring reinvestment, dilution and working
  capital; a noncash addback does not make economic cost disappear.
- valuation: growth, dilution, exit multiple and discount scenarios for positive
  equity earnings. It does not apply enterprise debt twice or assume dividends.
- analysts: latest target per firm, common currency/horizon, stale/future exclusion,
  median/range/IQR and matched target revisions. Targets are opinions, not fair value.
- revisions: matched contributor EPS/revenue estimates for the exact fiscal period
  and unit. Negative/zero baselines use absolute change, not misleading percentages.

No formula replaces balance-sheet/filing review. Banks, insurers, REITs and cyclical
businesses need their appropriate metrics. Explain debt maturities, liquidity,
credit quality, mid-cycle margins, recurring costs, cash conversion and credible
catalysts. Analyst coverage may be sparse; report absence without inventing consensus.

## Portfolio and accounting

portfolio_analytics supports lookthrough, covariance and stress operations on JSON.
Look-through expands fund holdings and keeps unexplained residuals UNKNOWN; never
assume unreported holdings are cash. Personal entries require complete fund/sector
coverage. Sources must be recent under policy. Underlying security/issuer mapping,
fund cash and cross-class concentration also need the host's reviewed evidence.

Covariance requires exactly aligned daily simple total returns for the projected
holdings, including pending buys, with at least 60 observations. It uses explicit
diagonal shrinkage and reports component risk/constant-series flags. Historical
correlation may fail in a crisis; stress scenarios ignore promised stop fills.
This is risk analysis, not an automatic return/covariance optimizer.

accounting_tools supports cash, returns, lots and wash-sale review (see its CLI
operation mapping and function signatures). Reconcile broker cash and corporate
actions; settled cash remains broker truth. Flow-timed returns need valuations
immediately before/after external flows. Sampled drawdown is not a full intraday
peak-to-trough record. Dividends are investment return, not external contributions.

FIFO/HIFO/specific lot outputs are proposals. Verify the actual broker's lot method,
identifiers, remaining quantities and acceptance before claiming tax-lot execution.
Wash-sale flags consider known purchases/reinvestment, declared identity groups and
the future window; they never certify tax clearance across unknown external/IRA
accounts. Emergency risk reduction may take precedence under an approved mandate,
with the unresolved tax implications reported. See [IRS Publication 550](https://www.irs.gov/publications/p550).

Every evidence JSON is a declaration the host must substantiate with retained
sources. Hashes detect changed files; they do not authenticate providers or humans.
