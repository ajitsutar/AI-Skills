# Example strategy library

These are analytical baselines, not evidence of profitable strategies. The skill
has no strategy registration or promotion requirement for execution. Validation
results describe recommendation confidence and do not control the host handoff.

| Setup | Research horizon | Trigger | Exit concept | Implementation |
|---|---|---|---|---|
| core_rebalance | Years | Chosen target drift | Thesis/tax-aware review | Allocation planner |
| sma_trend | Days/weeks | Completed daily close crosses trailing SMA | Prior-low or trend exit | strategy_lab.py |
| opening_range_breakout | Intraday | Completed bar crosses opening range with comparative volume | Range invalidation, reference target and session exit | strategy_lab.py |

The breakout replay uses its own declared session grid, volume, entry-limit and
one-entry-per-session assumptions. A gap may skip a simulated entry. These are
rules of that backtest, not conditions imposed on a real user-directed order.
The daily trend example uses one bar per session and a default 20-period SMA.
Neither strategy uses GARCH as a directional forecast.

Record exact rules, data, costs and validation windows before comparing results.
The core planner follows supplied allocations rather than predicting a market
turn. VWAP reclaim, gap-and-go, mean reversion and catalyst reaction can be researched,
but no bundled replay should be described as implementing them unless it does.

Execution, monitoring and any scheduled activity belong to the actual connected
host and broker. Read [execution-handoff.md](execution-handoff.md).
