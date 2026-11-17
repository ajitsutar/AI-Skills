"""Generic source/term/inventory and artifact invariants; no private case fixtures."""
import copy
from datetime import date
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import tax_lot_report as report
import accounting_tools as accounting


def fixture():
    return {"cash_ledger": {"currency": "EUR", "fees": 99},
            "sale": {"symbol": "SYNTH", "quantity": 5, "price": 100, "date": "2032-08-20", "specific_lots": [{"id": "B", "quantity": 3}, {"id": "A", "quantity": 2}]},
            "tax_lots": [{"id": "A", "symbol": "SYNTH", "quantity": 4, "unit_basis": 60, "acquired": "2030-01-04"},
                         {"id": "B", "symbol": "SYNTH", "quantity": 3, "unit_basis": 110, "acquired": "2032-08-03"},
                         {"id": "C", "symbol": "SYNTH", "quantity": 2, "unit_basis": 90, "acquired": "2032-04-15"}],
            "outside_account_transactions": None, "future_purchases": None}


def document(source=None):
    raw = json.dumps(source or fixture(), separators=(",", ":")); request = "Compare these synthetic sale alternatives, holding periods and purchase flags."
    return {"schema_version": 1, "request": {"text": request, "sha256": report.digest(request.encode())},
            "source": {"id": "original", "text": raw, "sha256": report.digest(raw.encode()), "adapter": "accounting_snapshot_v1"},
            "holding_period": {"convention": report.CONVENTION, "assumption_label": "Illustrative more-than-calendar-year analysis, not legal classification", "leap_day_policy": "unresolved"},
            "calendar": {"timestamp_timezone": None}, "common_unit_assumption": "Assume compatible source monetary units for mechanical arithmetic only.", "alternatives": ["FIFO", "HIFO"]}


def proposals(doc=None):
    return {p["method"]: p for p in report.build_report(doc or document())["proposals"]}


class TaxLotFacts(unittest.TestCase):
    def test_independent_components_and_conservation(self):
        p = proposals(); self.assertEqual(p["SPECIFIC_SOURCE"]["signed_gain"], "50")
        self.assertEqual(p["SPECIFIC_SOURCE"]["term_signed_totals"], {"long_under_assumption": "80", "short_under_assumption": "-30", "unresolved": "0"})
        self.assertEqual(p["FIFO"]["signed_gain"], "170"); self.assertEqual(p["HIFO"]["signed_gain"], "-10")
        for value in p.values():
            self.assertEqual(sum(Decimal(x["remaining_quantity"]) for x in value["lot_inventory"]), Decimal(4))
            self.assertEqual(sum(Decimal(x["signed_gain"]) for x in value["components"]), Decimal(value["signed_gain"]))
    def test_net_gain_still_loss_and_full_disposition(self):
        p = proposals()["SPECIFIC_SOURCE"]; self.assertEqual(p["loss_components"], ["B"])
        self.assertTrue(p["future_monitor_needed"]); flag = p["purchase_date_flags"][0]
        self.assertEqual((flag["linked_lot"], flag["selected_quantity"], flag["remaining_quantity"], flag["disposition"]), ("B", "3", "0", "fully_sold_in_this_proposal"))
        self.assertFalse(flag["tax_disallowance_established"]); self.assertFalse(p["tax_clearance"])
    def test_exact_partial_specific_not_greedy(self):
        source = fixture(); source["sale"]["specific_lots"] = [{"id": "B", "quantity": 2}, {"id": "A", "quantity": 3}]
        p = proposals(document(source))["SPECIFIC_SOURCE"]
        self.assertEqual(p["signed_gain"], "100"); self.assertEqual(p["purchase_date_flags"][0]["remaining_quantity"], "1")
        self.assertEqual(p["purchase_date_flags"][0]["disposition"], "partly_retained_in_this_proposal")
    def test_gain_only_no_flag(self):
        p = proposals()["FIFO"]; self.assertEqual(p["loss_components"], []); self.assertEqual(p["purchase_date_flags"], []); self.assertFalse(p["future_monitor_needed"])
    def test_fractional_quantities(self):
        source = fixture(); source["sale"]["quantity"] = "0.75"; source["sale"]["specific_lots"] = [{"id": "A", "quantity": "0.25"}, {"id": "B", "quantity": "0.50"}]
        p = proposals(document(source))["SPECIFIC_SOURCE"]; self.assertEqual(Decimal(p["signed_gain"]), Decimal("5"))
        self.assertEqual(sum(Decimal(x["quantity"]) for x in p["components"]), Decimal(".75"))
    def test_exact_original_decimal_lexeme(self):
        doc = document(); doc["source"]["text"] = doc["source"]["text"].replace('"price":100,', '"price":100.0000000000000000001,')
        doc["source"]["sha256"] = report.digest(doc["source"]["text"].encode())
        p = proposals(doc)["SPECIFIC_SOURCE"]; self.assertEqual(Decimal(p["signed_gain"]), Decimal("50.0000000000000000005"))
    def test_eligible_security_inventory(self):
        source = fixture(); source["tax_lots"].append({"id": "OTHER", "symbol": "UNRELATED", "quantity": 8, "unit_basis": 1, "acquired": "2031-01-01"})
        value = report.build_report(document(source)); self.assertEqual(value["source_lot_inventory"][-1]["scope"], "not_target_security")
        self.assertEqual(proposals(document(source))["FIFO"]["signed_gain"], "170")
    def test_invalid_lot_values(self):
        for bad in [True, "NaN", "Infinity", "-1", "0", "1e101"]:
            with self.subTest(bad=bad):
                source = fixture(); source["tax_lots"][0]["quantity"] = bad
                with self.assertRaises(ValueError): report.build_report(document(source))
    def test_duplicate_ids_overselection_and_future_lot(self):
        for change in ["duplicate", "quantity", "future"]:
            source = fixture()
            if change == "duplicate": source["tax_lots"][1]["id"] = "A"
            if change == "quantity": source["sale"]["specific_lots"][0]["quantity"] = 9
            if change == "future": source["tax_lots"][0]["acquired"] = "2033-01-01"
            with self.subTest(change=change), self.assertRaises(ValueError): report.build_report(document(source))
    def test_source_and_request_binding(self):
        for key in ["source", "request"]:
            doc = document(); doc[key]["sha256"] = "0" * 64
            with self.assertRaises(ValueError): report.build_report(doc)
    def test_duplicate_source_json_keys(self):
        doc = document(); doc["source"]["text"] = doc["source"]["text"].replace('"price":100', '"price":1,"price":100'); doc["source"]["sha256"] = report.digest(doc["source"]["text"].encode())
        with self.assertRaises(ValueError): report.build_report(doc)


class CalendarAndUnits(unittest.TestCase):
    def test_anniversary_not_universal_days(self):
        policy = document()["holding_period"]
        acquired = date(2031, 8, 20)
        self.assertEqual(report.term(acquired, date(2032, 8, 19), policy)["category"], "short_under_assumption")
        self.assertEqual(report.term(acquired, date(2032, 8, 20), policy)["category"], "short_under_assumption")
        self.assertEqual(report.term(acquired, date(2032, 8, 21), policy)["category"], "long_under_assumption")
        self.assertEqual(report.term(acquired, date(2032, 8, 19), policy)["elapsed_days"], 365)
    def test_leap_anniversary_explicit_or_unresolved(self):
        policy = document()["holding_period"]; acquired = date(2028, 2, 29); sold = date(2029, 3, 1)
        self.assertEqual(report.term(acquired, sold, policy)["category"], "unresolved")
        policy["leap_day_policy"] = "february_28"; self.assertEqual(report.term(acquired, sold, policy)["category"], "long_under_assumption")
        policy["leap_day_policy"] = "march_1"; self.assertEqual(report.term(acquired, sold, policy)["category"], "short_under_assumption")
    def test_unresolved_convention_preserves_gains(self):
        doc = document(); doc["holding_period"] = {"convention": None, "reason": "No applicable analytical convention chosen"}
        value = report.build_report(doc); self.assertEqual(value["status"], "PARTIAL")
        self.assertTrue(all(c["holding_period"]["category"] == "unresolved" for p in value["proposals"] for c in p["components"]))
        self.assertEqual(proposals(doc)["SPECIFIC_SOURCE"]["signed_gain"], "50")
    def test_calendar_source_date_no_invented_instant(self):
        value = report.build_report(document()); self.assertEqual(value["sale"]["source_date"], "2032-08-20")
        self.assertEqual(value["purchase_review_window"]["start"], "2032-07-21"); self.assertEqual(value["purchase_review_window"]["end"], "2032-09-19")
        self.assertIsNone(value["calendar"]["timestamp_timezone"])
    def test_aware_timezone_explicit(self):
        with self.assertRaises(ValueError): report.day("2032-08-20T00:30:00Z", None)
        self.assertEqual(report.day("2032-08-20T00:30:00Z", "America/Los_Angeles"), date(2032, 8, 19))
        with self.assertRaises(ValueError): report.day("2032-08-20T00:30:00", "UTC")
    def test_cash_currency_and_fee_not_transferred(self):
        value = report.build_report(document()); self.assertIsNone(value["currency_scope"]["currency"])
        self.assertFalse(value["currency_scope"]["cash_ledger_used"]); self.assertEqual(value["proposals"][0]["signed_gain"], "50")
    def test_shared_currency_explicit(self):
        source = fixture(); source["monetary_scope"] = {"currency": "USD", "applies_to": ["sale", "tax_lots"]}
        doc = document(source); doc["common_unit_assumption"] = None
        self.assertEqual(report.build_report(doc)["currency_scope"]["currency"], "USD")
    def test_conflicting_currency_and_missing_assumption(self):
        source = fixture(); source["sale"]["currency"] = "USD"; source["tax_lots"][0]["currency"] = "EUR"
        with self.assertRaises(ValueError): report.build_report(document(source))
        doc = document(); doc["common_unit_assumption"] = None
        with self.assertRaises(ValueError): report.build_report(doc)


class PurchaseEvidence(unittest.TestCase):
    def test_unknown_and_explicit_empty_distinct(self):
        value = report.build_report(document()); self.assertEqual(value["external_evidence"]["coverage"]["future_purchases"], "UNKNOWN_NULL")
        source = fixture(); source["future_purchases"] = []; source["outside_account_transactions"] = []
        value = report.build_report(document(source)); self.assertEqual(value["external_evidence"]["coverage"]["future_purchases"], "EMPTY_SUPPLIED_SCOPE")
        self.assertEqual(value["status"], "COMPLETE_FOR_SUPPORTED_ANALYTICAL_SCOPE"); self.assertFalse(value["semantic_request_completeness_verified"])
        self.assertFalse(value["proposals"][0]["external_coverage_complete"])
    def test_unlinked_external_and_window_edges(self):
        source = fixture(); source["outside_account_transactions"] = [
            {"id": "edge", "symbol": "SYNTH", "side": "buy", "date": "2032-07-21", "quantity": 1},
            {"id": "old", "symbol": "SYNTH", "side": "buy", "date": "2032-07-20", "quantity": 1}]
        source["future_purchases"] = [{"id": "future", "symbol": "SYNTH", "side": "buy", "date": "2032-09-19", "quantity": 2}, {"id": "beyond", "symbol": "SYNTH", "side": "buy", "date": "2032-09-20", "quantity": 2}]
        flags = proposals(document(source))["SPECIFIC_SOURCE"]["purchase_date_flags"]
        self.assertEqual(len(flags), 3); self.assertEqual({f["days_from_sale"] for f in flags}, {-17, -30, 30})
        self.assertEqual(sum(f["disposition"] == "linkage_unknown" for f in flags), 2)
    def test_linked_repeat_does_not_duplicate_acquisition(self):
        source = fixture(); source["outside_account_transactions"] = [{"id": "repeat", "symbol": "SYNTH", "side": "buy", "date": "2032-08-03", "quantity": 3, "lot_ref": "B"}]
        self.assertEqual(len(proposals(document(source))["SPECIFIC_SOURCE"]["purchase_date_flags"]), 1)
        source["outside_account_transactions"][0]["quantity"] = 2
        with self.assertRaises(ValueError): report.build_report(document(source))
    def test_unsupported_record_visible_partial(self):
        source = fixture(); source["outside_account_transactions"] = [{"ticker": "SYNTH", "amount": 4}]
        value = report.build_report(document(source)); self.assertEqual(value["status"], "PARTIAL")
        self.assertEqual(value["external_evidence"]["records"][0]["status"], "UNSUPPORTED_MAPPING")
    def test_reference_namespaces_cannot_collide(self):
        source = fixture(); source["tax_lots"][1]["id"] = "outside_account_transactions:x"; source["sale"]["specific_lots"][0]["id"] = "outside_account_transactions:x"
        source["outside_account_transactions"] = [{"id": "x", "symbol": "SYNTH", "side": "buy", "date": "2032-08-03", "quantity": 1}]
        flags = proposals(document(source))["SPECIFIC_SOURCE"]["purchase_date_flags"]; self.assertEqual(len(flags), 2)
        self.assertEqual({x["disposition"] for x in flags}, {"fully_sold_in_this_proposal", "linkage_unknown"})


class ArtifactDelivery(unittest.TestCase):
    def make(self, root):
        root = Path(root).resolve()
        source = root / "input.json"; source.write_text(json.dumps(document()), encoding="utf8")
        output = root / "result"; receipt = report.compose(source, output)
        return source, output, receipt
    def test_compose_replay_and_native_cli(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); source, output, receipt = self.make(root)
            self.assertEqual(report.verify(output)["status"], "SOURCE_BOUND_TAX_LOT_REPORT_REPLAYED")
            self.assertEqual(set(receipt["dependencies"]), set(report.DEPENDENCIES))
            command = subprocess.run([sys.executable, "-B", report.__file__, "verify", str(output)], capture_output=True, text=True)
            self.assertEqual(command.returncode, 0, command.stderr)
            self.assertFalse(json.loads((output / "response.json").read_bytes())["execution_authorized"])
    def test_modified_projection_rejected(self):
        for name in ["first-response.md", "response.json", "summary.txt"]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as td:
                _, output, _ = self.make(Path(td)); (output / name).write_bytes(b"Omitted term/inventory content")
                with self.assertRaises(ValueError): report.verify(output)
    def test_unknown_artifact_and_dependency_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            _, output, _ = self.make(Path(td)); (output / "extra.txt").write_text("unexpected")
            with self.assertRaises(ValueError): report.verify(output)
        with tempfile.TemporaryDirectory() as td:
            _, output, _ = self.make(Path(td))
            with mock.patch.object(report, "module_hashes", return_value={}):
                with self.assertRaises(ValueError): report.verify(output)
    def test_source_identity_and_external_receipt_pin(self):
        with tempfile.TemporaryDirectory() as td:
            _, output, _ = self.make(Path(td))
            with self.assertRaises(ValueError): report.verify(output, "0" * 64)
            (output / "original-source.json").write_text("{}")
            with self.assertRaises(ValueError): report.verify(output)
    def test_existing_output_not_overwritten(self):
        with tempfile.TemporaryDirectory() as td:
            source, output, _ = self.make(Path(td)); before = (output / "first-response.md").read_bytes()
            with self.assertRaises(ValueError): report.compose(source, output)
            self.assertEqual((output / "first-response.md").read_bytes(), before)


class AdditionalIntegrity(unittest.TestCase):
    def test_receipt_authority_tampering(self):
        for field, value in [("execution_authorized", True), ("semantic_request_completeness_verified", True), ("schema_version", True), ("extra", "unsupported")]:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as td:
                _, output, receipt = ArtifactDelivery().make(Path(td)); receipt[field] = value
                (output / "receipt.json").write_text(json.dumps(receipt), encoding="utf8")
                with self.assertRaises(ValueError): report.verify(output)
    def test_reparse_path_rejected(self):
        with mock.patch.object(Path, "is_symlink", return_value=True):
            with self.assertRaises(ValueError): report.safe_path("synthetic-output")
    def test_size_bound_and_unknown_input(self):
        with self.assertRaises(ValueError): report.parse_json(b" " * (report.MAX_BYTES + 1))
        value = document(); value["caller_verified"] = True
        with self.assertRaises(ValueError): report.build_report(value)
    def test_calendar_policy_visible_in_markdown(self):
        value = document(); value["holding_period"]["leap_day_policy"] = "march_1"
        output = report.render_markdown(report.build_report(value))
        self.assertIn("Leap-day policy: march_1", output)
        self.assertIn("Calendar:", output)


class LegacyPublicBehavior(unittest.TestCase):
    def test_legacy_group_error_precedes_invalid_transaction_iterable(self):
        with self.assertRaisesRegex(AttributeError, "get"):
            accounting.wash_sale_review("SYNTH", "2032-01-01T12:00:00+00:00", True, None, identity_groups="bad")
        with self.assertRaises(TypeError):
            accounting.wash_sale_review("SYNTH", "2032-01-01T12:00:00+00:00", True, None)
    def test_legacy_lot_shapes_and_specific_order(self):
        lots = [{"lot_ref": "a", "symbol": "X", "quantity": 4, "cost_per_share": 10, "acquired_at": "2030-01-01T00:00:00Z"}, {"lot_ref": "b", "symbol": "X", "quantity": 4, "cost_per_share": 20, "acquired_at": "2031-01-01T00:00:00Z"}]
        value = accounting.select_lots(lots, 5, "SPECIFIC", ["b", "a"])
        self.assertEqual(value["lots"], [{"lot_ref": "b", "quantity": "4", "basis": "80"}, {"lot_ref": "a", "quantity": "1", "basis": "10"}])
        self.assertEqual(set(value), {"method", "lots", "execution_authorized", "next_step"})
        lots[0]["acquired_at"] = "2030-01-01"
        with self.assertRaises(ValueError): accounting.select_lots(lots, 1)
    def test_legacy_no_loss_ignores_invalid_transactions(self):
        value = accounting.wash_sale_review("X", "2032-08-20T12:00:00Z", False, [{"at": "bad"}])
        self.assertEqual(value["potential_replacements"], []); self.assertFalse(value["tax_clearance"])
    def test_legacy_validation_order(self):
        tx = [{"at": "2032-08-19T12:00:00Z", "side": "buy", "symbol": "X", "quantity": -1, "local_ref": "a"}, {"at": "bad"}]
        with self.assertRaisesRegex(ValueError, "positive"):
            accounting.wash_sale_review("X", "2032-08-20T12:00:00Z", True, tx)


if __name__ == "__main__":
    unittest.main()
