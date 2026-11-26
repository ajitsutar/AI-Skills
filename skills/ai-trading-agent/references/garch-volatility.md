# Volatility helper: corrected behavior and limits

This is the built-in GARCH research specification. The main SKILL.md
states when to assess it and how to report computation versus a skipped overlay.
Load this reference when a shortlist/risk-sizing workflow reaches that step.

If this file or scripts/garch_volatility.py is unavailable in an upload, report a
missing package component. Do not reinterpret the missing upload as evidence that
GARCH is not part of the skill. Preserve a clear distinction between the bundled
helper and any separately verified alternative implementation.

GARCH forecasts conditional variance, not price direction or profitability.
Estimation/filtering/forecasting use arch 8.0.0 with its installed numerical dependencies.
See [dependency notices](../THIRD-PARTY-NOTICES.md). The helper assumes zero
conditional mean. Gaussian innovations remain the default; `--distribution t`
explicitly requests standardized Student-t innovations. Percent log returns
improve numerical scale. Do not label these variants the same model.

## Interpretation of supplied results

A retained volatility result can be interpreted without a price CSV or optional
model runtime. Attribute its symbol, dates, parameters, fit/holdout diagnostics
and eligibility flags to the supplied historical artifact. Comparing its supplied
scalar values is a new calculation, not a new model fit, price audit, raw-return
realized estimate or QLIKE replay. Invoke a fitter or price-history baseline only
when the required inputs are available and that calculation serves the request.
Keep missing inputs explicit; do not substitute another example history.

For account amounts, follow the [allocation basis](portfolio-management.md#allocation-and-rebalance).
When an allocation calculation is relevant and complete compatible inputs are
available, `portfolio_manager.py` returns `account_basis` and
`account_basis_summary` for inclusive equity, cash floor, targets and proposed
debits. Interpreting a historical volatility result alone does not require new
purchase proposals. Independently derived amounts still need their original
denominators and source currency scope. If the record does not fit the native
schema or execution is unavailable, disclose that limitation; do not call scratch
arithmetic a native planner result.

An amount's currency is unspecified when its applicable source does not establish
it. Use account currency units in prose and neutral amount names in structured
results; do not append `USD` or `_usd` to unknown-currency amounts. This also
applies to conditional sigma-scaled and stress amounts. Preserve an explicitly
supplied currency only within its actual source scope. A model symbol, unrelated
source currency, numerical coincidence or legacy `dollar_budget` field does not
supply account currency. State the selected amount base and assumed mapping for
any illustration; scaling an unrelated series does not establish asset or
portfolio risk.

Any stress scenario must be a clearly stated supplied or illustrative assumption
appropriate to the request. This route adds no required shock magnitude or
portfolio scenario. Scalar comparisons, regime labels and eligibility flags
remain advisory; they neither grant nor deny execution permission. These reporting
instructions do not verify arbitrary authored prose.

## Portable elementary baselines

When reporting constant-variance or EWMA benchmarks, use the bundled
`scripts/volatility_baselines.py`. It runs with the Python standard library and
the bundled price-audit helper; it does not import the optional GARCH runtime.

```text
python -B scripts/volatility_baselines.py prices.csv --data-audit prices.audit.json
```

Defaults match the adapter: 250 minimum training returns, 40 holdout returns,
EWMA decay0.94 and252 periods/year. The CSV and audit remain unchanged. Explicit
options are `--min-observations`, `--validation-test`, `--ewma-decay`,
`--periods-per-year`, `--close-column` and `--timestamp-column`.

Both baselines use percentage log returns. The constant variance is training
sample variance with ddof1, floored at1e-8. EWMA starts at that value, processes
**every training return**, then predicts each holdout variance before updating
with its target return. Starting the first holdout directly at sample variance
is a different benchmark. The helper exposes initialization, warm-up count,
units, all predictions and QLIKE; its shared recursion preserves the native
adapter's calculation. Standard-library and numerical-library reductions can
differ at floating-point precision.

The result is `BASELINES_ONLY_NO_GARCH_FIT`. One-step predictions describe the
historical holdout; they are not a forward GARCH forecast. If `arch` or another
native dependency is absent, preserve that actual limitation and leave native
convergence, parameters, GARCH QLIKE and forecast unavailable. Elementary
benchmarks do not replace the requested fit or establish sizing permission.
If deliberately using another initialization or return convention, name the
difference instead of calling it the bundled baseline. Audit declarations
remain caller supplied and do not authenticate prices or exchange sessions.

## Correct recursion

For GARCH, the first forecast uses the last observed squared return. Later forecasts
use omega + (alpha + beta) times the prior forecast variance. Setting the future
return to zero does not mean its expected square is zero.

GJR uses alpha + gamma/2 + beta in subsequent steps under the symmetric Gaussian
assumption. EGARCH's first step must include the last standardized innovation.
Multi-step EGARCH requires simulation/integration; this helper explicitly rejects
it rather than reporting an incorrect analytic estimate. Auto mode excludes EGARCH
when horizon exceeds one.

These choices follow the conditional-variance identities described in the
[arch forecasting documentation](https://arch.readthedocs.io/en/latest/univariate/forecasting.html).

## Input and validation

CSV requires timestamp (ISO timestamp with timezone) and close columns. Prices must
be finite and positive; times must be increasing and unique. Synthetic/interpolated
rows marked synthetic=true are rejected. The supplied fictional CSV is explicitly a
test fixture, not market data.

Defaults require 250 training returns plus 40 holdout returns (291 prices).
The helper uses all remaining returns for training, so training count is total
price rows minus one minus the holdout count. Report those actual counts. Request
enough daily history rather than assuming a one-year request is sufficient.
Do not drop bad prices and join returns across the resulting gaps. Upstream data
auditing must still verify expected session frequency, corporate actions and the
appropriate adjusted/unadjusted price basis. Timestamp ordering alone cannot
establish data quality.

The holdout fits parameters on the training prefix only, predicts one step,
observes that return, then updates state. It compares QLIKE/MSE with a fixed
training-variance benchmark. Failed fits or insufficient holdout data cannot
produce a successful forecast. Forecasts and JSON must remain finite.

Auto selects among converged models using holdout QLIKE. That holdout is therefore
a model-selection sample, not a clean final test. eligible_as_sizing_input requires
both beating this elementary variance baseline and a complete market-data audit
declaration. Fictional/unaudited data always produce false. Even true does not
authenticate evidence, authorize trading, establish significance or validate the
model for the proposed holding horizon.

## Corporate actions and exact input audit

Use `--data-audit path/to/audit.json` with
[price-audit.example.json](../templates/price-audit.example.json). Its unfilled
fields intentionally cannot pass as a completed audit. The helper has no vendor
connector, automatic repair or independent verification of declared evidence.

- Bind the exact CSV SHA-256, close/timestamp columns and periods_per_year. Record
  security ID, provider, provider_field, extraction options/version, interval,
  retrieval time, adjustment basis and notes.
- Audit splits/reverse splits, dividends/special distributions, spinoffs, mergers
  and symbol history using provider and issuer/action evidence over the entire
  window, including holdout. Empty events means a sourced review found none.
- Both corporate_actions and session_review require status=reviewed, evidence and
  exact first/last sample timestamps. Independently check missing sessions against
  the named calendar. Missing observations are not zero returns; no forward filling.
- Accepted bases are split_adjusted or total_return_adjusted; explain dividends
  and remaining ex-distribution effects. They need not produce the same forecast.
  In-sample actions require resolution=adjusted_in_series with evidence.
  outside_sample is allowed only at/before the first observation or after the last.
  Unresolved actions block fitting. For an economically changed post-spinoff
  business, use a post-action window or disclose insufficient comparable history.

Do not infer adjustment from the provider name or a field called close. The
[yfinance API](https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html)
exposes auto_adjust/actions settings and its
[source](https://raw.githubusercontent.com/ranaroussi/yfinance/main/yfinance/utils.py)
distinguishes Close from Adj Close before applying adjustment ratios. Record the
actual extraction path and inspect known-action returns; a wrapper option is not
proof that every vendor action was handled correctly. Use adjusted prices for
analysis without confusing them with current executable quotes.

Absolute simple returns >=25% trigger review before fitting, even with an audit
claiming adjusted data. This diagnostic is not a split detector or trading limit;
smaller artifacts may escape it. Repair artifacts upstream and regenerate hashes.
Preserve a genuine crash with a large_move_reviews entry: timestamp of the return's
ending observation, conclusion=genuine_market_move and corroborating evidence.
Do not drop/winsorize real moves to obtain NORMAL. Unreviewed jumps block the run.

Without a manifest, ordinary data may compute with status=UNVERIFIED and sizing
eligibility false. Invalid/mismatched manifests fail before fitting. A complete
market audit yields REVIEWED_DECLARATION, not independently verified data. The
helper validates the declaration's structure; caller-written JSON is not a
security boundary. data_kind=fictional always remains ineligible for real sizing.

## Reproducible baseline

Defaults: GARCH(1,1), horizon=1, daily bars, zero mean, Gaussian innovations,
100*log(P[t]/P[t-1]), no demeaning/outlier deletion. The training prefix contains
all but the last 40 returns (minimum 250). The holdout predicts sequentially using
prefix-fitted fixed parameters. Only the final forward forecast refits on all
returns. Never label predictions from the full-sample fit as held out.

The backend now uses arch's default backcasting, variance bounds and optimizer
initialization, with rescale=False. SLSQP has maxiter=2500 and ftol=1e-10.
Each holdout prediction calls arch's fixed-parameter API on only the observed
prefix; neither the target nor future data enters variance initialization.
GARCH/GJR persistence must be below one, and EGARCH beta must be below one.
Library parameter constraints apply; unlike the former implementation, GJR gamma
need not be nonnegative when arch's other positivity constraints are satisfied.
The training sample-variance benchmark retains ddof=1 and a floor of 1e-8.

Parameter names accompany the parameter array. The run specification identifies
arch and the numerical dependency versions, initialization, input/code hashes,
windows, model and units. Results can differ from v3.1: rerun and revalidate the
research rather than treating the new adapter as the old numerical implementation.

Regime ratio = next-period forecast volatility / standard deviation of the last
60 returns (ddof=1): LOW <0.70, NORMAL >=0.70 and <1.30, ELEVATED >=1.30 and <1.90,
EXTREME >=1.90. These illustrative thresholds are not calibrated eligibility gates.
Report the ratio too. Changes to window, price basis, distribution or mean must be
labeled as variants, not the identical GARCH test.

For day trading, daily GARCH is background context. Setting 252*78 for five-minute
data changes annualization but does not address overnight gaps, session boundaries,
opening/closing seasonality or execution risk. Validate an intraday model separately;
never mechanically scale a daily forecast into a precise intraday stop or signal.

## Units and use

forecast_variance_percent_squared is per input period. forecast_period_volatility
is a decimal per-period standard deviation. periods_per_year controls annualization;
252 is correct only for a conventional daily trading-day series. Legacy daily-named
fields remain for compatibility and are per-period values for intraday inputs.

Use the past 60 returns for the recent realized-volatility comparison. Regime labels
are illustrative ratios, not empirically calibrated trading regimes. No confidence
score is invented.

Volatility can inform an allocation recommendation. It does not gate execution or change the user's requested order.
Event gaps, earnings and regime changes can dominate historical variance. Planned
stops are not guaranteed loss bounds. Validate any use of volatility in strategy
sizing separately, against simpler alternatives and untouched data.

All model-quality flags describe analytical suitability. Missing data, failed fits,
regime labels and skipped overlays never impose an execution pause or approval.

## Extended diagnostics and compatibility

The optional distribution argument is appended to `model_specification`,
`fit_model` and `holdout_validation`; existing calls still use normal innovations.
`--ewma-decay` defaults to 0.94. The EWMA benchmark initializes only from the
training prefix and incorporates each held-out return after forecasting it.
Its decay is a disclosed convention, not a fitted or validated optimum.

Holdout output now retains both constant-variance and EWMA QLIKE comparisons.
Residual diagnostics include Ljung-Box tests on standardized residuals and their
squares, an ARCH LM check, persistence and Student-t innovation moment flags.
Student-t variance requires nu greater than two. Nu at most four flags an infinite
innovation fourth moment; this does not imply infinite conditional variance.
Finite innovation moments alone do not establish finite unconditional GARCH
moments. The diagnostic p-values are unadjusted screens, not independent proof
of model calibration. Near-unit persistence (at least 0.995) is flagged.

`eligible_as_sizing_input` preserves the earlier audited-declaration plus
constant-variance comparison contract. Its `legacy_eligibility_basis` field makes
that scope explicit. Use `strict_diagnostic_eligibility` for the extended screen:
reviewed input declaration, better QLIKE than both elementary baselines and no
residual/persistence/moment flags. Neither field certifies future performance or
authorizes a trade. Models that fail remain visible; do not relabel warnings as
calibrated forecasts.

Forecast output adds cumulative horizon sigma and annualized average sigma,
distinct from the existing next-period annualized sigma. These quantities assume
zero cross-period innovation covariance. Portfolio aggregation and current-weight
tail diagnostics are documented in [risk diagnostics](risk-diagnostics.md).

## When the requested operation depends on GARCH

Run `python scripts/research_preflight.py --require-garch` before promising a fit or GARCH-sized allocation. If it exits nonzero, identify the failing prerequisite and leave that requested result unavailable. Use the pinned runtime when supported by the host. A separately requested realized-volatility baseline has its own method and output.
