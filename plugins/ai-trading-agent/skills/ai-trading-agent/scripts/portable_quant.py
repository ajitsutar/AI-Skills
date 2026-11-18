"""Original optional local analytics inside the portable skill; no services.

No upstream implementation code is copied. References and dependency licenses:
statsmodels (BSD): https://github.com/statsmodels/statsmodels/blob/main/LICENSE.txt
https://www.statsmodels.org/stable/generated/statsmodels.tsa.arima.model.ARIMA.html
https://www.statsmodels.org/stable/generated/statsmodels.tsa.stattools.coint.html
QuantLib (modified BSD): https://www.quantlib.org/license.shtml
https://github.com/lballabio/QuantLib/blob/master/ql/pricingengines/vanilla/analyticeuropeanengine.hpp
VADER (MIT): https://github.com/cjhutto/vaderSentiment

Importing this module needs only Python's standard library. An operation requires
its optional locally installed package; it never downloads, installs, or calls a
network endpoint. Missing packages fail explicitly, without a substitute model.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime
from functools import wraps
from importlib.metadata import PackageNotFoundError, version
import json
import math
from pathlib import Path
import platform
import re
import threading
import warnings


_QL_LOCK = threading.RLock()
_BASIS = "caller_declared_frozen_inputs"


def _method_errors(function):
    """Translate expected library failures into the workbench's failure channel."""
    @wraps(function)
    def invoke(document):
        try:
            return function(document)
        except (RuntimeError, ArithmeticError, OSError) as exc:
            raise ValueError(f"CALCULATION_FAILED:{function.__name__}:{type(exc).__name__}:{exc}") from exc
    return invoke


def _schema(document, fields):
    expected = set(fields) | {"as_of", "currency"}
    if type(document) is not dict or set(document) != expected:
        raise ValueError("EXACT_FIELDS_REQUIRED:" + ",".join(sorted(expected)))
    timestamp = document["as_of"]
    if type(timestamp) is not str or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z", timestamp) is None:
        raise ValueError("AS_OF_UTC_TIMESTAMP_REQUIRED")
    try:
        cutoff = datetime.fromisoformat(timestamp[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("AS_OF_INVALID_TIMESTAMP") from exc
    currency = document["currency"]
    if type(currency) is not str or re.fullmatch(r"[A-Z]{3}", currency) is None:
        raise ValueError("CURRENCY_THREE_UPPERCASE_LETTERS_REQUIRED")
    return cutoff


def _number(value, label):
    if type(value) not in (int, float):
        raise ValueError("FINITE_NUMBER_REQUIRED:" + label)
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError("FINITE_NUMBER_REQUIRED:" + label) from exc
    if not math.isfinite(result):
        raise ValueError("FINITE_NUMBER_REQUIRED:" + label)
    return result


def _integer(value, label, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"INTEGER_RANGE:{label}:[{minimum},{maximum}]")
    return value


def _choice(value, label, choices):
    if value not in choices or (value is not None and type(value) is not str):
        raise ValueError(f"CHOICE_REQUIRED:{label}:{choices}")
    return value


def _label(value, name):
    if type(value) is not str or not value.strip() or value.strip() != value or len(value) > 200:
        raise ValueError("NONEMPTY_LABEL_REQUIRED:" + name)
    return value


def _series(values, name, minimum):
    if type(values) is not list or not minimum <= len(values) <= 20000:
        raise ValueError(f"SERIES_LENGTH:{name}:[{minimum},20000]")
    result = [_number(value, name) for value in values]
    if min(result) == max(result):
        raise ValueError("CONSTANT_SERIES:" + name)
    return result


def _finite(value, label):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("NONFINITE_CALCULATION:" + label)
    return result


def _runtime(packages):
    result = {"python": platform.python_version()}
    for package in packages:
        try:
            result[package] = version(package)
        except PackageNotFoundError as exc:
            raise ValueError("DEPENDENCY_UNAVAILABLE:" + package + ":optional local package is required; no substitute calculation was performed") from exc
    return result


def _metadata(document, runtime):
    return {"as_of": document["as_of"], "currency": document["currency"], "runtime": runtime}


def _frozen(document, units):
    if document["input_basis"] != _BASIS:
        raise ValueError("INPUT_BASIS_REQUIRED:" + _BASIS)
    for field in (*units, "observation_frequency"):
        _label(document[field], field)


@_method_errors
def arima(document):
    """Explicit non-seasonal state-space MLE. Nonconvergence emits no forecast."""
    _schema(document, ("values", "order", "trend", "steps", "maxiter", "diagnostic_lags", "alpha",
                       "input_basis", "value_unit", "observation_frequency"))
    _frozen(document, ("value_unit",))
    values = _series(document["values"], "values", 30)
    order = document["order"]
    if type(order) is not list or len(order) != 3:
        raise ValueError("ORDER_MUST_BE_P_D_Q")
    p, d, q = [_integer(value, "order", 0, maximum) for value, maximum in zip(order, (5, 2, 5))]
    if len(values) < max(30, 5 * (p + q + d + 1)):
        raise ValueError("INSUFFICIENT_OBSERVATIONS_FOR_ORDER")
    trend = _choice(document["trend"], "trend", ("n", "c", "t", "ct"))
    if (d > 0 and trend in ("c", "ct")) or (d > 1 and trend == "t"):
        raise ValueError("TREND_ORDER_BELOW_DIFFERENCING_ORDER")
    steps = _integer(document["steps"], "steps", 1, 3650)
    maxiter = _integer(document["maxiter"], "maxiter", 1, 1000)
    lag = _integer(document["diagnostic_lags"], "diagnostic_lags", p + q + 1, len(values) // 4)
    alpha = _number(document["alpha"], "alpha")
    if not 0 < alpha < 1:
        raise ValueError("ALPHA_MUST_BE_BETWEEN_ZERO_AND_ONE")
    runtime = _runtime(("numpy", "scipy", "pandas", "statsmodels"))
    try:
        import numpy as np
        from statsmodels.tsa.arima.model import ARIMA
        from statsmodels.stats.diagnostic import acorr_ljungbox
    except ImportError as exc:
        raise ValueError("DEPENDENCY_UNAVAILABLE:statsmodels/numpy/scipy/pandas import failed") from exc
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        model = ARIMA(values, order=(p, d, q), trend=trend, enforce_stationarity=True,
                      enforce_invertibility=True, concentrate_scale=False, missing="raise")
        model.initialize_default(approximate_diffuse_variance=1000000.0)
        fit = model.fit(method="statespace", cov_type="opg",
                        method_kwargs={"method": "lbfgs", "maxiter": maxiter, "disp": 0})
        if not bool(fit.mle_retvals.get("converged", False)):
            diagnostic = {"order": [p, d, q], "trend": trend, "maxiter": maxiter,
                          "runtime": runtime, "warnings": [str(item.message) for item in caught],
                          "converged": False, "forecast_emitted": False}
            raise ValueError("ARIMA_NOT_CONVERGED:" + json.dumps(diagnostic, sort_keys=True, allow_nan=False))
        predicted = fit.get_forecast(steps=steps)
        intervals = predicted.conf_int(alpha=alpha)
        burn = int(fit.loglikelihood_burn)
        residuals = np.asarray(fit.resid)[burn:]
        lb = acorr_ljungbox(residuals, lags=[lag], model_df=p + q, return_df=True)
    return {**_metadata(document, runtime), "converged": True,
        "observations": len(values), "order": [p, d, q], "trend": trend,
        "value_unit": document["value_unit"], "observation_frequency": document["observation_frequency"],
        "fit_method": "statespace_mle_lbfgs", "maxiter": maxiter,
        "initialization": "stationary ARMA states; approximate diffuse differenced states with variance 1000000",
        "enforce_stationarity": True, "enforce_invertibility": True,
        "parameters": {str(k): _finite(v, str(k)) for k, v in zip(fit.param_names, fit.params)},
        "aic": _finite(fit.aic, "aic"), "bic": _finite(fit.bic, "bic"),
        "log_likelihood": _finite(fit.llf, "log_likelihood"),
        "forecast": [_finite(value, "forecast") for value in predicted.predicted_mean],
        "prediction_intervals": [[_finite(value, "interval") for value in row] for row in intervals],
        "alpha": alpha,
        "residual_diagnostics": {"excluded_initial_observations": burn, "observations": len(residuals),
            "mean": _finite(np.mean(residuals), "residual_mean"),
            "rmse": _finite(np.sqrt(np.mean(residuals ** 2)), "residual_rmse"),
            "ljung_box_lag": lag, "model_degrees_of_freedom": p + q,
            "ljung_box_statistic": _finite(lb.iloc[0]["lb_stat"], "ljung_box_statistic"),
            "ljung_box_pvalue": _finite(lb.iloc[0]["lb_pvalue"], "ljung_box_pvalue")},
        "warnings": [str(item.message) for item in caught],
        "limitations": ["Raw arrays are caller-declared frozen, equally spaced observations; timestamps, availability and revisions are not independently verified.",
            "In-sample fit and conditional forecast only; no held-out accuracy or trading edge is established.",
            "Prediction intervals condition on the fitted model and do not cover all model or parameter uncertainty.",
            "No automatic order selection, resampling, scaling, differencing outside the specified ARIMA order, or missing-value imputation."]}


@_method_errors
def cointegration(document):
    """Directional Engle-Granger test; I(1) input assumption is not established."""
    _schema(document, ("y0", "y1", "trend", "maxlag", "autolag", "significance",
                       "input_basis", "y0_unit", "y1_unit", "observation_frequency"))
    _frozen(document, ("y0_unit", "y1_unit"))
    y0, y1 = _series(document["y0"], "y0", 40), _series(document["y1"], "y1", 40)
    if len(y0) != len(y1):
        raise ValueError("ALIGNED_EQUAL_LENGTH_SERIES_REQUIRED")
    trend = _choice(document["trend"], "trend", ("c", "ct", "ctt"))
    maxlag = _integer(document["maxlag"], "maxlag", 0, min(100, len(y0) // 2 - 4))
    autolag = _choice(document["autolag"], "autolag", (None, "aic", "bic", "t-stat"))
    significance = _number(document["significance"], "significance")
    if not 0 < significance < 1:
        raise ValueError("SIGNIFICANCE_MUST_BE_BETWEEN_ZERO_AND_ONE")
    runtime = _runtime(("numpy", "scipy", "pandas", "statsmodels"))
    try:
        import numpy as np
        from statsmodels.tsa.stattools import coint
    except ImportError as exc:
        raise ValueError("DEPENDENCY_UNAVAILABLE:statsmodels/numpy/scipy/pandas import failed") from exc
    time_index = np.arange(1, len(y0) + 1, dtype=float)
    columns, names = [np.asarray(y1), np.ones(len(y0))], ["y1", "intercept"]
    if trend in ("ct", "ctt"):
        columns.append(time_index)
        names.append("time_index_1_based")
    if trend == "ctt":
        columns.append(time_index * time_index)
        names.append("time_index_squared")
    coefficients, _, rank, _ = np.linalg.lstsq(np.column_stack(columns), y0, rcond=None)
    if rank != len(columns):
        raise ValueError("COINTEGRATING_DESIGN_RANK_DEFICIENT")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        statistic, pvalue, critical = coint(y0, y1, trend=trend, method="aeg", maxlag=maxlag, autolag=autolag)
    statistic, pvalue = _finite(statistic, "cointegration_statistic"), _finite(pvalue, "pvalue")
    return {**_metadata(document, runtime), "method": "augmented_engle_granger", "observations": len(y0),
        "dependent_series": "y0", "regressor_series": "y1", "y0_unit": document["y0_unit"],
        "y1_unit": document["y1_unit"], "observation_frequency": document["observation_frequency"],
        "normalization": "coefficient of y0 equals +1; residual = y0 - fitted(y1, deterministic terms)",
        "trend": trend, "maxlag": maxlag, "autolag": autolag,
        "coefficients": {name: _finite(value, name) for name, value in zip(names, coefficients)},
        "statistic": statistic, "pvalue": pvalue,
        "critical_values": {key: _finite(value, key) for key, value in zip(("1%", "5%", "10%"), critical)},
        "significance": significance, "reject_no_cointegration": pvalue < significance,
        "warnings": [str(item.message) for item in caught],
        "limitations": ["Null hypothesis is no cointegration. Both supplied series are assumed I(1); integration order is not verified.",
            "Caller-declared frozen arrays must be equally spaced and chronologically aligned; availability and data lineage are not independently verified.",
            "Direction matters in finite samples; reversing y0/y1 defines a different regression.",
            "One prespecified pair test; no multiple-pair-search correction or evidence of profitable, borrowable, cost-aware execution."]}


def _date(value, name):
    if type(value) is not str or re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is None:
        raise ValueError("DATE_YYYY_MM_DD_REQUIRED:" + name)
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("INVALID_DATE:" + name) from exc
    if not 1901 <= parsed.year <= 2199:
        raise ValueError("QUANTLIB_SUPPORTED_YEAR_REQUIRED:" + name)
    return parsed


@_method_errors
def european(document):
    cutoff = _schema(document, ("spot", "strike", "rate", "dividend_yield", "volatility",
        "evaluation_date", "maturity_date", "option_type", "day_count"))
    spot, strike, rate, dividend, volatility = [_number(document[key], key)
        for key in ("spot", "strike", "rate", "dividend_yield", "volatility")]
    if spot <= 0 or strike <= 0 or not 0 < volatility <= 10:
        raise ValueError("POSITIVE_SPOT_STRIKE_AND_VOLATILITY_AT_MOST_TEN_REQUIRED")
    if not -1 <= rate <= 1 or not -1 <= dividend <= 1:
        raise ValueError("CONTINUOUS_RATE_AND_DIVIDEND_MUST_BE_IN_MINUS_ONE_TO_ONE")
    today = _date(document["evaluation_date"], "evaluation_date")
    maturity = _date(document["maturity_date"], "maturity_date")
    if today != cutoff.date():
        raise ValueError("EVALUATION_DATE_MUST_MATCH_AS_OF_UTC_DATE")
    if maturity <= today:
        raise ValueError("MATURITY_MUST_BE_AFTER_EVALUATION_DATE")
    kind = _choice(document["option_type"], "option_type", ("call", "put"))
    _choice(document["day_count"], "day_count", ("Actual365Fixed",))
    runtime = _runtime(("QuantLib",))
    try:
        import QuantLib as ql
    except ImportError as exc:
        raise ValueError("DEPENDENCY_UNAVAILABLE:QuantLib import failed") from exc
    # SavedSettings preserves implicit/default date state as well as explicit dates.
    with _QL_LOCK, ql.SavedSettings():
        evaluation = ql.Date(today.day, today.month, today.year)
        expiry = ql.Date(maturity.day, maturity.month, maturity.year)
        ql.Settings.instance().evaluationDate = evaluation
        counter = ql.Actual365Fixed()
        curve = ql.YieldTermStructureHandle(ql.FlatForward(evaluation, rate, counter, ql.Continuous, ql.Annual))
        dividends = ql.YieldTermStructureHandle(ql.FlatForward(evaluation, dividend, counter, ql.Continuous, ql.Annual))
        vol = ql.BlackVolTermStructureHandle(ql.BlackConstantVol(evaluation, ql.NullCalendar(), volatility, counter))
        process = ql.BlackScholesMertonProcess(ql.QuoteHandle(ql.SimpleQuote(spot)), dividends, curve, vol)
        option = ql.VanillaOption(ql.PlainVanillaPayoff(ql.Option.Call if kind == "call" else ql.Option.Put, strike), ql.EuropeanExercise(expiry))
        option.setPricingEngine(ql.AnalyticEuropeanEngine(process))
        result = {"npv": _finite(option.NPV(), "npv"), "delta": _finite(option.delta(), "delta"),
            "gamma": _finite(option.gamma(), "gamma"), "vega": _finite(option.vega(), "vega"),
            "theta_per_year": _finite(option.theta(), "theta"), "rho": _finite(option.rho(), "rho"),
            "dividend_rho": _finite(option.dividendRho(), "dividend_rho"),
            "year_fraction": _finite(counter.yearFraction(evaluation, expiry), "year_fraction")}
    result.update({**_metadata(document, runtime), "engine": "QuantLib.AnalyticEuropeanEngine", "option_type": kind,
        "evaluation_date": today.isoformat(), "maturity_date": maturity.isoformat(),
        "day_count": "Actual365Fixed", "compounding": "continuous",
        "units": {"npv": "currency per underlying unit", "vega": "currency per 1.0 absolute volatility change",
                  "rho": "currency per 1.0 absolute rate change", "dividend_rho": "currency per 1.0 absolute dividend-yield change",
                  "theta_per_year": "currency per year"},
        "limitations": ["European exercise; positive spot; flat continuous rates/dividend yield; constant volatility.",
            "No discrete dividends, calibrated volatility surface, transaction costs, or contract multiplier.",
            "Date-level valuation; intraday time to expiry is not represented."]})
    return result


@_method_errors
def vader(document):
    _schema(document, ("texts",))
    texts = document["texts"]
    if type(texts) is not list or not 1 <= len(texts) <= 1000:
        raise ValueError("TEXTS_MUST_CONTAIN_ONE_TO_1000_STRINGS")
    if any(type(text) is not str or not 1 <= len(text) <= 10000 for text in texts) or sum(map(len, texts)) > 1000000:
        raise ValueError("TEXT_LENGTH_LIMIT:each 1..10000; total at most 1000000")
    runtime = _runtime(("vaderSentiment",))
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    except ImportError as exc:
        raise ValueError("DEPENDENCY_UNAVAILABLE:vaderSentiment import failed") from exc
    analyzer = SentimentIntensityAnalyzer()
    return {**_metadata(document, runtime), "model": "vaderSentiment.SentimentIntensityAnalyzer",
        "scores": [analyzer.polarity_scores(text) for text in texts],
        "limitations": ["Original neg/neu/pos/compound scores in input order; English lexical baseline.",
            "No financial-domain calibration, entity attribution, verified publication timing, or trading recommendation."]}


OPERATIONS = {"arima": arima, "cointegration": cointegration, "european": european, "vader": vader}


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("DUPLICATE_JSON_KEY:" + key)
        result[key] = value
    return result


def _nonfinite(value):
    raise ValueError("NONFINITE_JSON:" + value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=sorted(OPERATIONS))
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    try:
        document = json.loads(args.input.read_text(encoding="utf-8"), object_pairs_hook=_unique, parse_constant=_nonfinite)
        result = OPERATIONS[args.operation](document)
        print(json.dumps(result, sort_keys=True, allow_nan=False))
    except (ValueError, RuntimeError, OSError) as exc:
        print(json.dumps({"status": "FAILED", "error": str(exc)}, sort_keys=True))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
