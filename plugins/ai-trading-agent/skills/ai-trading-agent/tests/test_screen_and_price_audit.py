import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from price_audit import audit_prices, timestamp
from screen_review import REQUIRED_CHECKS, assess_candidate, review_screen


RAW = b"fixture bytes; not market data"
TIMES = [timestamp("2026-10-01T20:00:00Z"), timestamp("2026-10-02T20:00:00Z"),
         timestamp("2026-10-05T20:00:00Z")]


def audit_fixture():
    review = {"status": "reviewed", "window_start": TIMES[0].isoformat(),
              "window_end": TIMES[-1].isoformat(), "evidence": ["unit-test assertion only"]}
    return {"schema_version": 1, "csv_sha256": hashlib.sha256(RAW).hexdigest(),
            "close_column": "close", "timestamp_column": "timestamp", "periods_per_year": 252,
            "symbol": "FIXTURE", "provider": "unit-test fixture", "provider_field": "fixture.close",
            "bar_interval": "1d", "adjustment_notes": "Artificial declarations for unit tests",
            "retrieved_at": "2026-10-06T20:00:00Z", "data_kind": "fictional",
            "price_basis": "split_adjusted", "corporate_actions": {**review, "events": []},
            "session_review": {**review, "calendar": "fictional calendar"}, "large_move_reviews": []}


class PriceAuditTests(unittest.TestCase):
    def test_absent_audit_computes_but_cannot_size(self):
        result = audit_prices(RAW, [100, 101, 102], TIMES)
        self.assertEqual(result["status"], "UNVERIFIED")
        self.assertFalse(result["eligible_for_sizing"])

    def test_split_sized_jump_without_audit_blocks_fit(self):
        with self.assertRaisesRegex(ValueError, "Unreviewed price jump"):
            audit_prices(RAW, [100, 50, 51], TIMES)

    def test_split_sized_jump_even_with_generic_review_blocks_fit(self):
        with self.assertRaisesRegex(ValueError, "Unreviewed price jump"):
            audit_prices(RAW, [100, 50, 51], TIMES, audit_fixture())

    def test_hash_mismatch_rejects_audit_for_different_prices(self):
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            audit_prices(RAW + b"changed", [100, 101, 102], TIMES, audit_fixture())

    def test_adjustment_does_not_erase_genuine_crash(self):
        metadata = audit_fixture()
        metadata["large_move_reviews"] = [{"timestamp": TIMES[1].isoformat(),
            "conclusion": "genuine_market_move", "evidence": ["fictional earnings gap corroboration"]}]
        result = audit_prices(RAW, [100, 50, 51], TIMES, metadata)
        self.assertEqual(result["large_moves"][0]["simple_return"], -.5)
        self.assertEqual(result["status"], "FICTIONAL")
        self.assertFalse(result["eligible_for_sizing"])

    def test_declared_adjustment_does_not_excuse_an_unexplained_jump(self):
        metadata = audit_fixture()
        metadata["corporate_actions"]["events"] = [{"type": "split", "effective_at": TIMES[1].isoformat(),
            "resolution": "adjusted_in_series", "evidence": ["fixture split"]}]
        with self.assertRaisesRegex(ValueError, "Unreviewed price jump"):
            audit_prices(RAW, [100, 50, 51], TIMES, metadata)

    def test_unresolved_small_corporate_action_blocks_fit(self):
        metadata = audit_fixture()
        metadata["corporate_actions"]["events"] = [{"type": "spinoff", "effective_at": TIMES[1].isoformat(),
            "resolution": "unresolved", "evidence": ["fictional issuer notice"]}]
        with self.assertRaisesRegex(ValueError, "Unresolved corporate action"):
            audit_prices(RAW, [100, 90, 91], TIMES, metadata)

    def test_in_sample_action_cannot_be_marked_outside_sample(self):
        metadata = audit_fixture()
        metadata["corporate_actions"]["events"] = [{"type": "split", "effective_at": TIMES[1].isoformat(),
            "resolution": "outside_sample", "evidence": ["fictional split"]}]
        with self.assertRaisesRegex(ValueError, "inside the sample"):
            audit_prices(RAW, [100, 101, 102], TIMES, metadata)

    def test_manifest_cannot_change_field_or_annualization(self):
        for kwargs in ({"close_column": "adjusted_close"}, {"periods_per_year": 252 * 78},
                       {"timestamp_column": "time"}):
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(ValueError, "does not match"):
                audit_prices(RAW, [100, 101, 102], TIMES, audit_fixture(), **kwargs)

    def test_partial_window_and_future_observations_blocked(self):
        metadata = audit_fixture()
        metadata["corporate_actions"]["window_end"] = TIMES[1].isoformat()
        with self.assertRaisesRegex(ValueError, "exact sample window"):
            audit_prices(RAW, [100, 101, 102], TIMES, metadata)
        metadata = audit_fixture()
        metadata["retrieved_at"] = TIMES[0].isoformat()
        with self.assertRaisesRegex(ValueError, "precedes"):
            audit_prices(RAW, [100, 101, 102], TIMES, metadata)

    def test_market_declaration_is_explicitly_not_verified_by_helper(self):
        metadata = audit_fixture()
        metadata["data_kind"] = "market"  # Tests the schema branch, not real market data.
        result = audit_prices(RAW, [100, 101, 102], TIMES, metadata)
        self.assertEqual(result["status"], "REVIEWED_DECLARATION")
        self.assertTrue(result["eligible_for_sizing"])
        self.assertIn("not fetched", result["limitations"])

    def test_duplicate_jump_reviews_rejected(self):
        metadata = audit_fixture()
        entry = {"timestamp": TIMES[1].isoformat(), "conclusion": "genuine_market_move", "evidence": ["fixture"]}
        metadata["large_move_reviews"] = [entry, entry]
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            audit_prices(RAW, [100, 50, 51], TIMES, metadata)


def candidate_fixture():
    return {"symbol": "FICTION_A", "checks": {key: {"status": "pass", "reason": "Test-only judgment",
             "evidence": ["offline fixture"]} for key in REQUIRED_CHECKS},
            "event_review": {"status": "clear", "reason": "Fictional calendar review", "evidence": ["offline fixture"]}}


def screen_fixture():
    return {"universe": {"name": "Fictional custom universe", "source": "unit test",
            "as_of": "2026-10-07T16:00:00Z", "symbols": ["FICTION_A", "FICTION_B"],
            "scope_and_filters": "Two artificial securities, no count requirement"},
            "screening": [{"symbol": "FICTION_A", "outcome": "retained", "reason": "fixture",
                           "evidence": ["fixture"]}], "candidates": [candidate_fixture()]}


class ScreeningTests(unittest.TestCase):
    def test_legacy_manifest_does_not_claim_recorded_methodology(self):
        result = review_screen(screen_fixture())
        self.assertEqual(result["methodology"]["status"], "NOT_RECORDED")
        self.assertIsNone(result["methodology"]["spec_sha256"])
        self.assertEqual(result["report"]["kind"], "NOT_RECORDED")

    def test_not_advanced_is_counted_without_inventing_fundamental_failure(self):
        document = screen_fixture()
        document["screening"].append({"symbol": "FICTION_B", "outcome": "not_advanced",
            "reason": "Initial review deferred for deeper work", "evidence": ["fixture"]})
        result = review_screen(document)
        self.assertEqual(result["coverage"]["not_advanced"], 1)
        self.assertEqual(result["coverage"]["excluded"], 0)
        self.assertEqual(result["coverage"]["screened_with_evidence"], 2)
        self.assertEqual(result["coverage"]["candidate_reviews"], 1)
        self.assertTrue(result["coverage"]["all_constituents_screened"])
        self.assertNotIn("Reject", result["status_counts"])

    def test_unexamined_name_cannot_be_not_advanced(self):
        document = screen_fixture()
        document["screening"].append({"symbol": "FICTION_B", "outcome": "not_advanced",
            "reason": "No observations", "evidence": []})
        with self.assertRaisesRegex(ValueError, "need evidence"):
            review_screen(document)

    def test_method_hash_tracks_rules_but_not_dictionary_order(self):
        document = json.loads((ROOT / "examples/fictional-screen.json").read_text(encoding="utf-8"))
        original = review_screen(document)["methodology"]
        self.assertEqual(original["status"], "DECLARED")
        document["run_spec"] = dict(reversed(list(document["run_spec"].items())))
        self.assertEqual(review_screen(document)["methodology"]["spec_sha256"], original["spec_sha256"])
        document["run_spec"]["ranking_policy"] = "Changed research priority; not an investment ranking"
        self.assertNotEqual(review_screen(document)["methodology"]["spec_sha256"], original["spec_sha256"])

    def test_incomplete_or_invalid_method_cannot_claim_declared(self):
        original = json.loads((ROOT / "examples/fictional-screen.json").read_text(encoding="utf-8"))
        for field, value in (("schema_version", 99), ("mandate", " "), ("field_definitions", {}),
                             ("input_snapshot", []), ("changes", "none"),
                             ("defined_at", "2026-10-07T15:00:00")):
            with self.subTest(field=field):
                document = copy.deepcopy(original)
                document["run_spec"][field] = value
                with self.assertRaises(ValueError):
                    review_screen(document)

    def test_eligible_report_rejects_watch_speculative_reject_and_event_block(self):
        for state in ("unresolved", "material_risk", "fail", "event"):
            with self.subTest(state=state):
                document = screen_fixture()
                if state == "event":
                    document["candidates"][0]["event_review"]["status"] = "blocked"
                else:
                    document["candidates"][0]["checks"]["valuation_growth"]["status"] = state
                document["report"] = {"kind": "eligible_comparison", "ranked_symbols": ["FICTION_A"],
                    "selection_rationale": {"FICTION_A": "Test selection"}}
                with self.assertRaisesRegex(ValueError, "Eligible comparison cannot include"):
                    review_screen(document)

    def test_watch_hypotheses_report_retains_watch_without_authority(self):
        document = screen_fixture()
        document["candidates"][0]["checks"]["balance_sheet"]["status"] = "unresolved"
        document["report"] = {"kind": "screened_hypotheses", "ranked_symbols": ["FICTION_A"],
            "selection_rationale": {"FICTION_A": "Priority for balance-sheet research"}}
        result = review_screen(document)
        self.assertEqual(result["candidates"][0]["status"], "Watch")
        self.assertFalse(result["report"]["execution_authorized"])

    def test_rankings_cannot_add_unreviewed_or_duplicate_names(self):
        for symbols in (["FICTION_B"], ["FOREIGN"], ["FICTION_A", "FICTION_A"]):
            document = screen_fixture()
            document["report"] = {"kind": "screened_hypotheses", "ranked_symbols": symbols,
                "selection_rationale": {s: "Test rationale" for s in symbols}}
            with self.subTest(symbols=symbols), self.assertRaises(ValueError):
                review_screen(document)

    def test_rankings_require_specific_rationale_entries(self):
        for rationale in ({}, {"FICTION_A": " "}, {"FICTION_A": "Reason", "FOREIGN": "Extra"}):
            document = screen_fixture()
            document["report"] = {"kind": "screened_hypotheses", "ranked_symbols": ["FICTION_A"],
                "selection_rationale": rationale}
            with self.subTest(rationale=rationale), self.assertRaises(ValueError):
                review_screen(document)

    def test_empty_or_single_eligible_report_has_no_quota_or_authority(self):
        for symbols in ([], ["FICTION_A"]):
            document = screen_fixture()
            document["report"] = {"kind": "eligible_comparison", "ranked_symbols": symbols,
                "selection_rationale": {s: "All fixture checks pass; still not an order" for s in symbols}}
            result = review_screen(document)
            self.assertEqual(result["report"]["ranked_symbols"], symbols)
            self.assertFalse(result["execution_authorized"])

    def test_no_fixed_count_or_execution_permission(self):
        result = review_screen(screen_fixture())
        self.assertEqual(len(result["candidates"]), 1)
        self.assertFalse(result["execution_authorized"])

    def test_missing_rows_prevent_complete_screen_claim(self):
        result = review_screen(screen_fixture())["coverage"]
        self.assertEqual(result["absent_symbols"], ["FICTION_B"])
        self.assertFalse(result["all_constituents_screened"])

    def test_full_retrieval_with_missing_data_is_not_complete_analysis(self):
        document = screen_fixture()
        document["screening"].append({"symbol": "FICTION_B", "outcome": "missing_data", "reason": "Unavailable"})
        result = review_screen(document)["coverage"]
        self.assertEqual(result["retrieved_rows"], 2)
        self.assertFalse(result["all_constituents_screened"])

    def test_full_screen_does_not_mean_all_retained_reviewed(self):
        document = screen_fixture()
        document["screening"].append({"symbol": "FICTION_B", "outcome": "retained", "reason": "fixture", "evidence": ["fixture"]})
        result = review_screen(document)["coverage"]
        self.assertTrue(result["all_constituents_screened"])
        self.assertEqual(result["retained_without_review"], ["FICTION_B"])

    def test_duplicate_or_foreign_security_is_not_extra_coverage(self):
        for symbol in ("FICTION_A", "NOT_IN_UNIVERSE"):
            document = screen_fixture()
            row = copy.deepcopy(document["screening"][0])
            row["symbol"] = symbol
            document["screening"].append(row)
            with self.assertRaisesRegex(ValueError, "Duplicate or out-of-universe"):
                review_screen(document)

    def test_no_candidates_is_valid(self):
        document = screen_fixture()
        document["candidates"] = []
        self.assertFalse(review_screen(document)["candidates"])

    def test_reject_is_not_hidden_by_event(self):
        candidate = candidate_fixture()
        candidate["checks"]["balance_sheet"]["status"] = "fail"
        candidate["event_review"]["status"] = "blocked"
        result = assess_candidate(candidate)
        self.assertEqual(result["status"], "Reject")
        self.assertEqual(result["event_status"], "blocked")

    def test_speculative_is_not_eligible_even_if_other_checks_pass(self):
        candidate = candidate_fixture()
        candidate["checks"]["cycle_normalization"]["status"] = "material_risk"
        self.assertEqual(assess_candidate(candidate)["status"], "Speculative")

    def test_missing_filing_evidence_cannot_pass(self):
        candidate = candidate_fixture()
        candidate["checks"]["earnings_quality"]["evidence"] = []
        self.assertEqual(assess_candidate(candidate)["status"], "Watch")

    def test_missing_event_review_is_unknown_not_clear(self):
        candidate = candidate_fixture()
        del candidate["event_review"]
        result = assess_candidate(candidate)
        self.assertEqual(result["status"], "Watch")
        self.assertEqual(result["event_status"], "unknown")

    def test_event_blocked_retains_eligible_fundamentals(self):
        candidate = candidate_fixture()
        candidate["event_review"]["status"] = "blocked"
        result = assess_candidate(candidate)
        self.assertEqual(result["status"], "Event-blocked")
        self.assertEqual(result["fundamental_status"], "Eligible")

    def test_garch_regime_cannot_make_or_break_fundamental_eligibility(self):
        for regime in ("NORMAL", "EXTREME", "FAILED", None):
            candidate = candidate_fixture()
            candidate["garch_regime"] = regime
            self.assertEqual(assess_candidate(candidate)["status"], "Eligible")


if __name__ == "__main__":
    unittest.main()
