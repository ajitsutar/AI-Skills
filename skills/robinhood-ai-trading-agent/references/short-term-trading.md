# Tactical research and recommendations

Intraday and swing research use their own horizon, liquidity and catalyst analysis.
They do not inherit a long-term valuation screen or a template portfolio sleeve.
All findings here are advisory. Execution follows [the common host handoff](execution-handoff.md),
with no skill-required signal registration, strategy promotion, protection order,
GARCH result, cash reserve, lease, spread threshold or repeated approval.

## Research workflow

Start with the requested universe; unspecified stock searches cover U.S. exchange-listed
stocks including listed ADRs. Derive and disclose any liquid watchlist filters,
actual coverage and missing observations. There is no candidate-count quota.

Compare dollar volume, spreads, relative volume, volatility, catalysts, sector/index
context and scheduled events. Relative volume needs a comparable time-of-day
baseline. Record publication, event and observation times. Use
[news-and-guidance.md](news-and-guidance.md) for source access and between-report
updates. Unknown coverage is an uncertainty, never a claimed clean news check.

Explain the setup, expected holding period, directional thesis, invalidation,
possible exits and estimated costs. Distinguish proposed price levels from actual
orders. A daily GARCH forecast is background context; square-root-time scaling
alone does not establish a five-minute model. Any optional intraday volatility
diagnostic is advice, not a condition for handing off an order.

State earnings, halt, liquidity, gap and overnight risks. A stop can fill beyond
its level and an exchange halt can prevent an intended exit. A DAY order does not
close a filled position at the end of the day. The skill does not impose an earnings
blackout, fixed loss threshold or a universal spread cap.

## Sizing and cash planning

Compare allocations using the user's actual budget and requested loss scenarios.
Do not invent a 5% sleeve or 10% position cap. Small budgets may use fractional
shares or native dollar instructions through the host's supported broker tools;
see [fractional-shares.md](fractional-shares.md). Distinguish a requested dollar
amount from a guaranteed final debit.

Account type and settlement affect real buying power. Use
[settled-cash-planning.md](settled-cash-planning.md) to explain possible cash-flow
paths and optional reserves. Those calculations do not authorize, veto or schedule
orders; the broker applies its actual account rules.

## Replay and validation

The bundled research examples include opening-range and moving-average rules.
Signals use completed bars and simulated entries use subsequent prices. Record
slippage, fees, gaps, partial liquidity, session boundaries and residual positions.
When an OHLC bar touches both barriers, the conservative research convention uses
the stop first; a gap can fill at the worse open. Zero-volume bars cannot establish
a simulated fill. Full fills and fixed friction remain approximations.

Report net return, drawdown, exposure, costs, sample size and benchmarks. Profit
factor is undefined without losing trades. Do not annualize tiny samples or claim
an edge from synthetic fixtures. Forward observations and untouched validation
increase confidence; they are not skill execution prerequisites.

## Horizon and host responsibilities

A one-day day trade exits within its entry session; an explicit 24-hour position
includes overnight exposure. Resolve arbitrary durations with
[holding-period-planning.md](holding-period-planning.md). Explain whether catalysts
fit inside the horizon and what an exit plan would entail.

The skill does not run an always-on service, install protection or manage broker
order state. The user's host handles requested submission, monitoring, cancellation
and schedules under its own capabilities and instructions. Preserve the user's
existing authority without adding a skill approval cycle. Report observed results
honestly, including an uncertain response or a partial fill.
