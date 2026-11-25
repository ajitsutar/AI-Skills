# Long-term portfolio management

For fund comparisons with role/horizon or existing portfolio context, use
`planning.fund_comparison_report` and the [native bound report contract](fund-comparison-report.md).
Bind original prose spans or structured source fields, retain current holdings,
and preserve its generated comparison, JSON and summary. Honor any required
response envelope while retaining the exact native artifacts separately. Partial mapping
limits completeness claims; it does not permit omitting supplied context.


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

For this planner, `equity` is total account equity **including** the supplied cash;
adding `cash` to `equity` double-counts that cash. Target weights, cash-floor,
drift-band and turnover fractions use total equity. Use the returned
`account_basis` and derived `account_basis_summary` to preserve those denominators
and amounts when explaining the result. The reconciliation residual is equity
minus supplied cash and priced supplied holdings: unrepresented value is not
automatically cash or an identified position. The existing small reconciliation
tolerance can leave a negative residual; reporting retains it explicitly.

Distinguish policy target notionals from proposed purchases, fee/debit reservations
and remaining cash. Equity outside a partial target map is not necessarily cash,
and unused planning budget is not the cash balance. The helper has no currency
input: label amounts as account currency units, currency unspecified. Legacy
`dollar_budget` names do not establish USD. A currency declaration from another
operation does not fill this gap. The native summary is derived from this result;
it does not verify arbitrary authored prose. Field semantics are available under
`portfolio_manager.rebalance` in `profiles/report-facts-v2.json`; this standalone
producer is not thereby registered as a quant-workbench/compositor operation.

Core holding decisions use thesis durability, valuation ranges, cash generation,
balance sheet, material guidance changes and portfolio fit. Record a bear case,
thesis-invalidating facts, expected horizon and next review trigger. Do not create
intraday stops for long-term holdings merely because a tactical model uses them.

## Concentration and scenario review

Aggregate sector/theme, country, currency, factor and underlying issuer exposure.
Review ETF constituents and overlapping funds. Classification quality matters; ETF fund labels are not corporate sectors. Use
constituent look-through and disclose uncovered exposures.
When comparing a fund's composition with current holdings or an unheld alternative,
use the complete-source adapter's [fund composition denominators](source-exposure.md#fund-composition-denominators).
Its structured evidence and readable projection distinguish total-fund weights from
shares of the supplied immediate holdings slice. Preserve the basis labels, dated
coverage and unknowns; a slice percentage does not add an account position or prove
complete terminal-issuer coverage.

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

For supplied tax-aware sale comparisons, use the [source-bound tax-lot report](tax-lot-report.md)
to deliver holding-period components and proposal-specific retained quantities
alongside native selection and purchase-date flags. Preserve source currency scope
and exact quantities; generated projections do not certify legal tax treatment.

Use supplied tax lots, or available broker lots when the task authorizes access,
for a taxable-sale comparison. Missing lots allow a conditional comparison with
unknown tax results; they do not create a new execution gate. Consider holding period,
embedded gain, loss carryovers supplied by the user, and user-approved tax budgets.
Do not assume a tax-lot selection tool exists or silently switch the broker method.

Bind currency labels for sale price, lot basis, proceeds and gains to their source
fields or an explicit shared currency scope that applies to those records. Currency
in a separate cash ledger, a market convention or a ticker does not establish the
sale or lot currency. Keep the cash ledger's supplied currency within its own scope.
If currency is absent, label it unspecified; mechanical arithmetic can be shown in
unspecified source monetary units under an explicit common-unit assumption, without
calling that assumption a supplied fact. For explicitly different currencies or
unresolved unit compatibility, keep amounts separate or calculations conditional;
do not invent FX rates or claim a converted realized gain. Honor a genuinely
applicable shared currency declaration. Numerical helper output alone is not
currency evidence.

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
## Marked position review

For a supplied journal containing `positions`, `realized_trades` and `pending_orders`,
run `python scripts/marked_position_review.py build REQUEST SOURCE_ROOT NEW_OUTPUT`.
Run it again with `verify` against the delivered Markdown and JSON. The request
contains `journal` with a relative `path` and the SHA-256 of its exact bytes.
When applicable, list additional request/context files in `supporting_sources`
using the same path/hash form to verify and retain their identities in the result.
Each open long uses a symbol, quantity, per-share basis, current mark and as-of time.
Each closed long uses quantity, buy and sell prices, and total fees if known.
Pending buys use quantity, status and limit price. Attribute fills only when the
order's own evidence identifies them. Report fees separately from filled principal.

For each independent `events[].broker_snapshot`, report the snapshot ID, status,
requested and cumulative filled quantities, average price, and fee. Use its own
`side` (buy or sell). Keep its cash flows out of realized P&L and other orders.
The gross filled notional is the cumulative filled quantity times a positive
average price. A zero filled quantity has zero gross notional. An absent quantity
or a positive fill without a usable positive price leaves the notional unknown.
Keep any reported fee visible, including a reported zero.

For a positive fill with known gross notional and a reported cumulative fee,
a buy has signed cash flow of minus notional minus fee. A sell has signed cash
flow of notional minus fee. Positive is a credit and negative a debit. Use the
snapshot's `currency`, or its `price_currency` and `fee_currency` when stated
separately. Identify any assumed common unit and leave net cash flow unresolved
for explicitly different currencies. If side is missing or unrecognized,
report gross notional and fee separately throughout the assessment. Leave the
net fill cash flow unresolved when the fee is unknown. These calculations
describe the reported fill and cannot establish settlement or account cash.

For an exit scenario, add an entry in `exit_scenarios` with `symbol`, `quantity`,
`fill_price` and optional `exit_fees`. Price each scenario independently against
the supplied position. Unspecified fees leave net realized P&L unknown. For
example, changing a sell fill by one unit changes gross P&L by the number of
shares sold. The remaining shares keep their own marked P&L. Use the same
quantities, prices, fees and conditions in narrative, recommendations and tables.
Only use additional prose that stays consistent with the verified outputs.

Use optional report metadata for the caller's case/run identifiers, runtime
description and evidence paths when requested. For other position types, lot
methods or order types use the corresponding specialist calculations. A basis-to-mark
subtotal alone cannot establish whole-session performance.
