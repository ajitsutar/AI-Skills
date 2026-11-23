"""Reconcile marked and realized contributions to the single-symbol research account."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from strategy_lab import Bar, replay


def daily(closes):
    start = datetime(2024, 1, 2, 14, 30, tzinfo=timezone.utc)
    rows = []
    for i, (opening, close) in enumerate(closes):
        session = start + timedelta(days=i)
        end = session + timedelta(hours=6)
        rows.append(Bar(end, session, end, opening, max(opening, close) + 0.1,
                        min(opening, close) - 0.1, close, 1000))
    return rows


class ReplayPnlAttributionTests(unittest.TestCase):
    def run_replay(self, prices):
        return replay(daily(prices), "sma_trend", lookback=2, initial_cash=1000,
                      risk_fraction=1, capital_fraction=0.5, slippage_bps=10, fee_per_share=0.05)

    def test_closed_gain_and_losing_open_lot_include_only_incurred_costs(self):
        result = self.run_replay([(10, 10), (10, 10), (10, 11), (11, 13), (13, 12),
                                  (12, 12), (12, 13), (13, 12.8)])
        trade, = result["trades"]
        position = result["open_position"]
        closed = trade["quantity"] * (12 * .999 - 11 * 1.001 - .10)
        marked = position["quantity"] * (12.8 - 13 * 1.001 - .05)
        self.assertGreater(closed, 0)
        self.assertLess(marked, 0)
        a = result["pnl_attribution"]
        self.assertAlmostEqual(a["closed_trade_net_pnl"], closed)
        self.assertAlmostEqual(a["end_open_marked_pnl"], marked)
        self.assertAlmostEqual(a["account_equity_change"], closed + marked)
        self.assertAlmostEqual(a["account_equity_change"], 1000 * result["return"])
        self.assertLessEqual(abs(a["reconciliation_residual"]), a["rounding_tolerance"])
        self.assertTrue(a["reconciled"])
        self.assertIn(f"{a['closed_trade_net_pnl']:+,.2f}", a["summary"])
        self.assertIn(f"{a['end_open_marked_pnl']:+,.2f}", a["summary"])

    def test_open_only_lot_is_a_mark_and_has_no_exit_fee(self):
        result = self.run_replay([(10, 10), (10, 10), (10, 11), (11, 11.5)])
        position = result["open_position"]
        a = result["pnl_attribution"]
        self.assertEqual(result["closed_trades"], 0)
        self.assertEqual(a["closed_trade_net_pnl"], 0)
        self.assertAlmostEqual(a["end_open_marked_pnl"],
                               position["quantity"] * (11.5 - 11 * 1.001 - .05))
        self.assertAlmostEqual(a["end_open_marked_pnl"], a["account_equity_change"])
        self.assertTrue(a["reconciled"])

    def test_flat_and_closed_only_periods_have_zero_open_contribution(self):
        flat = self.run_replay([(10, 10), (10, 10), (10, 10)])
        stopped = self.run_replay([(10, 10), (10, 10), (10, 11), (11, 11), (8, 8.1)])
        for result in (flat, stopped):
            a = result["pnl_attribution"]
            self.assertIsNone(result["open_position"])
            self.assertEqual(a["end_open_marked_pnl"], 0)
            self.assertAlmostEqual(a["closed_trade_net_pnl"], a["account_equity_change"])
            self.assertTrue(a["reconciled"])
        self.assertEqual(flat["pnl_attribution"]["account_equity_change"], 0)
        self.assertLess(stopped["pnl_attribution"]["closed_trade_net_pnl"], 0)
