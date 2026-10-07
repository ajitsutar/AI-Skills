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
from execution_ledger import ExecutionLedger, GateClosed
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
        self.assertFalse(result["allowed"], result)
        self.assertTrue(any(code in r for r in result["reasons"]), result)


class RiskTests(Fixture):
    def test_valid_fixture(self):
        self.assertTrue(self.result()["allowed"], self.result())

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
            self.assertFalse(self.result()["allowed"], self.result())

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
        self.blocked("WHOLE_SHARES_REQUIRED")
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
        self.assertTrue(self.result()["allowed"], self.result())
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


class ExecutionTests(Fixture):
    def setUp(self):
        super().setUp()
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "execution.db"
        self.ledger = ExecutionLedger(self.path)
        self.snapshot.update(session_activity_reconciled=True,external_session_order_count=0,external_session_turnover='0',external_setup_entry_counts={})
        # These tests isolate legacy authorization/journal invariants. Full real
        # readiness integration (without this mock) is in test_personal_runtime.
        readiness = patch("personal_readiness.entry_readiness", return_value={
            "ready": True, "reasons": [], "evidence": {"request_hash": "unit-test-only"}})
        readiness.start()
        self.addCleanup(readiness.stop)
        self.review = {"order_hash": canonical_hash(self.order), "official_mcp": True,
                       "snapshot_hash": canonical_hash(self.snapshot),
                       "accepted": True, "supported_order": True, "checked_at": self.now.isoformat(),
                       "trade_approvals_enabled": False, "warnings": [], "exit_plan_verified": True,
                       "readiness_inputs": {}}

    def tearDown(self):
        self.ledger.close()
        self.temp.cleanup()

    def grant(self, kind="mandate"):
        personal = json.loads((ROOT / "templates/personal-policy.example.json").read_text())
        for key in ("schema_version", "configuration_status", "requirements", "event_policies", "strategy_registry", "stress_scenarios"):
            self.policy[key] = personal[key]
        for key in ("stress_loss_fraction", "portfolio_annualized_volatility"):
            self.policy["limits"][key] = personal["limits"][key]
        self.policy["deployment_context"] = "personal"
        self.policy["mode"] = "bounded_autonomous" if kind == "mandate" else "approval"
        self.policy["live_validated_setups"] = ["opening_range_breakout"]
        grant = {"id": "grant-1", "kind": kind, "policy_hash": canonical_hash(self.policy),
                 "account_alias": "demo-agentic", "starts_at": "2026-10-06T13:00:00Z",
                 "expires_at": "2026-10-06T20:00:00Z", "human_authorization_ref": "synthetic-test-only",
                 "order_hash": canonical_hash(self.order), "review_hash": canonical_hash(self.review)}
        self.ledger.authorize(grant)

    def claim(self, id=None):
        return self.ledger.claim(self.policy, self.snapshot, self.order, self.review, id, self.now)

    def test_paper_never_returns_live_permission(self):
        self.assertFalse(self.claim()["may_submit_once"])

    def test_authorized_bounded_order(self):
        self.grant()
        self.assertTrue(self.claim("grant-1")["may_submit_once"])

    def test_live_requires_human_record(self):
        self.policy["mode"] = "bounded_autonomous"
        self.policy["deployment_context"] = "personal"
        self.policy["live_validated_setups"] = ["opening_range_breakout"]
        with self.assertRaisesRegex(GateClosed, "NO_ACTIVE_HUMAN"):
            self.claim()

    def test_unvalidated_strategy_blocked(self):
        self.grant()
        self.policy["live_validated_setups"] = []
        with self.assertRaisesRegex(GateClosed, "STRATEGY_NOT_PROMOTED"):
            self.claim("grant-1")

    def test_policy_change_invalidates_mandate(self):
        self.grant()
        self.policy["limits"]["max_order_notional"] = "5001"
        with self.assertRaisesRegex(GateClosed, "POLICY_CHANGED"):
            self.claim("grant-1")

    def test_revoked_authorization(self):
        self.grant()
        self.ledger.revoke("grant-1")
        with self.assertRaisesRegex(GateClosed, "NO_ACTIVE_HUMAN"):
            self.claim("grant-1")

    def test_changed_exact_approval(self):
        self.grant("order")
        self.order["quantity"] = "19"
        with self.assertRaisesRegex(GateClosed, "APPROVED_ORDER_OR_REVIEW_CHANGED"):
            self.claim("grant-1")

    def test_broker_approval_cannot_be_bypassed(self):
        self.grant()
        self.review["trade_approvals_enabled"] = True
        with self.assertRaisesRegex(GateClosed, "BROKER_REQUIRES_MANUAL"):
            self.claim("grant-1")

    def test_autonomous_warnings_block(self):
        self.grant()
        self.review["warnings"] = ["New warning"]
        with self.assertRaisesRegex(GateClosed, "NEW_BROKER_WARNINGS"):
            self.claim("grant-1")

    def test_protection_is_required(self):
        self.grant()
        self.review["exit_plan_verified"] = False
        with self.assertRaisesRegex(GateClosed, "NO_VERIFIED_PROTECTION"):
            self.claim("grant-1")

    def test_duplicate_across_restart(self):
        self.claim()
        self.ledger.close()
        self.ledger = ExecutionLedger(self.path)
        with self.assertRaisesRegex(GateClosed, "DUPLICATE"):
            self.claim()

    def test_timeout_blocks_other_intents(self):
        self.claim()
        self.ledger.reconcile(self.order["id"], "UNKNOWN", "0")
        self.order["id"] = "another"
        self.order["signal_id"] = "different-signal"
        with self.assertRaisesRegex(GateClosed, "UNRESOLVED_PRIOR"):
            self.claim()

    def test_partial_cancel_retains_fills_and_is_idempotent(self):
        self.claim()
        self.ledger.reconcile(self.order["id"], "PARTIALLY_FILLED", "5", "100")
        self.ledger.reconcile(self.order["id"], "CANCEL_PENDING", "5", "100")
        self.assertEqual(len(self.ledger.unresolved()), 1)
        r = self.ledger.reconcile(self.order["id"], "CANCELLED", "7", "100")
        self.assertEqual(r["filled"], "7")
        self.ledger.reconcile(self.order["id"], "CANCELLED", "7", "100")
        self.assertFalse(self.ledger.unresolved())
        with self.assertRaisesRegex(GateClosed, "CONTRADICTORY_TERMINAL"):
            self.ledger.reconcile(self.order["id"], "FILLED", "20", "100")

    def test_cumulative_fill_cannot_regress_or_overfill(self):
        self.claim()
        self.ledger.reconcile(self.order["id"], "PARTIALLY_FILLED", "5", "100")
        for filled in (4, 21):
            with self.assertRaisesRegex(GateClosed, "NONMONOTONIC_OR_EXCESS"):
                self.ledger.reconcile(self.order["id"], "PARTIALLY_FILLED", filled, 100)

    def test_filled_requires_entire_quantity(self):
        self.claim()
        with self.assertRaisesRegex(GateClosed, "FILLED_REQUIRES_FULL"):
            self.ledger.reconcile(self.order["id"], "FILLED", 5, 100)

    def test_contradictory_terminal_state_latches_unknown_across_restart(self):
        self.claim()
        self.ledger.reconcile(self.order["id"], "CANCELLED", 0)
        with self.assertRaisesRegex(GateClosed, "CONTRADICTORY_TERMINAL"):
            self.ledger.reconcile(self.order["id"], "OPEN", 0)
        self.ledger.close()
        self.ledger = ExecutionLedger(self.path)
        self.snapshot["reconciled_through_intent"] = self.order["id"]
        self.order["id"], self.order["signal_id"] = "after-conflict", "after-conflict-signal"
        with self.assertRaisesRegex(GateClosed, "UNRESOLVED_PRIOR"):
            self.claim()

    def test_identical_terminal_fill_accepts_equivalent_decimal_format(self):
        self.claim()
        self.ledger.reconcile(self.order["id"], "FILLED", 20, "100.00")
        self.ledger.reconcile(self.order["id"], "FILLED", "20.0", "100")
        self.assertFalse(self.ledger.unresolved())

    def test_live_mode_switch_does_not_reset_daily_order_count(self):
        self.policy["limits"]["max_orders_per_day"] = 1
        self.grant()
        self.claim("grant-1")
        previous = self.order["id"]
        self.ledger.reconcile(previous, "CANCELLED", 0)
        self.policy["mode"] = "approval"
        self.snapshot["reconciled_through_intent"] = previous
        self.order["id"], self.order["signal_id"] = "next-live", "next-live-signal"
        self.review["order_hash"] = canonical_hash(self.order)
        self.review["snapshot_hash"] = canonical_hash(self.snapshot)
        self.ledger.authorize({"id": "grant-2", "kind": "order", "policy_hash": canonical_hash(self.policy),
            "account_alias": self.snapshot["account_alias"], "starts_at": "2026-10-06T13:00:00Z",
            "expires_at": "2026-10-06T20:00:00Z", "human_authorization_ref": "test-only",
            "order_hash": canonical_hash(self.order), "review_hash": canonical_hash(self.review)})
        with self.assertRaisesRegex(GateClosed, "DAILY_ORDER_LIMIT"):
            self.claim("grant-2")

    def test_new_order_requires_snapshot_reconciliation_after_last_fill(self):
        self.claim()
        self.ledger.reconcile(self.order["id"], "FILLED", 20, 100)
        self.order["id"] = "new-after-fill"
        self.order["signal_id"] = "next-signal"
        with self.assertRaisesRegex(GateClosed, "REFRESH_BROKER_SNAPSHOT"):
            self.claim()

    def test_changed_broker_snapshot_needs_new_review(self):
        self.grant()
        self.snapshot["day_pnl_ex_flows"] = "1"
        with self.assertRaisesRegex(GateClosed, "BROKER_SNAPSHOT_CHANGED"):
            self.claim("grant-1")

    def test_concurrent_claims_only_one_wins(self):
        def worker(n):
            ledger = ExecutionLedger(self.path)
            order = dict(self.order, id="thread-" + str(n), signal_id="signal-" + str(n))
            try:
                ledger.claim(self.policy, self.snapshot, order, {}, now=self.now)
                return True
            except GateClosed:
                return False
            finally:
                ledger.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sum(pool.map(worker, (1, 2))), 1)

    def test_new_id_cannot_replay_same_signal_after_fill(self):
        self.claim()
        self.ledger.reconcile(self.order["id"], "FILLED", 20, 100)
        self.snapshot["reconciled_through_intent"] = self.order["id"]
        self.order["id"] = "same-signal-new-id"
        with self.assertRaisesRegex(GateClosed, "DUPLICATE"):
            self.claim()

    def test_learning_context_blocks_even_with_live_mode(self):
        self.policy["mode"] = "bounded_autonomous"
        with self.assertRaisesRegex(GateClosed, "LEARNING_CONTEXT_LIVE_EXECUTION_DISABLED"):
            self.claim()


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
        result = rebalance(**fixture)
        self.assertEqual([(p["symbol"], p["quantity"]) for p in result["buy_candidates"]], [("GROWTH_A", "1")])
        self.assertEqual(result["cash_remaining_before_fees"], "455")

    def test_cash_first_and_drift_band(self):
        result = rebalance(10000, 5000, {"A": 40}, {"A": ".50"}, {"A": 100},
                           cash_floor=".10", band=".02", max_turnover=".05")
        self.assertEqual(result["buy_candidates"][0]["quantity"], "5")

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
