"""Independent numerical and rejection checks; optional packages skip explicitly."""
import copy
from contextlib import redirect_stdout
import importlib.util
from importlib.metadata import PackageNotFoundError
import json
import io
import math
from pathlib import Path
import random
import subprocess
import sys
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import portable_quant as pq

HAS_STATS = importlib.util.find_spec("statsmodels") is not None
HAS_QL = importlib.util.find_spec("QuantLib") is not None
HAS_VADER = importlib.util.find_spec("vaderSentiment") is not None
COMMON = {"as_of": "2025-01-01T00:00:00Z", "currency": "USD"}


def option_input(**changes):
    data = {**COMMON, "spot": 100, "strike": 100, "rate": 0.05, "dividend_yield": 0.02,
        "volatility": 0.2, "evaluation_date": "2025-01-01", "maturity_date": "2026-01-01",
        "option_type": "call", "day_count": "Actual365Fixed"}
    data.update(changes)
    return data


def arima_input(**changes):
    rng = random.Random(19)
    values = [0.2]
    for _ in range(119):
        values.append(0.55 * values[-1] + rng.gauss(0, 0.3))
    data = {**COMMON, "values": values, "order": [1, 0, 0], "trend": "c", "steps": 4,
        "maxiter": 200, "diagnostic_lags": 8, "alpha": 0.05, "input_basis": "caller_declared_frozen_inputs",
        "value_unit": "dimensionless fictional observations", "observation_frequency": "daily equally spaced exercise"}
    data.update(changes)
    return data


def coint_input(**changes):
    rng = random.Random(271)
    x, y, walk = [], [], 0.0
    for _ in range(150):
        walk += rng.gauss(0, 1)
        x.append(walk)
        y.append(1.75 * walk + 4 + rng.gauss(0, 0.6))
    data = {**COMMON, "y0": y, "y1": x, "trend": "c", "maxlag": 3,
        "autolag": None, "significance": 0.05, "input_basis": "caller_declared_frozen_inputs",
        "y0_unit": "fictional index", "y1_unit": "fictional index", "observation_frequency": "daily equally spaced exercise"}
    data.update(changes)
    return data


class PortableContractTests(unittest.TestCase):
    def test_import_works_without_site_packages(self):
        command = "import sys;sys.path.insert(0,sys.argv[1]);import portable_quant;print(sorted(portable_quant.OPERATIONS))"
        result = subprocess.run([sys.executable, "-S", "-c", command, str(SCRIPTS)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("cointegration", result.stdout)

    def test_missing_optional_dependencies_fail_without_substitution(self):
        cases = [(pq.arima, arima_input()), (pq.cointegration, coint_input()),
                 (pq.european, option_input()), (pq.vader, {**COMMON, "texts": ["excellent"]})]
        for function, document in cases:
            with self.subTest(function=function.__name__), patch.object(pq, "version", side_effect=PackageNotFoundError("fixture")):
                with self.assertRaisesRegex(ValueError, "DEPENDENCY_UNAVAILABLE"):
                    function(document)

    def test_explicit_common_schema(self):
        for change in ({"as_of": "2025-01-01"}, {"as_of": "2025-13-01T00:00:00Z"},
            {"as_of": "2025-01-01T00:00:00+00:00"}, {"currency": "usd"}, {"currency": "US"}, {"extra": 1}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                pq.vader({**COMMON, "texts": ["excellent"], **change})

    def test_invalid_values_before_optional_imports(self):
        for change in ({"spot": True}, {"spot": 10**1000}, {"strike": float("nan")}, {"volatility": 0},
            {"evaluation_date": "2024-01-01"}, {"maturity_date": "2024-01-01"}, {"day_count": "Actual360"}):
            with self.subTest(change=str(change)[:60]), self.assertRaises(ValueError):
                pq.european(option_input(**change))
        for change in ({"values": list(range(12))}, {"values": [1]*50}, {"order": [True, 0, 0]},
            {"order": [0, 1, 0], "trend": "c"}, {"diagnostic_lags": 1}, {"alpha": float("inf")},
            {"steps": True}, {"input_basis": "verified"}, {"value_unit": ""}):
            with self.subTest(change=str(change)[:60]), self.assertRaises(ValueError):
                pq.arima(arima_input(**change))
        for texts in ([], [True], [""], ["a"*10001]):
            with self.subTest(texts=str(texts)[:20]), self.assertRaises(ValueError):
                pq.vader({**COMMON, "texts": texts})

    def test_cli_rejects_duplicate_keys_and_nonfinite_json(self):
        for raw, expected in (( '{"texts":[],"texts":[]}', "DUPLICATE_JSON_KEY"),
                              ('{"spot":NaN}', "NONFINITE_JSON")):
            output = io.StringIO()
            with patch.object(sys, "argv", ["portable_quant.py", "vader", "input.json"]), \
                    patch.object(Path, "read_text", return_value=raw), redirect_stdout(output):
                self.assertEqual(pq.main(), 1)
            self.assertEqual(json.loads(output.getvalue())["status"], "FAILED")
            self.assertIn(expected, output.getvalue())


@unittest.skipUnless(HAS_QL, "optional QuantLib is unavailable")
class PricingTests(unittest.TestCase):
    def test_independent_closed_form_and_put_call_parity(self):
        call, put = pq.european(option_input()), pq.european(option_input(option_type="put"))
        normal = lambda x: (1 + math.erf(x / math.sqrt(2))) / 2
        d1 = (0.05 - 0.02 + 0.2 ** 2 / 2) / 0.2
        expected = 100 * math.exp(-0.02) * normal(d1) - 100 * math.exp(-0.05) * normal(d1 - 0.2)
        self.assertAlmostEqual(call["npv"], expected, places=10)
        self.assertAlmostEqual(call["npv"] - put["npv"], 100 * (math.exp(-0.02) - math.exp(-0.05)), places=10)
        self.assertEqual(call["year_fraction"], 1)
        self.assertEqual(call["runtime"]["QuantLib"], pq.version("QuantLib"))

    def test_greeks_against_finite_differences(self):
        base = pq.european(option_input())
        up, down = pq.european(option_input(spot=100.001)), pq.european(option_input(spot=99.999))
        self.assertAlmostEqual(base["delta"], (up["npv"]-down["npv"])/0.002, places=7)
        up, down = pq.european(option_input(volatility=0.20001)), pq.european(option_input(volatility=0.19999))
        self.assertAlmostEqual(base["vega"], (up["npv"]-down["npv"])/0.00002, places=6)

    def test_global_date_restored_on_success_and_failure(self):
        import QuantLib as ql
        with ql.SavedSettings():
            ql.Settings.instance().evaluationDate = ql.Date(13, 3, 2022)
            first = pq.european(option_input())
            self.assertEqual(first, pq.european(option_input()))
            self.assertEqual(ql.Settings.instance().evaluationDate, ql.Date(13, 3, 2022))
            with patch.object(ql, "AnalyticEuropeanEngine", side_effect=RuntimeError("fixture engine failure")):
                with self.assertRaisesRegex(ValueError, "CALCULATION_FAILED:european:RuntimeError:fixture engine"):
                    pq.european(option_input())
            self.assertEqual(ql.Settings.instance().evaluationDate, ql.Date(13, 3, 2022))


@unittest.skipUnless(HAS_STATS, "optional statsmodels is unavailable")
class EconometricsTests(unittest.TestCase):
    def test_arima_diagnostics_forecast_runtime_determinism_and_input_immutability(self):
        data = arima_input()
        original = copy.deepcopy(data)
        result = pq.arima(data)
        self.assertTrue(result["converged"])
        self.assertEqual(len(result["forecast"]), 4)
        self.assertTrue(0.25 < result["parameters"]["ar.L1"] < 0.85)
        self.assertEqual(result["residual_diagnostics"]["ljung_box_lag"], 8)
        for forecast, bounds in zip(result["forecast"], result["prediction_intervals"]):
            self.assertLess(bounds[0], forecast)
            self.assertLess(forecast, bounds[1])
        self.assertEqual(result, pq.arima(data))
        self.assertEqual(data, original)
        self.assertEqual(result["runtime"]["statsmodels"], pq.version("statsmodels"))
        json.dumps(result, allow_nan=False)

    def test_nonconvergence_emits_diagnostic_without_usable_forecast(self):
        from statsmodels.tsa.arima.model import ARIMA
        actual = ARIMA.fit
        def unconverged(model, *args, **kwargs):
            fit = actual(model, *args, **kwargs)
            fit.mle_retvals["converged"] = False
            fit.get_forecast = lambda *args, **kwargs: self.fail("must not calculate forecast after nonconvergence")
            return fit
        with patch.object(ARIMA, "fit", unconverged):
            with self.assertRaisesRegex(ValueError, "ARIMA_NOT_CONVERGED") as caught:
                pq.arima(arima_input())
        diagnostic = json.loads(str(caught.exception).split(":", 1)[1])
        self.assertFalse(diagnostic["forecast_emitted"])
        self.assertNotIn("forecast", diagnostic)
        self.assertNotIn("prediction_intervals", diagnostic)

    def test_random_walk_forecast_known_last_observation(self):
        data = arima_input(order=[0, 1, 0], trend="n")
        for value in pq.arima(data)["forecast"]:
            self.assertAlmostEqual(value, data["values"][-1], places=8)

    def test_cointegration_directional_normalization(self):
        data = coint_input()
        first = pq.cointegration(data)
        reverse = pq.cointegration({**data, "y0": data["y1"], "y1": data["y0"]})
        self.assertTrue(first["reject_no_cointegration"])
        self.assertAlmostEqual(first["coefficients"]["y1"], 1.75, delta=0.1)
        self.assertAlmostEqual(reverse["coefficients"]["y1"], 1/1.75, delta=0.1)
        self.assertNotEqual(first["statistic"], reverse["statistic"])
        self.assertEqual(first, pq.cointegration(data))
        json.dumps(first, allow_nan=False)

    def test_degenerate_and_malformed_pairs_rejected(self):
        data = coint_input()
        for change in ({"y0": data["y1"]}, {"y0": data["y0"][:-1]}, {"maxlag": True},
            {"autolag": "automatic"}, {"trend": "n"}, {"y0": [float("nan")]*150}):
            with self.subTest(change=str(change)[:40]), self.assertRaises(ValueError):
                pq.cointegration({**data, **change})


@unittest.skipUnless(HAS_VADER, "optional vaderSentiment is unavailable")
class SentimentTests(unittest.TestCase):
    def test_original_scores_and_polarities(self):
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        texts = ["This is wonderful and excellent!", "This is horrible and terrible!", "Not excellent."]
        result = pq.vader({**COMMON, "texts": texts})
        self.assertEqual(result["scores"], [SentimentIntensityAnalyzer().polarity_scores(text) for text in texts])
        self.assertGreater(result["scores"][0]["compound"], 0)
        self.assertLess(result["scores"][1]["compound"], 0)
        self.assertLess(result["scores"][2]["compound"], 0)
        self.assertEqual(result["runtime"]["vaderSentiment"], pq.version("vaderSentiment"))


if __name__ == "__main__":
    unittest.main()
