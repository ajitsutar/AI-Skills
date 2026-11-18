import copy
import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests'))
from test_flow_normalization import example, issuer
from flow_normalization import normalize_flows
from financial_normalize import normalize

class IndependentInvariants(unittest.TestCase):
    def test_date_interval_straddling_cutoff_excluded(self):
        data = example()
        data['sources'][0]['publication'] = {'precision': 'date', 'date': '2026-04-30', 'timezone': 'America/Los_Angeles'}
        result = normalize_flows(data)
        self.assertNotIn('cfo_ttm', issuer(result)['fields'])
        self.assertTrue(all(x['reason'] == 'NOT_KNOWN_BY_CUTOFF' for x in result['normalization']['extraction_issues']))
        self.assertEqual(result['normalization'], normalize(result['normalization_input']))

    def test_date_interval_before_cutoff_and_exact_timestamp_boundary(self):
        for publication in ({'precision': 'date', 'date': '2026-04-29', 'timezone': 'America/Los_Angeles'}, {'precision': 'timestamp', 'at': '2026-04-30T23:00:00Z'}):
            data = example()
            data['sources'][0]['publication'] = publication
            self.assertEqual(issuer(normalize_flows(data))['fields']['cfo_ttm']['value'], '60')

    def test_missing_ambiguous_and_corrupt_source_bytes(self):
        for variant in ('missing', 'ambiguous', 'invalid_base64'):
            data = example()
            source = data['sources'][0]
            if variant != 'ambiguous': source.pop('source_text')
            if variant != 'missing': source['source_bytes_base64'] = '%%' if variant == 'invalid_base64' else 'YWJj'
            result = normalize_flows(data)
            self.assertEqual(result['status'], 'MAPPING_REQUIRED')
            self.assertFalse(result['normalization_input']['sources'])
            self.assertFalse(result['normalization']['records'])

    def test_mapping_policy_mismatch(self):
        data = example()
        data['metric_mappings']['reported_operating_cash']['review']['policy_sha256'] = '0' * 64
        result = normalize_flows(data)
        self.assertTrue(all(i['reason'] == 'MAPPING_POLICY_MISMATCH' for i in result['mapping_issues']))
        self.assertFalse(result['normalization']['records'])

    def test_invalid_precision_raw_transform_and_two_values(self):
        for change in ({'decimals': None}, {'decimals': 31}, {'scale': 6}, {'display_text': '11'}):
            data = example()
            for row in data['observations']: row.update(change)
            result = normalize_flows(data)
            self.assertEqual(result['status'], 'MAPPING_REQUIRED')
            self.assertFalse(result['normalization']['records'])

    def test_basis_required_and_wrong_basis_delegated(self):
        for basis in (None, 'adjusted_parent'):
            data = example()
            mapping = data['metric_mappings']['reported_operating_cash']
            mapping['concept'] = 'parent_income'
            if basis: mapping['basis'] = basis
            result = normalize_flows(data)
            self.assertNotIn('net_income_ttm', issuer(result)['fields'])
            if basis:
                self.assertTrue(all(x['reason'] == 'ACCOUNTING_BASIS_NOT_SELECTED:adjusted_parent' for x in result['normalization']['extraction_issues']))
            else:
                self.assertTrue(all(x['reason'] == 'EXPLICIT_ACCOUNTING_BASIS_REQUIRED' for x in result['mapping_issues']))

    def test_display_sign_and_decimal_transform(self):
        data = example()
        for row in data['observations']:
            row['display_text'] = row.pop('value') + ',5'
            row.update(format='num-comma-decimal', sign='-', decimals=1)
        result = normalize_flows(data)
        self.assertEqual(issuer(result)['fields']['cfo_ttm']['value'], '-62.0')
        self.assertEqual(result['normalization'], normalize(result['normalization_input']))

    def test_contradictory_observation_basis_is_not_silently_overwritten(self):
        data = example()
        mapping = data['metric_mappings']['reported_operating_cash']
        mapping.update(concept='parent_income', basis='gaap_parent')
        for row in data['observations']: row['basis'] = 'adjusted_parent'
        result = normalize_flows(data)
        self.assertNotIn('net_income_ttm', issuer(result)['fields'])
        self.assertEqual(result['status'], 'MAPPING_REQUIRED')
        self.assertTrue(all(x['reason'] == 'OBSERVATION_MAPPING_BASIS_CONFLICT' for x in result['mapping_issues']))
        self.assertFalse(result['normalization_input']['transcriptions'])
        self.assertTrue(all(x['basis'] == 'adjusted_parent' for x in result['mapping_input']['observations']))

    def test_matching_or_absent_observation_basis_remains_usable(self):
        for explicit in (False, True):
            data = example()
            data['metric_mappings']['reported_operating_cash'].update(concept='parent_income', basis='gaap_parent')
            if explicit:
                for row in data['observations']: row['basis'] = 'gaap_parent'
            result = normalize_flows(data)
            self.assertFalse(result['mapping_issues'])
            self.assertEqual(issuer(result)['fields']['net_income_ttm']['value'], '60')

if __name__ == '__main__': unittest.main(verbosity=2)
