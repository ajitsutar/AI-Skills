"""Forward declarations need chronology, retained evidence and implementation identity."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import forward_evidence as forward


def evidence(text):
    return {'source_text': text, 'sha256': hashlib.sha256(text.encode()).hexdigest()}


def bind(row):
    row = copy.deepcopy(row)
    row.pop('evidence', None)
    row['evidence'] = evidence(json.dumps(row, sort_keys=True))
    return row


def document():
    source = evidence('# fictional inert implementation source\n')
    impl = {'implementation_sha256': source['sha256'], 'source_evidence': source,
            'strategy_id': 'fictional-trailing-rule', 'execution_rule': 'next_bar_open',
            'known_at': '2025-11-01T00:00:00Z'}
    row = {'id': 'observation-a', 'decision_at': '2026-01-05T16:00:00Z',
           'outcome_at': '2026-01-06T16:00:00Z', 'available_at': '2026-01-06T17:00:00Z',
           'data_kind': 'forward_paper_observation',
           'implementation_sha256': {'champion': source['sha256'], 'challenger': source['sha256']},
           'champion_net_return': .01, 'challenger_net_return': .02}
    return {'as_of': '2026-10-13T16:00:00Z',
            'protocol': {'start': '2026-01-01T00:00:00Z', 'end': '2026-10-01T00:00:00Z',
                         'frozen_at': '2025-12-01T00:00:00Z', 'minimum_observations': 2},
            'implementations': {'champion': copy.deepcopy(impl), 'challenger': copy.deepcopy(impl)},
            'observations': [bind(row)], 'changes': []}


class ForwardEvidenceTests(unittest.TestCase):
    def test_consistent_declaration_counts_without_proving_genuine_observation(self):
        doc = document()
        result = forward.assess(doc)
        self.assertEqual(result['admissible_declared_forward_count'], 1)
        self.assertEqual(result['additional_admissible_observations_needed'], 1)
        self.assertFalse(result['minimum_count_met'])
        self.assertEqual(result['implementation_comparison'], 'SAME_SUPPLIED_CODE_BYTES')
        self.assertFalse(result['genuine_forward_proven'])
        self.assertEqual(result['fill_agreement'], 'NOT_ESTABLISHED')
        self.assertEqual(doc, document())

    def test_chronology_failures_do_not_count_toward_minimum(self):
        for field, value, reason in (
                ('decision_at', '2025-11-01T00:00:00Z', 'BEFORE_PROTOCOL_WINDOW'),
                ('available_at', '2026-01-01T00:00:00Z', 'AVAILABLE_BEFORE_OUTCOME'),
                ('available_at', '2027-01-01T00:00:00Z', 'NOT_AVAILABLE_AS_OF'),
                ('outcome_at', '2026-01-04T00:00:00Z', 'OUTCOME_BEFORE_DECISION'),
                ('data_kind', 'synthetic', 'NOT_DECLARED_FORWARD_PAPER_OBSERVATION')):
            with self.subTest(field=field, value=value):
                doc = document()
                doc['observations'][0][field] = value
                doc['observations'][0] = bind(doc['observations'][0])
                result = forward.assess(doc)
                self.assertEqual(result['admissible_declared_forward_count'], 0)
                self.assertEqual(result['additional_admissible_observations_needed'], 2)
                self.assertIn(reason, result['rows'][0]['reasons'])

    def test_selected_payload_change_cannot_borrow_other_source_hash(self):
        doc = document()
        doc['observations'][0]['challenger_net_return'] = .99
        result = forward.assess(doc)
        self.assertEqual(result['admissible_declared_forward_count'], 0)
        self.assertIn('OBSERVATION_EVIDENCE_MISMATCH', result['rows'][0]['reasons'])

    def test_matching_entry_strings_are_not_implementation_agreement(self):
        doc = document()
        doc['implementations'] = {'champion': {'entry': 'next completed bar'},
                                  'challenger': {'entry': 'next completed bar'}}
        result = forward.assess(doc)
        self.assertEqual(result['implementation_comparison'], 'NOT_ESTABLISHED')
        self.assertEqual(result['admissible_declared_forward_count'], 0)
        self.assertEqual(result['change_list_completeness'], 'NOT_ESTABLISHED_BY_HASH_OR_ENTRY_STRINGS')

    def test_changed_code_and_execution_rule_are_reported_not_reduced_to_forecast_change(self):
        doc = document()
        new_source = evidence('# different inert implementation source\n')
        challenger = doc['implementations']['challenger']
        challenger.update(source_evidence=new_source, implementation_sha256=new_source['sha256'],
                          execution_rule='next_completed_close', forecast_volatility_daily=.018)
        doc['changes'] = ['forecast volatility only']
        result = forward.assess(doc)
        self.assertEqual(result['implementation_comparison'], 'DIFFERENT_SUPPLIED_CODE_BYTES')
        self.assertIn('execution_rule', [d['field'] for d in result['configuration_differences']])
        self.assertIn('CHALLENGER_IMPLEMENTATION_MISMATCH', result['rows'][0]['reasons'])
        self.assertEqual(result['declared_change_list'], ['forecast volatility only'])

    def test_source_tampering_and_date_only_rows_do_not_establish_admissibility(self):
        doc = document()
        doc['implementations']['champion']['source_evidence']['source_text'] += '# changed'
        doc['observations'][0]['decision_at'] = '2026-01-05'
        doc['observations'][0] = bind(doc['observations'][0])
        result = forward.assess(doc)
        self.assertEqual(result['admissible_declared_forward_count'], 0)
        self.assertIn('DECISION_AT_EXACT_TIMESTAMP_MISSING', result['rows'][0]['reasons'])
        self.assertEqual(result['implementations']['champion']['status'], 'NOT_ESTABLISHED')

    def test_raw_paper_study_preserves_synthetic_pre_window_contradictions(self):
        study = {'data_kind': 'fictional_offline_test', 'frozen_at': '2024-12-01T00:00:00Z',
                 'base_strategy': {'paper_start': '2026-10-14', 'paper_end': '2027-04-14', 'entry': 'next bar open'},
                 'prespecified_criteria': {'minimum_paper_observations': 60},
                 'champion': {'entry': 'next completed bar', 'forecast_volatility_daily': .02},
                 'challenger': {'entry': 'next completed bar', 'forecast_volatility_daily': .018},
                 'paper_observations': [{'date': '2026-09-' + str(i).zfill(2), 'available_after': '2026-08-01',
                                          'champion_net_return': .01, 'challenger_net_return': .02}
                                         for i in range(1, 11)]}
        original = copy.deepcopy(study)
        result = forward.paper_study(study, '2026-10-13T16:00:00Z')
        self.assertEqual(result['admissible_declared_forward_count'], 0)
        self.assertEqual(result['additional_admissible_observations_needed'], 60)
        self.assertEqual(result['supplied_observations'], 10)
        for row in result['rows']:
            self.assertIn('BEFORE_PROTOCOL_WINDOW', row['reasons'])
            self.assertIn('AVAILABLE_BEFORE_OUTCOME', row['reasons'])
            self.assertIn('NOT_DECLARED_FORWARD_PAPER_OBSERVATION', row['reasons'])
        self.assertEqual(result['implementation_comparison'], 'NOT_ESTABLISHED')
        self.assertEqual(result['declared_base_entry'], 'next bar open')
        self.assertEqual(study, original)

    def test_preregistration_after_start_invalidates_eligibility(self):
        doc = document()
        doc['protocol']['frozen_at'] = '2026-01-02T00:00:00Z'
        result = forward.assess(doc)
        self.assertEqual(result['admissible_declared_forward_count'], 0)
        self.assertIn('PROTOCOL_FROZEN_AFTER_START', result['protocol_reasons'])

    def test_parent_synthetic_kind_cannot_be_overridden_by_forward_row_label(self):
        doc = document()
        doc['data_kind'] = 'fictional_offline_test'
        result = forward.assess(doc)
        self.assertEqual(result['admissible_declared_forward_count'], 0)
        self.assertIn('PARENT_DATA_NOT_FORWARD_OBSERVATION', result['rows'][0]['reasons'])

    def test_late_implementation_and_missing_returns_are_not_forward_pairs(self):
        doc = document()
        doc['implementations']['challenger']['known_at'] = '2026-02-01T00:00:00Z'
        del doc['observations'][0]['champion_net_return']
        doc['observations'][0] = bind(doc['observations'][0])
        result = forward.assess(doc)
        self.assertEqual(result['admissible_declared_forward_count'], 0)
        self.assertIn('CHAMPION_NET_RETURN_MISSING_OR_INVALID', result['rows'][0]['reasons'])
        self.assertIn('CHALLENGER_IMPLEMENTATION_KNOWN_AFTER_FREEZE_OR_DECISION', result['rows'][0]['reasons'])

    def test_conflicting_duplicate_identity_never_selects_first_row(self):
        doc = document()
        doc['observations'].append(copy.deepcopy(doc['observations'][0]))
        doc['observations'][1]['challenger_net_return'] = .2
        doc['observations'][1] = bind(doc['observations'][1])
        result = forward.assess(doc)
        self.assertEqual(result['admissible_declared_forward_count'], 0)
        self.assertTrue(all('DUPLICATE_OBSERVATION_ID' in row['reasons'] for row in result['rows']))

    def test_zero_duration_forward_pair_is_not_a_new_outcome(self):
        doc = document()
        doc['observations'][0]['outcome_at'] = doc['observations'][0]['decision_at']
        doc['observations'][0] = bind(doc['observations'][0])
        result = forward.assess(doc)
        self.assertEqual(result['admissible_declared_forward_count'], 0)
        self.assertIn('OUTCOME_NOT_AFTER_DECISION', result['rows'][0]['reasons'])

    def test_malformed_native_model_summary_is_missing_identity_not_execution(self):
        result = forward.paper_study({'base_strategy': {}, 'champion': 'not code evidence',
                                     'challenger': None}, '2026-10-13T16:00:00Z')
        self.assertEqual(result['implementation_comparison'], 'NOT_ESTABLISHED')
        self.assertEqual(result['entry_rule_strings'], {'champion': None, 'challenger': None})


if __name__ == '__main__':
    unittest.main()
