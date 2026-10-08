"""Causal, single-symbol research/replay harness for two unvalidated long-only setups.

Bar timestamp is bar END; session_open/session_close are official calendar times.
Signals use completed bars; entries and signal exits occur no earlier than the next
bar open. Fixed friction and OHLC ambiguity assumptions are explicit, not L2 fills.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from risk_engine import timestamp


@dataclass(frozen=True)
class Bar:
    end: object
    session_open: object
    session_close: object
    open: float
    high: float
    low: float
    close: float
    volume: float


def read_bars(path):
    bars = []
    with open(path, newline="", encoding="utf-8-sig") as source:
        for row in csv.DictReader(source):
            values = [float(row[k]) for k in ("open", "high", "low", "close", "volume")]
            if not all(math.isfinite(v) for v in values) or min(values[:4]) <= 0 or values[4] < 0:
                raise ValueError("Nonfinite, negative, or zero price in bar")
            o, h, l, c, v = values
            if l > min(o, c) or h < max(o, c) or l > h:
                raise ValueError("Inconsistent OHLC")
            bar = Bar(timestamp(row["timestamp"]), timestamp(row["session_open"]),
                      timestamp(row["session_close"]), *values)
            if not bar.session_open < bar.end <= bar.session_close:
                raise ValueError("Bar outside official session")
            if bars and bar.end <= bars[-1].end:
                raise ValueError("Duplicate or unordered bars")
            if row.get("synthetic", "false").lower() not in {"false", "0", ""}:
                raise ValueError("Synthetic bar rejected")
            bars.append(bar)
    if not bars:
        raise ValueError("Empty price data")
    return bars


def signal(history, strategy, lookback=20, opening_bars=3, bar_minutes=5):
    """Pure function: history contains only completed bars available at decision time."""
    if not history:
        return None
    bar = history[-1]
    if bar.volume <= 0:
        return None
    if strategy == "opening_range_breakout":
        session = [b for b in history if b.session_open == bar.session_open]
        step = timedelta(minutes=bar_minutes)
        if len(session) <= opening_bars or session[0].end != bar.session_open + step:
            return None
        if any(b.end - a.end != step for a, b in zip(session, session[1:])):
            return None
        if bar.end >= bar.session_close - timedelta(minutes=30):
            return None
        base = session[:opening_bars]
        top, bottom = max(b.high for b in base), min(b.low for b in base)
        average_volume = sum(b.volume for b in base) / len(base)
        if session[-2].close <= top < bar.close and bar.volume >= 1.5 * average_volume and average_volume > 0:
            return {"action": "enter", "stop": bottom, "target": bar.close + 2.5 * (bar.close - bottom),
                    "entry_limit": bar.close * 1.001, "setup": strategy}
    elif strategy == "sma_trend":
        if len(history) < lookback + 1:
            return None
        # Daily strategy: one completed regular-session bar per trading session.
        sample = history[-lookback - 1:]
        if len({b.session_open for b in sample}) != len(sample):
            raise ValueError("sma_trend requires daily bars")
        current_mean = sum(b.close for b in history[-lookback:]) / lookback
        previous_mean = sum(b.close for b in history[-lookback - 1:-1]) / lookback
        if bar.close > current_mean and history[-2].close <= previous_mean:
            stop = min(b.low for b in history[-5:])
            if stop < bar.close:
                return {"action": "enter", "stop": stop, "target": None,
                        "entry_limit": bar.close * 1.005, "setup": strategy}
        if bar.close < current_mean:
            return {"action": "exit", "setup": strategy}
    else:
        raise ValueError("Unknown strategy")
    return None


def replay(bars, strategy, initial_cash=100000, risk_fraction=0.001,
           capital_fraction=0.05, slippage_bps=5, fee_per_share=0.005,
           lookback=20, opening_bars=3, bar_minutes=5, trade_start=0):
    """One position, one symbol; no leverage, one intraday entry per session.

    This price replay is not a cash-account settlement model. Proceeds enter ledger
    cash on exit; overnight residuals, holidays and multi-symbol cash reuse require
    separate settlement validation. It does not model the configurable intraday
    settled-cash reserve. Production uses broker-confirmed settled funds. Open positions at end are marked, never fabricated as sold.
    """
    if not bars or initial_cash <= 0 or not 0 < risk_fraction <= 1 or not 0 < capital_fraction <= 1:
        raise ValueError("Invalid capital or risk configuration")
    if slippage_bps < 0 or fee_per_share < 0 or lookback < 2 or opening_bars < 1 or bar_minutes <= 0:
        raise ValueError("Invalid model settings")
    if not 0 <= trade_start < len(bars):
        raise ValueError("Invalid trade start")
    if not all(math.isfinite(float(v)) for v in (initial_cash, risk_fraction, capital_fraction, slippage_bps, fee_per_share)):
        raise ValueError("Nonfinite model settings")
    slip = slippage_bps / 10000
    cash, peak, max_dd = float(initial_cash), float(initial_cash), 0.0
    position = None
    pending = None
    used_sessions = set()
    trades, curve, events = [], [], []

    def exit_position(price, reason, bar):
        nonlocal cash, position
        proceeds = position["quantity"] * (price - fee_per_share)
        cash += proceeds
        pnl = proceeds - position["cost"]
        trades.append({**position, "exit_time": bar.end.isoformat(), "exit_price": price,
                       "pnl": pnl, "reason": reason})
        position = None

    for i, bar in enumerate(bars):
        if i < trade_start:
            continue
        if position and strategy == "opening_range_breakout" and position["session"] != bar.session_open.isoformat():
            events.append("overnight_residual_due_to_missing_or_illiquid_exit_bar")
            if bar.volume > 0:
                exit_position(bar.open * (1 - slip), "overdue_session_exit", bar)
        if pending and bar.volume > 0:
            if pending["action"] == "exit" and position:
                exit_position(bar.open * (1 - slip), "signal_next_open", bar)
            elif pending["action"] == "enter" and position is None:
                same_session = pending["session"] == bar.session_open.isoformat()
                next_expected_bar = bar.end == timestamp(pending["signal_time"]) + timedelta(minutes=bar_minutes)
                permitted = strategy != "opening_range_breakout" or (
                    same_session and next_expected_bar and bar.session_open not in used_sessions)
                if strategy == "opening_range_breakout" and not permitted:
                    events.append("intraday_entry_expired_or_session_already_used")
                price = bar.open * (1 + slip)
                if permitted and pending["stop"] < price <= pending["entry_limit"]:
                    unit_risk = price - pending["stop"] + price * slip + 2 * fee_per_share
                    quantity = math.floor(min(cash * risk_fraction / unit_risk,
                                              cash * capital_fraction / (price + fee_per_share)))
                    if quantity > 0:
                        cost = quantity * (price + fee_per_share)
                        cash -= cost
                        position = {"quantity": quantity, "entry_price": price, "cost": cost,
                                    "entry_time": (bar.session_open if strategy == "sma_trend" else bar.end - timedelta(minutes=bar_minutes)).isoformat(),
                                    "entry_bar_end": bar.end.isoformat(), "session": bar.session_open.isoformat(),
                                    "stop": pending["stop"], "target": pending["target"],
                                    "signal_time": pending["signal_time"]}
                        used_sessions.add(bar.session_open)
        pending = None
        if position and bar.volume > 0:
            # If both barriers are touched, assume the adverse stop was first.
            if bar.low <= position["stop"]:
                exit_position(min(bar.open, position["stop"]) * (1 - slip), "stop_or_gap", bar)
            elif position["target"] is not None and bar.high >= position["target"] * (1 + slip):
                exit_position(position["target"], "target_limit", bar)
            elif strategy == "opening_range_breakout" and bar.end >= bar.session_close - timedelta(minutes=10):
                exit_position(bar.close * (1 - slip), "scheduled_session_exit", bar)
        s = signal(bars[:i + 1], strategy, lookback, opening_bars, bar_minutes)
        if s and ((s["action"] == "enter" and position is None) or (s["action"] == "exit" and position)):
            pending = {**s, "session": bar.session_open.isoformat(), "signal_time": bar.end.isoformat()}
        equity = cash + (position["quantity"] * bar.close if position else 0)
        peak = max(peak, equity)
        max_dd = max(max_dd, 1 - equity / peak)
        curve.append({"timestamp": bar.end.isoformat(), "equity": equity})
    wins = [t["pnl"] for t in trades if t["pnl"] > 0]
    losses = [-t["pnl"] for t in trades if t["pnl"] < 0]
    benchmark_qty = math.floor(initial_cash / (bars[trade_start].open * (1 + slip) + fee_per_share))
    benchmark_cash = initial_cash - benchmark_qty * (bars[trade_start].open * (1 + slip) + fee_per_share)
    benchmark_value = benchmark_cash + benchmark_qty * bars[-1].close
    return {"strategy": strategy, "final_equity": curve[-1]["equity"],
            "return": curve[-1]["equity"] / initial_cash - 1, "max_drawdown": max_dd,
            "closed_trades": len(trades), "win_rate": len(wins) / len(trades) if trades else None,
            "profit_factor": sum(wins) / sum(losses) if losses else None,
            "mean_trade_pnl": sum(t["pnl"] for t in trades) / len(trades) if trades else None,
            "buy_hold_return": benchmark_value / initial_cash - 1,
            "benchmark_caveat": "Full-capital buy-and-hold, entry friction, marked terminal value; different exposure, no dividends",
            "open_position": position, "events": sorted(set(events)), "trades": trades, "equity_curve": curve,
            "execution_time_resolution": "Entry at modeled bar open; exit_time labels the containing bar end, not an observed tick",
            "assumptions": {"slippage_bps": slippage_bps, "fee_per_share": fee_per_share,
                            "capital_fraction": capital_fraction, "risk_fraction": risk_fraction,
                            "intrabar_ambiguity": "stop_first", "queue_or_depth_model": False,
                            "broker_settlement_calendar_modeled": False,
                            "settled_cash_reserve_modeled": False},
            "validated_for_live": False}


def walk_forward(bars, strategy, train_bars=60, test_bars=20, **kwargs):
    """Frozen-rule expanding history, nonoverlapping forward windows, one-bar embargo.

    There is no optimizer. Each test fold starts flat and resets cash; fold returns
    must not be presented as a continuous portfolio track record.
    """
    if train_bars < 2 or test_bars < 2:
        raise ValueError("Invalid fold sizes")
    folds = []
    for start in range(train_bars + 1, len(bars) - test_bars + 1, test_bars):
        result = replay(bars[:start + test_bars], strategy, trade_start=start, **kwargs)
        folds.append({"train_end": bars[start - 2].end.isoformat(), "test_start": bars[start].end.isoformat(),
                      "test_end": bars[start + test_bars - 1].end.isoformat(),
                      **{k: result[k] for k in ("return", "max_drawdown", "closed_trades", "buy_hold_return")}})
    return {"folds": folds, "selection": "fixed_rules_no_parameter_optimization", "fold_capital_resets": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path)
    parser.add_argument("--strategy", choices=["opening_range_breakout", "sma_trend"], required=True)
    parser.add_argument("--slippage-bps", type=float, default=5)
    parser.add_argument("--fee-per-share", type=float, default=0.005)
    parser.add_argument("--walk-forward", action="store_true")
    args = parser.parse_args()
    bars = read_bars(args.csv)
    fn = walk_forward if args.walk_forward else replay
    print(json.dumps(fn(bars, args.strategy, slippage_bps=args.slippage_bps,
                       fee_per_share=args.fee_per_share), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
