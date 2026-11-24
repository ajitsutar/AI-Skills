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
its level and an exchange halt can prevent an intended exit. When comparing a halt
observation with a later quote, use the [halt-observation brief](halt-review.md#halt-observations-in-an-intraday-brief).
Carry the dated halt, separate resumption evidence and limits into the setup summary.
A DAY order does not
close a filled position at the end of the day. The skill does not impose an earnings
blackout, fixed loss threshold or a universal spread cap.

## Delivering a snapshot-based intraday brief

For a brief naming individual stocks, use the following native delivery path
when the source set contains a self-contained regular session, one or more
dated two-sided quotes, mixed published events, listed-security metadata and
prior daily closes/volume. It produces the complete first response, including
evidence limits, catalysts and earnings, quote age/spread, historical liquidity
and setup assessment. Historical figures and displayed sizes cannot establish
execution capacity. A dated halt supplies no current-status assertion.
For each symbol the pair includes a catalyst assessment at the cutoff. Publication on the supplied local session date is the stated freshness convention. Calendar and venue updates, pending
news, earlier developments and unclassified events retain their own evidence roles.
An explicitly reported earnings release time (`earnings_released_at`) differs from
a calendar's scheduled release time. A reported development supplies no proof of
price impact, and missing source coverage cannot establish market-wide absence.

Prepare a request with `symbols` (every security named in the original prompt)
and `sources`. Under `sources`, bind the unchanged `prompt`, `scope`, `session`,
`universe`, `quotes`, `events` and CSV `history` as separate objects containing
their original relative `path` and `sha256`. Bind a supplied original `context`
as well. If the host declares response fields in a separate document, bind its
unchanged bytes as `sources.response_contract` using the same path/hash format.
The helper also recognizes declarations in the original prompt and an inventory-bound
adjacent package protocol. Supply the required host observations in `metadata`:
`case_id`, optional `run_id`, a `runtime_model_metadata` object with actual or
unknown runtime details, and an `evidence_paths` list naming retained artifacts.
The renderer generates the per-symbol `rows` (also retained as `symbols`), source
hashes, and `limitations` from the evidence. Host metadata cannot replace them.

```text
python -B scripts/intraday_brief.py build request.json source-root output-directory
python -B scripts/intraday_brief.py verify request.json source-root output-directory
```

Use a fresh output directory for build. Deliver the emitted `first-response.md`
and `response.json` unchanged. For copies, run verify against the directory
containing the actual delivered pair. Verification rebuilds both files from their bound
sources and checks their exact bytes, including the final setup text. A separate
freehand setup recap can introduce a status claim the source does not make.
For a host requiring a short handoff, link the verified files.

The session carries its local open/close with UTC offsets, time zone, date and
`scenario_clock`. The quote file has the same clock, a `quotes` array with symbol,
currency, bid/ask and `quote_time`, and optional `bid_size_shares`, `ask_size_shares`
and `book_depth_levels`. The universe has a dated `as_of` and `rows`. The history
has `symbol`, `session_date`, `unadjusted_close_usd` and `shares_volume`. The
events file has `observations` with symbol, kind (`event_kind`) and `published_at`.
The renderer retains source text, announced earnings and windows. For
`exchange_halt`, it uses the [halt-observation fields](halt-review.md#halt-observations-in-an-intraday-brief).
A separate `exchange_status` observation carries a source-reported `status` and
`status_as_of`. Keep publication time distinct from the time of that status.

Inspect the supplied files and request for additional material evidence, such
as trade prints, bars, broker state, depth in other units, a specified strategy
or requested live verification. This snapshot profile does not evaluate those
tasks. Use the applicable broader research workflow when needed and preserve the
source-bound halt, quote-size, historical-volume and current-status distinctions
in every delivered setup and structured outcome.

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
