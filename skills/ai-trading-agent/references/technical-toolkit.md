# Reproducible technical analysis

Use `scripts/technical_toolkit.py` for supplied, finalized OHLCV bars. It computes indicators, explicit swing geometry, a bar-based volume-profile approximation, a supplied order-book snapshot imbalance, an SVG price chart, and a long/flat next-open research replay. It does not acquire market data, supply live depth, submit trades, or establish that an indicator predicts returns.

## Run and input contract

```sh
python scripts/technical_toolkit.py --input examples/technical-toolkit-input.json --output technical-result.json --chart technical-chart.svg
python -m unittest discover -s tests -p test_technical_toolkit.py -v
```

Import API: `analyze(request) -> dict`; `OPERATIONS['analyze']` exposes that callable. `resolve_request(request)` deep-copies and materializes all indicator, replay-cost and profile-window defaults without calculating results; freeze this resolved request for model comparisons. `chart_svg(validated_bars, result, title)` returns a self-contained SVG string. Lower-level OHLCV functions assume nonempty output from `validate_bars`; use the validated `analyze` boundary for external packets. CLI outputs use exclusive creation, refuse existing files, and cannot alias each other or the input; choose new names for subsequent runs.

Required request fields:

| Field | Contract |
| --- | --- |
| `symbol` | One instrument per request. |
| `timeframe` | Explicit bar frequency. All periods count observations at this frequency. |
| `price_basis` | State raw or consistently corporate-action-adjusted OHLCV and relevant source assumptions. Do not combine adjusted close with raw O/H/L. |
| `price_unit`, `volume_unit` | Explicit units, e.g. `USD per share` and `shares`. Do not mix currencies or volume conventions within a request. |
| `timestamp_basis` | Exactly `bar_open` or `bar_close`; every decision uses the completed bar regardless of label basis. |
| `finalized_bars` | Exactly `true`; exclude still-forming candles. |
| `bars` | Nonempty list of objects with `timestamp`, positive `open/high/low/close`, nonnegative `volume`, optional explicit `session`. |

Dates use `YYYY-MM-DD`; intraday timestamps require ISO-8601 timezone offsets. Strictly increasing unique instants are required. Date-only and intraday timestamps cannot mix. Session labels must occur on all bars or none and must be contiguous; labels identify the exchange session, including overnight sessions where applicable. No session is inferred from UTC date. Zero-volume bars are allowed; missing/nonfinite OHLCV, booleans as numeric data, unknown request/parameter/bar fields, and malformed OHLC ranges are rejected. Exchange-calendar gaps are not inferred or filled. Verify data provenance and calendar completeness before analysis.

Optional fields:

- `parameters`: any subset of the defaults below. The complete effective configuration is returned, so defaults are inspectable. Freeze it in a comparison packet before participant runs.
- `vwap_anchor_index`: zero-based observed bar index. Anchored VWAP crosses session boundaries and is null before the anchor.
- `fibonacci`: `{ "start_index": 0, "end_index": 5, "direction": "up" }`. Up uses the first bar's low and second bar's high; down uses high then low. Endpoints must agree with direction. Levels become available only after the end bar closes. Do not apply a retrospectively selected swing to earlier trades.
- `volume_profile`: `{ "bins": 20, "start_index": 0, "end_index": 99 }`. Omitted start/end use the first/last supplied bar; bins must be 1–200. It is an as-of-window result, not a causal historical column.
- `depth_snapshot`: `{ "as_of": "2026-01-05T10:00:00-05:00", "bids": [{"price":99,"size":30}], "asks": [{"price":101,"size":10}] }`. Timestamp must have offset; compare matched depth ranges/counts. Duplicate prices, negative sizes, or locked/crossed quotes are rejected. This standalone snapshot is not automatically time-aligned with bars and is never used by replay.
- `replay`: either `signals` (one `0`, `1`, or null per bar) or `strategy: "close_above_sma"`; optional `initial_cash:10000`, `fee_bps:0`, `slippage_bps:0`. Effective costs and actual signals are returned. A supplied signal's causal construction is the caller's responsibility; the built-in strategy is causal by construction.

## Formulas and deterministic conventions

Indexing below is zero based. Early values are JSON null until the full required history exists. Numeric output uses IEEE-754 double precision without presentation rounding; compare like-for-like results at absolute tolerance `1e-10` for the golden fixture and relative tolerance `1e-10` for large-magnitude data. Display rounding must not feed back into calculations. Standalone scalar-series functions accept nulls and restart recursive seeds after them; the external OHLCV boundary rejects missing bars instead of inventing values.

| Indicator / parameter defaults | Formula and first available index |
| --- | --- |
| `sma_period:20`, `ema_period:20` | SMA is the arithmetic average of n closes. EMA uses alpha `2/(n+1)`, seeded by the first n-close SMA; index `n-1`. |
| `rsi_period:14` | Separate positive/negative close changes, Wilder averages (alpha `1/n`, n-change SMA seed), then `100-100/(1+gain/loss)`; index n. Positive gain/no loss gives 100; no gain/positive loss gives 0; both zero gives 50 by explicit neutral convention. |
| `macd_fast:12`, `macd_slow:26`, `macd_signal:9` | Fast EMA minus slow EMA; signal is SMA-seeded EMA of valid MACD values; histogram is line minus signal. Fast < slow. Line index `slow-1`; signal/histogram index `slow+signal-2`. |
| `bollinger_period:20`, `bollinger_multiplier:2` | SMA ± multiplier × population standard deviation of n closes; index `n-1`. |
| `atr_period:14` | TR=max(H-L, abs(H-prior close), abs(L-prior close)); first bar TR=H-L. Wilder average starts at `n-1`. |
| `adx_period:14` | Positive DM is upward high movement only if strictly greater than downward low movement and positive; negative DM is the inverse. Ties give both zero. Exclude first bar from DM/TR seeds. Wilder-smoothed DM/TR ×100 gives DI at index n. DX=100×abs(+DI−−DI)/(+DI+−DI), zero when both DI zero; n-DX Wilder ADX starts at `2n-1`. Zero smoothed TR gives both DI zero. |
| `stochastic_period:14`, `stochastic_smooth_k:3`, `stochastic_smooth_d:3` | Raw K=100×(close−lowest low)/(highest high−lowest low), then K and D are successive SMAs. Raw index `n-1`; K `n+k-2`; D `n+k+d-3`. Zero range gives null, not an invented direction. |
| Session and anchored VWAP | Cumulative HLC3×volume / cumulative volume. Session resets only on explicit label changes; absent labels make session VWAP unavailable. Zero cumulative volume gives null. This is a bar-volume approximation to transaction VWAP. |
| OBV | Start at 0; add/subtract current volume on rising/falling close; equal close adds zero. Starting absolute value is arbitrary; compare changes. |
| `ichimoku_conversion:9`, `ichimoku_base:26`, `ichimoku_span:52`, `ichimoku_displacement:26` | Each midpoint=(rolling highest high+lowest low)/2. A=(conversion+base)/2; B=span midpoint. `span_*_projected` is stored at calculation time, conceptually projected forward d bars. `cloud_*_now[t]` uses the calculation at t−d. `lag_comparison_close[t]` is close[t−d], not a future close shifted backward. No conventional historical Chikou backfill is emitted. |
| `support_resistance_lookback:20` | Previous n bars' minimum low/maximum high, excluding current bar; first at index n. These are trailing levels, not hindsight-confirmed pivots. |

Fibonacci retracement at ratio r is `end − r×(end−start)`, using r = 0, .236, .382, .5, .618, .786, 1. Extensions measured from start use `start+r×(end−start)` at 1.272, 1.618, 2.618. These are geometric annotations, not probability estimates.

Candlestick labels are exact geometry rules: doji body ≤10% range; hammer lower wick ≥2×body and upper wick ≤.25×body; inverted hammer swaps wicks; engulfing requires opposite-color bodies, inclusive body containment and a strictly larger current body. Zero-range candle is `flat`. No preceding trend or reversal outcome is inferred.

Volume profile spreads each bar's volume uniformly over its high-low range by bin overlap; zero-range bars allocate their whole volume to the containing bin. This conserves volume but is **not measured transaction volume at price**. Point of control uses the largest allocated bin, lower-price bin on a tie; all-zero volume has no point of control. No volume delta or buy/sell aggressor classification is inferred.

Snapshot depth imbalance is `(sum bid sizes − sum ask sizes)/(sum bid sizes + sum ask sizes)`, null for zero total size. It describes supplied resting depth only, not trade flow, queue priority, spoofing detection, or a complete market feed.

## Replay timing and limitations

Signals are long (`1`), flat (`0`), or retain previous target (null). A decision at close t can execute only at open t+1. Entry buys fractional shares with all available cash at `open×(1+slippage)` and pays fee on executed notional; exits sell at `open×(1−slippage)` and deduct fee. A long target does not rebalance an existing holding. The final target is unexecuted without another bar. Equity is marked at each close; open positions are not forcibly liquidated. Opening gaps are naturally included by next-open prices.

This helper has no shorting, leverage, stop/limit intrabar path model, borrow, taxes, dividends, liquidity constraint, spread/impact calibration, or walk-forward optimizer. Supply consistently adjusted bars for the intended economic-return interpretation. Use the existing strategy/risk validation workflow for those additional assumptions and out-of-sample evidence. An in-sample indicator replay is not a validated trading strategy.

## Golden fixture, implementation provenance and method sources

`examples/technical-golden.json` contains original synthetic input, selected hand-calculated expected results, and calculation steps. `tests/test_technical_toolkit.py` checks those values, every indicator's prefix invariance, scale invariance, session resets, zero denominators, no same-bar fills, accounting identities, malformed input, volume conservation and SVG escaping. `examples/technical-prompts.md` provides model-neutral task prompts.

All toolkit code, tests, synthetic fixtures, chart code, and text were written originally for this repository from mathematical definitions. No TradingView/Pine/TA-Lib/vendor implementation or sample source was copied, no trained weights or market datasets are bundled, and no new dependency is added. Existing repository license applies to these original files. Links below attribute method documentation; they are not a license grant for vendor code or a claim of exact vendor parity. Seed/flat-value/rounding differences are explicitly fixed above.

- Wilder RSI and smoothing: [TradingView RSI](https://www.tradingview.com/support/solutions/43000502338-relative-strength-index-rsi/).
- Wilder directional movement and ADX: [TradingView ADX](https://www.tradingview.com/support/solutions/43000589099-average-directional-index-adx/).
- Ichimoku projection convention: [TradingView Ichimoku Cloud](https://www.tradingview.com/support/solutions/43000589152-ichimoku-cloud/).
- Moving-average convergence/divergence: [TradingView MACD](https://www.tradingview.com/support/solutions/43000502344-moving-average-convergence-divergence-macd-indicator/).
- John Bollinger bands: [TradingView Bollinger Bands](https://www.tradingview.com/support/solutions/43000501840-bollinger-bands-bb/).
- Bar VWAP: [TradingView VWAP](https://www.tradingview.com/support/solutions/43000502018-volume-weighted-average-price-vwap/).
- Stochastic oscillator: [TradingView Stochastic](https://www.tradingview.com/support/solutions/43000502332-stochastic-stoch/).
