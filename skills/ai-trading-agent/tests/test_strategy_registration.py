import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

import test_strategy_answer as fixtures
from strategy_registration import LEGACY, STRICT

ROOT = Path(__file__).resolve().parents[1]


class StrategyRegistrationTests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.StrategyAnswerTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.directory = fixture.directory
        self.source = fixture.source
        self.legacy = copy.deepcopy(fixture.request)
        study = json.loads(self.source.read_bytes())
        study['strategies'][0].update(cash_yield=0.0125, first='2029-02-01', last='2029-04-30')
        study['other']['cash_yield'] = 0.08
        self.source.write_text(json.dumps(study), encoding='utf8')
        self.legacy['sources'][0]['sha256'] = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.request = copy.deepcopy(self.legacy)
        terms = self.request['design_terms']
        for k in ('benchmark','development_validation_split','evaluation_window'):
            del terms[k]
        del self.request['answer_controls']['uncertainty']
        self.request['proposed_decision_rules'][0].update(measure='mean_paired_net_active_return', units='return_fraction',
                                                         measurement_window='registered_evaluation')
        self.request['strategy_registration'] = {
            'benchmark': {'kind':'cash','currency':{'proposal':'EUR'}, 'cash_return':{'convention':'simple_annual',
                          'annual_fraction':{'record_pointer':'/cash_yield'},'day_count':'actual_360'}},
            'evaluation': {'start':{'record_pointer':'/first'},'end':{'record_pointer':'/last'}}, 'development_fraction':0.6,
            'uncertainty': {'performance_rule':0,'confidence':0.9,'estimator':{'name':'newey_west_normal','lag_observations':4}}}

    def report(self, request):
        return fixtures.contracts.strategy_answer(request, self.directory)['result']

    def entry(self, options, flag, destination):
        prompt = self.directory/'question.txt'
        prompt.write_text('Study studies.json#/strategies/0 before proposing a decision.',encoding='utf8')
        choices = self.directory/'options.json'
        choices.write_text(json.dumps({k:v for k,v in options.items() if k not in ('allowlist','sources','strategy_source')}),encoding='utf8')
        return subprocess.run([sys.executable,'-X','utf8','-B',str(ROOT/'scripts/research_preflight.py'),
                               '--request',str(prompt),'--source-root',str(self.directory),'--source',self.source.name,
                               flag,str(choices),'--private-output',str(destination)],capture_output=True,text=True,encoding='utf8')

    def test_preflight_source_and_proposal_origin_generated_readback(self):
        out = self.directory/'registered'
        answer = self.entry(self.request,'--registered-design',out)
        self.assertEqual(answer.returncode,0,answer.stderr)
        self.assertEqual(json.loads(answer.stdout)['registration_scope'],STRICT)
        checks = fixtures.contracts.verify(out,out/'answer.md',out/'answer-rows.json')
        self.assertEqual(checks['registration_scope'],STRICT)
        row = json.loads((out/'answer-rows.json').read_bytes())[0]
        self.assertEqual(row['strategy_registration']['benchmark']['cash_return']['annual_fraction'],
                         {'basis':'supplied','record_pointer':'/cash_yield','value':0.0125})
        receipt_path = out/'receipt.json'
        receipt = json.loads(receipt_path.read_bytes())
        del receipt['registration_scope']
        receipt_path.write_text(json.dumps(receipt), encoding='utf8')
        with self.assertRaisesRegex(ValueError,'REGISTRATION_SCOPE_MISMATCH'):
            fixtures.contracts.verify(out)
        words = (out/'answer.md').read_text(encoding='utf8')
        for fragment in ('0.0125','supplied from selected record','(proposed)','strictly before evaluation','4 observation lags'):
            self.assertIn(fragment,words)
        self.assertNotIn('0.08',words)
        second = copy.deepcopy(self.request)
        second['strategy_registration']['benchmark']['cash_return']['annual_fraction']={'proposal':0.019}
        rate = self.report(second)['strategy_registration']['benchmark']['cash_return']['annual_fraction']
        self.assertEqual(rate,{'basis':'proposed','value':0.019})

    def test_invalid_or_competing_registration_cannot_choose_after_observation(self):
        changes = [
            (('strategy_registration','benchmark','cash_return','annual_fraction'),{'record_pointer':'/other/cash_yield'}),
            (('strategy_registration','benchmark','cash_return','annual_fraction'),{'proposal':'supplied annual rate'}),
            (('strategy_registration','benchmark','cash_return','annual_fraction'),{'record_pointer':'/cash_yield','proposal':0.4}),
            (('strategy_registration','benchmark','cash_return','annual_fraction'),{'record_pointer':'/first'}),
            (('strategy_registration','uncertainty','estimator'),{'name':'newey_west_normal','lag_observations':True}),
            (('strategy_registration','uncertainty','estimator'),{'name':'newey_west_normal','lag_observations':40}),
            (('strategy_registration','uncertainty','estimator'),{'name':'newey_west_normal','lag_observations':3,'also':'bootstrap'}),
            (('strategy_registration','uncertainty','estimator'),{'name':'bootstrap or HAC'}),
            (('strategy_registration','uncertainty','estimator'),{'name':'circular_moving_block_percentile','block_observations':2,'replicates':10}),
            (('strategy_registration','uncertainty','performance_rule'),1),
            (('strategy_registration','evaluation','start'),{'proposal':'2029-08-01'}),
            (('strategy_registration','development_fraction'),1),
            (('design_terms','development_validation_split'),{'proposal':'retrain on evaluation observations'}),
            (('answer_controls','uncertainty'),self.legacy['answer_controls']['uncertainty']),
            (('proposed_decision_rules',0,'measure'),'unpaired terminal wealth')]
        for path, value in changes:
            with self.subTest(path=path,value=value):
                request = copy.deepcopy(self.request)
                obj=request
                for part in path[:-1]:
                    obj=obj[part]
                obj[path[-1]]=value
                with self.assertRaises((KeyError, ValueError)):
                    self.report(request)

    def test_second_estimator_and_missing_cash_are_explicit(self):
        controls=self.request['strategy_registration']
        controls['benchmark']={'kind':'buy_and_hold','identifier':{'record_pointer':'/family'},'currency':{'proposal':'EUR'},
                               'cash_return':{'convention':'unavailable'}}
        controls['uncertainty']['estimator']={'name':'circular_moving_block_percentile','block_observations':4,
                                              'replicates':5000,'seed':67}
        row=self.report(self.request)
        self.assertIn('5000 replicates',row['answer_controls']['uncertainty']['dependence_treatment'])
        self.assertEqual(row['strategy_registration']['benchmark']['cash_return']['on_required_missing_input'],'inconclusive')
        self.assertEqual(row['strategy_registration']['benchmark']['identifier']['value'],'weekly volume')
        controls['uncertainty']['estimator']['replicates']=3
        with self.assertRaisesRegex(ValueError,'BOOTSTRAP_TAIL'):
            self.report(self.request)

    def test_open_prose_is_identified_and_cannot_satisfy_the_registered_entry(self):
        reject=self.entry(self.legacy,'--registered-design',self.directory/'invalid')
        self.assertNotEqual(reject.returncode,0)
        self.assertIn('TYPED_STRATEGY_REGISTRATION_REQUIRED',reject.stderr)
        out=self.directory/'old'
        run=self.entry(self.legacy,'--design',out)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(json.loads(run.stdout)['registration_scope'],LEGACY)
        self.assertEqual(fixtures.contracts.verify(out)['registration_scope'],LEGACY)
        receipt=out/'receipt.json'
        native=json.loads(receipt.read_bytes());native['registration_scope']=STRICT
        receipt.write_text(json.dumps(native),encoding='utf8')
        with self.assertRaisesRegex(ValueError,'REGISTRATION_SCOPE_MISMATCH'):
            fixtures.contracts.verify(out)
        del native['registration_scope']
        receipt.write_text(json.dumps(native),encoding='utf8')
        self.assertEqual(fixtures.contracts.verify(out)['registration_scope'],LEGACY)

    def test_forward_registration_omits_development_and_checks_both_windows(self):
        request=self.request
        request['design_kind']='forward_paper'
        request['design_terms'].update(variant_decision_record={'proposal':'decision ledger'},
                                       quote_order_fill_reconciliation={'proposal':'retained quote and order records'})
        request['proposed_decision_rules'].append(dict(request['proposed_decision_rules'][1],purpose='operations'))
        with self.assertRaisesRegex(ValueError,'DESIGN_CONTROL_FIELDS_REQUIRED'):
            self.report(request)
        del request['strategy_registration']['development_fraction']
        row=self.report(request)
        self.assertEqual(row['strategy_registration']['evaluation']['start']['value'],'2029-02-01')
        self.assertNotIn('development_validation_split',row['design_terms'])
