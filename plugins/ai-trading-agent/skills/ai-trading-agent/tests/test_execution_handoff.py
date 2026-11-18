"""Research hands execution to native tools without local skill enforcement."""
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from execution_handoff import handoff, redact_private
import guarded_execution
import user_directed_execution
from execution_ledger import ExecutionLedger
from personal_runtime import dispatch, doctor, initialize


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.intent = {'tool_name':'place_equity_order','arguments':{'symbol':'DEMO','side':'buy',
            'type':'market','dollar_amount':'133.33','market_hours':'regular_hours','time_in_force':'gfd',
            'account_number':'FICTIONAL-PRIVATE','ref_id':'c733dfe3-03ee-4d08-90aa-149ef48c4edb'}}

    def assertHandoff(self,result):
        self.assertEqual(result['kind'],'NATIVE_HOST_BROKER_HANDOFF')
        self.assertEqual(result['skill_execution_gates'],[])
        self.assertFalse(result['local_runtime_required'])
        self.assertFalse(result['skill_submitted_order'])
        self.assertFalse(result['external_permissions_changed'])
        self.assertNotIn('allowed',result)
        self.assertNotIn('blocked',result)
        self.assertNotIn('permitted_once',result)

    def test_exact_native_dollar_payload_preserved_without_synthesized_limit(self):
        original = copy.deepcopy(self.intent)
        result = handoff(self.intent)
        self.assertHandoff(result)
        self.assertEqual(result['payload'],original)
        result['payload']['arguments']['dollar_amount']='1'
        self.assertEqual(self.intent,original)

    def test_fractional_quantity_preserved_without_repricing_or_rounding(self):
        del self.intent['arguments']['dollar_amount']
        self.intent['arguments']['quantity']='0.000123'
        self.assertEqual(handoff(self.intent)['payload'],self.intent)

    def test_research_status_funding_volatility_spread_and_expiry_never_gate_handoff(self):
        for status in ('Watch','Eligible','RESEARCH_QUEUE_ONLY','data_unavailable','excessive_volatility'):
            with self.subTest(status=status):
                payload={'order':self.intent,'research_status':status,'settled_cash':None,
                    'spread_bps':'9000','as_of':'1999-01-01','expires_at':'1999-01-02',
                    'price_deviation_percent':'500','risk_verdict':{'allowed':False},'authorization_id':None}
                result=handoff(payload)
                self.assertHandoff(result)
                self.assertEqual(result['payload'],payload)

    def test_missing_policy_approval_quote_and_runtime_do_not_block(self):
        self.assertHandoff(handoff())
        with tempfile.TemporaryDirectory() as temp:
            nonexistent=Path(temp)/'does-not-exist'
            self.assertHandoff(guarded_execution.submit(nonexistent,{'order':self.intent}))
            self.assertHandoff(user_directed_execution.submit(nonexistent,{'order':self.intent}))
            self.assertFalse(nonexistent.exists())

    def test_legacy_submit_does_not_invoke_supplied_broker_transport(self):
        transport=Mock(side_effect=AssertionError('No broker callback from research skill'))
        with patch('subprocess.run',side_effect=AssertionError('No subprocess dispatch')):
            for module in (guarded_execution,user_directed_execution):
                self.assertHandoff(module.submit('ignored',{'order':self.intent},transport))
            self.assertHandoff(guarded_execution.CommandTransport('ignored')(self.intent))
        transport.assert_not_called()

    def test_legacy_ticket_hook_has_no_authorization_or_refusal_function(self):
        result=guarded_execution.consume_host_ticket('missing','missing',self.intent['tool_name'],self.intent['arguments'])
        self.assertHandoff(result)
        self.assertEqual(result['payload'],self.intent)

    def test_legacy_gate_operations_ignore_bad_policy_and_preserve_historical_file(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            database=folder/'execution.db'
            database.write_bytes(b'old opaque runtime data must not change')
            (folder/'policy.json').write_text('invalid old policy')
            before=database.read_bytes()
            for operation in ('authorize','claim','session','claim-cancel','resolve-incident','quarantine','reconcile'):
                self.assertHandoff(dispatch(folder,operation,{'order':self.intent}))
            ledger=ExecutionLedger(database)
            for operation in ('authorize','claim','consume_dispatch','consume_transport','claim_cancel','reconcile','quarantine'):
                self.assertHandoff(getattr(ledger,operation)({'bad':'legacy input'}))
            self.assertEqual(database.read_bytes(),before)

    def test_runtime_init_creates_no_policy_or_execution_databases(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)/'research'
            initialize(folder)
            self.assertTrue((folder/'evidence').is_dir())
            self.assertTrue((folder/'reports').is_dir())
            self.assertFalse((folder/'policy.json').exists())
            self.assertFalse((folder/'execution.db').exists())
            self.assertFalse((folder/'supervised-session.db').exists())

    def test_doctor_is_research_diagnostic_without_policy_or_live_readiness(self):
        with tempfile.TemporaryDirectory() as temp:
            result=doctor(Path(temp)/'missing')
            self.assertEqual(result['skill_execution_gates'],[])
            self.assertEqual(result['failures'],[])
            self.assertNotIn('live_readiness',result)
            self.assertNotIn('policy_hash',result['checks'])

    def test_historical_unknown_records_remain_readable_without_becoming_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'execution.db'
            db=sqlite3.connect(path)
            db.execute('CREATE TABLE orders(id TEXT,state TEXT,filled TEXT)')
            db.execute("INSERT INTO orders VALUES ('old-local-intent','UNKNOWN','0')")
            db.commit(); db.close()
            before=hashlib.sha256(path.read_bytes()).hexdigest()
            ledger=ExecutionLedger(path)
            self.assertEqual(ledger.unresolved()[0]['state'],'UNKNOWN')
            self.assertHandoff(ledger.claim())
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),before)

    def test_cli_redacts_private_routing_but_api_preserves_exact_native_request(self):
        completed=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/execution_handoff.py')],
            input=json.dumps(self.intent),capture_output=True,text=True,check=True)
        output=json.loads(completed.stdout)
        self.assertHandoff(output)
        self.assertEqual(output['payload']['arguments']['account_number'],'<PRIVATE_HOST_VALUE>')
        self.assertNotIn('FICTIONAL-PRIVATE',completed.stdout)
        self.assertEqual(output['payload']['arguments']['dollar_amount'],'133.33')

    def test_private_key_variants_are_redacted_in_nested_display_copies_only(self):
        private_keys = ('account_id', 'accountAlias', 'ACCOUNT-NUMBER', 'account.identifier',
                        'Account UUID', 'brokerAccountId', 'privateRouting', 'authorizationHeader',
                        'accessToken', 'refresh-token', 'session_token', 'clientSecret',
                        'API KEY', 'X-API-Key', 'set-cookie', 'brokerOrderID')
        payload = {'orders': [{'details': {key: 'FICTIONAL-'+str(i)}} for i, key in enumerate(private_keys)],
                   'account_status': 'active', 'token_count': 0, 'quantity': '0.123456',
                   'notional': '25.00', 'limit_price': '100.02', 'order_type': 'limit'}
        before = copy.deepcopy(payload)
        result = handoff(payload)
        shown = redact_private(result)
        self.assertEqual(result['payload'], before)
        self.assertEqual(payload, before)
        for row in shown['payload']['orders']:
            self.assertEqual(row['details'], {key: '<PRIVATE_HOST_VALUE>' for key in row['details']})
        for key in ('account_status', 'token_count', 'quantity', 'notional', 'limit_price', 'order_type'):
            self.assertEqual(shown['payload'][key], payload[key])
        self.assertNotIn('FICTIONAL-', json.dumps(shown))
        shown['payload']['quantity'] = '999'
        self.assertEqual(result['payload'], before)

    def test_private_containers_and_tuple_members_do_not_leak_on_display(self):
        payload = {'account': {'id': 'FICTIONAL-ACCOUNT'},
                   'credentials': {'custom_name': 'FICTIONAL-CREDENTIAL'},
                   'rows': ({'nested': [{'accountAlias': 'FICTIONAL-ALIAS'}]},)}
        before = copy.deepcopy(payload)
        self.assertNotIn('FICTIONAL-', json.dumps(redact_private(payload)))
        self.assertEqual(handoff(payload)['payload'], before)
        self.assertEqual(payload, before)

    def test_every_handoff_display_entrypoint_uses_private_field_redaction(self):
        payload = {'orders': [{'symbol': 'DEMO', 'side': 'buy', 'notional': '25.00',
                    'order_type': 'market', 'accountId': 'FICTIONAL-ACCOUNT-ID',
                    'account_alias': 'FICTIONAL-ACCOUNT-ALIAS',
                    'routing': {'Authorization-Header': 'FICTIONAL-AUTH'}}]}
        commands = [('execution_handoff.py', []),
                    ('guarded_execution.py', ['submit', 'missing-runtime']),
                    ('user_directed_execution.py', ['submit', 'missing-runtime']),
                    ('personal_runtime.py', ['submit', 'missing-runtime'])]
        for filename, arguments in commands:
            with self.subTest(filename=filename):
                completed = subprocess.run([sys.executable, '-B', str(ROOT/'scripts'/filename), *arguments],
                    input=json.dumps(payload), capture_output=True, text=True, check=True)
                shown = json.loads(completed.stdout)
                self.assertHandoff(shown)
                self.assertNotIn('FICTIONAL-', completed.stdout + completed.stderr)
                order = shown['payload']['orders'][0]
                self.assertEqual(order['notional'], '25.00')
                self.assertEqual(order['order_type'], 'market')
                self.assertEqual(order['accountId'], '<PRIVATE_HOST_VALUE>')
                self.assertEqual(order['account_alias'], '<PRIVATE_HOST_VALUE>')
        self.assertEqual(handoff(payload)['payload'], payload)

    def test_legacy_cli_operations_return_handoff_with_no_runtime_lookup(self):
        for filename in ('guarded_execution.py','user_directed_execution.py'):
            with self.subTest(filename=filename):
                completed=subprocess.run([sys.executable,'-B',str(ROOT/'scripts'/filename),'submit','missing-runtime'],
                    input=json.dumps(self.intent),capture_output=True,text=True,check=True)
                self.assertHandoff(json.loads(completed.stdout))

    def test_adverse_risk_cli_is_successful_advisory_not_shell_veto(self):
        completed=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/risk_engine.py'),
            str(ROOT/'templates/policy.example.json'),str(ROOT/'examples/snapshot.json'),
            str(ROOT/'examples/order.json'),'--as-of','2026-10-13T15:00:00Z'],capture_output=True,text=True,check=True)
        result=json.loads(completed.stdout)
        self.assertFalse(result['within_research_limits'])
        self.assertFalse(result['enforces_execution'])
        self.assertNotIn('allowed',result)
        self.assertNotIn('entry_disposition',result)

    def test_missing_volatility_cli_returns_advisory_not_execution_pause(self):
        completed=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/execution_volatility.py')],
            input='{}',capture_output=True,text=True,check=True)
        result=json.loads(completed.stdout)
        self.assertEqual(result['status'],'data_unavailable')
        self.assertIsNone(result['within_historical_range'])
        self.assertFalse(result['enforces_execution'])
        self.assertNotIn('allowed',result)
        self.assertNotIn('deadline',result)

    def test_optional_risk_diagnostic_does_not_require_personal_policy(self):
        with tempfile.TemporaryDirectory() as temp:
            result=dispatch(temp,'risk',{})
            self.assertEqual(result['diagnostic_status'],'DATA_UNAVAILABLE')
            self.assertFalse(result['enforces_execution'])

    def test_optional_mapper_preserves_native_market_without_old_profile_gates(self):
        from broker_bridge import build_request
        schema={'type':'object','properties':{'symbol':{'type':'string'},'type':{'type':'string'},'dollar_amount':{'type':'string'}},
                'required':['symbol','type','dollar_amount'],'additionalProperties':False}
        caps={'operations':{'submit':{'tool_name':'place_equity_order','input_schema':schema,
                'bindings':{'symbol':{'pointer':'/symbol','type':'string'},
                            'type':{'pointer':'/type','type':'string'},
                            'dollar_amount':{'pointer':'/dollar_amount','type':'string'}}}}}
        payload={'symbol':'DEMO','type':'market','dollar_amount':'400.00'}
        result=build_request(caps,'submit',payload,None,None)
        self.assertEqual(result['request']['arguments'],payload)
        self.assertFalse(result['enforces_execution'])


class RecurringDollarIntentTests(unittest.TestCase):
    def request(self):
        return {'plan_id': 'periodic-savings', 'occurrence_id': 'cycle-4',
                'account_alias': 'FICTIONAL-ROUTING', 'amounts': {'NORTH': '12.3400', 'SOUTH': '7.6600'},
                'prices': {'NORTH': '81', 'SOUTH': '63'}, 'available_cash': '80'}

    def test_unmapped_record_preserves_source_lexemes_and_context(self):
        from execution_handoff import recurring_dollar_intent
        request = self.request()
        context = {'order_type': 'limit', 'limit_prices': {'NORTH': '80.1200'},
                   'purpose': 'reserve-building', 'cadence': 'quarterly', 'permissions': None}
        original = copy.deepcopy((request, context))
        result = recurring_dollar_intent(request, currency='CAD', companion_context=context)
        self.assertEqual(result['original_recurring_request'], request)
        self.assertEqual(result['companion_context'], context)
        self.assertEqual([row['requested_dollar_amount'] for row in result['economic_intents']], ['12.3400', '7.6600'])
        self.assertTrue(all(row['currency'] == 'CAD' for row in result['economic_intents']))
        self.assertEqual(result['schema_basis']['status'], 'UNMAPPED')
        self.assertFalse(result['schema_basis']['broker_contract_bound'])
        self.assertFalse(result['schema_basis']['host_capability_verified'])
        self.assertNotIn('tool_name', json.dumps(result))
        self.assertEqual(result['skill_execution_gates'], [])
        self.assertFalse(result['skill_submitted_order'])
        self.assertFalse(result['schedule_created'])
        result['original_recurring_request']['amounts']['NORTH'] = '999'
        result['companion_context']['order_type'] = 'market'
        self.assertEqual((request, context), original)

    def test_unknown_currency_is_not_inferred_from_dollar_name(self):
        from execution_handoff import recurring_dollar_intent
        result = recurring_dollar_intent(self.request())
        self.assertEqual(result['currency_status'], 'NOT_SUPPLIED_TO_CONSTRUCTOR')
        self.assertTrue(all(row['currency'] is None for row in result['economic_intents']))
        self.assertIn('currency not supplied to this constructor; original request context not verified', result['summary'])
        self.assertNotIn('USD', json.dumps(result))
        self.assertIsNone(result['companion_context'])

    def test_summary_is_generated_from_the_same_economic_record(self):
        from execution_handoff import recurring_dollar_intent, recurring_dollar_summary
        result = recurring_dollar_intent(self.request(), currency='AUD')
        self.assertEqual(result['summary'], recurring_dollar_summary(result))
        for row in result['economic_intents']:
            self.assertIn(f"{row['requested_dollar_amount']} ({row['currency']}) for {row['symbol']}", result['summary'])
        self.assertIn('no broker tool or argument schema is bound', result['summary'])

    def test_waiting_cash_is_a_separate_observation_not_a_handoff_refusal(self):
        from portfolio_manager import recurring_handoff, recurring_buys
        request = self.request()
        request['available_cash'] = '1'
        result = recurring_handoff(request)
        self.assertEqual(result['sizing_observation'], recurring_buys(**request))
        self.assertEqual(result['sizing_observation']['status'], 'WAIT_FOR_SETTLED_CASH')
        self.assertEqual(len(result['economic_intents']), 2)
        self.assertEqual(result['skill_execution_gates'], [])
        self.assertNotIn('allowed', result)
        self.assertNotIn('blocked', result)
        self.assertEqual(result['original_recurring_request']['amounts'], request['amounts'])

    def test_whole_share_sizing_does_not_replace_dollar_intent(self):
        from portfolio_manager import recurring_handoff, recurring_buys
        request = self.request()
        request['allow_fractional'] = False
        result = recurring_handoff(request)
        self.assertEqual(result['sizing_observation'], recurring_buys(**request))
        self.assertEqual(result['original_recurring_request'], request)
        self.assertEqual([row['requested_dollar_amount'] for row in result['economic_intents']], list(request['amounts'].values()))
        self.assertTrue(all('quantity' not in row for row in result['economic_intents']))

    def test_constructor_does_not_require_prices_cash_or_call_broker_tools(self):
        from execution_handoff import recurring_dollar_intent
        with patch('subprocess.run', side_effect=AssertionError('No tool dispatch')):
            result = recurring_dollar_intent({'amounts': {'EAST': '0.00', 'WEST': 3}})
        self.assertEqual([row['requested_dollar_amount'] for row in result['economic_intents']], ['0.00', 3])
        self.assertNotIn('sizing_observation', result)

    def test_ambiguous_numeric_input_rejected_without_changing_generic_formatter(self):
        from execution_handoff import recurring_dollar_intent
        for amount in (0.1, True, 'NaN', 'Infinity', '-1', {}, 'not-a-number'):
            with self.subTest(amount=amount):
                request = {'amounts': {'EAST': amount}}
                with self.assertRaises(ValueError):
                    recurring_dollar_intent(request)
                self.assertEqual(handoff(request)['payload'], request)

    def test_redacted_display_retains_unredacted_private_api_record(self):
        from execution_handoff import recurring_dollar_intent
        result = recurring_dollar_intent(self.request(), companion_context={'accountId': 'FICTIONAL-PRIVATE'})
        shown = redact_private(result)
        self.assertNotIn('FICTIONAL-', json.dumps(shown))
        self.assertEqual(result['original_recurring_request']['account_alias'], 'FICTIONAL-ROUTING')
        self.assertEqual(result['companion_context']['accountId'], 'FICTIONAL-PRIVATE')
        self.assertEqual(shown['summary'], result['summary'])

    def test_cli_new_route_preserves_json_decimal_lexemes_and_old_route(self):
        from portfolio_manager import recurring_buys
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            path = root/'input.json'
            request = self.request()
            path.write_text(json.dumps({'recurring_request': request, 'currency': None,
                                       'companion_context': {'order_type': 'limit'}}).replace('"12.3400"', '12.3400'), encoding='utf-8')
            command = [sys.executable, '-B', str(ROOT/'scripts/portfolio_manager.py'), str(path)]
            result = subprocess.run(command+['--recurring-handoff'], capture_output=True, text=True, check=True)
            shown = json.loads(result.stdout)
            self.assertEqual(shown['economic_intents'][0]['requested_dollar_amount'], '12.3400')
            self.assertEqual(shown['companion_context']['order_type'], 'limit')
            self.assertNotIn('FICTIONAL-', result.stdout)
            self.assertEqual(shown['schema_basis']['status'], 'UNMAPPED')
            path.write_text(json.dumps(request), encoding='utf-8')
            legacy = subprocess.run(command+['--recurring'], capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(legacy.stdout), recurring_buys(**request))

    def test_cli_rejects_duplicate_amounts_or_context_only_on_new_route(self):
        from portfolio_manager import recurring_buys
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            path = root/'duplicate-input.json'
            request = self.request()
            request_json = json.dumps(request)
            duplicate_request = request_json.replace('"NORTH": "12.3400"', '"NORTH": "2.01", "NORTH": "12.3400"')
            command = [sys.executable, '-B', str(ROOT/'scripts/portfolio_manager.py'), str(path)]
            cases = ['{"recurring_request": '+duplicate_request+'}',
                     '{"recurring_request": '+request_json+', "currency":"CAD", "currency":"USD"}',
                     '{"recurring_request": '+request_json+', "companion_context":{"order_type":"limit","order_type":"market"}}']
            for payload in cases:
                with self.subTest(payload=payload):
                    path.write_text(payload, encoding='utf-8')
                    result = subprocess.run(command+['--recurring-handoff'], capture_output=True, text=True)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(result.stdout, '')
                    self.assertIn('Duplicate JSON key in recurring handoff input', result.stderr)
            path.write_text(duplicate_request, encoding='utf-8')
            legacy = subprocess.run(command+['--recurring'], capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(legacy.stdout), recurring_buys(**request))


if __name__ == '__main__':
    unittest.main()
