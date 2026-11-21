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

When a user asks for a daily SMA without specifying its rule, name the method
you use. `sma_trend` compares the completed close with one trailing average.
`backtest.dual_sma` compares two trailing averages. Their position sizes, costs
and returns can differ even on identical prices. Report each under its own name.

Explain signal time and execution time separately using the replay's
`execution_basis`. For example, the bar ending at 13:50 can use its own closing
price for the decision. A breakout entry can use the following bar's modeled
open at 13:50 if eligible. Those bars share a clock boundary. The dual-SMA
entry uses the open at the signal index plus one plus the declared bar delay.
Distinguish close-driven entries from independently modeled stop, target and
scheduled exits.

A costed-bar replay receives a supplied signal and simulates its fill at an
eligible open. Spread, liquidity and delay estimates from that replay describe
the model. To report actual latency, match timestamped decisions to order
acknowledgements. For realized execution cost, match quotes and fees to fill
records. For settlement, use dated account cash records. State which of those
records were supplied and who produced them. A paper ledger can reconcile
supplied events while retaining their original hypothetical or observed status.

Record exact rules, data, costs and validation windows before comparing results.
The core planner follows supplied allocations rather than predicting a market
turn. VWAP reclaim, gap-and-go, mean reversion and catalyst reaction can be researched,
but no bundled replay should be described as implementing them unless it does.

Execution, monitoring and any scheduled activity belong to the actual connected
host and broker. Read [execution-handoff.md](execution-handoff.md).
