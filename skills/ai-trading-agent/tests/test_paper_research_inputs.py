import copy
import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from french_daily_factors import evaluate
from paper_pricing import common_anchor, paper_mark
from research_preflight import task_preflight


def packet(symbol):
    identity = {"symbol": symbol, "currency": "USD", "basis": "adjusted_close", "provider": "feed-a"}
    bars = [{**identity, "session": "2026-04-01", "close": 25, "source_id": "capture-1",
             "observed_at": "2026-04-01T20:10:00Z"},
            {**identity, "session": "2026-04-02", "close": None, "source_id": "capture-2",
             "observed_at": "2026-04-02T20:10:00Z"}]
    return {**identity, "session": "2026-04-02", "as_of": "2026-04-02T22:00:00Z", "bars": bars}


class PaperPricing(unittest.TestCase):
    def test_prior_mark_and_status_must_follow_the_exchange_close(self):
        data = packet("AAA")
        data["bars"][0]["observed_at"] = "2026-04-01T18:00:00Z"
        with self.assertRaises(ValueError):
            paper_mark(data)
        data["session_closes"] = {"2026-04-01": "2026-04-01T17:00:00Z"}
        data["status_check"] = {"symbol": "AAA", "session": data["session"],
                                "source_id": "status-source", "observed_at": "2026-04-02T18:00:00Z",
                                "status": "NO_HALT_OR_DELISTING_OBSERVED"}
        self.assertEqual(paper_mark(data)["status"], "STATUS_CHECK_OUTSIDE_CUTOFF")

    def test_carry_requires_same_day_security_status_and_retains_revision(self):
        data = packet("AAA")
        self.assertIsNone(paper_mark(data)["close"])
        check = {"symbol": "AAA", "session": data["session"], "source_id": "status-log",
                 "observed_at": "2026-04-02T20:15:00Z", "status": "HALTED"}
        data["status_check"] = check
        self.assertFalse(paper_mark(data)["carried"])
        check["status"] = "NO_HALT_OR_DELISTING_OBSERVED"
        expected = paper_mark(data)
        self.assertEqual((expected["close"], expected["last_bar_session"], expected["carried"]),
                         (25, "2026-04-01", True))
        data["bars"].append(dict(data["bars"][1], close=26, source_id="revised-capture",
                                 observed_at="2026-04-02T22:15:00Z"))
        self.assertEqual(paper_mark(data), expected)
        data["as_of"] = "2026-04-02T23:00:00Z"
        updated = paper_mark(data)
        self.assertEqual((updated["close"], updated["carried"]), (26, False))
        self.assertIsNone(updated["revisions"][0]["before"]["close"])
        self.assertEqual(updated["revisions"][0]["after"]["source_id"], "revised-capture")
        data["bars"].pop()
        check["observed_at"] = "2026-04-03T18:00:00Z"
        data["as_of"] = "2026-04-04T18:00:00Z"
        self.assertEqual(paper_mark(data)["status"], "STATUS_CHECK_OUTSIDE_CUTOFF")

    def test_partial_coverage_does_not_change_anchor(self):
        a, b = packet("AAA"), packet("BBB")
        panel = {key: a[key] for key in ("currency", "provider", "basis", "as_of")}
        panel.update(requested_session=a["session"], completed_sessions=["2026-04-02", "2026-04-01"],
                     universe=["AAA", "BBB"], series=[a, b])
        self.assertIsNone(common_anchor(panel)["actual_session"])
        panel["allow_previous_complete"] = True
        self.assertEqual(common_anchor(panel)["actual_session"], "2026-04-01")
        b["bars"][1]["close"] = 100
        self.assertIsNone(common_anchor(panel)["actual_session"])
        panel["fallback_max_coverage_fraction"] = 0.5
        self.assertEqual(common_anchor(panel)["actual_session"], "2026-04-01")
        a["bars"][0]["close"] = None
        self.assertIsNone(common_anchor(panel)["actual_session"])
        panel["series"].pop()
        with self.assertRaises(ValueError):
            common_anchor(panel)

    def test_required_garch_reports_blocked_even_when_general_preflight_is_usable(self):
        capabilities = {"volatility": "SKIPPED_MISSING_COMPONENTS", "package_integrity": {"status": "VERIFIED"}}
        self.assertEqual(task_preflight(capabilities, require_garch=True)["blocked"], ["garch"])
        self.assertEqual(task_preflight(capabilities)["blocked"], [])
        capabilities["volatility"] = "AVAILABLE"
        self.assertEqual(task_preflight(capabilities, require_garch=True)["status"], "READY")


class FrenchDaily(unittest.TestCase):
    def test_exact_vintage_alignment_and_percent_conversion(self):
        lines = [",Mkt-RF,SMB,HML,RF"]
        assets = []
        for i in range(1, 10):
            x, y, z = i-3, (i*i)%5, (i*3)%4
            lines.append(f"202604{i:02d},{x},{y},{z},0.01")
            assets.append({"session": f"2026-04-{i:02d}", "asset_return": (2*x+3*y-z+0.01)/100})
        raw = ("\n".join(lines)+"\n").encode()
        cfg = {"model": "FF3", "retrieved_at": "2026-04-10T10:00:00Z",
               "as_of": "2026-04-11T10:00:00Z", "through_session": "2026-04-09",
               "source_url": "fictional factor fixture", "asset_returns": assets,
               "sha256": hashlib.sha256(raw).hexdigest()}
        result = evaluate(raw, cfg)["regression"]
        for name, target in (("mkt_rf", 2), ("smb", 3), ("hml", -1)):
            self.assertAlmostEqual(result["betas"][name], target)
        with self.assertRaises(ValueError):
            evaluate(raw, dict(cfg, sha256="0"*64))
        with self.assertRaises(ValueError):
            evaluate(raw, dict(cfg, as_of="2026-04-09T10:00:00Z"))
        with self.assertRaises(ValueError):
            evaluate(raw, dict(cfg, retrieved_at="2026-04-08T11:00:00Z"))
        altered = raw.replace(b",0.01\n", b",-99.99\n", 1)
        with self.assertRaises(ValueError):
            evaluate(altered, dict(cfg, sha256=hashlib.sha256(altered).hexdigest()))
        missing = copy.deepcopy(cfg)
        missing["asset_returns"][0]["session"] = "2026-03-31"
        with self.assertRaises(ValueError):
            evaluate(raw, missing)
