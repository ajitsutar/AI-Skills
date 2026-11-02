"""Offline intent/estimate contracts; no broker, network or execution calls."""
import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from fractional_shares import cash_requirement, size_dollar_buy
from portfolio_manager import recurring_buys


class RecurringIntentTests(unittest.TestCase):
    def recurring(self, **changes):
        inputs = dict(plan_id="demo", occurrence_id="2026-10", account_alias="fictional",
                      amounts={"A": "10.00", "B": "15.00"},
                      prices={"A": "7", "B": "11"}, available_cash="30", reserve_amount="5",
                      fee_per_order="0.25", allow_fractional=False)
        inputs.update(changes)
        return recurring_buys(**inputs)

    def assert_original_intent(self, result):
        self.assertEqual(result["plan_id"], "demo")
        self.assertEqual(result["occurrence_id"], "2026-10")
        self.assertEqual(result["account_alias"], "fictional")
        self.assertEqual(result["request_basis"], "dollar_budget")
        self.assertEqual(result["requested_amounts"], {"A": "10.00", "B": "15.00"})
        self.assertTrue(result["calculation_only"])

    def test_rounding_and_fees_do_not_replace_requested_dollars(self):
        result = self.recurring()
        self.assert_original_intent(result)
        self.assertEqual(result["estimated_cash_debit"], "18.50")
        self.assertEqual(result["cash_remaining_after_reservations"], "11.50")
        for row in result["buy_candidates"]:
            self.assertEqual(row["requested_dollar_budget"], result["requested_amounts"][row["symbol"]])
            self.assertEqual(row["quantity"], "1")
            self.assertEqual(row["fee_reserve"], "0.25")
            self.assertNotEqual(row["estimated_cash_debit"], row["requested_dollar_budget"])

    def test_cash_shortfall_retains_all_intent_without_fabricated_candidates(self):
        result = self.recurring(available_cash="24.99")
        self.assert_original_intent(result)
        self.assertEqual(result["status"], "WAIT_FOR_SETTLED_CASH")
        self.assertEqual(result["buy_candidates"], [])
        self.assertEqual(result["available_after_reserve"], "19.99")
        self.assertNotIn("estimated_cash_debit", result)

    def test_skipped_symbols_keep_requested_dollars(self):
        result = self.recurring(prices={"A": "700", "B": "1100"})
        self.assert_original_intent(result)
        self.assertEqual(result["buy_candidates"], [])
        self.assertEqual([row["symbol"] for row in result["skipped"]], ["A", "B"])
        result = self.recurring(allow_fractional=True, quantity_rules={"A": {"eligible": False}, "B": {"eligible": False}})
        self.assert_original_intent(result)
        self.assertEqual(len(result["skipped"]), 2)

    def test_price_changes_alter_estimate_not_dollars_or_occurrence_identity(self):
        first = self.recurring(allow_fractional=True)
        later = self.recurring(allow_fractional=True, prices={"A": "14", "B": "22"})
        self.assertEqual(first["requested_amounts"], later["requested_amounts"])
        for before, after in zip(first["buy_candidates"], later["buy_candidates"]):
            self.assertEqual(before["signal_id"], after["signal_id"])
            self.assertNotEqual(before["quantity"], after["quantity"])
            self.assertEqual(before["requested_dollar_budget"], after["requested_dollar_budget"])

    def test_market_price_can_exceed_full_budget_reference_estimate(self):
        result = size_dollar_buy("10.00", "100")
        self.assertEqual(result["estimated_cash_debit"], "10.00")
        self.assertEqual(result["maximum_cash_debit"], result["estimated_cash_debit"])
        self.assertEqual(result["unspent_budget"], "0.00")
        self.assertFalse(result["cash_debit_is_guaranteed"])
        self.assertEqual(result["estimate_basis"], "quantity_at_reference_price_with_supplied_fee_assumptions")
        self.assertGreater(cash_requirement(result["quantity"], "101"), Decimal(result["estimated_cash_debit"]))

    def test_input_budget_preserved_before_cent_floor(self):
        result = size_dollar_buy("10.009", "300", quantity_increment="0.0025", fee_per_order="0.005")
        self.assertEqual(result["requested_dollar_budget"], "10.009")
        self.assertEqual(result["dollar_budget"], "10.00")
        self.assertEqual(result["order_basis"], "quantity")
        self.assertEqual(result["request_basis"], "dollar_budget")

    def test_outputs_describe_calculations_not_submission_or_permission(self):
        for result in (self.recurring(), self.recurring(available_cash="0")):
            with self.subTest(status=result["status"]):
                self.assertTrue(result["calculation_only"])
                self.assertFalse(result["execution_authorized"])
                self.assertIn("not permission for host execution", result["handoff_guidance"])
                self.assertIn("actual host/broker results", result["handoff_guidance"])
                self.assertIn("native dollar instructions", result["handoff_guidance"])
                self.assertIn("not a guaranteed market debit", result["handoff_guidance"])
                for row in result["buy_candidates"]:
                    self.assertTrue(row["calculation_only"])
                    self.assertFalse(row["cash_debit_is_guaranteed"])
        self.assertFalse(self.recurring()["schedule_created"])


if __name__ == "__main__":
    unittest.main()
