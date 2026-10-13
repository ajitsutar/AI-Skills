# Fractional shares and small dollar contributions

Small budgets and recurring contributions can use fractional quantities or native
dollar instructions. A high share price alone is not a reason to exclude a stock.
The skill prepares recommendations and [host handoffs](execution-handoff.md); it
has no separate fractional authorization, live-readiness or protection requirement.

## Actual broker semantics

Robinhood's [fractional-share guidance](https://robinhood.com/us/en/support/articles/fractional-shares/)
describes dollar/share amounts, general eligibility and retail minimums. Its
[agent trading guidance](https://robinhood.com/us/en/support/articles/trading-with-your-agent/)
describes share/dollar market orders and symbol tradability tools. These pages are
discovery sources; the connected host uses its actual available tool schema.

Preserve a requested native dollar amount. Do not silently replace it with whole
shares or an approximate fixed share quantity. A broker may compute shares from
`dollar_amount` using a recent trade price, so the instruction is not necessarily
a hard maximum debit or an exact final investment. Market fills, fees and partial
fills can change final economics. Price uncertainty is disclosed, not a skill gate.

Respect an explicitly requested order type; otherwise a market handoff does not
need a skill-imposed limit price. The broker determines fractional eligibility,
precision, minimums, session support and residual Sell All availability. Do not
invent support or impose the old package's regular-session/quantity-limit adapter
as an additional constraint on the host.

## Analytical sizing

`fractional_shares.size_dollar_buy` estimates a fractional quantity from a budget,
price, quantity increment, minimum notional/quantity and fee estimates. Decimal
arithmetic rounds down and reports estimated cost and unused budget. Its maximum
cash-debit estimate depends on its supplied price and assumptions; it is not a
market-order spending guarantee or a broker permission decision.

The sizing output preserves `requested_dollar_budget` and `request_basis` separately
from its legacy `order_basis: quantity` estimate. `estimated_cash_debit` aliases
`maximum_cash_debit`; both use the supplied reference price and fee assumptions.
`cash_debit_is_guaranteed: false` applies even when cent rounding exhausts the
budget. A different fill price can exceed that estimate. `calculation_only: true`
does not indicate a submitted order or a broker response.

Recurring results retain per-symbol `requested_amounts` even if cash/reserve
assumptions yield `WAIT_FOR_SETTLED_CASH`, or a symbol is skipped by the sizing
calculation. Preserve those amounts in a native dollar handoff where the actual
host supports it. Never replace them with rounded quantities or estimated debit.
When emitting a standalone handoff artifact, retain the supplied account alias,
plan and contribution occurrence as context alongside the native payload. If the
actual broker schema has no corresponding fields, use a separate envelope or
companion context; do not invent broker fields or imply a schedule or submission.
The legacy status and `execution_authorized: false` describe this helper's local
calculation; they create no cash test, execution gate or additional approval.
Actual host/broker capabilities, submission and fills must come from observed tools
and results. This helper cannot establish them.

`portfolio_manager.rebalance` defaults to fractional planning with configurable
minimums. Offline assumptions are marked `OFFLINE_ASSUMPTIONS_UNVERIFIED`.
Per-symbol `quantity_rules` can improve the calculation; the calculation's skipped
symbols and constraint results describe that plan, not an execution veto.
Whole-share planning is optional. Explain unallocated cash rather than calling it
invested.

For a fictional contribution calculation:

```text
python scripts/portfolio_manager.py examples/recurring-fractional.json --recurring
```

This produces one occurrence's proposal. It does not install a schedule or trade.
Stable plan/occurrence identifiers help distinguish repeated reports; the skill
maintains no execution ticket, duplicate-submission lock or reservation ledger.
The broker/host owns actual order state and reconciliation.

## Recurring investments and fills

[Robinhood recurring investments](https://robinhood.com/us/en/support/articles/recurring-investments/)
use the broker's own scheduling and order semantics. A research instruction does
not itself request a new schedule. When scheduling is requested, the host uses its
supported tools and reports the confirmed schedule rather than claiming that a
local sizing example created one.

Retain decimal quantities and actual cumulative fills in analysis. Do not round
partial fills into whole shares or count the same cumulative update twice. Cash
and fee records determine realized debit and remaining budget. Report unknown
fees as unknown, not zero. These are accounting-quality requirements, not gates.

`size_tactical` accepts a quantity increment and minimum notional for fractional
research sizing. The historical replay's whole-share baseline does not validate a
fractional-fill strategy. Arithmetic tests establish calculations, not live broker
certification.
