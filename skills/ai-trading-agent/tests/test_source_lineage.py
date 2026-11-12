"""Synthetic lineage checks; no financial case answers or original data."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import source_lineage as subject


class SourceLineageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.original = {'issuer': 'Harbor Example', 'unit': 'EUR million',
                         'period': {'start': '2032-01-01', 'end': '2032-12-31'},
                         'scope': 'common holders', 'amount': 12, 'nullable': None,
                         'array': [True, 1.0], 'a/b': {'~': 'escaped'}}
        self.manifest = self.root / 'ingress.json'
        self.make_manifest(self.original)

    def make_manifest(self, document):
        raw = json.dumps(document).encode()
        (self.root / 'original.json').write_bytes(raw)
        manifest = {'schema_version': 1, 'sources': [{'id': 'original', 'path': 'original.json',
                    'sha256': hashlib.sha256(raw).hexdigest(), 'format': 'json'}]}
        self.manifest.write_text(json.dumps(manifest), encoding='utf-8')
        self.pin = subject.sha(self.manifest.read_bytes())

    def run_audit(self, target, required, mappings):
        return subject.audit(target, required, mappings, self.manifest, self.pin)

    def mapping(self, target='/unit', source='/unit', source_id='original'):
        return {'target_pointer': target, 'source_id': source_id, 'source_pointer': source}

    def test_original_leaf_matches_without_authenticating_semantics(self):
        result = self.run_audit({'currency_unit': 'EUR million'}, ['/currency_unit'],
                               [self.mapping('/currency_unit')])
        self.assertEqual(result['status'], 'IDENTITY_MATCHED')
        self.assertTrue(result['fields'][0]['eligible_as_original_leaf'])
        self.assertFalse(result['source_authenticity_verified'])
        self.assertFalse(result['semantic_scope_verified'])
        self.assertFalse(result['external_anchor_origin_verified'])

    def test_authored_request_role_does_not_make_metadata_original(self):
        target = {'role': 'Original supplied request', 'unit': 'USD', 'start': '2031-01-01'}
        report = self.run_audit(target, ['/unit', '/start'], [])
        self.assertEqual(report['status'], 'PARTIAL')
        self.assertTrue(all(not row['eligible_as_original_leaf'] for row in report['fields']))

    def test_wrong_original_value_is_invalid(self):
        report = self.run_audit({'unit': 'USD'}, ['/unit'], [self.mapping()])
        self.assertEqual(report['fields'][0]['reason'], 'ORIGINAL_VALUE_MISMATCH')

    def test_legitimate_original_request_remains_supported(self):
        original_request = {'jobs': [{'inputs': {'unit': 'JPY billion'}}]}
        self.make_manifest(original_request)
        result = self.run_audit(original_request, ['/jobs/0/inputs/unit'],
                               [self.mapping('/jobs/0/inputs/unit', '/jobs/0/inputs/unit')])
        self.assertEqual(result['status'], 'IDENTITY_MATCHED')

    def test_manifest_tamper_fails_before_analysis(self):
        self.manifest.write_text(self.manifest.read_text() + ' ', encoding='utf-8')
        with self.assertRaisesRegex(subject.LineageError, 'INGRESS_MANIFEST_HASH_MISMATCH'):
            self.run_audit({'unit': 'EUR million'}, ['/unit'], [self.mapping()])

    def test_original_tamper_fails_even_for_unselected_source(self):
        (self.root / 'original.json').write_text('{}', encoding='utf-8')
        with self.assertRaisesRegex(subject.LineageError, 'INGRESS_SOURCE_HASH_MISMATCH'):
            self.run_audit({'unit': 'EUR million'}, ['/unit'], [])

    def test_missing_original_and_missing_pointer_cannot_pass(self):
        for mapping in [self.mapping(source_id='authored'), self.mapping(source='/invented')]:
            with self.subTest(mapping=mapping):
                result = self.run_audit({'unit': 'EUR million'}, ['/unit'], [mapping])
                self.assertEqual(result['status'], 'INVALID')

    def test_boolean_and_integer_are_not_equivalent(self):
        result = self.run_audit({'flag': 1}, ['/flag'], [self.mapping('/flag', '/array/0')])
        self.assertEqual(result['fields'][0]['reason'], 'ORIGINAL_VALUE_MISMATCH')

    def test_integer_and_decimal_are_not_equivalent(self):
        result = self.run_audit({'flag': 1}, ['/flag'], [self.mapping('/flag', '/array/1')])
        self.assertEqual(result['fields'][0]['reason'], 'ORIGINAL_VALUE_MISMATCH')

    def test_null_original_is_unknown(self):
        result = self.run_audit({'unit': None}, ['/unit'], [self.mapping(source='/nullable')])
        self.assertEqual(result['status'], 'PARTIAL')
        self.assertEqual(result['fields'][0]['reason'], 'ORIGINAL_VALUE_NULL')

    def test_no_mapping_and_absent_target_is_unknown(self):
        result = self.run_audit({}, ['/unit'], [])
        self.assertEqual(result['fields'][0]['status'], 'UNKNOWN')

    def test_mapping_to_absent_target_is_invalid(self):
        self.assertEqual(self.run_audit({}, ['/unit'], [self.mapping()])['status'], 'INVALID')

    def test_json_pointer_escape(self):
        result = self.run_audit({'unit': 'escaped'}, ['/unit'], [self.mapping(source='/a~1b/~0')])
        self.assertEqual(result['status'], 'IDENTITY_MATCHED')
        with self.assertRaisesRegex(subject.LineageError, 'INVALID_JSON_POINTER_ESCAPE'):
            self.run_audit({'unit': 'escaped'}, ['/unit'], [self.mapping(source='/a~2b')])

    def test_object_inheritance_is_not_a_leaf_mapping(self):
        result = self.run_audit({'period': self.original['period']}, ['/period'],
                               [self.mapping('/period', '/period')])
        self.assertEqual(result['fields'][0]['reason'], 'TARGET_MUST_BE_LEAF')

    def test_duplicate_or_extra_mappings_fail(self):
        for mappings in [[self.mapping(), self.mapping()], [self.mapping('/unknown')]]:
            with self.assertRaises(subject.LineageError):
                self.run_audit({'unit': 'EUR million'}, ['/unit'], mappings)

    def test_no_authorship_or_transform_flag_accepted(self):
        for extra in [{'role': 'original'}, {'transform': 'identity'}, {'parent': '/unit'}]:
            with self.assertRaisesRegex(subject.LineageError, 'INVALID_IDENTITY_MAPPING'):
                self.run_audit({'unit': 'EUR million'}, ['/unit'], [{**self.mapping(), **extra}])

    def test_path_escape_fails(self):
        document = json.loads(self.manifest.read_text())
        document['sources'][0]['path'] = '../outside.json'
        self.manifest.write_text(json.dumps(document), encoding='utf-8')
        self.pin = subject.sha(self.manifest.read_bytes())
        with self.assertRaisesRegex(subject.LineageError, 'INGRESS_SOURCE_PATH_ESCAPE'):
            self.run_audit({}, ['/unit'], [])

    def test_json_duplicate_keys_and_nonfinite_rejected(self):
        for raw in ['{"a":1,"a":2}', '{"a":NaN}']:
            with self.assertRaises(subject.LineageError):
                subject.parse(raw)

    def test_cli_exact_decimal_preservation_and_no_overwrite(self):
        self.make_manifest({'amount': 1.25})
        (self.root / 'target.json').write_text('{"amount":1.25}', encoding='utf-8')
        (self.root / 'mappings.json').write_text(json.dumps([self.mapping('/amount', '/amount')]), encoding='utf-8')
        (self.root / 'required.json').write_text('["/amount"]', encoding='utf-8')
        args = ['--manifest', str(self.manifest), '--manifest-sha256', self.pin,
                '--target', str(self.root/'target.json'), '--mappings', str(self.root/'mappings.json'),
                '--required-pointers', str(self.root/'required.json'), '--output', str(self.root/'report.json')]
        self.assertEqual(subject.main(args), 0)
        self.assertEqual(json.loads((self.root/'report.json').read_text())['status'], 'IDENTITY_MATCHED')
        with self.assertRaisesRegex(subject.LineageError, 'OUTPUT_ALREADY_EXISTS'):
            subject.main(args)

    def test_reit_wrapper_masks_only_unproven_metadata_preserving_amounts(self):
        document = {'ffo_bridge': {'basis': {'amount_unit': 'EUR million',
                     'period_start': '2031-01-01', 'period_end': '2032-12-31',
                     'holder_basis': 'common holders'}, 'net_income': 14},
                    'property_fractions': [{'value': 0.82, 'denominator': 'area', 'time_anchor': None}]}
        preserved = deepcopy(document)
        mappings = [self.mapping('/document/ffo_bridge/basis/amount_unit', '/unit'),
                    self.mapping('/document/ffo_bridge/basis/period_end', '/period/end')]
        report = subject.reit_metadata_audit(document, mappings, self.manifest, self.pin)
        result = report['original_lineage_document']
        self.assertEqual(document, preserved)
        self.assertEqual(result['ffo_bridge']['net_income'], 14)
        self.assertEqual(result['ffo_bridge']['basis']['amount_unit'], 'EUR million')
        self.assertEqual(result['ffo_bridge']['basis']['period_end'], '2032-12-31')
        self.assertIsNone(result['ffo_bridge']['basis']['period_start'])
        self.assertIsNone(result['ffo_bridge']['basis']['holder_basis'])
        self.assertEqual(result['property_fractions'][0]['value'], 0.82)
        self.assertIsNone(result['property_fractions'][0]['denominator'])
        self.assertEqual(report['status'], 'PARTIAL')
        self.assertEqual(report['declared_document'], preserved)


if __name__ == '__main__':
    unittest.main()
