# Optional local quantitative methods

These calculations run directly inside the skill through `scripts/portable_quant.py`.
There is no separate application, service, account, hosted endpoint or client.
Importing the script needs only the Python standard library. Calling a method
requires its optional locally installed numerical package. An unavailable package
produces `DEPENDENCY_UNAVAILABLE`; never replace that failure with invented output
or claim the model's own arithmetic came from the library.

The wrappers are original code using documented library APIs. No upstream
implementation has been copied. Package licenses and sources are linked below.
Any dependency installation is a separate environment action; the script never
installs packages or obtains market data.

Every document has exactly the method's listed fields plus `as_of` and `currency`.
`as_of` is a valid UTC ISO timestamp ending in `Z`, optionally with up to six
fractional-second digits. `currency` is three uppercase ASCII letters and labels
the supplied exercise; it does not convert currencies. Unknown fields, booleans
used as numbers, nonfinite values and duplicate CLI JSON keys are rejected.
Results record the exact Python version and relevant installed package versions.
Keep the original document, output and runtime versions when comparing models.
Different environments are an exploratory comparison, not proven independent
reproducibility. No numerical method here establishes profitability.

Direct CLI examples from the skill root:

```text
python scripts/portable_quant.py arima examples/portable-quant-arima.json
python scripts/portable_quant.py cointegration examples/portable-quant-cointegration.json
python scripts/portable_quant.py european examples/portable-quant-european.json
python scripts/portable_quant.py vader examples/portable-quant-vader.json
```

The same functions are available through the existing workbench as `portable.arima`,
`portable.cointegration`, `portable.european` and `portable.vader`. Pass the same
flat method document; do not remove its explicit conventions. Numerical failures
remain failures in the workbench. A missing optional dependency must not break
unrelated standard-library workflows.

## ARIMA

Additional exact fields:

| Field | Meaning |
|---|---|
| `values` | 30–20,000 finite, nonconstant training observations in chronological order |
| `order` | Explicit integer `[p,d,q]`, with p/q from 0–5 and d from 0–2 |
| `trend` | `n`, `c`, `t`, or `ct`; incompatible polynomial/differencing orders are rejected |
| `steps` | 1–3,650 future observation steps, not an inferred calendar horizon |
| `maxiter` | 1–1,000 optimizer iterations |
| `diagnostic_lags` | Ljung–Box lag, greater than p+q and at most floor(n/4) |
| `alpha` | Prediction-interval tail probability strictly between 0 and 1 |
| `input_basis` | Exactly `caller_declared_frozen_inputs` |
| `value_unit` | Explicit unit label, for example `USD/share` or `dimensionless log return` |
| `observation_frequency` | Explicit, nonempty spacing label, such as `one trading session` |

The sample must also contain at least 5(p+q+d+1) observations. The method uses
statsmodels state-space maximum likelihood, LBFGS, stationary/invertible ARMA
constraints, no concentrated scale, OPG covariance, stationary ARMA-state
initialization and approximate diffuse differenced-state variance 1,000,000.
There is no automatic order search, calendar generation, standardization,
resampling or missing-value imputation. Remaining internal numerical defaults
belong to the recorded statsmodels version.

Only a converged fit can return a forecast. Nonconvergence raises
`ARIMA_NOT_CONVERGED` with runtime/settings/warnings and `forecast_emitted: false`;
it does not calculate or return a usable forecast. Other outputs include fitted
parameters, AIC/BIC, likelihood, model-conditional prediction intervals and
residual mean/RMSE/Ljung–Box diagnostics. Initial likelihood-burn observations
are excluded from residual diagnostics. This is an in-sample fit, not a held-out
accuracy score. Prediction intervals do not capture every source of model or
parameter uncertainty.

Raw arrays have no timestamp or revision proof. Build them from observations
eligible at `as_of`, retain that mapping, and disclose gaps. The skill's
`point_in_time_data.py` snapshot workflow (`data.asof_snapshot`) can help select supplied observations; it
does not authenticate a provider's availability claims. See its executable
example and reference for that separate schema.

Prompt: “Using these frozen daily log returns available by the declared as-of
time, fit ARIMA(1,0,0) with a constant, 200 optimizer iterations, diagnostic lag
8 and alpha 0.05. Forecast four observation steps only if the fit converges.
Report units, residual diagnostics, runtime versions and the lack of held-out
validation.”

## Engle–Granger cointegration

Additional exact fields: `y0`, `y1`, `trend`, `maxlag`, `autolag`, `significance`,
`input_basis`, `y0_unit`, `y1_unit`, `observation_frequency`.

Both series need 40–20,000 finite, nonconstant aligned observations of equal
length. `trend` is `c`, `ct`, or `ctt`; the deterministic time index starts at 1.
`maxlag` is an explicit integer from 0 through min(100, floor(n/2)-4).
`autolag` is explicitly null (fixed maximum lag), `aic`, `bic`, or `t-stat`.
`significance` is strictly between 0 and 1. Units and frequency must be nonempty
labels; `input_basis` is exactly `caller_declared_frozen_inputs`.

The augmented Engle–Granger test has null hypothesis **no cointegration**.
It assumes both series are I(1); this operation does not prove that assumption.
The normalization is `y0 - fitted(y1, deterministic terms)`, so y0 has coefficient
+1. Reversing the pair defines a different finite-sample regression. The reported
coefficients describe that normalization, alongside the test statistic, p-value
and 1%/5%/10% critical values. Near-perfect collinearity yielding a nonfinite test
statistic is rejected rather than being presented as decisive evidence.

This is one prespecified pair. Searching many pairs requires separately retained
trial records and multiple-testing controls. No borrow availability, dividends,
two-leg costs, execution or strategy profitability is established.

Prompt: “For these two frozen, aligned series, treat y0 as dependent and y1 as
regressor. Use Engle–Granger with a constant, maxlag 3, no autolag and significance
0.05. State the I(1) assumption, directional normalization and multiple-pair
testing limitation. Do not call a rejection a profitable trading strategy.”

## European vanilla option

Additional exact fields: `spot`, `strike`, `rate`, `dividend_yield`, `volatility`,
`evaluation_date`, `maturity_date`, `option_type`, `day_count`.

Spot and strike are positive. Annualized volatility is in (0,10]; continuous
annual interest and dividend yields are in [-1,1]. Dates are exact `YYYY-MM-DD`
within QuantLib's supported 1901–2199 range. The evaluation date must equal the
UTC date of `as_of`, and maturity must be later. `option_type` is `call` or `put`;
`day_count` is exactly `Actual365Fixed`.

QuantLib's analytic European engine uses flat continuous yield curves and constant
volatility. NPV is per underlying unit, without a contract multiplier. Delta and
gamma are spot sensitivities; vega, rho and dividend rho are per 1.0 absolute
change, not per percentage point. Divide those three values by 100 for a one
percentage-point interpretation. Theta is per year. The calculation serializes
its own QuantLib settings changes and restores settings on success or failure.

This does not calibrate a surface, support American exercise, model discrete
dividends or include transaction costs. Intraday expiry timing is not modeled.

Prompt: “Price the supplied European call and otherwise identical put using
flat continuous rates, dividend yield and volatility with Actual365Fixed.
Check put-call parity independently, state per-unit and Greek conventions,
and retain the exact QuantLib version.”

## VADER lexical sentiment

Additional exact field: `texts`, an array of 1–1,000 strings. Each string has
1–10,000 characters; the total limit is 1,000,000 characters. Output preserves
the package's original `neg`, `neu`, `pos`, and `compound` scores in input order,
with no rescaling or invented financial interpretation.

VADER is an English lexical baseline. It is not a calibrated financial model,
does not assign sentiment to particular entities/aspects, and does not verify
publication times. The existing sentiment workflow remains the route for source
selection, attribution, temporal controls and assessment.

Prompt: “Score these supplied English snippets using VADER without modifying
its scores. Keep input order, record the package version, and distinguish the
lexical tone from any claim about financial performance or investment value.”

## Sources and licenses

- statsmodels: [ARIMA API](https://www.statsmodels.org/stable/generated/statsmodels.tsa.arima.model.ARIMA.html),
  [cointegration API](https://www.statsmodels.org/stable/generated/statsmodels.tsa.stattools.coint.html),
  [BSD license](https://github.com/statsmodels/statsmodels/blob/main/LICENSE.txt).
- QuantLib: [analytic European engine API](https://github.com/lballabio/QuantLib/blob/master/ql/pricingengines/vanilla/analyticeuropeanengine.hpp),
  [modified BSD license](https://www.quantlib.org/license.shtml).
- VADER: [project, algorithm references and MIT license](https://github.com/cjhutto/vaderSentiment).

Example files are fictional input-only exercises. They contain no other model's
accepted answer and must not be mistaken for market history or research evidence.
