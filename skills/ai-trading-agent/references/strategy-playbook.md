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

For a daily single-SMA replay, use the returned `rule_summary` to explain the
actual lookback, next-bar entry cap, gap-stop price, signal-exit timing and
meaning of the exit timestamps. Distinguish the modeled loss budget from the
capital allocated to the purchase. Gaps can cross the stop. Use the returned
after-cost account return for the same dates as the passive comparator.

When explaining a replay's gain or loss, read `pnl_attribution` alongside the
return. Compare the signed contribution from closed trades with the final
open position's mark less its fee-inclusive cost basis. Quote the amounts
and check that they reconcile to the change in account equity before
describing either part as the main source. A position still open at the end
has no modeled sale or exit fee. If the reconciliation fails, report the
residual and leave the explanation unresolved.

For walk-forward results, take the signed extremes from `fold_return_summary`.
Its numeric returns are fractions and its `return_range_text` is already in
percent. Include every complete window. A fold with zero closed trades can
still gain or lose on the terminal mark of an open position. Check any stated
range against the fold rows before quoting it.

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

## Testing exits in daily mean reversion

Freeze a baseline and a small set of alternatives before examining holdout outcomes. For a screen entering on 14-session Wilder RSI below 30, compare the original RSI-above-60 exit with an RSI-above-50 exit, a fixed maximum holding period and a close at least 15% below entry. These are research variants. Specify strict versus inclusive thresholds, holding-session count, gaps and exit precedence. A close-based signal can fill only at a subsequent eligible price. A carried mark cannot trigger an exit. Price any overnight gap, spread, fees and delisting proceeds explicitly.

Compare variants on the same entries and same eligible sessions. Keep an untouched chronological holdout, count every variant tried, and report net returns, drawdown, turnover, number of exits and censored positions. A short window that motivated a variant is development data. Repeated tuning on it cannot validate a replacement exit.

## Reducing turnover in sector rotation

A 21-session sector ranking reacts to past prices and can reverse between scheduled rebalances. A candidate rule can require agreement between trailing 21- and 63-session rankings before admitting a replacement, plus a minimum number of completed holding sessions. Freeze rank cutoff, ties, rebalance frequency, holding period and precedence for a mandatory event exit. Specify whether disagreement retains an eligible incumbent or leaves the sleeve in cash. Use the same total-return convention and common session for every sector. Compare turnover, costs, drawdown and net performance against the original single-window rule on matching out-of-sample windows before adopting it.
