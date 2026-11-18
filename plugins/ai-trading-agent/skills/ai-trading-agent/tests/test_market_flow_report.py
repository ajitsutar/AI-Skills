"""Synthetic source/projection counterexamples; no private comparison answers."""
from copy import deepcopy
from fractions import Fraction
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
import market_flow_report as module
import supplied_research
from test_market_flow import pressure_document


def synthetic():
    document = pressure_document()
    records = {r['id']: r for r in document['records']}
    records['si']['payload']['short_interest_shares'] = '1650'
    records['d1']['payload']['volume'] = '250'
    records['d2']['payload']['volume'] = '450'
    return document


class MarketFlowReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='market-report-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = self.root / 'ingress.json'
        self.request = {'documents': [{'id': 'sample', 'source_ref': {'source_id': 'original', 'pointer': '/market'}}],
                        'operations': ['flow', 'positioning', 'squeeze']}
        self.sources(synthetic())

    def sources(self, document):
        raw = json.dumps({'market': document}).encode()
        (self.root / 'original.json').write_bytes(raw)
        other = b'Additional context remains in the full corpus.'
        (self.root / 'context.txt').write_bytes(other)
        self.manifest.write_text(json.dumps({'schema_version': 1, 'sources': [
            {'id': 'original', 'path': 'original.json', 'format': 'json', 'sha256': hashlib.sha256(raw).hexdigest()},
            {'id': 'context', 'path': 'context.txt', 'format': 'text', 'sha256': hashlib.sha256(other).hexdigest()}]}))
        self.pin = hashlib.sha256(self.manifest.read_bytes()).hexdigest()

    def analyze(self):
        return module.analyze(self.request, self.manifest, self.pin, self.root)

    def adv(self, result):
        return result['rows'][0]['operations']['positioning']['result']['short_interest'][0]['adv']

    def mismatched(self):
        document = synthetic()
        for row in document['records']:
            if row['id'] in ('d1', 'd2'):
                row['payload']['adjustment_basis'] = 'other_split_basis'
        self.sources(document)

    def compose(self):
        plan = {'output_contract': final_report.STRICT, 'sections': [
            {'kind': 'source_report', 'producer': 'market_flow_report', 'request': self.request}]}
        plan_path = self.root / 'plan.json'; plan_path.write_text(json.dumps(plan))
        output = self.root / 'report'
        final_report.compose(plan_path, output, self.manifest, self.pin, self.root)
        return output

    def export(self):
        report = self.compose()
        metadata = self.root / 'metadata.json'
        metadata.write_text(json.dumps({'case_id': 'synthetic-market-research',
            'runtime_model_metadata': {'model': 'unknown', 'effort': 'unknown'}}))
        output = self.root / 'export'
        final_report.export_response(report, metadata, output)
        return output

    def test_complete_comparable_window_uses_independent_arithmetic(self):
        result = self.analyze(); adv = self.adv(result)
        self.assertEqual(adv['average_daily_volume'], 350)
        self.assertAlmostEqual(adv['days_to_cover'], float(Fraction(33, 7)))
        self.assertEqual(adv['conditional_days_to_cover'], adv['days_to_cover'])
        self.assertIsNone(adv['unreconciled_share_count_quotient'])
        self.assertEqual(result['failed_operations'], 0)
        self.assertEqual({r['source_id'] for r in result['source_inventory']}, {'original', 'context'})
        self.assertFalse(result['whole_report_semantic_pass'])

    def test_matched_basis_incomplete_calendar_retains_conditional_only(self):
        document = synthetic()
        si = next(r['payload'] for r in document['records'] if r['id'] == 'si')
        si['adv_window']['start_date'] = '2026-11-06'
        si['adv_window']['expected_sessions'].insert(0, '2026-11-06')
        self.sources(document)
        adv = self.adv(self.analyze())
        self.assertEqual(adv['window_coverage'], 'INCOMPLETE_DECLARED_SESSIONS')
        self.assertIsNone(adv['days_to_cover'])
        self.assertAlmostEqual(adv['conditional_days_to_cover'], float(Fraction(33, 7)))

    def test_mismatch_never_promotes_quotient_to_conditional_dtc(self):
        self.mismatched(); result = self.analyze(); adv = self.adv(result)
        self.assertEqual(adv['share_adjustment_comparability'], 'MISMATCH')
        self.assertIsNone(adv['average_daily_volume'])
        self.assertIsNone(adv['days_to_cover'])
        self.assertIsNone(adv['conditional_days_to_cover'])
        self.assertEqual(adv['supplied_volume_arithmetic_mean'], 350)
        self.assertAlmostEqual(adv['unreconciled_share_count_quotient'], float(Fraction(33, 7)))
        self.assertEqual(self.analyze(), result)

    def test_missing_basis_is_distinct_from_mismatch(self):
        document = synthetic()
        next(r['payload'] for r in document['records'] if r['id'] == 'd1').pop('adjustment_basis')
        self.sources(document); adv = self.adv(self.analyze())
        self.assertEqual(adv['share_adjustment_comparability'], 'UNKNOWN')
        self.assertIsNone(adv['conditional_days_to_cover'])
        self.assertAlmostEqual(adv['unreconciled_share_count_quotient'], float(Fraction(33, 7)))

    def test_original_fractional_numeric_token_keeps_native_type(self):
        document = synthetic()
        next(r['payload'] for r in document['records'] if r['id'] == 'd1')['volume'] = 250.5
        self.sources(document)
        result = self.analyze()['rows'][0]['operations']['positioning']['result']
        raw_record = next(r for r in result['evidence']['records'] if r['id'] == 'd1')
        self.assertIs(type(raw_record['payload']['volume']), float)
        saved = json.loads(supplied_research.encode(result))
        saved_record = next(r for r in saved['evidence']['records'] if r['id'] == 'd1')
        self.assertEqual(saved_record['payload']['volume'], 250.5)
        self.assertAlmostEqual(saved['short_interest'][0]['adv']['average_daily_volume'], 350.25)

    def test_zero_adv_and_provider_dtc_remain_separate(self):
        document = synthetic()
        for row in document['records']:
            if row['id'] in ('d1', 'd2'): row['payload']['volume'] = 0
            if row['id'] == 'si': row['payload']['reported_days_to_cover'] = '9.5'
        self.sources(document)
        si = self.analyze()['rows'][0]['operations']['positioning']['result']['short_interest'][0]
        self.assertEqual(si['provider_reported_days_to_cover'], 9.5)
        self.assertEqual(si['adv']['average_daily_volume'], 0)
        self.assertIsNone(si['adv']['conditional_days_to_cover'])
        self.assertIsNone(si['adv']['days_to_cover'])

    def test_float_class_mismatch_keeps_unknown_without_losing_records(self):
        document = synthetic()
        next(r['payload'] for r in document['records'] if r['id'] == 'float')['share_class'] = 'B'
        self.sources(document); output = self.analyze()['rows'][0]['operations']['positioning']['result']
        self.assertIsNone(output['short_interest'][0]['short_interest_percent_float'])
        self.assertEqual(len(output['evidence']['records']), len(document['records']))
        self.assertTrue(output['issues'])

    def test_every_selected_operation_runs_without_input_mutation(self):
        for operation in self.request['operations']:
            original = module.OPERATIONS[operation]
            with patch.dict(module.OPERATIONS, {operation: original}) as operations:
                with patch.dict(operations, {operation: unittest.mock.Mock(wraps=original)}):
                    self.analyze()
                    operations[operation].assert_called_once()
        before = (self.root / 'original.json').read_bytes()
        self.analyze()
        self.assertEqual((self.root / 'original.json').read_bytes(), before)

    def test_failed_native_operation_is_retained_with_independent_results(self):
        document = synthetic(); document['settings']['print_percentile_threshold'] = 'not-a-number'
        self.sources(document); result = self.analyze()
        self.assertEqual(result['status'], 'PARTIAL_RETAINED_FAILURES')
        self.assertEqual(result['rows'][0]['operations']['flow']['status'], 'FAILED')
        self.assertEqual(result['rows'][0]['operations']['positioning']['status'], 'EXECUTED')
        self.assertIn('error', result['rows'][0]['operations']['flow'])

    def test_no_literal_overrides_results_or_partial_document_binding(self):
        for change in ('override', 'cached_result', 'leaf', 'duplicate', 'unknown_op'):
            old = deepcopy(self.request)
            if change == 'override': self.request['adjustment_basis'] = 'same'
            elif change == 'cached_result': self.request['documents'][0]['result'] = {'conditional_days_to_cover': 4}
            elif change == 'leaf': self.request['documents'][0]['source_ref']['pointer'] = '/market/records/0/payload'
            elif change == 'duplicate': self.request['documents'].append(deepcopy(self.request['documents'][0]))
            else: self.request['operations'] = ['evaluate_arbitrary_code']
            with self.subTest(change=change), self.assertRaises(ValueError): self.analyze()
            self.request = old

    def test_all_originals_pinned_even_when_unselected(self):
        (self.root / 'context.txt').write_text('Changed unselected context')
        with self.assertRaisesRegex(ValueError, 'HASH_MISMATCH'): self.analyze()

    def test_canonical_export_rejects_null_transplant_and_extra_cross_check(self):
        self.mismatched(); output = self.export()
        raw = (output / 'response.json').read_bytes()
        response = json.loads(raw)
        result = response['rows'][0]['result']
        self.assertIsNone(self.adv(result)['conditional_days_to_cover'])
        original = deepcopy(response)
        for mutation in ('quotient_as_dtc', 'extra_cross_check', 'drop_record', 'basis'):
            response = deepcopy(original)
            result = response['rows'][0]['result']
            if mutation == 'quotient_as_dtc': self.adv(result)['conditional_days_to_cover'] = self.adv(result)['unreconciled_share_count_quotient']
            elif mutation == 'extra_cross_check': response['independent_cross_check'] = {'conditional_days_to_cover': 4}
            elif mutation == 'drop_record': result['rows'] = []
            else: self.adv(result)['share_adjustment_comparability'] = 'MATCHED_DECLARED_SHARE_BASIS'
            published = self.root / 'published.json'; published.write_text(json.dumps(response))
            with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError, 'PUBLISHED_STRUCTURED_RESPONSE_DIFFERS'):
                final_report.verify_response(output, published)
        self.assertEqual((output / 'response.json').read_bytes(), raw)

    def test_portable_replay_and_implementation_change_rejection(self):
        self.mismatched(); output = self.export()
        moved = self.root / 'relocated'; shutil.copytree(output, moved)
        self.assertEqual(final_report.verify_response(moved)['status'], 'COMPLETED_CANONICAL_RESPONSE_EXPORT')
        with patch.object(supplied_research, 'implementations', return_value={'changed.py': '0' * 64}):
            with self.assertRaisesRegex(ValueError, 'IMPLEMENTATION_CHANGED'): final_report.verify_response(moved)

    def test_replay_detects_modified_native_result_even_if_inventory_resigned(self):
        self.mismatched(); report = self.compose()
        producer = report / 'sections/000/producer'
        result_path = producer / 'result.json'; result = json.loads(result_path.read_bytes())
        self.adv(result)['conditional_days_to_cover'] = self.adv(result)['unreconciled_share_count_quotient']
        result_path.write_bytes(supplied_research.encode(result))
        receipt_path = producer / 'receipt.json'; receipt = json.loads(receipt_path.read_bytes())
        receipt['artifacts'] = supplied_research.file_inventory(producer)
        receipt_path.write_bytes(supplied_research.encode(receipt))
        with self.assertRaises(ValueError): supplied_research.verify(producer)


if __name__ == '__main__':
    unittest.main()
