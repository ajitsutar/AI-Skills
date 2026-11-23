"""Regression coverage for response field declarations supplied by the caller."""
import hashlib
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import response_contract
import test_strategy_answer as fixtures


class ResponseContractTests(unittest.TestCase):
    def test_original_clause_and_required_key_json(self):
        protocol = b"Write response.json containing `observations`, assumptions, and sources. Follow other instructions."
        self.assertEqual(response_contract.declared_fields(protocol), ["observations", "assumptions", "sources"])
        declaration = b'{"type":"object","required":["source tags","rows"]}'
        result = response_contract.audit(declaration, {"source tags": [], "rows": [{}]})
        self.assertEqual(result["contract_sha256"], hashlib.sha256(declaration).hexdigest())

    def test_ambiguous_duplicate_or_unsupported_contracts_fail(self):
        for text in (b"No field list.", b"response.json containing source or evidence.",
                     b"response.json with required fields source, source.", b'{"required":[]}',
                     b'{"required":["rows"],"additionalProperties":false}',
                     b"response.json containing a. response.json containing b."):
            with self.subTest(contract=text), self.assertRaises(ValueError):
                response_contract.declared_fields(text)

    def test_delivery_and_actual_readback_enforce_original(self):
        fixture = fixtures.StrategyAnswerTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        bundle = fixture.export()
        base = fixture.directory
        metadata, protocol = base / "declarations.json", base / "protocol.txt"
        metadata.write_text('{"notes":[]}', encoding="utf-8")
        protocol.write_text("Save response.json containing rows, notes and sources.", encoding="utf-8")
        destination = base / "delivery"
        with self.assertRaisesRegex(ValueError, "sources"):
            fixtures.contracts.deliver_strategy(bundle, metadata, destination, protocol)
        self.assertFalse(destination.exists())
        metadata.write_text('{"notes":[],"sources":["original observation"]}', encoding="utf-8")
        result = fixtures.contracts.deliver_strategy(bundle, metadata, destination, protocol)
        details = result["checks"]["response_contract"]
        self.assertEqual(details["required_fields_present"], ["rows", "notes", "sources"])
        self.assertEqual(details["contract_sha256"], hashlib.sha256(protocol.read_bytes()).hexdigest())
        first, rows = destination / "files/first-response.md", destination / "files/response.json"
        reviewed = fixtures.contracts.verify(bundle, first, rows, metadata, protocol)
        self.assertEqual(reviewed["checks"]["response_contract"], details)
        protocol.write_text("Save response.json containing rows, notes, sources and runtime.", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "runtime"):
            fixtures.contracts.verify(bundle, first, rows, metadata, protocol)
        self.assertEqual(json.loads(rows.read_bytes())["sources"], ["original observation"])


if __name__ == "__main__":
    unittest.main()
