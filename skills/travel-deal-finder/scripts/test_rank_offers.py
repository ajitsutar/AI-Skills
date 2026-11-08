#!/usr/bin/env python3
"""Regression tests for rank_offers.py using only the Python standard library."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

import rank_offers


class RankOffersTests(unittest.TestCase):
    def eligible_offer(self, **changes: object) -> dict:
        offer = {
            "title": "Verified offer",
            "url": "https://example.com/offer",
            "total_price": 500,
            "currency": "USD",
            "qualifies": True,
            "verification": "verified",
            "verified_at": "2026-11-07T10:00:00-08:00",
            "unknown_fees": False,
        }
        offer.update(changes)
        return offer

    def data_rows(self, table: str) -> list[str]:
        return [line for line in table.splitlines() if line.startswith("| ")][1:]

    def test_missing_total_is_unknown_and_ranks_after_verified_total(self) -> None:
        table = rank_offers.markdown_table(
            [
                {
                    "source": "Incomplete",
                    "title": "Unknown total",
                    "url": "https://example.com/unknown",
                },
                {
                    "source": "Verified",
                    "title": "Known total",
                    "url": "https://example.com/known",
                    "total_price": 500,
                    "currency": "USD",
                    "qualifies": True,
                    "verification": "verified",
                    "verified_at": "2026-11-07",
                    "unknown_fees": False,
                },
            ]
        )
        self.assertLess(table.index("Known total"), table.index("Unknown total"))
        self.assertIn("| Unknown |", table)
        self.assertNotIn("USD 0.00", table)
        rows = self.data_rows(table)
        self.assertTrue(rows[0].startswith("| 1 |"))
        self.assertTrue(rows[1].startswith("| Unranked |"))
        self.assertIn("unknown total", rows[1])

    def test_risks_do_not_change_actual_total_ranking(self) -> None:
        offers = [
            self.eligible_offer(title="Expensive", total_price=101),
            self.eligible_offer(
                title="Cheaper with risks", total_price=100,
                cancellable=False, refundable="false", split_ticket="yes",
                poor_location=True, notes="Long transfer",
            ),
        ]
        table = rank_offers.markdown_table(offers)
        rows = self.data_rows(table)
        self.assertTrue(rows[0].startswith("| 1 |"))
        self.assertIn("Cheaper with risks", rows[0])
        self.assertIn("USD 100.00", rows[0])
        self.assertIn("Long transfer; noncancellable; nonrefundable; split ticket; poor location", rows[0])
        self.assertTrue(rows[1].startswith("| 2 |"))
        self.assertIn("USD 101.00", rows[1])
        self.assertNotIn("Adjusted score", table)

    def test_each_eligibility_requirement_blocks_ranking(self) -> None:
        cases = [
            ({"qualifies": False}, "qualifies is not explicitly true"),
            ({"qualifies": None}, "qualifies is not explicitly true"),
            ({"qualifies": "true"}, "qualifies is not explicitly true"),
            ({"qualifies": 1}, "qualifies is not explicitly true"),
            ({"verification": "unverified"}, "verification is not verified"),
            ({"verification": "stale"}, "verification is not verified"),
            ({"verification": "Verified"}, "verification is not verified"),
            ({"verification": None}, "verification is not verified"),
            ({"verified_at": ""}, "missing verified_at"),
            ({"verified_at": " \t\n"}, "missing verified_at"),
            ({"verified_at": None}, "missing verified_at"),
            ({"verified_at": True}, "missing verified_at"),
            ({"url": None}, "missing source URL"),
            ({"url": " \t"}, "missing source URL"),
            ({"total_price": None}, "unknown total"),
            ({"unknown_fees": True}, "unknown fees"),
            ({"unknown_fees": "unknown"}, "unknown fees"),
            ({"unknown_fees": 25}, "unknown fees"),
            ({"hard_fail_reason": "Wrong dates"}, "hard constraint failed: Wrong dates"),
        ]
        for changes, reason in cases:
            with self.subTest(changes=changes):
                table = rank_offers.markdown_table([self.eligible_offer(**changes)])
                row, = self.data_rows(table)
                self.assertTrue(row.startswith("| Unranked |"))
                self.assertIn(reason, row)

    def test_missing_required_metadata_is_not_inferred(self) -> None:
        for field in ("qualifies", "verification", "verified_at", "url", "total_price", "unknown_fees"):
            with self.subTest(field=field):
                offer = self.eligible_offer()
                del offer[field]
                row, = self.data_rows(rank_offers.markdown_table([offer]))
                self.assertTrue(row.startswith("| Unranked |"))

    def test_legacy_input_is_unverified_with_all_reasons(self) -> None:
        table = rank_offers.markdown_table([{"title": "Legacy"}])
        row, = self.data_rows(table)
        self.assertTrue(row.startswith("| Unranked | no | unverified |"))
        for reason in (
            "qualifies is not explicitly true", "verification is not verified",
            "missing verified_at", "missing source URL", "unknown total",
            "fee completeness unconfirmed",
        ):
            self.assertIn(reason, row)
        self.assertIn("does not independently verify live websites", table)

    def test_only_eligible_offers_receive_contiguous_ranks(self) -> None:
        offers = [
            self.eligible_offer(title="Unranked first", total_price=1, verification="stale"),
            self.eligible_offer(title="Second", total_price=600),
            self.eligible_offer(title="Unranked later", total_price=0, unknown_fees=True),
            self.eligible_offer(title="First", total_price=500),
        ]
        rows = self.data_rows(rank_offers.markdown_table(offers))
        for row, rank, title in zip(rows, ("1", "2", "Unranked", "Unranked"),
                                    ("First", "Second", "Unranked first", "Unranked later")):
            self.assertTrue(row.startswith(f"| {rank} |"))
            self.assertIn(title, row)

    def test_zero_total_and_false_fee_encodings_are_eligible(self) -> None:
        for fees in (False, "false", "no", "n", "none", " FALSE ", 0, 0.0, "0", "0.00"):
            with self.subTest(fees=fees):
                row, = self.data_rows(rank_offers.markdown_table([
                    self.eligible_offer(total_price=0, unknown_fees=fees)
                ]))
                self.assertTrue(row.startswith("| 1 |"))
                self.assertIn("USD 0.00 | no |", row)

    def test_unconfirmed_fee_completeness_is_unranked_and_displayed(self) -> None:
        for changes in ({}, {"unknown_fees": None}, {"unknown_fees": ""},
                        {"unknown_fees": " \t\n"}, {"unknown_fees": "$"}):
            with self.subTest(changes=changes):
                offer = self.eligible_offer(title="Incomplete fees", total_price=1)
                del offer["unknown_fees"]
                offer.update(changes)
                self.assertEqual(rank_offers.unknown_fee_details(offer), (None, None))
                self.assertEqual(rank_offers.eligibility_reasons(offer),
                                 ["fee completeness unconfirmed"])
                rows = self.data_rows(rank_offers.markdown_table([
                    offer, self.eligible_offer(title="Complete fees", total_price=500),
                ]))
                self.assertTrue(rows[0].startswith("| 1 |"))
                self.assertIn("Complete fees", rows[0])
                self.assertTrue(rows[1].startswith("| Unranked |"))
                self.assertIn("USD 1.00 | unconfirmed | fee completeness unconfirmed |", rows[1])

    def test_mixed_currencies_are_rejected(self) -> None:
        offers = [
            {"title": "US", "total_price": 500, "currency": "USD"},
            {"title": "Europe", "total_price": 450, "currency": "EUR"},
        ]
        with self.assertRaisesRegex(ValueError, "multiple currencies"):
            rank_offers.markdown_table(offers)

    def test_priced_offer_requires_currency(self) -> None:
        with self.assertRaisesRegex(ValueError, "no three-letter currency"):
            rank_offers.markdown_table([{"title": "No currency", "total_price": 250}])

    def test_unknown_fee_amount_and_risk_flags_are_visible(self) -> None:
        table = rank_offers.markdown_table(
            [
                {
                    "source": "Example",
                    "title": "Hotel",
                    "url": "https://example.com/hotel",
                    "total_price": 100,
                    "currency": "USD",
                    "unknown_fees": 25,
                    "cancellable": False,
                    "refundable": False,
                }
            ]
        )
        self.assertIn("estimated additional USD 25.00", table)
        self.assertIn("USD 100.00", table)
        self.assertNotIn("USD 225.00", table)
        self.assertIn("| Unranked |", table)
        self.assertIn("noncancellable; nonrefundable", table)

    def test_boolean_unknown_fee_is_explicit(self) -> None:
        table = rank_offers.markdown_table(
            [
                {
                    "title": "Flight",
                    "url": "https://example.com/flight",
                    "total_price": 300,
                    "currency": "USD",
                    "unknown_fees": True,
                }
            ]
        )
        self.assertIn("yes (amount unknown)", table)
        self.assertIn("USD 300.00", table)
        self.assertNotIn("USD 400.00", table)
        self.assertIn("| Unranked |", table)

    def test_unknown_is_only_accepted_for_unknown_fees(self) -> None:
        offer = {
            "title": "Flight",
            "total_price": 300,
            "currency": "USD",
            "cancellable": "unknown",
        }
        with self.assertRaisesRegex(ValueError, "Expected a boolean"):
            rank_offers.markdown_table([offer])

    def test_markdown_cells_and_link_target_are_escaped(self) -> None:
        table = rank_offers.markdown_table(
            [
                {
                    "source": "Agency|Name\nSecond",
                    "title": "Deal [one]|two",
                    "url": "https://example.com/a path?q=x|y",
                    "total_price": 100,
                    "currency": "USD",
                    "notes": "line1|line2\nline3",
                }
            ]
        )
        self.assertIn(r"Agency\|Name Second", table)
        self.assertIn(
            r"[Deal \[one\]\|two](<https://example.com/a%20path?q=x%7Cy>)",
            table,
        )
        self.assertIn(r"line1\|line2 line3", table)

    def test_html_and_non_http_links_are_rejected_or_escaped(self) -> None:
        table = rank_offers.markdown_table(
            [
                {
                    "source": "<b>Agency</b>",
                    "title": "<img src=x onerror=alert(1)>",
                    "url": "https://example.com/deal",
                    "total_price": 100,
                    "currency": "USD",
                }
            ]
        )
        self.assertIn("&lt;b&gt;Agency&lt;/b&gt;", table)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", table)
        self.assertNotIn("<img", table)

        with self.assertRaisesRegex(ValueError, "absolute HTTP"):
            rank_offers.markdown_table(
                [
                    {
                        "title": "Unsafe",
                        "url": "javascript:alert(1)",
                        "total_price": 100,
                        "currency": "USD",
                    }
                ]
            )

    def test_components_sum_but_absent_price_remains_none(self) -> None:
        self.assertEqual(
            rank_offers.offer_total({"base_price": 100, "taxes": 20, "fees": 5}),
            125,
        )
        self.assertIsNone(rank_offers.offer_total({"title": "No price"}))

    def test_component_totals_currency_and_money_parsing_are_preserved(self) -> None:
        offer = self.eligible_offer(
            total_price=None, base_price="$1,000.00", taxes="25.50", fees=4.5,
            currency=" usd ",
        )
        row, = self.data_rows(rank_offers.markdown_table([offer]))
        self.assertTrue(row.startswith("| 1 |"))
        self.assertIn("USD 1,030.00", row)
        self.assertEqual(rank_offers.offer_total(dict(offer, total_price="900")), 900)

    def test_unknown_fee_estimate_requires_currency_even_without_total(self) -> None:
        with self.assertRaisesRegex(ValueError, "no three-letter currency"):
            rank_offers.markdown_table([{"unknown_fees": 25}])

    def test_invalid_currency_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "three-letter code"):
            rank_offers.markdown_table([self.eligible_offer(currency="US")])

    def test_unsafe_urls_are_rejected_even_for_unranked_offers(self) -> None:
        for url in (
            "javascript:alert(1)", "file:///tmp/offer", "/relative",
            "https://example.com:bad/",
            "https://[invalid/",
        ):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    rank_offers.markdown_table([self.eligible_offer(url=url, qualifies=False)])

    def test_urls_with_credentials_are_rejected(self) -> None:
        for url in ("https://user:password@localhost/offer",
                    "https://user@localhost/offer", "https://:password@localhost/offer"):
            with self.subTest(url=url):
                with self.assertRaisesRegex(ValueError, "must not embed credentials"):
                    rank_offers.markdown_table([self.eligible_offer(url=url, qualifies=False)])

    def test_metadata_and_reasons_are_escaped(self) -> None:
        table = rank_offers.markdown_table([self.eligible_offer(
            verification="stale|<b>", verified_at="date|\nnext",
            hard_fail_reason="Wrong|<date>\nnext",
        )])
        self.assertIn(r"stale\|&lt;b&gt;", table)
        self.assertIn(r"date\| next", table)
        self.assertIn(r"hard constraint failed: Wrong\|&lt;date&gt; next", table)

    def test_negative_and_nonfinite_amounts_are_rejected(self) -> None:
        for value in (-1, "nan", "inf"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "finite, nonnegative"):
                    rank_offers.money(value)

    def test_boolean_money_and_overflowing_component_total_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "not a boolean"):
            rank_offers.money(True)
        with self.assertRaisesRegex(ValueError, "finite, nonnegative"):
            rank_offers.markdown_table([
                self.eligible_offer(total_price=None, base_price=1e308, taxes=1e308)
            ])

    def test_cli_accepts_stdin_without_creating_an_input_file(self) -> None:
        script = Path(__file__).with_name("rank_offers.py")
        payload = json.dumps(
            [
                {
                    "source": "Direct",
                    "title": "Known offer",
                    "url": "https://example.com",
                    "total_price": 125,
                    "currency": "USD",
                }
            ]
        )
        completed = subprocess.run(
            [sys.executable, "-B", str(script), "-"],
            input=payload,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("USD 125.00", completed.stdout)
        self.assertIn("| Unranked | no | unverified |", completed.stdout)

    def test_cli_accepts_offers_wrapper_and_reports_malformed_input(self) -> None:
        script = Path(__file__).with_name("rank_offers.py")
        for payload, expected_code, expected_text in (
            (json.dumps({"offers": [self.eligible_offer()]}), 0, "| 1 | yes | verified |"),
            ('{"offers": [42]}', 2, "Offer 1 must be a JSON object"),
            ('{"offers": {}}', 2, "Input must be a JSON array"),
            ('{"offers":', 2, "error:"),
        ):
            with self.subTest(payload=payload):
                completed = subprocess.run(
                    [sys.executable, "-B", str(script), "-"], input=payload,
                    text=True, capture_output=True, check=False,
                )
                self.assertEqual(completed.returncode, expected_code, completed.stderr)
                self.assertIn(expected_text, completed.stdout + completed.stderr)


if __name__ == "__main__":
    unittest.main()
