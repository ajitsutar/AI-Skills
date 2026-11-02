"""Financial identities for honest monthly portfolio controls; all data fictional."""
import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import portfolio_backtest


def period(start, end, returns, weights=None, known_at=None, cost=0.0):
    symbols = list(returns)
    row = {"start": start, "end": end, "returns": returns,
           "tradable": {symbol: True for symbol in symbols},
           "cash_return": 0.0, "benchmark_return": 0.0}
    if weights is not None:
        row.update({"decision": {"known_at": known_at, "weights": weights,
                                 "evidence_hash": "FICTIONAL_CONTROL"},
                    "one_way_costs": [cost] * len(symbols),
                    "impact_coefficients": [0.0] * len(symbols),
                    "max_trade_values": [1000.0] * len(symbols)})
    return row


def document(symbols, initial_weights, periods):
    return {"symbols": symbols, "initial_equity": 100.0,
            "initial_weights": initial_weights, "cash_floor": 0.0,
            "return_basis": "total_return_decimal",
            "universe_evidence": "FICTIONAL_DECLARED_PANEL",
            "corporate_action_evidence": "FICTIONAL_TOTAL_RETURNS",
            "periods": periods}


class MonthlyPortfolioFinancialTests(unittest.TestCase):
    def test_explicit_initial_cash_purchase_pays_entry_cost(self):
        # A 1% purchase fee means invested value x satisfies x + .01*x = 100.
        invested = 100.0 / 1.01
        entry = period("2020-02-03T21:00:00Z", "2020-02-04T21:00:00Z",
                       {"A": 0.0}, [invested / 100.0],
                       "2020-01-31T21:01:00Z", cost=.01)
        paid = portfolio_backtest.simulate(document(["A"], [0.0], [entry]))
        free = portfolio_backtest.simulate(document(["A"], [1.0], [period(
            entry["start"], entry["end"], {"A": 0.0})]))
        self.assertAlmostEqual(paid["curve"][-1]["equity"], invested)
        self.assertAlmostEqual(paid["costs_paid"], 100.0 - invested)
        self.assertAlmostEqual(free["curve"][-1]["equity"], 100.0)
        self.assertEqual(free["costs_paid"], 0.0)

    def test_decision_at_or_after_return_start_is_rejected(self):
        for known_at in ("2020-02-03T21:00:00Z", "2020-02-03T21:00:01Z"):
            with self.subTest(known_at=known_at):
                row = period("2020-02-03T21:00:00Z", "2020-03-02T21:00:00Z",
                             {"A": .05}, [.9], known_at)
                with self.assertRaisesRegex(ValueError,
                                            "DECISION_MUST_PRECEDE_RETURN_INTERVAL"):
                    portfolio_backtest.simulate(document(["A"], [0.0], [row]))

    def test_dividend_total_return_benchmark_changes_active_return(self):
        # Fictional unchanged price with a 5% reinvested distribution: price return
        # is zero, total return is 5%. Neither series receives a second cash dividend.
        row = period("2020-02-03T21:00:00Z", "2020-03-02T21:00:00Z", {"A": .05})
        price_only = document(["A"], [1.0], [row])
        matched_total = copy.deepcopy(price_only)
        matched_total["periods"][0]["benchmark_return"] = .05
        misleading = portfolio_backtest.simulate(price_only)
        matched = portfolio_backtest.simulate(matched_total)
        self.assertAlmostEqual(misleading["total_return_difference"], .05)
        self.assertAlmostEqual(matched["total_return_difference"], 0.0)
        self.assertAlmostEqual(matched["curve"][-1]["equity"], 105.0)

    def test_fixed_equal_monthly_control_is_not_buy_and_hold(self):
        first = period("2020-02-03T21:00:00Z", "2020-03-02T21:00:00Z",
                       {"A": .20, "B": -.10})
        second = period("2020-03-02T21:00:00Z", "2020-04-01T20:00:00Z",
                        {"A": -.10, "B": .20}, [.5, .5],
                        "2020-02-28T21:01:00Z")
        monthly = document(["A", "B"], [.5, .5], [first, second])
        held = copy.deepcopy(monthly)
        for key in ("decision", "one_way_costs", "impact_coefficients", "max_trade_values"):
            held["periods"][1].pop(key)
        rebalanced = portfolio_backtest.simulate(monthly)
        buy_hold = portfolio_backtest.simulate(held)
        # Equal monthly arithmetic returns are +5%, +5%; both individual
        # buy-and-hold paths are +8%. The panel never changes in either control.
        self.assertAlmostEqual(rebalanced["curve"][-1]["equity"], 100 * 1.05 ** 2)
        self.assertAlmostEqual(buy_hold["curve"][-1]["equity"], 108.0)
        self.assertAlmostEqual(rebalanced["gross_traded_notional"], 15.0)
        self.assertEqual(buy_hold["gross_traded_notional"], 0.0)
        self.assertFalse(rebalanced["point_in_time_evidence_verified"])


if __name__ == "__main__":
    unittest.main()
