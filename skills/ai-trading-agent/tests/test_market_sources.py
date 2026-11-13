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


class SecDailyIndexTests(unittest.TestCase):
    URL = "https://www.sec.gov/Archives/edgar/daily-index/2026/QTR4/master.20261112.idx"
    PREFIX = ("Description:           Master Index of EDGAR Dissemination Feed\n"
              "Last Data Received:    November 12, 2026\nComments:              webmaster@sec.gov\n\n"
              "CIK|Company Name|Form Type|Date Filed|Filename\n"
              "--------------------------------------------------------------------------------\n")
    ROWS = ["42|Fictional Alpha|8-K|2026-11-12|edgar/data/42/0000009999-26-000001.txt",
            "84|Fictional Beta|4|2026-11-12|edgar/data/84/0000009999-26-000002.txt",
            "126|Fictional Fund|NPORT-P|2026-11-12|edgar/data/126/0000009999-26-000003.txt"]

    def document(self, text=None, mapped=True):
        source = {"id": "fictional-whole-index", "url": self.URL,
                  "retrieved_at": "2026-11-13T09:00:00Z", "observed_at": "2026-11-13T09:00:00Z",
                  "published_at": None, "availability_basis": "first_observed_snapshot",
                  "access": "public", "rights": "synthetic_fixture_only"}
        document = {"schema_version": 1, "as_of": "2026-11-13T11:00:00Z", "adapter": "sec_daily_index",
                    "source": source, "text": self.PREFIX + "\n".join(self.ROWS) + "\n" if text is None else text}
        if mapped:
            provenance = copy.deepcopy(source)
            provenance.update(id="fictional-identity-map", url="https://example.org/retained-cik-symbol-map",
                              retrieved_at="2026-11-12T20:00:00Z", observed_at="2026-11-12T20:00:00Z")
            document["cik_symbol_mapping"] = {str(cik).zfill(10): {
                "ticker": ticker, "available_at": "2026-11-12T20:00:00Z", "source": copy.deepcopy(provenance),
                "identity_note": "Fictional caller-supplied mapping; no listing certification"}
                for cik, ticker in [(42, "ALPHA"), (84, "BETA"), (126, "FUND")]}
        return document

    def observed_format_document(self):
        document = self.document()
        document["text"] = (document["text"].replace("Master Index", "Daily Index")
                            .replace("November 12, 2026", "Nov 12, 2026")
                            .replace("Date Filed|Filename", "Date Filed|File Name")
                            .replace("|2026-11-12|", "|20261112|"))
        return document

    def test_observed_daily_index_schema_preserves_normalized_fields_and_original_headers(self):
        document = self.observed_format_document(); before = copy.deepcopy(document)
        result = ms.parse(document); original = ms.parse(self.document())
        self.assertEqual(document, before)
        self.assertTrue(all(row["eligible"] for row in result["records"]))
        self.assertEqual(result["adapter_metadata"]["source_headers"][-1], "File Name")
        self.assertEqual(result["adapter_metadata"]["received_date_raw"], "Nov 12, 2026")
        self.assertEqual(result["adapter_metadata"]["source_data_rows"], 3)
        for row, prior in zip(result["records"], original["records"]):
            for field in ("filer_cik", "filer_name", "form", "filing_date", "filename", "accession_number",
                          "source_filename_url", "filing_document_url"):
                self.assertEqual(row["payload"][field], prior["payload"][field])
            self.assertEqual(row["payload"]["raw_fields"][3], "20261112")
            self.assertIn("|20261112|", row["payload"]["raw_line"])

    def test_supported_daily_schema_variants_combine_without_erasing_prior_format(self):
        for daily in (False, True):
            for short_month in (False, True):
                for spaced_header in (False, True):
                    for basic_date in (False, True):
                        document = self.document()
                        for enabled, before, after in [(daily, "Master Index", "Daily Index"),
                                (short_month, "November 12, 2026", "Nov 12, 2026"),
                                (spaced_header, "Date Filed|Filename", "Date Filed|File Name"),
                                (basic_date, "|2026-11-12|", "|20261112|")]:
                            if enabled:
                                document["text"] = document["text"].replace(before, after)
                        with self.subTest(daily=daily, short_month=short_month, spaced_header=spaced_header, basic_date=basic_date):
                            result = ms.parse(document)
                            self.assertEqual(result["adapter_metadata"]["parsed_rows"], 3)
                            self.assertEqual(result["adapter_metadata"]["eligible_rows_at_cutoff"], 3)
                            self.assertTrue(all(r["payload"]["filing_date"] == "2026-11-12" for r in result["records"]))

    def test_daily_schema_rejects_unrecognized_description_header_and_received_dates(self):
        for before, after in [("Daily Index", "Company Index"), ("Daily Index", "Not Daily Index"),
                              ("Date Filed|File Name", "Date Filed|FileName"),
                              ("Nov 12, 2026", "Nov. 12, 2026"), ("Nov 12, 2026", "11/12/2026")]:
            document = self.observed_format_document()
            document["text"] = document["text"].replace(before, after)
            with self.subTest(after=after), self.assertRaises(ValueError):
                ms.parse(document)
        document = self.observed_format_document()
        document["text"] += "CIK|Company Name|Form Type|Date Filed|Filename\n"
        with self.assertRaisesRegex(ValueError, "header missing or duplicated"):
            ms.parse(document)

    def test_compact_filing_dates_still_require_valid_calendar_and_index_order(self):
        for date in ["20261131", "20261113", "202611122", "2026/11/12"]:
            document = self.observed_format_document()
            document["text"] = document["text"].replace("|20261112|", "|" + date + "|", 1)
            result = ms.parse(document)
            self.assertFalse(result["records"][0]["eligible"])
            self.assertTrue(result["records"][1]["eligible"])
            self.assertEqual(result["records"][0]["payload"]["raw_fields"][3], date)
            self.assertEqual(result["adapter_metadata"]["malformed_rows"], 1)
            self.assertEqual(len(result["adapter_metadata"]["source_row_queue"]), 3)

    def test_complete_transport_allows_complete_no_newline_index_with_explicit_qualification(self):
        for location in ("top", "source", "both"):
            document = self.observed_format_document(); document["text"] = document["text"].rstrip("\n")
            if location in ("top", "both"):
                document["raw_complete"] = True
            if location in ("source", "both"):
                document["source"]["raw_complete"] = True
            result = ms.parse(document); metadata = result["adapter_metadata"]
            self.assertTrue(all(row["eligible"] for row in result["records"]))
            self.assertFalse(metadata["terminal_newline_present"])
            self.assertEqual(metadata["terminal_newline_qualification"], "ABSENT_WITH_COMPLETE_TRANSPORT_DECLARATION")
            self.assertEqual(len(metadata["source_row_queue"]), 3)
            self.assertTrue(metadata["source_row_queue"][-1]["raw_line"].endswith(".txt"))
            self.assertTrue(metadata["retained_file_structurally_valid"])
            self.assertEqual(metadata["queue_status"], "RETAINED_FILE_QUEUE_READY_FOR_REVIEW")
            self.assertFalse(metadata["upstream_index_completeness_verified"])
            self.assertFalse(metadata["exhaustive_us_listed_discovery_verified"])

    def test_no_newline_unknown_partial_or_conflicting_transport_still_excludes_whole_capture(self):
        for declarations in [{}, {"raw_complete": None}, {"raw_complete": False},
                             {"raw_complete": True, "nested": False}, {"raw_complete": None, "nested": False}]:
            document = self.observed_format_document(); document["text"] = document["text"].rstrip("\n")
            for key, value in declarations.items():
                (document["source"] if key == "nested" else document)["raw_complete"] = value
            result = ms.parse(document); metadata = result["adapter_metadata"]
            self.assertTrue(all(not row["eligible"] for row in result["records"]))
            self.assertEqual(metadata["terminal_newline_qualification"], "ABSENT_POSSIBLE_TRUNCATION")
            self.assertEqual(metadata["queue_status"], "RETAINED_INDEX_INCOMPLETE_OR_MALFORMED")
            self.assertEqual(len(metadata["source_row_queue"]), 3)

    def test_complete_transport_does_not_conceal_malformed_unterminated_tail(self):
        document = self.observed_format_document(); document["text"] += "42|Fictional truncated"
        document["raw_complete"] = True; document["form_filter"] = ["8-K"]
        result = ms.parse(document); metadata = result["adapter_metadata"]
        self.assertEqual(metadata["source_data_rows"], 4)
        self.assertEqual(metadata["malformed_rows"], 1)
        self.assertEqual(len(metadata["source_row_queue"]), 4)
        self.assertTrue(all(not row["eligible"] for row in result["records"]))
        self.assertEqual(metadata["terminal_newline_qualification"], "ABSENT_POSSIBLE_TRUNCATION")

    def test_observed_schema_retains_filter_mapping_and_original_clock_guards(self):
        document = self.observed_format_document(); document.pop("cik_symbol_mapping")
        document["raw_complete"] = True; document["text"] = document["text"].rstrip("\n")
        document["form_filter"] = ["8-K", "6-K"]
        result = ms.parse(document); metadata = result["adapter_metadata"]
        self.assertEqual(metadata["source_data_rows"], 3)
        self.assertEqual(metadata["filtered_out_rows"], 2)
        self.assertEqual(len(result["records"]), 1)
        self.assertFalse(result["records"][0]["eligible"])
        self.assertIn("SEC_DAILY_INDEX_SYMBOL_MAPPING_UNRESOLVED", result["records"][0]["exclusion_reasons"])
        document["source"].update(retrieved_at="2026-11-11T20:00:00Z", observed_at="2026-11-11T20:00:00Z")
        result = ms.parse(document)
        self.assertEqual(result["adapter_metadata"]["queue_status"], "RETAINED_INDEX_CHRONOLOGY_CONFLICT")
        self.assertIn("PARSE_ERROR", result["records"][0]["exclusion_reasons"])

    def test_explicit_form_filter_can_select_exact_reported_spaced_form_labels(self):
        document = self.observed_format_document()
        document["text"] = document["text"].replace("|8-K|", "|SCHEDULE 13G/A|")
        document["form_filter"] = ["SCHEDULE 13G/A"]
        result = ms.parse(document); metadata = result["adapter_metadata"]
        self.assertEqual(len(result["records"]), 1)
        self.assertEqual(result["records"][0]["payload"]["form"], "SCHEDULE 13G/A")
        self.assertTrue(result["records"][0]["eligible"])
        self.assertEqual(metadata["source_data_rows"], 3)
        self.assertEqual(len(metadata["source_row_queue"]), 3)
        self.assertEqual(metadata["filtered_out_rows"], 2)
        self.assertEqual(metadata["emitted_form_counts"], {"SCHEDULE 13G/A": 1})
        self.assertEqual(metadata["form_filter"], ["SCHEDULE 13G/A"])

    def test_form_filter_does_not_trim_coerce_or_accept_unbounded_spaced_labels(self):
        for value in [" SCHEDULE 13G/A", "SCHEDULE 13G/A ", "SCHEDULE  13G/A", "SCHEDULE\t13G/A",
                      "SCHEDULE\n13G/A", "SCHEDULE 13G/A?proxy=1", "A" * 33]:
            document = self.observed_format_document(); document["form_filter"] = [value]
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "Explicit unique form_filter"):
                ms.parse(document)

    def test_exact_index_url_requires_consistent_calendar_and_no_proxy_query_or_redirect(self):
        self.assertEqual(ms.allowed_public_url(self.URL), "www.sec.gov")
        for url in [self.URL.replace("QTR4", "QTR3"), self.URL.replace("/2026/", "/2025/"),
                    self.URL.replace("20261112.idx", "20261131.idx"),
                    self.URL.replace("QTR4/master.20261112", "QTR1/master.20260229"),
                    self.URL.replace("www.sec.gov", "data.sec.gov"), self.URL.replace("www.sec.gov", "example.org"),
                    self.URL + "?proxy=1", self.URL + "#fragment", self.URL.replace("www.sec.gov", "user@www.sec.gov"),
                    self.URL.replace("www.sec.gov", "www.sec.gov:444"), self.URL.replace("master.", "company."),
                    self.URL.replace("/QTR4/", "/QTR4/../QTR4/")]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                ms.allowed_public_url(url)
        redirect = ms._NoRedirect()
        with self.assertRaises(HTTPError):
            redirect.redirect_request(ms.Request(self.URL), None, 302, "redirect", {}, "https://example.org/proxy")

    def test_whole_index_retains_all_forms_and_filer_types_with_mapping_provenance(self):
        document = self.document(); before = copy.deepcopy(document)
        result = ms.parse(document); rows = result["records"]; metadata = result["adapter_metadata"]
        self.assertEqual(document, before)
        self.assertEqual([r["payload"]["form"] for r in rows], ["8-K", "4", "NPORT-P"])
        self.assertEqual([r["ticker"] for r in rows], ["ALPHA", "BETA", "FUND"])
        self.assertTrue(all(r["eligible"] for r in rows))
        self.assertEqual(rows[0]["payload"]["filer_cik"], "42")
        self.assertEqual(rows[0]["payload"]["filer_name"], "Fictional Alpha")
        self.assertEqual(rows[0]["payload"]["filing_date"], "2026-11-12")
        self.assertEqual(rows[0]["payload"]["accession_number"], "0000009999-26-000001")
        self.assertEqual(rows[0]["payload"]["raw_line"], self.ROWS[0])
        self.assertEqual(rows[0]["payload"]["symbol_mapping"], document["cik_symbol_mapping"]["0000000042"])
        self.assertIsNone(rows[0]["payload"]["published_at"])
        self.assertIsNone(rows[0]["source"]["published_at"])
        self.assertEqual(rows[0]["available_at"], document["source"]["retrieved_at"])
        self.assertEqual(ms.allowed_public_url(rows[0]["payload"]["filing_document_url"]), "www.sec.gov")
        self.assertEqual(ms.allowed_public_url(rows[0]["payload"]["source_filename_url"]), "www.sec.gov")
        self.assertEqual(rows[0]["payload"]["filing_document_url_status"], "CONSTRUCTED_NOT_FETCHED")
        self.assertEqual(metadata["source_data_rows"], 3)
        self.assertEqual(metadata["parsed_rows"], 3)
        self.assertEqual(metadata["eligible_rows_at_cutoff"], 3)
        self.assertTrue(metadata["all_retained_nonempty_data_rows_processed"])
        self.assertFalse(metadata["upstream_index_completeness_verified"])
        self.assertFalse(metadata["exhaustive_us_listed_discovery_verified"])
        self.assertEqual(metadata["queue_status"], "RETAINED_FILE_QUEUE_READY_FOR_REVIEW")
        self.assertIs(result["execution_authorized"], False)

    def test_without_mapping_every_parsed_row_remains_visible_but_identity_unusable(self):
        result = ms.parse(self.document(mapped=False))
        self.assertEqual(len(result["records"]), 3)
        self.assertTrue(all(r["ticker"] is None and not r["eligible"] for r in result["records"]))
        self.assertTrue(all("SEC_DAILY_INDEX_SYMBOL_MAPPING_UNRESOLVED" in r["exclusion_reasons"] for r in result["records"]))
        self.assertTrue(all("parse_error" not in r for r in result["records"]))
        self.assertEqual(result["adapter_metadata"]["queue_status"], "IDENTITY_RESOLUTION_INCOMPLETE")
        self.assertEqual(result["adapter_metadata"]["parsed_rows"], 3)
        self.assertEqual(result["adapter_metadata"]["identity_unresolved_rows"], 3)
        self.assertEqual(ms.normalize({"schema_version": 1, "as_of": result["as_of"],
                                       "records": result["records"]})["records"][0]["eligible"], False)

    def test_partial_or_future_identity_mapping_never_manufactures_full_scope(self):
        document = self.document()
        for key in ["0000000084", "0000000126"]:
            document["cik_symbol_mapping"].pop(key)
        mapped = document["cik_symbol_mapping"]["0000000042"]
        mapped["available_at"] = "2026-11-13T10:00:00Z"
        mapped["source"].update(retrieved_at=mapped["available_at"], observed_at=mapped["available_at"])
        result = ms.parse(document)
        self.assertEqual(result["adapter_metadata"]["eligible_rows_at_cutoff"], 1)
        self.assertEqual(result["records"][0]["available_at"], mapped["available_at"])
        earlier = ms.normalize({"schema_version": 1, "as_of": "2026-11-13T09:30:00Z", "records": result["records"]})
        self.assertFalse(earlier["records"][0]["eligible"])
        document["as_of"] = "2026-11-13T09:30:00Z"
        self.assertTrue(all(not r["eligible"] for r in ms.parse(document)["records"]))

    def test_ambiguous_or_unproven_mapping_stays_unusable_with_original_declaration(self):
        for replacement in ["ALPHA", {"ticker": "ALPHA"}, {"ticker": ["ALPHA", "ALPHA.B"]}]:
            document = self.document(); document["cik_symbol_mapping"]["0000000042"] = replacement
            row = ms.parse(document)["records"][0]
            self.assertFalse(row["eligible"])
            self.assertIsNone(row["ticker"])
            self.assertEqual(row["payload"]["symbol_mapping"], replacement)
        document = self.document(); document["cik_symbol_mapping"]["42"] = copy.deepcopy(document["cik_symbol_mapping"]["0000000042"])
        with self.assertRaisesRegex(ValueError, "Duplicate normalized CIK"):
            ms.parse(document)

    def test_invalid_index_availability_remains_unknown_without_duplicate_rows(self):
        document = self.document(); document["available_at"] = "not-an-exact-clock"
        rows = ms.parse(document)["records"]
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(not r["eligible"] for r in rows))
        self.assertTrue(all("AVAILABILITY_UNKNOWN_OR_INVALID" in r["exclusion_reasons"] for r in rows))

    def test_future_index_date_retains_rows_but_cannot_become_eligible_at_later_cutoff(self):
        for cutoff in ["2026-11-13T11:00:00Z", "2027-01-07T11:00:00Z"]:
            document = self.document()
            document["source"]["url"] = self.URL.replace("2026/QTR4/master.20261112", "2027/QTR1/master.20270105")
            document["text"] = document["text"].replace("November 12, 2026", "January 05, 2027").replace("2026-11-12|", "2027-01-05|")
            document["as_of"] = cutoff
            if cutoff.startswith("2027"):
                for mapping in document["cik_symbol_mapping"].values():
                    mapping["available_at"] = "2027-01-06T09:00:00Z"
                    mapping["source"].update(retrieved_at=mapping["available_at"], observed_at=mapping["available_at"])
            before = copy.deepcopy(document)
            result = ms.parse(document); metadata = result["adapter_metadata"]
            self.assertEqual(document, before)
            self.assertEqual(len(result["records"]), metadata["source_data_rows"])
            self.assertEqual(len(metadata["source_row_queue"]), 3)
            self.assertEqual([r["raw_line"] for r in metadata["source_row_queue"]], document["text"].splitlines()[-3:])
            self.assertTrue(metadata["retained_file_structurally_valid"])
            self.assertEqual(metadata["queue_status"], "RETAINED_INDEX_CHRONOLOGY_CONFLICT")
            self.assertEqual(metadata["eligible_rows_at_cutoff"], 0)
            self.assertTrue(all(not r["eligible"] and "PARSE_ERROR" in r["exclusion_reasons"] for r in result["records"]))
            self.assertTrue(all("SEC_DAILY_INDEX_DATE_AFTER_ORIGINAL_CLOCK" in r["parse_error"] for r in result["records"]))
            self.assertEqual(metadata["index_chronology"]["checked_original_clock_utc_dates"]["source.retrieved_at"], "2026-11-13")
            if cutoff.startswith("2027"):
                self.assertEqual(result["records"][0]["available_at"], "2027-01-06T09:00:00Z")

    def test_each_original_capture_or_availability_clock_is_checked_independently(self):
        for field in ["source.retrieved_at", "source.observed_at", "available_at"]:
            document = self.document(); document["available_at"] = "2026-11-13T09:00:00Z"
            document["source"]["availability_basis"] = "declared_source_availability"
            if field.startswith("source."):
                document["source"][field.split(".")[1]] = "2026-11-11T23:00:00Z"
            else:
                document[field] = "2026-11-11T23:00:00Z"
            result = ms.parse(document)
            self.assertEqual(result["adapter_metadata"]["index_chronology"]["conflicting_clock_fields"], [field])
            self.assertTrue(all(not row["eligible"] for row in result["records"]))

    def test_offset_normalization_allows_same_utc_date_without_inventing_publication(self):
        document = self.document(); clock = "2026-11-11T19:30:00-05:00"
        document["available_at"] = clock
        document["source"].update(retrieved_at=clock, observed_at=clock)
        result = ms.parse(document); chronology = result["adapter_metadata"]["index_chronology"]
        self.assertTrue(all(row["eligible"] for row in result["records"]))
        self.assertEqual(set(chronology["checked_original_clock_utc_dates"].values()), {"2026-11-12"})
        self.assertEqual(chronology["status"], "NECESSARY_DATE_CHECK_PASSED")
        self.assertTrue(chronology["necessary_check_only"])
        self.assertEqual(chronology["date_basis"], "UTC_CALENDAR_DATE")
        self.assertTrue(all(row["source"]["published_at"] is None and row["payload"]["published_at"] is None for row in result["records"]))

    def test_offset_normalization_excludes_future_utc_date_even_after_identity_advances_availability(self):
        document = self.document(); clock = "2026-11-12T00:30:00+02:00"
        document["available_at"] = clock
        document["source"].update(retrieved_at=clock, observed_at=clock)
        result = ms.parse(document); chronology = result["adapter_metadata"]["index_chronology"]
        self.assertTrue(all(not row["eligible"] for row in result["records"]))
        self.assertEqual(set(chronology["checked_original_clock_utc_dates"].values()), {"2026-11-11"})
        self.assertEqual(result["records"][0]["available_at"], "2026-11-12T20:00:00Z")

    def test_historical_index_passes_only_necessary_calendar_check(self):
        result = ms.parse(self.document()); metadata = result["adapter_metadata"]
        self.assertTrue(all(row["eligible"] for row in result["records"]))
        self.assertEqual(metadata["index_chronology"]["status"], "NECESSARY_DATE_CHECK_PASSED")
        self.assertEqual(metadata["capture_qualification_errors"], [])
        self.assertFalse(metadata["upstream_index_completeness_verified"])
        self.assertFalse(metadata["exhaustive_us_listed_discovery_verified"])

    def test_contradictory_transport_flags_are_retained_as_gap_without_priority(self):
        for top, nested in [(True, False), (False, True)]:
            document = self.document(); document["raw_complete"] = top
            document["source"]["raw_complete"] = nested
            document["form_filter"] = ["8-K"]
            result = ms.parse(document); metadata = result["adapter_metadata"]
            self.assertEqual(len(metadata["source_row_queue"]), 3)
            self.assertTrue(all("SEC_DAILY_INDEX_CAPTURE_COMPLETENESS_CONFLICT" in row["qualification_errors"] for row in metadata["source_row_queue"]))
            self.assertEqual(metadata["transport_completion_declarations"], {"raw_complete": top, "source.raw_complete": nested})
            self.assertTrue(metadata["transport_completion_conflict"])
            self.assertIsNone(metadata["transport_complete_declared"])
            self.assertEqual(metadata["queue_status"], "RETAINED_INDEX_INCOMPLETE_OR_MALFORMED")
            self.assertFalse(result["records"][0]["eligible"])
            self.assertEqual(result["records"][0]["source"]["raw_complete"], nested)

    def test_transport_flags_reconcile_equal_redundant_truthful_and_unknown_values(self):
        for top, nested, expected in [(True, True, True), (False, False, False),
                                      (None, True, True), (True, None, True),
                                      (None, False, False), (False, None, False), (None, None, None)]:
            document = self.document(); document["raw_complete"] = top
            document["source"]["raw_complete"] = nested
            result = ms.parse(document); metadata = result["adapter_metadata"]
            self.assertIs(metadata["transport_complete_declared"], expected)
            self.assertFalse(metadata["transport_completion_conflict"])
            self.assertEqual(all(row["eligible"] for row in result["records"]), expected is not False)
        for location in ["top", "source"]:
            document = self.document()
            (document if location == "top" else document["source"])["raw_complete"] = True
            self.assertTrue(ms.parse(document)["adapter_metadata"]["transport_complete_declared"])

    def test_invalid_transport_declaration_cannot_hide_behind_another_true_flag(self):
        for top, nested in [(True, "False"), (1, True), (False, []), (True, 0)]:
            document = self.document(); document["raw_complete"] = top
            document["source"]["raw_complete"] = nested
            with self.assertRaisesRegex(ValueError, "raw_complete must be Boolean"):
                ms.parse(document)

    def test_header_structure_and_selected_filename_date_must_match(self):
        for text in [self.PREFIX.replace("November 12", "November 11") + self.ROWS[0] + "\n",
                     self.PREFIX.replace("Master Index", "Company Index") + self.ROWS[0] + "\n",
                     self.PREFIX.replace("CIK|Company Name", "CIK|Name") + self.ROWS[0] + "\n",
                     self.PREFIX.replace("--------------------------------------------------------------------------------", "broken") + self.ROWS[0] + "\n"]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                ms.parse(self.document(text=text))

    def test_malformed_rows_are_retained_and_whole_queue_failure_is_explicit(self):
        for bad in ["42|Fictional tail", self.ROWS[0].replace("edgar/data/42/", "edgar/data/84/"),
                    self.ROWS[0].replace("edgar/data/42/", "https://example.org/edgar/data/42/"),
                    self.ROWS[0].replace("edgar/data/42/", "edgar/data/42/../"),
                    self.ROWS[0].replace("2026-11-12|", "2026-11-13|"),
                    self.ROWS[0].replace(".txt", ".txt?proxy=1")]:
            with self.subTest(bad=bad):
                document = self.document(text=self.PREFIX + self.ROWS[0] + "\n" + bad + "\n")
                result = ms.parse(document)
                self.assertEqual(len(result["records"]), 2)
                self.assertTrue(result["records"][0]["eligible"])
                self.assertFalse(result["records"][1]["eligible"])
                self.assertEqual(result["records"][1]["payload"]["raw_line"], bad)
                self.assertIn("parse_error", result["records"][1])
                self.assertEqual(result["adapter_metadata"]["source_data_rows"], 2)
                self.assertEqual(result["adapter_metadata"]["malformed_rows"], 1)
                self.assertEqual(result["adapter_metadata"]["queue_status"], "RETAINED_INDEX_INCOMPLETE_OR_MALFORMED")

    def test_malformed_tail_and_declared_partial_capture_cannot_enter_queue(self):
        for document in [self.document(text=self.PREFIX + self.ROWS[0] + "\n42|truncated"),
                         dict(self.document(), raw_complete=False)]:
            result = ms.parse(document)
            self.assertTrue(result["records"])
            self.assertTrue(all(not r["eligible"] for r in result["records"]))
            self.assertFalse(result["adapter_metadata"]["retained_file_structurally_valid"])
            self.assertEqual(result["adapter_metadata"]["queue_status"], "RETAINED_INDEX_INCOMPLETE_OR_MALFORMED")

    def test_well_formed_prefix_and_full_body_declaration_do_not_certify_upstream_completeness(self):
        document = self.document(text=self.PREFIX + self.ROWS[0] + "\n")
        document["raw_complete"] = True
        result = ms.parse(document); meta = result["adapter_metadata"]
        self.assertEqual(meta["source_data_rows"], 1)
        self.assertTrue(meta["retained_file_structurally_valid"])
        self.assertTrue(meta["transport_complete_declared"])
        self.assertFalse(meta["upstream_index_completeness_verified"])
        self.assertFalse(meta["exhaustive_us_listed_discovery_verified"])

    def test_unknown_ticker_behavior_of_existing_other_adapters_is_preserved(self):
        document = parse_doc("sec_submissions", data={"cik": "42", "filings": {"recent": {
            "accessionNumber": ["0000009999-26-000001"], "form": ["8-K"], "filingDate": ["2026-11-10"]}}})
        row = ms.parse(document)["records"][0]
        self.assertIsNone(row["ticker"])
        self.assertTrue(row["eligible"])

    def test_direct_submission_capture_family_remains_exact_and_does_not_fetch_links(self):
        url = "https://www.sec.gov/Archives/edgar/data/42/0000009999-26-000001.txt"
        self.assertEqual(ms.allowed_public_url(url), "www.sec.gov")
        for bad in [url + '?redirect=1', url + '#content', url.replace('.txt', '.html'),
                    url.replace('.txt', '.txt.exe'), url.replace('www.sec.gov', 'proxy.example.org'),
                    url.replace('/data/42/', '/data/42/../')]:
            with self.subTest(url=bad), self.assertRaises(ValueError):
                ms.allowed_public_url(bad)
        with patch.object(ms, 'build_opener', side_effect=AssertionError('pure parse must not fetch filing links')):
            self.assertEqual(ms.parse(self.document())['adapter_metadata']['source_data_rows'], 3)

    def test_explicit_form_filter_keeps_whole_raw_queue_and_never_hides_malformed_rows(self):
        amendment = self.ROWS[0].replace('|8-K|', '|8-K/A|').replace('000001.txt', '000004.txt')
        malformed = '42|Fictional broken row'
        document = self.document(text=self.PREFIX + '\n'.join(self.ROWS + [amendment, malformed]) + '\n')
        document['form_filter'] = ['8-K', '6-K']
        result = ms.parse(document); meta = result['adapter_metadata']
        self.assertEqual(meta['source_data_rows'], 5)
        self.assertEqual(meta['parsed_rows'], 4)
        self.assertEqual(meta['filtered_out_rows'], 3)
        self.assertEqual(meta['emitted_records'], 2)
        self.assertEqual(len(meta['source_row_queue']), 5)
        self.assertEqual([r['raw_line'] for r in meta['source_row_queue']], self.ROWS + [amendment, malformed])
        self.assertEqual(meta['source_form_counts'], {'8-K': 1, '4': 1, 'NPORT-P': 1, '8-K/A': 1})
        self.assertEqual(meta['emitted_form_counts'], {'8-K': 1})
        self.assertEqual(meta['emitted_scope'], 'EXPLICIT_FORM_FILTER_SUBSET')
        self.assertEqual(result['records'][0]['payload']['form'], '8-K')
        self.assertEqual(result['records'][1]['payload']['raw_line'], malformed)
        self.assertFalse(result['records'][1]['eligible'])
        self.assertEqual(meta['queue_status'], 'RETAINED_INDEX_INCOMPLETE_OR_MALFORMED')
        self.assertFalse(meta['exhaustive_us_listed_discovery_verified'])

    def test_over_10000_source_rows_are_preserved_with_explicit_subset_or_partition_requirement(self):
        rows = ['42|Fictional Alpha|' + ('8-K' if n == 10000 else '4') +
                '|2026-11-12|edgar/data/42/0000009999-26-' + str(n).zfill(6) + '.txt' for n in range(10001)]
        document = self.document(text=self.PREFIX + '\n'.join(rows) + '\n')
        complete = ms.parse(document)
        self.assertEqual(len(complete['records']), 10001)
        self.assertEqual(len(complete['adapter_metadata']['source_row_queue']), 10001)
        self.assertTrue(complete['adapter_metadata']['downstream_partition_required'])
        self.assertEqual(complete['adapter_metadata']['queue_status'], 'DOWNSTREAM_DOCUMENT_PARTITION_REQUIRED')
        document['form_filter'] = ['8-K', '6-K']
        selected = ms.parse(document); meta = selected['adapter_metadata']
        self.assertEqual(len(selected['records']), 1)
        self.assertEqual(meta['source_data_rows'], 10001)
        self.assertEqual(meta['filtered_out_rows'], 10000)
        self.assertEqual(len(meta['source_row_queue']), 10001)
        self.assertEqual(meta['source_form_counts'], {'4': 10000, '8-K': 1})
        self.assertFalse(meta['downstream_partition_required'])
        self.assertTrue(meta['form_filter_applied'])
        self.assertFalse(meta['upstream_index_completeness_verified'])
        self.assertFalse(meta['exhaustive_us_listed_discovery_verified'])
        self.assertEqual(meta['eligible_rows_at_cutoff'], 1)

    def test_form_filter_is_explicit_unique_and_never_a_silent_default(self):
        for value in [[], ['8-K', '8-K'], '8-K', [True], ['8-K?query=1']]:
            document = self.document(); document['form_filter'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                ms.parse(document)
        unfiltered = ms.parse(self.document())
        self.assertFalse(unfiltered['adapter_metadata']['form_filter_applied'])
        self.assertEqual(len(unfiltered['records']), 3)

    def test_form_filter_preserves_source_row_ids_within_the_same_capture_vintage(self):
        document = self.document()
        whole = ms.parse(document)
        document['form_filter'] = ['4']
        subset = ms.parse(document)
        self.assertEqual(len(subset['records']), 1)
        self.assertEqual(subset['records'][0]['id'], whole['records'][1]['id'])
        self.assertEqual(subset['records'][0]['payload']['raw_line'], self.ROWS[1])
        self.assertEqual([r['source_record_id'] for r in subset['adapter_metadata']['source_row_queue']],
                         [r['id'] for r in whole['records']])


class Response(io.BytesIO):
    def __init__(self, body, status=200, headers=None, url=URL):
        super().__init__(body)
        self.status = self.code = status
        self.headers = headers or {}
        self.url = url

    def geturl(self):
        return self.url


class AcquisitionTests(unittest.TestCase):
    def test_selected_sec_daily_index_mock_capture_and_parse_keep_transport_and_scope_separate(self):
        fixture = SecDailyIndexTests().document()
        body = fixture['text'].encode('utf8')
        response = Response(body, headers={'Content-Length': str(len(body)), 'ETag': '"fictional-index"'},
                            url=SecDailyIndexTests.URL)
        with tempfile.TemporaryDirectory() as root, patch.object(ms, 'build_opener') as builder:
            builder.return_value.open.return_value = response
            capture = ms.acquire(SecDailyIndexTests.URL, Path(root)/'index', 'fictional-index',
                                 'Synthetic client test@example.invalid', retries=0)
            self.assertEqual(capture['status'], 'ACQUIRED')
            request = builder.return_value.open.call_args.args[0]
            self.assertEqual(request.full_url, SecDailyIndexTests.URL)
            self.assertEqual(request.get_method(), 'GET')
            self.assertNotIn('Authorization', request.headers)
            self.assertNotIn('Cookie', request.headers)
            self.assertEqual((Path(root)/'index'/capture['raw_file']).read_bytes(), body)
            fixture.update(source=capture['source'], as_of=capture['available_at'],
                           raw_complete=capture['attempts'][0]['raw_complete'])
            result = ms.parse(fixture)
            self.assertEqual(result['adapter_metadata']['eligible_rows_at_cutoff'], 3)
            self.assertTrue(result['adapter_metadata']['transport_complete_declared'])
            self.assertFalse(result['adapter_metadata']['upstream_index_completeness_verified'])
            self.assertFalse(result['adapter_metadata']['exhaustive_us_listed_discovery_verified'])

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
