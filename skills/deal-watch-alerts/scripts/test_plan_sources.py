import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from plan_sources import plan


class SourcePlannerTests(unittest.TestCase):
    def test_seed_order_and_dedup(self):
        result = plan(["WWW.Shop-Demo.COM.", "maker-demo.com"], ["shop-demo.com", "uk.retail-demo.co.uk"])
        self.assertEqual(result["eligible"], [
            {"domain": "shop-demo.com", "origin": "seed"},
            {"domain": "maker-demo.com", "origin": "seed"},
            {"domain": "uk.retail-demo.co.uk", "origin": "proposed"},
        ])
        self.assertEqual(result["coverage"], "not_evaluated")

    def test_eligibility_precedence_and_aliases(self):
        aliases = ["outlet.demo-shop.com=demo-shop.com"]
        result = plan(["outlet.demo-shop.com"], ["demo-shop.com", "store.maker-demo.com", "other-demo.net"],
                      excluded=["maker-demo.com"], paused=["outlet.demo-shop.com"],
                      allowed=["demo-shop.com", "store.maker-demo.com"], aliases=aliases)
        self.assertEqual(result["eligible"], [])
        self.assertEqual([r["reason"] for r in result["skipped"]], ["paused", "excluded", "not_allowlisted"])
        self.assertEqual(plan(["outlet.demo-shop.com"], ["demo-shop.com"], aliases=aliases)["eligible"],
                         [{"domain": "demo-shop.com", "origin": "seed"}])
        self.assertEqual(plan(["demo-shop.com"], paused=["maker-demo.com"],
                              aliases=["shop.maker-demo.com=demo-shop.com"])["skipped"][0]["reason"], "paused")

    def test_allowlist_is_exact_and_does_not_add_candidates(self):
        self.assertFalse(plan(["shop-demo.com"], allowed=[])["eligible"])
        result = plan(proposed=["shop-demo.com", "x.shop-demo.com", "notshop-demo.com"],
                      allowed=["www.shop-demo.com", "maker-demo.com"])
        self.assertEqual([r["domain"] for r in result["eligible"]], ["shop-demo.com"])
        self.assertEqual([r["domain"] for r in result["skipped"]], ["x.shop-demo.com", "notshop-demo.com"])

    def test_bad_hosts_fail_the_entire_plan(self):
        for bad in ("", " shop-demo.com", "*.shop-demo.com", "https://shop-demo.com", "@".join(("user", "shop-demo.com")),
                    "shop-demo.com:443", "shop-demo.com/p", "shop-demo.com?q", "shop-demo.com#x",
                    "foo..com", "foo.com..", "foo.localhost", "host.internal", "127.0.0.1",
                    "[::1]", "co.uk", "com", "x.example.com", "a" * 64 + ".com"):
            for field in ("seeds", "proposed", "paused", "excluded", "allowed"):
                with self.subTest(field=field, bad=bad), self.assertRaises(ValueError):
                    plan(**{field: [bad]})

    def test_conflicting_aliases_and_cycles_fail(self):
        for aliases in (["bad"], ["a.com=b.com", "a.com=c.com"], ["a.com=b.com", "b.com=a.com"],
                        ["a.com=b.com", "b.com=c.com"], ["a.com=http://b.com"]):
            with self.subTest(aliases=aliases), self.assertRaises(ValueError):
                plan(aliases=aliases)

    def test_cli_from_unrelated_directory_no_outputs_written(self):
        script = Path(__file__).with_name("plan_sources.py").resolve()
        with tempfile.TemporaryDirectory() as tmp:
            cli = [sys.executable, "-B", str(script)]
            args = ["--seed", "shop-demo.com", "--discover", "maker-demo.com", "--only-listed"]
            result = subprocess.run(cli + args, cwd=tmp, capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(result.stdout)["skipped"][0]["reason"], "not_allowlisted")
            bad = subprocess.run(cli + ["--discover", "../invalid"], cwd=tmp, capture_output=True)
            self.assertNotEqual(bad.returncode, 0)
            self.assertEqual(bad.stdout, b"")
            self.assertEqual(list(Path(tmp).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
