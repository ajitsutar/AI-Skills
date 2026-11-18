"""Synthetic independent boundary, basis and replay regressions."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from vintage_eligibility import assess
import quant_workbench as workbench
import research_workflow


def request(**changes):
    d = {'value_id': 'synthetic:revenue:original', 'source_ref': 'fixture/statement/original',
         'precision': 'date', 'as_of': '2023-03-19', 'first_publication': '2023-03-18',
         'superseded_at': '2023-06-07', 'basis_from': None, 'basis_until': None}
    d.update(changes)
    return d


class VintageEligibilityTests(unittest.TestCase):
    def test_original_does_not_leak_before_first_release(self):
        self.assertEqual(assess(request(as_of='2023-03-17'))['status'], 'INELIGIBLE')
        self.assertEqual(assess(request())['status'], 'CONDITIONAL_ELIGIBLE')

    def test_both_date_release_boundaries_remain_unknown(self):
        for day in ('2023-03-18', '2023-06-07'):
            with self.subTest(day=day):
                result = assess(request(as_of=day))
                self.assertEqual(result['status'], 'UNRESOLVED')
                self.assertFalse(result['eligible_under_supplied_bounds'])
                self.assertEqual(result['bounds']['first_publication'], '2023-03-18')

    def test_old_and_new_values_have_distinct_windows(self):
        for day, old_status, new_status in (
                ('2023-06-06', 'CONDITIONAL_ELIGIBLE', 'INELIGIBLE'),
                ('2023-06-07', 'UNRESOLVED', 'UNRESOLVED'),
                ('2023-06-08', 'INELIGIBLE', 'CONDITIONAL_ELIGIBLE')):
            self.assertEqual(assess(request(as_of=day))['status'], old_status)
            revised = request(value_id='synthetic:revenue:revised', as_of=day,
                              first_publication='2023-06-07', superseded_at=None)
            self.assertEqual(assess(revised)['status'], new_status)

    def test_basis_does_not_replace_publication_lower_bound(self):
        d = request(basis_from='2023-01-01', basis_until='2023-04-02')
        self.assertEqual(assess({**d, 'as_of': '2023-02-01'})['status'], 'INELIGIBLE')
        self.assertEqual(assess({**d, 'as_of': '2023-04-01'})['status'], 'CONDITIONAL_ELIGIBLE')
        self.assertEqual(assess({**d, 'as_of': '2023-04-02'})['status'], 'INELIGIBLE')

    def test_later_recast_is_not_available_on_basis_start(self):
        d = request(basis_from='2023-07-02', first_publication='2023-07-04', superseded_at=None)
        self.assertEqual(assess({**d, 'as_of': '2023-07-02'})['status'], 'INELIGIBLE')
        self.assertEqual(assess({**d, 'as_of': '2023-07-04'})['status'], 'UNRESOLVED')
        self.assertEqual(assess({**d, 'as_of': '2023-07-05'})['status'], 'CONDITIONAL_ELIGIBLE')

    def test_disjoint_basis_and_publication_never_yield_eligible(self):
        d = request(basis_until='2023-03-17')
        for day in ('2023-03-16', '2023-03-17', '2023-03-18', '2023-06-06'):
            self.assertEqual(assess({**d, 'as_of': day})['status'], 'INELIGIBLE')

    def test_unknown_first_release_is_not_an_unbounded_past(self):
        result = assess(request(first_publication=None))
        self.assertEqual(result['status'], 'UNRESOLVED')
        self.assertIsNone(result['bounds']['first_publication'])

    def test_timestamp_cutoffs_include_first_exclude_supersession(self):
        d = request(precision='timestamp', first_publication='2023-03-18T09:30:00-04:00',
                    superseded_at='2023-06-07T13:30:00Z')
        for cutoff, status in [('2023-03-18T13:29:59.999999Z', 'INELIGIBLE'),
                               ('2023-03-18T13:30:00Z', 'CONDITIONAL_ELIGIBLE'),
                               ('2023-06-07T13:29:59.999999Z', 'CONDITIONAL_ELIGIBLE'),
                               ('2023-06-07T13:30:00Z', 'INELIGIBLE')]:
            self.assertEqual(assess({**d, 'as_of': cutoff})['status'], status)

    def test_equal_publication_dates_are_never_an_interior_window(self):
        for day, status in [('2023-03-17', 'INELIGIBLE'), ('2023-03-18', 'UNRESOLVED'),
                             ('2023-03-19', 'INELIGIBLE')]:
            self.assertEqual(assess(request(as_of=day, superseded_at='2023-03-18'))['status'], status)

    def test_rejects_unknown_fields_mixed_precision_bad_order_and_naive_times(self):
        for changes in ({'extra': 1}, {'as_of': '2023-03-19T00:00:00Z'},
                        {'first_publication': '2023-02-30'}, {'first_publication': True},
                        {'superseded_at': '2023-01-01'}, {'basis_from': '2023-05-01', 'basis_until': '2023-05-01'},
                        {'precision': 'timestamp', 'as_of': '2023-03-19T00:00:00'},
                        {'source_ref': ''}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                assess(request(**changes))

    def test_no_mutation_and_all_constraints_retained(self):
        d = request(as_of='2023-03-18', basis_until='2023-03-17')
        before = copy.deepcopy(d)
        result = assess(d)
        self.assertEqual(d, before)
        self.assertEqual(result['status'], 'INELIGIBLE')
        self.assertIn('UNRESOLVED', [x['result'] for x in result['constraints']])
        self.assertEqual(len(result['constraints']), 4)

    def test_public_example_and_operation_replay(self):
        d = json.loads((ROOT / 'examples/vintage-eligibility.json').read_text())
        packet = {'schema_version': 1, 'contract': {'prompt': 'Synthetic publication audit',
                  'purpose': 'compatibility', 'base_currency': 'USD', 'horizon_id': 'audit',
                  'as_of': '2024-09-01T00:00:00Z'},
                  'jobs': [{'id': 'bounds', 'operation': 'data.vintage_eligibility', 'inputs': {'document': d}}]}
        bundle = workbench.freeze(packet)
        row = bundle['result']['results'][0]
        self.assertEqual(row['status'], 'COMPUTED')
        self.assertEqual(row['result']['status'], 'UNRESOLVED')
        self.assertEqual(workbench.verify(bundle)['status'], 'REPLAY_MATCH')
        self.assertIn('data.vintage_eligibility', json.dumps(research_workflow.catalog()))


if __name__ == '__main__':
    unittest.main()
