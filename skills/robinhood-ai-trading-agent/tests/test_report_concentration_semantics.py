"""Default exports must keep the bound meaning alongside a concentration number."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import quant_workbench as qw
import report_facts as rf
from test_projection_scope import document
from test_planning_comparison_integration import contract


class ConcentrationExportTests(unittest.TestCase):
    def projected(self, complete):
        inputs = document()
        inputs.pop('scenario_flows')
        inputs['source']['identities'] = {'asset': {'issuer_id': 'employer'}}
        inputs['alternatives'] = [{'id': 'held'}]
        if not complete:
            inputs['other_assets'] = None
        bundle = qw.freeze({'schema_version': 1, 'contract': contract(), 'jobs': [
            {'id': 'account', 'operation': 'planning.source_alternatives',
             'inputs': {'document': inputs}}]})
        self.assertEqual(bundle['result']['results'][0]['status'], 'COMPUTED')
        self.assertEqual(qw.implementation_hash(), rf.quant_hash())
        return {fact['source']['pointer']: fact for fact in
                rf.project(json.dumps(bundle).encode(), 'quant')['facts']}

    def test_known_complete_ratio_retains_exact_label_without_exporting_source_text(self):
        facts = self.projected(True)
        stem = '/result/results/0/result/alternatives/0/employer_concentration_evidence/'
        self.assertIsNotNone(facts[stem+'ratio']['value'])
        self.assertEqual(facts[stem+'ratio']['unit'], 'fraction')
        self.assertEqual(facts[stem+'bound_status']['value'], 'EXACT')
        self.assertEqual(facts[stem+'numerator/completeness']['value'], 'COMPLETE')
        self.assertEqual(facts[stem+'denominator/relation']['value'], 'EXACT')

    def test_incomplete_account_keeps_unknown_and_sensitivity_not_a_bound(self):
        facts = self.projected(False)
        stem = '/result/results/0/result/alternatives/0/'
        self.assertIsNone(facts[stem+'employer_concentration_evidence/ratio']['value'])
        self.assertEqual(facts[stem+'employer_concentration_evidence/bound_status']['value'], 'UNKNOWN')
        sensitivity = stem+'identified_assets_employer_concentration_evidence/'
        self.assertIsNotNone(facts[sensitivity+'ratio']['value'])
        self.assertEqual(facts[sensitivity+'value_role']['value'], 'SENSITIVITY_ONLY')
        self.assertEqual(facts[sensitivity+'bound_status']['value'], 'UNKNOWN')


if __name__ == '__main__':
    unittest.main()
