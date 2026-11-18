# Technical-analysis prompts

Use the same frozen packet, toolkit revision and numerical conventions across Codex, Muse and Claude. The packet must state units, source/adjustment basis, bar timestamp basis, finalized status, sessions and frequency. Do not silently replace unavailable observations or recompute with a vendor's different initialization convention. Report unknowns and warm-up nulls separately from bearish/neutral readings.

## Indicator review and chart

> Analyze the attached finalized OHLCV packet using the bundled technical toolkit. My intended holding period is 2–6 weeks. Compute SMA/EMA 20, RSI/ATR/ADX 14, MACD 12/26/9, Bollinger 20 with population standard deviation and multiplier 2, stochastic 14/3/3, and Ichimoku 9/26/52 displaced 26 bars. Return the effective parameters and latest non-null values with timestamps, plus an SVG price chart. Explain whether price, trend strength, momentum and volatility agree, but do not turn that agreement into a calibrated win probability. Identify incomplete warm-up and stale or inconsistent data. Keep output rounding separate from calculation precision.

## Session VWAP and explicit levels

> For these finalized 5-minute bars, compare price with session VWAP and anchored VWAP starting at index 24. The packet supplies the exchange-session labels. My holding period is the remainder of the current session. Use prior 20-bar support/resistance; calculate Fibonacci geometry only for my specified up swing from index 10 to index 28 and mark it unavailable before bar 28 closes. Summarize candlestick geometry and a 20-bin volume-profile approximation. Clearly distinguish bar-volume estimates from measured transaction volume at price and resting depth from executed order flow. Do not infer an order-book feed or trade placement.

## Reproduce a causal research replay

> Replay the bundled close-above-SMA rule on this frozen packet with SMA 20, initial cash 10,000 in the packet's price currency, 5 basis points commission per side and 10 basis points slippage per side. Decide at close and execute at the next open, long or flat with fractional shares. Show the first three decisions/fills, total fees, ending cash/shares, mark-to-market return, drawdown and unexecuted final signal. Do not force a final liquidation or treat the in-sample result as out-of-sample validation. The research horizon is the supplied six months; the position is held until the rule exits.

## Formula parity before interpretation

> Run `examples/technical-golden.json` using the bundled implementation and compare the listed expected rows at absolute tolerance 1e-10. Report input, implementation version, formula conventions, first available indicator indices, and any discrepancies before interpreting signals. Keep this fixture separate from fresh market evidence. Do not share another participant's answer or adjust the fixture to obtain agreement.

For prompts without a holding period, follow the skill's holding-period policy before tailoring a trade interpretation; indicator arithmetic can still be performed using the explicitly supplied bar frequency.
