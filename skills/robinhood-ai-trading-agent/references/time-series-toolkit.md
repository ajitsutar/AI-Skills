# Bounded time-series research tools

`scripts/time_series_toolkit.py` supplies three independent offline operations: seeded GBM scenarios, causal discrete trend derivatives, and a fixed-pair train-only OLS spread normalization. It does not place trades, select a profitable strategy, estimate ARMA, test cointegration, or qualify a production deployment. GARCH volatility remains in its existing separate module with its declared zero-mean convention.

## Contract and invocation

```text
python scripts/time_series_toolkit.py examples/time-series-gbm-input.json
python scripts/time_series_toolkit.py examples/time-series-trend-input.json --output new-trend-result.json
python scripts/time_series_toolkit.py examples/time-series-pair-input.json
```

The Python API is `run(document)`; `OPERATIONS = {'run': run}` supports wrapper discovery. Exact envelope: `{"schema_version":1,"operation":"gbm|trend|pair_ols","inputs":{...}}`. The operation string must be one of those three individual names. The tables below enumerate **all required keys**. There are no optional/hidden input defaults, no automatic currency conversion, no downloaded data or code, and no model installation. Unknown/missing keys and unsupported conventions fail. The CLI rejects duplicate JSON keys at every nesting level, creates output files exclusively, rejects input aliases and refuses to replace existing evidence. Callers of the Python API must reject duplicates when decoding their own JSON before passing a dictionary. Results identify their input SHA-256, method version and execution/production flags. Preserve the input and source records alongside the result; a hash is not source authentication.

All timestamps must use `YYYY-MM-DDTHH:MM:SS[.ffffff]Z` with a valid calendar date/time; only UTC Z and at most six fractional-second digits are accepted. Date-only, local/offset times, ISO week dates and leap seconds are rejected. Observed rows must be strictly increasing and unique in observation time. Each row has `timestamp <= available_at <= as_of`; training rows must have been available by the training cutoff. Missing/nonfinite/bool/string numeric values are rejected rather than filled or silently converted. Signed values are permitted for trend/pair inputs, including negative-price observations; GBM strictly requires positive prices. Numeric calculation uses Python binary64 without presentation rounding; compare numerical results with declared tolerances, and retain the runtime/version for reproducibility.

## GBM scenarios

Use `operation: "gbm"`. All these keys are required:

| Input | Convention |
|---|---|
| `symbol`, `price_unit`, `price_basis` | Nonempty explicit labels identifying what the supplied initial price represents. |
| `initial_price` | Strictly positive starting level in `price_unit`; negative-price futures are incompatible. |
| `parameters_available_at`, `start_at`, `as_of` | Parameters must be available by `as_of`; scenario start must equal `as_of`. Future generated paths are hypothetical, not future observations. |
| `mu`, `sigma` | Arithmetic price-process drift per year and volatility per square-root year, decimal units; `sigma >= 0`. `mu` is not the expected log-return drift. No estimation/calibration is performed. |
| `horizon_years`, `steps`, `paths` | Positive horizon; integer step/path counts each 1 through 100,000, at most 1,000,000 output path cells including initial values. |
| `seed` | Integer 0 through 2^63-1. Isolated RNG; no ambient random state is read or changed. |
| `year_basis` | Exactly `ACT_365_FIXED_SECONDS`: one model year is 365*86400 elapsed seconds, not trading sessions. End timestamp derives from this basis. |
| `distribution` | Exactly `independent_standard_normal_log_increments`. One asset with independent temporal Gaussian innovations; no jumps or cross-asset dependence. |
| `measure` | `real_world_scenario` or `risk_neutral`. This is an assumption label, not evidence of calibration. |
| `risk_free_rate`, `dividend_yield` | Both explicitly null for real-world scenarios. For risk-neutral scenarios both must be numbers (nonnegative dividend yield) and `mu = risk_free_rate - dividend_yield` within 1e-12 absolute/relative tolerance; continuous annual rates and continuous proportional yield. |

For `dt = horizon_years / steps`, each path starts with `S0` and uses

```text
S_next = S * exp((mu - sigma^2 / 2) * dt + sigma * sqrt(dt) * Z)
E[S_T] = S0 * exp(mu * T)
Var[S_T] = S0^2 * exp(2 * mu * T) * (exp(sigma^2 * T) - 1)
```

This is the exact GBM interval distribution, not Euler price stepping. `Z` uses an original uncached Box-Muller transform: two successive `random.Random(seed).random()` values `r1,r2`, `U=1-r1`, `Z=sqrt(-2*log(U))*cos(2*pi*r2)`. Draw ordering is path-major; every step consumes two draws even if sigma is zero. Increasing only the path count preserves earlier paths. Changing the grid changes the random discretization; grids are not coupled Brownian paths. The output includes every path, model-year offsets, terminal mean/variance and sample mean, plus Python version. Fixed seed and method/runtime make reruns reproducible; different platforms' floating-point transcendentals may differ at rounding level. This RNG is not cryptographic.

The continuous-yield risk-neutral path is an ex-dividend price model; it does not simulate reinvested dividend cash. No jump/default/bankruptcy/negative-price model, drift confidence interval, empirical probability estimate or trading recommendation follows from these paths. Nonfinite calculations and underflow to zero in path prices, terminal expectation or theoretically nonzero terminal variance are rejected; zero terminal variance is valid only when sigma is zero. Intermediate floating-point overflow/underflow can cause rejection even when an algebraically rearranged calculation could remain representable. Very short horizons below datetime microsecond resolution can have an end label rounded to that resolution; numeric model-year offsets retain the requested time grid.

**Golden example:** `time-series-gbm-input.json` has S0=100, mu=sigma=0, horizon=1, steps=2, paths=3; all nine prices are 100, terminal expectation 100 and variance zero. Independently, sigma=0 and mu=ln(2) imply 100, 100*sqrt(2), 200. Tests also compare 50,000 stochastic terminal samples with analytic moments under a specified seed.

## Causal velocity and acceleration estimates

Use `operation: "trend"` with required keys `symbol`, `value_unit`, `price_basis`, `time_unit`, `method`, `as_of`, `rows`.

- `time_unit` is exactly `second`, `hour` or `day`; day means 86400 elapsed seconds, not market sessions.
- `method` is exactly `backward_secant_midpoint_acceleration`.
- Each nonempty row is exactly `{timestamp, available_at, value}`. Price basis is supplied and must be consistent; no split adjustment is inferred.
- At observation i, `v_i = (p_i - p_(i-1)) / (t_i - t_(i-1))`. Velocity is the slope of the last interval, conceptually centered at that interval's midpoint; it is attached to the current timestamp because that is when the interval ends.
- For i>=2, `a_i = (v_i-v_(i-1)) / ((t_i-t_(i-2))/2)`. The denominator is the elapsed time between the two interval midpoints. It is not merely the last irregular interval length.
- First velocity and first two accelerations are null warmup. Each output's availability is the latest availability of observations contributing to it. No future observation or centered smoothing is used.

Units are `value_unit/time_unit` and `value_unit/time_unit^2`. These are discrete estimates, not the exact instantaneous derivatives of an unknown price process. Sparse/noisy observations can yield unstable estimates. A price discontinuity from a corporate action requires an appropriate supplied price basis. Appending future rows cannot change prior numerical outputs.

**Golden irregular-grid example:** elapsed days 0,1,3 with values 0,1,9 yield velocities null,1,4 and accelerations null,null,2. A wrong denominator using only the final interval would return 1.5 instead of 2. Time-unit conversion to hours divides velocity by 24 and acceleration by 24^2.

## Fixed-pair OLS spread normalization

Use `operation: "pair_ols"`. Required keys are `x_symbol`, `y_symbol`, `x_unit`, `y_unit`, `price_basis`, `train_cutoff`, `as_of`, `standard_deviation`, `minimum_x_variance`, `minimum_spread_std`, `train_rows`, `test_rows`.

- X/Y symbols must differ; units and price basis are explicit labels. Rows represent caller-aligned simultaneous observations; no inner joins, currency conversion or survivorship correction occur.
- `train_rows` has at least three rows and `test_rows` at least one, each exactly `{timestamp, available_at, x, y}`. All training values must be available by `train_cutoff <= as_of`; every test observation is strictly after the training cutoff and available by `as_of`.
- Both minimum thresholds are required positive numbers: `minimum_x_variance` in x-unit squared, `minimum_spread_std` in y-unit. They are caller-selected numerical conditioning policies, not inferred statistical significance levels.
- `standard_deviation` must equal `population_training_residual`; no sample/population ambiguity or holdout refitting.

Fit the intercept OLS model `y = alpha + beta*x + residual` only on the training rows:

```text
beta = sum((x-x_mean)*(y-y_mean)) / sum((x-x_mean)^2)
alpha = y_mean - beta*x_mean
spread = (y-y_mean) - beta*(x-x_mean)
z = (spread - training_residual_mean) / training_residual_population_std
```

Centered arithmetic reduces cancellation. The denominator variance uses divisor n. The training residual standard deviation also uses divisor n, explicitly a normalization convention rather than an unbiased regression error estimator. The frozen intercept, slope, residual mean and scale are applied unchanged to each test row. Exact or near-zero residual spread, insufficient x variation, future training information, invalid chronology or nonfinite arithmetic fail rather than produce fabricated zero z-scores. Alpha/spread are in y-units, beta in y-unit/x-unit; z is dimensionless. Appending or changing test rows cannot change the fitted model or earlier test outputs.

**Golden example:** training x=[1,2,3], y=[3,3,6] gives alpha=1, beta=1.5, residuals=[0.5,-1,0.5], residual mean=0 and population std=sqrt(0.5). Test x=4,y=8 gives spread=1 and z=sqrt(2). Translating every y by 100 changes only the intercept, not residuals/z-scores.

This is not a cointegration/stationarity test, an estimated probability, selected pair, causal economic relationship, trading strategy, or validated arbitrage. No entry/exit rule, short borrow, margin, dividends, two-leg fill, costs or out-of-sample profit test is performed. A large z-score can reflect a structural break. Retain every chosen pair and failed trial before any later strategy validation.

## Example prompts

1. "Run the supplied time-series GBM packet unchanged. Explain mu versus expected log-return drift, quote the measure/year basis, and compare sample terminal mean with the analytic expectation. Do not treat scenarios as a price target or change the seed after seeing results."
2. "Compute causal trend velocity and acceleration from the supplied frozen irregular observations. Use the declared elapsed-time unit and price basis, show warmup nulls and availability, and explain why the acceleration denominator is the distance between interval midpoints."
3. "Fit the supplied X/Y OLS model using only rows available by the training cutoff, freeze it, and apply its residual z-score to the supplied test rows. Report thresholds and units. Do not call the result cointegration, predictive arbitrage, or a trade recommendation."
4. "Review whether this dataset can support ARMA forecasting. The current tool does not implement ARMA; state the missing fixed order, mean convention, stationary/invertible fit, residual diagnostics and held-out forecast evaluation, without substituting an unrelated regression or silently installing a dependency."

All numerical selected expectations are retained in `examples/time-series-golden.json`. The separate input-only examples contain no accepted model answers.

## Deferred ARMA and provenance

ARMA is intentionally **not implemented** here. A robust conditional least-squares estimator needs declared initialization/burn-in and intercept conventions, stationary/invertible parameterization or root rejection, convergence and identifiability checks, residual diagnostics, separate held-out forecasts, order-selection trial retention and meaningful numerical reference tests. A simplistic optimizer success flag would not provide those guarantees. This release does not present the fixed-pair OLS operation as ARMA, and does not change existing GARCH behavior.

All code in this module and its tests was written originally from mathematical definitions. No vendor/sample source code or model weights were copied; no dependency or code asset was added. Python's existing standard library supplies arithmetic, RNG and JSON. Method sources reviewed:

- [MIT 18.642 stochastic-calculus lecture](https://ocw.mit.edu/courses/18-642-topics-in-mathematics-with-applications-in-finance-fall-2024/mit18_642_f24_lec19_1.pdf): Brownian motion and lognormal price-process mathematics; formulas implemented independently.
- [Python random reproducibility](https://docs.python.org/3/library/random.html#notes-on-reproducibility): isolated generator behavior and reproducible `random()` sequence; no source copied.
- [statsmodels cointegration documentation](https://www.statsmodels.org/stable/generated/statsmodels.tsa.stattools.coint.html): distinguishes cointegration testing from the supplied OLS descriptive component; no cointegration implementation is claimed.
- [statsmodels ARIMA documentation](https://www.statsmodels.org/stable/generated/statsmodels.tsa.arima.model.ARIMA.html): ARMA/ARIMA and stationarity/invertibility conventions informing the explicit deferral; no library installed or code copied.

The fixed-pair OLS and backward finite-difference equations above fully specify the original elementary calculations; the references do not grant permission to copy unrelated code or use a model/data asset without its own license check.
