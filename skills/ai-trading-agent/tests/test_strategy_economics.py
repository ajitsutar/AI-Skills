import copy
import json
import unittest
from pathlib import Path

import test_strategy_registration as fixtures
from strategy_economics import adverse_shortfall_bps, economics_schema


class StrategyEconomicsTests(unittest.TestCase):
    def setUp(self):
        base = fixtures.StrategyRegistrationTests()
        base.setUp()
        self.addCleanup(base.doCleanups)
        self.base = base
        source = json.loads(base.source.read_bytes())
        source['strategies'][0].update(windows=[4,12], trade_fee=7, active=True)
        base.source.write_text(json.dumps(source), encoding='utf8')
        self.options = copy.deepcopy(base.request)
        registration = self.options['strategy_registration']
        registration['economics'] = economics_schema()
        e = registration['economics']
        e['cost_bps_per_side'] = {'record_pointer':'/trade_fee'}
        e['signal']['windows'] = {'record_pointer':'/windows'}
        del self.options['design_terms']['execution_convention']
        c = self.options['answer_controls']
        for key in ('warmup','initial_state'):
            del c[key]
        for key in ('event_unit','minimum_events'):
            del c['sample'][key]
        c['variants']['primary'] = {'record_pointer':'/windows'}

    def entry(self, choices, name):
        out = self.base.directory/name
        result = self.base.entry(choices,'--executable-design',out)
        return result,out

    def test_real_request_source_rows_render_and_verification(self):
        result,out = self.entry(self.options,'registered-economics')
        self.assertEqual(result.returncode,0,result.stderr)
        checked = fixtures.fixtures.contracts.verify(out,out/'answer.md',out/'answer-rows.json')
        self.assertEqual(checked['operation'],'strategy-answer')
        row = json.loads((out/'answer-rows.json').read_bytes())[0]
        e = row['strategy_registration']['economics']
        self.assertEqual(e['cost_bps_per_side'],{'basis':'supplied','record_pointer':'/trade_fee','value':7})
        self.assertEqual(e['signal']['windows']['value'],[4,12])
        self.assertEqual(e['position']['entry_equity_fraction'],{'basis':'proposed','value':1.0})
        self.assertEqual((out/'source-bytes/__research_request__/original.txt').read_bytes(),
                         (self.base.directory/'question.txt').read_bytes())
        words = (out/'answer.md').read_text(encoding='utf8')
        for text in ('4 and 12','first nonzero','Equality before seeding','negative-to-positive',
                     'next','fraction × C','1 − k','receivable','settled idle cash','pre-trade NAV',
                     'Flat holds','terminal mark'):
            self.assertIn(text,words)
        self.assertEqual(row['answer_controls']['sample']['minimum_events'],3)
        self.assertNotIn('execution_quality',e)

    def test_forward_registers_distinct_order_quality_and_primary_activity(self):
        opt = self.options
        opt['design_kind'] = 'forward_paper'
        del opt['strategy_registration']['development_fraction']
        e = opt['strategy_registration']['economics']
        e['execution_quality'] = {'minimum_on_time_filled_fraction':0.85,'maximum_adverse_shortfall_bps':18}
        opt['design_terms'].update(variant_decision_record={'proposal':'primary and secondary journals'},
                                    quote_order_fill_reconciliation={'proposal':'reconcile independent orders and fills'})
        opt['proposed_decision_rules'].append(dict(opt['proposed_decision_rules'][1],purpose='operations'))
        result,out = self.entry(opt,'forward-economics')
        self.assertEqual(result.returncode,0,result.stderr)
        row = json.loads((out/'answer-rows.json').read_bytes())[0]
        self.assertEqual(row['strategy_registration']['economics']['execution_quality'],e['execution_quality'])
        text = (out/'answer.md').read_text(encoding='utf8')
        for phrase in ('fraction ≥ 0.85','≤ 18 bps','unfilled opportunity cost','arrival bid/ask midpoint',
                       'unresolved identity','opening-auction fill','intended quantity','zero','fully executed exit',
                       'sum(q_i × (P_i − M)) + U × (C − M)','fee-free buy of 100 shares at 101 against arrival 100 costs 100 bps'):
            self.assertIn(phrase,text)
        self.assertIn('forward_reconciliation',row)
        del e['execution_quality']
        rejected,_ = self.entry(opt,'no-quality')
        self.assertNotEqual(rejected.returncode,0)

    def test_missing_inconsistent_or_inapplicable_controls_are_rejected(self):
        alterations = [
            (('strategy_registration','economics','cost_bps_per_side'),{'proposal':-2}),
            (('strategy_registration','economics','cost_bps_per_side'),{'record_pointer':'/absent'}),
            (('strategy_registration','economics','position','entry_equity_fraction'),{'proposal':True}),
            (('strategy_registration','economics','position','entry_equity_fraction'),{'proposal':1.2}),
            (('strategy_registration','economics','signal','windows'),{'proposal':[8,16]}),
            (('strategy_registration','economics','signal','windows'),{'proposal':[4,2]}),
            (('strategy_registration','economics','signal'),{'kind':'binary_target','target_field':{'record_pointer':'/trade_fee'}}),
            (('strategy_registration','economics','sample','minimum_completed_round_trips'),1),
            (('strategy_registration','benchmark','cash_return'),{'convention':'unavailable'}),
            (('answer_controls','initial_state'),'start long'),
            (('answer_controls','sample','event_unit'),'any decision row'),
            (('design_terms','execution_convention'),{'proposal':'same close'}),
        ]
        for i,(keys,value) in enumerate(alterations):
            with self.subTest(keys=keys):
                request = copy.deepcopy(self.options)
                node = request
                for key in keys[:-1]:
                    node=node[key]
                node[keys[-1]]=value
                rejected,out=self.entry(request,'invalid-'+str(i))
                self.assertNotEqual(rejected.returncode,0)
                self.assertFalse(out.exists())
        del self.options['strategy_registration']['economics']
        rejected,_ = self.entry(self.options,'missing-economics')
        self.assertIn('EXECUTABLE_ECONOMIC_DESIGN_REQUIRED',rejected.stderr)

    def test_known_boolean_level_has_distinct_first_observation_policy(self):
        e = self.options['strategy_registration']['economics']
        e['signal'] = {'kind':'binary_target','target_field':{'record_pointer':'/active'}}
        self.options['answer_controls']['variants']['primary']={'record_pointer':'/active'}
        result,out = self.entry(self.options,'binary-target')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('first qualified true target from flat schedules entry',(out/'answer.md').read_text(encoding='utf8'))

    def test_signed_quantity_weighted_shortfall_and_residual(self):
        from decimal import Decimal
        self.assertEqual(adverse_shortfall_bps('buy', 100, 100, [(100,101)], 0), 100)
        self.assertEqual(adverse_shortfall_bps('buy', 100, 100, [(30,99),(20,102)], 5, 103), 165)
        self.assertEqual(adverse_shortfall_bps('sell', 100, 100, [(25,99),(35,98)], 5, 97), 220)
        self.assertEqual(adverse_shortfall_bps('sell', 100, 100, [(100,103)], 2), 0)
        self.assertEqual(adverse_shortfall_bps('buy', Decimal('0.5'), 100, [], Decimal('0.25'), 101), 150)
        for fills, close in (([(101,101)],None), ([(50,101)],None), ([(0,101)],100)):
            with self.subTest(fills=fills), self.assertRaises(ValueError):
                adverse_shortfall_bps('buy', 100, 100, fills, 0, close)

    def test_primary_is_the_executable_signal_for_sourced_and_proposed_rules(self):
        variants = self.options['answer_controls']['variants']
        signal = self.options['strategy_registration']['economics']
        for i, primary in enumerate(({'record_pointer':'/active'},{'proposal':'SMA(5,12)'})):
            variants['primary'] = primary
            rejected,_ = self.entry(self.options,'mismatched-sma-'+str(i))
            self.assertIn('PRIMARY_AND_SIGNAL_WINDOWS_DISAGREE',rejected.stderr)
        variants['primary'] = {'proposal':'SMA(4,12)'}
        ok,_ = self.entry(self.options,'proposed-sma')
        self.assertEqual(ok.returncode,0,ok.stderr)
        signal['signal'] = {'kind':'binary_target','target_field':{'record_pointer':'/active'}}
        for i, primary in enumerate(({'record_pointer':'/windows'},{'proposal':'binary_target(/other)'})):
            variants['primary'] = primary
            rejected,_ = self.entry(self.options,'mismatched-binary-'+str(i))
            self.assertIn('PRIMARY_AND_SIGNAL_FIELDS_DISAGREE',rejected.stderr)
        variants['primary'] = {'proposal':'binary_target(/active)'}
        ok,_ = self.entry(self.options,'proposed-binary')
        self.assertEqual(ok.returncode,0,ok.stderr)
