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



import numpy as np
from types import SimpleNamespace
from garch_volatility import (model_specification, analytic_variance, fit_model,
    forecast, holdout_validation, require_usable_fit, run_analysis, parse_options, variance_loss)


class VolatilityTests(unittest.TestCase):
    def setUp(self):
        self.returns = np.random.default_rng(42).normal(0, 1, 320)

    def test_garch_multistep_keeps_expected_shock_variance(self):
        fixed = model_specification("garch", self.returns).fix([.1, .1, .8])
        previous = fixed.conditional_volatility[-1] ** 2
        first = .1 + .1 * self.returns[-1] ** 2 + .8 * previous
        np.testing.assert_allclose(analytic_variance(fixed, 3),
                                   [first, .1 + .9 * first, .19 + .81 * first])

    def test_gjr_uses_symmetric_future_negative_shock_expectation(self):
        self.returns[-1] = -2
        fixed = model_specification("gjr", self.returns).fix([.1, .1, .2, .7])
        first = .1 + .3 * 4 + .7 * fixed.conditional_volatility[-1] ** 2
        np.testing.assert_allclose(analytic_variance(fixed, 2), [first, .1 + .9 * first])

    def test_egarch_one_step_uses_last_innovation(self):
        self.returns[-1] = -2
        fixed = model_specification("egarch", self.returns).fix([.01, .1, -.2, .8])
        variance = fixed.conditional_volatility[-1] ** 2
        z = -2 / math.sqrt(variance)
        expected = math.exp(.01 + .8 * math.log(variance) + .1 * (abs(z) - math.sqrt(2 / math.pi)) - .2 * z)
        self.assertAlmostEqual(analytic_variance(fixed, 1)[0], expected)

    def test_egarch_multistep_is_explicitly_unsupported(self):
        fixed = model_specification("egarch", self.returns).fix([.01, .1, -.2, .8])
        with self.assertRaisesRegex(ValueError, "simulation"):
            analytic_variance(fixed, 2)

    def test_failed_fit_cannot_forecast(self):
        broken = SimpleNamespace(convergence_flag=9, optimization_result=SimpleNamespace(message="failed"))
        with self.assertRaisesRegex(ValueError, "optimizer failed"):
            forecast(broken, 1)

    def test_nonstationary_fit_is_rejected(self):
        good = fit_model("garch", self.returns)
        broken = SimpleNamespace(convergence_flag=0, params=good.params.copy(),
            conditional_volatility=good.conditional_volatility, loglikelihood=good.loglikelihood, model=good.model)
        broken.params["alpha[1]"], broken.params["beta[1]"] = .1, .9
        with self.assertRaisesRegex(ValueError, "stationary"):
            require_usable_fit(broken)

    def test_zero_length_holdout_is_not_ok(self):
        self.assertEqual(holdout_validation(self.returns, "garch", 250, 0)["status"], "insufficient_data")

    def test_holdout_target_and_future_cannot_change_their_prediction(self):
        # Fix the parameters to isolate chronology from optimizer boundary cases.
        estimate = SimpleNamespace(params=[.1, .1, .8])
        changed = self.returns.copy()
        changed[255] = 50
        with patch("garch_volatility.fit_model", return_value=estimate):
            original = holdout_validation(self.returns, "garch", 250, 20)
            later = holdout_validation(changed, "garch", 250, 20)
        self.assertEqual(original["status"], "ok")
        self.assertEqual(later["status"], "ok")
        a, b = [x["predicted_variance_percent_squared"] for x in (original, later)]
        np.testing.assert_array_equal(a[:6], b[:6])
        self.assertNotEqual(a[6], b[6])

    def test_holdout_fits_once_and_only_on_training_prefix(self):
        estimate = SimpleNamespace(params=[.1, .1, .8])
        with patch("garch_volatility.fit_model", return_value=estimate) as fitting:
            outcome = holdout_validation(self.returns, "garch", 250, 10)
        self.assertEqual(outcome["status"], "ok")
        self.assertEqual(fitting.call_count, 1)
        np.testing.assert_array_equal(fitting.call_args.args[1], self.returns[:250])

    def test_invalid_data_and_horizons_are_rejected(self):
        for values in (np.ones(50), [1, 2, float("nan")], [[1, 2], [3, 4]]):
            with self.assertRaises(ValueError):
                fit_model("garch", values)
        fixed = model_specification("garch", self.returns).fix([.1, .1, .8])
        for horizon in (0, -1, 1.5, True):
            with self.assertRaises(ValueError):
                analytic_variance(fixed, horizon)

    def test_fitting_synthetic_returns_produces_finite_positive_forecasts(self):
        estimate = fit_model("garch", self.returns)
        self.assertEqual(estimate.convergence_flag, 0)
        self.assertTrue(np.all(forecast(estimate, 5) > 0))
        self.assertTrue(np.isfinite(estimate.loglikelihood))

    def test_qlike_exact_prediction_and_invalid_inputs(self):
        self.assertAlmostEqual(variance_loss([1, 2], [1, 2]), 0)
        for actual, predicted in (([1], [0]), ([-1], [1]), ([1], [float("nan")]), ([], [])):
            with self.assertRaises(ValueError):
                variance_loss(actual, predicted)

    def test_fictional_audit_and_output_units_remain_ineligible(self):
        skill = Path(__file__).resolve().parents[1]
        args = [str(skill / "examples/fictional-daily.csv"), "--data-audit",
                str(skill / "examples/fictional-daily.audit.json")]
        result = run_analysis(parse_options(args))
        self.assertFalse(result["eligible_as_sizing_input"])
        self.assertEqual(result["run_specification"]["backend"], "arch")
        self.assertEqual(result["parameter_names"], ["omega", "alpha[1]", "beta[1]"])
        self.assertEqual(len(result["parameters"]), len(result["parameter_names"]))
        self.assertAlmostEqual(result["forecast_period_volatility"] ** 2 * 10000,
                               result["forecast_variance_percent_squared"][0])
        self.assertAlmostEqual(result["forecast_annualized_volatility"],
                               result["forecast_period_volatility"] * math.sqrt(252))

    def test_missing_audit_stays_research_only(self):
        skill = Path(__file__).resolve().parents[1]
        result = run_analysis(parse_options([str(skill / "examples/fictional-daily.csv")]))
        self.assertFalse(result["eligible_as_sizing_input"])
        self.assertEqual(result["data_quality"]["status"], "UNVERIFIED")


if __name__ == "__main__":
    unittest.main()
