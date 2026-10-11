# Instruments, strategies and implementation boundaries

Read only the rows relevant to the mandate. Every instrument needs identifier,
legal issuer/underlying, venue, currency, units/multiplier, price convention,
calendar, settlement, liquidity, corporate actions and applicable broker support.
Unknown exposure cannot be counted as diversified or assigned zero risk.

| Investment/strategy | Required research and risk treatment | Current package support |
|---|---|---|
| Cash, T-bills, liabilities | Liquidity ladder, settlement, deposit/counterparty concentration, reinvestment, inflation and base currency | Cash benchmarks, per-currency ladder and fixed cash-flow pricing; broker balances remain authoritative |
| Long-only equities, value/quality/momentum | Existing uniform discovery, normalized primary financials, cyclicality, valuation scenarios, event and concentration review | Existing research/risk/execution gates; v4 construction and attribution |
| ETFs, index and strategic allocation | Constituents/look-through, fees, tracking, premium/discount, domicile/tax, authorized investment mandate | Existing look-through plus long-only allocation/backtest; leveraged/inverse paths not treated as linear buy-and-hold |
| Day/swing trading | Registered causal setup, completed bars, fresh executable quotes, spread/participation, event/time exit, protection and settlement | Existing opening-range/trend research examples and supervised equity execution gate; no claim of profitable edge |
| Equity long/short, market/factor neutral | Borrow availability/cost/recall, dividends in lieu, beta/sector neutrality, gross/net/collateral limits, short squeeze and asymmetric loss | Signed research allocation and scenario P&L; no short-sale broker adapter |
| Trend, carry, defensive or tactical allocation | Distinct versioned model, correct futures/FX total return, roll/funding, regime and cost tests; prevent correlated sleeve crowding | Method workflow and retained-policy backtests; strategy-specific signal engines/calibration must be supplied and validated |
| Investment-grade/high-yield/sovereign debt | Cash-flow schedule, clean/dirty/accrued price, curve/spread, duration/convexity, covenants, recovery/default, liquidity | Fixed noncallable cash-flow pricing and parallel-shift scenarios; no spread/default forecast or callable model |
| Futures/commodities | Multiplier, tick value, expiry/roll, physical delivery/first notice, margin and variation cash, negative prices, term structure | Linear marked P&L with explicit absolute price shocks; notional is not funded value; live futures unsupported |
| FX/international holdings | Base/quote convention, local return plus FX cross term, settlement holidays, hedging cost and counterparty | Exact spot translation scenarios and currency cash ladder; forwards/swaps require additional pricing and broker adapters |
| Options/volatility | Exercise/settlement style, multiplier, surface/skew/term structure, bid/ask, liquidity, Greeks, gap/pin/assignment/dividend risk | European constant-volatility valuation/Greeks and full scenario repricing; American, exotic and discrete-dividend pricing explicitly unsupported |
| REITs/real assets | Common unadjusted FFO bridge, debt maturity/refinancing, occupancy, cap rates, maintenance/development capex | Strict specialized accounting adapter and source recovery; no automatic private-property valuation |
| Insurers/banks | Legal-entity and capital scope, reserves/credit quality, asset-liability mismatch, regulatory/distribution constraints | Existing specialized financial factors and primary-data recovery; qualitative/supplemental risk review still required |
| Crypto/alternative assets | Custody/key/counterparty, 24/7 liquidity, token concentration, forks, funding/depeg/redemption and tax | Spot-price/FX stress and research procedure only; derivatives/staking/DeFi custody and execution unsupported |
| Event-driven, merger, distressed | Deal terms, consideration, legal/regulatory milestones, financing, break price, borrow/locate, default/recovery and path-dependent timing | Scenario/research workflow only; no automatic event-probability estimator or promoted strategy |
| Private funds/PE/VC/real estate | Vintage, capital calls, distributions, stale valuations, commitments, gates, lockups, manager/counterparty and scenario haircuts | Cash-flow/commitment analysis and conventional XIRR; no reliable liquid mark, automatic selection or transaction adapter |

Research an unsupported asset when useful, but name the missing model/data/adapter.
Never route it through a superficially similar supported type. Trading capability
requires separate broker, risk, order-state and failure-recovery validation, not
just a formula or a positive model output.

## Mandatory scenario details

For options, shock the underlying, volatility, rates, time and FX together; linear
delta alone can miss gamma/vega losses. The European helper rejects American style.
When the actual instrument is American, stop at that unsupported result: do not
change its exercise style to obtain a European price, even under a generic
"research only" label. A separate, explicitly requested hypothetical European
comparison is a different analysis and cannot stand in for the actual position.
Do not infer an exercise/assignment decision from theoretical price. Spreads need
each leg repriced and separate assignment/funding analysis; exercise can create a
stock obligation even when the account cannot fund it.

For futures, variation margin creates cash demands while collateral remains
encumbered. A small deposit does not mean small exposure. Never offset a margin
call with an unrealized gain or unconfirmed future sale. Model rolls using actual
contracts; a back-adjusted continuous series is not a tradable price history.

For fixed income, a parallel rate shock misses curve twists, convexity changes,
credit/default and callable/prepayment effects. Price the declared cash flows,
retain actual day-count and accrued-interest conventions for production use, and
use instrument-specific models for nonlinear obligations.

For illiquid assets, stale marks understate measured volatility and correlation.
Do not feed smoothed NAVs into liquid-asset allocation as if risks were comparable.
Include commitments, gates and redemptions in liquidity planning before sizing.

Sources: [OCC/OIC assignment guidance](https://www.optionseducation.org/referencelibrary/faq/options-assignment),
[CME contract notional](https://www.cmegroup.com/education/courses/introduction-to-futures/about-contract-notional-value),
[CME futures margin](https://www.cmegroup.com/education/courses/understanding-the-benefits-of-futures/the-benefits-of-futures-margins),
[FINRA bond due diligence](https://syndication.finra.org/content/bond-investing-and-due-diligence).
