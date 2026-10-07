import csv
import math
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from risk_engine import timestamp
from strategy_lab import Bar, signal, replay, read_bars, walk_forward


def intraday_bars():
    start = timestamp("2026-10-06T13:30:00Z")
    close = timestamp("2026-10-06T20:00:00Z")
    values = [(100, 101, 99, 100, 1000), (100, 101, 99.5, 100.5, 1000),
              (100.5, 101, 100, 100.8, 1000), (100.8, 102.1, 100.5, 102, 2000),
              (102, 112, 98, 104, 2000), (104, 105, 103, 104, 1000)]
    return [Bar(start + timedelta(minutes=5 * (i + 1)), start, close, *v) for i, v in enumerate(values)]


class ReplayTests(unittest.TestCase):
    def test_opening_range_requires_completed_window(self):
        bars = intraday_bars()
        self.assertIsNone(signal(bars[:3], "opening_range_breakout"))
        self.assertEqual(signal(bars[:4], "opening_range_breakout")["action"], "enter")

    def test_next_bar_entry_and_stop_first_ambiguity(self):
        bars = intraday_bars()
        result = replay(bars, "opening_range_breakout")
        self.assertEqual(result["closed_trades"], 1)
        trade = result["trades"][0]
        self.assertGreater(trade["entry_bar_end"], trade["signal_time"])
        self.assertGreaterEqual(trade["entry_time"], trade["signal_time"])
        self.assertEqual(trade["reason"], "stop_or_gap")
        self.assertLess(trade["pnl"], 0)

    def test_missing_opening_bar_suppresses_signal(self):
        self.assertIsNone(signal(intraday_bars()[1:4], "opening_range_breakout"))

    def test_no_fill_with_zero_volume(self):
        bars = intraday_bars()
        b = bars[4]
        bars[4] = Bar(b.end, b.session_open, b.session_close, b.open, b.high, b.low, b.close, 0)
        result = replay(bars, "opening_range_breakout")
        self.assertEqual(result["closed_trades"], 0)
        self.assertIsNone(result["open_position"])

    def test_gap_above_entry_limit_is_skipped(self):
        bars = intraday_bars()
        b = bars[4]
        bars[4] = Bar(b.end, b.session_open, b.session_close, 110, 112, 98, 104, 2000)
        self.assertFalse(replay(bars, "opening_range_breakout")["trades"])

    def test_missing_next_intraday_bar_expires_entry(self):
        bars = intraday_bars()
        # A later tradable bar must not fill the old signal after a feed gap.
        bars[4] = Bar(bars[4].end + timedelta(minutes=20), bars[4].session_open,
                      bars[4].session_close, 102, 103, 101, 102, 2000)
        result = replay(bars[:5], "opening_range_breakout")
        self.assertIsNone(result["open_position"])
        self.assertEqual(result["closed_trades"], 0)
        self.assertIn("intraday_entry_expired_or_session_already_used", result["events"])

    def test_intraday_time_exit_and_illiquid_residual(self):
        bars = intraday_bars()[:4]
        last = bars[-1]
        bars.append(Bar(last.end + timedelta(minutes=5), last.session_open, last.session_close,
                        102, 103, 101, 102, 2000))
        bars.append(Bar(last.session_close - timedelta(minutes=10), last.session_open, last.session_close,
                        102, 103, 101, 102, 1000))
        result = replay(bars, "opening_range_breakout")
        self.assertEqual(result["trades"][0]["reason"], "scheduled_session_exit")
        self.assertIsNone(result["open_position"])
        b = bars[-1]
        bars[-1] = Bar(b.end, b.session_open, b.session_close, b.open, b.high, b.low, b.close, 0)
        result = replay(bars, "opening_range_breakout")
        self.assertIsNotNone(result["open_position"])
        self.assertEqual(result["closed_trades"], 0)

    def test_no_second_intraday_entry_after_exit_same_session(self):
        bars = intraday_bars()  # First trade stopped out in bar 5.
        last = bars[-1]
        for index, close in enumerate((100, 102, 103), 1):
            bars.append(Bar(last.end + timedelta(minutes=5 * index), last.session_open,
                            last.session_close, 102, max(103, close), min(100, close), close, 2000))
        result = replay(bars, "opening_range_breakout")
        self.assertEqual(result["closed_trades"], 1)
        self.assertIsNone(result["open_position"])

    def test_five_percent_sleeve_on_small_account_can_size_zero(self):
        result = replay(intraday_bars(), "opening_range_breakout", initial_cash=500)
        self.assertEqual(result["closed_trades"], 0)
        self.assertIsNone(result["open_position"])

    def test_future_bar_does_not_change_existing_signal(self):
        bars = intraday_bars()
        before = signal(bars[:4], "opening_range_breakout")
        bars.append(Bar(bars[-1].end + timedelta(minutes=5), bars[0].session_open, bars[0].session_close,
                        1000, 1001, 999, 1000, 1e6))
        self.assertEqual(before, signal(bars[:4], "opening_range_breakout"))

    def test_more_costs_do_not_improve_same_trade(self):
        bars = intraday_bars()
        cheap = replay(bars, "opening_range_breakout", slippage_bps=0, fee_per_share=0)
        costly = replay(bars, "opening_range_breakout", slippage_bps=5, fee_per_share=.01)
        self.assertLess(costly["return"], cheap["return"])

    def test_daily_strategy_rejects_intraday_bars(self):
        with self.assertRaisesRegex(ValueError, "requires daily"):
            signal(intraday_bars(), "sma_trend", lookback=2)

    def test_read_rejects_duplicate_and_invalid_bars(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "bars.csv"
            header = "timestamp,session_open,session_close,open,high,low,close,volume\n"
            row = "2026-10-06T13:35:00Z,2026-10-06T13:30:00Z,2026-10-06T20:00:00Z,100,101,99,100,1000\n"
            p.write_text(header + row + row)
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                read_bars(p)
            p.write_text(header + row.replace(",100,101,99,100,", ",100,99,101,100,"))
            with self.assertRaisesRegex(ValueError, "OHLC"):
                read_bars(p)

    def test_forward_windows_do_not_overlap(self):
        start = timestamp("2026-01-01T13:30:00Z")
        bars = []
        for i in range(90):
            opening = start + timedelta(days=i)
            price = 100 + math.sin(i / 5) * 5
            bars.append(Bar(opening + timedelta(hours=6.5), opening, opening + timedelta(hours=6.5),
                            price, price + 1, price - 1, price, 1000))
        result = walk_forward(bars, "sma_trend", train_bars=30, test_bars=20)
        self.assertEqual(len(result["folds"]), 2)
        self.assertLess(result["folds"][0]["test_end"], result["folds"][1]["test_start"])


try:
    import numpy as np
    from garch_volatility import Fit, forecast, holdout_validation, fit_model
    SCIENTIFIC = True
except ImportError:
    SCIENTIFIC = False


@unittest.skipUnless(SCIENTIFIC, "Install requirements.txt for numerical regression tests")
class VolatilityTests(unittest.TestCase):
    def test_garch_multistep_keeps_expected_shock_variance(self):
        fit = Fit("garch", np.array([.1, .1, .8]), np.array([1.0]), 0, True, "fixture")
        actual = forecast(fit, np.array([2.0]), 3)
        np.testing.assert_allclose(actual, [1.3, 1.27, 1.243])

    def test_gjr_uses_symmetric_future_negative_shock_expectation(self):
        fit = Fit("gjr", np.array([.1, .1, .2, .7]), np.array([1.0]), 0, True, "fixture")
        np.testing.assert_allclose(forecast(fit, np.array([-2.0]), 2), [2.0, 1.9])

    def test_egarch_one_step_uses_last_innovation(self):
        fit = Fit("egarch", np.array([.01, .1, -.2, .8]), np.array([1.0]), 0, True, "fixture")
        expected = math.exp(.01 + .1 * (2 - math.sqrt(2 / math.pi)) + .4)
        self.assertAlmostEqual(forecast(fit, np.array([-2.0]), 1)[0], expected)

    def test_egarch_multistep_is_explicitly_unsupported(self):
        fit = Fit("egarch", np.array([0, .1, -.2, .8]), np.array([1.0]), 0, True, "fixture")
        with self.assertRaisesRegex(ValueError, "simulation"):
            forecast(fit, np.array([-2.0]), 2)

    def test_failed_fit_cannot_forecast(self):
        fit = Fit("garch", np.array([.1, .1, .8]), np.array([1]), 0, False, "failed")
        with self.assertRaises(ValueError):
            forecast(fit, np.array([1]), 1)

    def test_zero_length_holdout_is_not_ok(self):
        self.assertEqual(holdout_validation(np.arange(10), "garch", 10, 0)["status"], "insufficient_data")

    def test_holdout_updates_from_observed_past_not_future(self):
        fit = Fit("garch", np.array([.1, .1, .8]), np.ones(3), 0, True, "fixture")
        calls = []
        def record(f, r, horizon):
            answer = forecast(f, r, horizon)
            calls.append(float(answer[0]))
            return answer
        with patch("garch_volatility.fit_model", return_value=fit) as fitted, patch("garch_volatility.forecast", side_effect=record):
            result = holdout_validation(np.array([1., -1., 2., 3., 1000.]), "garch", 3, 2)
        np.testing.assert_allclose(calls, [1.3, 2.04])
        np.testing.assert_allclose(fitted.call_args.args[1], [1, -1, 2])
        self.assertEqual(result["n"], 2)

    def test_constant_and_nonfinite_data_rejected(self):
        for values in (np.ones(50), np.array([1, 2, float("nan")])):
            with self.assertRaises(ValueError):
                fit_model("garch", values)

    def test_fitting_synthetic_returns_produces_feasible_variance(self):
        rng = np.random.default_rng(42)
        fit = fit_model("garch", rng.normal(0, 1, 250))
        self.assertTrue(fit.success, fit.message)
        self.assertLess(sum(fit.params[1:]), 1)
        self.assertTrue(np.all(fit.variance > 0))


if __name__ == "__main__":
    unittest.main()
