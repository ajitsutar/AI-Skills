"""Portable constant-variance/EWMA holdout benchmarks; no GARCH fit or sizing authority."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime
import hashlib
import io
import json
import math
import operator
from pathlib import Path
import statistics

from price_audit import audit_prices


def finite_number(value):
    if isinstance(value, (bool, str, bytes)):
        raise ValueError("A finite numeric value is required")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("A finite numeric value is required")
    return number


def count(value, minimum):
    if isinstance(value, bool):
        raise ValueError("Counts must be integers")
    try:
        result = operator.index(value)
    except TypeError as exc:
        raise ValueError("Counts must be integers") from exc
    if result < minimum:
        raise ValueError(f"Count must be at least {minimum}")
    return result


def ewma_predictions(observations, train, test, decay, initial_variance):
    """Shared native recursion: training warm-up, then predict BEFORE each target.

    The native adapter supplies its existing numpy-derived initial variance.
    This function preserves its float conversions, exponent and operation order.
    Values after the requested holdout are not used.
    """
    train, test = count(train, 3), count(test, 1)
    decay, state = finite_number(decay), finite_number(initial_variance)
    if not 0 < decay < 1 or state <= 0:
        raise ValueError("Decay must be between zero and one; initial variance must be positive")
    data = list(observations)[:train + test]
    if len(data) != train + test:
        raise ValueError("Insufficient training and holdout observations")
    data = [finite_number(value) for value in data]
    try:
        for value in data[:train]:
            state = decay * state + (1-decay) * float(value)**2
        predictions = []
        for value in data[train:train+test]:
            if not math.isfinite(state):
                raise ValueError("Nonfinite EWMA variance")
            predictions.append(max(state, 1e-12))
            state = decay * state + (1-decay) * float(value)**2
        if not math.isfinite(state):
            raise ValueError("Nonfinite EWMA variance")
        return predictions
    except OverflowError as exc:
        raise ValueError("Nonfinite EWMA variance") from exc


def variance_loss(squared_returns, predictions):
    """QLIKE in matching units; zero realized squares are floored at1e-12."""
    actual = [finite_number(value) for value in squared_returns]
    expected = [finite_number(value) for value in predictions]
    if not actual or len(actual) != len(expected):
        raise ValueError("Variance loss requires equally sized nonempty arrays")
    if any(value < 0 for value in actual) or any(value <= 0 for value in expected):
        raise ValueError("Squared returns cannot be negative and predictions must be positive")
    terms = []
    for value, prediction in zip(actual, expected):
        ratio = max(value, 1e-12) / prediction
        if not math.isfinite(ratio) or ratio <= 0:
            raise ValueError("Nonfinite variance-loss ratio")
        terms.append(ratio - 1 - math.log(ratio))
    result = sum(terms) / len(terms)
    if not math.isfinite(result):
        raise ValueError("Nonfinite variance loss")
    return result


def baseline_comparison(observations, train, test, decay=.94):
    """Elementary benchmarks on percentage log returns, without optional packages."""
    train, test = count(train, 3), count(test, 1)
    data = list(observations)[:train + test]
    if len(data) != train + test:
        raise ValueError("Insufficient training and holdout observations")
    data = [finite_number(value) for value in data]
    initial = max(float(statistics.variance(data[:train])), 1e-8)
    constant = [initial] * test
    ewma = ewma_predictions(data, train, test, decay, initial)
    actual = [value**2 for value in data[train:train+test]]
    return {"status": "BASELINES_ONLY_NO_GARCH_FIT",
            "return_definition": "100 * log(P[t] / P[t-1])",
            "variance_units": "percent_log_return_squared_per_observation",
            "forecast_horizon_observations": 1,
            "prediction_scope": "one-step historical holdout; no forward GARCH forecast",
            "training_returns": train, "holdout_returns": test,
            "initial_variance_percent_squared": initial,
            "initialization": "training sample variance (ddof=1), floored at1e-8",
            "ewma_training_warmup_returns": train,
            "ewma_recursion": "state=decay*state+(1-decay)*return_percent**2 for every training return; then predict before updating with each holdout target",
            "ewma_decay": float(decay),
            "constant_predicted_variance_percent_squared": constant,
            "ewma_predicted_variance_percent_squared": ewma,
            "holdout_squared_percent_log_returns": actual,
            "constant_variance_qlike": variance_loss(actual, constant),
            "ewma_qlike": variance_loss(actual, ewma),
            "qlike_definition": "mean(x/v - 1 - log(x/v)); x=max(squared percentage log return,1e-12); lower is better",
            "garch_fit_performed": False, "garch_qlike": None,
            "garch_forecast_variance": None, "garch_convergence": None,
            "native_adapter_sizing_eligibility": None,
            "execution_authorized": False,
            "limitation": "Elementary benchmarks only. Neither these losses nor an audit establish a GARCH fit, predictive superiority, sizing eligibility or execution permission."}


def from_csv(raw, audit=None, *, close_column="close", timestamp_column="timestamp",
             min_observations=250, validation_test=40, periods_per_year=252.0, decay=.94):
    minimum, test = count(min_observations, 30), count(validation_test, 10)
    periods_per_year = finite_number(periods_per_year)
    if periods_per_year <= 0:
        raise ValueError("Annualization periods must be finite and positive")
    prices, times = [], []
    for row in csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline="")):
        price = float(row[close_column])
        stamp = datetime.fromisoformat(row[timestamp_column].replace("Z", "+00:00"))
        if price <= 0 or not math.isfinite(price):
            raise ValueError("Every price must be finite and positive; repair data upstream")
        if stamp.utcoffset() is None or (times and stamp <= times[-1]):
            raise ValueError("Price timestamps need timezone offsets and strict chronological order")
        if row.get("synthetic", "false").strip().lower() not in ("", "false", "0"):
            raise ValueError("Synthetic/interpolated price rows cannot enter the benchmark")
        prices.append(price); times.append(stamp)
    if len(prices) < minimum + test + 1:
        raise ValueError(f"Need {minimum + test + 1} prices including the holdout; received {len(prices)}")
    quality = audit_prices(raw, prices, times, audit, close_column=close_column,
                           timestamp_column=timestamp_column, periods_per_year=periods_per_year)
    changes = [100 * math.log(b/a) for a, b in zip(prices, prices[1:])]
    train = len(changes) - test
    result = baseline_comparison(changes, train, test, decay)
    result.update(price_count=len(prices), return_count=len(changes),
                  first_timestamp=times[0].isoformat(), last_timestamp=times[-1].isoformat(),
                  training_last_return_end=times[train].isoformat(),
                  holdout_first_return_end=times[train+1].isoformat(),
                  csv_sha256=hashlib.sha256(raw).hexdigest(),
                  close_column=close_column, timestamp_column=timestamp_column,
                  bar_interval=quality.get("bar_interval", "UNVERIFIED"),
                  periods_per_year=periods_per_year, data_quality=quality,
                  annualization_applied_to_losses=False)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv")
    parser.add_argument("--data-audit")
    parser.add_argument("--close-column", default="close")
    parser.add_argument("--timestamp-column", default="timestamp")
    parser.add_argument("--min-observations", type=int, default=250)
    parser.add_argument("--validation-test", type=int, default=40)
    parser.add_argument("--periods-per-year", type=float, default=252.0)
    parser.add_argument("--ewma-decay", type=float, default=.94)
    args = parser.parse_args(argv)
    raw = Path(args.csv).read_bytes()
    audit_raw = Path(args.data_audit).read_bytes() if args.data_audit else None
    audit = json.loads(audit_raw.decode("utf-8-sig")) if audit_raw is not None else None
    result = from_csv(raw, audit, close_column=args.close_column, timestamp_column=args.timestamp_column,
                      min_observations=args.min_observations, validation_test=args.validation_test,
                      periods_per_year=args.periods_per_year, decay=args.ewma_decay)
    result["audit_sha256"] = hashlib.sha256(audit_raw).hexdigest() if audit_raw is not None else None
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
