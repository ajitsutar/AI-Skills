"""Invented observations exercise mapping; arithmetic belongs to the engine."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from flow_normalization import normalize_flows
from financial_normalize import normalize


def example(periods=None):
    periods = periods or [('2025-04-01', '2025-06-30', '11'),
                          ('2025-07-01', '2025-09-30', '13'),
                          ('2025-10-01', '2025-12-31', '17'),
                          ('2026-01-01', '2026-03-31', '19')]
    rows = [dict(record_id='row-' + str(i), source_id='source', issuer_id='issuer',
                 entity_id='entity', metric='reported_operating_cash',
                 source_pointer='/observations/' + str(i), quote='Invented reported cash ' + value,
                 period_start=start, period_end=end, value=value, unit='USD', decimals=0)
            for i, (start, end, value) in enumerate(periods)]
    return dict(flow_mapping_schema_version=1, information_cutoff='2026-04-30T23:00:00Z',
        sources=[dict(source_id='source', source_text=json.dumps({'observations': rows}),
                      uri='urn:invented:mapping-test', distribution_host='invented.example',
                      document_origin='issuer_release', delivery='issuer',
                      publication={'precision': 'timestamp', 'at': '2026-04-20T10:00:00Z'},
                      retrieved_at='2026-05-01T10:00:00Z')],
        issuers=[dict(issuer_id='issuer', entity_id='entity', adapter='corporate',
                      ttm_start='2025-04-01', financial_period_end='2026-03-31')],
        metric_mappings={'reported_operating_cash': {
            'concept': 'cfo', 'review': {'status': 'reviewed', 'basis_evidence': 'Invented review: reported consolidated operating cash'}}},
        observations=rows)


def issuer(result):
    return result['normalization']['issuers'][0]


class FlowMappingTests(unittest.TestCase):
    def test_quarters_delegate_and_retain_provenance(self):
        data = example()
        original = copy.deepcopy(data)
        result = normalize_flows(data)
        self.assertEqual(data, original)
        self.assertEqual(issuer(result)['fields']['cfo_ttm']['value'], '60')
        self.assertEqual(result['normalization'], normalize(result['normalization_input']))
        self.assertEqual(result['mapping_input'], original)
        source = result['normalization_input']['sources'][0]
        self.assertEqual(source['content_sha256'], hashlib.sha256(data['sources'][0]['source_text'].encode('utf-8')).hexdigest())
        self.assertEqual(source['source_text'], original['sources'][0]['source_text'])
        self.assertEqual(result['normalization']['records'][0]['source_pointer'], '/observations/0')
        self.assertEqual(result['normalization_input']['schema_version'], 1)
        self.assertFalse(result['execution_authorized'])

    def test_annual_plus_current_ytd_minus_prior_ytd(self):
        result = normalize_flows(example([('2025-01-01', '2025-12-31', '80'),
                                          ('2025-01-01', '2025-03-31', '20'),
                                          ('2026-01-01', '2026-03-31', '19')]))
        self.assertEqual(issuer(result)['fields']['cfo_ttm']['value'], '79')
        self.assertIn('FY_PLUS_YTD_MINUS_PRIOR_YTD', json.dumps(issuer(result)['fields']['cfo_ttm']['derivation']))

    def test_duplicate_period_reconciliation_is_engine_owned(self):
        data = example()
        duplicate = dict(data['observations'][0], record_id='duplicate', source_pointer='/duplicate')
        data['observations'].append(duplicate)
        result = normalize_flows(data)
        self.assertEqual(issuer(result)['fields']['cfo_ttm']['value'], '60')
        self.assertIn('duplicate', issuer(result)['fields']['cfo_ttm']['record_ids'])
        duplicate['value'] = '30'
        result = normalize_flows(data)
        self.assertNotIn('cfo_ttm', issuer(result)['fields'])
        self.assertTrue(any('CONFLICTING_OBSERVATIONS' in g['reason'] for g in issuer(result)['gaps']))

    def test_after_cutoff_observations_do_not_enter_ttm(self):
        data = example()
        data['sources'][0]['publication']['at'] = '2026-05-01T09:00:00Z'
        result = normalize_flows(data)
        self.assertNotIn('cfo_ttm', issuer(result)['fields'])
        self.assertEqual(len(result['normalization']['extraction_issues']), 4)
        self.assertTrue(all(i['reason'] == 'NOT_KNOWN_BY_CUTOFF' for i in result['normalization']['extraction_issues']))

    def test_amendment_is_not_silently_preferred(self):
        data = example()
        amendment = copy.deepcopy(data['sources'][0])
        amendment.update(source_id='amendment', amendment_of='source', source_text='Invented amended observation')
        amendment['publication']['at'] = '2026-04-25T10:00:00Z'
        data['sources'].append(amendment)
        data['observations'].append(dict(data['observations'][0], record_id='amended-row', source_id='amendment', value='99'))
        result = normalize_flows(data)
        self.assertNotIn('cfo_ttm', issuer(result)['fields'])
        self.assertTrue(any('CONFLICT' in g['reason'] for g in issuer(result)['gaps']))
        self.assertEqual(result['normalization_input']['sources'][1]['amendment_of'], 'source')

    def test_unverified_and_latest_public_period_defaults_stay_unresolved(self):
        result = normalize_flows(example())
        self.assertEqual(issuer(result)['fields']['cfo_ttm']['status'], 'DRAFT_UNVERIFIED')
        self.assertFalse(issuer(result)['latest_public_period_checked'])
        self.assertFalse(result['normalization']['source_reviews']['source']['ready'])
        self.assertNotIn('latest_public_period_review', result['normalization_input']['issuers'][0])
        self.assertEqual(result['normalization_input']['sources'][0]['verification'], {'status': 'unverified'})

    def test_explicit_source_claims_are_visible_not_invented(self):
        data = example()
        verification = {'status': 'verified', 'method': 'Invented caller declaration', 'evidence': ['Invented evidence']}
        data['sources'][0]['verification'] = verification
        result = normalize_flows(data)
        self.assertEqual(result['mapping_input']['sources'][0]['verification'], verification)
        self.assertEqual(result['normalization_input']['sources'][0]['verification'], verification)
        self.assertEqual(issuer(result)['fields']['cfo_ttm']['status'], 'READY')
        self.assertFalse(issuer(result)['latest_public_period_checked'])
        self.assertIn('not independently authenticated', result['limitations'])

    def test_unknown_metric_or_concept_is_mapping_work(self):
        for replacement in ({}, {'reported_operating_cash': {'concept': 'operating_cash_flow'}}):
            data = example()
            data['metric_mappings'] = replacement
            result = normalize_flows(data)
            self.assertEqual(result['status'], 'MAPPING_REQUIRED')
            self.assertEqual(len(result['mapping_issues']), 4)
            self.assertFalse(result['normalization']['records'])

    def test_review_and_precision_are_not_invented(self):
        for field in ('review', 'decimals'):
            data = example()
            if field == 'review':
                del data['metric_mappings']['reported_operating_cash']['review']
            else:
                for row in data['observations']:
                    del row['decimals']
            result = normalize_flows(data)
            self.assertEqual(result['status'], 'MAPPING_REQUIRED')
            self.assertFalse(result['normalization_input']['transcriptions'])

    def test_bad_source_hash_is_not_overwritten(self):
        data = example()
        data['sources'][0]['content_sha256'] = '0' * 64
        result = normalize_flows(data)
        self.assertEqual(result['mapping_issues'][0]['reason'], 'SOURCE_BYTES_HASH_MISMATCH')
        self.assertEqual(result['mapping_input']['sources'][0]['content_sha256'], '0' * 64)
        self.assertFalse(result['normalization_input']['sources'])

    def test_binary_bytes_are_preserved(self):
        data = example()
        del data['sources'][0]['source_text']
        raw = b'\xff\x00retained invented binary evidence'
        encoded = base64.b64encode(raw).decode('ascii')
        data['sources'][0]['source_bytes_base64'] = encoded
        result = normalize_flows(data)
        source = result['normalization_input']['sources'][0]
        self.assertEqual(source['source_bytes_base64'], encoded)
        self.assertEqual(source['content_sha256'], hashlib.sha256(raw).hexdigest())

    def test_entity_and_units_cannot_be_guessed(self):
        for key, value in [('entity_id', 'different'), ('unit', 'USD millions')]:
            data = example()
            for row in data['observations']:
                row[key] = value
            result = normalize_flows(data)
            self.assertEqual(result['status'], 'MAPPING_REQUIRED')
            self.assertFalse(result['normalization']['records'])

    def test_explicit_display_scale_and_precision_delegate(self):
        data = example()
        for row in data['observations']:
            row['display_text'] = row.pop('value')
            row.update(scale=3, decimals=-3)
        result = normalize_flows(data)
        self.assertEqual(issuer(result)['fields']['cfo_ttm']['value'], '60000')
        self.assertEqual(issuer(result)['fields']['cfo_ttm']['rounding_error_bound'], '2000')


if __name__ == '__main__':
    unittest.main()
