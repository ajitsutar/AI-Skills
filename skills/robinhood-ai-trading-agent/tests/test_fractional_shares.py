"""Fictional cash, quantity and broker-schema contracts; no live brokerage calls."""
import copy
import json
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from fractional_shares import cash_requirement, round_quantity_down, size_dollar_buy
from risk_engine import canonical_hash, dec, evaluate, size_tactical, timestamp
from portfolio_manager import rebalance, recurring_buys
from broker_bridge import build_request
from execution_ledger import ExecutionLedger, GateClosed
from test_personal_components import capability_fixture


def rules(now):
    return dict(eligible=True, quantity_increment="0.000001", min_quantity="0.000001",
                min_notional="1", order_types=["limit"], time_in_force=["day"],
                sides=["buy", "sell"], sessions=["regular"], checked_at=now.isoformat(),
                source="official_broker", evidence=["fictional test observation"])


class SizingTests(unittest.TestCase):
    def test_400_dollars_buys_fraction_of_expensive_stock_without_exceeding_budget(self):
        result = size_dollar_buy("400", "1046.08", fee_per_share="0.005", fee_per_order="0.15")
        self.assertGreater(dec(result["quantity"]), 0)
        self.assertLess(dec(result["quantity"]), 1)
        self.assertLessEqual(dec(result["maximum_cash_debit"]), 400)
        self.assertLess(dec(result["unspent_budget"]), Decimal("0.02"))
        step = dec(result["quantity_increment"])
        self.assertGreater(cash_requirement(dec(result["quantity"]) + step, "1046.08", ".005", ".15"), 400)

    def test_one_dollar_and_below_minimum(self):
        self.assertEqual(size_dollar_buy("1", "1000")["quantity"], "0.001000")
        self.assertEqual(size_dollar_buy(".99", "1000")["status"], "BELOW_MINIMUM_OR_BUDGET")
        self.assertEqual(size_dollar_buy("1", "1000", fee_per_order=".01")["quantity"], "0")

    def test_arbitrary_quantity_increment_and_cent_fee_rounding(self):
        result = size_dollar_buy("10.009", "300", quantity_increment="0.0025", fee_per_order=".005")
        self.assertEqual(dec(result["quantity"]) % Decimal(".0025"), 0)
        self.assertLessEqual(dec(result["maximum_cash_debit"]), 10)
        self.assertEqual(cash_requirement(".000001", "100", ".001", ".001"), Decimal(".02"))
        self.assertEqual(round_quantity_down(".012345", ".0025"), Decimal(".0125") - Decimal(".0025"))

    def test_invalid_numbers_and_grid_fail(self):
        for value in (True, "NaN", "Infinity", "-1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                size_dollar_buy(value, "100")
        for step in ("0", "-1", "2", "0.0000000000000000001"):
            with self.subTest(step=step), self.assertRaises(ValueError):
                size_dollar_buy("100", "100", quantity_increment=step)

    def test_whole_share_mode_retained(self):
        self.assertEqual(size_dollar_buy("400", "700", quantity_increment="1")["quantity"], "0")
        self.assertEqual(size_dollar_buy("400", "100", quantity_increment="1")["quantity"], "4")

    def test_tactical_fractional_size_respects_both_risk_and_cash(self):
        result = size_tactical(400, 1000, 900, ".01", 400, quantity_increment=".000001",
                               min_notional="1", fee_per_order=".25")
        self.assertGreater(dec(result["quantity"]), 0)
        self.assertLess(dec(result["quantity"]), 1)
        self.assertLessEqual(dec(result["planned_loss"]), 4)
        self.assertLessEqual(cash_requirement(result["quantity"], 1000, fee_per_order=".25"), 400)

    def test_tiny_tactical_size_includes_penny_rounded_round_trip_fees(self):
        result = size_tactical("100", "100", "99", ".001", "100", slippage_bps=0,
                               fee_per_share=".005", quantity_increment=".000001", min_notional="1")
        self.assertEqual(dec(result["quantity"]), Decimal(".08"))
        self.assertEqual(dec(result["planned_loss"]), Decimal(".10"))

    def test_default_rebalance_uses_fractional_planning_and_reserves_fees(self):
        result = rebalance(400, 400, {}, {"HIGH": "1"}, {"HIGH": "1000"}, cash_floor="0",
                           band="0", max_turnover="1", fee_per_order=".25")
        row = result["buy_candidates"][0]
        self.assertGreater(dec(row["quantity"]), 0)
        self.assertLessEqual(dec(row["maximum_cash_debit"]), 400)
        self.assertIn("UNVERIFIED", row["quantity_rules_status"])
        self.assertEqual(rebalance(400, 400, {}, {"HIGH": "1"}, {"HIGH": "1000"},
                                  cash_floor="0", max_turnover="1", allow_fractional=False)["buy_candidates"], [])

    def test_supplied_unknown_eligibility_skips_not_assumes(self):
        result = rebalance(400, 400, {}, {"HIGH": "1"}, {"HIGH": "1000"}, cash_floor="0",
                           max_turnover="1", quantity_rules={"HIGH": {"eligible": None}})
        self.assertFalse(result["buy_candidates"])
        self.assertEqual(result["skipped"][0]["reason"], "FRACTIONAL_ELIGIBILITY_NOT_CONFIRMED")

    def test_recurring_small_amounts_and_stable_occurrence_identity(self):
        inputs = dict(plan_id="monthly", occurrence_id="2026-10-15", account_alias="demo",
                      amounts={"A": "10", "B": "15"}, prices={"A": "700", "B": "400"},
                      available_cash="30", reserve_amount="5")
        first = recurring_buys(**inputs)
        self.assertEqual(len(first["buy_candidates"]), 2)
        self.assertGreaterEqual(dec(first["cash_remaining_after_reservations"]), 5)
        self.assertFalse(first["schedule_created"])
        inputs["prices"]["A"] = "750"
        again = recurring_buys(**inputs)
        self.assertEqual(first["buy_candidates"][0]["signal_id"], again["buy_candidates"][0]["signal_id"])
        inputs["occurrence_id"] = "2026-11-16"
        self.assertNotEqual(first["buy_candidates"][0]["signal_id"], recurring_buys(**inputs)["buy_candidates"][0]["signal_id"])
        inputs["available_cash"] = "24"
        self.assertEqual(recurring_buys(**inputs)["status"], "WAIT_FOR_SETTLED_CASH")


class FractionalRiskTests(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads((ROOT / "templates/policy.example.json").read_text())
        self.snapshot = json.loads((ROOT / "examples/snapshot.json").read_text())
        self.order = json.loads((ROOT / "examples/order.json").read_text())
        self.now = timestamp("2026-10-06T14:00:00Z")
        self.policy["fractional_shares"] = dict(enabled=True, max_rules_age_seconds=60)
        self.order["quantity"] = ".123456"
        self.snapshot["quotes"]["DEMO"]["fractional_rules"] = rules(self.now)

    def result(self):
        return evaluate(self.policy, self.snapshot, self.order, self.now)

    def test_fractional_limit_passes_all_existing_paper_risk_gates(self):
        self.assertTrue(self.result()["allowed"], self.result())

    def test_fractional_permission_metadata_minimum_and_increments(self):
        changes = [({"eligible": None}, "ELIGIBILITY"), ({"quantity_increment": ".01"}, "INCREMENT"),
                   ({"min_notional": "20"}, "MINIMUM"), ({"min_quantity": "1"}, "MINIMUM"),
                   ({"checked_at": "2026-10-05T14:00:00Z"}, "STALE"),
                   ({"order_types": ["market"]}, "UNSUPPORTED"), ({"evidence": []}, "INVALID_OR_MISSING")]
        original = rules(self.now)
        for change, expected in changes:
            with self.subTest(change=change):
                self.snapshot["quotes"]["DEMO"]["fractional_rules"] = dict(original, **change)
                self.assertFalse(self.result()["allowed"])
                self.assertIn(expected, str(self.result()["reasons"]))

    def test_opt_out_and_missing_rules_block(self):
        self.policy["fractional_shares"]["enabled"] = False
        self.assertIn("FRACTIONAL_SHARES_NOT_ENABLED", self.result()["reasons"])
        del self.snapshot["quotes"]["DEMO"]["fractional_rules"]
        self.assertIn("FRACTIONAL_RULES_MISSING", self.result()["reasons"])

    def test_malformed_semantics_and_evidence_never_authorize_fractional_order(self):
        for field, value in (("order_types", "unlimited"), ("time_in_force", "notday"),
                             ("sides", "nobuy"), ("sessions", "irregular"), ("evidence", "unverified"),
                             ("sides", ["notbuy"]), ("evidence", [True]), ("sessions", {"regular": True})):
            with self.subTest(field=field, value=value):
                self.snapshot["quotes"]["DEMO"]["fractional_rules"] = dict(rules(self.now), **{field: value})
                result = self.result()
                self.assertFalse(result["allowed"], result)
                self.assertIn("INVALID_OR_MISSING_INPUT", str(result["reasons"]))
        for malformed in (None, [], "enabled"):
            with self.subTest(policy=malformed):
                self.policy["fractional_shares"] = malformed
                self.assertFalse(self.result()["allowed"])
        self.policy["fractional_shares"] = dict(enabled=True, max_rules_age_seconds=60)
        for malformed in (None, [], "eligible"):
            with self.subTest(rules=malformed):
                self.snapshot["quotes"]["DEMO"]["fractional_rules"] = malformed
                self.assertFalse(self.result()["allowed"])

    def test_live_source_requirement_and_native_notional_block(self):
        self.policy["mode"] = "approval"
        self.snapshot["quotes"]["DEMO"]["fractional_rules"]["source"] = "retail documentation"
        self.assertIn("FRACTIONAL_RULES_REQUIRE_OFFICIAL_BROKER", self.result()["reasons"])
        self.order["order_basis"] = "notional"
        self.assertIn("NATIVE_DOLLAR_ORDER_ADAPTER_UNAVAILABLE", self.result()["reasons"])

    def test_dollar_budget_reserves_fees_and_cents(self):
        self.order["dollar_budget"] = "12.34"
        self.assertIn("ORDER_EXCEEDS_DOLLAR_BUDGET_INCLUDING_FEES", self.result()["reasons"])
        self.order["dollar_budget"] = "12.36"
        self.assertTrue(self.result()["allowed"], self.result())

    def test_fractional_risk_gate_uses_same_rounded_fees_as_sizing(self):
        self.order.update(quantity=".08", limit_price="100", stop_price="99", target_price="105")
        self.policy["limits"].update(slippage_bps=0, fee_per_share=".005", risk_per_trade=".000001")
        result = self.result()
        self.assertTrue(result["allowed"], result)
        self.assertEqual(dec(result["metrics"]["planned_loss"]), Decimal(".10"))
        self.order["quantity"] = ".080001"
        self.assertIn("PER_TRADE_RISK_CAP", self.result()["reasons"])

    def test_fractional_sell_cannot_consume_reserved_or_another_sleeve_shares(self):
        self.snapshot["positions"] = [dict(symbol="DEMO", quantity=".2", mark="100", sleeve="intraday", stop_price="98", sector="technology")]
        self.snapshot["cash"] = "99980"
        self.order["side"] = "sell"
        self.assertTrue(self.result()["allowed"], self.result())
        self.snapshot["open_orders"] = [dict(local_ref="protect", status="cancel_pending", symbol="DEMO", side="sell", sleeve="intraday", remaining_quantity=".1")]
        self.assertIn("SELL_EXCEEDS_SLEEVE_AVAILABLE_SHARES", self.result()["reasons"])

    def test_decimal_partial_fill_cancel_restart_and_duplicate_protection(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "ledger.db"
            ledger = ExecutionLedger(path)
            ledger.claim(self.policy, self.snapshot, self.order, {}, now=self.now)
            ledger.reconcile(self.order["id"], "PARTIALLY_FILLED", ".023456", "100", self.now)
            ledger.close()
            ledger = ExecutionLedger(path)
            try:
                row = ledger.reconcile(self.order["id"], "CANCELLED", ".03456789", "100", self.now)
                self.assertEqual(row["filled"], "0.03456789")  # Actual fills are never rounded to the order-entry grid.
                self.assertFalse(ledger.unresolved())
                with self.assertRaisesRegex(GateClosed, "DUPLICATE"):
                    ledger.claim(self.policy, self.snapshot, self.order, {}, now=self.now)
                with self.assertRaisesRegex(GateClosed, "EXCESS_FILL"):
                    ledger.reconcile(self.order["id"], "FILLED", ".13", "100", self.now)
                self.assertEqual(ledger.unresolved()[0]["state"], "UNKNOWN")
            finally:
                ledger.close()


class FractionalBrokerTests(unittest.TestCase):
    def setUp(self):
        self.caps = capability_fixture()
        self.now = timestamp(self.caps["checked_at"])
        self.tool = self.caps["operations"]["submit"]
        self.tool["bindings"]["quantity"]["type"] = "string"
        self.tool["input_schema"]["properties"]["quantity"] = {"type": "string"}
        self.tool["schema_hash"] = canonical_hash(self.tool["input_schema"])
        self.inputs = dict(order=dict(symbol="DEMO", side="buy", quantity="0.123456", limit_price="100", account_alias="demo",
                                      order_type="limit", time_in_force="day", extended_hours=False), private_routing={"account": "fixture"})

    def build(self):
        return build_request(self.caps, "submit", self.inputs, self.now, "demo")

    def test_observed_number_schema_alone_does_not_prove_fractional_execution(self):
        with self.assertRaisesRegex(ValueError, "Observed fractional"):
            self.build()
        self.tool["fractional_share_semantics"] = dict(quantity_based=True, cumulative_fractional_fills=True,
            order_types=["limit"], time_in_force=["day"], sides=["buy", "sell"], sessions=["regular"], evidence=["fictional schema"])
        result = self.build()
        self.assertEqual(result["request"]["arguments"]["quantity"], "0.123456")
        self.assertFalse(result["execution_authorized"])
        self.tool["fractional_share_semantics"]["cumulative_fractional_fills"] = False
        with self.assertRaisesRegex(ValueError, "Observed fractional"):
            self.build()

    def test_integer_only_tool_never_truncates_a_fraction(self):
        self.tool["bindings"]["quantity"]["type"] = "integer"
        with self.assertRaisesRegex(ValueError, "Noninteger"):
            self.build()

    def test_malformed_broker_semantic_strings_never_match_by_substring(self):
        valid = dict(quantity_based=True, cumulative_fractional_fills=True, order_types=["limit"],
                     time_in_force=["day"], sides=["buy", "sell"], sessions=["regular"], evidence=["fictional schema"])
        for field, value in (("order_types", "unlimited"), ("time_in_force", "notday"),
                             ("sides", "nobuy"), ("sessions", "irregular"), ("evidence", "unverified")):
            with self.subTest(field=field):
                self.tool["fractional_share_semantics"] = dict(valid, **{field: value})
                with self.assertRaisesRegex(ValueError, "nonempty list"):
                    self.build()
        for malformed in (None, [], "supported"):
            with self.subTest(semantics=malformed):
                self.tool["fractional_share_semantics"] = malformed
                with self.assertRaises(ValueError):
                    self.build()


if __name__ == "__main__":
    unittest.main()
