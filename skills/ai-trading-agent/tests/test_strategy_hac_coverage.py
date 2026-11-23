"""Separate design eligibility from Bartlett lag arithmetic in the normal workflow."""
import json
import unittest
import test_strategy_economics as fixtures


class StrategyHacCoverageTests(unittest.TestCase):
    def setUp(self):
        case = fixtures.StrategyEconomicsTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        self.case = case
        self.sample = case.options['answer_controls']['sample']
        self.estimate = case.options['strategy_registration']['uncertainty']['estimator']

    def enter(self, name):
        out = self.case.base.directory/name
        result = self.case.base.entry(self.case.options, '--scoped-design', out)
        return result, out

    def test_same_estimator_distinct_policy_floors(self):
        from quant_validation import hac_mean
        data = [.001, .002, -.001, 0., .003, .001, -.002, .002]
        self.assertGreater(hac_mean(data, 3)['standard_error_hac'], 0)
        del self.sample['rationale']
        self.estimate['lag_observations'] = 3
        for minimum in (8, 46):
            with self.subTest(minimum=minimum):
                self.sample['minimum_observations'] = minimum
                result, out = self.enter('policy-' + str(minimum))
                self.assertEqual(result.returncode, 0, result.stderr)
                row = json.loads((out/'answer-rows.json').read_bytes())[0]
                self.assertEqual(row['hac_coverage'], {'registered_observation_floor':minimum, 'lag_observations':3,
                                 'minimum_for_all_lag_products':4,'pairs_at_longest_lag_at_registered_floor':minimum-3})
                self.assertIn(row['answer_controls']['sample']['rationale'], (out/'answer.md').read_text(encoding='utf8'))
                checked = fixtures.fixtures.fixtures.contracts.verify(out,out/'answer.md',out/'answer-rows.json')
                self.assertEqual(checked['status'], 'RETAINED_BYTES_AND_REPLAY_CONSISTENT')

    def test_false_caller_rationale_rejected_and_previous_interface_readable(self):
        self.sample['rationale'] = 'The study floor is mathematically required to compute any bound.'
        result, out = self.enter('contradiction')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('SCOPED_HAC_RATIONALE_IS_GENERATED', result.stderr)
        self.assertFalse(out.exists())
        old, legacy = self.case.entry(self.case.options, 'legacy')
        self.assertEqual(old.returncode, 0, old.stderr)
        self.assertNotIn('hac_coverage',json.loads((legacy/'answer-rows.json').read_bytes())[0])

    def test_lag_must_fit_the_registered_minimum(self):
        self.sample.pop('rationale')
        self.sample['minimum_observations'] = 3
        self.estimate['lag_observations'] = 3
        result, out = self.enter('invalid-lag')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('FIXED_HAC_LAG_REQUIRED', result.stderr)
        self.assertFalse(out.exists())
