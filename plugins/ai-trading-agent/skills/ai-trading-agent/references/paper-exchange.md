# Deterministic multi-asset paper ledger

Use `python scripts/paper_exchange.py examples/paper-multiasset.json` or
`paper_exchange.replay(document)`. This original standard-library implementation
has no network, credential, broker, subprocess or live-order capability. It accepts
only `environment: "paper"`. It replays **supplied hypothetical fills**, not actual
trades or automatically inferred fills from touching a candle high/low.

The ledger supports funded long equities/ETFs, vanilla long options, funded spot
crypto, supplied dirty-price bonds, linear futures with supplied collateral, and
funded two-currency FX conversion. It does not establish that a connected broker
supports any of these products. No output constitutes production qualification.

## Input contract

All fields below are required unless stated otherwise. Unknown fields fail.
Decimal values may be strings or finite JSON numbers; strings preserve exact
decimal intent. Booleans are not numbers. Accounting uses 34-digit Decimal precision
and half-even rounding, independently of all caller Decimal settings. The fresh
context fixes exponent bounds to -999 through 999, disables clamp, and traps invalid
operations, division by zero, overflow and underflow. Nonzero input adjusted
exponents outside that range are rejected. Arithmetic range failures become
controlled input errors; nonfinite accounting output is never accepted.
Timestamps must have time zones. Events are ordered by timestamp then their given
list order, never silently sorted. Original input is not mutated.

Top-level fields: `schema_version:1`, `environment:"paper"`, `base_currency`,
`initial_cash` mapping currency to nonnegative settled amounts, `instruments`,
`events`, `as_of`, `max_quote_age_seconds`, `max_fx_age_seconds`. No external flows
are inferred, and no annualized performance metric is generated from these events.

Each instrument: unique `id`, `kind` (`equity`, `etf`, `option`, `future`, `bond`,
`crypto`), `currency`, positive `multiplier`, `quantity_step`, `price_tick`.
Price × quantity × multiplier is funded consideration, except futures where only
variation P&L and fees affect cash. Futures support negative prices and signed
positions. Futures additionally require `expiry` and positive supplied
`margin_per_contract`; this is a research collateral assumption, not a broker
margin calculation. Options require `expiry`, `underlying` (a declared equity/ETF
in the same currency with multiplier one), `strike`, `right` (`call`/`put`),
`exercise_style` (`american`/`european`), `settlement_type` (`cash`/`physical`).
Option and futures quantity steps must be one. For a bond redemption, provide the
bond's `expiry` as its maturity timestamp. Bond quotes must be dirty currency price
in the explicitly chosen multiplier/quantity convention; a quote per 100 par must
be converted explicitly before use. FX is a cash conversion event, not a leveraged
FX instrument. Leveraged/path-dependent ETF behavior is not synthesized.

Every event has unique `id`, `type`, timezone-aware `at` plus:

| Type | Fields and semantics |
|---|---|
| `quote` | `instrument,bid,ask,bid_size,ask_size`; on-grid, non-crossed quotes. Funded ask >0; futures prices may be negative. Sizes are instrument quantities, consumed by later fills until replaced by a new quote. Quotes are supplied observations, not a market-data subscription. |
| `order` | Unique `order_id,instrument,side,quantity,order_type`; side buy/sell, order type market/limit. `limit_price` only for limits. Orders do not themselves cause fills or reserve cash. |
| `fill` | `order_id,quantity,price,fee,settle_at`; strictly after order time, before expiry, within remaining order quantity and supplied quote size. Buys cannot fill below ask, sells above bid; declared limits still apply. Better-than-quote fills are outside this harness. Fees use instrument currency. Buy cash is debited immediately; sell proceeds are receivables until the declared settlement event unless immediate. Futures fill cash is immediate and realizes the old position's change from its prior basis before adjusting quantity/rebasing. |
| `cancel_request` / `cancel_ack` | `order_id`; a request sets CANCEL_PENDING, which can still fill. Acknowledgment closes its remaining quantity. A fully filled order cannot subsequently acknowledge cancellation in this simplified state model. |
| `settle_cash` | `fill_id`; transfers that sale's receivable to settled cash at/after its due time, once only. |
| `futures_settlement` | `instrument,price,margin_per_contract,final`; realizes signed quantity × multiplier × change from prior basis. `final:true` is an explicit **cash-settlement assumption**, must occur exactly at expiry, and clears the position. It does not simulate physical delivery or a roll. Repeated marks with distinct IDs at the same price cause no repeated variation profit. |
| `fx_rate` | `currency,rate_to_base`; positive base-currency units per foreign unit for NAV translation, with its own freshness limit. Base currency always translates at one. |
| `fx_convert` | `from_currency,to_currency,amount,rate,fee`; debit amount+fee from source, credit amount×rate to destination. Rate is destination units per source unit; fee is source currency. Immediate funded conversion only; no forward settlement or swap financing. |
| `distribution` | `instrument,entitled_quantity,amount_per_unit`; supplied record-date entitlement and cash per quantity unit. Credited in instrument currency. Entitlement is not inferred from payment-date holdings; the caller must retain its evidence. Includes coupon/dividend scenarios, not a corporate-action source. |
| `split` | `instrument,ratio`; equity/ETF quantities multiplied by ratio. Requires no active orders and no held or unexpired declared option instruments on that underlying, including unfilled option orders. Adjusted deliverables require a separately modeled packet; stale option terms cannot survive the split. Old equity quotes are invalidated. Off-step residuals reject; no guessed cash-in-lieu. |
| `option_exercise` | `instrument,quantity`; explicit long physical exercise at expiry, or earlier for declared American options. Calls pay strike cash and receive multiplier shares; puts deliver owned shares for strike cash. No short option assignment or cashless financing. |
| `option_expiry` | `instrument,underlying_settlement_price`; exact expiry time. Cash options receive intrinsic value × multiplier × contracts; physical options can expire through this event only at zero intrinsic. In-the-money physical options require explicit exercise. The supplied settlement price is not independently verified. |
| `bond_redemption` | `instrument,principal_per_unit`; at maturity, pays supplied principal per quantity unit and clears holdings. No assumed final coupon, default recovery waterfall, callable exercise or accrued-interest discovery. |

Identical repeated event IDs are ignored, including transport retransmission later
in the input. Reusing an ID with different content fails. Different IDs represent
different events; the harness cannot infer that two external fills are duplicates.
Persist the complete original input outside the skill. Replaying that complete
sequence reproduces state after a restart; this is not a durable live event service.

All applied events must be at/before `as_of`. Active contracts/orders must not
remain unresolved past expiry. At every event settled cash must cover supplied
futures collateral; funded assets cannot become short. Buy/sell orders have no
pending-order reservations, so fill feasibility is checked individually. This is
deliberately not a broker buying-power or portfolio-margin model.

## Outputs and reconciliation

Output includes settled and pending cash separately, positions, order states,
applied-event journal, ignored duplicate IDs, original input hash and NAV by
currency/base currency. Funded positions use fresh bid/ask midpoint values;
futures use unrealized variation since the last settlement/fill basis. Pending sale
receivables count toward NAV but cannot finance a purchase. No currency amounts
are summed without explicit fresh FX translation. Midpoints are not liquidation
prices; liquidity, slippage and spread stress belong in the supplied scenarios.

The test suite covers cash/receivable reconciliation, duplicate replay, cancellation
races, liquidity consumption, stale quotes, no same-time fills, negative futures
prices, variation/collateral, FX, splits, option exercise/expiry and bond redemption.
These are software/accounting checks, not live broker or empirical fill validation.

## Provenance and references

Code, tests and fictional fixtures are original; no vendor source was copied and
no dependencies added. References explain why explicit conventions matter:

- [Alpaca order lifecycle](https://docs.alpaca.markets/us/docs/orders-at-alpaca):
  primary example of distinct order states; does not establish Robinhood semantics.
- [QuantConnect reality models](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/key-concepts):
  costs, fills and settlement need separate models. This harness does not claim
  equivalent functionality or borrow that implementation.
- [Robinhood agent capabilities](https://robinhood.com/us/en/support/articles/trading-with-your-agent/):
  live tool support is external to this offline calculation and must be discovered
  in the actual host. A paper scenario is not an instruction to place a trade.
