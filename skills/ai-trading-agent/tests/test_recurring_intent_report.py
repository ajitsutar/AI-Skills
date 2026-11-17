import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from recurring_intent_report import build, summary
from handoff_report import sha


def source(text, *roles):
    return {'text': text, 'sha256': sha(text.encode('utf-8')), 'roles': list(roles)}


class RecurringSourceTests(unittest.TestCase):
    def spec(self):
        instruction = 'For this occurrence, request CAD amounts for both assets; keep the limit preference.'
        return {'sources': {
            'instruction': source(instruction, 'instruction'),
            'fixture': source('{"plan_id":"rainy-day","occurrence_id":"cycle-7","account_alias":"FICTIONAL","amounts":{"PINE":12.3400,"ELM":7.6600}}', 'recurring_request'),
            'context': source('{"order_type":"limit","limit":"42.1000","currency":null}', 'companion_context')},
            'recurring_request': {'source_id':'fixture', 'json_pointer':''},
            'companion_context': {'source_id':'context', 'json_pointer':''},
            'currency_selections': [{'source_id':'instruction','utf8_span':[29,32], 'intent_symbols':['PINE','ELM']}]}

    def test_instruction_only_currency_and_complete_context_retained(self):
        spec = self.spec()
        original = copy.deepcopy(spec)
        result = build(spec)
        self.assertEqual(result['original_sources'], spec['sources'])
        self.assertEqual([i['currency'] for i in result['economic_intents']], ['CAD','CAD'])
        self.assertEqual([i['requested_dollar_amount'] for i in result['economic_intents']], ['12.3400','7.6600'])
        self.assertEqual(result['original_recurring_request']['account_alias'], 'FICTIONAL')
        self.assertEqual(result['companion_context']['limit'], '42.1000')
        self.assertEqual(result['schema_basis']['status'], 'UNMAPPED')
        self.assertEqual(result['summary'], summary(result))
        self.assertIn('12.3400 (CAD)', result['summary'])
        self.assertEqual(result['skill_execution_gates'], [])
        self.assertFalse(result['skill_submitted_order'])
        self.assertEqual(spec, original)
        result['original_sources']['instruction']['text'] = 'changed'
        self.assertEqual(spec, original)

    def test_hash_edit_is_rejected_not_misreported_as_bound(self):
        spec = self.spec()
        spec['sources']['instruction']['text'] += ' amended'
        with self.assertRaisesRegex(ValueError, 'HASH_MISMATCH'): build(spec)

    def test_missing_selection_is_unresolved_even_with_explicit_code_in_instruction(self):
        spec = self.spec(); spec.pop('currency_selections')
        result = build(spec)
        self.assertEqual(result['currency_status'], 'CURRENCY_MAPPING_UNRESOLVED')
        self.assertTrue(all(i['currency'] is None for i in result['economic_intents']))
        self.assertNotIn('unspecified', result['summary'].lower())

    def test_bare_dollar_is_not_inferred(self):
        spec = self.spec(); spec['sources']['instruction'] = source('Contribute the stated dollar amounts.', 'instruction')
        spec['currency_selections'] = []
        result = build(spec)
        self.assertEqual(result['currency_status'], 'CURRENCY_MAPPING_UNRESOLVED')
        self.assertNotIn('USD', result['summary'])

    def test_unbound_instruction_is_separate_from_currency_selection(self):
        spec = self.spec(); spec['sources']['instruction']['roles'] = ['currency_evidence']
        selected = build(spec)
        self.assertEqual(selected['request_context_status'], 'REQUEST_CONTEXT_UNBOUND')
        self.assertEqual(selected['currency_status'], 'SOURCE_SELECTED')
        spec['currency_selections'] = []
        self.assertEqual(build(spec)['currency_status'], 'REQUEST_CONTEXT_UNBOUND')

    def test_json_currency_pointer_and_scoped_mixed_codes(self):
        spec = self.spec()
        spec['sources']['units'] = source('{"a":"EUR","b":"JPY"}', 'currency_evidence')
        spec['currency_selections'] = [{'source_id':'units','json_pointer':'/a','intent_symbols':['PINE']},
                                       {'source_id':'units','json_pointer':'/b','intent_symbols':['ELM']}]
        result = build(spec)
        self.assertEqual([i['currency'] for i in result['economic_intents']], ['EUR','JPY'])
        self.assertIn('7.6600 (JPY)', result['summary'])

    def test_conflicting_sources_preserved_without_last_value_wins(self):
        spec = self.spec()
        spec['sources']['units'] = source('{"currency":"EUR"}', 'currency_evidence')
        spec['currency_selections'].append({'source_id':'units','json_pointer':'/currency','intent_symbols':['PINE']})
        result = build(spec)
        self.assertEqual(result['economic_intents'][0]['currency_status'], 'CONFLICTING_SOURCE_SELECTIONS')
        self.assertIsNone(result['economic_intents'][0]['currency'])
        self.assertEqual(len(result['economic_intents'][0]['currency_observations']), 2)
        self.assertEqual(result['economic_intents'][1]['currency'], 'CAD')

    def test_null_missing_and_absent_selection_are_distinct(self):
        spec = self.spec()
        spec['currency_selections'] = [{'source_id':'context','json_pointer':'/currency','intent_symbols':['PINE']}]
        result = build(spec)
        self.assertEqual([i['currency_status'] for i in result['economic_intents']], ['SOURCE_FIELD_NULL','CURRENCY_MAPPING_UNRESOLVED'])
        spec['currency_selections'][0]['json_pointer'] = '/absent'
        with self.assertRaisesRegex(ValueError, 'POINTER_NOT_FOUND'): build(spec)

    def test_null_and_positive_selection_conflict(self):
        spec = self.spec()
        spec['currency_selections'].append({'source_id':'context','json_pointer':'/currency','intent_symbols':['PINE']})
        self.assertEqual(build(spec)['economic_intents'][0]['currency_status'], 'CONFLICTING_SOURCE_SELECTIONS')

    def test_invalid_or_ambiguous_scope_is_not_silently_expanded(self):
        for scope in ([], ['UNKNOWN'], ['PINE','PINE'], None):
            spec = self.spec(); spec['currency_selections'][0]['intent_symbols'] = scope
            with self.subTest(scope=scope), self.assertRaises(ValueError): build(spec)

    def test_utf8_span_boundaries_and_selected_syntax(self):
        spec = self.spec()
        text = 'é CAD for these assets.'
        spec['sources']['instruction'] = source(text, 'instruction')
        spec['currency_selections'][0]['utf8_span'] = [3,6]
        self.assertEqual(build(spec)['economic_intents'][0]['currency'], 'CAD')
        for span in ([1,4],[3,5],[3,99],[True,6]):
            spec['currency_selections'][0]['utf8_span'] = span
            with self.subTest(span=span), self.assertRaises((ValueError, UnicodeError)): build(spec)

    def test_negated_currency_is_not_claimed_semantically_verified(self):
        spec = self.spec()
        spec['sources']['instruction'] = source('Do not use CAD; clarify the unit.', 'instruction')
        spec['currency_selections'][0]['utf8_span'] = [11,14]
        result = build(spec)
        self.assertEqual(result['currency_status'], 'SOURCE_SELECTED')
        self.assertIn('negation', ' '.join(result['limitations']))
        self.assertIn('does not prove semantic applicability', result['summary'])

    def test_duplicate_keys_and_contradictory_override_rejected(self):
        spec = self.spec()
        spec['sources']['fixture'] = source('{"amounts":{"PINE":2,"PINE":3}}','recurring_request')
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_JSON_KEY'): build(spec)
        spec = self.spec(); spec['currency'] = 'EUR'
        with self.assertRaisesRegex(ValueError, 'INVALID_FIELDS'): build(spec)

    def test_decimal_exponent_spelling_retained(self):
        spec = self.spec()
        raw = spec['sources']['fixture']['text'].replace('12.3400','1.23400e1')
        spec['sources']['fixture'] = source(raw,'recurring_request')
        self.assertEqual(build(spec)['economic_intents'][0]['requested_dollar_amount'], '1.23400e1')

    def test_cli_uses_canonical_fixture_root_and_preserves_full_private_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            path = root/'request.json'; path.write_text(json.dumps(self.spec()), encoding='utf-8')
            command = [sys.executable,'-B',str(ROOT/'scripts/recurring_intent_report.py'),str(path)]
            result = subprocess.run(command,capture_output=True,text=True,check=True)
            actual = json.loads(result.stdout)
            self.assertEqual(actual['summary'], build(self.spec())['summary'])
            self.assertEqual(actual['original_sources'], self.spec()['sources'])
            path.write_text('{"sources":{},"sources":{}}',encoding='utf-8')
            bad = subprocess.run(command,capture_output=True,text=True)
            self.assertNotEqual(bad.returncode,0)
            self.assertEqual(bad.stdout,'')
            self.assertIn('DUPLICATE_JSON_KEY',bad.stderr)


if __name__ == '__main__':
    unittest.main()
