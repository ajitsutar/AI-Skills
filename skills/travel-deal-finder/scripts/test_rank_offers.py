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
                },
            ]
        )
        self.assertLess(table.index("Known total"), table.index("Unknown total"))
        self.assertIn("| Unknown |", table)
        self.assertNotIn("USD 0.00", table)

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
        self.assertIn("USD 225.00", table)
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
        self.assertIn("USD 400.00", table)

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

    def test_negative_and_nonfinite_amounts_are_rejected(self) -> None:
        for value in (-1, "nan", "inf"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "finite, nonnegative"):
                    rank_offers.money(value)

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


if __name__ == "__main__":
    unittest.main()
