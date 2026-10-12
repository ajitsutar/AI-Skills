# Fractional shares and small dollar contributions

Use fractional sizing for small stock/ETF budgets and recurring contributions;
nominal share price must not eliminate an otherwise suitable investment. Research,
portfolio targets, settled cash, fees, concentration and authorization still apply.
The implementation supports exact fractional **quantity-based DAY limit orders**
when the connected broker's actual schemas and observed semantics support them.
Whole-share mode remains available. No connection or trade is made by these helpers.

## Broker facts and implementation boundary

Checked October 12, 2026 against Robinhood's official documentation:

- [Fractional shares](https://robinhood.com/us/en/support/articles/fractional-shares/)
  describes dollar or share amounts, a $1 normal order minimum, eligible listed
  NMS securities, and a retail Sell All exception for sub-dollar residuals. Its
  price/market-cap eligibility description is a general rule, not a per-symbol
  guarantee. Actual share increments are not established by that page.
- [Trading with your agent](https://robinhood.com/us/en/support/articles/trading-with-your-agent/)
  lists share/dollar market orders, limit orders and `get_equity_tradability`, whose
  description includes fractional eligibility. These are discovery hints; inspect
  connected tools before binding real parameters or asserting live availability.
- [Limit orders](https://robinhood.com/us/en/support/articles/limit-order/)
  describes price protection and possible nonfills. Retail order defaults and
  extended-hours eligibility do not override this package's regular-session scope.
- [Recurring investments](https://robinhood.com/us/en/support/articles/recurring-investments/)
  describes native dollar-based recurring orders filled through market-order
  batches. The helper below is a per-occurrence proposal generator; it does not
  install or manage a broker recurring schedule.

Native dollar-market orders, extended hours and the sub-dollar Sell All exception
are not implemented by this quantity-limit adapter. Do not convert a native dollar
order into a supposedly equivalent fixed share order silently. A quantity limit
proposal can spend less than its dollar ceiling because of rounding, fees, price
improvement or partial fills. Do not call the residual a completed investment.

## Sizing and contributions

`fractional_shares.size_dollar_buy` accepts a dollar ceiling inclusive of fee
reserves, a price, `quantity_increment`, `min_notional`, `min_quantity`,
`fee_per_share` and `fee_per_order`. Decimal arithmetic rounds quantities down;
notional and aggregate fees are conservatively reserved up to cents. It returns
the exact quantity, estimated notional, maximum cash debit and unused budget. It
never rounds a small invalid trade up to a venue minimum or exceeds the ceiling.
Actual broker charges remain authoritative and must be reconciled.

`portfolio_manager.rebalance` defaults to fractional planning and a configurable
$1 minimum planning trade. Its offline fallback uses a 0.000001 share increment
and $1 notional, explicitly marked `OFFLINE_ASSUMPTIONS_UNVERIFIED`. These are
planning assumptions, not broker precision claims. Supply per-symbol
`quantity_rules={symbol:{eligible,quantity_increment,min_notional,min_quantity}}`
for observed constraints. Supplied unknown/false eligibility skips that symbol;
it never assumes permission. Set `allow_fractional=false` for integer proposals.
Drift bands and turnover limits still apply; lower a planning band only when the
user's allocation policy allows it. Fees count toward planning cash/turnover caps.

For one contribution occurrence:

```text
python scripts/portfolio_manager.py examples/recurring-fractional.json --recurring
```

The fictional example allocates $10 and $15 toward $300 and $700 securities and
preserves a $5 reserve from $30 settled, unreserved cash. `amounts` are whole-cent
cash ceilings inclusive of supplied fee estimates. Insufficient funding returns
`WAIT_FOR_SETTLED_CASH`; unavailable symbols remain cash and are not redistributed.
Recurring amounts describe a funding plan, not an exemption from target weights.
Use the current approved targets and risk gate for every occurrence.

`plan_id`, `occurrence_id`, account alias and symbol determine stable intent/signal
keys. Repricing the same occurrence retains its key; a new ID must not bypass an
existing claim. The occurrence should identify the original scheduled obligation
even if a holiday moves execution to another session. Resolve actual session dates
with the exchange calendar. Reconcile once through the durable ledger; cancelled
or partially filled occurrences are not automatically topped up. Creating another
occurrence or plan to evade deduplication is prohibited.

Run either a separately configured broker-native recurring plan or the supervised
host proposal loop for a given contribution, not both. Creating schedules requires
an explicit user request and supported tools. This module is not a scheduler or
an unattended service and does not count unsettled deposits as funding.

## Exact runtime contract

The personal draft policy includes:

```json
"fractional_shares": {"enabled": true, "max_rules_age_seconds": 60}
```

Older policies without this field retain whole-share-only authorization. Changing
an approved policy invalidates its hash and requires reauthorization. Paper mode
may use labeled fictional rules; live orders require `source=official_broker`.
Every fractional order needs fresh `snapshot.quotes[symbol].fractional_rules`:

```json
{
  "eligible": true,
  "quantity_increment": "0.000001",
  "min_quantity": "0.000001",
  "min_notional": "1",
  "order_types": ["limit"],
  "time_in_force": ["day"],
  "sides": ["buy", "sell"],
  "sessions": ["regular"],
  "checked_at": "2026-10-12T15:00:00Z",
  "source": "official_broker",
  "evidence": ["ILLUSTRATIVE ONLY: replace with actual tool observation"]
}
```

All values above are illustrative. Refresh actual symbol rules; do not relabel
this fixture or the retail $1 rule as observed broker metadata. Invalid increments,
unknown eligibility, stale evidence, wrong order/TIF/side/session or amounts below
the observed minimum block. There is no automatic truncation or upward rounding
of an already approved quantity. Sub-dollar residual sales remain blocked unless
a future tested Sell All adapter is added.

The order remains `order_basis=quantity` (omission preserves legacy semantics),
with exact decimal-string `quantity` and `limit_price`. Optional `dollar_budget`
caps its maximum cash debit including policy fees. `limits.fee_per_order` is an
optional nonnegative fixed fee reserve in addition to `fee_per_share`; neither
field is a claim about Robinhood's current fee schedule. Missing fixed fee defaults
to zero for compatibility; the host must supply current applicable fees.

The observed review/submit operation also needs `fractional_share_semantics`:
`quantity_based=true`, `cumulative_fractional_fills=true`, evidenced supported
`order_types`, `time_in_force`, `sides`, `sessions`, and `evidence`. A JSON schema
that accepts numbers alone is insufficient. Bind the exact decimal through a
supported string/number schema; the bridge rejects integer truncation and numeric
precision loss. Native notional input is rejected instead of being ignored.

All other readiness checks still run. Tactical fractional entries need the same
observed native atomic protection, fractional partial-fill coverage, exclusive
exits and supervised time-exit contract. Unsupported protection keeps them in
paper/proposal mode; a manually written stop price is not broker protection.

## Fills, reservations and compatibility

Positions, pending buys/sells and cumulative fills retain decimal strings. Pending
fractional buys reserve remaining quantity at the bounded reservation price plus
fees; cancellation requests release nothing until authoritative terminal status.
Actual partial fills may have finer precision than the entry grid: do not round
them, add repeated cumulative reports twice, oversell owned quantities or spend
unsettled proceeds. Broker cash/fee records resolve penny differences; the sizing
reservation is not an accounting receipt. Full/partial/cancelled status and fill
prices continue through `ExecutionLedger.reconcile` and its conflict latch.

`size_tactical` accepts an explicit `quantity_increment` and minimum notional for
fractional risk sizing. Its default remains integer sizing for old callers. The
bundled historical strategy replay remains a whole-share baseline; do not present
that result as a validated fractional-fill strategy. Unit and mocked integration
tests establish arithmetic/gate behavior, not a completed live broker certification.
