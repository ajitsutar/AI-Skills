"""Offline evidence semantics, not live broker or independent receipt validation."""
import copy
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import platform_readiness as p


def request(asset='stocks', mode='live'):
    return {'asset_class': asset, 'mode': mode, 'scope_id': 'fictional-scope',
            'scope_description': 'Fictional bounded test only; no account or observed broker.'}


def packet(asset='stocks', mode='live'):
    return {'schema_version': 1, 'as_of': '2026-10-23T12:00:00Z',
            'host': {'id': 'fictional-host', 'package_sha256': 'a' * 64, 'runtime_sha256': 'b' * 64},
            'requests': [request(asset, mode)], 'evidence': [], 'documentation': []}


def receipt(document, kind, capability=None):
    scope = document['requests'][0]
    r = {'kind': kind, 'host_id': document['host']['id'], 'asset_class': scope['asset_class'],
         'mode': scope['mode'], 'scope_id': scope['scope_id'], 'scope_sha256': p.digest(scope),
         'observed_at': '2026-10-23T10:00:00Z', 'valid_until': '2026-10-24T10:00:00Z',
         'package_sha256': document['host']['package_sha256'], 'runtime_sha256': document['host']['runtime_sha256'],
         'capability_sha256': capability, 'artifact_ref': 'fictional-test:' + kind,
         'checks': [{'id': name, 'outcome': 'pass', 'evidence_ref': 'fictional-test:' + name}
                    for name in p.required_checks(kind, scope['asset_class'])]}
    if kind == 'host_capability':
        schema = {'type': 'object', 'properties': {}, 'additionalProperties': False}
        r.update(capability_status='supported', tools=[{'name': 'fictional_host_tool',
                 'operations': list(p.OPERATIONS), 'input_schema': schema, 'schema_sha256': p.digest(schema)}])
    return {'id': kind, 'receipt': r, 'receipt_sha256': p.digest(r)}


def sealed(record):
    record['receipt_sha256'] = p.digest(record['receipt'])
    return record


def complete(asset='stocks', mode='live'):
    doc = packet(asset, mode)
    cap = receipt(doc, 'host_capability') if mode != 'research' else None
    if cap:
        doc['evidence'].append(cap)
    for kind in p.required_categories(mode):
        if kind != 'host_capability':
            doc['evidence'].append(receipt(doc, kind, cap['receipt_sha256'] if cap else None))
    return doc


class PlatformReadinessTests(unittest.TestCase):
    def status(self, doc):
        return p.assess(doc)['results'][0]

    def test_all_assets_and_modes_have_distinct_complete_catalogs(self):
        for asset in p.ASSETS:
            for mode in p.MODES:
                with self.subTest(asset=asset, mode=mode):
                    out = p.assess(complete(asset, mode))
                    self.assertTrue(out['catalog_evidence_complete'])
                    self.assertEqual(out['results'][0]['evidence_status'], 'EVIDENCE_QUALIFIED_CONDITIONAL')
                    self.assertEqual(out['results'][0]['readiness_claim'], 'NOT_ESTABLISHED_BY_THIS_ASSESSOR')
                    self.assertFalse(out['execution_authorized'])
                    self.assertFalse(out['enforces_execution'])

    def test_missing_catalog_is_unverified_not_unsupported(self):
        out = self.status(packet())
        self.assertEqual(out['evidence_status'], 'UNVERIFIED')
        self.assertFalse(out['catalog_evidence_complete'])
        self.assertEqual(len(out['missing_or_failed_categories']), len(p.REQUIRED['live']))

    def test_documentation_cannot_qualify_or_deny_host(self):
        for support in ('documented', 'documented_unsupported', 'not_documented'):
            doc = packet()
            doc['documentation'] = [{'id': 'doc', 'host_id': 'fictional-host', 'asset_classes': ['stocks'],
                                     'modes': ['live'], 'observed_at': doc['as_of'],
                                     'source_url': 'https://example.org/documentation', 'summary': 'Fictional.', 'support': support}]
            out = self.status(doc)
            self.assertEqual(out['evidence_status'], 'UNVERIFIED')
            self.assertFalse(out['documentation_context'][0]['qualifies_host'])

    def test_future_document_retained_but_identified(self):
        doc = packet()
        doc['documentation'] = [{'id': 'd', 'host_id': 'fictional-host', 'asset_classes': ['stocks'],
                                  'modes': ['live'], 'observed_at': '2099-01-01T00:00:00Z',
                                  'source_url': 'https://example.org', 'summary': 'Fictional.', 'support': 'documented'}]
        self.assertTrue(self.status(doc)['documentation_context'][0]['future_relative_to_assessment'])

    def test_current_unsupported_receipt_scoped_and_expiring(self):
        doc = packet()
        cap = receipt(doc, 'host_capability')
        cap['receipt'].update(capability_status='unsupported', tools=[])
        doc['evidence'] = [sealed(cap)]
        self.assertEqual(self.status(doc)['evidence_status'], 'UNSUPPORTED_IN_SUPPLIED_HOST_OBSERVATION')
        doc['as_of'] = cap['receipt']['valid_until']
        self.assertEqual(self.status(doc)['evidence_status'], 'UNVERIFIED')

    def test_unsupported_documentation_is_not_permanent_asset_denial(self):
        doc = complete('futures')
        self.assertTrue(self.status(doc)['catalog_evidence_complete'])

    def test_incomplete_negative_observation_does_not_deny(self):
        doc = packet()
        cap = receipt(doc, 'host_capability')
        cap['receipt'].update(capability_status='unsupported', checks=[])
        doc['evidence'] = [sealed(cap)]
        self.assertEqual(self.status(doc)['evidence_status'], 'UNVERIFIED')

    def test_both_supported_and_unsupported_remain_conflict(self):
        doc = complete()
        negative = receipt(doc, 'host_capability')
        negative['id'] = 'negative'
        negative['receipt'].update(capability_status='unsupported', tools=[])
        doc['evidence'].append(sealed(negative))
        self.assertEqual(self.status(doc)['evidence_status'], 'CONFLICTING_EVIDENCE')
        self.assertFalse(self.status(doc)['catalog_evidence_complete'])

    def test_failed_attempt_is_not_hidden_by_passing_attempt(self):
        doc = complete()
        bad = copy.deepcopy(next(r for r in doc['evidence'] if r['id'] == 'restart_recovery'))
        bad['id'] = 'failed-restart'
        bad['receipt']['checks'][0]['outcome'] = 'fail'
        doc['evidence'].append(sealed(bad))
        out = self.status(doc)
        self.assertEqual(out['evidence_status'], 'CONFLICTING_EVIDENCE')
        self.assertIn('failed-restart', out['conflicts'][0]['failed_receipts'])

    def test_partial_checks_do_not_qualify(self):
        doc = complete()
        r = next(r for r in doc['evidence'] if r['id'] == 'order_identity')
        r['receipt']['checks'].pop()
        sealed(r)
        self.assertFalse(self.status(doc)['catalog_evidence_complete'])

    def test_self_declared_ready_boolean_rejected(self):
        doc = packet()
        doc['production_ready'] = True
        with self.assertRaisesRegex(ValueError, 'EXACT_FIELDS'):
            p.assess(doc)
        doc = complete()
        doc['evidence'][1]['receipt']['checks'][0]['outcome'] = True
        sealed(doc['evidence'][1])
        with self.assertRaisesRegex(ValueError, 'CHECK_OUTCOME'):
            p.assess(doc)

    def test_hash_bound_receipt_and_schema_reject_tampering(self):
        doc = complete()
        doc['evidence'][1]['receipt']['artifact_ref'] += '-changed'
        with self.assertRaisesRegex(ValueError, 'RECEIPT_HASH_MISMATCH'):
            p.assess(doc)
        doc = complete()
        doc['evidence'][0]['receipt']['tools'][0]['input_schema']['title'] = 'changed'
        sealed(doc['evidence'][0])
        with self.assertRaisesRegex(ValueError, 'TOOL_SCHEMA_HASH_MISMATCH'):
            p.assess(doc)

    def test_new_schema_invalidates_old_operational_receipts(self):
        doc = complete()
        tool = doc['evidence'][0]['receipt']['tools'][0]
        tool['input_schema']['title'] = 'new-schema'
        tool['schema_sha256'] = p.digest(tool['input_schema'])
        sealed(doc['evidence'][0])
        out = self.status(doc)
        self.assertFalse(out['catalog_evidence_complete'])
        self.assertTrue(any('UNBOUND_HOST_CAPABILITY_RECEIPT' in r['reasons'] for r in out['excluded_receipts']))

    def test_each_required_operation_must_be_observed(self):
        for operation in p.OPERATIONS:
            doc = complete()
            doc['evidence'][0]['receipt']['tools'][0]['operations'].remove(operation)
            sealed(doc['evidence'][0])
            self.assertFalse(self.status(doc)['catalog_evidence_complete'])

    def test_categories_cannot_mix_incompatible_inventory_snapshots(self):
        doc = complete()
        second = copy.deepcopy(doc['evidence'][0])
        second['id'] = 'second-capability'
        second['receipt']['artifact_ref'] = 'second-inventory-observation'
        sealed(second)
        doc['evidence'].append(second)
        lifecycle = next(r for r in doc['evidence'] if r['id'] == 'order_lifecycle')
        lifecycle['receipt']['capability_sha256'] = second['receipt_sha256']
        sealed(lifecycle)
        out = self.status(doc)
        self.assertEqual(out['evidence_status'], 'CONFLICTING_EVIDENCE')
        self.assertEqual(out['conflicts'][0]['reason'], 'NO_COMMON_CAPABILITY_RECEIPT_ACROSS_CATEGORIES')

    def test_receipts_not_transferable_between_hosts_deployments_or_runtime(self):
        for field in ('id', 'package_sha256', 'runtime_sha256'):
            doc = complete()
            doc['host'][field] = 'other-host' if field == 'id' else 'c' * 64
            self.assertFalse(self.status(doc)['catalog_evidence_complete'])
        doc = complete()
        doc['host']['package_sha256'] = None
        self.assertFalse(self.status(doc)['catalog_evidence_complete'])

    def test_receipts_not_transferable_between_modes_assets_or_scopes(self):
        for field, value in (('mode', 'paper'), ('asset_class', 'options'), ('scope_id', 'other'), ('scope_description', 'Changed economic scope')):
            doc = complete()
            doc['requests'][0][field] = value
            self.assertFalse(self.status(doc)['catalog_evidence_complete'])

    def test_expired_and_future_evidence_excluded(self):
        for value in ('2026-10-23T09:00:00Z', '2026-10-24T10:00:00Z'):
            doc = complete()
            doc['as_of'] = value
            out = self.status(doc)
            self.assertFalse(out['catalog_evidence_complete'])
            self.assertTrue(out['excluded_receipts'])

    def test_timestamps_exact_and_valid_intervals(self):
        for value in ('2026-10-23', '2026-10-23T12:00:00', '2026-10-23T12:00:00-99:00'):
            doc = packet()
            doc['as_of'] = value
            with self.assertRaises(ValueError):
                p.assess(doc)
        doc = complete()
        doc['evidence'][0]['receipt']['valid_until'] = doc['evidence'][0]['receipt']['observed_at']
        sealed(doc['evidence'][0])
        with self.assertRaisesRegex(ValueError, 'VALIDITY_INTERVAL'):
            p.assess(doc)

    def test_malformed_offsets_rejected_at_every_timestamp_boundary(self):
        for offset in ('+00:99', '+01:60', '-00:60', '+23:60', '+24:00', '-99:00'):
            for location in ('as_of', 'observed_at', 'valid_until', 'documentation'):
                with self.subTest(offset=offset, location=location):
                    doc = complete()
                    if location == 'as_of':
                        doc['as_of'] = '2026-10-23T12:00:00' + offset
                    elif location in ('observed_at', 'valid_until'):
                        record = doc['evidence'][0]
                        day = '2026-10-24' if location == 'valid_until' else '2026-10-23'
                        record['receipt'][location] = day + 'T12:00:00' + offset
                        sealed(record)
                    else:
                        doc['documentation'] = [{'id': 'd', 'host_id': 'fictional-host',
                            'asset_classes': ['stocks'], 'modes': ['live'],
                            'observed_at': '2026-10-23T12:00:00' + offset,
                            'source_url': 'https://example.org', 'summary': 'Fictional.', 'support': 'documented'}]
                    with self.assertRaisesRegex(ValueError, 'INVALID_TIMESTAMP_OFFSET'):
                        p.assess(doc)

    def test_valid_offset_boundaries_remain_supported(self):
        self.assertEqual(p.clock('2026-10-23T12:00:00+00:59').isoformat(), '2026-10-23T11:01:00+00:00')
        self.assertEqual(p.clock('2026-10-23T12:00:00+23:59').isoformat(), '2026-10-22T12:01:00+00:00')
        self.assertEqual(p.clock('2026-10-23T12:00:00-23:59').isoformat(), '2026-10-24T11:59:00+00:00')

    def test_unknown_fields_and_categories_rejected(self):
        doc = complete()
        doc['evidence'][1]['receipt']['automatically_approved'] = True
        sealed(doc['evidence'][1])
        with self.assertRaisesRegex(ValueError, 'EXACT_FIELDS'):
            p.assess(doc)
        doc = complete()
        doc['evidence'][1]['receipt']['kind'] = 'production_ready'
        sealed(doc['evidence'][1])
        with self.assertRaisesRegex(ValueError, 'UNKNOWN_EVIDENCE_KIND'):
            p.assess(doc)

    def test_duplicate_request_evidence_check_or_tool_rejected(self):
        for target in ('requests', 'evidence'):
            doc = complete()
            doc[target].append(copy.deepcopy(doc[target][0]))
            with self.assertRaisesRegex(ValueError, 'DUPLICATE'):
                p.assess(doc)
        for target in ('tools', 'checks'):
            doc = complete()
            row = doc['evidence'][0]
            row['receipt'][target].append(copy.deepcopy(row['receipt'][target][0]))
            sealed(row)
            with self.assertRaisesRegex(ValueError, 'DUPLICATE'):
                p.assess(doc)

    def test_asset_specific_checks_are_required(self):
        doc = complete('options', 'research')
        row = next(r for r in doc['evidence'] if r['id'] == 'instrument_semantics')
        row['receipt']['checks'] = row['receipt']['checks'][:3]
        sealed(row)
        self.assertFalse(self.status(doc)['catalog_evidence_complete'])

    def test_no_mutation_and_canonical_mapping_hash(self):
        doc = complete()
        before = copy.deepcopy(doc)
        a = p.assess(doc)
        self.assertEqual(doc, before)
        self.assertEqual(a, p.assess(dict(reversed(list(doc.items())))))

    def test_packaged_example_all_scopes_unverified_no_account_data(self):
        doc = json.loads((ROOT / 'examples/platform-readiness.json').read_text(encoding='utf-8'))
        out = p.assess(doc)
        self.assertEqual(len(out['results']), 21)
        self.assertEqual({r['evidence_status'] for r in out['results']}, {'UNVERIFIED'})
        self.assertFalse(out['catalog_evidence_complete'])
        self.assertEqual(doc['evidence'], [])

    def test_cli_uses_strict_json_and_prints_only_advisory_output(self):
        with patch.object(sys, 'argv', ['platform_readiness.py', 'fixture.json']), \
             patch.object(Path, 'read_text', return_value=json.dumps(packet())), \
             patch('sys.stdout', new_callable=io.StringIO) as output:
            self.assertEqual(p.main(), 0)
            self.assertFalse(json.loads(output.getvalue())['enforces_execution'])
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_JSON_KEY'):
            json.loads('{"a": 1, "a": 2}', object_pairs_hook=p.strict_object)


if __name__ == '__main__':
    unittest.main()
