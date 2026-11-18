"""Portable metadata boundaries and exact original JSON evidence."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import source_metadata_fitness as module


def historical():
    return {'history_range': ['2017-03-01', '2020-02-28'],
            'roster_snapshot_at': '2022-04-07T16:00:00+02:00',
            'constituents': ['ALPHA', 'BETA'],
            'revised_download_at': '2023-06-08T09:30:00Z',
            'row_first_available_at': None}


class MetadataFitnessTests(unittest.TestCase):
    def audit(self, document=None, raw=None, ref=True):
        if raw is None:
            raw = json.dumps(document if document is not None else {'clock': '2024-02-03T00:00:00Z',
                                                                      'context': historical()}).encode()
        source = {'raw': raw, 'sha256': hashlib.sha256(raw).hexdigest(), 'format': 'json',
                  'path': 'renamed/context-original.json'}
        corpus = SimpleNamespace(sources={'arbitrary-source': source})
        reference = {'source_id': 'arbitrary-source', 'pointer': '/clock'} if ref else None
        return module.audit_bound_context(corpus, reference)

    def test_historical_limits_source_bound_without_actual_bias_claim(self):
        result = self.audit(); row = result['descriptors'][0]
        self.assertEqual(row['profile'], 'HISTORICAL_DESCRIPTOR_V1')
        self.assertEqual(row['fields']['row_first_available_at']['state'], 'NULL')
        self.assertEqual(row['fields']['revision_vintages']['state'], 'ABSENT')
        meanings = ' '.join(f['meaning'] for f in row['findings'])
        for phrase in ['conditioned on the supplied roster', 'row-level availability', 'earlier decision-time']:
            self.assertIn(phrase, meanings)
        self.assertFalse(result['no_lookahead_verified'])
        self.assertFalse(result['whole_request_completeness_verified'])
        self.assertEqual(row['fields']['history_range']['source_ref']['pointer'], '/context/history_range')

    def test_renamed_parents_nested_lists_multiple_and_escaped_pointers(self):
        second = {'history_range': ['2014-01-01', '2015-01-01'], 'revised_download_at': None}
        result = self.audit({'clock': '2024-02-03T00:00:00Z', 'renamed/~': [historical(), second]})
        self.assertEqual([r['source_ref']['pointer'] for r in result['descriptors']], ['/renamed~1~0/0', '/renamed~1~0/1'])
        self.assertEqual(result['traversal']['descriptors_recognized'], 2)

    def test_present_declarations_never_certify_dataset(self):
        data = historical()
        data.update(row_first_available_at={'rows': ['retained declaration']},
                    historical_membership=[{'member': 'ALPHA'}], revision_vintages=[{'vintage': 'retained'}])
        result = self.audit({'clock': '2024-02-03T00:00:00Z', 'data': data})
        self.assertEqual(result['status'], 'DECLARATIONS_PRESENT_UNVERIFIED')
        for target in [result, result['descriptors'][0]]:
            for key in module.CERTIFICATIONS: self.assertIs(target[key], False)
        text = json.dumps(result)
        self.assertNotIn('cannot be reconstructed', text)
        self.assertIn('does not reconstruct or establish', text)

    def test_absent_null_empty_false_true_distinct(self):
        variants = [('ABSENT', ...), ('NULL', None), ('EMPTY_DECLARATION', ''),
                    ('EMPTY_DECLARATION', []), ('EMPTY_DECLARATION', {}),
                    ('UNSUPPORTED_STRUCTURE', False), ('UNSUPPORTED_STRUCTURE', True)]
        for expected, value in variants:
            with self.subTest(value=value):
                data = historical(); data.pop('row_first_available_at')
                if value is not ...: data['row_first_available_at'] = value
                row = self.audit({'clock': '2024-02-03T00:00:00Z', 'data': data})['descriptors'][0]['fields']['row_first_available_at']
                self.assertEqual(row['state'], expected)
                self.assertEqual(row['source_pointer_exists'], value is not ...)
                if value is ...: self.assertNotIn('original_json', row)
                else: self.assertEqual(json.loads(row['original_json']), value)
                if type(value) is bool: self.assertIn('TRUE' if value else 'FALSE', row['detail'])

    def test_malformed_presence_still_recognized(self):
        for field, value, expected in [('history_range', ['2021-01-01', '2018-01-01'], 'MALFORMED'),
              ('history_range', ['not-a-date', '2020-01-01'], 'MALFORMED'),
              ('roster_snapshot_at', '2020-01-01', 'INSUFFICIENT_PRECISION'),
              ('revised_download_at', '2020-01-01T12:00:00', 'INSUFFICIENT_PRECISION'),
              ('constituents', ['ALPHA', 'ALPHA'], 'MALFORMED'),
              ('constituents', [3], 'MALFORMED'), ('historical_membership', True, 'UNSUPPORTED_STRUCTURE'),
              ('revision_vintages', 12, 'MALFORMED')]:
            with self.subTest(field=field, value=value):
                data = historical(); data[field] = value
                result = self.audit({'clock': '2024-02-03T00:00:00Z', 'data': data})
                self.assertEqual(len(result['descriptors']), 1)
                self.assertEqual(result['descriptors'][0]['fields'][field]['state'], expected)
                self.assertEqual(result['status'], 'PARTIAL_OR_MALFORMED_METADATA')

    def test_global_availability_timestamp_does_not_establish_row_knowledge(self):
        data = historical(); data['row_first_available_at'] = '2021-01-02T00:00:00Z'
        row = self.audit({'clock': '2024-02-03T00:00:00Z', 'x': data})['descriptors'][0]
        self.assertEqual(row['fields']['row_first_available_at']['detail'], 'GLOBAL_TIMESTAMP_NOT_PER_ROW_KNOWLEDGE')
        self.assertFalse(row['no_lookahead_verified'])

    def test_no_anchor_and_no_profile_do_not_search_or_certify(self):
        result = self.audit(ref=False)
        self.assertEqual(result['status'], 'NO_BOUND_CONTEXT'); self.assertEqual(result['descriptors'], [])
        result = self.audit({'clock': '2024-02-03T00:00:00Z', 'history_range': ['2010', '2011'],
                             'downloaded_at': '2024-02-03T00:00:00Z'})
        self.assertEqual(result['status'], 'NO_SUPPORTED_DESCRIPTOR')
        self.assertFalse(result['point_in_time_complete_certified'])

    def test_unrelated_download_not_revision_event(self):
        data = historical(); data.pop('revised_download_at'); data['downloaded_at'] = '2024-01-01T00:00:00Z'
        row = self.audit({'clock': '2024-02-03T00:00:00Z', 'x': data})['descriptors'][0]
        self.assertEqual(row['fields']['revised_download_at']['state'], 'ABSENT')
        self.assertIn('/x/downloaded_at', row['unassessed_field_pointers'])
        self.assertNotIn('REVISION_AWARE_HISTORY_NOT_ESTABLISHED', [f['code'] for f in row['findings']])

    def test_numeric_tokens_and_types_lossless_even_nested_malformed(self):
        tokens = ['1e-410', '1e410', '0.12345678901234567890123456789',
                  '900719925474099312345678901', '-0', '-0.00e+0']
        for token in tokens:
            with self.subTest(token=token):
                raw = ('{"clock":"2024-02-03T00:00:00Z","x":{"history_range":' + token +
                       ',"roster_snapshot_at":null,"revision_vintages":[{"value":' + token + '}],'
                       '"row_first_available_at":"' + token + '"}}').encode()
                row = self.audit(raw=raw)['descriptors'][0]
                field = row['fields']['history_range']
                self.assertEqual(field['original_json'], token)
                self.assertEqual(field['original_value_kind'], 'number'); self.assertNotIn('original_value', field)
                nested = row['fields']['revision_vintages']['original_json']
                self.assertIn(token, nested)
                parsed = json.loads(nested, parse_float=lambda x: ('number', x), parse_int=lambda x: ('number', x))
                self.assertEqual(parsed[0]['value'], ('number', token))
                self.assertEqual(json.loads(row['fields']['row_first_available_at']['original_json']), token)
                json.dumps(row, allow_nan=False)  # No custom token objects leak to strict report encoding.

    def test_duplicate_keys_nonfinite_and_invalid_source_reference_rejected(self):
        for raw in [b'{"clock":"x","clock":"y"}', b'{"clock":"x","a":NaN}']:
            with self.subTest(raw=raw), self.assertRaises(ValueError): self.audit(raw=raw)
        corpus = SimpleNamespace(sources={})
        for ref in [{'source_id': 'missing', 'pointer': ''}, {'source_id': 'missing', 'pointer': '', 'override': 1}]:
            with self.assertRaises(ValueError): module.audit_bound_context(corpus, ref)

    def test_traversal_depth_nodes_descriptors_explicit_partial(self):
        for bound, limit, document, reason in [
            ('MAX_DEPTH', 1, {'clock': 'x', 'a': {'b': historical()}}, 'MAX_DEPTH'),
            ('MAX_NODES', 2, {'clock': 'x', 'a': historical()}, 'MAX_NODES'),
            ('MAX_DESCRIPTORS', 1, {'clock': 'x', 'a': [historical(), historical()]}, 'MAX_DESCRIPTORS')]:
            with self.subTest(bound=bound), patch.object(module, bound, limit):
                result = self.audit(document)
                self.assertEqual(result['status'], 'PARTIAL_METADATA_AUDIT')
                self.assertTrue(result['traversal']['traversal_truncated'])
                self.assertIn(reason, [r['reason'] for r in result['skipped_scopes']])

    def test_field_and_inventory_bounds_are_visible_partial(self):
        with patch.object(module, 'MAX_FIELD_JSON_BYTES', 8):
            result = self.audit()
            field = result['descriptors'][0]['fields']['history_range']
            self.assertEqual(field['projection_status'], 'NOT_PROJECTED_BOUND')
            self.assertNotIn('original_json', field)
            self.assertEqual(result['status'], 'PARTIAL_OR_MALFORMED_METADATA')
        data = historical(); data.update(extra_a=1, extra_b=2, extra_c=3)
        with patch.object(module, 'MAX_SCOPE_INVENTORY', 1):
            result = self.audit({'clock': 'x', 'a': data})
            row = result['descriptors'][0]
            self.assertEqual(row['unassessed_field_count'], 3)
            self.assertEqual(len(row['unassessed_field_pointers']), 1)
            self.assertTrue(row['unassessed_inventory_truncated'])
            self.assertEqual(row['status'], 'PARTIAL_OR_MALFORMED_METADATA')
            self.assertEqual(result['status'], 'PARTIAL_METADATA_AUDIT')

    def test_import_order_entrypoints_no_cycle(self):
        for first in ['supplied_research', 'final_report', 'request_coverage', 'market_sources_report']:
            code = ('import sys; sys.path.insert(0, ' + repr(str(SCRIPTS)) + '); import ' + first +
                    '; import source_metadata_fitness as m; m.exact_codec()')
            completed = subprocess.run([sys.executable, '-X', 'utf8', '-B', '-c', code], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == '__main__': unittest.main()
