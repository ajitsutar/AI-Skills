"""Readback of the daily replay and signed, marked forward-window returns."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from strategy_lab import Bar, replay, walk_forward


def daily_bars(prices):
    start = datetime(2020, 1, 1, 14, 30, tzinfo=timezone.utc)
    bars = []
    for i, (opening, close, low, volume) in enumerate(prices):
        session = start + timedelta(days=i)
        end = session + timedelta(hours=6, minutes=30)
        bars.append(Bar(end, session, end, opening, max(opening, close) + 0.1, low, close, volume))
    return bars


class DailyReplayReadbackTests(unittest.TestCase):
    def test_gap_stop_and_clock_under_nondefault_assumptions(self):
        bars = daily_bars([(10, 10, 9, 100), (10, 10, 9.2, 100), (10, 11, 9.5, 100),
                           (11, 11.1, 10.5, 100), (8, 8.2, 7.8, 100)])
        result = replay(bars, "sma_trend", initial_cash=1000, lookback=2,
                        risk_fraction=0.1, capital_fraction=0.3, slippage_bps=10, fee_per_share=0.01)
        trade, = result["trades"]
        self.assertEqual(trade["quantity"], 27)
        self.assertEqual(trade["signal_time"], bars[2].end.isoformat())
        self.assertEqual(trade["entry_time"], bars[3].session_open.isoformat())
        self.assertEqual(trade["stop"], 9)
        self.assertEqual(trade["reason"], "stop_or_gap")
        self.assertAlmostEqual(trade["exit_price"], 8 * 0.999)
        self.assertEqual(trade["exit_time"], bars[4].end.isoformat())
        self.assertAlmostEqual(result["final_equity"], 1000 + 27 * (8 * .999 - 11 * 1.001 - .02))
        for fragment in ("bar 3", "10 bps", "10% modeled per-trade risk", "30% purchase",
                         "0.01 per share", "lower of the stop", "containing bar ends"):
            self.assertIn(fragment, result["rule_summary"])

    def test_pending_entry_expires_on_zero_volume_bar(self):
        bars = daily_bars([(10, 10, 9, 100), (10, 10, 9, 100), (10, 11, 9, 100),
                           (11, 11, 10.5, 0), (11, 11, 10.5, 100)])
        result = replay(bars, "sma_trend", lookback=2)
        self.assertEqual(result["closed_trades"], 0)
        self.assertIsNone(result["open_position"])
        self.assertIn("attempt lasts one bar", result["rule_summary"])

    def test_fold_includes_marked_loss_without_a_closed_trade(self):
        bars = daily_bars([(10, 10, 9, 100)] * 3 + [(10, 11, 9.5, 100), (11, 10.97, 10.8, 100)])
        result = walk_forward(bars, "sma_trend", train_bars=2, test_bars=2, lookback=2,
                              initial_cash=110, risk_fraction=1, capital_fraction=1,
                              slippage_bps=0, fee_per_share=0)
        fold, = result["folds"]
        self.assertEqual(fold["closed_trades"], 0)
        self.assertAlmostEqual(fold["return"], 10 * (10.97 - 11) / 110)
        stats = result["fold_return_summary"]
        self.assertEqual((stats["minimum_return"], stats["maximum_return"]), (fold["return"], fold["return"]))
        self.assertEqual((stats["negative_returns"], stats["zero_returns"], stats["positive_returns"]), (1, 0, 0))
        self.assertEqual(stats["return_range_text"], "-0.272727% to -0.272727%")

    def test_no_complete_window_has_no_range(self):
        bars = daily_bars([(10, 10, 9, 100)] * 3)
        stats = walk_forward(bars, "sma_trend", train_bars=2, test_bars=2)["fold_return_summary"]
        self.assertEqual(stats["complete_folds"], 0)
        self.assertIsNone(stats["minimum_return"])
        self.assertIsNone(stats["maximum_return"])
        self.assertEqual(stats["return_range_text"], "No complete test windows")
