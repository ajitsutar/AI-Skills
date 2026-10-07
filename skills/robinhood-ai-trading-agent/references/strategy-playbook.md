# Example strategy library

These setups are research baselines, not validated investments. All included replay
outputs set validated_for_live=false. A setup is not enabled for live use just
because it exists in the library.

| Setup | Horizon | Trigger | Exit concept | Implementation |
|---|---|---|---|---|
| core_rebalance | Years | Approved target drift and usable cash | Thesis/tax-aware review | Cash-first planner plus target cap |
| sma_trend | Days/weeks | Completed daily close crosses above a trailing SMA | Prior five-day low stop or next-open trend exit | strategy_lab.py |
| opening_range_breakout | Intraday | Completed bar crosses first three 5-minute bars' high, with 1.5x opening average volume | Opening-range low stop, 2.5R reference target, scheduled close cutoff | strategy_lab.py |

For breakout, require contiguous bars from the official session open, sufficient
liquidity, no disallowed event and a current quote. The example admits at most one
entry per session. Gaps above the signal's entry limit are skipped. The target uses
the signal close; recalculate net reward/risk against the actual proposed limit
before any broker action.

For daily trend, require one bar per session. The SMA period defaults to 20. The
strategy uses a structural prior-low stop, not a fitted GARCH directional prediction.

The core planner is allocation-driven, not a timing signal. Public insider activity
remains optional corroborating research; it no longer governs the default portfolio.

Register a strategy version and evaluation evidence before proposing promotion.
Other concepts from the original ZIP (VWAP reclaim, gap-and-go, mean reversion,
catalyst reaction) remain ideas, with no implemented or validated execution module.
