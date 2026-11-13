"""Synthetic source-bound per-metric study reporting counterexamples."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import final_report
import institutional_research
import institutional_report as module
import supplied_research
from test_institutional_research import evaluated


def study():
    result = evaluated()
    observation = result['evaluation']['cases'][0]
    observation['usefulness']['assisted_minutes'] = 7.5
    observation['usefulness']['baseline_minutes'] = 19.25
    observation['paper_return']['return_decimal'] = 0.0375
    observation['paper_return']['benchmark']['return_decimal'] = 0.0125
    return result


class InstitutionalReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='institutional-report-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = self.root / 'ingress.json'
        self.request = {'documents': [{'id': 'study-a', 'source_ref': {'source_id': 'original', 'pointer': '/study'}}],
                        'operations': ['plan', 'evaluate']}
        self.sources(study())

    def sources(self, document):
        self.document = deepcopy(document)
        raw = json.dumps({'study': document}).encode()
        (self.root / 'original.json').write_bytes(raw)
        extra = b'Unselected independent context remains retained.'
        (self.root / 'context.txt').write_bytes(extra)
        self.manifest.write_text(json.dumps({'schema_version': 1, 'sources': [
            {'id': 'original', 'path': 'original.json', 'format': 'json', 'sha256': hashlib.sha256(raw).hexdigest()},
            {'id': 'context', 'path': 'context.txt', 'format': 'text', 'sha256': hashlib.sha256(extra).hexdigest()}]}))
        self.pin = hashlib.sha256(self.manifest.read_bytes()).hexdigest()

    def analyze(self):
        return module.analyze(self.request, self.manifest, self.pin, self.root)

    def evaluation(self, result):
        return result['rows'][0]['operations']['evaluate']['result']

    def baseline_conflict(self):
        document = study()
        document['evaluation']['return_baseline_id'] = 'later-comparison'
        document['evaluation']['cases'][0]['paper_return']['benchmark']['id'] = 'later-comparison'
        self.sources(document)

    def compose(self):
        plan = {'output_contract': final_report.STRICT, 'sections': [
            {'kind': 'source_report', 'producer': 'institutional_report', 'request': self.request}]}
        plan_path = self.root / 'plan.json'; plan_path.write_text(json.dumps(plan))
        report = self.root / 'report'
        final_report.compose(plan_path, report, self.manifest, self.pin, self.root)
        return report

    def export(self):
        report = self.compose()
        metadata = self.root / 'metadata.json'
        metadata.write_text(json.dumps({'case_id': 'synthetic-institutional-study',
            'runtime_model_metadata': {'model': 'unknown', 'effort': 'unknown'}}))
        output = self.root / 'export'
        final_report.export_response(report, metadata, output)
        return output

    def test_direct_native_standard_decode_equivalence_including_fractional_tokens(self):
        original_bytes = (self.root / 'original.json').read_bytes()
        decoded = json.loads(original_bytes)['study']
        result = self.analyze()
        for name in ('plan', 'evaluate'):
            with self.subTest(operation=name):
                actual = result['rows'][0]['operations'][name]
                self.assertEqual(actual['status'], 'EXECUTED')
                self.assertEqual(actual['result'], getattr(institutional_research, name)(deepcopy(decoded)))
        self.assertEqual((self.root / 'original.json').read_bytes(), original_bytes)
        evaluation = self.evaluation(result)
        self.assertEqual(evaluation['usefulness']['mean_declared_minutes_saved'], '11.75')
        self.assertEqual(evaluation['returns']['mean_descriptive_excess_return_decimal'], '0.0250')
        original_value = evaluation['evaluation_contract']['cases'][0]['usefulness']['assisted_minutes']
        self.assertIs(type(original_value), float)
        self.assertEqual(original_value, 7.5)

    def test_return_baseline_conflict_excludes_only_returns(self):
        self.baseline_conflict(); result = self.evaluation(self.analyze()); row = result['cases'][0]
        self.assertTrue(row['usefulness_included'])
        self.assertFalse(row['returns_included'])
        self.assertEqual(result['usefulness']['included_cases'], 1)
        self.assertEqual(result['returns']['included_cases'], 0)
        self.assertIsNone(result['returns']['mean_descriptive_excess_return_decimal'])
        self.assertIn('PILOT_EVALUATION_PROTOCOL_CONFLICT:study.return_baseline_id', row['return_exclusion_reasons'])

    def test_reviewer_conflict_excludes_only_usefulness(self):
        document = study(); document['evaluation']['cases'][0]['usefulness']['reviewer_id'] = 'another-reviewer'
        self.sources(document); result = self.evaluation(self.analyze()); row = result['cases'][0]
        self.assertFalse(row['usefulness_included'])
        self.assertTrue(row['returns_included'])
        self.assertEqual(result['usefulness']['included_cases'], 0)
        self.assertEqual(result['returns']['included_cases'], 1)
        self.assertEqual(row['usefulness_exclusion_reasons'], ['PILOT_REVIEWER_MISMATCH'])

    def test_shared_protocol_conflict_excludes_both_metrics(self):
        document = study(); document['evaluation']['workflow_baseline_id'] = 'post-outcome-baseline'
        document['evaluation']['cases'][0]['usefulness']['baseline_id'] = 'post-outcome-baseline'
        self.sources(document); result = self.evaluation(self.analyze()); row = result['cases'][0]
        self.assertFalse(row['usefulness_included']); self.assertFalse(row['returns_included'])
        self.assertEqual(result['usefulness']['included_cases'], 0)
        self.assertEqual(result['returns']['included_cases'], 0)
        self.assertTrue(row['prospective_exclusion_reasons'])

    def test_roster_gaps_and_native_limits_not_discarded(self):
        document = study(); document['evaluation']['expected_case_ids'].append('missing-observation')
        self.sources(document); result = self.evaluation(self.analyze())
        self.assertEqual(result['roster']['missing'], ['missing-observation'])
        self.assertEqual(result['roster']['status'], 'INCOMPLETE_OR_UNEXPECTED')
        self.assertFalse(result['actual_elapsed_operation_verified'])
        self.assertFalse(result['profitability_established'])
        self.assertFalse(result['external_or_independent_validation_established'])
        self.assertTrue(result['readiness']); self.assertTrue(result['limitations'])

    def test_missing_original_response_remains_a_native_exclusion(self):
        document = study(); document['evaluation']['cases'][0]['first_response']['sha256'] = '0' * 64
        self.sources(document); row = self.evaluation(self.analyze())['cases'][0]
        self.assertFalse(row['usefulness_included']); self.assertFalse(row['returns_included'])
        self.assertTrue(row['prospective_exclusion_reasons'])

    def test_failed_evaluation_retains_plan_and_error(self):
        document = study(); document.pop('evaluation'); self.sources(document)
        result = self.analyze(); operations = result['rows'][0]['operations']
        self.assertEqual(result['status'], 'PARTIAL_RETAINED_FAILURES')
        self.assertEqual(operations['plan']['status'], 'EXECUTED')
        self.assertEqual(operations['evaluate']['status'], 'FAILED')
        self.assertEqual(operations['evaluate']['error']['message'], 'EVALUATION_OBJECT_REQUIRED')

    def test_unselected_original_and_manifest_changes_rejected(self):
        (self.root / 'context.txt').write_text('Altered context')
        with self.assertRaisesRegex(ValueError, 'HASH_MISMATCH'): self.analyze()
        self.sources(study())
        with self.assertRaisesRegex(ValueError, 'MANIFEST_HASH_MISMATCH'):
            module.analyze(self.request, self.manifest, '0' * 64, self.root)

    def test_no_result_overrides_partial_objects_or_mutating_operations(self):
        for change in ('override', 'partial', 'journal', 'capture', 'recover', 'acquire', 'duplicate'):
            old = deepcopy(self.request)
            if change == 'override': self.request['returns_included'] = True
            elif change == 'partial': self.request['documents'][0]['source_ref']['pointer'] = '/study/evaluation'
            elif change == 'duplicate': self.request['documents'].append(deepcopy(self.request['documents'][0]))
            else: self.request['operations'] = [change]
            with self.subTest(change=change), self.assertRaises(ValueError): self.analyze()
            self.request = old

    def test_native_call_and_complete_source_binding(self):
        original = module.OPERATIONS['evaluate']
        with patch.dict(module.OPERATIONS, {'evaluate': unittest.mock.Mock(wraps=original)}):
            result = self.analyze()
            module.OPERATIONS['evaluate'].assert_called_once()
        self.assertEqual({r['source_id'] for r in result['source_inventory']}, {'original', 'context'})
        binding = result['rows'][0]['source_binding']
        self.assertEqual(binding['pointer'], '/study')
        self.assertEqual(binding['source_sha256'], hashlib.sha256((self.root / 'original.json').read_bytes()).hexdigest())

    def test_canonical_response_rejects_per_case_change_with_correct_aggregate(self):
        self.baseline_conflict(); output = self.export()
        response = json.loads((output / 'response.json').read_bytes())
        evaluation = self.evaluation(response['rows'][0]['result'])
        self.assertEqual(evaluation['returns']['included_cases'], 0)
        evaluation['cases'][0]['returns_included'] = True
        published = self.root / 'published.json'; published.write_text(json.dumps(response))
        with self.assertRaisesRegex(ValueError, 'PUBLISHED_STRUCTURED_RESPONSE_DIFFERS'):
            final_report.verify_response(output, published)

    def test_canonical_text_rejects_contradictory_inclusion_sentence(self):
        self.baseline_conflict(); report = self.compose()
        text = (report / 'first-response.md').read_text(encoding='utf8')
        published = self.root / 'published.md'
        published.write_text(text + '\nThe observation was included in both metrics.\n', encoding='utf8')
        with self.assertRaises(ValueError): final_report.verify(report, published)
        final_report.verify(report)

    def test_replay_rejects_changed_native_result_with_resigned_inventory(self):
        self.baseline_conflict(); report = self.compose(); producer = report / 'sections/000/producer'
        path = producer / 'result.json'; result = json.loads(path.read_bytes())
        self.evaluation(result)['cases'][0]['returns_included'] = True
        path.write_bytes(supplied_research.encode(result))
        path = producer / 'receipt.json'; receipt = json.loads(path.read_bytes())
        receipt['artifacts'] = supplied_research.file_inventory(producer)
        path.write_bytes(supplied_research.encode(receipt))
        with self.assertRaises(ValueError): supplied_research.verify(producer)

    def test_portable_canonical_export(self):
        self.baseline_conflict(); output = self.export()
        moved = self.root / 'moved'; shutil.copytree(output, moved)
        self.assertEqual(final_report.verify_response(moved)['status'], 'COMPLETED_CANONICAL_RESPONSE_EXPORT')


if __name__ == '__main__':
    unittest.main()
