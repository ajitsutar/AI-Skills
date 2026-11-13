import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import institutional_research as research


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode()).hexdigest()


class WorkflowContractTests(unittest.TestCase):
    def example(self, evaluation=False):
        name = 'institutional-evaluation-input.json' if evaluation else 'institutional-event-input.json'
        document = json.loads((ROOT / 'examples' / name).read_text(encoding='utf8'))
        document['workflow'] = document.pop('pilot')
        return document

    def test_plan_binds_exact_supplied_protocol_and_original_input(self):
        document = self.example()
        original = copy.deepcopy(document)
        result = research.plan(document)
        self.assertEqual(document, original)
        self.assertEqual(result['workflow'], document['workflow'])
        self.assertEqual(result['workflow_sha256'], digest(document['workflow']))
        self.assertEqual(result['input_sha256'], digest(document))
        translated = copy.deepcopy(document)
        translated['pilot'] = translated.pop('workflow')
        self.assertEqual(result['protocol_mapping']['calculation_input_sha256'], digest(translated))

    def test_brief_preserves_event_and_portfolio_results(self):
        document = self.example()
        legacy = copy.deepcopy(document)
        legacy['pilot'] = legacy.pop('workflow')
        current, prior = research.brief(document), research.brief(legacy)
        self.assertEqual(current['event'], prior['event'])
        self.assertEqual(current['portfolio_impact'], prior['portfolio_impact'])
        self.assertEqual(current['workflow_sha256'], digest(document['workflow']))
        self.assertFalse(current['execution_authorized'])

    def test_evaluation_current_identity_is_reconciled(self):
        document = self.example(evaluation=True)
        evaluation = document['evaluation']
        evaluation['workflow_id'] = document['workflow']['id']
        evaluation['workflow_sha256'] = digest(document['workflow'])
        result = research.evaluate(document)
        self.assertEqual(result['protocol_reconciliation']['status'], 'MATCHED_DECLARED_PROTOCOL')
        self.assertEqual(result['input_sha256'], digest(document))

    def test_evaluation_wrong_current_identity_stays_conflicting(self):
        document = self.example(evaluation=True)
        document['evaluation']['workflow_id'] = 'different-workflow'
        result = research.evaluate(document)
        self.assertEqual(result['protocol_reconciliation']['status'], 'PROTOCOL_CONFLICT')
        self.assertEqual(result['usefulness']['included_cases'], 0)

    def test_conflicting_protocol_aliases_are_rejected(self):
        document = self.example()
        document['pilot'] = dict(document['workflow'], id='conflicting')
        for operation in (research.plan, research.brief, research.evaluate):
            with self.subTest(operation=operation.__name__):
                with self.assertRaisesRegex(ValueError, 'CONFLICTING_PROTOCOL_DECLARATIONS'):
                    operation(document)

    def test_conflicting_evaluation_aliases_are_rejected(self):
        document = self.example(evaluation=True)
        document['evaluation'].update(workflow_id='current', pilot_id='different')
        with self.assertRaisesRegex(ValueError, 'CONFLICTING_EVALUATION_PROTOCOL_DECLARATIONS'):
            research.evaluate(document)

    def test_malformed_workflow_is_not_ignored(self):
        document = self.example()
        document['workflow'] = False
        with self.assertRaisesRegex(ValueError, 'WORKFLOW_OBJECT_REQUIRED'):
            research.plan(document)

    def test_equal_aliases_preserve_compatibility(self):
        document = self.example()
        document['pilot'] = copy.deepcopy(document['workflow'])
        self.assertEqual(research.plan(document)['workflow'], document['workflow'])

    def test_boolean_and_number_are_distinct_protocol_values(self):
        document = self.example()
        document['workflow']['declared_extra_flag'] = True
        document['pilot'] = dict(document['workflow'], declared_extra_flag=1)
        with self.assertRaisesRegex(ValueError, 'CONFLICTING_PROTOCOL_DECLARATIONS'):
            research.plan(document)

    def test_mixed_evaluation_aliases_reconcile_under_retained_protocol(self):
        document = self.example(evaluation=True)
        document['pilot'] = document.pop('workflow')
        document['evaluation'].update(pilot_id=document['pilot']['id'], workflow_id='conflicting-current-id')
        with self.assertRaisesRegex(ValueError, 'CONFLICTING_EVALUATION_PROTOCOL_DECLARATIONS'):
            research.evaluate(document)

    def test_current_evaluation_identity_is_checked_under_retained_protocol(self):
        document = self.example(evaluation=True)
        document['pilot'] = document.pop('workflow')
        document['evaluation']['workflow_id'] = 'conflicting-current-id'
        result = research.evaluate(document)
        self.assertEqual(result['protocol_reconciliation']['status'], 'PROTOCOL_CONFLICT')
        self.assertEqual(result['usefulness']['included_cases'], 0)
        self.assertEqual(result['input_sha256'], digest(document))

    def test_completed_operating_profile_matches_driver_configuration_schema(self):
        import research_operations
        profile = json.loads((ROOT / 'profiles/event-research-workflow.json').read_text(encoding='utf8'))
        choices = self.example()['workflow']
        for key in ('horizon', 'reviewer', 'study'):
            profile['workflow'][key] = choices[key]
        profile['freshness']['max_capture_age_seconds'] = 3600
        self.assertEqual(research_operations._config(profile), profile)


if __name__ == '__main__':
    unittest.main()
