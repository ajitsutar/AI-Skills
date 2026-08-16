import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


SCRIPT = Path(__file__).resolve().with_name("deal_memory.py")
SPEC = importlib.util.spec_from_file_location("deal_memory_under_test", SCRIPT)
deal_memory = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = deal_memory
assert SPEC.loader is not None
SPEC.loader.exec_module(deal_memory)


def deal(price=100, currency="USD", url="https://shop.example/item?id=1&utm_source=test", **updates):
    value = {
        "store": "Example Shop",
        "product_url": url,
        "item_id": "widget-1",
        "model": "Widget",
        "variant": {"color": "Blue", "size": "Large"},
        "condition": "New",
        "seller": "Example Seller",
        "price": price,
        "currency": currency,
    }
    value.update(updates)
    return value


class DealKeyTests(unittest.TestCase):
    def test_help_lists_claim_protocol(self):
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), "--help"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("claim", result.stdout)
        self.assertIn("commit", result.stdout)

    def test_tracking_parameters_and_query_order_are_canonical(self):
        first = deal(url="https://SHOP.example:443/item?b=2&utm_source=x&a=1#fragment")
        second = deal(url="https://shop.example/item?a=1&b=2&utm_source=y")
        self.assertEqual(deal_memory.build_offer_key(first), deal_memory.build_offer_key(second))

    def test_currency_is_part_of_identity(self):
        self.assertNotEqual(
            deal_memory.build_offer_key(deal(currency="USD")),
            deal_memory.build_offer_key(deal(currency="CAD")),
        )

    def test_empty_identity_and_missing_currency_are_rejected(self):
        with self.assertRaises(ValueError):
            deal_memory.build_key({})
        with self.assertRaisesRegex(ValueError, "currency"):
            deal_memory.build_key({"product_id": "one", "price": 10})

    def test_config_booleans_are_strict(self):
        with self.assertRaisesRegex(ValueError, "true or false"):
            deal_memory.policy_from_config({"memory": {"treat_lower_price_as_new": "false"}})

    def test_key_policy_must_populate_non_currency_identity(self):
        policy = deal_memory.policy_from_config({"memory": {"key_fields": ["currency"]}})
        with self.assertRaisesRegex(ValueError, "non-currency"):
            deal_memory.build_offer_key(deal(), policy)

    def test_configured_shipping_field_changes_offer_key(self):
        policy = deal_memory.policy_from_config(
            {
                "memory": {
                    "key_fields": ["store", "product_id_or_url", "shipping"],
                    "treat_lower_price_as_new": True,
                }
            }
        )
        self.assertNotEqual(
            deal_memory.build_offer_key(deal(shipping="free"), policy),
            deal_memory.build_offer_key(deal(shipping="$9.99"), policy),
        )


class DealMemoryTests(unittest.TestCase):
    def test_only_lower_price_is_new_by_default(self):
        with tempfile.TemporaryDirectory() as temporary:
            memory = Path(temporary) / "memory.json"
            deal_memory.record_alert(memory, deal(price=100), None, None)
            self.assertTrue(deal_memory.check_deal(memory, deal(price=110))["duplicate"])
            lower = deal_memory.check_deal(memory, deal(price=90))
            self.assertFalse(lower["duplicate"])
            self.assertEqual(lower["reason"], "lower_price")

    def test_policy_can_suppress_all_repeat_offer_prices(self):
        policy = deal_memory.policy_from_config(
            {"memory": {"key_fields": list(deal_memory.DEFAULT_IDENTITY_FIELDS), "treat_lower_price_as_new": False}}
        )
        with tempfile.TemporaryDirectory() as temporary:
            memory = Path(temporary) / "memory.json"
            deal_memory.record_alert(memory, deal(price=100), None, None, policy)
            result = deal_memory.check_deal(memory, deal(price=80), policy)
            self.assertTrue(result["duplicate"])
            self.assertIn(result["reason"], {"exact_deal_key", "offer_already_alerted"})

    def test_concurrent_claims_allow_only_one_sender(self):
        with tempfile.TemporaryDirectory() as temporary:
            memory = Path(temporary) / "memory.json"
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(lambda _: deal_memory.claim_deal(memory, deal(), lease_seconds=60), range(2)))
            statuses = sorted(result["status"] for result in results)
            self.assertEqual(statuses, ["already_claimed", "claimed"])
            stored = json.loads(memory.read_text(encoding="utf-8"))
            self.assertEqual(len(stored["pending_claims"]), 1)

    def test_subprocess_claims_allow_only_one_sender(self):
        with tempfile.TemporaryDirectory() as temporary:
            memory = Path(temporary) / "memory.json"
            payload = json.dumps(deal())
            command = [
                sys.executable,
                "-B",
                str(SCRIPT),
                "claim",
                "--memory",
                str(memory),
                "--deal",
                payload,
                "--lease-seconds",
                "60",
            ]
            processes = [
                subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                for _ in range(2)
            ]
            completed = [process.communicate(timeout=15) for process in processes]
            for process, (_, stderr) in zip(processes, completed):
                self.assertEqual(process.returncode, 0, stderr)
            statuses = sorted(json.loads(stdout)["status"] for stdout, _ in completed)
            self.assertEqual(statuses, ["already_claimed", "claimed"])

    def test_expired_claim_stays_blocking_until_explicit_release(self):
        with tempfile.TemporaryDirectory() as temporary:
            memory = Path(temporary) / "memory.json"
            deal_memory.claim_deal(memory, deal(), lease_seconds=60)
            stored = json.loads(memory.read_text(encoding="utf-8"))
            stored["pending_claims"][0]["claimed_at"] = "2000-01-01T00:00:00+00:00"
            stored["pending_claims"][0]["expires_at"] = "2000-01-01T00:01:00+00:00"
            memory.write_text(json.dumps(stored), encoding="utf-8")

            result = deal_memory.claim_deal(memory, deal(), lease_seconds=60)
            self.assertEqual(result["status"], "already_claimed")
            self.assertTrue(result["claim_expired"])
            self.assertIn("remains blocking", result["claim_warning"])

    def test_malformed_claim_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            memory = Path(temporary) / "memory.json"
            memory.write_text(
                json.dumps({"alerts_sent": [], "pending_claims": [{"claim_id": "ambiguous"}]}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "manual review"):
                deal_memory.claim_deal(memory, deal(), lease_seconds=60)

    def test_memory_path_is_canonicalized_before_locking(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "nested").mkdir()
            direct = root / "memory.json"
            alias = root / "nested" / ".." / "memory.json"
            self.assertEqual(
                deal_memory.canonical_memory_path(direct),
                deal_memory.canonical_memory_path(alias),
            )

    def test_commit_records_delivery_and_removes_claim(self):
        with tempfile.TemporaryDirectory() as temporary:
            memory = Path(temporary) / "memory.json"
            claimed = deal_memory.claim_deal(memory, deal(), lease_seconds=60)
            record = deal_memory.commit_claim(memory, claimed["claim_id"], deal(), None, "sent")
            self.assertEqual(record["notes"], "sent")
            self.assertTrue(deal_memory.check_deal(memory, deal())["duplicate"])
            stored = json.loads(memory.read_text(encoding="utf-8"))
            self.assertEqual(stored["pending_claims"], [])
            self.assertEqual(len(stored["alerts_sent"]), 1)

    def test_release_allows_retry_after_failed_notification(self):
        with tempfile.TemporaryDirectory() as temporary:
            memory = Path(temporary) / "memory.json"
            claimed = deal_memory.claim_deal(memory, deal(), lease_seconds=60)
            self.assertTrue(deal_memory.release_claim(memory, claimed["claim_id"]))
            retried = deal_memory.claim_deal(memory, deal(), lease_seconds=60)
            self.assertEqual(retried["status"], "claimed")

    def test_concurrent_records_are_not_lost_or_corrupted(self):
        with tempfile.TemporaryDirectory() as temporary:
            memory = Path(temporary) / "memory.json"
            candidates = [
                deal(url="https://shop.example/item/one", item_id="one", model="One"),
                deal(url="https://shop.example/item/two", item_id="two", model="Two"),
            ]
            with ThreadPoolExecutor(max_workers=2) as executor:
                list(executor.map(lambda candidate: deal_memory.record_alert(memory, candidate, None, None), candidates))
            stored = json.loads(memory.read_text(encoding="utf-8"))
            self.assertEqual(len(stored["alerts_sent"]), 2)


if __name__ == "__main__":
    unittest.main()
