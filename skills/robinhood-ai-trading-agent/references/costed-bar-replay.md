# Costed bar replay

Original standard-library Python research calculation. Run `python scripts/costed_bar_replay.py examples/costed-bar-replay.json`, or use workbench operation `backtest.costed_bars` with `document` containing the same JSON. No package installation, external engine, service or broker is used. The separate `paper_exchange.py` event ledger remains unchanged.

The closed input schema is the supplied example: integer `schema_version: 1`, UTC `as_of`, three-uppercase-letter `currency`, `asset_class: equity|etf|spot_crypto`, `initial_cash`, `quantity_step`, `max_participation`, `time_in_force: carry|cancel`, `costs`, `bars`, `signals`. Currency format is checked; actual ISO currency membership is not certified. Every amount is a nonnegative decimal string, at most 36 digits and 18 decimal places. Prices, order quantities and quantity step must be positive; participation is in `(0,1]`. Signals must be step-aligned. Unknown or missing fields are errors.

Each bar explicitly separates `open_at`, `close_at`, and full-bar `available_at`. UTC timestamps end in Z and allow up to six fractional digits. Bars must be chronological and nonoverlapping, with `open_at < close_at <= available_at <= as_of`. Signals reference unique ascending bar-close timestamps and cannot be available before their full bar or after `as_of`. Open quotes are assumed observable at their open timestamp. Exchange sessions are not inferred or validated; example dates are fictional observations.

Signals can fill only at a bar open **strictly after both their source close and their availability**. Arrival exactly at an open waits for a later open. At shared timestamps, completed-bar availability is processed before signal arrivals and opening attempts. A newly available signal replaces any unfilled pending remainder. Replacements follow arrival time; an older source signal arriving late can replace a newer source signal. Signals with equal arrival times follow source timestamp order.

Capacity is the latest already available completed bar's volume multiplied by participation, rounded down to quantity step. It never uses the execution bar's future volume. This is a prior-volume proxy, not evidence of actual opening liquidity, queues or market impact. A delayed older bar cannot overwrite a newer volume or mark observation.

Buy price is `open * (1 + (spread_bps/2 + slippage_bps)/10000)`; sell price uses subtraction. Fee per nonzero fill is `quantity * price * fee_bps/10000 + fixed_fee`. Both aggregate price impact and the fee rate must be below 100%. Buys are reduced to affordable step-aligned quantities including fees; sells cannot exceed holdings or make cash negative. `carry` retains remainder for later opens; `cancel` cancels remainder after the first eligible attempt, including zero-volume or unaffordable attempts. No final liquidation is invented.

Cash, prices and fees use the single stated currency with immediate settlement. Positions start at zero and remain long-only. Arithmetic uses a locally fixed 120-digit HALF_EVEN Decimal context with explicit exponent limits and traps; quantities round down to step. Currency-minor-unit and price-tick rounding, FX conversion, interest, taxes, corporate actions, margin, short borrow and derivatives are not represented. An available mark values the current holdings at the latest observed close; the output supplies both observation and price times.

Output preserves modeled fills, cancellations, marks, fees, cash, position, equity and final pending quantity, with `production_qualified: false`. The sample independently gives 10 shares bought at 11.011 and 5 at 12.012, total fees 0.117017, cash **829.712983**, position **15**, close-mark equity **1017.212983** and **5 shares pending**. These are fictional accounting checks, not strategy-performance evidence.

Example prompts:

- "Replay the attached frozen bars and signals through `backtest.costed_bars`. Use USD, a three-bar horizon, 10% prior-volume participation, the supplied costs and carry policy. Show partial fills and pending quantity; distinguish modeled opening liquidity from observed liquidity."
- "Compare carry versus cancel for this same frozen document. Keep all prices, costs and availability timestamps identical. Explain how the first eligible opening attempt affects the unfilled remainder."
- "Audit whether a signal arriving exactly at the next open can trade at that open. Run the calculation, show the actual fill timestamp and preserve any unfilled position at the cutoff."
- "For these spot-crypto bars, use the supplied fractional quantity step and quote currency. Report fee-inclusive cash constraints and mark-to-market exposure. Do not add exchange-calendar, funding or borrow assumptions."

Implementation is original code; no third-party source was copied. The 18 focused tests cover arithmetic, causal timing, cutoff enforcement, delayed observations, partial fills, replacement/cancellation, cash and long-only invariants, fractional quantities, strict JSON and hostile Decimal contexts.
