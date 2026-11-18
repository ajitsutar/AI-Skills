"""Original synthetic coverage decisions: prevent both event omission and duplication."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from terminal_return_coverage import assess
import quant_workbench as workbench
import research_workflow


def request(**changes):
    d = {'event_id': 'synthetic:terminal:one', 'event_source_ref': 'fixture/event/one',
         'terminal_return': -0.27, 'series_id': 'synthetic:series:one',
         'series_coverage': 'unknown', 'coverage_evidence': []}
    d.update(changes)
    return d


def known(coverage, **changes):
    return request(series_coverage=coverage,
                   coverage_evidence=[{'source_ref': 'fixture/coverage/one', 'kind': 'event_reconciliation'}],
                   **changes)


class TerminalReturnCoverageTests(unittest.TestCase):
    def test_missing_series_preserves_supplied_event_without_choosing_inclusion(self):
        out = assess(request(series_id=None))
        self.assertEqual(out['status'], 'UNRESOLVED')
        self.assertEqual(out['event']['terminal_return'], -0.27)
        self.assertIsNone(out['additional_application_count'])
        self.assertIsNone(out['combined_return'])

    def test_known_embedding_prevents_second_application_but_retains_event(self):
        out = assess(known('embedded'))
        self.assertEqual(out['action'], 'ALREADY_INCLUDED_DO_NOT_REAPPLY')
        self.assertEqual(out['additional_application_count'], 0)
        self.assertEqual(out['event']['terminal_return'], -0.27)
        self.assertIsNone(out['separate_terminal_return'])

    def test_known_absence_requires_one_separate_component(self):
        out = assess(known('not_embedded'))
        self.assertEqual(out['action'], 'INCLUDE_EVENT_ONCE_SEPARATELY')
        self.assertEqual(out['additional_application_count'], 1)
        self.assertEqual(out['separate_terminal_return'], -0.27)
        self.assertIsNone(out['combined_return'])

    def test_missing_event_value_is_not_zero_or_total_loss(self):
        out = assess(known('not_embedded', terminal_return=None))
        self.assertEqual(out['action'], 'OBTAIN_MISSING_TERMINAL_RETURN')
        self.assertIsNone(out['additional_application_count'])
        self.assertIsNone(out['event']['terminal_return'])

    def test_embedding_proof_does_not_require_reapplying_unknown_separate_value(self):
        out = assess(known('embedded', terminal_return=None))
        self.assertEqual(out['additional_application_count'], 0)
        self.assertIsNone(out['event']['terminal_return'])
        self.assertIsNone(out['combined_return'])

    def test_zero_full_loss_and_gain_are_preserved_not_imputed(self):
        for value in (0, -1, 0.18):
            out = assess(known('not_embedded', terminal_return=value))
            self.assertEqual(out['additional_application_count'], 1)
            self.assertEqual(out['separate_terminal_return'], value)

    def test_endpoint_date_is_not_coverage_evidence(self):
        d = request(series_coverage='embedded', coverage_evidence=[
            {'source_ref': 'fixture/last-price/2024-11-14', 'kind': 'endpoint_date'}])
        with self.assertRaises(ValueError):
            assess(d)
        with self.assertRaises(ValueError):
            assess({**request(), 'last_price_date': '2024-11-14'})

    def test_unknown_coverage_does_not_depend_on_date_text_in_identity(self):
        for suffix in ('2024-11-13', '2024-11-14', '2024-11-15'):
            out = assess(request(series_id='series-ending-' + suffix))
            self.assertEqual(out['status'], 'UNRESOLVED')
            self.assertIsNone(out['additional_application_count'])

    def test_asserted_known_coverage_without_evidence_or_series_is_rejected(self):
        for coverage in ('embedded', 'not_embedded'):
            with self.assertRaises(ValueError):
                assess(request(series_coverage=coverage))
            with self.assertRaises(ValueError):
                assess(known(coverage, series_id=None))

    def test_partial_evidence_does_not_upgrade_unknown_coverage(self):
        d = known('unknown')
        out = assess(d)
        self.assertEqual(out['status'], 'UNRESOLVED')
        self.assertEqual(out['coverage_evidence'], d['coverage_evidence'])

    def test_invalid_values_schemas_and_duplicate_evidence_rejected(self):
        for value in (True, False, float('nan'), float('inf'), -1.01, '-0.27'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                assess(request(terminal_return=value))
        for changes in ({'series_coverage': 'guess'}, {'coverage_evidence': {}}, {'event_id': ''},
                        {'coverage_evidence': [{'source_ref': 'x', 'kind': 'provider_methodology'}] * 2}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                assess(request(**changes))

    def test_input_and_output_are_not_aliased(self):
        d = known('not_embedded'); before = copy.deepcopy(d)
        out = assess(d)
        out['coverage_evidence'][0]['source_ref'] = 'changed'
        out['event']['terminal_return'] = 99
        self.assertEqual(d, before)

    def test_catalog_and_frozen_replay_preserve_three_way_distinction(self):
        docs = [json.loads((ROOT / 'examples/terminal-return-coverage.json').read_bytes()),
                known('embedded'), known('not_embedded')]
        packet = {'schema_version': 1, 'contract': {'prompt': 'Synthetic coverage audit',
                  'purpose': 'compatibility', 'base_currency': 'USD', 'horizon_id': 'audit',
                  'as_of': '2024-12-01T00:00:00Z'}, 'jobs': [
                  {'id': 'coverage-' + str(i), 'operation': 'data.terminal_return_coverage',
                   'inputs': {'document': d}} for i, d in enumerate(docs)]}
        bundle = workbench.freeze(packet)
        rows = bundle['result']['results']
        self.assertEqual([r['status'] for r in rows], ['COMPUTED'] * 3)
        self.assertEqual([r['result']['additional_application_count'] for r in rows], [None, 0, 1])
        self.assertEqual(workbench.verify(bundle)['status'], 'REPLAY_MATCH')
        self.assertIn('data.terminal_return_coverage', json.dumps(research_workflow.catalog()))


if __name__ == '__main__':
    unittest.main()
