# Long-term portfolio management

## Investment policy and ownership

Record objective, horizon, liquidity needs, contributions/withdrawals, benchmark,
tax location, excluded instruments and loss tolerance. Core/swing/intraday weights
refer to total account equity. They are maximum deployment budgets, not a command
to stay fully invested. Never replenish a losing tactical sleeve automatically.

The example 80/10/5 plus 5% cash is an implementation illustration. Obtain actual
targets and funding before live use. Maintain a separate ownership map for each
position/lot and strategy; map manual positions explicitly. The risk helper rejects
new symbol overlap across sleeves and never permits an intraday sell to consume
core shares.

## Allocation and rebalance

Use a diversified policy benchmark appropriate to the user's objectives. Define
target weights, drift bands, minimum trade size, turnover budget and review cadence.
Use new contributions and dividends to repair underweights first. Review sells
separately; unfilled sales are never spendable funding for a new buy.

`portfolio_manager.rebalance` returns cash-funded buy candidates and separate trim
reviews, prioritizing largest dollar underweights with deterministic tie-breaking.
It rounds down to whole shares, preserves the cash floor and caps turnover. Its
prices are planning inputs, not live executable quotes. Add fees, fetch fresh broker
state, and run each final order through the execution gate. The executable core gate
also enforces approved per-symbol targets and the core sleeve cap.

Core holding decisions use thesis durability, valuation ranges, cash generation,
balance sheet, material guidance changes and portfolio fit. Record a bear case,
thesis-invalidating facts, expected horizon and next review trigger. Do not create
intraday stops for long-term holdings merely because a tactical model uses them.

## Concentration and scenario review

Aggregate sector/theme, country, currency, factor and underlying issuer exposure.
Review ETF constituents and overlapping funds. The local sector cap is only as good
as the supplied classification. Personal readiness additionally computes constituent look-through; ETF fund labels are not treated as corporate sectors.

Where sufficient aligned point-in-time return data exist, review covariance,
correlation clusters and component risk contributions. Distinguish estimation
uncertainty from precision. Do not add an optimizer that maximizes noisy historical
returns and call that a better portfolio. Compare a simple allocation baseline.

Review plausible equity selloffs, sector shocks, rate moves and correlation spikes,
including a gap through tactical stops. Estimated stop loss is not worst-case loss.
Flag correlated positions even when individual symbol limits pass. These broader
analytics are implemented in portfolio_analytics.py and rerun from policy-required retained inputs in personal_readiness.py. The host still verifies source quality and external exposures.

## Taxes and lot-aware selling

Fetch broker tax lots before proposing a taxable sale. Consider holding period,
embedded gain, loss carryovers supplied by the user, and user-approved tax budgets.
Do not assume a tax-lot selection tool exists or silently switch the broker method.

Check possible wash-sale interactions across core/tactical sleeves, dividend
reinvestment, and other known household/retirement accounts. Missing external
transactions mean incomplete coverage, not clearance. accounting_tools.py flags potential matches and proposes lots; it does not certify final tax treatment or determine whether instruments are substantially identical.
Escalate ambiguous tax treatment for human review rather than claiming a deduction.
The IRS describes the relevant window and replacement-acquisition cases in
[Publication 550](https://www.irs.gov/publications/p550).

## Attribution and review

Separate market gains from external cash flows, realized from unrealized P&L, and
investment selection from execution cost. Track net return, drawdown, exposure,
turnover, fees and slippage by sleeve and setup. Compare core to its policy benchmark;
compare tactical results to cash and comparable-exposure alternatives.

`portfolio_manager.performance` chain-links returns with an explicit end-of-period
cash-flow convention. Exact time-weighted return for intraday flows requires a
valuation at each flow; accounting_tools.time_weighted_return implements that flow-timed calculation. Neither helper computes money-weighted IRR, taxes or dividends
missing from input values. Never count a deposit as trading profit.
