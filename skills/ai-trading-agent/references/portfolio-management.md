# Long-term portfolio management

## Investment objectives and ownership

Record objective, horizon, liquidity needs, contributions/withdrawals, benchmark,
tax location, excluded instruments and loss tolerance. Record the denominator and
whether core/swing/intraday weights are targets, observations or maximum deployment
budgets; these meanings are not interchangeable. Do not infer an instruction to
stay fully invested or replenish a losing tactical sleeve from an example weight.
Use [planning input roles](planning-input-roles.md) when state or scope is ambiguous.

Sample sleeve weights are illustrative analytical inputs. Use the user's actual
objectives, holdings and contribution instructions. Position/lot ownership helps
avoid mistaken exposure attribution; it is not a skill execution permission map.
All allocation and risk findings are advisory.

## Allocation and rebalance

Use a diversified policy benchmark appropriate to the user's objectives. Define
target weights, drift bands, minimum trade size, turnover budget and review cadence.
Use new contributions and dividends to repair underweights first. Review sells
separately; unfilled sales are never spendable funding for a new buy.

`portfolio_manager.rebalance` returns cash-funded buy candidates and separate trim
reviews, prioritizing largest dollar underweights with deterministic tie-breaking.
It rounds down to fractional quantities by default, with configurable whole-share
mode, preserves the cash floor and caps turnover including fee reserves. Its
prices are planning inputs. Read [fractional-shares.md](fractional-shares.md) for
fractional planning and per-occurrence contributions. The planner's target, cash
and turnover constraints apply only to its calculation. They do not impose an
execution gate; use [execution-handoff.md](execution-handoff.md) for actual requests.

Core holding decisions use thesis durability, valuation ranges, cash generation,
balance sheet, material guidance changes and portfolio fit. Record a bear case,
thesis-invalidating facts, expected horizon and next review trigger. Do not create
intraday stops for long-term holdings merely because a tactical model uses them.

## Concentration and scenario review

Aggregate sector/theme, country, currency, factor and underlying issuer exposure.
Review ETF constituents and overlapping funds. Classification quality matters; ETF fund labels are not corporate sectors. Use
constituent look-through and disclose uncovered exposures.

Where sufficient aligned point-in-time return data exist, review covariance,
correlation clusters and component risk contributions. Distinguish estimation
uncertainty from precision. Do not add an optimizer that maximizes noisy historical
returns and call that a better portfolio. Compare a simple allocation baseline.

Review plausible equity selloffs, sector shocks, rate moves and correlation spikes,
including a gap through tactical stops. Estimated stop loss is not worst-case loss.
Explain correlated positions even when each weight appears modest.
portfolio_analytics.py supplies optional covariance, look-through and stress
calculations; report source quality and unknown external exposures.

For future vests or withdrawals, use [dated portfolio projections](portfolio-projection.md).
Carry each supplied intervening cash flow into the target-date ledger or explicitly
show its exclusion. Current exposure and future exposure need separately labeled
denominators; a withdrawal can increase a remaining stock's weight even after a
small sale. Keep unknown residual assets distinct from identified holdings and cash.

## Taxes and lot-aware selling

Use supplied tax lots, or available broker lots when the task authorizes access,
for a taxable-sale comparison. Missing lots allow a conditional comparison with
unknown tax results; they do not create a new execution gate. Consider holding period,
embedded gain, loss carryovers supplied by the user, and user-approved tax budgets.
Do not assume a tax-lot selection tool exists or silently switch the broker method.

Check possible wash-sale interactions across core/tactical sleeves, dividend
reinvestment, and other known household/retirement accounts. Missing external
transactions mean incomplete coverage, not clearance. accounting_tools.py flags potential matches and proposes lots; it does not certify final tax treatment or determine whether instruments are substantially identical.
Escalate ambiguous tax treatment for human review rather than claiming a deduction.
The IRS describes the relevant window and replacement-acquisition cases in
[Publication 550](https://www.irs.gov/publications/p550).

Use `planning.tax_sensitivity` for explicit supplied-rate calculations. State how
selling costs affect the gain base; do not choose a tax rule silently. A tax reserve
reduces uncommitted cash but remains an asset, while a payment reduces cash and
assets. Reconcile liability balances separately to avoid subtracting one obligation
twice. A modeled loss does not create immediately spendable tax savings.

When tax cost, concentration, allocation drift and liquidity favor different sales,
do not invent a user preference to claim a unique best trade. Present comparable
alternatives using `planning.alternative_comparison`, retain unresolved criteria,
and explain which stated priority would favor each. Apply supplied priorities in
a separate explicit analysis; this helper does not optimize preferences. A proposed
cash-raising path must improve the cash deficit: reducing a sale while keeping an
unfunded purchase cannot cure that deficit.

Use `planning.settlement_transfer_paths` for supplied date-only calendars and lags.
A same-day settlement-to-transfer path needs an explicit ordering assumption;
otherwise show it as possible with unknown acceptance and compare an earlier-sale
path. A transfer initiated on the spending deadline is not automatically received
that day. Example rebalance flags or draft settings do not create new approval
requirements for a requested analytical proposal.

## Attribution and review

Separate market gains from external cash flows, realized from unrealized P&L, and
investment selection from execution cost. Track net return, drawdown, exposure,
turnover, fees and slippage by sleeve and setup. Compare core to its policy benchmark;
compare tactical results to cash and comparable-exposure alternatives.

Perform that separation only to the extent supported by actual records. Disclosed
fees can be added back to net endpoint returns once, but the remaining result
still includes any unseparated slippage, timing and market effects. Call it a
before-disclosed-fee accounting result, not established investment-selection loss.
Brinson `selection` is a mathematical component, not causal proof. Unknown sleeve
periods, currencies or benchmark definitions prevent an unconditional combined
portfolio attribution; show any explicit common-basis assumption separately.

`portfolio_manager.performance` chain-links returns with an explicit end-of-period
cash-flow convention. Exact time-weighted return for intraday flows requires a
valuation at each flow; accounting_tools.time_weighted_return implements that flow-timed calculation. Neither helper computes money-weighted IRR, taxes or dividends
missing from input values. Never count a deposit as trading profit.
