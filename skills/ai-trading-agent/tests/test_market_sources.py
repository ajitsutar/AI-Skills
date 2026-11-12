import copy
import hashlib
from http.client import IncompleteRead
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import market_sources as ms

NOW = "2026-11-11T21:00:00Z"
SOURCE = {"id": "fictional-official-snapshot", "url": "https://www.finra.org/example",
          "retrieved_at": "2026-11-11T20:00:00Z", "published_at": None,
          "observed_at": "2026-11-11T20:00:00Z", "availability_basis": "first_observed_snapshot",
          "access": "public", "rights": "unknown"}
VOLUME = ("Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market\n"
          "20261110|DEMO|20.125|3|50.5|B,Q,N\n1\n")
URL = "https://cdn.finra.org/equity/regsho/daily/CNMSshvol20261110.txt"


def record(identity="r1", **extra):
    result = {"id": identity, "kind": "trade", "ticker": "DEMO",
              "available_at": "2026-11-11T20:00:00Z", "source": copy.deepcopy(SOURCE),
              "payload": {"quantity": 10, "price": 20, "unknown_field": {"retained": True}}}
    result.update(extra)
    return result


def doc(*records):
    return {"schema_version": 1, "as_of": NOW, "records": list(records)}


def parse_doc(adapter, text="", **extra):
    result = {"schema_version": 1, "as_of": NOW, "adapter": adapter,
              "source": copy.deepcopy(SOURCE), "text": text}
    result.update(extra)
    return result


class EligibilityTests(unittest.TestCase):
    def test_preserves_unknown_fields_and_does_not_mutate_input(self):
        original = doc(record())
        frozen = copy.deepcopy(original)
        result = ms.normalize(original)
        self.assertEqual(original, frozen)
        self.assertTrue(result["records"][0]["eligible"])
        self.assertEqual(result["records"][0]["payload"], original["records"][0]["payload"])
        self.assertFalse(result["execution_authorized"])
        self.assertEqual(result["kind"], "MARKET_EVIDENCE")

    def test_availability_unknown_date_only_and_future_are_not_usable(self):
        for value in (None, "2026-11-11", "2026-11-11T20:00:00", "2026-11-11T22:00:00Z"):
            with self.subTest(value=value):
                row = ms.normalize(doc(record(available_at=value)))["records"][0]
                self.assertFalse(row["eligible"])
        with self.assertRaises(ValueError):
            ms.normalize({"schema_version": True, "as_of": NOW, "records": []})

    def test_snapshot_cannot_be_backdated_or_source_observed_in_future(self):
        first = record(available_at="2026-11-10T20:00:00Z")
        self.assertIn("AVAILABILITY_BEFORE_SNAPSHOT", ms.normalize(doc(first))["records"][0]["exclusion_reasons"])
        second = record()
        second["source"]["observed_at"] = "2026-11-12T20:00:00Z"
        self.assertFalse(ms.normalize(doc(second))["records"][0]["eligible"])

    def test_duplicate_ids_exclude_all_instead_of_picking_first(self):
        result = ms.normalize(doc(record(), record()))
        self.assertTrue(all(not row["eligible"] for row in result["records"]))
        self.assertEqual(result["issues"][0]["code"], "DUPLICATE_RECORD_ID")

    def test_available_replace_and_cancel_are_clock_scoped(self):
        replacement = record("r2", available_at="2026-11-11T20:30:00Z", action="replace", supersedes="r1")
        rows = ms.normalize(doc(record(), replacement))["records"]
        self.assertFalse(rows[0]["eligible"])
        self.assertTrue(rows[1]["eligible"])
        replacement["action"] = "cancel"
        rows = ms.normalize(doc(record(), replacement))["records"]
        self.assertFalse(any(row["eligible"] for row in rows))
        replacement["available_at"] = "2026-11-11T22:30:00Z"
        rows = ms.normalize(doc(record(), replacement))["records"]
        self.assertTrue(rows[0]["eligible"])
        self.assertFalse(rows[1]["eligible"])

    def test_wrong_scope_or_ambiguous_order_cannot_supersede_original(self):
        base = record()
        for field, value in (("ticker", "OTHER"), ("kind", "bar")):
            replacement = record("r2", available_at="2026-11-11T20:30:00Z", action="replace", supersedes="r1")
            replacement[field] = value
            rows = ms.normalize(doc(base, replacement))["records"]
            self.assertTrue(rows[0]["eligible"])
            self.assertIn("REVISION_SCOPE_MISMATCH", rows[1]["exclusion_reasons"])
        replacement["ticker"] = "DEMO"
        replacement["kind"] = "trade"
        replacement["source"]["id"] = "different-feed"
        self.assertFalse(ms.normalize(doc(base, replacement))["records"][1]["eligible"])
        replacement["source"] = copy.deepcopy(SOURCE)
        replacement["available_at"] = base["available_at"]
        self.assertTrue(ms.normalize(doc(base, replacement))["records"][0]["eligible"])
        replacement["supersedes"] = "absent"
        self.assertFalse(ms.normalize(doc(base, replacement))["records"][1]["eligible"])

    def test_source_validation_does_not_raise_for_malformed_record_metadata(self):
        row = record(kind={}, source={"id": "bad", "url": "https://user:secret@example.com"})
        result = ms.normalize(doc(row))
        self.assertFalse(result["records"][0]["eligible"])
        self.assertIn("SOURCE_URL_INVALID", result["records"][0]["exclusion_reasons"])

    def test_trade_and_bar_revisions_preserve_declared_measurement_identity(self):
        for kind, field in (("trade", "feed_id"), ("trade", "trade_id"), ("trade", "currency"),
                            ("trade", "quantity_unit"), ("trade", "issuer_id"), ("trade", "share_class"),
                            ("bar", "session_id"), ("bar", "end_at"), ("bar", "price_basis")):
            with self.subTest(kind=kind, field=field):
                original = record(kind=kind)
                original["payload"][field] = "original"
                revised = record("r2", kind=kind, available_at="2026-11-11T20:30:00Z",
                                 action="replace", supersedes="r1")
                revised["payload"][field] = "different"
                rows = ms.normalize(doc(original, revised))["records"]
                self.assertTrue(rows[0]["eligible"])
                self.assertFalse(rows[1]["eligible"])
                del revised["payload"][field]
                self.assertTrue(ms.normalize(doc(original, revised))["records"][0]["eligible"])


class ParsingTests(unittest.TestCase):
    def test_current_finra_fractional_shares_and_exempt_subset_are_preserved(self):
        result = ms.parse(parse_doc("finra_short_volume", VOLUME))
        row = result["records"][0]
        self.assertTrue(row["eligible"])
        self.assertEqual(row["payload"]["short_volume"], 20.125)
        self.assertEqual(row["payload"]["short_exempt_volume"], 3)
        self.assertTrue(row["payload"]["short_volume_includes_exempt"])
        self.assertEqual(row["payload"]["raw_fields"]["ShortVolume"], "20.125")
        self.assertEqual(row["payload"]["trade_date"], "2026-11-10")
        self.assertEqual(row["available_at"], SOURCE["retrieved_at"])

    def test_default_ids_are_stable_within_capture_and_distinguish_vintages(self):
        original = parse_doc("finra_short_volume", VOLUME)
        saved = copy.deepcopy(original)
        first = ms.parse(original)["records"][0]["id"]
        self.assertEqual(first, ms.parse(original)["records"][0]["id"])
        later = copy.deepcopy(original)
        later["source"]["retrieved_at"] = "2026-11-11T20:30:00Z"
        self.assertNotEqual(first, ms.parse(later)["records"][0]["id"])
        self.assertEqual(original, saved)

    def test_trailer_missing_or_wrong_and_malformed_rows_are_retained_as_excluded(self):
        for text in (VOLUME.replace("\n1\n", "\n2\n"), VOLUME.removesuffix("1\n"),
                     VOLUME.replace("20.125", "nan"), VOLUME.replace("20.125", "-1")):
            result = ms.parse(parse_doc("finra_short_volume", text))
            self.assertFalse(result["records"][0]["eligible"])
            self.assertIn("raw_fields", result["records"][0]["payload"])
        self.assertEqual(ms.parse(parse_doc("finra_short_volume", VOLUME.splitlines()[0] + "\n0\n"))["records"], [])

    def test_identical_literal_headers_are_rejected_before_dictreader_data_loss(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            ms.parse(parse_doc("finra_short_interest_csv",
                              "Settlement Date,Symbol,Current Short,Current Short\n2026-10-30,DEMO,1200,1300\n"))

    def test_conflicting_supported_aliases_retain_the_row_as_unusable(self):
        for header, values in [
            ("Current Short,Short Interest", "1200,1800"),
            ("Short Interest,Current Short", "1800,1200"),
            ("Current Short,Current-Short", "1200,1800"),
            ("Current Short,Short Interest", "1200,1200.00000000000000001"),
            ("Current Short,Days to Cover,daysToCoverQuantity", "1200,2.4,3"),
            ("Current Short,Avg Daily Volume,averageDailyVolumeQuantity", "1200,500,N/A"),
        ]:
            with self.subTest(header=header, values=values):
                text = "Settlement Date,Symbol," + header + "\n2026-10-30,DEMO," + values + "\n"
                source = parse_doc("finra_short_interest_csv", text)
                before = copy.deepcopy(source)
                result = ms.parse(source)
                row = result["records"][0]
                self.assertFalse(row["eligible"])
                self.assertIn("PARSE_ERROR", row["exclusion_reasons"])
                self.assertIn("Conflicting source field aliases", row["parse_error"])
                self.assertNotIn("short_interest_shares", row["payload"])
                self.assertEqual(len(row["payload"]["raw_fields"]), len(header.split(",")) + 2)
                self.assertTrue(any(issue["code"] == "ROW_PARSE_ERROR" for issue in result["issues"]))
                self.assertEqual(source, before)

    def test_conflicting_symbol_and_normalized_date_aliases_are_not_selected(self):
        for text in [
            "Settlement Date,Symbol,Issue Symbol,Current Short\n2026-10-30,DEMO,OTHER,1200\n",
            "Settlement Date,settlementDate,Symbol,Current Short\n2026-10-30,2026-11-10,DEMO,1200\n",
        ]:
            row = ms.parse(parse_doc("finra_short_interest_csv", text))["records"][0]
            self.assertFalse(row["eligible"])
            self.assertIn("Conflicting source field aliases", row["parse_error"])
            self.assertEqual(len(row["payload"]["raw_fields"]), 4)

    def test_equal_redundant_aliases_use_exact_numeric_and_date_meaning(self):
        text = ("Settlement Date,settlementDate,Symbol,Issue Symbol,Current Short,Current-Short,Short Interest,"
                "Avg Daily Volume,averageDailyVolumeQuantity,Days to Cover,daysToCoverQuantity\n"
                '20261030,2026-10-30,DEMO,DEMO,"1,200",1200.00,1200,500,500.0,2.40,2.4\n')
        result = ms.parse(parse_doc("finra_short_interest_csv", text))
        row = result["records"][0]
        self.assertTrue(row["eligible"])
        self.assertEqual(row["ticker"], "DEMO")
        self.assertEqual(row["payload"]["settlement_date"], "2026-10-30")
        self.assertEqual(row["payload"]["short_interest_shares"], 1200)
        self.assertEqual(row["payload"]["average_daily_volume"], 500)
        self.assertEqual(row["payload"]["reported_days_to_cover"], 2.4)
        self.assertEqual(row["payload"]["raw_fields"]["Current Short"], "1,200")
        self.assertEqual(row["payload"]["raw_fields"]["Current-Short"], "1200.00")
        self.assertEqual(result["issues"], [])

    def test_optional_redundant_unknowns_remain_unknown(self):
        text = ("Settlement Date,Symbol,Current Short,Days to Cover,daysToCoverQuantity\n"
                "2026-10-30,DEMO,1200,N/A,.\n")
        row = ms.parse(parse_doc("finra_short_interest_csv", text))["records"][0]
        self.assertTrue(row["eligible"])
        self.assertIsNone(row["payload"]["reported_days_to_cover"])

    def test_finra_volume_normalized_aliases_require_equal_values(self):
        for second, eligible in [("20.1250", True), ("21", False)]:
            text = ("Date|Symbol|ShortVolume|Short Volume|ShortExemptVolume|TotalVolume|Market\n"
                    "20261110|DEMO|20.125|" + second + "|3|50.5|B,Q,N\n1\n")
            result = ms.parse(parse_doc("finra_short_volume", text))
            row = result["records"][0]
            self.assertEqual(row["eligible"], eligible)
            self.assertEqual(row["payload"]["raw_fields"]["Short Volume"], second)
            if eligible:
                self.assertEqual(row["payload"]["short_volume"], 20.125)
            else:
                self.assertIn("Conflicting source field aliases", row["parse_error"])

    def test_official_short_interest_is_a_separate_dated_measure(self):
        text = "Settlement Date,Symbol,Current Short,Avg Daily Volume,Days to Cover,Issue Name\n2026-10-30,DEMO,1200,500,2.40,Demo Inc\n"
        result = ms.parse(parse_doc("finra_short_interest_csv", text))
        row = result["records"][0]
        self.assertEqual(row["kind"], "short_interest")
        self.assertEqual(row["payload"]["short_interest_shares"], 1200)
        self.assertEqual(row["payload"]["reported_days_to_cover"], 2.4)
        self.assertNotIn("float_shares", row["payload"])
        self.assertEqual(row["available_at"], SOURCE["retrieved_at"])

    def test_cboe_cycle_export_preserves_dated_current_shares_and_reported_fields(self):
        text = ('Cycle Settlement Date,BATS-Symbol,Security Name,# Shares Net Short Current Cycle,'
                '# Shares Net Short Previous Cycle,Cycle Avg Daily Trade Vol,Min # of Trade Days To Cover Shorts,'
                'Split Indicator ("S" or null),Manual Revision Indicator ("R" or null),'
                'Percent Change in Short Position,Change in Short Position From Previous\n'
                '20261030,DEMO,Fictional Company,1200,1500,500,3,S,R,-20,-300\n')
        result = ms.parse(parse_doc("finra_short_interest_csv", text))
        row = result["records"][0]; payload = row["payload"]
        self.assertTrue(row["eligible"])
        self.assertEqual(row["ticker"], "DEMO")
        self.assertEqual(payload["settlement_date"], "2026-10-30")
        self.assertEqual(payload["short_interest_shares"], 1200)
        self.assertEqual(payload["average_daily_volume"], 500)
        # Preserve the reported minimum display instead of recomputing 1200/500.
        self.assertEqual(payload["reported_days_to_cover"], 3)
        self.assertEqual(payload["reported_days_to_cover_semantics"], "source_reported_minimum_trade_days_to_cover")
        self.assertEqual(payload["average_daily_volume_semantics"], "source_reported_cycle_average_daily_trade_volume")
        self.assertEqual(payload["security_name"], "Fictional Company")
        self.assertEqual(payload["raw_fields"]["# Shares Net Short Previous Cycle"], "1500")
        self.assertEqual(payload["raw_fields"]['Split Indicator ("S" or null)'], "S")
        self.assertEqual(payload["raw_fields"]['Manual Revision Indicator ("R" or null)'], "R")
        self.assertEqual(payload["raw_fields"]["Change in Short Position From Previous"], "-300")
        self.assertEqual(len(payload["raw_fields"]), 11)
        self.assertEqual(row["available_at"], SOURCE["retrieved_at"])
        self.assertIsNone(row["source"]["published_at"])
        for field in ('adjustment_basis', 'float_shares', 'adv_window', 'issuer_id', 'share_class'):
            self.assertNotIn(field, payload)
        self.assertEqual(result["issues"], [])

    def test_cboe_alias_cannot_silently_override_a_conflicting_finra_field(self):
        for header, values in [
            ("Current Short,# Shares Net Short Current Cycle", "1200,1500"),
            ("Current Short,Days to Cover,Min # of Trade Days To Cover Shorts", "1200,2.4,3"),
        ]:
            text = "Cycle Settlement Date,BATS-Symbol," + header + "\n20261030,DEMO," + values + "\n"
            row = ms.parse(parse_doc("finra_short_interest_csv", text))["records"][0]
            self.assertFalse(row["eligible"])
            self.assertIn("Conflicting source field aliases", row["parse_error"])
            self.assertIn("raw_fields", row["payload"])

    def test_ftd_balance_and_unknown_price_are_never_daily_new_fails(self):
        text = "SETTLEMENT DATE|CUSIP|SYMBOL|QUANTITY (FAILS)|DESCRIPTION|PRICE\n20261015|012345678|DEMO|100|Demo Inc|.\n"
        row = ms.parse(parse_doc("sec_ftd", text))["records"][0]
        self.assertEqual(row["payload"]["quantity"], 100)
        self.assertIsNone(row["payload"]["price"])
        self.assertEqual(row["payload"]["balance_semantics"], "aggregate_outstanding_fails")

    def test_sec_submissions_handles_forms_and_does_not_use_acceptance_as_availability(self):
        recent = {"accessionNumber": ["0000000001-26-000001", "0000000001-26-000002"],
                  "form": ["SC 13D", "13F-HR"], "filingDate": ["2026-10-01", "2026-11-10"],
                  "reportDate": ["2026-09-30", "2026-09-30"],
                  "acceptanceDateTime": ["2026-10-01T12:00:00Z", "2026-11-10T12:00:00Z"],
                  "primaryDocument": ["report.xml", "primary_doc.xml"]}
        data = {"cik": "0000000001", "tickers": ["FILER"], "filings": {"recent": recent, "files": [{"name": "older.json"}]}}
        result = ms.parse(parse_doc("sec_submissions", data=data))
        self.assertEqual(result["records"][0]["available_at"], SOURCE["retrieved_at"])
        self.assertIsNone(result["records"][0]["ticker"])
        self.assertIn("/1/000000000126000001/report.xml", result["records"][0]["payload"]["primary_document_url"])
        self.assertFalse(result["adapter_metadata"]["history_complete"])
        recent["form"].pop()
        with self.assertRaisesRegex(ValueError, "column lengths"):
            ms.parse(parse_doc("sec_submissions", data=data))

    def test_form4_keeps_disposal_and_footnotes_without_calling_them_short_sales(self):
        text = """<ownershipDocument><documentType>4</documentType><issuer><issuerTradingSymbol>DEMO</issuerTradingSymbol></issuer>
        <nonDerivativeTable><nonDerivativeTransaction><securityTitle><value>Common</value></securityTitle>
        <transactionDate><value>2026-11-09</value></transactionDate><transactionCoding><transactionCode>F</transactionCode></transactionCoding>
        <transactionAmounts><transactionShares><value>25</value></transactionShares><transactionPricePerShare><value>10</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode></transactionAmounts></nonDerivativeTransaction></nonDerivativeTable>
        <footnotes><footnote id="F1">Fictional tax withholding.</footnote></footnotes></ownershipDocument>"""
        result = ms.parse(parse_doc("sec_form4_xml", text))
        payload = result["records"][0]["payload"]
        self.assertEqual(payload["transaction_code"], "F")
        self.assertEqual(payload["acquired_disposed_code"], "D")
        self.assertNotIn("short_position", payload)
        self.assertTrue(result["adapter_metadata"]["footnotes"])
        with self.assertRaisesRegex(ValueError, "DTD"):
            ms.parse(parse_doc("sec_form4_xml", '<!DOCTYPE a [<!ENTITY x "x">]><ownershipDocument/>'))

    def test_13f_namespace_units_and_put_do_not_become_a_short_position(self):
        text = """<informationTable xmlns="urn:sec"><infoTable><nameOfIssuer>Demo</nameOfIssuer><titleOfClass>COM</titleOfClass>
        <cusip>012345678</cusip><value>1234</value><shrsOrPrnAmt><sshPrnamt>40</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
        <putCall>Put</putCall></infoTable></informationTable>"""
        row = ms.parse(parse_doc("sec_13f_xml", text, ticker="WRONG"))["records"][0]
        self.assertIsNone(row["ticker"])
        self.assertEqual(row["payload"]["value_unit"], "unknown")
        self.assertEqual(row["payload"]["put_call"], "Put")
        self.assertNotIn("short_interest_shares", row["payload"])
        self.assertEqual(ms.parse(parse_doc("sec_13f_xml", text, value_unit="USD_thousands"))["records"][0]["payload"]["reported_value"], 1234)

    def test_venue_export_requires_explicit_mapping_and_stays_an_aggregate(self):
        text = "Symbol,Week,Venue,Qty,Count\nDEMO,2026-10-19,Venue A,500,3\n"
        row = ms.parse(parse_doc("venue_csv", text, columns={"week_start": "Week", "venue": "Venue", "shares": "Qty", "trades": "Count"}))["records"][0]
        self.assertEqual(row["kind"], "venue_aggregate")
        self.assertEqual(row["payload"]["shares"], 500)
        self.assertNotIn("buyer", row["payload"])
        self.assertFalse(ms.parse(parse_doc("venue_csv", text))["records"][0]["eligible"])

    def test_social_input_is_canonical_lead_only_and_not_primary_verification(self):
        result = ms.parse(parse_doc("social_leads", data=[{
            "url": "https://twitter.com/demo/status/123?ref=old", "author": "demo",
            "posted_date": "2026-11-10", "text": "Fictional claim", "primary_verified": True}]))
        row = result["records"][0]
        self.assertEqual(row["payload"]["canonical_url"], "https://x.com/demo/status/123")
        self.assertTrue(row["payload"]["requires_primary_verification"])
        self.assertFalse(row["payload"]["primary_verified"])
        self.assertTrue(row["payload"]["declared_primary_verified"])
        self.assertTrue(row["payload"]["raw_fields"]["primary_verified"])
        self.assertEqual(row["payload"]["primary_verification_status"], "NOT_ESTABLISHED_BY_SOCIAL_PARSER")
        self.assertEqual(row["payload"]["use"], "lead_only")
        self.assertEqual(row["payload"]["posted_date"], "2026-11-10")

    def test_parsing_and_normalization_never_open_files_or_network(self):
        with patch.object(ms, "build_opener", side_effect=AssertionError("network")), patch("builtins.open", side_effect=AssertionError("filesystem")):
            self.assertTrue(ms.parse(parse_doc("finra_short_volume", VOLUME))["records"][0]["eligible"])
            self.assertTrue(ms.normalize(doc(record()))["records"][0]["eligible"])


class Response(io.BytesIO):
    def __init__(self, body, status=200, headers=None, url=URL):
        super().__init__(body)
        self.status = self.code = status
        self.headers = headers or {}
        self.url = url

    def geturl(self):
        return self.url


class AcquisitionTests(unittest.TestCase):
    def test_url_allowlist_rejects_credentials_queries_ports_and_official_lookalikes(self):
        for url in ("http://cdn.finra.org/equity/regsho/daily/CNMSshvol20261110.txt",
                    URL + "?secret=x", URL.replace("cdn.finra.org", "cdn.finra.org.evil.example"),
                    URL.replace("https://", "https://u:p@"), URL.replace("cdn.finra.org", "cdn.finra.org:444"),
                    "https://www.sec.gov/private/path"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                ms.allowed_public_url(url)
        self.assertEqual(ms.allowed_public_url(URL), "cdn.finra.org")

    def capture(self, responses, root, **kwargs):
        with patch.object(ms, "build_opener") as builder, patch.object(ms.time, "sleep"):
            builder.return_value.open.side_effect = responses
            result = ms.acquire(URL, Path(root) / "capture", "fixture-finra", "FictionalResearch tester@example.invalid", **kwargs)
            return result, builder.return_value.open.call_count

    def test_capture_retains_exact_bytes_hash_headers_and_snapshot_clock(self):
        body = VOLUME.encode()
        with tempfile.TemporaryDirectory() as root:
            result, calls = self.capture([Response(body, headers={"ETag": '"rev-1"', "Content-Length": str(len(body))})], root)
            self.assertEqual(result["status"], "ACQUIRED")
            self.assertEqual(calls, 1)
            self.assertEqual(result["raw_sha256"], hashlib.sha256(body).hexdigest())
            self.assertEqual((Path(root) / "capture" / result["raw_file"]).read_bytes(), body)
            self.assertEqual(result["available_at"], result["source"]["retrieved_at"])
            self.assertIsNone(result["source"]["published_at"])
            self.assertEqual(result["source"]["response_headers"]["ETag"], '"rev-1"')
            self.assertTrue(result["attempts"][0]["raw_complete"])
            self.assertFalse(result["execution_authorized"])

    def test_denial_and_rate_limit_are_retained_without_retries_or_bypass(self):
        for status in (403, 404, 429):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as root:
                result, calls = self.capture([Response(b"denied", status)], root)
                self.assertEqual(result["status"], "FAILED")
                self.assertEqual(calls, 1)
                self.assertEqual(result["attempts"][0]["http_status"], status)
                self.assertTrue((Path(root) / "capture" / "manifest.json").exists())
                self.assertNotIn("source", result)

    def test_transient_retry_keeps_both_versions_and_is_bounded(self):
        with tempfile.TemporaryDirectory() as root:
            result, calls = self.capture([Response(b"temporary", 503), Response(b"new")], root)
            self.assertEqual(calls, 2)
            self.assertEqual(len(result["attempts"]), 2)
            self.assertIn("HTTP_503", result["attempts"][0]["error"])
            self.assertEqual(result["status"], "ACQUIRED")
            self.assertNotEqual(result["attempts"][0]["raw_sha256"], result["raw_sha256"])

    def test_oversize_and_short_body_are_not_labeled_complete(self):
        for response, limit in ((Response(b"12345"), 4),
                                (Response(b"12", headers={"Content-Length": "8"}), 8)):
            with tempfile.TemporaryDirectory() as root:
                result, _ = self.capture([response], root, max_bytes=limit, retries=0)
                self.assertEqual(result["status"], "FAILED")
                self.assertFalse(result["attempts"][0]["raw_complete"])
                self.assertLessEqual(result["attempts"][0]["retained_bytes"], limit)

    def test_transport_failure_retains_returned_prefix_and_error(self):
        class Broken(Response):
            def read(self, size=-1):
                if self.tell() > 0:
                    raise IncompleteRead(b"unknown-final-fragment", 10)
                return super().read(min(2, size))
        with tempfile.TemporaryDirectory() as root:
            result, _ = self.capture([Broken(b"prefix")], root, retries=0)
            entry = result["attempts"][0]
            self.assertEqual(result["status"], "FAILED")
            self.assertEqual(entry["retained_bytes"], 2)
            self.assertEqual(entry["raw_sha256"], hashlib.sha256(b"pr").hexdigest())
            self.assertIn("IncompleteRead", entry["error"])
            self.assertFalse(entry["raw_complete"])

    def test_redirect_handler_refuses_before_following(self):
        with self.assertRaises(HTTPError):
            ms._NoRedirect().redirect_request(type("Req", (), {"full_url": URL})(), None, 302, "redirect", {}, "https://evil.example/")
        with tempfile.TemporaryDirectory() as root:
            result, _ = self.capture([Response(b"unexpected", url="https://evil.example/")], root)
            self.assertEqual(result["status"], "FAILED")
            self.assertIn("UNEXPECTED_REDIRECT", result["attempts"][0]["error"])

    def test_existing_output_and_invalid_bounds_fail_before_network(self):
        with tempfile.TemporaryDirectory() as root, patch.object(ms, "build_opener") as builder:
            with self.assertRaises(FileExistsError):
                ms.acquire(URL, root, "x", "Research test@example.invalid")
            for values in ({"retries": True}, {"max_bytes": True}, {"timeout": float("nan")}, {"user_agent": "anonymous"}):
                arguments = dict(url=URL, output_dir=Path(root) / "unused", source_id="x", user_agent="Research test@example.invalid")
                arguments.update(values)
                with self.assertRaises(ValueError):
                    ms.acquire(**arguments)
            builder.assert_not_called()

    def test_zip_requires_explicit_safe_single_member_and_retains_two_hashes(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "data.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("ftd.txt", "header\nrow\n")
            with self.assertRaises(ValueError):
                ms.raw_text(path)
            text, raw_hash, content_hash = ms.raw_text(path, "ftd.txt")
            self.assertEqual(text, "header\nrow\n")
            self.assertEqual(raw_hash, hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(content_hash, hashlib.sha256(text.encode()).hexdigest())
            with self.assertRaises(ValueError):
                ms.raw_text(path, "../other")


if __name__ == "__main__":
    unittest.main()
