"""Prespecified membership must precede study-metric accumulation."""
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import institutional_research as research
import institutional_report
from test_institutional_research import evaluated


def counterexample():
    document = evaluated()
    case = document['evaluation']['cases'][0]
    case['paper_return']['return_decimal'] = '-0.1'
    case['paper_return']['benchmark']['return_decimal'] = '0'
    extra = deepcopy(case); extra['id'] = 'unregistered-positive'
    extra['paper_return']['return_decimal'] = '1'
    extra['usefulness']['useful'] = False
    document['evaluation']['cases'].append(extra)
    return document


class CohortTests(unittest.TestCase):
    def test_audit_counterexample_cannot_change_registered_mean(self):
        original = evaluated(); original['evaluation']['cases'] = counterexample()['evaluation']['cases'][:1]
        baseline = research.evaluate(original)
        document = counterexample(); before = deepcopy(document)
        result = research.evaluate(document)
        self.assertEqual(document, before)
        self.assertEqual(result['returns'], baseline['returns'])
        self.assertEqual(Decimal(result['returns']['mean_descriptive_excess_return_decimal']), Decimal('-0.1'))
        self.assertEqual(Decimal(result['all_supplied_descriptive']['returns']['mean_descriptive_excess_return_decimal']), Decimal('0.45'))
        self.assertEqual(result['usefulness']['declared_useful_fraction'], '1')
        self.assertEqual(result['all_supplied_descriptive']['usefulness']['declared_useful_fraction'], '0.5')
        row = result['cases'][1]
        self.assertEqual(row['cohort_membership'], 'UNEXPECTED')
        self.assertFalse(row['returns_included']); self.assertFalse(row['usefulness_included'])
        self.assertTrue(row['all_supplied_descriptive_returns_included'])
        self.assertIn('CASE_OUTSIDE_PRESPECIFIED_COHORT', row['return_exclusion_reasons'])

    def test_missing_observation_is_never_a_zero(self):
        document = evaluated(); document['evaluation']['expected_case_ids'].append('missing')
        result = research.evaluate(document)
        self.assertEqual(result['returns']['included_cases'], 1)
        self.assertEqual(result['roster']['missing'], ['missing'])
        self.assertEqual(len(result['cases']), 1)
        document['evaluation']['cases'] = []
        result = research.evaluate(document)
        self.assertEqual(result['returns']['included_cases'], 0)
        self.assertIsNone(result['returns']['mean_descriptive_excess_return_decimal'])
        self.assertIsNone(result['usefulness']['declared_useful_fraction'])

    def test_all_unexpected_retained_without_primary_metric(self):
        document = counterexample(); document['evaluation']['expected_case_ids'] = ['unobserved']
        result = research.evaluate(document)
        self.assertEqual(len(result['cases']), 2)
        self.assertEqual(result['returns']['included_cases'], 0)
        self.assertIsNone(result['returns']['mean_descriptive_excess_return_decimal'])
        self.assertEqual(result['all_supplied_descriptive']['returns']['included_cases'], 2)

    def test_roster_order_immaterial_and_protocol_roster_authoritative(self):
        document = counterexample()
        ids = [case['id'] for case in document['evaluation']['cases']]
        document['evaluation']['expected_case_ids'] = ids
        document['pilot']['study']['expected_case_ids'] = list(reversed(ids))
        result = research.evaluate(document)
        self.assertEqual(result['roster']['status'], 'MATCHED')
        self.assertEqual(result['protocol_reconciliation']['status'], 'MATCHED_DECLARED_PROTOCOL')
        self.assertEqual(result['returns']['included_cases'], 2)
        document['evaluation']['expected_case_ids'] = ['unregistered-positive']
        result = research.evaluate(document)
        self.assertEqual(result['roster']['expected_case_ids'], list(reversed(ids)))
        self.assertEqual(result['protocol_reconciliation']['status'], 'PROTOCOL_CONFLICT')
        self.assertEqual(result['returns']['included_cases'], 0)

    def test_duplicate_case_and_roster_ids_rejected(self):
        for part in ('cases', 'expected_case_ids'):
            document = evaluated(); document['evaluation'][part] *= 2
            with self.subTest(part=part), self.assertRaisesRegex(ValueError, 'UNIQUE_'):
                research.evaluate(document)

    def test_no_roster_preserves_standalone_descriptive_work(self):
        document = counterexample(); del document['evaluation']['expected_case_ids']
        result = research.evaluate(document)
        self.assertEqual(result['roster']['status'], 'UNKNOWN')
        self.assertEqual(result['metric_cohort'], 'UNREGISTERED_ALL_SUPPLIED')
        self.assertEqual(result['returns']['included_cases'], 2)
        self.assertEqual(result['cases'][0]['cohort_membership'], 'UNREGISTERED_SUPPLIED')

    def test_source_bound_report_keeps_both_cohorts_and_denominators(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); raw = json.dumps(counterexample()).encode()
            (root / 'original.json').write_bytes(raw)
            manifest = root / 'manifest.json'
            manifest.write_text(json.dumps({'schema_version': 1, 'sources': [
                {'id': 'study', 'path': 'original.json', 'format': 'json', 'sha256': hashlib.sha256(raw).hexdigest()}]}))
            result = institutional_report.analyze({'documents': [{'id': 'study', 'source_ref': {'source_id': 'study', 'pointer': ''}}],
                                                   'operations': ['evaluate']}, manifest, hashlib.sha256(manifest.read_bytes()).hexdigest(), root)
            native = result['rows'][0]['operations']['evaluate']['result']
            self.assertEqual(native, research.evaluate(counterexample()))
            self.assertIn('ALL_SUPPLIED_DESCRIPTIVE_NOT_REGISTERED_COHORT', result['report']['text'])
            self.assertIn('CASE_OUTSIDE_PRESPECIFIED_COHORT', result['report']['text'])


if __name__ == '__main__':
    unittest.main()
