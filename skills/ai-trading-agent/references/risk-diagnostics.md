# Portable risk and allocation diagnostics

These operations consume retained, source-bound inputs. They do not download
data, produce a strategy backtest, predict price direction, certify a funding goal
or impose an execution gate. Retain original inputs, outputs and code hashes.
Examples and fixtures are fictional arithmetic, not market validation.

## Current-weight empirical tail distribution

`risk_diagnostics.empirical_tail(document)` applies the same supplied current
weights to each aligned historical return vector solely to estimate a shock
distribution. It never chains returns into an investment curve or pretends that
today's positions were known historically.

Required fields:

- Ordered unique `symbols`; `weights` with exactly those keys, nonnegative decimal
  fractions summing to at most one.
- `currency`, positive `notional`, `weight_basis: fraction_of_supplied_notional`,
  and explicit `period_label`, for example `one_trading_day`.
- Timezone-aware `as_of`; at least three `observations`, each with increasing
  unique `timestamp` no later than `as_of` and complete `returns` for all symbols.
- `return_basis: simple_total_return_decimal`. Returns below -1 are invalid.
  No missing values are filled or dropped. Supplied alignment does not prove that
  the sample contains every expected exchange session.
- Unique `confidence_levels` between 0.5 and 0.99999, inclusive.

Optional `minimum_effective_tail_observations` defaults to 20. This is a reporting
warning threshold, not an established statistical minimum. Tail mass is exactly
N times (1-confidence); its boundary order statistic receives fractional weight.
For four losses of 0.4, 0.2, -0.1, -0.2 at 62.5% confidence, VaR is 0.2 and
expected shortfall is (0.4+0.5*0.2)/1.5. Monetary results use the supplied notional,
not an inferred equity-only denominator. Unallocated cash has zero modeled shock.

Results retain fractional and monetary VaR/expected shortfall, effective tail
sample size and sparse-sample warnings. Signed loss may be negative when even the
estimated adverse tail is a gain. No multi-period tail scaling, maximum-loss
guarantee or calibrated future probability is generated.

## Conditional portfolio variance paths

`risk_diagnostics.conditional_portfolio(document)` combines marginal variance
paths with a fixed correlation matrix. This is an explicitly conditional
approximation, not a fitted multivariate GARCH model.

Use the same symbols, weights, currency, notional, period label, denominator and
`as_of` contract as above. Also supply:

- Timezone-aware `forecast_origin` and `correlation_as_of`: correlation must be
  available no later than the forecast origin, itself no later than `as_of`.
- `correlation_ids` exactly equal to `symbols`; a symmetric positive semidefinite
  `correlation` matrix with unit diagonal.
- `variance_paths`: one nonnegative, equal-length array for each symbol;
  `variance_units: decimal_return_squared_per_period`.
- `variance_basis` and `correlation_return_basis`, each either
  `log_return_decimal` or `simple_total_return_decimal`. Mixing them requires
  `cross_basis_approximation_acknowledged: true` and is labeled in the result.
- `model_flags`: an explicit list for every symbol, including an empty list when
  no flags are supplied. Flags survive aggregation; missing fields are rejected.
- Positive `periods_per_year` and unique positive integer `horizons`, each within
  every supplied variance path's length.

For each period the calculation is w'D R D w, with D holding marginal standard
deviations. Summing period variances assumes zero cross-period innovation
covariance. Cumulative sigma, average-period sigma and annualized average sigma
are different fields. Log-return variance with fixed monetary weights is a local
linear approximation, particularly weak for large moves. Sigma is not a loss cap
or confidence band. Model diagnostic failures are not repaired by taking the
maximum of models or averaging forecasts; such an envelope is a separate scenario.

## Numerically robust constrained allocation

`quant_portfolio.construct(document)` preserves its input contract. For long-only,
zero-cost `minimum_risk` cases, it additionally solves an independent linear
program against the convex objective's gradient. A sufficiently small directional
gap certifies the minimum of the supplied covariance objective within numerical
tolerance. This does not certify covariance accuracy or future performance.
Variance/tracking caps are omitted from the linear witness's feasible set, which
enlarges it. A zero gap remains sufficient; a positive gap means certification
was not established, not necessarily that the solution is wrong. Other
objectives/cost structures are explicitly outside this certificate.

If SLSQP fails or reports success without this certificate, the eligible case
retries an equivalent reduced long-only formulation. Constraints implied by a
fixed net target are removed algebraically. No cash, stock, group or stress limit
is relaxed. Original actual-weight constraints, capacity and bounds are checked
again with the existing 1e-7 feasibility tolerance. Solver attempts and certificate
states remain visible. Infeasibility emits no weights.

Diagnostics show covariance conditioning, variance contributions, constraint
slacks and binding stock/group/cash/turnover limits. Singular covariance is
disclosed rather than silently repaired. Active caps expose dependence on
judgment-based risk budgets. Low estimated variance does not establish a
recession-proof portfolio or a likely spending-goal return.

## Prespecified covariance and cap sensitivity

`quant_portfolio.sensitivity(document)` takes `base` (a construct document) and
one to 20 cases across optional `covariance_scenarios` and `constraint_scenarios`.
Case IDs must be unique across both lists. Each covariance case supplies `id`, `covariance`,
exact `covariance_ids`, matching `horizon_id`, and `estimated_at`. Other
constraints and assumptions remain unchanged. Each case retains its result or
infeasibility, gross weight change from baseline and risk of the baseline weights
under that covariance. `selected_case` is always null. Freeze cases before
inspection; sensitivity analysis is not another opportunity to search for a
preferred historical portfolio.

Constraint cases have an `id`, optional `constraint_overrides`, and optional
`asset_max_weights` keyed by existing asset ID. At least one override is required.
Only `gross_cap`, `gross_turnover_cap`, `cash_floor`, `issuer_gross_cap`,
`group_gross_caps`, `volatility_cap`, and `tracking_volatility_cap` are permitted
in `constraint_overrides`. Group overrides merge explicitly named caps. Asset
maximum weights are bounded to [0,1]; objectives, net targets, costs, expected
returns and other base fields cannot be replaced. Normal construct validation
still applies. The original request remains the baseline, unchanged.

Each `constraint_cases` result retains changed field paths and before/after
values, weights or infeasibility, and a hypothesis-change flag. Changed cap
hypotheses require a distinct disclosed registry attempt for research selection
or performance claims; this advisory does not impose trade approval or register
attempts automatically. The helper does not choose a winner. Invalid request
schemas fail validation rather than being mistaken for feasible cases.

All emitted risk aggregates must be finite; finite inputs whose arithmetic
overflows are rejected explicitly, including notional-scaled tail losses and
cumulative variance paths.

Fixtures independently check fractional-tail identities, covariance units,
warning preservation, future-date rejection, inverse-variance weights,
redundant-boundary recovery and genuine infeasibility. Passing these tests proves
those behaviors, not investment performance.
