#!/usr/bin/env python3
"""Audited-price adapter for arch. See ../PROVENANCE.md and ../THIRD-PARTY-NOTICES.md.

The external library performs estimation, filtering and variance forecasts.
This adapter controls input evidence, chronological validation and output units.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import io
import json
import math
import sys
from datetime import datetime
from importlib.metadata import version
from pathlib import Path

import numpy as np
from arch import arch_model
from arch.univariate import EGARCH

from price_audit import audit_prices


def model_specification(family, observations):
    """Construct a zero-mean normal model with explicit input units."""
    choices = {"garch": ("GARCH", 0), "gjr": ("GARCH", 1), "egarch": ("EGARCH", 1)}
    if family not in choices:
        raise ValueError(f"Unknown volatility family: {family}")
    data = np.asarray(observations, dtype=np.float64)
    if data.ndim != 1 or data.size < 3 or not np.isfinite(data).all():
        raise ValueError("Provide at least three finite returns in a one-dimensional series")
    if float(data.var()) <= 1e-12:
        raise ValueError("Returns must have nonzero variation")
    process, asymmetry = choices[family]
    return arch_model(data, mean="Zero", vol=process, p=1, o=asymmetry,
                      q=1, dist="normal", rescale=False)


def require_usable_fit(estimate):
    if estimate.convergence_flag != 0:
        raise ValueError(f"Volatility optimizer failed: {estimate.optimization_result.message}")
    numbers = np.r_[estimate.params, estimate.conditional_volatility, estimate.loglikelihood]
    if not np.isfinite(numbers).all() or np.any(estimate.conditional_volatility <= 0):
        raise ValueError("Volatility fit contains invalid numerical values")
    pars = estimate.params
    persistence = float(pars["beta[1]"])
    if not isinstance(estimate.model.volatility, EGARCH):
        persistence += float(pars["alpha[1]"]) + .5 * float(pars.get("gamma[1]", 0))
    if persistence >= 1.0:
        raise ValueError("A stationary volatility fit is required for this sizing adapter")


def fit_model(family, observations):
    result = model_specification(family, observations).fit(
        disp="off", update_freq=0, show_warning=False,
        options={"maxiter": 2500, "ftol": 1e-10})
    require_usable_fit(result)
    return result


def analytic_variance(estimate, steps):
    if isinstance(steps, bool) or not isinstance(steps, (int, np.integer)) or steps < 1:
        raise ValueError("Forecast horizon must be a positive integer")
    if isinstance(estimate.model.volatility, EGARCH) and steps != 1:
        raise ValueError("Multi-step EGARCH needs simulation; this adapter supports one step")
    table = estimate.forecast(horizon=int(steps), method="analytic", reindex=False)
    prediction = table.residual_variance.iloc[-1].to_numpy(dtype=float)
    if prediction.shape != (steps,) or not np.isfinite(prediction).all() or np.any(prediction <= 0):
        raise ValueError("Backend returned an invalid variance forecast")
    return prediction


def forecast(estimate, horizon):
    require_usable_fit(estimate)
    return analytic_variance(estimate, horizon)


def variance_loss(squared_returns, predictions):
    """QLIKE: x/y - log(x/y) - 1, flooring zero realized squared returns."""
    actual, expected = np.asarray(squared_returns, dtype=float), np.asarray(predictions, dtype=float)
    if actual.shape != expected.shape or actual.size == 0:
        raise ValueError("Variance loss requires equally sized nonempty arrays")
    if not np.isfinite(actual).all() or not np.isfinite(expected).all():
        raise ValueError("Variance loss requires finite inputs")
    if np.any(actual < 0) or np.any(expected <= 0):
        raise ValueError("Squared returns cannot be negative and predictions must be positive")
    scaled = np.clip(actual, 1e-12, None) / expected
    return float(np.average(scaled - 1 - np.log(scaled)))


def holdout_validation(observations, family, train, test):
    if train < 3 or test < 1 or len(observations) < train + test:
        return {"status": "insufficient_data"}
    data = np.asarray(observations, dtype=float)
    try:
        estimate = fit_model(family, data[:train])
        predictions = []
        for end in range(train, train + test):
            # The target and future data never enter the backend. Parameters stay
            # fixed; arch filters/backcasts using only this observed prefix.
            past = model_specification(family, data[:end]).fix(estimate.params)
            predictions.append(float(analytic_variance(past, 1)[0]))
        expected = np.asarray(predictions)
        actual = np.square(data[train:train + test])
        baseline = np.repeat(max(float(data[:train].var(ddof=1)), 1e-8), test)
        score, reference = variance_loss(actual, expected), variance_loss(actual, baseline)
        return {"status": "ok", "n": test, "qlike": score,
                "mse": float(np.square(actual - expected).mean()),
                "baseline_qlike": reference, "beats_constant_variance": score < reference,
                "predicted_variance_percent_squared": predictions,
                "method": "fixed_parameter_sequential_one_step",
                "filtering": "arch fixed parameters; observed prefixes only"}
    except (ValueError, FloatingPointError, OverflowError) as error:
        return {"status": "fit_failed", "message": str(error)}


def load_price_input(path, close_column, timestamp_column):
    content = Path(path).read_bytes()
    prices, stamps = [], []
    for row in csv.DictReader(io.StringIO(content.decode("utf-8-sig"), newline="")):
        price = float(row[close_column])
        stamp = datetime.fromisoformat(row[timestamp_column].replace("Z", "+00:00"))
        if price <= 0 or not math.isfinite(price):
            raise ValueError("Every price must be finite and positive; repair data upstream")
        if stamp.utcoffset() is None or (stamps and stamp <= stamps[-1]):
            raise ValueError("Price timestamps need timezone offsets and strict chronological order")
        if row.get("synthetic", "false").strip().lower() not in ("", "false", "0"):
            raise ValueError("Synthetic/interpolated price rows cannot enter the risk model")
        prices.append(price)
        stamps.append(stamp)
    return content, np.asarray(prices, dtype=float), stamps


def parse_options(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv")
    parser.add_argument("--data-audit")
    parser.add_argument("--model", default="garch", choices=("garch", "gjr", "egarch", "auto"))
    parser.add_argument("--close-column", default="close")
    parser.add_argument("--timestamp-column", default="timestamp")
    parser.add_argument("--horizon", default=1, type=int)
    parser.add_argument("--min-observations", default=250, type=int)
    parser.add_argument("--validation-test", default=40, type=int)
    parser.add_argument("--periods-per-year", default=252.0, type=float)
    opts = parser.parse_args(argv)
    if opts.horizon < 1 or opts.min_observations < 30 or opts.validation_test < 10:
        raise ValueError("Minimums: horizon 1, training returns 30, holdout returns 10")
    if not math.isfinite(opts.periods_per_year) or opts.periods_per_year <= 0:
        raise ValueError("Annualization periods must be finite and positive")
    if opts.model == "egarch" and opts.horizon > 1:
        raise ValueError("Multi-step EGARCH needs simulation; request horizon=1")
    return opts


def run_analysis(opts):
    raw, prices, times = load_price_input(opts.csv, opts.close_column, opts.timestamp_column)
    required = opts.min_observations + opts.validation_test + 1
    if prices.size < required:
        raise ValueError(f"Need {required} prices including the holdout; received {prices.size}")
    audit_bytes = Path(opts.data_audit).read_bytes() if opts.data_audit else None
    declaration = json.loads(audit_bytes.decode("utf-8-sig")) if audit_bytes is not None else None
    quality = audit_prices(raw, prices, times, declaration, close_column=opts.close_column,
                           timestamp_column=opts.timestamp_column, periods_per_year=opts.periods_per_year)
    changes = np.log(prices[1:] / prices[:-1]) * 100
    prefix_size = int(changes.size - opts.validation_test)
    families = [opts.model] if opts.model != "auto" else ["garch", "gjr", "egarch"]
    families = [name for name in families if name != "egarch" or opts.horizon == 1]
    diagnostics, estimates = {}, {}
    for family in families:
        diagnostics[family] = holdout_validation(changes, family, prefix_size, opts.validation_test)
        if diagnostics[family]["status"] != "ok":
            continue
        try:
            estimates[family] = fit_model(family, changes)
        except (ValueError, FloatingPointError, OverflowError) as error:
            diagnostics[family]["refit_error"] = str(error)
    if not estimates:
        raise ValueError("No usable model after chronological validation: " + json.dumps(diagnostics))
    selected = min(estimates, key=lambda name: diagnostics[name]["qlike"])
    fitted = estimates[selected]
    variances = forecast(fitted, opts.horizon)
    period_sigma = float(np.sqrt(variances[0]) * .01)
    recent_count = min(60, int(changes.size))
    realized_sigma = float(changes[-recent_count:].std(ddof=1) * .01)
    ratio = period_sigma / realized_sigma if realized_sigma > 0 else None
    labels = ("LOW", "NORMAL", "ELEVATED", "EXTREME")
    bucket = "UNKNOWN" if ratio is None else labels[bisect.bisect_right((.7, 1.3, 1.9), ratio)]
    digest = lambda value: hashlib.sha256(value).hexdigest()
    script = Path(__file__)
    spec = {
        "implementation": "arch-adapter-3.2.0", "backend": "arch",
        "script_sha256": digest(script.read_bytes()),
        "audit_helper_sha256": digest(script.with_name("price_audit.py").read_bytes()),
        "csv_sha256": quality["csv_sha256"],
        "audit_sha256": digest(audit_bytes) if audit_bytes is not None else None,
        "python": sys.version.split()[0],
        **{name: version(name) for name in ("arch", "numpy", "scipy", "pandas", "statsmodels")},
        "close_column": opts.close_column, "timestamp_column": opts.timestamp_column,
        "first_timestamp": times[0].isoformat(), "last_timestamp": times[-1].isoformat(),
        "price_count": int(prices.size), "return_count": int(changes.size),
        "training_returns": prefix_size, "holdout_returns": opts.validation_test,
        "training_last_return_end": times[prefix_size].isoformat(),
        "holdout_first_return_end": times[prefix_size + 1].isoformat(),
        "return_definition": "100 * log(P[t] / P[t-1]); zero mean; Gaussian innovations",
        "requested_model": opts.model, "selected_model": selected, "horizon": opts.horizon,
        "periods_per_year": opts.periods_per_year,
        "variance_initialization": "arch default backcast and variance bounds on observed prefix",
        "optimizer": "arch fit using SLSQP; maxiter=2500; ftol=1e-10; rescale=False",
        "parameter_names": list(fitted.params.index),
        "forecast_fit": "full-sample refit after fixed-parameter observed-prefix holdout",
        "realized_window_returns": recent_count, "regime_ratio": ratio,
        "regime_ratio_boundaries": [.7, 1.3, 1.9],
    }
    return {
        "model": selected, "parameters": fitted.params.tolist(), "parameter_names": list(fitted.params.index),
        "observations": int(changes.size), "last_price": float(prices[-1]), "last_timestamp": times[-1].isoformat(),
        "forecast_variance_percent_squared": variances.tolist(),
        "forecast_period_volatility": period_sigma, "forecast_daily_volatility": period_sigma,
        "forecast_annualized_volatility": period_sigma * math.sqrt(opts.periods_per_year),
        "recent_realized_daily_volatility": realized_sigma, "regime": bucket,
        "fit_success": True, "fit_message": str(fitted.optimization_result.message),
        "log_likelihood": float(fitted.loglikelihood), "validation": diagnostics,
        "periods_per_year": opts.periods_per_year, "innovation_distribution": "Gaussian; zero conditional mean",
        "eligible_as_sizing_input": bool(quality["eligible_for_sizing"] and diagnostics[selected]["beats_constant_variance"]),
        "data_quality": quality, "selection_caveat": "Selection holdout is not independent strategy-performance evidence",
        "run_specification": spec,
    }


def main(argv=None):
    print(json.dumps(run_analysis(parse_options(argv)), sort_keys=True, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, KeyError, OSError) as problem:
        print(f"ERROR: {problem}", file=sys.stderr)
        sys.exit(1)

