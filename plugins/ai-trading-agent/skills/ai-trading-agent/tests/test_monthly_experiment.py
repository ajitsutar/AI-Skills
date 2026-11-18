"""Observable monthly timing/cap/shortlist invariants; fictional offline inputs."""
import copy
import json
import math
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import monthly_experiment as m
import portfolio_backtest
import quant_workbench
from quant_common import digest


def target_document():
    days=['2024-01-25','2024-01-26','2024-01-29','2024-01-30','2024-01-31','2024-02-01','2024-02-02']
    return {'composition_mode':'fixed_adaptive','symbols':['A','B'],
        'as_of':'2024-02-02T22:00:00Z','start':'2024-01-31','end':'2024-01-31',
        'calendar':[{'session_date':d,'close_utc':d+'T21:00:00Z'} for d in days],
        'calendar_evidence':'FICTIONAL_EXPLICIT_SESSIONS','lookback':3,'ddof':1,'equity_weight':.99,'cap':.6,
        'observations':[{'session_date':d,'available_at':d+'T21:00:00Z','prices':{'A':a,'B':b}}
            for d,a,b in zip(days,[100,101,104,102,105,210,231],[100,104,102,110,106,212,233.2])]}


def design():
    return {'composition_mode':'fixed_adaptive',
      'candidates':[{'candidate_id':s,'symbols':['A','B']} for s in ['P1','P2','P3']],
      'counts':{'screen':3,'finalists':2,'selected':1},
      'screen_window':{'start':'2025-10-30','end':'2026-10-30'},
      'final_window':{'start':'2021-10-29','end':'2026-10-30'},
      'weighting_rule':{'method':'capped_inverse_volatility','lookback':60,'ddof':1,'equity_weight':.99,'cap':.6},
      'benchmark':{'symbol':'FICTIONAL_INDEX','entry':'matched-next-close','policy':'buy-and-hold'},
      'execution_convention':'next_session_close','cash_treatment':'1%pre-fee target;zero interest',
      'tax_treatment':'excluded','universe_vintage':'current_names_retrospective',
      'source_contract':{'provider':'fictional','prices_sha256':'a'*64},
      'base_one_way_cost_bps':10,'stress_one_way_cost_bps':[25],
      'sealed_at':'2026-10-31T10:00:00Z'}


def attempts(frozen,stage='screen',ids=None):
    return [{'candidate_id':s,'status':'COMPUTED',
       'window':frozen['contract']['screen_window' if stage=='screen' else 'final_window'],
       'one_way_cost_bps':10,'result_sha256':digest({'fictional':s,'stage':stage}),
       'accounting_input_sha256':digest({'fictional_accounting_input':s,'stage':stage}),
       'result_contract':{'experiment_contract_sha256':frozen['contract_sha256'],
           'symbols':next(r['symbols'] for r in frozen['contract']['candidates'] if r['candidate_id']==s),
           **{k:copy.deepcopy(frozen['contract'][k]) for k in ('weighting_rule','execution_convention','cash_treatment','tax_treatment','benchmark','source_contract')}},
       'metrics':{'cagr':.1+i*.01,'sharpe':1+i*.01,'max_drawdown':.2-i*.01,'annual_gross_turnover':1.}}
       for i,s in enumerate(ids or ['P1','P2','P3'])]


def screen(frozen):
    return m.rank_stage({'frozen':frozen,'stage':'screen','results':attempts(frozen),'sealed_at':'2026-10-31T10:01:00Z'})


class WaterfillTests(unittest.TestCase):
    def test_saturating_cap_does_not_renormalize_above_cap(self):
        r=m.capped_inverse_volatility({'volatilities':{'A':.01,'B':.2,'C':.2},'equity_weight':.99,'cap':.4})
        self.assertEqual(r['weights']['A'],.4)
        self.assertAlmostEqual(r['weights']['B'],.295)
        self.assertAlmostEqual(math.fsum(r['weights'].values()),.99)
        self.assertAlmostEqual(r['cash_weight_before_fees'],.01)

    def test_order_independence_and_extreme_volatility(self):
        d={'volatilities':{'C':1e-200,'A':2e-200,'B':3e-200},'equity_weight':.99,'cap':.4}
        a=m.capped_inverse_volatility(d)['weights']
        d['volatilities']=dict(reversed(list(d['volatilities'].items())))
        self.assertEqual(a,m.capped_inverse_volatility(d)['weights'])

    def test_infeasible_or_nonfinite_or_zero_rejected(self):
        for v,cap in [({'A':0,'B':1},.6),({'A':float('nan'),'B':1},.6),({'A':1,'B':2},.4),({'A':True,'B':1},.6)]:
            with self.subTest(v=v,cap=cap), self.assertRaises(ValueError):
                m.capped_inverse_volatility({'volatilities':v,'cap':cap})


class MonthlyTargetTests(unittest.TestCase):
    def test_next_close_and_only_prior_prices(self):
        d=target_document();a=m.monthly_targets(d)
        self.assertEqual(a['status'],'COMPLETE_TARGETS')
        t=a['decisions'][0]
        self.assertEqual(t['formation_date'],'2024-01-31')
        self.assertEqual(t['execution_date'],'2024-02-01')
        self.assertEqual(t['known_at'],'2024-01-31T21:00:01+00:00')
        d['observations'][-1]['prices']['A']=999999
        self.assertEqual(t,m.monthly_targets(d)['decisions'][0])

    def test_truncated_calendar_rejected_not_last_price_month_end(self):
        d=target_document(); d['calendar']=d['calendar'][:5]
        with self.assertRaisesRegex(ValueError,'EXTEND_INTO_FOLLOWING_MONTH'):
            m.monthly_targets(d)

    def test_declared_holiday_and_pending_signal(self):
        d=target_document()
        d['calendar']=d['calendar'][:5]+[{'session_date':'2024-02-05','close_utc':'2024-02-05T21:00:00Z'}]
        d['observations']=d['observations'][:5]
        d['as_of']='2024-01-31T22:00:00Z'
        t=m.monthly_targets(d)['decisions'][0]
        self.assertEqual(t['execution_date'],'2024-02-05')
        self.assertEqual(t['state'],'PENDING')
        self.assertFalse(m.monthly_targets(d)['calendar_and_source_authenticity_verified'])

    def test_late_known_price_missing_price_and_zero_vol_keep_failure(self):
        for kind in ['late','missing','zero']:
            d=target_document()
            if kind=='late': d['observations'][4]['available_at']='2024-02-01T20:00:00Z'
            if kind=='missing': d['observations'].pop(3)
            if kind=='zero':
                for r in d['observations']: r['prices']['A']=100
            result=m.monthly_targets(d)
            self.assertEqual(result['status'],'INCOMPLETE_TARGETS')
            self.assertEqual(len(result['failures']),1)
            self.assertEqual(result['decisions'],[])

    def test_future_and_changed_composition_rejected(self):
        d=target_document();d['observations'][-1]['available_at']='2024-02-03T00:00:00Z'
        with self.assertRaisesRegex(ValueError,'AVAILABILITY_OUTSIDE_CUTOFF'):m.monthly_targets(d)
        d=target_document();d['observations'][-1]['prices']['C']=12
        with self.assertRaisesRegex(ValueError,'FIXED_PRICE_UNIVERSE_MISMATCH'):m.monthly_targets(d)
        d=target_document();d['composition_mode']='reselection'
        with self.assertRaisesRegex(ValueError,'RESELECTION_REQUIRES'):m.monthly_targets(d)

    def test_equal_mode_keeps_zero_vol_names_and_funds_native_entry(self):
        d=target_document();d['composition_mode']='fixed_equal'
        for row in d['observations']:row['prices']['A']=100
        t=m.monthly_targets(d)['decisions'][0]
        self.assertEqual(t['weights'],[.495,.495])
        base={'symbols':['A','B'],'initial_equity':1000,'initial_weights':[0,0],
            'cash_floor':0,'return_basis':'total_return_decimal','universe_evidence':'FICTIONAL','corporate_action_evidence':'FICTIONAL',
            'periods':[{'start':'2024-01-31T21:00:00Z','end':'2024-02-01T21:00:00Z','returns':{'A':1,'B':1},'tradable':{'A':True,'B':True},'cash_return':0,'benchmark_return':0},
            {'start':'2024-02-01T21:00:00Z','end':'2024-02-02T21:00:00Z','returns':{'A':.1,'B':.1},'tradable':{'A':True,'B':True},'cash_return':0,'benchmark_return':0,
             'decision':{'known_at':t['known_at'],'weights':t['weights'],'evidence_hash':t['source_window_sha256']},
             'one_way_costs':[.001,.001],'impact_coefficients':[0,0],'max_trade_values':[10000,10000]}]}
        r=portfolio_backtest.simulate(base)
        self.assertEqual(r['curve'][0]['equity'],1000)
        self.assertAlmostEqual(r['curve'][-1]['equity'],1098.01)
        self.assertAlmostEqual(r['costs_paid'],.99)
        base['periods'][1]['decision']['weights']=[.5,.5]
        with self.assertRaisesRegex(ValueError,'CASH_FLOOR_AFTER_COSTS'):portfolio_backtest.simulate(base)


class StageTests(unittest.TestCase):
    def test_wrong_composition_or_retuned_policy_result_rejected(self):
        frozen=m.freeze_experiment(design())
        for key,value in [('symbols',['A','C']),('weighting_rule',{'method':'retuned'}),
                          ('execution_convention','same_month_end_close'),
                          ('experiment_contract_sha256','0'*64)]:
            rows=attempts(frozen);rows[0]['result_contract'][key]=value
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'RESULT_DESIGN_OR_COMPOSITION_MISMATCH'):
                m.rank_stage({'frozen':frozen,'stage':'screen','results':rows,'sealed_at':'2026-10-31T10:01:00Z'})
        rows=attempts(frozen);rows[0].pop('accounting_input_sha256')
        with self.assertRaisesRegex(ValueError,'ACCOUNTING_INPUT_HASH_REQUIRED'):
            m.rank_stage({'frozen':frozen,'stage':'screen','results':rows,'sealed_at':'2026-10-31T10:01:00Z'})

    def test_explicit_unsupported_ranking_policy_is_not_silently_replaced(self):
        for key,value in [('score',{'cagr':1,'sharpe':0,'max_drawdown':0}),
                          ('tie_break',['candidate_id'])]:
            d=design();d[key]=value
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'UNSUPPORTED_EXPLICIT'):
                m.freeze_experiment(d)
        d=design();d['score']=dict(m.SCORE)
        d['tie_break']=['lower_annual_gross_turnover','candidate_id']
        self.assertEqual(m.freeze_experiment(d)['contract']['score'],m.SCORE)

    def test_freeze_then_sealed_shortlist_then_final(self):
        frozen=m.freeze_experiment(design());parent=screen(frozen)
        self.assertEqual(parent['selected_ids'],['P3','P2'])
        r=m.rank_stage({'frozen':frozen,'stage':'final','screen_receipt':parent,
            'final_data_opened_at':'2026-10-31T10:02:00Z','sealed_at':'2026-10-31T10:03:00Z',
            'results':attempts(frozen,'final',parent['selected_ids'])})
        self.assertEqual(r['selected_ids'],['P2'])
        self.assertTrue(r['windows_overlap'])
        self.assertFalse(r['untouched_holdout_established'])

    def test_changed_contract_or_shortlist_or_early_final_data_rejected(self):
        frozen=m.freeze_experiment(design());parent=screen(frozen)
        doc={'frozen':frozen,'stage':'final','screen_receipt':parent,'final_data_opened_at':'2026-10-31T10:02:00Z',
             'sealed_at':'2026-10-31T10:03:00Z','results':attempts(frozen,'final',parent['selected_ids'])}
        for kind in ['contract','shortlist','timestamp','forged_receipt']:
            d=copy.deepcopy(doc)
            if kind=='contract':d['frozen']['contract']['weighting_rule']['cap']=.8
            if kind=='shortlist':d['screen_receipt']['selected_ids'].reverse()
            if kind=='timestamp':d['final_data_opened_at']=parent['sealed_at']
            if kind=='forged_receipt':
                d['screen_receipt']['selected_ids'].reverse()
                d['screen_receipt']['receipt_sha256']=digest({k:v for k,v in d['screen_receipt'].items() if k!='receipt_sha256'})
            with self.subTest(kind=kind),self.assertRaises(ValueError):m.rank_stage(d)

    def test_failures_cannot_be_silently_omitted_or_substituted(self):
        frozen=m.freeze_experiment(design());rows=attempts(frozen)
        for row in rows[:2]:row.update(status='UNPRICEABLE',reason='Fictional missing history')
        r=m.rank_stage({'frozen':frozen,'stage':'screen','results':rows,'sealed_at':'2026-10-31T10:01:00Z'})
        self.assertEqual(r['status'],'INSUFFICIENT_VALID_CANDIDATES')
        self.assertEqual(r['selected_ids'],[])
        self.assertEqual(len(r['failures']),2)
        with self.assertRaisesRegex(ValueError,'ALL_EXPECTED_ATTEMPTS_REQUIRED'):
            m.rank_stage({'frozen':frozen,'stage':'screen','results':rows[1:],'sealed_at':'2026-10-31T10:01:00Z'})

    def test_metric_ties_use_turnover_then_id_and_mismatched_cost_fails(self):
        frozen=m.freeze_experiment(design());rows=attempts(frozen)
        for row in rows:row['metrics']={'cagr':.1,'sharpe':1,'max_drawdown':.2,'annual_gross_turnover':1}
        rows[2]['metrics']['annual_gross_turnover']=.5
        r=m.rank_stage({'frozen':frozen,'stage':'screen','results':rows,'sealed_at':'2026-10-31T10:01:00Z'})
        self.assertEqual(r['selected_ids'],['P3','P1'])
        self.assertEqual(r['ranked'][0]['exact_score'],'1/2')
        rows[0]['one_way_cost_bps']=25
        with self.assertRaisesRegex(ValueError,'STAGE_COST_MISMATCH'):
            m.rank_stage({'frozen':frozen,'stage':'screen','results':rows,'sealed_at':'2026-10-31T10:01:00Z'})

    def test_workbench_native_routes_and_cutoff_and_chaining(self):
        doc={'schema_version':1,'contract':{'prompt':'fictional','purpose':'research','base_currency':'USD','horizon_id':'P1Y','as_of':'2026-10-31T11:00:00Z'},
             'jobs':[{'id':'freeze','operation':'experiment.freeze','inputs':{'document':design()}}]}
        result=quant_workbench.run(doc)['results'][0]
        self.assertEqual(result['status'],'COMPUTED')
        parent=screen(result['result'])
        parent['execution_authorized']=False
        final=m.rank_stage({'frozen':result['result'],'stage':'final','screen_receipt':parent,
            'final_data_opened_at':'2026-10-31T10:02:00Z','sealed_at':'2026-10-31T10:03:00Z',
            'results':attempts(result['result'],'final',parent['selected_ids'])})
        self.assertEqual(final['status'],'RANKED_STAGE')
        doc['contract']['as_of']='2026-10-30T11:00:00Z'
        self.assertEqual(quant_workbench.run(doc)['results'][0]['status'],'REJECTED_INPUT')
        for op in ['portfolio.capped_inverse_volatility','backtest.monthly_targets','experiment.freeze','experiment.rank_stage']:
            self.assertIn(op,quant_workbench.operation_catalog()['operations'])


if __name__=='__main__':unittest.main()
