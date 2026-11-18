import copy
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from risk_engine import canonical_hash, evaluate, size_tactical, timestamp, InvalidInput
from portfolio_manager import rebalance, performance
from install_skill import install


class Fixture(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads((ROOT / "templates/policy.example.json").read_text())
        self.snapshot = json.loads((ROOT / "examples/snapshot.json").read_text())
        self.order = json.loads((ROOT / "examples/order.json").read_text())
        self.now = timestamp("2026-10-06T14:00:00Z")

    def result(self):
        return evaluate(self.policy, self.snapshot, self.order, self.now)

    def blocked(self, code):
        result = self.result()
        self.assertFalse(result["within_research_limits"], result)
        self.assertTrue(any(code in r for r in result["reasons"]), result)


class RiskTests(Fixture):
    def test_valid_fixture(self):
        self.assertTrue(self.result()["within_research_limits"], self.result())

    def test_order_cannot_relabel_stock_as_etf_for_a_larger_cap(self):
        self.order["asset_type"] = "etf"
        self.blocked("INSTRUMENT_TYPE_MISMATCH")

    def test_setup_cannot_jump_to_another_sleeve(self):
        self.order["setup"] = "core_rebalance"
        self.blocked("SETUP_SLEEVE_MISMATCH")

    def test_size_includes_round_trip_friction(self):
        result = size_tactical(100000, 100, 98, ".001", 5000, 5, ".005")
        self.assertEqual(result["quantity"], "47")
        self.assertLessEqual(float(result["planned_loss"]), 100)

    def test_nan_inf_and_missing_fail_closed(self):
        for value in ("NaN", "Infinity", "-1", None, True):
            with self.subTest(value=value):
                self.snapshot["equity"] = value
                self.blocked("INVALID_OR_MISSING_INPUT")

    def test_missing_quote(self):
        self.snapshot["quotes"] = {}
        self.blocked("INVALID_OR_MISSING_INPUT")

    def test_stale_and_future_quote(self):
        for when in ("2026-10-06T13:59:44Z", "2026-10-06T14:00:01Z"):
            self.snapshot["quotes"]["DEMO"]["as_of"] = when
            self.blocked("STALE_OR_FUTURE_QUOTE")

    def test_stale_account(self):
        self.snapshot["as_of"] = "2026-10-05T14:00:00Z"
        self.blocked("STALE_OR_FUTURE_ACCOUNT")

    def test_crossed_quote(self):
        self.snapshot["quotes"]["DEMO"]["bid"] = "101"
        self.blocked("INVALID_OR_MISSING_INPUT")

    def test_spread(self):
        self.snapshot["quotes"]["DEMO"]["ask"] = "101"
        self.blocked("SPREAD_TOO_WIDE")

    def test_halt(self):
        self.snapshot["quotes"]["DEMO"]["halted"] = True
        self.blocked("UNTRADABLE_OR_HALTED")

    def test_event_block_or_unknown_cannot_be_clearance(self):
        for state in (False, None, "true"):
            self.snapshot["quotes"]["DEMO"]["event_clear"] = state
            self.assertFalse(self.result()["within_research_limits"], self.result())

    def test_early_close(self):
        self.snapshot["session"]["close"] = "2026-10-06T14:20:00Z"
        self.blocked("TOO_LATE_FOR_NEW_ENTRY")

    def test_non_trading_day(self):
        self.snapshot["session"]["is_trading_day"] = False
        self.blocked("OUTSIDE_REGULAR_SESSION")

    def test_unsettled_cash_cannot_buy(self):
        self.snapshot["settled_cash"] = "1000"
        self.blocked("INSUFFICIENT_UNRESERVED_SETTLED_CASH")

    def test_position_cash_equity_mismatch(self):
        self.snapshot["cash"] = "99900"
        self.blocked("EQUITY_POSITION_CASH_MISMATCH")

    def test_pending_buy_counts_toward_sleeve(self):
        self.snapshot["open_orders"] = [{"local_ref": "pending-1", "status": "cancel_pending",
            "symbol": "OTHER", "side": "buy", "sleeve": "intraday", "remaining_quantity": "40",
            "reservation_price": "100", "stop_price": "99", "sector": "technology"}]
        self.blocked("SLEEVE_CAP")

    def test_unknown_order_halts(self):
        self.snapshot["open_orders"] = [{"local_ref": "pending-1", "status": "unknown",
            "symbol": "OTHER", "side": "sell", "sleeve": "intraday", "remaining_quantity": "1"}]
        self.blocked("UNKNOWN_OPEN_ORDER_STATE")

    def test_fractional_and_tick_rejected(self):
        self.order["quantity"] = "1.5"
        self.order["limit_price"] = "100.021"
        self.blocked("FRACTIONAL_SHARES_NOT_ENABLED")
        self.blocked("INVALID_PRICE_INCREMENT")

    def test_stop_wrong_side(self):
        self.order["stop_price"] = "101"
        self.blocked("INVALID_OR_MISSING_INPUT")

    def test_risk_and_reward_caps(self):
        self.order["stop_price"] = "90"
        self.blocked("PER_TRADE_RISK_CAP")
        self.blocked("REWARD_RISK_AFTER_COSTS")

    def test_daily_weekly_drawdown_loss_breakers(self):
        for field, value, code in (("day_pnl_ex_flows", "-1000", "DAILY_LOSS_BREAKER"),
             ("week_pnl_ex_flows", "-2500", "WEEKLY_LOSS_BREAKER"),
             ("flow_adjusted_equity", "90000", "DRAWDOWN_BREAKER")):
            with self.subTest(code=code):
                self.snapshot[field] = value
                self.blocked(code)

    def test_sell_can_reduce_during_loss_breaker_and_kill_switch(self):
        self.snapshot["day_pnl_ex_flows"] = "-9999"
        self.snapshot["kill_switch"] = True
        self.snapshot["positions"] = [{"symbol": "DEMO", "quantity": "20", "mark": "100",
            "sleeve": "intraday", "stop_price": "98", "sector": "technology"}]
        self.snapshot["cash"] = "98000"
        self.order["side"] = "sell"
        self.assertTrue(self.result()["within_research_limits"], self.result())
        self.order["quantity"] = "21"
        self.blocked("SELL_EXCEEDS_SLEEVE_AVAILABLE_SHARES")

    def test_core_cannot_be_sold_by_day_sleeve(self):
        self.snapshot["positions"] = [{"symbol": "DEMO", "quantity": "20", "mark": "100",
            "sleeve": "core", "sector": "technology"}]
        self.snapshot["cash"] = "98000"
        self.order["side"] = "sell"
        self.blocked("SELL_EXCEEDS_SLEEVE_AVAILABLE_SHARES")
        self.order["side"] = "buy"
        self.blocked("CROSS_SLEEVE_SYMBOL_CONFLICT")

    def test_core_requires_target(self):
        self.order["sleeve"] = "core"
        self.order["setup"] = "core_rebalance"
        self.blocked("CORE_TARGET_CAP")

    def test_no_fake_account_alias(self):
        self.order["account_alias"] = "different"
        self.blocked("ACCOUNT_SCOPE_MISMATCH")

    def test_policy_allocations_cannot_exceed_capital(self):
        self.policy["sleeves"]["intraday"] = "0.50"
        self.blocked("INVALID_OR_MISSING_INPUT")

    def test_breached_existing_stop_blocks_more_risk(self):
        self.snapshot["positions"] = [{"symbol": "OTHER", "quantity": "10", "mark": "100",
            "sleeve": "swing", "stop_price": "101", "sector": "technology"}]
        self.snapshot["cash"] = "99000"
        self.blocked("EXISTING_TACTICAL_STOP_BREACHED")

    def test_price_deviation_is_bounded(self):
        self.order["limit_price"] = "105"
        self.blocked("LIMIT_TOO_FAR_FROM_CURRENT_QUOTE")

    def test_pending_exit_not_repeated(self):
        self.snapshot["open_orders"] = [{"local_ref": "exit-1", "status": "cancel_pending", "side": "sell",
            "symbol": "DEMO", "sleeve": "intraday", "remaining_quantity": "1"}]
        self.blocked("SYMBOL_HAS_PENDING_ORDER")




class InstallerTests(unittest.TestCase):
    def test_existing_destination_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            source, dest = Path(directory) / "source", Path(directory) / "dest"
            source.mkdir()
            dest.mkdir()
            (dest / "user-policy.txt").write_text("preserve")
            with self.assertRaises(FileExistsError):
                install(source, dest)
            self.assertEqual((dest / "user-policy.txt").read_text(), "preserve")

    def test_separate_temporary_copy_excludes_runtime_state(self):
        with tempfile.TemporaryDirectory() as directory:
            source, dest = Path(directory) / "source", Path(directory) / "dest"
            source.mkdir()
            (source / "SKILL.md").write_text("fictional test skill")
            (source / "private.db").write_text("must not copy")
            install(source, dest)
            self.assertTrue((dest / "SKILL.md").exists())
            self.assertFalse((dest / "private.db").exists())

    def test_recursive_copy_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                install(directory, Path(directory) / "nested")


class PortfolioTests(unittest.TestCase):
    def test_small_budget_does_not_force_unaffordable_stock(self):
        fixture = json.loads((ROOT / "examples/small-account.json").read_text())
        result = rebalance(**fixture, allow_fractional=False)
        self.assertEqual([(p["symbol"], p["quantity"]) for p in result["buy_candidates"]], [("GROWTH_A", "1")])
        self.assertEqual(result["cash_remaining_before_fees"], "455")

    def test_cash_first_and_drift_band(self):
        result = rebalance(10000, 5000, {"A": 40}, {"A": ".50"}, {"A": 100},
                           cash_floor=".10", band=".02", max_turnover=".05")
        self.assertEqual(float(result["buy_candidates"][0]["quantity"]), 5)

    def test_no_funding_from_unfilled_sale(self):
        result = rebalance(10000, 1000, {"A": 80}, {"A": ".30", "B": ".50"},
                           {"A": 100, "B": 100}, cash_floor=".10", allow_sales=True)
        self.assertFalse(result["buy_candidates"])
        self.assertEqual(result["sell_reviews"][0]["action"], "REVIEW_TRIM")

    def test_external_deposit_is_not_profit(self):
        result = performance([100, 150, 165], [50, 0])
        self.assertAlmostEqual(float(result["time_weighted_return"]), .10)

    def test_flow_adjusted_drawdown(self):
        result = performance([100, 200, 180], [100, 0])
        self.assertAlmostEqual(float(result["max_drawdown"]), .10)


if __name__ == "__main__":
    unittest.main()
