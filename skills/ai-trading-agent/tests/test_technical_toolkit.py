"""Original formula fixtures, timing checks and conservation invariants."""
from copy import deepcopy
from datetime import date, timedelta
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import technical_toolkit as t


def bars(values, volumes=None, session=True):
    return [{"timestamp": (date(2025, 1, 1) + timedelta(days=i)).isoformat(),
             "open": v, "high": v + 1, "low": v - 1, "close": v,
             "volume": 10 if volumes is None else volumes[i],
             **({"session": "A" if i < 3 else "B"} if session else {})}
            for i, v in enumerate(values)]


def request(values=None):
    return {"symbol": "FICTIONAL", "timeframe": "daily", "price_basis": "synthetic consistently adjusted OHLCV",
            "price_unit": "USD per share", "volume_unit": "shares",
            "timestamp_basis": "bar_open", "finalized_bars": True,
            "bars": bars(values if values is not None else [10 + i / 10 + (i % 7) for i in range(90)]),
            "parameters": {"sma_period": 3, "ema_period": 3, "rsi_period": 3,
                           "macd_fast": 2, "macd_slow": 4, "macd_signal": 2,
                           "bollinger_period": 3, "atr_period": 3, "adx_period": 3,
                           "stochastic_period": 3, "stochastic_smooth_k": 2, "stochastic_smooth_d": 2,
                           "ichimoku_conversion": 2, "ichimoku_base": 3, "ichimoku_span": 4,
                           "ichimoku_displacement": 3, "support_resistance_lookback": 3}}


class TechnicalToolkitTests(unittest.TestCase):
    def test_hand_calculated_smoothing_and_gap_reseed(self):
        self.assertEqual(t.sma([1, 2, 3, 4], 3), [None, None, 2, 3])
        self.assertEqual(t.ema([1, 2, 3, 7], 3), [None, None, 2, 4.5])
        self.assertEqual(t.wilder([1, 2, 3, 8], 3), [None, None, 2, 4])
        self.assertEqual(t.ema([1, 2, None, 8, 10, 12], 2), [None, 1.5, None, None, 9, 11])
        self.assertEqual(t.sma([1, None, 3, 5], 2), [None, None, None, 4])

    def test_rsi_hand_calculation_and_flat_convention(self):
        values = t.rsi([10, 12, 11, 13, 12], 3)
        self.assertEqual(values[:3], [None] * 3)
        self.assertAlmostEqual(values[3], 80)
        self.assertAlmostEqual(values[4], 100 * (8 / 9) / (8 / 9 + 5 / 9))
        self.assertEqual(t.rsi([10] * 5, 3), [None, None, None, 50, 50])
        self.assertEqual(t.rsi([10, 11, 12], 2)[-1], 100)
        self.assertEqual(t.rsi([12, 11, 10], 2)[-1], 0)
        self.assertEqual(t.rsi([], 3), [])

    def test_macd_sma_seeds_warmup(self):
        result = t.macd([1, 2, 3, 4, 5, 6], 2, 4, 2)
        self.assertEqual(result["line"], [None, None, None, 1, 1, 1])
        self.assertEqual(result["signal"], [None, None, None, None, 1, 1])
        self.assertEqual(result["histogram"][-2:], [0, 0])

    def test_bollinger_population_std(self):
        result = t.bollinger([2, 4, 6], 3, 2)
        self.assertEqual(result["middle"][-1], 4)
        self.assertAlmostEqual(result["upper"][-1], 4 + 2 * (8 / 3) ** .5)
        self.assertAlmostEqual(result["lower"][-1], 4 - 2 * (8 / 3) ** .5)

    def test_atr_uses_gap_and_wilder(self):
        fixture = bars([10, 14, 12, 13])
        self.assertEqual(t.true_range(fixture), [2, 5, 3, 2])
        self.assertEqual(t.atr(fixture, 3)[:2], [None, None])
        self.assertAlmostEqual(t.atr(fixture, 3)[2], 10 / 3)
        self.assertAlmostEqual(t.atr(fixture, 3)[3], 26 / 9)

    def test_adx_first_value_and_trend(self):
        result = t.adx(bars([10, 11, 12, 13, 14, 15, 16]), 3)
        self.assertEqual(result["plus_di"][:3], [None] * 3)
        self.assertEqual(result["plus_di"][3:], [50] * 4)
        self.assertEqual(result["minus_di"][3:], [0] * 4)
        self.assertEqual(result["adx"][:5], [None] * 5)
        self.assertEqual(result["adx"][5:], [100, 100])

    def test_adx_equal_directional_moves_zero(self):
        fixture = bars([10] * 8)
        for i, bar in enumerate(fixture):
            bar["high"], bar["low"] = 10 + i / 2, 10 - i / 2
        result = t.adx(fixture, 2)
        self.assertEqual(result["plus_di"][2:], [0] * 6)
        self.assertEqual(result["minus_di"][2:], [0] * 6)
        self.assertEqual(result["adx"][3:], [0] * 5)

    def test_flat_range_zero_denominators(self):
        fixture = bars([10] * 8, [0] * 8)
        for bar in fixture:
            bar["high"] = bar["low"] = 10
        self.assertEqual(t.stochastic(fixture, 3, 1, 1)["raw_k"], [None] * 8)
        self.assertEqual(t.adx(fixture, 2)["adx"][3:], [0] * 5)
        self.assertEqual(t.vwap(fixture), [None] * 8)
        self.assertIsNone(t.volume_profile(fixture)["point_of_control_bin"])

    def test_stochastic_hand_calculation(self):
        result = t.stochastic(bars([10, 11, 12, 13]), 3, 1, 2)
        self.assertEqual(result["raw_k"], [None, None, 75, 75])
        self.assertEqual(result["d"], [None, None, None, 75])

    def test_vwap_explicit_session_reset_anchor_crosses_session(self):
        fixture = bars([10, 12, 14, 20, 22], [1, 2, 0, 0, 3])
        self.assertEqual(t.vwap(fixture), [10, 34 / 3, 34 / 3, None, 22])
        self.assertEqual(t.vwap(fixture, 1), [None, 12, 12, 12, 18])
        for bar in fixture:
            del bar["session"]
        self.assertEqual(t.vwap(fixture), [None] * 5)
        self.assertEqual(t.vwap(fixture, 1)[-1], 18)

    def test_obv_unchanged_close_has_no_volume_effect(self):
        self.assertEqual(t.obv(bars([10, 11, 11, 9], [5, 10, 99, 4])), [0, 10, 10, 6])

    def test_ichimoku_projection_and_lag_are_causal(self):
        fixture = bars([10, 12, 14, 16, 18, 20, 22, 24])
        result = t.ichimoku(fixture, 2, 3, 4, 3)
        self.assertEqual(result["conversion"][2], 13)
        self.assertEqual(result["base"][2], 12)
        self.assertEqual(result["span_a_projected"][2], 12.5)
        self.assertEqual(result["cloud_a_now"][5], 12.5)
        self.assertEqual(result["lag_comparison_close"][3], 10)
        self.assertIsNone(result["cloud_b_now"][5])
        self.assertEqual(result["cloud_b_now"][6], 13)

    def test_previous_window_support_not_current_breakout(self):
        levels = t.support_resistance(bars([10, 11, 12, 30]), 3)
        self.assertEqual(levels, {"resistance": [None, None, None, 13], "support": [None, None, None, 9]})

    def test_fibonacci_known_endpoints_and_availability(self):
        result = t.fibonacci(bars([10, 20]), 0, 1, "up")
        self.assertEqual(result["retracements"]["0.5"], 15)
        self.assertEqual(result["available_after_close_index"], 1)
        self.assertAlmostEqual(result["extensions_from_start"]["1.618"], 9 + 1.618 * 12)
        reverse = t.fibonacci(bars([20, 10]), 0, 1, "down")
        self.assertEqual(reverse["retracements"]["0.5"], 15)
        with self.assertRaises(ValueError):
            t.fibonacci(bars([10, 20]), 1, 0, "up")

    def test_candlestick_labels_are_geometry_only(self):
        fixture = bars([10, 10, 10, 10])
        fixture[0].update(open=11, close=10, high=12, low=9)
        fixture[1].update(open=9, close=12, high=12, low=9)
        fixture[2].update(open=10, close=11, high=11.2, low=7)
        fixture[3].update(open=10, close=10, high=12, low=9)
        result = t.candlesticks(fixture)
        self.assertIn("bullish_body_engulfing", result[1])
        self.assertIn("hammer_geometry", result[2])
        self.assertIn("doji_geometry", result[3])

    def test_profile_volume_conservation_and_flat_price_boundary(self):
        fixture = bars([10, 10], [100, 50])
        fixture[0].update(low=8, high=12)
        fixture[1].update(open=12, close=12, low=12, high=12)
        result = t.volume_profile(fixture, 2)
        self.assertEqual([x["volume"] for x in result["bins"]], [50, 100])
        self.assertEqual(result["total_allocated_volume"], result["total_input_volume"])
        self.assertEqual(result["point_of_control_bin"], 1)
        self.assertEqual(result["available_after_close_index"], 1)

    def test_depth_snapshot_arithmetic_and_crossed_book(self):
        result = t.depth_imbalance([{"price": 99, "size": 30}], [{"price": 101, "size": 10}])
        self.assertEqual(result["size_imbalance"], .5)
        self.assertEqual(result["spread"], 2)
        self.assertEqual(result["mid"], 100)
        with self.assertRaises(ValueError):
            t.depth_imbalance([{"price": 102, "size": 30}], [{"price": 101, "size": 10}])

    def test_replay_next_open_gap_and_cost_cash_identity(self):
        fixture = bars([10, 20, 30])
        fixture[1].update(open=15, low=14)
        fixture[2].update(open=25, low=24)
        result = t.replay(fixture, [1, 0, 1], 1000, 10, 20)
        quantity = 1000 / (15 * 1.002 * 1.001)
        ending_cash = quantity * 25 * .998 * .999
        self.assertAlmostEqual(result["trades"][0]["shares"], quantity)
        self.assertEqual(result["trades"][0]["fill_index"], 1)
        self.assertEqual(result["trades"][0]["decision_index"], 0)
        self.assertAlmostEqual(result["ending_cash"], ending_cash)
        self.assertEqual(result["ending_shares"], 0)
        self.assertEqual(result["last_signal_unexecuted"], 1)
        self.assertEqual(len(result["trades"]), 2)

    def test_replay_null_holds_and_no_end_liquidation(self):
        result = t.replay(bars([10, 10, 12, 14]), [1, None, None, 0], 1000)
        self.assertEqual(len(result["trades"]), 1)
        self.assertEqual(result["ending_shares"], 100)
        self.assertEqual(result["equity"][-1], 1400)
        self.assertAlmostEqual(result["total_return"], .4)

    def test_every_indicator_prefix_invariance(self):
        req = request()
        req["vwap_anchor_index"] = 1
        full = t.analyze(req)["rows"]
        for stop in (2, 3, 6, 12, 30, 70):
            partial = deepcopy(req)
            partial["bars"] = partial["bars"][:stop]
            self.assertEqual(t.analyze(partial)["rows"], full[:stop], f"future leakage at length {stop}")

    def test_price_scale_invariance(self):
        req = request()
        a = t.analyze(req)["rows"]
        for bar in req["bars"]:
            for key in ("open", "high", "low", "close"):
                bar[key] *= 7
        b = t.analyze(req)["rows"]
        for x, y in zip(a, b):
            for key in ("rsi", "directional_adx", "stochastic_k"):
                if x[key] is not None:
                    self.assertAlmostEqual(x[key], y[key], places=9)
            for key in ("sma", "ema", "atr", "session_vwap"):
                if x[key] is not None:
                    self.assertAlmostEqual(x[key] * 7, y[key], places=9)

    def test_invalid_bars_are_rejected_without_filling(self):
        for mutate in (lambda b: b[0].update(close=None), lambda b: b[0].update(volume=-1),
                       lambda b: b[0].update(close=float("nan")), lambda b: b[0].update(close=True),
                       lambda b: b[0].update(high=8), lambda b: b[1].update(timestamp=b[0]["timestamp"]),
                       lambda b: b[0].update(timestamp="2025-01-01T09:30:00"),
                       lambda b: b[0].update(open=0), lambda b: b[1].pop("session")):
            fixture = bars([10, 11])
            mutate(fixture)
            with self.subTest(fixture=fixture), self.assertRaises(ValueError):
                t.validate_bars(fixture)
        fixture = bars([10, 11, 12])
        for row, sess in zip(fixture, ("A", "B", "A")):
            row["session"] = sess
        with self.assertRaises(ValueError):
            t.validate_bars(fixture)

    def test_intraday_offsets_compare_actual_instant(self):
        fixture = bars([10, 11])
        fixture[0]["timestamp"] = "2025-01-01T09:30:00-05:00"
        fixture[1]["timestamp"] = "2025-01-01T14:31:00Z"
        self.assertEqual(len(t.validate_bars(fixture)), 2)
        fixture[1]["timestamp"] = "2025-01-01T14:29:00Z"
        with self.assertRaises(ValueError):
            t.validate_bars(fixture)

    def test_date_only_requires_calendar_date_not_iso_week(self):
        fixture=bars([10])
        fixture[0]['timestamp']='2025-W01-1'
        with self.assertRaises(ValueError):t.validate_bars(fixture)

    def test_invalid_parameters_are_errors_not_silent_defaults(self):
        for params in ({"rsi_period": 0}, {"ema_period": 1.5}, {"rsi_period": True},
                       {"typo_period": 2}, {"macd_fast": 30}, {"bollinger_multiplier": -1}):
            req = request()
            req["parameters"].update(params)
            with self.subTest(params=params), self.assertRaises(ValueError):
                t.analyze(req)

    def test_short_history_returns_null_warmup_no_nan(self):
        req = request([10])
        result = t.analyze(req)
        self.assertIsNone(result["rows"][0]["rsi"])
        self.assertIsNone(result["rows"][0]["directional_adx"])
        json.dumps(result, allow_nan=False)

    def test_input_contract_rejects_ambiguity_and_unknown_fields(self):
        for change in ({"timestamp_basis": "unknown"}, {"finalized_bars": False}, {"finalized_bars": 1},
                       {"symbol": ""}, {"unkown_option": 1}, {"replay": []}):
            req = request()
            req.update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                t.analyze(req)

    def test_frozen_golden_fixture(self):
        root = Path(__file__).resolve().parents[1]
        golden = json.loads((root / "examples/technical-golden.json").read_text(encoding="utf-8"))
        result = t.analyze(golden["request"])
        for expected in golden["expected_rows"]:
            actual = result["rows"][expected["index"]]
            for key, value in expected.items():
                if key == "index":
                    continue
                if value is None:
                    self.assertIsNone(actual[key], key)
                else:
                    self.assertAlmostEqual(actual[key], value, places=10, msg=key)

    def test_default_resolution_is_complete_idempotent_and_nonmutating(self):
        req = request()
        req.update(volume_profile={}, replay={"strategy": "close_above_sma"})
        original = deepcopy(req)
        resolved = t.resolve_request(req)
        self.assertEqual(req, original)
        self.assertEqual(resolved, t.resolve_request(resolved))
        self.assertEqual(resolved["volume_profile"], {"bins": 20, "start_index": 0, "end_index": 89})
        self.assertEqual(resolved["replay"], {"strategy": "close_above_sma", "initial_cash": 10000, "fee_bps": 0, "slippage_bps": 0})
        self.assertEqual(set(resolved["parameters"]), set(t.DEFAULTS))
        self.assertEqual(t.analyze(req), t.analyze(resolved))

    def test_cli_does_not_overwrite_input_or_existing_output(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            source, existing = Path(tmp) / "input.json", Path(tmp) / "existing.json"
            source.write_text(json.dumps(request()), encoding="utf-8")
            existing.write_text("original evidence", encoding="utf-8")
            original = source.read_bytes()
            for target in (source, existing):
                run = subprocess.run([sys.executable, str(root / "scripts/technical_toolkit.py"),
                                      "--input", str(source), "--output", str(target)], capture_output=True, text=True)
                self.assertEqual(run.returncode, 2)
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(existing.read_text(encoding="utf-8"), "original evidence")

    def test_svg_valid_xml_and_untrusted_title_escaped(self):
        req = request()
        svg = t.chart_svg(req["bars"], t.analyze(req), '<script>alert("x")</script>')
        root = ET.fromstring(svg)
        self.assertEqual(root.tag, "{http://www.w3.org/2000/svg}svg")
        self.assertNotIn("<script>", svg)
        self.assertIn("&lt;script&gt;", svg)

    def test_cli_example_runs_without_external_dependencies(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            output, chart = Path(tmp) / "result.json", Path(tmp) / "chart.svg"
            run = subprocess.run([sys.executable, str(root / "scripts/technical_toolkit.py"),
                                  "--input", str(root / "examples/technical-toolkit-input.json"),
                                  "--output", str(output), "--chart", str(chart)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["schema"], "technical-toolkit-v1")
            self.assertIn("replay", result)
            ET.parse(chart)


if __name__ == "__main__":
    unittest.main()
