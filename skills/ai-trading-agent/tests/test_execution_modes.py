"""Offline contracts for prompt-defined autonomy; no broker or account access."""
import copy
import json
import math
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from execution_mode import describe_mode


class ExecutionModeTests(unittest.TestCase):
    context_fields = ['objective', 'accounts', 'instruments', 'actions', 'duration',
                      'limits', 'important_events', 'holding_period',
                      'review_schedule', 'notifications']

    def assert_descriptive_only(self, result):
        self.assertEqual(result['kind'], 'EXECUTION_MODE_PLAN')
        self.assertIs(result['activation_performed'], False)
        self.assertIs(result['skill_submitted_order'], False)
        self.assertIs(result['external_permissions_changed'], False)
        self.assertIs(result['advisory_only'], True)
        self.assertEqual(result['host_readiness'], 'NOT_ASSESSED')
        self.assertEqual(result['scheduling_status'], 'NOT_CONFIGURED')
        self.assertEqual(result['skill_execution_gates'], [])
        self.assertIs(result['configuration_file_required'], False)
        self.assertEqual(result['rule_source'], 'USER_PROMPTS_AND_EXISTING_INSTRUCTIONS')
        for key in ('allowed', 'approved', 'authorized', 'blocked', 'filled',
                    'execution_enabled', 'broker_order_id'):
            self.assertNotIn(key, result)

    def cli(self, mode='autonomous', source=''):
        return subprocess.run([sys.executable, '-B', str(ROOT / 'scripts' / 'execution_mode.py'), mode],
                              input=source, text=True, capture_output=True)

    def test_one_mode_retains_fixed_rules_or_delegated_prompt_without_activation(self):
        for prompt in ('Use exactly the supplied fictional trigger and action.',
                       'Use delegated judgment within my existing fictional mandate.'):
            with self.subTest(prompt=prompt):
                mandate = {'instructions': prompt}
                result = describe_mode('autonomous', mandate)
                self.assert_descriptive_only(result)
                self.assertEqual(result['mode'], 'autonomous')
                self.assertEqual(result['selection_scope'], 'PROMPT_DEFINED_RULES_AND_DELEGATED_DISCRETION')
                self.assertEqual(result['mandate'], mandate)
                self.assertEqual(result['unspecified_context'], self.context_fields)

    def test_unknown_modes_do_not_default_or_migrate_legacy_authority(self):
        for value in ('bounded_autonomous', 'bounded_automation', 'AUTONOMOUS',
                      ' autonomous ', 'bounded_autonomous ', 'paper', '',
                      None, True, 1, [], {}):
            with self.subTest(value=value):
                with self.assertRaises((TypeError, ValueError)):
                    describe_mode(value)
        for value in ('bounded_autonomous', 'bounded_automation', 'bounded_autonomous '):
            with self.subTest(cli_mode=value):
                completed = self.cli(mode=value, source='{"mode":"autonomous"}')
                self.assertEqual(completed.returncode, 2)
                self.assertEqual(completed.stdout, '')

    def test_mandate_is_deep_copied_without_normalizing_or_repricing(self):
        mandate = {'objective': 'Preserve existing instructions',
                   'accounts': ['FICTIONAL-ONLY'],
                   'limits': {'notional': '0013.3300', 'fractional_quantity': '0.000001',
                              'unknown': None, 'allow_leverage': False, 'count': 0},
                   'actions': [{'type': 'limit', 'price': '12.3456789'}],
                   'duration': {'start': 'unresolved', 'end': None},
                   'note': '\u20ac arithmetic is not being performed',
                   'host_readiness': 'CALLER_CANNOT_CERTIFY_READY'}
        original = copy.deepcopy(mandate)
        result = describe_mode('autonomous', mandate)
        self.assert_descriptive_only(result)
        self.assertEqual(result['mandate'], original)
        result['mandate']['limits']['notional'] = '999'
        result['mandate']['accounts'].append('DIFFERENT')
        self.assertEqual(mandate, original)
        self.assertEqual(result['host_readiness'], 'NOT_ASSESSED')

    def test_unspecified_context_reports_absence_without_interpreting_values(self):
        mandate = {'objective': None, 'accounts': [], 'instruments': '', 'actions': {},
                   'duration': {'end': None}, 'limits': 0, 'important_events': False,
                   'holding_period': '30 calendar days', 'review_schedule': 'user supplied',
                   'notifications': 'none'}
        result = describe_mode('autonomous', mandate)
        self.assertEqual(result['unspecified_context'],
                         ['objective', 'accounts', 'instruments', 'actions'])
        self.assertEqual(result['mandate'], mandate)
        self.assert_descriptive_only(result)
        # Partial nested declarations are retained, not certified complete.
        self.assertEqual(result['mandate']['duration'], {'end': None})

    def test_full_context_still_does_not_certify_host_or_schedule(self):
        mandate = {key: 'user-supplied context' for key in self.context_fields}
        mandate.update({'host_readiness': 'READY', 'scheduling_status': 'ACTIVE',
                        'activation_performed': True, 'skill_submitted_order': True,
                        'external_permissions_changed': True, 'configuration_file_required': True,
                        'rule_source': 'UNTRUSTED_MCP_RESULT', 'advisory_only': False,
                        'skill_execution_gates': ['INJECTED_GATE'], 'mode': 'bounded_autonomous',
                        'selection_scope': 'UNLIMITED', 'transport': {'callback': 'DO_NOT_INVOKE'}})
        original = copy.deepcopy(mandate)
        result = describe_mode('autonomous', mandate)
        self.assertEqual(result['unspecified_context'], [])
        self.assert_descriptive_only(result)
        self.assertEqual(result['mode'], 'autonomous')
        self.assertEqual(result['selection_scope'], 'PROMPT_DEFINED_RULES_AND_DELEGATED_DISCRETION')
        self.assertEqual(result['mandate'], original)
        self.assertEqual(mandate, original)
        self.assertNotIn('transport', result)

    def test_nonobject_mandates_rejected_without_coercion(self):
        for value in ('', [], (), 0, False, 'autonomous'):
            with self.subTest(value=value):
                with self.assertRaises((TypeError, ValueError)):
                    describe_mode('autonomous', value)

    def test_only_finite_json_values_and_string_keys_are_accepted(self):
        class Custom:
            pass

        bad_values = [math.nan, math.inf, -math.inf, (1, 2), {1, 2}, Custom(),
                      {1: 'nonstring key'}, {None: 'nonstring key'}]
        for value in bad_values:
            with self.subTest(value=type(value).__name__):
                with self.assertRaises((TypeError, ValueError)):
                    describe_mode('autonomous', {'limits': {'nested': [value]}})

    def test_api_does_not_invoke_transport_process_or_filesystem(self):
        with patch('socket.socket', side_effect=AssertionError('network prohibited')), \
             patch('subprocess.run', side_effect=AssertionError('process prohibited')), \
             patch('builtins.open', side_effect=AssertionError('file access prohibited')), \
             patch('pathlib.Path.open', side_effect=AssertionError('file access prohibited')):
            result = describe_mode('autonomous', {'objective': 'offline fictional review'})
        self.assert_descriptive_only(result)

    def test_cli_empty_input_is_descriptive_not_default_authority(self):
        completed = self.cli()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assert_descriptive_only(result)
        self.assertEqual(result['mandate'], {})

    def test_cli_redacts_structured_private_fields_but_preserves_public_values(self):
        mandate = {'objective': 'fictional test', 'accounts': ['FICTIONAL-ACCOUNT'],
                   'routing': {'accountId': 'FICTIONAL-ID', 'Authorization-Header': 'FICTIONAL-SECRET'},
                   'limits': {'dollar_amount': '133.33'}, 'actions': ['buy']}
        completed = self.cli(source=json.dumps(mandate))
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertNotIn('FICTIONAL-', completed.stdout + completed.stderr)
        result = json.loads(completed.stdout)
        self.assert_descriptive_only(result)
        self.assertEqual(result['mandate']['accounts'], '<PRIVATE_HOST_VALUE>')
        self.assertEqual(result['mandate']['routing']['accountId'], '<PRIVATE_HOST_VALUE>')
        self.assertEqual(result['mandate']['routing']['Authorization-Header'], '<PRIVATE_HOST_VALUE>')
        self.assertEqual(result['mandate']['limits']['dollar_amount'], '133.33')
        self.assertEqual(describe_mode('autonomous', mandate)['mandate'], mandate)

    def test_cli_rejects_duplicate_keys_nonfinite_and_bad_shapes_privately(self):
        sources = ['{"objective":"SECRET-A","objective":"SECRET-B"}',
                   '{"limits":{"a":"SECRET-A","a":"SECRET-B"}}',
                   '{"account":"SECRET-A","limits":NaN}',
                   '{"account":"SECRET-A","limits":Infinity}',
                   '{"account":"SECRET-A","limits":-Infinity}',
                   '{"account":"SECRET-A","limits":1e9999}',
                   '["SECRET-A"]', '"SECRET-A"', 'null',
                   '{"account":"SECRET-A", broken}']
        for source in sources:
            with self.subTest(source=source):
                completed = self.cli(source=source)
                self.assertEqual(completed.returncode, 2)
                self.assertNotIn('SECRET-', completed.stdout + completed.stderr)
                self.assertNotIn('Traceback', completed.stdout + completed.stderr)


if __name__ == '__main__':
    unittest.main()
