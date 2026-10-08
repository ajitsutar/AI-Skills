# Tactical operating model

Keep intraday and swing capital separate from core holdings. No borrowed funds,
automatic loss replenishment, martingale sizing, averaging down to rescue a failed
setup, or relabeling a day trade as a long-term holding.

## Planning

This workflow is separate from long-term value investing: configurable liquid
watchlist -> session/catalyst/event checks -> registered completed-bar setup ->
entry/stop/target/time exit and net costs -> sizing/risk gates -> authorized paper
or authorized personal live execution -> fills/protection/exit reconciliation. Undervaluation,
analyst upside and an Eligible research label are neither prerequisites nor
substitutes for an intraday setup. S&P 500 may seed discovery; the intraday universe
can be configured independently. There is no candidate-count quota.

Prepare the watchlist before the session where possible. Use dollar volume,
current spread/liquidity, reliable quotes/bars, relevant catalysts, session-relative
volume, volatility and sector/index context. Relative volume needs comparable
time-of-day history; a full-day average is not an opening-minute baseline. Record
rules/version and actual screening coverage. Only policy-allowed symbols/setups
can reach execution; research membership cannot extend that authorization.

Use read-only scout/analyst and risk-review roles, followed by a sole authorized
execution stage. These are logical responsibilities; the skill does not require or
implicitly authorize additional agents.

Classify trend/range, volatility, liquidity, sector/index context and scheduled
events. Missing regime evidence means wait or research, not a fabricated label.
Choose only a registered setup that fits the available data and intended horizon.

Specify signal timestamp/version, entry trigger and limit, stop/invalidation,
target, time exit, event exclusions and planned loss. Size after defining the stop.
Use current bid/ask and costs. Assess GARCH under the explicit SKILL.md procedure;
report a computation or a specific skip/failure reason. Its sizing effect is
conditional on model quality and policy, not automatically applied because it ran.

Daily GARCH is background risk context. An intraday model needs audited bars,
session-gap/seasonality treatment and validation at its actual horizon against
simpler estimates. Square-root-time scaling alone does not validate a five-minute
model. LOW/NORMAL must not loosen capital limits or determine a directional entry.

Define event blackouts in the strategy card with sourced dates/timezones, start
and release conditions. Recheck the calendar, material news and halts before entry.
Unknown event coverage is not clear. A future catalyst-reaction strategy needs its
own validated post-event rules; it cannot waive the breakout setup's event block.

## Gates

The local helper checks cash/settlement, open-order reservations, hard sleeve and
symbol/sector caps, exact core targets, tactical stop-risk/reward after friction,
loss/drawdown breakers, current session bounds, quote freshness, halt/tradability,
liquidity, allowed setups and limit-price increments.

Personal readiness also checks policy-required covariance, look-through/stress, actual event windows, strategy evidence and GARCH. Tax and data-vendor validity still need source-backed review. Loss metrics must include unrealized marked changes and exclude external
flows. Unknown inputs cannot be interpreted as zero risk.

## Intraday lifecycle

Before open: reconcile, check actual calendar and event exclusions, verify data
quality and protection coverage. During the session: completed bars generate
candidates; fresh quotes and account state govern executable parameters. Stop new
entries at the configured cutoff.

Before close: manage only the tactical shares, cancel outstanding entry orders when
authorized, and verify exits/remaining protection. An exchange halt can prevent
liquidation; never promise a guaranteed flat close. Missing/illiquid exit bars in
the replay retain a residual position and report the limitation.

Record signal expiry, entry cutoff, time-exit deadline, maximum open risk and loss
breakers. DAY validity does not create a stop or close a filled position. A fresh
signal needs fresh quotes/account state; an uncertain submit needs reconciliation.
The replay expires an intraday entry when its immediately following expected bar
is missing, rather than filling the stale signal later in the session.

A strategy signal is not approval. Follow [approval-gated-execution.md](approval-gated-execution.md)
for either an exact grant or bounded mandate. Autonomous tactical entry requires
verified native protection and supervised time-exit coverage. The active session uses supervised_session.py and personal_runtime.py; it has no always-on process after Codex closes. Follow personal-setup.md and the durable cancellation workflow.

Small-account sizing uses actual settled cash and broker-specific restrictions.
Do not assume intraday sale proceeds are reusable immediately or hard-code an
obsolete universal account rule. Keep core shares/cash reserved. At $500 equity,
the illustrative 5% intraday sleeve permits at most $25 notional before stricter
risk/cash/cost limits; whole-share sizing may correctly be zero. Do not increase
the sleeve, enable leverage or choose illiquid cheap shares to manufacture activity.
Fractional trading needs a separately supported and validated adapter.

## Costs and replay

Signals use completed bars; simulated entries use the next open and must meet the
prior signal's price cap. Slippage and fees reduce cash and P&L. When an OHLC bar
touches both barriers, assume the stop occurred first; a stop gap fills at the worse
open. Zero-volume bars cannot fill. Full fills and fixed friction remain simplified
assumptions, not executable liquidity estimates.

Report net returns, drawdown, trades, exposure, costs, residual positions and a
benchmark. Profit factor is undefined when there are no losing trades; report null
rather than infinity. Do not annualize tiny samples or claim positive expectancy
from a synthetic fixture.

## Current implementation boundary

The executable live signal adapter is opening_range_breakout. It validates the
current complete session bar grid, recomputes the signal, verifies its economics
and enforces a per-symbol session entry limit across restart and mode changes.
The default limit is one attempted entry per symbol/session, including cancelled
attempts. Snapshot external_setup_entry_counts includes unmatched broker activity.
No bundled setup is approved for live trading; a positive synthetic replay is not
promotion evidence. The SMA example remains research-only until a matching live
signal/exit adapter and evaluation are added. This does not restrict the separate
long-term core portfolio workflow.

## Holding-period boundary

Read [holding-period-planning.md](holding-period-planning.md) when a duration is
specified. A one-day day trade exits in its entry session; a 24-hour overnight
position is a swing. The standalone horizon_review helper can resolve the clock
without imposing a fundamental screen. Arbitrary longer holds route to swing or
long-term research with their own evidence, events and review cadence. Do not
extend an intraday exit or reuse its live adapter for a multi-session strategy.
Event scope defaults to entry_and_hold for compatibility with approved live
policies; entry_only is a different policy choice, not an automatic relaxation.
