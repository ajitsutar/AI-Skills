# Cash availability and settlement planning

Selling holdings creates proceeds, not necessarily immediately reusable buying
power. Keeping other stocks invested does not itself create cash. This reference
supports cash-flow advice; it imposes no execution gate or reserve requirement.

## Broker rules are external

Robinhood's published stock/ETF settlement convention is T+1. Cash-account use of
unsettled proceeds differs from limited-margin and other account arrangements.
T+1 is a business-day convention, not a 24-hour timer. Recheck the actual account
and current broker documentation when explaining availability; do not assume one
rule for every account or change an account type on the user's behalf.

Sources: [settlement and buying power](https://robinhood.com/us/en/support/articles/settlement-and-buying-power/),
[T+1](https://robinhood.com/us/en/support/articles/T1-settlements/),
[Agentic account types](https://robinhood.com/us/en/support/articles/setting-up-an-agent/).

The skill does not demand settled cash when the broker permits another funding
basis. Actual buying power, holds, account restrictions and order acceptance belong
to the broker and connected host.

## Optional reserve analysis

If the user asks to maintain liquidity, preserve each input's meaning with
[planning input roles](planning-input-roles.md): observation, minimum, maximum,
target, pending item or hypothetical scenario. A pending item is not automatically
an additional cash reservation. Missing amounts are unknown, not zero.

Only when the user specifies two minimum reserves for the same purpose and
denominator may they be combined as
`reserve = max(minimum_dollar_reserve, declared_equity * minimum_reserve_fraction)`.
Do not convert a target or maximum into a minimum.

Use an explicit cash basis and compute the signed result first:
`cash_after_reserve = cash_before_reservations - not_yet_deducted_reservations - reserve`.
A separate illustrative purchase budget can be `max(0, cash_after_reserve)`, but
retain any negative shortfall. Never subtract reservations already reflected in
the supplied cash. An earmarked tax reserve remains an account asset; an actual
tax payment leaves the account. Include fees and distinguish current cash,
pending sales and expected settlements. Reserves are user-selected planning
preferences; sample values are not mandatory constraints on another request.

For a fictional $500 cash account, a $250 reserve leaves $250 for purchases before
costs. A completed $200 round trip may leave $300 settled and $200 unsettled,
leaving $50 above that planning reserve until proceeds become available. Changing
the symbol for the next purchase does not change the settlement arithmetic.

An expected settlement date is an estimate. Broker-reported balances establish
actual availability, including holidays, transfer holds, fees and partial fills.
A calendar forecast does not itself create cash or a scheduled order.

Use `planning.cash_plan` for declared currency-specific cash events and
`planning.dated_projection` for holdings, dated flows and a consistent portfolio
denominator; see [portfolio projection](portfolio-projection.md). Use
`planning.settlement_transfer_paths` for supplied settlement/transfer dates and
lags; see [planning comparison](planning-comparison.md). A date alone does not
establish an intraday cutoff or prove that a same-day transfer can meet a deadline.

## Report and handoff

Report liquidity shortfalls and alternatives as advice. The skill neither pauses
submission nor demands reapproval because of its own cash calculation. Follow
[execution-handoff.md](execution-handoff.md) for the user's requested order; actual
broker/platform requirements remain external.

A price-only strategy replay is not a settlement model. Sustainable cash turnover
needs a separate account cash-flow simulation and observed account conventions.
Do not portray an illustrative reserve or a hypothetical balance as broker truth.
