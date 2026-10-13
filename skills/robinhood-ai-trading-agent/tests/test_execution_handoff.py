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


if __name__ == '__main__':
    unittest.main()
