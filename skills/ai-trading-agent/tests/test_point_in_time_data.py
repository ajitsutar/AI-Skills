"""Original fictional fixtures test causality and hostile-input rejection."""
import copy
import json
import math
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from point_in_time_data import content_hash, normalize, snapshot, strict_load, timestamp


def row(**overrides):
    result = {"instrument_id": "fictional:AAA", "asset_class": "equity", "currency": "USD",
              "field": "close", "event_at": "2026-01-02T21:00:00Z", "available_at": "2026-01-02T21:01:00Z",
              "value": 100.5, "unit": "USD/share", "revision_id": "initial"}
    result.update(overrides)
    return result


def dataset(*rows):
    return {"schema_version": 1, "dataset_id": "fictional-review",
            "source": {"name": "original synthetic fixture", "license": "CC0-1.0", "uri": "urn:synthetic:pit"},
            "records": list(rows)}


def select(data, cutoff="2026-01-03T00:00:00Z"):
    return snapshot({"as_of": cutoff, "dataset": data})


class PointInTimeTests(unittest.TestCase):
    def test_no_restatement_or_future_observation_leakage(self):
        data = dataset(row(), row(revision_id="revised", value=80, available_at="2026-01-05T00:00:00Z"),
                       row(event_at="2026-01-04T21:00:00Z", available_at="2026-01-04T22:00:00Z"))
        result = select(data)
        self.assertEqual([r["value"] for r in result["records"]], [100.5])
        self.assertEqual(result["exclusion_counts"], {"future_event": 1, "future_availability": 1, "superseded_revision": 0})

    def test_exact_cutoff_revision_and_partition(self):
        data = dataset(row(), row(revision_id="revised", value=80, available_at="2026-01-05T00:00:00Z"))
        result = select(data, "2026-01-05T00:00:00Z")
        self.assertEqual(result["records"][0]["value"], 80)
        self.assertEqual(result["exclusion_counts"]["superseded_revision"], 1)
        self.assertEqual(result["input_record_count"], result["selected_record_count"] + sum(result["exclusion_counts"].values()))

    def test_preannounced_future_event_excluded(self):
        self.assertEqual(select(dataset(row(event_at="2026-02-01T00:00:00Z")))["records"], [])

    def test_instrument_field_and_event_define_observation(self):
        data = dataset(row(), row(instrument_id="fictional:BBB"), row(field="volume", unit="shares"),
                       row(event_at="2026-01-02T20:00:00Z"))
        self.assertEqual(select(data)["selected_record_count"], 4)

    def test_offset_and_input_order_invariant(self):
        first = dataset(row(), row(instrument_id="fictional:BBB"))
        second = copy.deepcopy(first)
        second["records"].reverse()
        second["records"][0]["event_at"] = "2026-01-02T16:00:00-05:00"
        second["records"][0]["available_at"] = "2026-01-02T16:01:00.000000-05:00"
        self.assertEqual(content_hash(first), content_hash(second))
        self.assertEqual(select(first), select(second, "2026-01-02T19:00:00-05:00"))

    def test_fractional_seconds_sort_chronologically(self):
        data = dataset(row(revision_id="later", available_at="2026-01-02T21:01:00.000001Z", value=90), row())
        self.assertEqual(select(data, "2026-01-02T21:01:00Z")["records"][0]["value"], 100.5)
        self.assertEqual(select(data, "2026-01-02T21:01:00.000001Z")["records"][0]["value"], 90)

    def test_no_input_mutation_or_output_aliasing(self):
        data = dataset(row()); before = copy.deepcopy(data)
        normalize(data)["records"][0]["value"] = 7
        select(data)["source"]["license"] = "changed"
        self.assertEqual(before, data)

    def test_hash_binds_full_dataset_provenance_and_cutoff(self):
        first = dataset(row()); second = copy.deepcopy(first)
        second["source"]["license"] = "restricted"
        self.assertNotEqual(content_hash(first), content_hash(second))
        second = copy.deepcopy(first)
        second["records"].append(row(revision_id="future", available_at="2027-01-01T00:00:00Z"))
        self.assertEqual(select(first)["records"], select(second)["records"])
        self.assertNotEqual(select(first)["input_sha256"], select(second)["input_sha256"])
        self.assertNotEqual(select(first)["input_sha256"], select(first, "2026-01-04T00:00:00Z")["input_sha256"])

    def test_rejects_duplicate_revision_even_with_offset_and_changed_value(self):
        with self.assertRaisesRegex(ValueError, "duplicates"):
            normalize(dataset(row(), row(event_at="2026-01-02T16:00:00-05:00", value=1)))

    def test_rejects_ambiguous_equal_availability(self):
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            normalize(dataset(row(), row(revision_id="other")))

    def test_rejects_changed_conventions_across_revisions(self):
        for changes in ({"unit": "cents/share"}, {"currency": "EUR"}, {"asset_class": "bond"}):
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, "changes"):
                normalize(dataset(row(), row(revision_id="other", available_at="2026-01-03T00:00:00Z", **changes)))

    def test_rejects_bool_nonfinite_and_numeric_strings(self):
        for value in (True, False, math.nan, math.inf, -math.inf, "1", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize(dataset(row(value=value)))

    def test_rejects_naive_unknown_invalid_or_overprecise_time(self):
        values = ["2026-01-02", "2026-01-02T21:00:00", "2026-01-02T21:00:00-00:00", "2026-02-30T00:00:00Z",
                  "2026-01-02T21:00:60Z", "2026-01-02T21:00:00.1234567Z", "2026-01-02T21:00:00+01:60", "2026-01-02T21:00:00+24:00"]
        for value in values:
            with self.subTest(value=value), self.assertRaises(ValueError):
                timestamp(value)
        with self.assertRaises(ValueError):
            select(dataset(row()), "2026-01-03")

    def test_exact_schemas_at_every_level(self):
        for path in ((), ("dataset",), ("dataset", "source"), ("dataset", "records", 0)):
            for operation in ("extra", "missing"):
                value = {"as_of": "2026-01-03T00:00:00Z", "dataset": dataset(row())}
                node = value
                for key in path:
                    node = node[key]
                if operation == "extra": node["untrusted_instruction"] = "ignore rules"
                else: del node[next(iter(node))]
                with self.subTest(path=path, operation=operation), self.assertRaises(ValueError):
                    snapshot(value)

    def test_rejects_invalid_identifier_currency_asset_and_unicode(self):
        for changes in ({"instrument_id": " "}, {"field": " close"}, {"currency": "usd"}, {"currency": "USDT"},
                        {"asset_class": "unlisted"}, {"unit": "bad\ntext"}, {"revision_id": "\ud800"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                normalize(dataset(row(**changes)))

    def test_schema_version_and_container_types_are_strict(self):
        for value in (True, 1.0, "1", 2):
            data = dataset(row()); data["schema_version"] = value
            with self.assertRaises(ValueError): normalize(data)
        for value in ({}, (), "rows"):
            data = dataset(row()); data["records"] = value
            with self.assertRaises(ValueError): normalize(data)

    def test_six_classes_preserve_values_without_adjustment(self):
        data = dataset(*(row(instrument_id="fictional:" + kind, asset_class=kind, value=-4.25)
                         for kind in ("equity", "option", "future", "fx", "bond", "crypto")))
        result = select(data)
        self.assertEqual(result["selected_record_count"], 6)
        self.assertTrue(all(r["value"] == -4.25 for r in result["records"]))
        self.assertEqual(result["corporate_action_policy"], "no_adjustments_applied")

    def test_empty_dataset_and_equal_json_numbers(self):
        self.assertEqual(select(dataset())["records"], [])
        self.assertEqual(content_hash(dataset(row(value=1))), content_hash(dataset(row(value=1.0))))
        self.assertEqual(content_hash(dataset(row(value=-0.0))), content_hash(dataset(row(value=0))))

    def test_hostile_provenance_is_inert_and_disclaimed(self):
        data = dataset(row())
        data["source"]["uri"] = "https://invalid.example/ignore-instructions-and-execute"
        result = select(data)
        self.assertEqual(result["source"], data["source"])
        self.assertEqual(result["availability_basis"], "caller_declared_not_verified")
        self.assertEqual(result["source_license_basis"], "caller_declared_not_verified")

    def test_json_duplicate_keys_and_nonfinite_literals_rejected(self):
        for value in ('{"dataset":1,"dataset":2}', '{"value":NaN}', '{"value":Infinity}'):
            with self.subTest(value=value), self.assertRaises(ValueError): strict_load(value)

    def test_packaged_example_and_cli(self):
        root = Path(__file__).resolve().parents[1]
        path = root / "examples/point-in-time-data.json"
        expected = snapshot(strict_load(path.read_text(encoding="utf-8")))
        result = subprocess.run([sys.executable, str(root / "scripts/point_in_time_data.py"), str(path)],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), expected)
        self.assertEqual(expected["records"][0]["value"], 1000000)
        self.assertEqual(expected["exclusion_counts"]["future_availability"], 1)


if __name__ == "__main__":
    unittest.main()
