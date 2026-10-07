#!/usr/bin/env python3
"""GARCH-family volatility forecasting for the Robinhood Codex trading skill.

Input: CSV with a close column (or configurable column).
Output: JSON with fitted model, forecast variance/volatility, regime hints,
and optional rolling holdout diagnostics.

Dependencies: numpy and scipy. No broker/account information is used.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, Tuple

import numpy as np
import scipy
from scipy.optimize import minimize

from price_audit import audit_prices


@dataclass
class Fit:
    model: str
    params: np.ndarray
    variance: np.ndarray
    loglik: float
    success: bool
    message: str


def gaussian_nll(returns: np.ndarray, var: np.ndarray) -> float:
    v = np.maximum(var, 1e-12)
    return float(0.5 * np.sum(np.log(2.0 * np.pi) + np.log(v) + returns**2 / v))


def stationary_var(returns: np.ndarray) -> float:
    v = float(np.var(returns, ddof=1))
    return max(v, 1e-8)


def garch_variance(params: np.ndarray, returns: np.ndarray) -> np.ndarray:
    omega, alpha, beta = params
    var = np.empty(len(returns), dtype=float)
    var[0] = stationary_var(returns)
    for t in range(1, len(returns)):
        var[t] = omega + alpha * returns[t - 1] ** 2 + beta * var[t - 1]
    return np.maximum(var, 1e-12)


def gjr_variance(params: np.ndarray, returns: np.ndarray) -> np.ndarray:
    omega, alpha, gamma, beta = params
    var = np.empty(len(returns), dtype=float)
    var[0] = stationary_var(returns)
    for t in range(1, len(returns)):
        neg = 1.0 if returns[t - 1] < 0 else 0.0
        var[t] = omega + alpha * returns[t - 1] ** 2 + gamma * neg * returns[t - 1] ** 2 + beta * var[t - 1]
    return np.maximum(var, 1e-12)


def egarch_variance(params: np.ndarray, returns: np.ndarray) -> np.ndarray:
    omega, alpha, gamma, beta = params
    log_var = np.empty(len(returns), dtype=float)
    log_var[0] = math.log(stationary_var(returns))
    e_abs_z = math.sqrt(2.0 / math.pi)
    for t in range(1, len(returns)):
        prev_var = math.exp(log_var[t - 1])
        z = returns[t - 1] / math.sqrt(max(prev_var, 1e-12))
        log_var[t] = (
            omega
            + beta * log_var[t - 1]
            + alpha * (abs(z) - e_abs_z)
            + gamma * z
        )
        log_var[t] = float(np.clip(log_var[t], -30.0, 30.0))
    return np.maximum(np.exp(log_var), 1e-12)


def fit_model(model: str, returns: np.ndarray) -> Fit:
    returns = np.asarray(returns, dtype=float)
    if len(returns) < 3 or not np.all(np.isfinite(returns)) or np.var(returns) <= 1e-12:
        raise ValueError("Need at least three finite, nonconstant returns")
    model = model.lower()
    v0 = stationary_var(returns)
    if model == "garch":
        fn = garch_variance
        x0 = np.array([v0 * 0.05, 0.08, 0.90], dtype=float)
        bounds = [(1e-10, max(v0 * 2, 1e-6)), (1e-8, 0.999), (1e-8, 0.999)]

        def cons(x):
            return 0.999 - x[1] - x[2]

        constraints = [{"type": "ineq", "fun": cons}]
    elif model == "gjr":
        fn = gjr_variance
        x0 = np.array([v0 * 0.03, 0.05, 0.05, 0.85], dtype=float)
        bounds = [(1e-10, max(v0 * 2, 1e-6)), (1e-8, 0.999), (0.0, 0.999), (1e-8, 0.999)]

        def cons(x):
            return 0.999 - x[1] - 0.5 * x[2] - x[3]

        constraints = [{"type": "ineq", "fun": cons}]
    elif model == "egarch":
        fn = egarch_variance
        x0 = np.array([0.0, 0.08, -0.05, 0.95], dtype=float)
        bounds = [(-1.0, 1.0), (-2.0, 2.0), (-2.0, 2.0), (0.0, 0.999)]
        constraints = []
    else:
        raise ValueError(f"Unsupported model: {model}")

    def objective(x: np.ndarray) -> float:
        try:
            var = fn(x, returns)
            if not np.all(np.isfinite(var)) or np.any(var <= 0):
                return 1e50
            return gaussian_nll(returns, var)
        except (OverflowError, FloatingPointError, ValueError):
            return 1e50

    result = minimize(objective, x0, method="SLSQP", bounds=bounds, constraints=constraints,
                      options={"maxiter": 2500, "ftol": 1e-10})
    params = result.x
    var = fn(params, returns)
    feasible = all(c["fun"](params) >= -1e-7 for c in constraints)
    ok = bool(result.success) and feasible and np.all(np.isfinite(var))
    return Fit(model, params, var, -objective(params), bool(ok), str(result.message))


def forecast(fit: Fit, returns: np.ndarray, horizon: int) -> np.ndarray:
    if not fit.success or horizon < 1 or int(horizon) != horizon:
        raise ValueError("Forecast requires a converged fit and positive integer horizon")
    if fit.model == "egarch" and horizon > 1:
        raise ValueError("EGARCH multi-step forecasts require simulation; use horizon=1")
    h = int(horizon)
    last_var = float(fit.variance[-1])
    last_r = float(returns[-1])
    out = []

    for step in range(h):
        if fit.model == "garch":
            omega, alpha, beta = fit.params
            next_var = omega + alpha * last_r**2 + beta * last_var if step == 0 else omega + (alpha + beta) * last_var
        elif fit.model == "gjr":
            omega, alpha, gamma, beta = fit.params
            neg = 1.0 if last_r < 0 else 0.0
            next_var = (omega + alpha * last_r**2 + gamma * neg * last_r**2 + beta * last_var
                        if step == 0 else omega + (alpha + 0.5 * gamma + beta) * last_var)
        else:
            omega, alpha, gamma, beta = fit.params
            z = last_r / math.sqrt(max(last_var, 1e-12))
            next_log = omega + beta * math.log(max(last_var, 1e-12)) + alpha * (abs(z) - math.sqrt(2 / math.pi)) + gamma * z
            next_var = math.exp(float(np.clip(next_log, -30.0, 30.0)))
        next_var = max(float(next_var), 1e-12)
        out.append(next_var)
        # Future shocks have zero mean but NONZERO expected squared magnitude.
        last_var = next_var
        last_r = 0.0
    return np.asarray(out)


def qlike(realized_var: np.ndarray, forecast_var: np.ndarray) -> float:
    rv = np.maximum(np.asarray(realized_var, dtype=float), 1e-12)
    fv = np.maximum(np.asarray(forecast_var, dtype=float), 1e-12)
    ratio = rv / fv
    return float(np.mean(ratio - np.log(ratio) - 1.0))


def holdout_validation(returns: np.ndarray, model: str, train: int, test: int) -> Dict[str, float]:
    """Fixed-parameter, sequential ONE-step holdout. Update only after observing each return."""
    if train < 3 or test < 1 or len(returns) < train + test:
        return {"status": "insufficient_data"}
    train_returns = returns[:train]
    realized = returns[train:train + test] ** 2
    fit = fit_model(model, train_returns)
    if not fit.success:
        return {"status": "fit_failed", "message": fit.message}
    predictions = []
    state = float(fit.variance[-1])
    last_return = float(train_returns[-1])
    for observed in returns[train:train + test]:
        one = Fit(model, fit.params, np.array([state]), fit.loglik, True, fit.message)
        state = float(forecast(one, np.array([last_return]), 1)[0])
        predictions.append(state)
        last_return = float(observed)
    forecast_var = np.asarray(predictions)
    baseline = np.full(test, stationary_var(train_returns))
    return {
        "status": "ok",
        "n": int(len(realized)),
        "qlike": qlike(realized, forecast_var),
        "mse": float(np.mean((realized - forecast_var) ** 2)),
        "baseline_qlike": qlike(realized, baseline),
        "beats_constant_variance": bool(qlike(realized, forecast_var) < qlike(realized, baseline)),
        "method": "fixed_parameter_sequential_one_step",
    }


def regime(forecast_vol: float, realized_vol: float) -> str:
    if realized_vol <= 0:
        return "UNKNOWN"
    ratio = forecast_vol / realized_vol
    if ratio < 0.70:
        return "LOW"
    if ratio < 1.30:
        return "NORMAL"
    if ratio < 1.90:
        return "ELEVATED"
    return "EXTREME"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", help="CSV containing close prices")
    ap.add_argument("--close-column", default="close")
    ap.add_argument("--model", choices=["garch", "gjr", "egarch", "auto"], default="garch")
    ap.add_argument("--horizon", type=int, default=1)
    ap.add_argument("--periods-per-year", type=float, default=252.0)
    ap.add_argument("--min-observations", type=int, default=250)
    ap.add_argument("--validation-test", type=int, default=40)
    ap.add_argument("--timestamp-column", default="timestamp")
    ap.add_argument("--data-audit", help="JSON audit tied to the exact CSV; absent audit is research-only")
    args = ap.parse_args()

    if args.horizon < 1 or args.min_observations < 30 or args.validation_test < 10:
        raise ValueError("Require horizon >= 1, training >= 30 and validation >= 10")
    if not math.isfinite(args.periods_per_year) or args.periods_per_year <= 0:
        raise ValueError("periods-per-year must be finite and positive")
    from datetime import datetime
    raw_csv = Path(args.csv).read_bytes()
    rows = list(csv.DictReader(io.StringIO(raw_csv.decode("utf-8-sig"), newline="")))
    prices, times = [], []
    for row in rows:
        price = float(row[args.close_column])
        if not math.isfinite(price) or price <= 0:
            raise ValueError("Invalid price row; do not silently drop or join across gaps")
        time = datetime.fromisoformat(row[args.timestamp_column].replace("Z", "+00:00"))
        if time.tzinfo is None or (times and time <= times[-1]):
            raise ValueError("Timestamps must include offsets and be unique and increasing")
        if row.get("synthetic", "false").lower() not in {"false", "0", ""}:
            raise ValueError("Synthetic bars require upstream data repair")
        prices.append(price)
        times.append(time)
    prices = np.asarray(prices)
    needed = args.min_observations + args.validation_test + 1
    if len(prices) < needed:
        raise ValueError(f"Need at least {needed} timestamped prices including holdout; found {len(prices)}")

    raw_audit = Path(args.data_audit).read_bytes() if args.data_audit else None
    metadata = json.loads(raw_audit.decode("utf-8-sig")) if raw_audit is not None else None
    data_quality = audit_prices(raw_csv, prices, times, metadata,
                                close_column=args.close_column, timestamp_column=args.timestamp_column,
                                periods_per_year=args.periods_per_year)

    returns = 100.0 * np.diff(np.log(prices))
    candidates = ["garch", "gjr", "egarch"] if args.model == "auto" else [args.model]
    if args.horizon > 1:
        if args.model == "egarch":
            raise ValueError("EGARCH supports horizon=1 only; simulation not implemented")
        candidates = [m for m in candidates if m != "egarch"]
    fits = {m: fit_model(m, returns) for m in candidates}

    validations = {}
    train_len = len(returns) - args.validation_test
    for m in candidates:
        validations[m] = holdout_validation(returns, m, train_len, args.validation_test)

    valid_models = [m for m in candidates if fits[m].success and validations[m].get("status") == "ok"]
    if args.model == "auto" and valid_models:
        selected = min(valid_models, key=lambda m: validations[m]["qlike"])
    elif args.model in valid_models:
        selected = args.model
    else:
        raise ValueError("No model converged with valid holdout diagnostics")

    fit = fits[selected]
    fc = forecast(fit, returns, args.horizon)
    forecast_daily_vol = np.sqrt(fc[0]) / 100.0
    realized_daily_vol = np.std(returns[-min(60, len(returns)):], ddof=1) / 100.0
    annualized = forecast_daily_vol * math.sqrt(args.periods_per_year)

    result = {
        "model": selected,
        "parameters": [float(x) for x in fit.params],
        "observations": int(len(returns)),
        "last_price": float(prices[-1]),
        "forecast_variance_percent_squared": [float(x) for x in fc],
        "forecast_daily_volatility": float(forecast_daily_vol),
        "forecast_annualized_volatility": float(annualized),
        "recent_realized_daily_volatility": float(realized_daily_vol),
        "regime": regime(forecast_daily_vol, realized_daily_vol),
        "fit_success": fit.success,
        "fit_message": fit.message,
        "log_likelihood": float(fit.loglik),
        "validation": validations,
        "forecast_period_volatility": float(forecast_daily_vol),
        "periods_per_year": args.periods_per_year,
        "innovation_distribution": "Gaussian; zero conditional mean",
        "eligible_as_sizing_input": bool(validations[selected]["beats_constant_variance"]
                                        and data_quality["eligible_for_sizing"]),
        "data_quality": data_quality,
        "selection_caveat": "Holdout used for model selection, not independent strategy performance proof",
        "last_timestamp": times[-1].isoformat(),
        "run_specification": {
            "implementation": "bundled-garch-2.2.0",
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "audit_helper_sha256": hashlib.sha256(Path(__file__).with_name("price_audit.py").read_bytes()).hexdigest(),
            "csv_sha256": data_quality["csv_sha256"],
            "audit_sha256": hashlib.sha256(raw_audit).hexdigest() if raw_audit is not None else None,
            "python": sys.version.split()[0], "numpy": np.__version__, "scipy": scipy.__version__,
            "close_column": args.close_column, "timestamp_column": args.timestamp_column,
            "first_timestamp": times[0].isoformat(), "last_timestamp": times[-1].isoformat(),
            "price_count": len(prices), "return_count": len(returns),
            "training_returns": train_len, "holdout_returns": args.validation_test,
            "training_last_return_end": times[train_len].isoformat(),
            "holdout_first_return_end": times[train_len + 1].isoformat(),
            "return_definition": "100 * log(P[t] / P[t-1]); zero mean; Gaussian innovations",
            "requested_model": args.model, "selected_model": selected, "horizon": args.horizon,
            "periods_per_year": args.periods_per_year,
            "variance_initialization": "sample variance ddof=1 on each fit sample",
            "optimizer": "SLSQP; maxiter=2500; ftol=1e-10; deterministic single start",
            "forecast_fit": "refit on all available returns after sequential prefix-only holdout",
            "realized_window_returns": min(60, len(returns)),
            "regime_ratio": float(forecast_daily_vol / realized_daily_vol),
            "regime_ratio_boundaries": [0.70, 1.30, 1.90],
        },
    }
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
