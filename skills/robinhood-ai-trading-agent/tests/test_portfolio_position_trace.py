"""Accounting invariants for opt-in position evidence in period simulations."""
import copy
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from portfolio_backtest import simulate


def fixture():
    return {
        'symbols':['A','B'], 'initial_equity':1000, 'initial_weights':[0,0],
        'cash_floor':0, 'return_basis':'total_return_decimal',
        'universe_evidence':'Explicit fictional two-symbol accounting fixture',
        'corporate_action_evidence':'Supplied synthetic total-return inputs; no actual corporate actions',
        'periods':[
            {'start':'2024-01-02T21:00:00Z','end':'2024-01-03T21:00:00Z',
             'returns':{'A':.10,'B':-.05}, 'tradable':{'A':True,'B':True},
             'cash_return':.001,'benchmark_return':0,
             'one_way_costs':[.001,.001],'impact_coefficients':[0,0],
             'max_trade_values':[10000,10000],
             'decision':{'known_at':'2024-01-02T20:59:00Z','weights':[.45,.45],'evidence_hash':'fictional-fixture'}},
            {'start':'2024-01-03T21:00:00Z','end':'2024-01-04T21:00:00Z',
             'returns':{'A':-.02,'B':.04},'tradable':{'A':True,'B':True},
             'cash_return':0,'benchmark_return':0,
             'one_way_costs':[.001,.001],'impact_coefficients':[0,0],
             'max_trade_values':[10000,10000],
             'decision':{'known_at':'2024-01-03T20:59:00Z','weights':[.45,.45],'evidence_hash':'fictional-fixture-two'}}
        ]}


class PositionTraceTests(unittest.TestCase):
    def test_opt_in_preserves_accounting_and_default_output(self):
        base=fixture(); traced=copy.deepcopy(base); traced['include_positions']=True
        plain=simulate(base); result=simulate(traced)
        self.assertNotIn('position_trace',plain)
        self.assertTrue(all('positions' not in r for r in plain['curve']))
        for key in ['metrics','benchmark_total_return','total_return_difference','costs_paid','gross_traded_notional']:
            self.assertEqual(plain[key],result[key])
        for original,row in zip(plain['curve'],result['curve']):
            self.assertEqual(original,{k:v for k,v in row.items() if k!='positions'})
        self.assertEqual(result['position_trace']['final_weights'],result['curve'][-1]['positions']['ending_weights'])

    def test_each_ledger_reconciles_before_and_after_costs_and_returns(self):
        d=fixture();d['include_positions']=True;result=simulate(d)
        previous=None
        for source,row in zip(d['periods'],result['curve']):
            p=row['positions']
            self.assertAlmostEqual(p['opening_cash']+sum(p['opening_holdings'].values()),p['opening_equity'])
            self.assertAlmostEqual(p['post_trade_cash']+sum(p['post_trade_holdings'].values()),p['opening_equity']-row['trade_cost'])
            self.assertAlmostEqual(p['post_trade_cash']-p['opening_cash'],-sum(p['trades'].values())-row['trade_cost'])
            self.assertAlmostEqual(sum(abs(x) for x in p['trades'].values()),row['traded_notional'])
            self.assertAlmostEqual(row['cash']+sum(p['ending_holdings'].values()),row['equity'])
            self.assertAlmostEqual(sum(p['ending_weights'].values())+p['ending_cash_weight'],1)
            for symbol in d['symbols']:
                self.assertAlmostEqual(p['ending_holdings'][symbol],p['post_trade_holdings'][symbol]*(1+source['returns'][symbol]))
            if previous:
                self.assertEqual(p['opening_holdings'],previous['ending_holdings'])
            previous=p
        self.assertAlmostEqual(result['curve'][0]['trade_cost'],.9)

    def test_no_decision_does_not_create_trades(self):
        d=fixture();d['include_positions']=True;del d['periods'][1]['decision']
        row=simulate(d)['curve'][1];p=row['positions']
        self.assertEqual(p['opening_holdings'],p['post_trade_holdings'])
        self.assertEqual(p['opening_cash'],p['post_trade_cash'])
        self.assertEqual(p['trades'],{'A':0.,'B':0.})
        self.assertEqual(row['trade_cost'],0)

    def test_insolvency_retains_dollar_positions_but_not_fictitious_weights(self):
        d=fixture();d['initial_weights']=[1,0];d['include_positions']=True
        d['periods']=d['periods'][:1];row=d['periods'][0];del row['decision']
        row['returns']={'A':-1,'B':0};row['cash_return']=0
        result=simulate(d)
        self.assertEqual(result['curve'][0]['equity'],0)
        self.assertEqual(result['curve'][0]['positions']['ending_holdings'],{'A':0.,'B':0.})
        self.assertIsNone(result['position_trace']['final_weights'])

    def test_trace_flag_rejects_truthy_substitutes(self):
        for invalid in [1,'true',None,[]]:
            with self.subTest(invalid=invalid):
                d=fixture();d['include_positions']=invalid
                with self.assertRaisesRegex(ValueError,'INCLUDE_POSITIONS_MUST_BE_BOOL'):
                    simulate(d)


if __name__=='__main__': unittest.main()
