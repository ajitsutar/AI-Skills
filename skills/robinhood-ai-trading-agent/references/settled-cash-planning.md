# Settled cash for day trading

Use this procedure to avoid deploying all usable cash and then waiting for sale
proceeds to settle. It controls new intraday buys, not which stocks may be sold.
Selling positions creates proceeds; a cash account cannot immediately reuse those
proceeds. Retaining other stocks does not itself create buying power. Protect
liquidity before entry by keeping part of the account in uncommitted settled cash.

## Current broker rules

Checked October 8, 2026: Robinhood describes stock/ETF sales as T+1 and says cash
accounts cannot trade with unsettled sale proceeds. Weekends and applicable market
or banking holidays can delay availability. T+1 is not a 24-hour timer. Its Agentic
limited-margin account permits using unsettled proceeds without borrowing power;
account type must be observed, not assumed. This package continues to require
settled funds even if a broker account offers broader buying power. Do not change
account type or enable a different funding model automatically.

Sources: [settlement and buying power](https://robinhood.com/us/en/support/articles/settlement-and-buying-power/),
[T+1](https://robinhood.com/us/en/support/articles/T1-settlements/),
[Agentic account types](https://robinhood.com/us/en/support/articles/setting-up-an-agent/).
Recheck these and the actual connected account before live use.

## Configure the reserve

The policy's `limits` accepts two optional fields:

```json
{
  "intraday_settled_cash_floor_amount": "250",
  "intraday_settled_cash_floor_fraction": "0.25"
}
```

The reserve is the larger of the dollar amount and the fraction of current total
account equity. The snippet illustrates settings, not an approved allocation.
With $500 equity it reserves $250, not $375. Use amount=0 for percentage only,
fraction=0 for dollars only, or both=0 to disable this additional reserve. Other
settled-cash, cash-floor, sleeve, risk and broker checks still apply.

The shipped draft policies explicitly use amount=0 and fraction=0.05. For older
policies, a missing amount means zero and a missing fraction uses their existing
`cash_floor` fraction. Make both fields explicit when reviewing a personal policy.
Changing settings invalidates policy-bound grants and session authorization. A
reserve larger than the available balance blocks entries; it never sells holdings
or changes allocations to manufacture cash. A dollar floor can preserve a fixed
amount when equity changes; a percentage floor changes with marked equity.

Before each proposed day-trade buy:

1. Reconcile current broker cash, settled cash, buying power, positions and all
   pending buys, including other sleeves and manual activity.
2. Calculate `reserve = max(amount, equity * fraction)` and
   `intraday_cash_budget = max(0, settled_cash - pending_buy_reservations - reserve)`.
   Reservations include remaining quantities and fees, including cancel-pending
   orders. Use gross normalized settled cash; do not subtract reservations twice.
3. Bound the new buy's full limit cost plus fees by that budget and all existing
   caps. The reserve overlaps the ordinary cash floor; do not add the two floors.
4. After each fill or cancellation, refresh and reconcile. Completed sales add
   no reusable settled cash until the broker actually reports it as settled.

For illustration, $500 of settled cash with a $250 reserve permits at most $250
of new buys including costs, before tighter limits. After a $200 round trip whose
net sale proceeds equal its entry cost, settled cash remains $300 while $200 is
unsettled. Only $50 remains available for another entry under this reserve.
The rest waits for a confirmed balance update. This arithmetic is independent of
whether the second trade uses the same symbol or a different one. The package's
separate illustrative 5% intraday sleeve can impose a much smaller trade cap.

The minimum remains reserved: it is not automatically released later that day or
the next morning to force another trade. Keep that buffer and stagger entries
from the balance above it; no compulsory X/Y rotation or symbol ban is needed.

## Waiting and exits

`risk_engine.evaluate` reports `INTRADAY_SETTLED_CASH_RESERVE` for an entry that
would breach the floor. Its metrics show required cash, pending buy reservations,
unreserved settled cash, the reserve and the cash-budget shortfall. When cash is
the only blocker, `entry_disposition=WAIT_FOR_CASH_BUDGET` is a local planning
result, not an executable or scheduled order. Waiting alone may not resolve a
shortfall: there may be no pending settlement or the account may be too small.

Do not send or park an unfunded entry at the broker for later execution. Expire
the signal normally. When funds become available, require a fresh valid signal,
quotes, account snapshot, event review, risk checks and applicable authorization.
Do not re-date an old signal or reuse an expired exact-order approval. A broker
rejection needs reconciliation, not a blind retry. Readiness is never implied by
the `READY_FOR_NEXT_GATE` label.

An expected settlement date is planning information only. Do not credit funds at
midnight, after 24 hours, at the next exchange opening, or because a local calendar
predicts settlement. Broker confirmation remains authoritative, including holidays,
partial fills, transfer holds and restrictions. No background wakeup is created.

Allow authorized exits, stops and risk reductions even with no settled cash. Never
keep a failed day trade open or sell core holdings merely to preserve trading
activity. The reserve is an entry-time constraint, not a guarantee against manual
trades, other systems, withdrawals, fees or market/account changes. Reconcile those
changes and stop new entries if the floor is breached. If an account is already
fully invested, report the liquidity gap; do not promise an immediate repair.

The added reserve applies only to `sleeve=intraday` buys. Core and swing orders
retain their existing cash rules. All sleeves share the real account cash, so
their reservations still reduce an intraday entry's budget. If the user wants an
account-wide liquidity floor across all strategies, configure that separately;
do not claim this intraday-only setting protects against other strategies' buys.

## Replay boundary

The strategy lab is a single-symbol price/strategy simulation. Its one-entry-per-
session rule is not a broker settlement model, especially with overnight residual
positions, banking holidays or multiple symbols. It does not simulate this reserve
or establish sustainable cash-account turnover. Report that limitation and validate
the proposed sequence with broker-normalized or explicitly fictional cash snapshots
through the risk gate before using it as cash-account operational evidence.
