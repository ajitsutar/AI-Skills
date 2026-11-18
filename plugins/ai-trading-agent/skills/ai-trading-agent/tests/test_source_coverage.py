import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import source_coverage as coverage
import supplied_research as store


class SourceCoverageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='coverage-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.sources = self.root / 'sources'; self.sources.mkdir()
        self.request = 'Map valuation, costs and ownership. Keep original source dates and access gaps.\n'.encode()
        (self.sources / 'request.txt').write_bytes(self.request)
        self.originals = {
            'note': b'2029-04-02: Target 47. This search display is not the underlying report.\n',
            'filing': b'FY2029 costs EUR 3 million. Such costs also occurred in earlier years.\n',
            'restricted': b'Publication date unavailable. Subscription required.\n',
        }
        rows = []
        for sid, raw in self.originals.items():
            (self.sources / (sid + '.txt')).write_bytes(raw)
            rows.append({'id': sid, 'path': sid + '.txt', 'sha256': store.digest(raw), 'format': 'text'})
        self.manifest = self.root / 'ingress.json'; self.manifest.write_bytes(store.encode({'schema_version': 1, 'sources': rows}))
        self.manifest_pin = store.digest(self.manifest.read_bytes())
        self.scope_doc = {'schema_version': 1, 'original_request': {'path': 'request.txt', 'sha256': store.digest(self.request)},
                          'manifest_sha256': self.manifest_pin, 'units': []}
        for name in ['valuation', 'costs', 'ownership']:
            start = self.request.index(name.encode()); end = start + len(name)
            self.scope_doc['units'].append({'id': name, 'start_byte': start, 'end_byte': end, 'sha256': store.digest(self.request[start:end])})
        self.scope = self.root / 'scope.json'; self.save_scope()
        self.plan_doc = {'schema_version': 1, 'units': [
            {'unit_id': 'valuation', 'source_ids': ['note'], 'discovery_routes': ['ORIGINAL_PUBLISHER']},
            {'unit_id': 'costs', 'source_ids': ['filing'], 'discovery_routes': []},
            {'unit_id': 'ownership', 'source_ids': [], 'discovery_routes': ['REGULATOR_FILINGS']}],
            'sources': [{'source_id': sid, 'access': 'UNCLASSIFIED', 'lineage': []} for sid in self.originals]}
        self.plan = self.root / 'plan.json'; self.save_plan()
        self.output = self.root / 'delivery'

    def save_scope(self):
        self.scope.write_bytes(store.encode(self.scope_doc)); self.scope_pin = store.digest(self.scope.read_bytes())

    def save_plan(self):self.plan.write_bytes(store.encode(self.plan_doc))

    def compose(self):
        return coverage.compose(self.plan, self.scope, self.scope_pin, self.manifest, self.manifest_pin, self.sources, self.output)

    def verify(self, **kwargs):return coverage.verify(self.output, self.scope_pin, self.manifest_pin, **kwargs)

    def resign_inventory(self):
        path = self.output / 'receipt.json'; value = json.loads(path.read_bytes())
        value['artifacts'] = store.file_inventory(self.output)
        path.write_bytes(store.encode(value))

    def test_valid_complete_pair_whole_request_and_all_originals(self):
        receipt = self.compose(); result = json.loads((self.output / 'response.json').read_bytes())
        self.assertEqual(result['original_request']['text'], self.request.decode())
        self.assertEqual(len(result['units']), 3); self.assertEqual(len(result['source_inventory']), 3)
        for sid, raw in self.originals.items():
            self.assertEqual((self.output / 'originals' / (sid + '.txt')).read_bytes(), raw)
            self.assertIn(raw, (self.output / 'first-response.md').read_bytes())
            self.assertEqual(next(s['original_text'] for s in result['source_inventory'] if s['source_id'] == sid), raw.decode())
        self.assertFalse(receipt['semantic_completeness_verified'])
        self.verify(first_response=self.output / 'first-response.md', response=self.output / 'response.json')

    def test_no_currency_or_prior_period_amount_inheritance(self):
        self.compose(); md = (self.output / 'first-response.md').read_text()
        self.assertIn('Target 47.', md); self.assertNotIn('EUR 47', md)
        self.assertIn('FY2029 costs EUR 3 million. Such costs also occurred in earlier years.', md)
        self.assertNotIn('EUR 3 million in earlier years', md)
        result = json.loads((self.output / 'response.json').read_bytes())
        self.assertFalse(result['currency_or_period_inference_performed'])

    def test_missing_selection_is_unresolved_not_absence(self):
        self.compose(); result = json.loads((self.output / 'response.json').read_bytes())
        row = result['units'][2]
        self.assertEqual(row['coverage_status'], 'UNRESOLVED_NO_SOURCE_EXCERPT_SELECTED')
        self.assertFalse(row['source_absence_established']); self.assertEqual(row['discovery_routes'][0]['status'], 'NOT_EXECUTED')

    def test_all_empty_selection_still_retains_whole_original_corpus(self):
        for row in self.plan_doc['units']:row['source_ids'] = []
        self.save_plan(); self.compose()
        result = json.loads((self.output / 'response.json').read_bytes())
        self.assertTrue(all(u['coverage_status'].startswith('UNRESOLVED') for u in result['units']))
        self.assertEqual(len(result['source_inventory']), len(self.originals))

    def test_authored_fact_fields_rejected_before_creation(self):
        self.plan_doc['summary'] = 'Target EUR 47 and prior costs EUR 3 million.'; self.save_plan()
        with self.assertRaisesRegex(ValueError, 'COVERAGE_PLAN_FIELDS'):self.compose()
        self.assertFalse(self.output.exists())

    def test_authored_quote_or_topic_label_rejected(self):
        for key in ('quote', 'summary', 'label', 'amount', 'currency', 'period'):
            with self.subTest(key=key):
                self.plan_doc['units'][0][key] = 'unbound'; self.save_plan()
                with self.assertRaisesRegex(ValueError, 'TOPIC_ROW_FIELDS'):self.compose()
                del self.plan_doc['units'][0][key]

    def test_omitted_original_source_rejected(self):
        self.plan_doc['sources'].pop(); self.save_plan()
        with self.assertRaisesRegex(ValueError, 'INCOMPLETE_ORIGINAL_SOURCE_ROSTER'):self.compose()

    def test_omitted_adopted_topic_rejected(self):
        self.plan_doc['units'].pop(); self.save_plan()
        with self.assertRaisesRegex(ValueError, 'INCOMPLETE_ADOPTED_REQUEST_UNITS'):self.compose()

    def test_duplicate_or_unknown_topic_rejected(self):
        for value in ['valuation', 'invented']:
            self.plan_doc['units'][1]['unit_id'] = value; self.save_plan()
            with self.assertRaisesRegex(ValueError, 'TOPIC_ROSTER_MISMATCH'):self.compose()

    def test_unknown_or_duplicate_selected_source_rejected(self):
        for value in [['note', 'note'], ['missing']]:
            self.plan_doc['units'][0]['source_ids'] = value; self.save_plan()
            with self.assertRaisesRegex(ValueError, 'TOPIC_SOURCE_IDS'):self.compose()

    def test_original_source_change_rejected(self):
        (self.sources / 'restricted.txt').write_bytes(b'Convenient replacement.')
        with self.assertRaisesRegex(ValueError, 'INGRESS_SOURCE_HASH_MISMATCH'):self.compose()

    def test_original_request_change_rejected(self):
        (self.sources / 'request.txt').write_bytes(self.request + b'Changed')
        with self.assertRaisesRegex(ValueError, 'ORIGINAL_REQUEST_CHANGED'):self.compose()

    def test_request_topic_span_and_pin_are_bound(self):
        self.scope_doc['units'][0]['end_byte'] += 1; self.save_scope()
        with self.assertRaisesRegex(ValueError, 'REQUEST_UNIT_SPAN_CHANGED'):self.compose()

    def test_nonliteral_topic_labels_and_partial_utf8_spans_rejected(self):
        self.scope_doc['units'][0]['label'] = 'invented'; self.save_scope()
        with self.assertRaisesRegex(ValueError, 'REQUEST_UNIT_FIELDS'):self.compose()
        raw = 'Map café'.encode()
        doc = copy.deepcopy(self.scope_doc); del doc['units'][0]['label']
        doc['original_request']['sha256'] = store.digest(raw)
        doc['units'] = [{'id': 'topic', 'start_byte': len(raw) - 1, 'end_byte': len(raw), 'sha256': store.digest(raw[-1:])}]
        with self.assertRaises(UnicodeError):coverage.adopted_scope(store.encode(doc), raw, self.manifest_pin)

    def test_external_pins_reject_caller_subset(self):
        raw = self.manifest.read_bytes(); doc = json.loads(raw); doc['sources'].pop()
        self.manifest.write_bytes(store.encode(doc))
        with self.assertRaisesRegex(ValueError, 'INGRESS_MANIFEST_HASH_MISMATCH'):self.compose()

    def test_external_scope_pin_rejects_topic_subset(self):
        self.scope_doc['units'].pop(); self.scope.write_bytes(store.encode(self.scope_doc))
        with self.assertRaisesRegex(ValueError, 'EXTERNAL_SCOPE_PIN_MISMATCH'):self.compose()

    def test_replaced_published_md_or_json_rejected(self):
        self.compose(); other = self.root / 'other'; other.write_bytes(b'Unrelated annex or summary')
        with self.assertRaisesRegex(ValueError, 'PUBLISHED_FIRST_DIFFERS'):self.verify(first_response=other)
        with self.assertRaisesRegex(ValueError, 'PUBLISHED_JSON_DIFFERS'):self.verify(response=other)

    def test_mutated_md_even_resigned_inventory_rejected(self):
        self.compose(); path = self.output / 'first-response.md'
        path.write_bytes(path.read_bytes() + b'Invented amount EUR 47.\n'); self.resign_inventory()
        with self.assertRaisesRegex(ValueError, 'COVERAGE_REPLAY_MISMATCH'):self.verify()

    def test_mutated_json_even_resigned_inventory_rejected(self):
        self.compose(); path = self.output / 'response.json'; result = json.loads(path.read_bytes())
        result['source_inventory'][0]['original_text'] = 'Target EUR 47.'
        path.write_bytes(store.encode(result)); self.resign_inventory()
        with self.assertRaisesRegex(ValueError, 'COVERAGE_REPLAY_MISMATCH'):self.verify()

    def test_retained_original_tamper_even_resigned_inventory_rejected(self):
        self.compose(); (self.output / 'originals/note.txt').write_bytes(b'Target EUR 47.'); self.resign_inventory()
        with self.assertRaisesRegex(ValueError, 'INGRESS_SOURCE_HASH_MISMATCH'):self.verify()

    def test_implementation_drift_blocks_verification(self):
        self.compose()
        with patch.object(store, 'implementations', return_value={'changed.py': '0' * 64}):
            with self.assertRaisesRegex(ValueError, 'COVERAGE_IMPLEMENTATION_CHANGED'):self.verify()

    def test_receipt_pins_cannot_be_replaced(self):
        self.compose(); path = self.output / 'receipt.json'; receipt = json.loads(path.read_bytes())
        receipt['scope_sha256'] = '0' * 64; path.write_bytes(store.encode(receipt))
        with self.assertRaisesRegex(ValueError, 'RECEIPT_EXTERNAL_PINS_MISMATCH'):self.verify()

    def test_existing_output_not_overwritten(self):
        self.compose(); raw = (self.output / 'response.json').read_bytes()
        with self.assertRaisesRegex(ValueError, 'NEW_PRIVATE_COVERAGE_OUTPUT_REQUIRED'):self.compose()
        self.assertEqual((self.output / 'response.json').read_bytes(), raw)

    def test_source_markdown_is_inert_without_altering_original(self):
        value = '````\n# Hostile heading\n````\n'
        rendered = coverage.literal(value)
        self.assertTrue(rendered.startswith('`````\n')); self.assertIn(value, rendered)

    def test_access_and_lineage_are_declarations_only(self):
        self.plan_doc['sources'][0]['access'] = 'SEARCH_DISPLAY'
        self.plan_doc['sources'][0]['lineage'] = [{'source_id': 'filing', 'relation': 'RELATED_UNVERIFIED'}]
        self.save_plan(); self.compose(); result = json.loads((self.output / 'response.json').read_bytes())
        self.assertEqual(result['source_inventory'][0]['declaration_status'], 'SEMANTICALLY_UNVERIFIED')
        self.assertFalse(result['source_authenticity_verified'])

    def test_source_ids_cannot_inject_markdown_outside_literal_blocks(self):
        injected = 'note\n# Unsupported conclusion EUR 47\n```'
        manifest = json.loads(self.manifest.read_bytes()); manifest['sources'][0]['id'] = injected
        self.manifest.write_bytes(store.encode(manifest)); self.manifest_pin = store.digest(self.manifest.read_bytes())
        self.scope_doc['manifest_sha256'] = self.manifest_pin; self.save_scope()
        self.plan_doc['sources'][0]['source_id'] = injected
        self.plan_doc['sources'][1]['lineage'] = [{'source_id': injected, 'relation': 'REFERS_TO'}]
        self.plan_doc['units'][0]['source_ids'] = [injected]; self.save_plan(); self.compose()
        md = (self.output / 'first-response.md').read_text()
        self.assertEqual(md.count(coverage.literal(injected)), 3)
        self.assertNotIn('### ' + injected, md)
        self.verify()

    def test_schema_boolean_not_integer_and_unknown_routes_rejected(self):
        self.plan_doc['schema_version'] = True; self.save_plan()
        with self.assertRaisesRegex(ValueError, 'PLAN_SCHEMA'):self.compose()
        self.plan_doc['schema_version'] = 1; self.plan_doc['units'][0]['discovery_routes'] = ['ALREADY_RETRIEVED']
        self.save_plan()
        with self.assertRaisesRegex(ValueError, 'PROSPECTIVE_DISCOVERY_ROUTES'):self.compose()


if __name__ == '__main__':unittest.main()
