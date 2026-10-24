import copy
from contextlib import nullcontext
from datetime import datetime, timezone
import hashlib
import io
import math
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import sentiment_toolkit as s


def record(key='a', text='Acme revenue beat expectations.', hour='12'):
    return {'id': key, 'text': text, 'source': 'issuer',
            'published_at': f'2026-01-01T{hour}:00:00Z', 'available_at': f'2026-01-01T{hour}:00:00Z'}


def fixture():
    return {'as_of': '2026-01-01T14:00:00Z', 'half_life_hours': 1,
            'entities': {'ACME': ['Acme'], 'BETA': ['Beta']}, 'required_aspects': ['revenue'],
            'records': [record()]}


def supplied(row, positive=.8, negative=.1):
    annotation = {'start': 0, 'end': len(row['text']), 'entity': 'ACME', 'aspect': 'revenue'}
    annotation['prediction'] = {'binding_sha256': s.binding(row, annotation), 'model_id': 'fixture-model',
                                'model_revision': 'frozen-1', 'computed_at': row['available_at'],
                                'probabilities': {'positive': positive, 'negative': negative, 'neutral': 1 - positive - negative}}
    row['annotations'] = [annotation]
    return row


class SentimentToolkitTests(unittest.TestCase):
    def test_positive_vs_missing_and_immutable(self):
        data = fixture(); original = copy.deepcopy(data)
        result = s.analyze(data)
        self.assertEqual(result['summary'][0]['polarity'], 1)
        self.assertEqual(result['summary'][1]['status'], 'MISSING')
        self.assertEqual(data, original)
        self.assertIsNone(result['scores'][0]['probabilities'])

    def test_time_decay_weighted_hand_math(self):
        data = fixture()
        data['records'].append(record('b', 'Acme revenue misses expectations.', '13'))
        result = s.analyze(data)
        self.assertAlmostEqual(result['summary'][0]['polarity'], -1 / 3)
        self.assertTrue(result['summary'][0]['contradictory'])
        self.assertEqual([r['weight'] for r in result['scores']], [.25, .5])

    def test_source_weights(self):
        data = fixture(); data['records'].append(record('b', 'Acme revenue misses expectations.'))
        data['records'][1]['source'] = 'social'; data['source_weights'] = {'issuer': 3, 'social': 1}
        self.assertAlmostEqual(s.analyze(data)['summary'][0]['polarity'], .5)

    def test_publication_and_observed_cutoffs(self):
        data = fixture(); data['records'][0]['available_at'] = '2026-01-01T15:00:00Z'
        result = s.analyze(data)
        self.assertEqual(result['excluded_records'][0]['reason'], 'FUTURE_OR_UNAVAILABLE')
        self.assertIsNone(result['summary'][0]['polarity'])

    def test_bad_timestamp_and_order(self):
        data = fixture(); data['as_of'] = '2026-01-01T14:00:00'
        with self.assertRaisesRegex(ValueError, 'TIMEZONE_REQUIRED'): s.analyze(data)
        data = fixture(); data['records'][0]['available_at'] = '2026-01-01T11:00:00Z'
        with self.assertRaisesRegex(ValueError, 'AVAILABLE_BEFORE'): s.analyze(data)

    def test_ambiguity_not_arbitrarily_assigned(self):
        data = fixture(); data['records'][0]['text'] = 'Acme beats Beta revenue expectations.'
        result = s.analyze(data)
        self.assertEqual(result['scores'], [])
        self.assertEqual(result['omitted_spans'][0]['reason'], 'ENTITY_OR_ASPECT_AMBIGUOUS')
        data['records'][0]['text'] = 'Acme revenue beats but debt rises.'
        self.assertEqual(s.analyze(data)['scores'], [])

    def test_multi_aspect_separate_clauses(self):
        data = fixture(); data['records'][0]['text'] = 'Acme revenue beats; Acme debt rises.'
        result = s.analyze(data)
        by_aspect = {r['aspect']: r['polarity'] for r in result['summary'] if r['entity'] == 'ACME'}
        self.assertEqual(by_aspect, {'balance_sheet': -1, 'revenue': 1})

    def test_negation_and_no_hit(self):
        self.assertEqual(s.baseline('Acme revenue did not beat', 'revenue')['polarity'], -1)
        self.assertIsNone(s.baseline('Acme revenue announcement', 'revenue')['polarity'])
        self.assertEqual(s.baseline('Acme revenue strong and weak', 'revenue')['polarity'], 0)

    def test_debt_decline_and_multi_balance_target_abstention(self):
        self.assertEqual(s.baseline('Acme debt declined', 'balance_sheet')['polarity'], 1)
        self.assertEqual(s.baseline('Acme debt did not decline', 'balance_sheet')['polarity'], -1)
        self.assertEqual(s.baseline('Acme debt decreases', 'balance_sheet')['polarity'], 1)
        self.assertEqual(s.baseline('Acme debt grew', 'balance_sheet')['polarity'], -1)
        result = s.baseline('Acme cash rises as debt falls', 'balance_sheet')
        self.assertIsNone(result['polarity'])
        self.assertEqual(result['status'], 'UNSCORED_AMBIGUOUS_BALANCE_TARGETS')

    def test_entity_mapping_order_does_not_change_result(self):
        data = fixture()
        first = s.analyze(data)
        data['entities'] = dict(reversed(list(data['entities'].items())))
        second = s.analyze(data)
        self.assertEqual(first, second)
        self.assertEqual(s.matches('Beta and Acme', data['entities']), ['ACME', 'BETA'])

    def test_exact_duplicate_and_same_words_different_date(self):
        data = fixture(); data['records'].append(record('b'))
        result = s.analyze(data)
        self.assertEqual(len(result['events']), 1)
        self.assertEqual(len(result['scores']), 2)
        data['records'][1]['published_at'] = data['records'][1]['available_at'] = '2026-01-01T13:00:00Z'
        self.assertEqual(len(s.analyze(data)['events']), 2)

    def test_reviewed_events_cap_weight_preserve_conflict(self):
        data = fixture(); data['records'].append(record('b', 'Acme revenue misses expectations.'))
        for row in data['records']:
            row.update(reviewed_event_id='same-announcement', event_review_note='Fictional matching release.')
        result = s.analyze(data)
        self.assertEqual(len(result['events']), 1)
        self.assertEqual(result['events'][0]['weight'], .25)
        self.assertEqual(result['summary'][0]['polarity'], 0)
        self.assertTrue(result['summary'][0]['contradictory'])
        data['records'].append({**data['records'][0], 'id': 'syndicated-copy'})
        self.assertEqual(s.analyze(data)['summary'][0]['polarity'], 0)

    def test_supplied_binding_and_provenance(self):
        data = fixture(); supplied(data['records'][0])
        result = s.analyze(data)
        self.assertAlmostEqual(result['summary'][0]['polarity'], .7)
        self.assertEqual(result['scores'][0]['method'], 'supplied_probabilities_not_independently_inferred')
        data['records'][0]['text'] += ' Changed.'
        with self.assertRaisesRegex(ValueError, 'BINDING_MISMATCH'): s.analyze(data)

    def test_supplied_future_prediction_not_replayed(self):
        data = fixture(); supplied(data['records'][0])
        data['records'][0]['annotations'][0]['prediction']['computed_at'] = '2026-01-02T00:00:00Z'
        result = s.analyze(data)
        self.assertIsNone(result['summary'][0]['polarity'])
        self.assertEqual(result['omitted_spans'][0]['reason'], 'PREDICTION_NOT_AVAILABLE_AT_CUTOFF')

    def test_bad_probability_and_revision(self):
        data = fixture(); supplied(data['records'][0])
        prediction = data['records'][0]['annotations'][0]['prediction']
        prediction['probabilities']['positive'] = .9
        with self.assertRaisesRegex(ValueError, 'SUM_TO_ONE'): s.analyze(data)
        prediction['model_revision'] = 'main'
        with self.assertRaisesRegex(ValueError, 'PINNED_MODEL'): s.analyze(data)

    def test_zero_source_weight_does_not_mean_neutral(self):
        data = fixture(); data['source_weights'] = {'issuer': 0}
        self.assertEqual(s.analyze(data)['summary'][0]['status'], 'MISSING')

    def test_backtest_next_interval_costs_hand_math(self):
        doc = {'sentiment': fixture(), 'entity': 'ACME', 'aspect': 'revenue',
               'cost_bps_per_unit_turnover': 100,
               'periods': [{'decision_at': '2026-01-01T11:00:00Z', 'start': '2026-01-01T11:01:00Z',
                            'end': '2026-01-01T12:00:00Z', 'asset_return': .5},
                           {'decision_at': '2026-01-01T12:00:00Z', 'start': '2026-01-01T12:01:00Z',
                            'end': '2026-01-01T13:00:00Z', 'asset_return': .1}]}
        result = s.backtest(doc)
        self.assertEqual([r['exposure'] for r in result['periods']], [0, 1])
        self.assertAlmostEqual(result['net_total_return'], .99 * 1.1 * .99 - 1)
        self.assertAlmostEqual(result['buy_hold_net_total_return'], .99 * 1.5 * 1.1 * .99 - 1)
        self.assertEqual(result['missing_signal_periods'], 1)
        doc['periods'][1]['start'] = doc['periods'][1]['decision_at']
        with self.assertRaisesRegex(ValueError, 'CAUSAL'): s.backtest(doc)

    def test_calibration_hand_math(self):
        result = s.calibrate({'bins': 2, 'rows': [{'id': 'a', 'label': 'positive',
            'model_id': 'test', 'model_revision': '1', 'predicted_at': '2026-01-01T00:00:00Z',
            'label_available_at': '2026-01-02T00:00:00Z',
            'probabilities': {'positive': .8, 'negative': .1, 'neutral': .1}}]})
        self.assertAlmostEqual(result['multiclass_brier_sum'], .06)
        self.assertAlmostEqual(result['log_loss'], -math.log(.8))
        self.assertAlmostEqual(result['expected_calibration_error'], .2)

    def test_label_leak_rejected(self):
        with self.assertRaisesRegex(ValueError, 'PRECEDE_LABEL'):
            s.calibrate({'rows': [{'id': 'a', 'label': 'positive', 'model_id': 'test', 'model_revision': '1',
                'predicted_at': '2026-01-02T00:00:00Z', 'label_available_at': '2026-01-01T00:00:00Z'}]})

    def test_optional_model_missing_no_download(self):
        result = s.infer_local({'model': {'directory': str(Path(__file__).parent / 'nonexistent-model-fixture-97629'),
            'license': {'identifier': 'user-supplied', 'source_url': 'https://example.test/license',
                        'intended_use': 'test', 'weights_terms': 'user-reviewed',
                        'training_data_terms_review': 'user-reviewed', 'use_permitted_attestation': True}}})
        self.assertEqual(result['status'], 'UNAVAILABLE')
        self.assertEqual(result['reason'], 'LOCAL_MODEL_DIRECTORY_MISSING')

    def test_model_license_permission_required(self):
        with self.assertRaisesRegex(ValueError, 'MODEL_LICENSE'):
            s.infer_local({'model': {'directory': 'missing'}})

    def test_optional_prediction_receipt_is_after_inference_completion(self):
        # Stub the optional classifier only: verify lifecycle timing without any model/runtime install.
        directory = MagicMock()
        directory.resolve.return_value = directory
        directory.is_dir.return_value = True
        files = []
        for name in ('config.json', 'model.safetensors'):
            file = MagicMock()
            file.relative_to.return_value = Path(name)
            file.is_file.return_value = True
            file.is_symlink.return_value = False
            file.resolve.return_value.is_relative_to.return_value = True
            file.open.return_value = io.BytesIO(b'fixture')
            files.append(file)
        directory.rglob.return_value = files
        classifier = MagicMock()
        classifier.config = SimpleNamespace(num_labels=3, id2label={0: 'negative', 1: 'neutral', 2: 'positive'}, max_position_embeddings=512)
        tokenizer = lambda *args, **kwargs: {'input_ids': SimpleNamespace(shape=(1, 5))}
        transformers = SimpleNamespace(
            AutoTokenizer=SimpleNamespace(from_pretrained=lambda *a, **k: tokenizer),
            AutoModelForSequenceClassification=SimpleNamespace(from_pretrained=lambda *a, **k: (classifier, {})))
        torch = SimpleNamespace(set_num_threads=lambda n: None, use_deterministic_algorithms=lambda v: None,
                                no_grad=nullcontext, softmax=lambda *a, **k: [SimpleNamespace(tolist=lambda: [.2, .3, .5])])
        row = record()
        doc = {'model': {'directory': 'fixture', 'id': 'fixture', 'revision': '1',
            'files_sha256': {name: hashlib.sha256(b'fixture').hexdigest() for name in ('config.json', 'model.safetensors')},
            'package_versions': {name: '1' for name in ('torch', 'transformers', 'tokenizers', 'safetensors')},
            'label_mapping': {'0': 'negative', '1': 'neutral', '2': 'positive'},
            'license': {'identifier': 'fixture', 'source_url': 'https://example.test/license', 'intended_use': 'fixture',
                        'weights_terms': 'fixture', 'training_data_terms_review': 'fixture', 'use_permitted_attestation': True}},
            'items': [{'record': row, 'annotation': {'entity': 'ACME', 'aspect': 'revenue', 'start': 0, 'end': len(row['text'])}}]}
        before = datetime(2026, 1, 1, 13, tzinfo=timezone.utc)
        completed = datetime(2026, 1, 1, 14, tzinfo=timezone.utc)
        with patch.object(s, 'Path', return_value=directory), patch.object(s.importlib.metadata, 'version', return_value='1'), \
             patch.dict(sys.modules, {'torch': torch, 'transformers': transformers}), patch.object(s, 'datetime', wraps=datetime) as clock:
            clock.now.side_effect = [before, completed]
            result = s.infer_local(doc)
        self.assertEqual(result['predictions'][0]['prediction']['computed_at'], completed.isoformat())

    def test_nan_and_boolean_not_accepted_as_numeric(self):
        data = fixture(); data['half_life_hours'] = float('nan')
        with self.assertRaises(ValueError): s.analyze(data)
        data['half_life_hours'] = True
        with self.assertRaises(ValueError): s.analyze(data)

    def test_prior_only_trend(self):
        data = fixture()
        data['records'].append(record('b', 'Acme revenue misses.', '13'))
        result = s.trend({'sentiment': data, 'entity': 'ACME', 'aspect': 'revenue',
                          'cutoffs': ['2026-01-01T12:00:00Z', '2026-01-01T13:00:00Z', '2026-01-01T14:00:00Z']})
        self.assertEqual(result['rows'][0]['prior_observation_count'], 0)
        self.assertAlmostEqual(result['rows'][2]['prior_mean'], 1 / 3)
        self.assertAlmostEqual(result['rows'][2]['prior_sample_sd'], math.sqrt(8 / 9))
        self.assertAlmostEqual(result['rows'][2]['prior_only_z_score'], -1 / math.sqrt(2))

    def test_fixed_feature_fusion_future_missing_and_hand_math(self):
        base = {'observed_at': '2026-01-01T12:00:00Z', 'available_at': '2026-01-01T12:00:00Z',
                'normalization': 'provided normalized fixture', 'evidence_sha256': 'a' * 64}
        result = s.fuse({'as_of': '2026-01-01T14:00:00Z', 'features': [
            {**base, 'name': 'sentiment', 'weight': 3, 'value': .6},
            {**base, 'name': 'volatility', 'weight': 1, 'value': -.2},
            {**base, 'name': 'orderbook', 'weight': 1, 'value': .9, 'available_at': '2026-01-01T15:00:00Z'}]})
        self.assertAlmostEqual(result['composite'], .4)
        self.assertAlmostEqual(result['weight_coverage'], .8)
        self.assertEqual(result['status'], 'PARTIAL')

    def test_golden_analyze_replay(self):
        root = Path(__file__).resolve().parents[1] / 'examples'
        doc = json.loads((root / 'sentiment-offline.json').read_text())
        expected = json.loads((root / 'sentiment-offline.expected.json').read_text())
        self.assertEqual(s.analyze(doc), expected)

    def test_golden_backtest_replay(self):
        root = Path(__file__).resolve().parents[1] / 'examples'
        doc = json.loads((root / 'sentiment-backtest.json').read_text())
        expected = json.loads((root / 'sentiment-backtest.expected.json').read_text())
        self.assertEqual(s.backtest(doc), expected)

    def test_default_resolution_deep_and_immutable(self):
        doc = {'sentiment': fixture(), 'entity': 'ACME', 'aspect': 'revenue', 'periods': [{'asset_return': .1}]}
        original = copy.deepcopy(doc)
        resolved = s.resolve_document('backtest', doc)
        self.assertEqual(resolved['periods'][0]['cash_return'], 0)
        self.assertEqual(resolved['sentiment']['source_weights'], {'issuer': 1.0})
        self.assertEqual(resolved['signal_policy'], 'long_cash')
        self.assertEqual(doc, original)

    def test_misspelled_options_rejected_instead_of_using_default(self):
        doc = fixture(); doc['half_life_hour'] = 1
        with self.assertRaisesRegex(ValueError, 'UNKNOWN_ANALYZE_DOCUMENT_FIELDS'):
            s.analyze(doc)
        with self.assertRaisesRegex(ValueError, 'UNKNOWN_ANALYZE_DOCUMENT_FIELDS'):
            s.resolve_document('analyze', doc)

    def test_similar_opposite_claim_is_flagged_never_collapsed(self):
        data = fixture()
        data['records'] = [record('a', 'Acme revenue beat the carefully updated analyst consensus for this quarter.'),
                           record('b', 'Acme revenue not beat the carefully updated analyst consensus for this quarter.')]
        result = s.analyze(data)
        self.assertEqual(len(result['events']), 2)
        self.assertTrue(result['possible_duplicates'])
        self.assertTrue(result['summary'][0]['contradictory'])


if __name__ == '__main__':
    unittest.main()
