"""Synthetic price operands: binding provenance survives workflow calculation."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import price_comparison as prices
import research_workflow as workflow
from test_research_workflow import assumed, selected, encode, plan_for, build, write_artifacts


def inputs():
    basis = {'security_id': 'SYN-common', 'issuer_id': 'SYN', 'currency': 'EUR',
             'share_basis': 'common', 'adjustment_basis': 'post-split'}
    return {'quote': dict(basis, id='spot', value=48),
            'references': [dict(basis, id='estimate', kind='fair_value', value=64)]}


def source_case(arguments=None, values=None):
    values = inputs() if values is None else values
    sources = {'prices': ('prices.json', encode(values), 'supplied_observations')}
    arguments = selected('prices') if arguments is None else arguments
    return plan_for(sources, [{'id': 'compare', 'operation': 'evidence.price_comparison',
                               'arguments': arguments}]), sources


def result_for(plan, sources):
    artifacts = build(plan, sources)
    result = json.loads(artifacts['result.json'])['jobs'][0]
    assert result['status'] == 'COMPUTED', result
    return result['result']['comparisons'][0], artifacts


class PriceBasisTests(unittest.TestCase):
    def test_source_bound_success_and_original_arguments(self):
        plan, sources = source_case()
        row, artifacts = result_for(plan, sources)
        self.assertEqual(row['primary_status'], 'COMPUTED')
        self.assertEqual(row['primary_calculations']['quote_discount_relative_to_reference_pct']['value'], 25)
        self.assertEqual(json.loads(artifacts['jobs/0000/arguments.json']), inputs())
        self.assertNotIn('basis_provenance', json.loads(artifacts['jobs/0000/arguments.json']))
        self.assertEqual(row['basis_evidence_mode'], 'SOURCE_BOUND_PROVENANCE')

    def test_assumed_whole_arguments_are_conditional_and_replayable(self):
        plan, sources = source_case(assumed(inputs()))
        before = copy.deepcopy(plan)
        row, artifacts = result_for(plan, sources)
        self.assertEqual(row['primary_status'], 'UNRESOLVED_BASIS')
        self.assertIsNone(row['primary_calculations'])
        self.assertEqual(row['conditional_sensitivity']['status'], 'CONDITIONAL_COMPUTED')
        self.assertEqual(len(row['assumed_basis_fields']), 10)
        self.assertEqual(plan, before)
        self.assertEqual(artifacts, build(plan, sources))
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / 'run'
            write_artifacts(folder, artifacts)
            self.assertEqual(workflow.verify(folder)['status'], 'WORKFLOW_REPLAY_AND_REPORT_MATCH')

    def test_assumed_reference_ancestor_does_not_upgrade_basis(self):
        args = {'quote': selected('prices', '/quote'), 'references': assumed(inputs()['references'])}
        row, _ = result_for(*source_case(args))
        self.assertEqual(len(row['assumed_basis_fields']), 5)
        self.assertEqual(row['primary_operands']['quote']['share_basis'], 'common')
        self.assertIsNone(row['primary_operands']['reference']['share_basis'])
        self.assertEqual(row['conditional_sensitivity']['status'], 'CONDITIONAL_COMPUTED')

    def test_mixed_leaf_binding_preserves_unknown_primary_and_known_values(self):
        vals = inputs()
        reference = {k: selected('prices', '/references/0/' + k) for k in vals['references'][0]}
        reference['adjustment_basis'] = assumed('post-split', 'Explicit comparability scenario')
        args = {'quote': selected('prices', '/quote'), 'references': [reference]}
        row, _ = result_for(*source_case(args))
        self.assertEqual(row['compatibility']['unknown_dimensions'], ['adjustment_basis'])
        self.assertEqual(row['conditional_sensitivity']['status'], 'CONDITIONAL_COMPUTED')
        self.assertEqual(row['reference']['adjustment_basis'], 'post-split')
        self.assertIsNone(row['primary_operands']['reference']['adjustment_basis'])
        self.assertEqual(row['assumed_basis_fields'][0]['evidence']['reason'], 'Explicit comparability scenario')

    def test_missing_null_and_unknown_do_not_gain_basis(self):
        for value in (None, 'unknown', ''):
            vals = inputs(); vals['references'][0]['share_basis'] = value
            row, _ = result_for(*source_case(values=vals))
            self.assertEqual(row['primary_status'], 'UNRESOLVED_BASIS')
            self.assertIsNone(row['conditional_sensitivity'])
        vals = inputs(); del vals['references'][0]['share_basis']
        row, _ = result_for(*source_case(values=vals))
        self.assertIn('share_basis', row['compatibility']['unknown_dimensions'])

    def test_null_assumption_is_not_filled_by_another_operand(self):
        vals = inputs(); vals['references'][0]['share_basis'] = None
        row, _ = result_for(*source_case(assumed(vals)))
        self.assertEqual(row['conditional_sensitivity']['status'], 'UNRESOLVED_BASIS')
        self.assertIsNone(row['conditional_sensitivity']['calculations'])

    def test_explicit_global_conditional_fills_unknown_only(self):
        vals = inputs(); vals['references'][0]['share_basis'] = None
        args = {'quote': selected('prices', '/quote'), 'references': selected('prices', '/references'),
                'conditional_same_basis': assumed({'label': 'Common-share scenario', 'dimensions': {'share_basis': 'common'}})}
        row, _ = result_for(*source_case(args, vals))
        self.assertEqual(row['primary_status'], 'UNRESOLVED_BASIS')
        self.assertEqual(row['conditional_sensitivity']['status'], 'CONDITIONAL_COMPUTED')
        self.assertIsNone(row['reference']['share_basis'])

    def test_observed_conflict_cannot_be_removed_by_global_assumption(self):
        vals = inputs(); vals['references'][0]['currency'] = 'GBP'
        args = {'quote': selected('prices', '/quote'), 'references': selected('prices', '/references'),
                'conditional_same_basis': assumed({'label': 'EUR sensitivity', 'dimensions': {'currency': 'EUR'}})}
        row, _ = result_for(*source_case(args, vals))
        self.assertEqual(row['conditional_sensitivity']['status'], 'UNRESOLVED_BASIS')
        self.assertIn('currency', row['conditional_sensitivity']['compatibility']['mismatched_dimensions'])

    def test_caller_cannot_inject_workflow_provenance(self):
        vals = inputs(); vals['basis_provenance'] = {}
        plan, sources = source_case(assumed(vals))
        job = json.loads(build(plan, sources)['result.json'])['jobs'][0]
        self.assertEqual(job['status'], 'UNRESOLVED_INPUT_OR_FAILED')
        self.assertIn('WORKFLOW_DERIVED', job['reason'])

    def test_competing_explicit_assumptions_are_not_silently_merged(self):
        vals = inputs()
        vals['conditional_same_basis'] = {'label': 'Preferred-share scenario', 'dimensions': {'share_basis': 'preferred'}}
        row, _ = result_for(*source_case(assumed(vals)))
        conditional = row['conditional_sensitivity']
        self.assertEqual(conditional['status'], 'UNRESOLVED_BASIS')
        self.assertIsNone(conditional['calculations'])
        self.assertEqual(len(conditional['assumption_conflicts']), 2)

    def test_direct_helper_compatibility_and_no_mutation(self):
        vals = inputs(); original = copy.deepcopy(vals)
        row = prices.compare_prices(**vals)['comparisons'][0]
        self.assertEqual(row['primary_status'], 'COMPUTED')
        self.assertEqual(row['basis_evidence_mode'], 'CALLER_SUPPLIED_UNVERIFIED')
        vals['references'][0]['share_basis'] = None
        unknown = copy.deepcopy(vals)
        row = prices.compare_prices(**vals, conditional_same_basis={
            'label': 'Same share scenario', 'dimensions': {'share_basis': 'common'}})['comparisons'][0]
        self.assertEqual(row['primary_status'], 'UNRESOLVED_BASIS')
        self.assertEqual(row['conditional_sensitivity']['status'], 'CONDITIONAL_COMPUTED')
        self.assertEqual(vals, unknown)
        self.assertEqual(original['quote'], vals['quote'])


if __name__ == '__main__':
    unittest.main()
