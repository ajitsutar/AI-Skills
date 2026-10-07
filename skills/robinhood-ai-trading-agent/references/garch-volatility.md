# Volatility helper: corrected behavior and limits

This is the built-in GARCH specification for package 3.1.0. The main SKILL.md
states when to assess it and how to report computation versus a skipped overlay.
Load this reference when a shortlist/risk-sizing workflow reaches that step.

If this file or scripts/garch_volatility.py is unavailable in an upload, report a
missing package component. Do not reinterpret the missing upload as evidence that
GARCH is not part of the skill. Preserve a clear distinction between the bundled
helper and any separately verified alternative implementation.

GARCH forecasts conditional variance, not price direction or profitability.
Dependencies are NumPy and SciPy. The helper assumes zero conditional mean and
Gaussian innovations; percent log returns improve numerical scale.

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

Initial variance is sample variance (ddof=1, floor 1e-8); likelihood variance has
floor 1e-12. SLSQP uses a deterministic single start, maxiter=2500, ftol=1e-10.
GARCH parameter order is omega/alpha/beta with alpha+beta <= 0.999. GJR adds gamma
before beta and uses alpha+gamma/2+beta <= 0.999, gamma >= 0. The emitted
run_specification records exact code/audit-helper/input/audit hashes, Python and
NumPy/SciPy versions, windows/counts, model/horizon and annualization. Code hashes
capture remaining bounds/choices. Preserve inputs plus output JSON; dependency
or optimizer changes can still cause small numeric differences.

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

Volatility can lower an existing risk allocation, never override hard limits.
Event gaps, earnings and regime changes can dominate historical variance. Planned
stops are not guaranteed loss bounds. Validate any use of volatility in strategy
sizing separately, against simpler alternatives and untouched data.
