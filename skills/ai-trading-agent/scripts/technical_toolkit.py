"""Deterministic, causal OHLCV analysis. Standard library only; no data or broker I/O.

Run: python scripts/technical_toolkit.py --input request.json [--output result.json]
     [--chart chart.svg]. See references/technical-toolkit.md for conventions.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import html
import json
import math
import re
from pathlib import Path
import statistics


def number(value, name="number"):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name}: finite numeric value required")
    return float(value)


def period(value, name="period"):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name}: positive integer required")
    return value


def series(values):
    return [None if x is None else number(x) for x in values]


def rolling(values, n, reducer):
    """Full contiguous windows only. Nulls invalidate the affected windows."""
    n = period(n)
    values = series(values)
    result = [None] * len(values)
    for i in range(n - 1, len(values)):
        window = values[i - n + 1:i + 1]
        if all(x is not None for x in window):
            result[i] = reducer(window)
    return result


def sma(values, n):
    return rolling(values, n, statistics.fmean)


def smooth(values, n, alpha):
    n = period(n)
    alpha = number(alpha, "alpha")
    if not 0 < alpha <= 1:
        raise ValueError("alpha must be in (0, 1]")
    seed, previous, result = [], None, []
    for value in series(values):
        if value is None:
            seed, previous = [], None
        elif previous is None:
            seed.append(value)
            if len(seed) == n:
                previous = statistics.fmean(seed)
        else:
            previous += alpha * (value - previous)
        result.append(previous)
    return result


def ema(values, n):
    return smooth(values, n, 2 / (period(n) + 1))


def wilder(values, n):
    return smooth(values, n, 1 / period(n))


def rsi(values, n=14):
    n = period(n)
    values = series(values)
    gains, losses = [None], [None]
    for current, previous in zip(values[1:], values):
        change = None if current is None or previous is None else current - previous
        gains.append(None if change is None else max(change, 0))
        losses.append(None if change is None else max(-change, 0))
    if not values:
        return []
    gains, losses = wilder(gains, n), wilder(losses, n)
    return [None if gain is None or loss is None else
            (50.0 if gain == loss == 0 else 100.0 if loss == 0 else 100 - 100 / (1 + gain / loss))
            for gain, loss in zip(gains, losses)]


def macd(values, fast=12, slow=26, signal=9):
    if period(fast) >= period(slow):
        raise ValueError("MACD fast must be less than slow")
    a, b = ema(values, fast), ema(values, slow)
    line = [None if x is None or y is None else x - y for x, y in zip(a, b)]
    sig = ema(line, signal)
    return {"line": line, "signal": sig,
            "histogram": [None if x is None or y is None else x - y for x, y in zip(line, sig)]}


def bollinger(values, n=20, multiplier=2):
    multiplier = number(multiplier, "bollinger multiplier")
    if multiplier <= 0:
        raise ValueError("bollinger multiplier must be positive")
    mid, std = sma(values, n), rolling(values, n, statistics.pstdev)
    return {"middle": mid,
            "upper": [None if x is None else x + multiplier * s for x, s in zip(mid, std)],
            "lower": [None if x is None else x - multiplier * s for x, s in zip(mid, std)]}


def validate_bars(bars):
    if not isinstance(bars, list) or not bars:
        raise ValueError("bars: nonempty chronological list required")
    result, previous, date_only, seen_sessions, active_session = [], None, None, set(), None
    for i, raw in enumerate(bars):
        if not isinstance(raw, dict):
            raise ValueError(f"bar {i}: object required")
        if set(raw) - {"timestamp", "session", "open", "high", "low", "close", "volume"}:
            raise ValueError(f"bar {i}: unknown fields")
        stamp = raw.get("timestamp")
        if not isinstance(stamp, str):
            raise ValueError(f"bar {i}: ISO timestamp required")
        is_date = re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", stamp) is not None
        try:
            parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"bar {i}: invalid ISO timestamp") from exc
        if is_date:
            parsed = parsed.replace(tzinfo=timezone.utc)
        elif parsed.tzinfo is None:
            raise ValueError(f"bar {i}: intraday timestamp requires timezone offset")
        if date_only is not None and date_only != is_date:
            raise ValueError("do not mix date-only and intraday timestamps")
        date_only = is_date
        if previous is not None and parsed <= previous:
            raise ValueError("bars must have strictly increasing unique timestamps")
        previous = parsed
        row = {key: number(raw.get(key), f"bar {i}.{key}")
               for key in ("open", "high", "low", "close", "volume")}
        if min(row[k] for k in ("open", "high", "low", "close")) <= 0:
            raise ValueError("OHLC prices must be positive")
        if row["volume"] < 0 or not row["low"] <= min(row["open"], row["close"]) <= max(row["open"], row["close"]) <= row["high"]:
            raise ValueError(f"bar {i}: inconsistent OHLC or negative volume")
        row["timestamp"] = stamp
        session = raw.get("session")
        if session is not None:
            if not isinstance(session, str) or not session.strip():
                raise ValueError("session must be a nonempty explicit exchange-session label")
            if session != active_session:
                if session in seen_sessions:
                    raise ValueError("session labels must be contiguous")
                seen_sessions.add(session)
                active_session = session
            row["session"] = session
        result.append(row)
    if any("session" in x for x in result) and not all("session" in x for x in result):
        raise ValueError("session labels must be present on all bars or none")
    return result


def true_range(bars):
    return [bar["high"] - bar["low"] if i == 0 else max(
        bar["high"] - bar["low"], abs(bar["high"] - bars[i - 1]["close"]),
        abs(bar["low"] - bars[i - 1]["close"])) for i, bar in enumerate(bars)]


def atr(bars, n=14):
    return wilder(true_range(bars), n)


def adx(bars, n=14):
    plus, minus, tr = [None], [None], [None]
    for previous, current in zip(bars, bars[1:]):
        up, down = current["high"] - previous["high"], previous["low"] - current["low"]
        plus.append(up if up > down and up > 0 else 0)
        minus.append(down if down > up and down > 0 else 0)
        tr.append(max(current["high"] - current["low"], abs(current["high"] - previous["close"]),
                      abs(current["low"] - previous["close"])))
    plus, minus, tr = wilder(plus, n), wilder(minus, n), wilder(tr, n)
    pdi, mdi, dx = [], [], []
    for p, m, t in zip(plus, minus, tr):
        p = None if t is None else (0.0 if t == 0 else 100 * p / t)
        m = None if t is None else (0.0 if t == 0 else 100 * m / t)
        pdi.append(p); mdi.append(m)
        dx.append(None if p is None else (0.0 if p + m == 0 else 100 * abs(p - m) / (p + m)))
    return {"plus_di": pdi, "minus_di": mdi, "adx": wilder(dx, n)}


def stochastic(bars, n=14, smooth_k=3, smooth_d=3):
    highs = rolling([x["high"] for x in bars], n, max)
    lows = rolling([x["low"] for x in bars], n, min)
    raw = [None if h is None or h == l else 100 * (b["close"] - l) / (h - l)
           for b, h, l in zip(bars, highs, lows)]
    k = sma(raw, smooth_k)
    return {"raw_k": raw, "k": k, "d": sma(k, smooth_d)}


def vwap(bars, anchor_index=None):
    """HLC3 bar-volume approximation. Sessions are explicit, never inferred."""
    if anchor_index is not None:
        if isinstance(anchor_index, bool) or not isinstance(anchor_index, int) or not 0 <= anchor_index < len(bars):
            raise ValueError("anchor_index must identify an existing bar")
    elif not all("session" in x for x in bars):
        return [None] * len(bars)
    result, total_pv, total_volume, session = [], 0.0, 0.0, None
    for i, bar in enumerate(bars):
        if anchor_index is not None and i < anchor_index:
            result.append(None)
            continue
        if anchor_index is None and bar["session"] != session:
            total_pv, total_volume, session = 0.0, 0.0, bar["session"]
        total_pv += (bar["high"] + bar["low"] + bar["close"]) / 3 * bar["volume"]
        total_volume += bar["volume"]
        result.append(total_pv / total_volume if total_volume else None)
    return result


def obv(bars):
    result, value = [], 0.0
    for i, bar in enumerate(bars):
        if i:
            change = bar["close"] - bars[i - 1]["close"]
            value += bar["volume"] * (1 if change > 0 else -1 if change < 0 else 0)
        result.append(value)
    return result


def ichimoku(bars, conversion=9, base=26, span=52, displacement=26):
    displacement = period(displacement, "displacement")
    def midpoint(n):
        hi, lo = rolling([x["high"] for x in bars], n, max), rolling([x["low"] for x in bars], n, min)
        return [None if h is None else (h + l) / 2 for h, l in zip(hi, lo)]
    tenkan, kijun, b = midpoint(conversion), midpoint(base), midpoint(span)
    a = [None if t is None or k is None else (t + k) / 2 for t, k in zip(tenkan, kijun)]
    # Store projections when known. Never backfill future close into old rows.
    return {"conversion": tenkan, "base": kijun, "span_a_projected": a, "span_b_projected": b,
            "cloud_a_now": [None if i < displacement else a[i - displacement] for i in range(len(bars))],
            "cloud_b_now": [None if i < displacement else b[i - displacement] for i in range(len(bars))],
            "lag_comparison_close": [None if i < displacement else bars[i - displacement]["close"] for i in range(len(bars))]}


def support_resistance(bars, lookback=20):
    """Prior-window extremes, excluding the current bar; no hindsight pivots."""
    hi, lo = rolling([x["high"] for x in bars], lookback, max), rolling([x["low"] for x in bars], lookback, min)
    return {"resistance": [None] + hi[:-1], "support": [None] + lo[:-1]}


def fibonacci(bars, start_index, end_index, direction):
    for name, value in (("start_index", start_index), ("end_index", end_index)):
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < len(bars):
            raise ValueError(f"{name} must identify a bar")
    if start_index >= end_index or direction not in ("up", "down"):
        raise ValueError("Fibonacci requires start < end and direction up or down")
    start = bars[start_index]["low" if direction == "up" else "high"]
    end = bars[end_index]["high" if direction == "up" else "low"]
    if (end - start) * (1 if direction == "up" else -1) <= 0:
        raise ValueError("Fibonacci swing endpoints conflict with direction")
    return {"start_index": start_index, "end_index": end_index, "available_after_close_index": end_index,
            "start_price": start, "end_price": end, "direction": direction,
            "retracements": {str(r): end - r * (end - start) for r in (0, .236, .382, .5, .618, .786, 1)},
            "extensions_from_start": {str(r): start + r * (end - start) for r in (1.272, 1.618, 2.618)},
            "scope": "User-selected swing geometry; no predictive validation or automatic pivot selection."}


def candlesticks(bars):
    result = []
    for i, bar in enumerate(bars):
        o, h, l, c = [bar[k] for k in ("open", "high", "low", "close")]
        body, width, lower, upper = abs(c - o), h - l, min(o, c) - l, h - max(o, c)
        labels = []
        if width == 0:
            labels.append("flat")
        elif body <= .1 * width:
            labels.append("doji_geometry")
        if body > 0 and lower >= 2 * body and upper <= .25 * body:
            labels.append("hammer_geometry")
        if body > 0 and upper >= 2 * body and lower <= .25 * body:
            labels.append("inverted_hammer_geometry")
        if i:
            p = bars[i - 1]
            if c > o and p["close"] < p["open"] and o <= p["close"] and c >= p["open"] and body > abs(p["close"] - p["open"]):
                labels.append("bullish_body_engulfing")
            if c < o and p["close"] > p["open"] and o >= p["close"] and c <= p["open"] and body > abs(p["close"] - p["open"]):
                labels.append("bearish_body_engulfing")
        result.append(labels)
    return result


def volume_profile(bars, bins=20, start_index=0, end_index=None):
    bins = period(bins, "bins")
    if bins > 200:
        raise ValueError("bins must be <= 200")
    end_index = len(bars) - 1 if end_index is None else end_index
    if any(isinstance(v, bool) or not isinstance(v, int) for v in (start_index, end_index)) or not 0 <= start_index <= end_index < len(bars):
        raise ValueError("invalid volume-profile window")
    selected = bars[start_index:end_index + 1]
    lo, hi = min(x["low"] for x in selected), max(x["high"] for x in selected)
    count = 1 if hi == lo else bins
    width = (hi - lo) / count
    volumes = [0.0] * count
    for bar in selected:
        if bar["high"] == bar["low"]:
            index = 0 if width == 0 else min(count - 1, int((bar["low"] - lo) / width))
            volumes[index] += bar["volume"]
        else:
            for j in range(count):
                overlap = max(0, min(bar["high"], lo + (j + 1) * width) - max(bar["low"], lo + j * width))
                volumes[j] += bar["volume"] * overlap / (bar["high"] - bar["low"])
    profile = [{"low": lo + j * width, "high": lo + (j + 1) * width, "volume": v} for j, v in enumerate(volumes)]
    return {"method": "uniform_bar_range_approximation_not_trade_volume_at_price", "bins": profile,
            "start_index": start_index, "available_after_close_index": end_index,
            "total_input_volume": sum(x["volume"] for x in selected), "total_allocated_volume": sum(volumes),
            "point_of_control_bin": None if sum(volumes) == 0 else max(range(count), key=volumes.__getitem__)}


def depth_imbalance(bids, asks):
    """Aggregate only the supplied snapshot levels; no inferred order flow."""
    def levels(raw):
        if not isinstance(raw, list) or not raw:
            raise ValueError("nonempty depth levels required")
        result = []
        for item in raw:
            if not isinstance(item, dict) or set(item) != {"price", "size"}:
                raise ValueError("depth level requires exactly price and size")
            p, q = number(item.get("price"), "depth price"), number(item.get("size"), "depth size")
            if p <= 0 or q < 0:
                raise ValueError("invalid depth price/size")
            result.append((p, q))
        if len({p for p, _ in result}) != len(result):
            raise ValueError("duplicate depth prices")
        return result
    bid, ask = levels(bids), levels(asks)
    best_bid, best_ask = max(p for p, _ in bid), min(p for p, _ in ask)
    if best_bid >= best_ask:
        raise ValueError("crossed or locked snapshot unsupported")
    b, a = sum(q for _, q in bid), sum(q for _, q in ask)
    return {"bid_size": b, "ask_size": a, "size_imbalance": None if b + a == 0 else (b - a) / (b + a),
            "spread": best_ask - best_bid, "mid": (best_ask + best_bid) / 2,
            "scope": "supplied snapshot only; depth selection must match across sides; not executed order flow"}


def replay(bars, signals, initial_cash=10000, fee_bps=0, slippage_bps=0):
    """Long/flat transitions: close t target fills open t+1. Fractional shares."""
    if not isinstance(signals, list) or len(signals) != len(bars):
        raise ValueError("one signal per bar required")
    if any(x is not None and (isinstance(x, bool) or x not in (0, 1)) for x in signals):
        raise ValueError("signals must be 0 (flat), 1 (long), or null (hold target)")
    cash = number(initial_cash, "initial_cash")
    fee, slip = number(fee_bps, "fee_bps") / 10000, number(slippage_bps, "slippage_bps") / 10000
    if cash <= 0 or not 0 <= fee < 1 or not 0 <= slip < 1:
        raise ValueError("initial cash > 0 and costs in [0,10000) bps required")
    shares, target, trades, curve, fees = 0.0, 0, [], [], 0.0
    for i, bar in enumerate(bars):
        if i and signals[i - 1] is not None:
            target = signals[i - 1]
        if target and shares == 0:
            price = bar["open"] * (1 + slip)
            shares = cash / (price * (1 + fee))
            charge = shares * price * fee
            trades.append({"side": "buy", "decision_index": i - 1, "fill_index": i, "price": price, "shares": shares, "fee": charge})
            fees += charge
            cash = 0.0
        elif not target and shares > 0:
            price = bar["open"] * (1 - slip)
            charge = shares * price * fee
            cash = shares * price - charge
            trades.append({"side": "sell", "decision_index": i - 1, "fill_index": i, "price": price, "shares": shares, "fee": charge})
            shares = 0.0
            fees += charge
        curve.append(cash + shares * bar["close"])
    peak, drawdown = initial_cash, 0.0
    for equity in curve:
        peak = max(peak, equity)
        drawdown = min(drawdown, equity / peak - 1)
    return {"trades": trades, "equity": curve, "ending_cash": cash, "ending_shares": shares,
            "parameters": {"initial_cash": initial_cash, "fee_bps": fee_bps, "slippage_bps": slippage_bps},
            "signals": signals,
            "total_fees": fees, "total_return": curve[-1] / initial_cash - 1, "max_drawdown": drawdown,
            "last_signal_unexecuted": signals[-1], "valuation": "last close mark; open position is not liquidated",
            "scope": "research replay, long/flat fractional shares, no financing/dividends/taxes/market-impact model"}


DEFAULTS = {"sma_period": 20, "ema_period": 20, "rsi_period": 14,
            "macd_fast": 12, "macd_slow": 26, "macd_signal": 9,
            "bollinger_period": 20, "bollinger_multiplier": 2,
            "atr_period": 14, "adx_period": 14, "stochastic_period": 14,
            "stochastic_smooth_k": 3, "stochastic_smooth_d": 3,
            "ichimoku_conversion": 9, "ichimoku_base": 26, "ichimoku_span": 52,
            "ichimoku_displacement": 26, "support_resistance_lookback": 20}


def resolve_request(request):
    """Materialize every optional numeric default before freezing an input hash.

    Does not compute indicators. Absent optional analyses remain absent; explicit
    nulls are not converted into defaults. Full value validation is in analyze.
    """
    if not isinstance(request, dict):
        raise ValueError("request must be an object")
    result = deepcopy(request)
    params = result.get("parameters", {})
    if not isinstance(params, dict) or set(params) - DEFAULTS.keys():
        raise ValueError("unknown or malformed parameters")
    result["parameters"] = dict(DEFAULTS, **params)
    if "volume_profile" in result:
        options = result["volume_profile"]
        if not isinstance(options, dict) or set(options) - {"bins", "start_index", "end_index"}:
            raise ValueError("unknown or malformed volume_profile options")
        if not isinstance(result.get("bars"), list) or not result["bars"]:
            raise ValueError("volume_profile requires nonempty bars")
        result["volume_profile"] = dict(bins=20, start_index=0, end_index=len(result["bars"]) - 1)
        result["volume_profile"].update(options)
    if "replay" in result:
        options = result["replay"]
        if not isinstance(options, dict) or set(options) - {"strategy", "signals", "initial_cash", "fee_bps", "slippage_bps"}:
            raise ValueError("unknown or malformed replay options")
        result["replay"] = dict(initial_cash=10000, fee_bps=0, slippage_bps=0)
        result["replay"].update(options)
    return result


def analyze(request):
    request = resolve_request(request)
    allowed = {"symbol", "timeframe", "price_basis", "price_unit", "volume_unit", "timestamp_basis", "finalized_bars", "bars", "parameters",
               "vwap_anchor_index", "fibonacci", "volume_profile", "depth_snapshot", "replay"}
    if set(request) - allowed:
        raise ValueError("unknown request fields: " + ", ".join(sorted(set(request) - allowed)))
    for key in ("symbol", "timeframe", "price_basis", "price_unit", "volume_unit"):
        if not isinstance(request.get(key), str) or not request[key].strip():
            raise ValueError(f"{key}: explicit metadata required")
    if request.get("timestamp_basis") not in ("bar_open", "bar_close"):
        raise ValueError("timestamp_basis must be bar_open or bar_close")
    if request.get("finalized_bars") is not True:
        raise ValueError("finalized_bars must be true; incomplete bars are unsupported")
    bars = validate_bars(request.get("bars"))
    supplied = request.get("parameters", {})
    if not isinstance(supplied, dict) or set(supplied) - DEFAULTS.keys():
        raise ValueError("unknown or malformed parameters")
    p = dict(DEFAULTS, **supplied)
    for key, value in p.items():
        if key != "bollinger_multiplier":
            period(value, key)
    close = [b["close"] for b in bars]
    columns = {"sma": sma(close, p["sma_period"]), "ema": ema(close, p["ema_period"]),
               "rsi": rsi(close, p["rsi_period"]), "atr": atr(bars, p["atr_period"]),
               "session_vwap": vwap(bars), "obv": obv(bars), "candlestick_labels": candlesticks(bars)}
    groups = {"macd": macd(close, p["macd_fast"], p["macd_slow"], p["macd_signal"]),
              "bollinger": bollinger(close, p["bollinger_period"], p["bollinger_multiplier"]),
              "directional": adx(bars, p["adx_period"]),
              "stochastic": stochastic(bars, p["stochastic_period"], p["stochastic_smooth_k"], p["stochastic_smooth_d"]),
              "ichimoku": ichimoku(bars, p["ichimoku_conversion"], p["ichimoku_base"], p["ichimoku_span"], p["ichimoku_displacement"]),
              "levels": support_resistance(bars, p["support_resistance_lookback"])}
    for group, values in groups.items():
        columns.update({f"{group}_{key}": value for key, value in values.items()})
    if "vwap_anchor_index" in request:
        if request["vwap_anchor_index"] is None:
            raise ValueError("vwap_anchor_index cannot be null")
        columns["anchored_vwap"] = vwap(bars, request["vwap_anchor_index"])
    rows = [{"timestamp": b["timestamp"], **{key: values[i] for key, values in columns.items()}} for i, b in enumerate(bars)]
    warnings = ["Supplied bars only; verify source, corporate-action adjustments, timezone, and bar completeness.",
                "Periods count observations. Missing calendar bars are not filled or detected without an exchange calendar.",
                "Indicators and geometric labels do not establish predictive accuracy or a trade recommendation."]
    if not all("session" in b for b in bars):
        warnings.append("Session VWAP unavailable: explicit exchange-session labels absent.")
    result = {"schema": "technical-toolkit-v1", "symbol": request["symbol"], "timeframe": request["timeframe"],
              "price_basis": request["price_basis"], "price_unit": request["price_unit"], "volume_unit": request["volume_unit"],
              "timestamp_basis": request["timestamp_basis"],
              "finalized_bars": True, "parameters": p, "rows": rows, "warnings": warnings,
              "conventions": {"ema_seed": "SMA of first full contiguous window", "wilder_alpha": "1/n, SMA seed",
                              "bollinger_std": "population", "flat_rsi": 50, "flat_stochastic": None,
                              "vwap": "HLC3 bar-volume approximation", "obv_start": 0,
                              "ichimoku": "projections stored at calculation time; no future-close backfill",
                              "numeric_precision": "IEEE-754 double, unrounded JSON; compare with stated numeric tolerance"}}
    for key, func in (("fibonacci", fibonacci), ("volume_profile", volume_profile)):
        if key in request:
            if not isinstance(request[key], dict):
                raise ValueError(f"{key} must be an object")
            result[key] = func(bars, **request[key])
    if "depth_snapshot" in request:
        snapshot = request["depth_snapshot"]
        if not isinstance(snapshot, dict) or set(snapshot) != {"as_of", "bids", "asks"} or not isinstance(snapshot.get("as_of"), str):
            raise ValueError("depth_snapshot requires as_of, bids, asks")
        try:
            snapshot_time = datetime.fromisoformat(snapshot["as_of"].replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("depth_snapshot.as_of requires ISO timestamp") from exc
        if snapshot_time.tzinfo is None:
            raise ValueError("depth_snapshot.as_of requires timezone offset")
        result["depth_snapshot"] = {"as_of": snapshot["as_of"], **depth_imbalance(snapshot.get("bids"), snapshot.get("asks"))}
    if "replay" in request:
        if not isinstance(request["replay"], dict):
            raise ValueError("replay must be an object")
        config = dict(request["replay"])
        strategy = config.pop("strategy", None)
        if strategy is not None:
            if strategy != "close_above_sma" or "signals" in config:
                raise ValueError("replay strategy must be close_above_sma without supplied signals")
            config["signals"] = [None if m is None else int(c > m) for c, m in zip(close, columns["sma"])]
        result["replay"] = replay(bars, **config)
    return result


OPERATIONS = {"analyze": analyze}


def chart_svg(bars, result, title="Technical analysis"):
    """Static price chart. SVG has no scripts, links, or external resources."""
    width, height, left, top, plot_width, plot_height = 1000, 540, 70, 60, 900, 410
    values = [b[k] for b in bars for k in ("high", "low")]
    for row in result["rows"]:
        values.extend(row[k] for k in ("sma", "ema", "bollinger_upper", "bollinger_lower") if row[k] is not None)
    lo, hi = min(values), max(values)
    pad = max((hi - lo) * .05, hi * .01)
    lo, hi = lo - pad, hi + pad
    def x(i): return left + (i + .5) * plot_width / len(bars)
    def y(price): return top + (hi - price) / (hi - lo) * plot_height
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
             '<rect width="100%" height="100%" fill="white"/>',
             f'<text x="70" y="26" font-family="sans-serif" font-size="20">{html.escape(title)}</text>',
             '<text x="70" y="46" font-family="sans-serif" font-size="12">Candles; SMA blue; EMA orange; Bollinger gray. Supplied bars, no predictive claim.</text>']
    for i in range(6):
        price = lo + (hi - lo) * i / 5
        parts.append(f'<line x1="{left}" y1="{y(price):.2f}" x2="970" y2="{y(price):.2f}" stroke="#eee"/><text x="5" y="{y(price):.2f}" font-family="sans-serif" font-size="11">{price:.3f}</text>')
    body_width = max(.5, min(10, plot_width / len(bars) * .65))
    for i, bar in enumerate(bars):
        color = "#16834a" if bar["close"] >= bar["open"] else "#b33b35"
        parts.append(f'<line x1="{x(i):.2f}" x2="{x(i):.2f}" y1="{y(bar["high"]):.2f}" y2="{y(bar["low"]):.2f}" stroke="{color}"/>')
        parts.append(f'<rect x="{x(i)-body_width/2:.2f}" y="{min(y(bar["open"]),y(bar["close"])):.2f}" width="{body_width:.2f}" height="{max(.5,abs(y(bar["open"])-y(bar["close"]))):.2f}" fill="{color}"/>')
    for key, color in (("bollinger_upper", "#999"), ("bollinger_lower", "#999"), ("sma", "#246bc4"), ("ema", "#cf7718")):
        path, started = [], False
        for i, row in enumerate(result["rows"]):
            if row[key] is None:
                started = False
            else:
                path.append(f'{"L" if started else "M"}{x(i):.2f},{y(row[key]):.2f}')
                started = True
        parts.append(f'<path d="{" ".join(path)}" fill="none" stroke="{color}" stroke-width="1.5"/>')
    parts.append(f'<text x="70" y="500" font-family="sans-serif" font-size="12">{html.escape(bars[0]["timestamp"])} to {html.escape(bars[-1]["timestamp"])} | {html.escape(result["timeframe"])} | {html.escape(result["price_basis"])}</text></svg>')
    return "\n".join(parts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output")
    parser.add_argument("--chart")
    args = parser.parse_args()
    try:
        input_path = Path(args.input).resolve()
        output_paths = [Path(value).resolve() for value in (args.output, args.chart) if value]
        if input_path in output_paths or len(set(output_paths)) != len(output_paths):
            raise ValueError("output paths must be distinct from each other and the frozen input")
        if any(path.exists() for path in output_paths):
            raise ValueError("output exists; use new output paths to preserve prior evidence")
        request = json.loads(input_path.read_text(encoding="utf-8-sig"))
        result = analyze(request)
        serialized = json.dumps(result, indent=2, allow_nan=False)
        if args.output:
            with Path(args.output).open("x", encoding="utf-8") as stream:
                stream.write(serialized + "\n")
        else:
            print(serialized)
        if args.chart:
            with Path(args.chart).open("x", encoding="utf-8") as stream:
                stream.write(chart_svg(validate_bars(request["bars"]), result, request["symbol"]))
    except (ValueError, TypeError, KeyError, OSError) as exc:
        parser.exit(2, f"technical_toolkit: {exc}\n")


if __name__ == "__main__":
    main()
