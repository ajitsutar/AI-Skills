from pathlib import Path
import copy
import json
import math
import subprocess
import tempfile
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import fundamental_toolkit as f


def valuation():
    return {'cash_flow_type':'FCFF','discount_rate_basis':'WACC','discount_rate':.1,'terminal_growth':0,
            'annual_cash_flows':[10,10],'terminal_next_cash_flow':10,'shares':10,
            'equity_bridge':{'excess_cash':5,'nonoperating_assets':2,'debt':20,'other_claims':3}}


def accounting():
    return {'sales':100,'cogs':60,'receivables':10,'current_assets':40,'net_ppe':40,'assets':100,
            'depreciation':4,'depreciation_amortization':4,'sga':10,'current_liabilities':20,'long_term_debt':20,
            'cash':5,'current_maturities_ltd':5,'tax_payable':2}


def projection():
    return {'company_type':'nonfinancial','tax_loss_policy':'no_benefit', 'opening_revenue':100,
            'opening':{'cash':20,'receivables':10,'inventory':10,'net_ppe':60,'payables':10,'debt':30,'equity':60},
            'years':[{'revenue_growth':.1,'cogs_fraction':.5,'opex_fraction':.2,'depreciation':6,'capex':10,
                      'interest_rate':.1,'tax_rate':.25,'receivables_fraction':.1,'inventory_fraction':.2,
                      'payables_fraction':.2,'new_debt':0,'debt_repayment':5,'equity_issuance':0,'dividends':4}]}


class FundamentalsTests(unittest.TestCase):
    def test_ratios_dupont_and_peg_units(self):
        r=f.ratios({'revenue':100,'cogs':60,'ebit':20,'net_income':12,'tax_rate':.25,
                    'average_invested_capital':50,'average_assets':80,'average_equity':40,
                    'current_assets':30,'current_liabilities':15,'cash':5,'marketable_securities':2,'receivables':8,
                    'interest_expense':4,'cfo':18,'capex':6,'debt':20,'equity':40,'price':50,'eps':5,'eps_growth_rate':.1})
        self.assertEqual(r['status'],'COMPUTED');a=r['ratios']
        self.assertAlmostEqual(a['roic'],.3);self.assertEqual(a['peg'],1)
        self.assertEqual(a['quick_ratio'],1);self.assertAlmostEqual(a['dupont_roe'],a['roe'])

    def test_missing_ratios_not_zero(self):
        r=f.ratios({'price':50,'eps':-1,'eps_growth_rate':.1,'current_assets':20,'current_liabilities':0})
        self.assertEqual(r['status'],'PARTIAL');self.assertIsNone(r['ratios']['peg']);self.assertIsNone(r['ratios']['current_ratio'])

    def test_piotroski_nine_independent_signals(self):
        p={'beginning_assets':100,'assets':100,'income_before_extraordinary':5,'cfo':4,'long_term_debt':30,
           'current_assets':30,'current_liabilities':20,'sales':100,'cogs':70}
        c={'beginning_assets':100,'assets':100,'income_before_extraordinary':10,'cfo':12,'long_term_debt':20,
           'current_assets':40,'current_liabilities':20,'sales':120,'cogs':72,'equity_issued':False}
        d={'turnover_basis':'beginning_assets','company_type':'nonfinancial','annual_periods_comparable':True,'current':c,'prior':p}
        self.assertEqual(f.piotroski(d)['score'],9)
        c['equity_issued']=True
        self.assertEqual(f.piotroski(d)['score'],8)
        c['cfo']=10
        self.assertEqual(f.piotroski(d)['signals']['cash_exceeds_income'],0)

    def test_piotroski_average_asset_denominators(self):
        p={'beginning_assets':100,'assets':200,'income_before_extraordinary':5,'cfo':4,'long_term_debt':30,
           'current_assets':30,'current_liabilities':20,'sales':150,'cogs':70}
        c={**p,'beginning_assets':200,'assets':400,'sales':300,'equity_issued':False}
        r=f.piotroski({'turnover_basis':'average_assets','company_type':'nonfinancial','annual_periods_comparable':True,'current':c,'prior':p})
        self.assertEqual(r['measures']['current']['turnover'],1);self.assertEqual(r['signals']['higher_turnover'],0)
        self.assertEqual(r['measures']['current']['roa'],.025)

    def test_piotroski_turnover_variant_can_change_score(self):
        p={'beginning_assets':100,'assets':200,'income_before_extraordinary':5,'cfo':4,'long_term_debt':30,
           'current_assets':30,'current_liabilities':20,'sales':150,'cogs':70}
        c={**p,'beginning_assets':200,'assets':220,'sales':270,'equity_issued':False}
        d={'operation':'piotroski','currency':'USD','amount_unit':'USD','company_type':'nonfinancial',
           'annual_periods_comparable':True,'current':c,'prior':p}
        with self.assertRaisesRegex(ValueError,'TURNOVER_BASIS_REQUIRED'): f.run(d)
        a=f.run({**d,'turnover_basis':'beginning_assets'})
        b=f.run({**d,'turnover_basis':'average_assets'})
        self.assertEqual(a['signals']['higher_turnover'],0)
        self.assertEqual(b['signals']['higher_turnover'],1)
        self.assertEqual(b['score'],a['score']+1)
        self.assertNotEqual(a['formula_id'],b['formula_id'])

    def test_cli_output_never_overwrites_input_or_existing_evidence(self):
        script=Path(__file__).resolve().parents[1]/'scripts'/'fundamental_toolkit.py'
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'input.json'
            data=json.dumps({'operation':'ddm','currency':'USD','amount_unit':'USD per share',
                             'next_dividend_per_share':2,'cost_equity':.1,'growth':.02})
            p.write_text(data,encoding='utf-8')
            run=subprocess.run([sys.executable,str(script),'--input',str(p),'--output',str(p)],capture_output=True)
            self.assertNotEqual(run.returncode,0)
            self.assertEqual(p.read_text(encoding='utf-8'),data)
            out=Path(tmp)/'output.json'
            run=subprocess.run([sys.executable,str(script),'--input',str(p),'--output',str(out)],capture_output=True)
            self.assertEqual(run.returncode,0)
            first=out.read_bytes()
            run=subprocess.run([sys.executable,str(script),'--input',str(p),'--output',str(out)],capture_output=True)
            self.assertNotEqual(run.returncode,0);self.assertEqual(out.read_bytes(),first)

    def test_altman_hand_computed_and_applicability(self):
        d={'company_type':'public_manufacturing','annual_periods_comparable':True,'assets':100,
           'working_capital':20,'retained_earnings':10,'ebit':10,'market_equity':60,'total_liabilities':40,'sales':100}
        self.assertAlmostEqual(f.altman(d)['score'],2.610)
        d['company_type']='bank'
        with self.assertRaisesRegex(ValueError,'NOT_APPLICABLE'):f.altman(d)

    def test_beneish_hand_computed_original_accruals(self):
        a=accounting()
        r=f.beneish({'company_type':'nonfinancial','annual_periods_comparable':True,'current':a,'prior':a})
        for k,v in r['indices'].items():self.assertAlmostEqual(v,-.04 if k=='TATA' else 1)
        self.assertAlmostEqual(r['score'],-2.66716)

    def test_beneish_never_imputes_bad_denominator(self):
        a=accounting();b=accounting();b['receivables']=0
        with self.assertRaisesRegex(ValueError,'POSITIVE_DENOMINATOR'):
            f.beneish({'company_type':'nonfinancial','annual_periods_comparable':True,'current':a,'prior':b})
        b=accounting();del b['tax_payable']
        with self.assertRaisesRegex(ValueError,'MISSING_FIELD'):
            f.beneish({'company_type':'nonfinancial','annual_periods_comparable':True,'current':a,'prior':b})

    def test_beneish_separates_depreciation_from_amortization(self):
        a=accounting();b=accounting();a['depreciation_amortization']=6
        r=f.beneish({'company_type':'nonfinancial','annual_periods_comparable':True,'current':a,'prior':b})
        self.assertEqual(r['indices']['DEPI'],1)
        self.assertEqual(r['indices']['TATA'],-.06)

    def test_fixture_golden_hand_calculations(self):
        examples=Path(__file__).resolve().parents[1]/'examples'
        golden=json.loads((examples/'fundamental-golden.json').read_text(encoding='utf-8'))
        for case in golden['cases']:
            with self.subTest(case=case['input']):
                answer=f.run(json.loads((examples/case['input']).read_text(encoding='utf-8')))
                for path,expected in case['expected'].items():
                    actual=answer
                    for key in path.split('.'):
                        actual=actual[int(key)] if isinstance(actual,list) else actual[key]
                    self.assertTrue(math.isclose(actual,expected,abs_tol=1e-9,rel_tol=1e-9),(path,actual,expected))

    def test_every_example_executes(self):
        examples=Path(__file__).resolve().parents[1]/'examples'
        for p in examples.glob('fundamental-*.json'):
            if p.name=='fundamental-golden.json':continue
            with self.subTest(example=p.name):
                answer=f.run(json.loads(p.read_text(encoding='utf-8')))
                self.assertEqual(answer['status'],'COMPUTED')

    def test_monte_carlo_independent_of_json_key_order(self):
        p=Path(__file__).resolve().parents[1]/'examples'/'fundamental-monte-carlo.json'
        d=json.loads(p.read_text(encoding='utf-8'));original=f.run(d)
        d['distributions']=dict(reversed(list(d['distributions'].items())))
        self.assertEqual(f.run(d),original)

    def test_wacc_tax_shield(self):
        r=f.wacc({'market_equity':60,'market_debt':40,'cost_equity':.1,'pretax_cost_debt':.05,'tax_rate':.25})
        self.assertAlmostEqual(r['wacc'],.075)

    def test_full_dcf_perpetuity_and_bridge(self):
        r=f.dcf(valuation())
        self.assertAlmostEqual(r['cash_flow_value'],100);self.assertAlmostEqual(r['equity_value'],84)
        self.assertAlmostEqual(r['per_share'],8.4)
        self.assertAlmostEqual(r['annual'][0]['present_value'],10/1.1)

    def test_dcf_never_double_subtracts_debt_from_fcfe(self):
        d=valuation();d.update(cash_flow_type='FCFE',discount_rate_basis='cost_of_equity')
        with self.assertRaisesRegex(ValueError,'ALREADY_AFTER_DEBT'):f.dcf(d)
        d['equity_bridge'].update(debt=0,other_claims=0)
        self.assertAlmostEqual(f.dcf(d)['equity_value'],107)

    def test_dcf_negative_forecast_cf_and_equity_retained(self):
        d=valuation();d.update(annual_cash_flows=[-10],terminal_next_cash_flow=0)
        self.assertLess(f.dcf(d)['equity_value'],0)

    def test_dcf_rejects_bad_growth_nan_missing_and_basis(self):
        for mutation in ({'terminal_growth':.1},{'terminal_growth':-1},{'discount_rate':float('nan')},{'shares':0},{'discount_rate_basis':'cost_of_equity'}):
            with self.assertRaises(ValueError):f.dcf({**valuation(),**mutation})
        d=valuation();del d['equity_bridge']['debt']
        with self.assertRaisesRegex(ValueError,'MISSING_FIELD'):f.dcf(d)

    def test_reverse_dcf_recovers_known_growth(self):
        v=valuation();v['annual_cash_flows']=[11,12.1];v['terminal_next_cash_flow']=12.1
        target=f.dcf(v)['equity_value']
        r=f.reverse_dcf({'base_cash_flow':10,'target_equity_value':target,'years':2,'growth_low':-.5,'growth_high':.5,'valuation':valuation()})
        self.assertAlmostEqual(r['implied_annual_growth'],.1)
        with self.assertRaisesRegex(ValueError,'OUTSIDE_GROWTH_BRACKET'):
            f.reverse_dcf({'base_cash_flow':10,'target_equity_value':100000,'years':2,'growth_low':-.5,'growth_high':.5,'valuation':valuation()})

    def test_ddm_and_residual_income(self):
        self.assertAlmostEqual(f.ddm({'cost_equity':.1,'growth':.02,'next_dividend_per_share':2})['per_share'],25)
        r=f.residual_income({'opening_book_equity':100,'cost_equity':.1,'years':[{'net_income':15,'dividends':5}], 'terminal_residual_income_value':0})
        self.assertAlmostEqual(r['equity_value'],100+5/1.1);self.assertEqual(r['annual'][0]['closing_book_equity'],110)

    def test_sotp_eliminates_corporate_costs_and_claims(self):
        d={'segments':[{'id':'a','enterprise_value':100},{'id':'b','enterprise_value':50}], 'corporate_cost_present_value':10,
           'excess_cash':5,'nonoperating_assets':2,'debt':30,'other_claims':7,'shares':10}
        r=f.sotp(d);self.assertEqual(r['equity_value'],110);self.assertEqual(r['per_share'],11)
        d['segments'][1]['id']='a'
        with self.assertRaisesRegex(ValueError,'UNIQUE'):f.sotp(d)

    def test_integrated_forecast_balances_cash_and_debt(self):
        r=f.forecast(projection())['annual'][0]
        self.assertAlmostEqual(r['revenue'],110);self.assertAlmostEqual(r['ebit'],27)
        self.assertAlmostEqual(r['interest'],3);self.assertAlmostEqual(r['cash_taxes'],6)
        self.assertAlmostEqual(r['net_income'],18);self.assertAlmostEqual(r['cfo'],23)
        self.assertAlmostEqual(r['fcff'],15.25);self.assertAlmostEqual(r['fcfe'],8)
        self.assertAlmostEqual(r['balance_sheet']['cash'],24);self.assertAlmostEqual(r['balance_sheet']['debt'],25)
        self.assertAlmostEqual(r['balance_sheet']['equity'],74)
        self.assertAlmostEqual(r['balance_residual'],0);self.assertAlmostEqual(r['cash_conservation_residual'],0)

    def test_forecast_multiple_period_conservation(self):
        d=projection();d['years']*=4
        for y in f.forecast(d)['annual']:
            self.assertAlmostEqual(y['balance_residual'],0);self.assertAlmostEqual(y['cash_conservation_residual'],0)

    def test_forecast_rejects_hidden_financing_and_bad_opening(self):
        d=projection();d['years'][0]['dividends']=100
        with self.assertRaisesRegex(ValueError,'UNFUNDED_CASH'):f.forecast(d)
        d=projection();d['opening']['cash']+=1
        with self.assertRaisesRegex(ValueError,'NOT_BALANCED'):f.forecast(d)
        d=projection();d['years'][0]['debt_repayment']=31
        with self.assertRaisesRegex(ValueError,'EXCEEDS_DEBT'):f.forecast(d)

    def test_loss_tax_has_no_imaginary_cash_refund(self):
        d=projection();d['years'][0].update(opex_fraction=.6,new_debt=50,debt_repayment=0,dividends=0)
        r=f.forecast(d)['annual'][0]
        self.assertLess(r['net_income'],0);self.assertEqual(r['cash_taxes'],0);self.assertAlmostEqual(r['balance_residual'],0)

    def test_monte_carlo_reproducible_quantiles_and_domains(self):
        d={'seed':7,'draws':100,'valuation':valuation(),'distributions':{'discount_rate':{'low':.09,'mode':.1,'high':.11},
           'terminal_growth':{'low':0,'mode':.01,'high':.02},'cash_flow_multiplier':{'low':.9,'mode':1,'high':1.1}}}
        a=f.monte_carlo(d);self.assertEqual(a,f.monte_carlo(copy.deepcopy(d)))
        self.assertEqual(list(a['quantiles'].values()),sorted(a['quantiles'].values()))
        d['distributions']['terminal_growth']['high']=.1
        with self.assertRaisesRegex(ValueError,'SUPPORT_INVALID'):f.monte_carlo(d)

    def test_run_requires_units(self):
        with self.assertRaisesRegex(ValueError,'UNIT_REQUIRED'):f.run({'operation':'ddm'})

    def example(self,name):
        return json.loads((Path(__file__).resolve().parents[1]/'examples'/name).read_text(encoding='utf-8'))

    def test_every_operation_rejects_extra_assumptions_and_missing_required_fields(self):
        examples=Path(__file__).resolve().parents[1]/'examples'
        for path in examples.glob('fundamental-*.json'):
            if path.name=='fundamental-golden.json':continue
            packet=json.loads(path.read_text(encoding='utf-8'))
            with self.subTest(operation=packet['operation']), self.assertRaisesRegex(ValueError,'UNKNOWN_FIELDS'):
                f.run({**packet,'unsupported_assumption':7})
            if packet['operation']!='ratios':
                for key in f.SCHEMAS[packet['operation']]:
                    missing=copy.deepcopy(packet);del missing[key]
                    with self.subTest(operation=packet['operation'],missing=key),self.assertRaises(ValueError):
                        f.run(missing)

    def test_explicit_timing_share_basis_and_extra_claims_cannot_be_ignored(self):
        packet=self.example('fundamental-dcf.json')
        for key,value in (('cash_timing','midyear'),('share_unit','individual_shares')):
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'UNKNOWN_FIELDS'):
                f.run({**packet,key:value})
        packet['equity_bridge']['lease_liabilities']=100
        with self.assertRaisesRegex(ValueError,'UNKNOWN_FIELDS'):
            f.run(packet)

    def test_nested_valuation_units_must_match_and_unknown_fields_fail(self):
        for name in ('fundamental-monte-carlo.json','fundamental-reverse-dcf.json'):
            packet=self.example(name)
            if 'draws' in packet:packet['draws']=10
            baseline=f.run(packet)
            for key in ('currency','amount_unit'):
                altered=copy.deepcopy(packet);altered['valuation'][key]='conflicting basis'
                with self.subTest(name=name,key=key),self.assertRaisesRegex(ValueError,'UNIT_MISMATCH'):
                    f.run(altered)
            packet['valuation'].update(currency=packet['currency'],amount_unit=packet['amount_unit'])
            self.assertEqual(f.run(packet),baseline)
            packet['valuation']['cash_timing']='midyear'
            with self.assertRaisesRegex(ValueError,'UNKNOWN_FIELDS'):f.run(packet)

    def test_nested_period_distribution_and_forecast_unknowns_are_rejected(self):
        cases=[('fundamental-piotroski.json',('current',)),('fundamental-beneish.json',('prior',)),
               ('fundamental-forecast.json',('opening',)),('fundamental-forecast.json',('years',0)),
               ('fundamental-monte-carlo.json',('distributions','discount_rate')),
               ('fundamental-residual-income.json',('years',0)),('fundamental-sotp.json',('segments',0))]
        for name,path in cases:
            packet=self.example(name);nested=packet
            for key in path:nested=nested[key]
            nested['ignored_before_review']=99
            with self.subTest(name=name,path=path),self.assertRaisesRegex(ValueError,'UNKNOWN_FIELDS'):
                f.run(packet)

    def test_liquidity_contradiction_only_invalidates_affected_ratios(self):
        packet={'operation':'ratios','currency':'USD','amount_unit':'USD','current_assets':10,'current_liabilities':5,
                'cash':20,'marketable_securities':0,'receivables':0,'revenue':100,'cogs':60,'ebit':20}
        answer=f.run(packet)
        for key in ('current_ratio','quick_ratio'):
            self.assertIsNone(answer['ratios'][key]);self.assertIn('INCONSISTENT',answer['unavailable'][key])
        self.assertEqual(answer['ratios']['gross_margin'],.4)
        self.assertEqual(answer['ratios']['operating_margin'],.2)
        packet['cash']=1;del packet['receivables']
        answer=f.run(packet)
        self.assertEqual(answer['ratios']['current_ratio'],2)
        self.assertIsNone(answer['ratios']['quick_ratio'])
        packet['cash']=20
        self.assertIsNone(f.run(packet)['ratios']['current_ratio'])

    def test_screen_current_assets_cannot_exceed_assets(self):
        packet=self.example('fundamental-piotroski.json')
        packet['current']['current_assets']=packet['current']['assets']+10
        with self.assertRaisesRegex(ValueError,'CURRENT_ASSETS_EXCEED'):f.run(packet)

    def test_non_object_nested_rows_are_structured_invalid_inputs(self):
        for name,key in (('fundamental-sotp.json','segments'),('fundamental-forecast.json','years'),
                         ('fundamental-residual-income.json','years')):
            for bad in (None, 'not an object', 42, []):
                packet=self.example(name);packet[key]=[bad]
                with self.subTest(name=name,bad=bad),self.assertRaisesRegex(ValueError,'OBJECT_REQUIRED'):
                    f.run(packet)
        script=Path(__file__).resolve().parents[1]/'scripts'/'fundamental_toolkit.py'
        with tempfile.TemporaryDirectory() as tmp:
            packet=self.example('fundamental-sotp.json');packet['segments']=[None]
            path=Path(tmp)/'bad.json';path.write_text(json.dumps(packet),encoding='utf-8')
            run=subprocess.run([sys.executable,str(script),'--input',str(path)],capture_output=True,text=True)
            self.assertEqual(run.returncode,2)
            self.assertEqual(json.loads(run.stdout)['status'],'INVALID_INPUT')
            self.assertNotIn('Traceback',run.stderr)

    def test_per_share_unit_and_monetary_scale_invariance(self):
        packet=self.example('fundamental-dcf.json');baseline=f.run(packet)
        self.assertEqual(baseline['per_share_unit'],'USD per share')
        for key in ('terminal_next_cash_flow','shares'):packet[key]*=1e6
        packet['annual_cash_flows']=[x*1e6 for x in packet['annual_cash_flows']]
        packet['equity_bridge']={k:v*1e6 for k,v in packet['equity_bridge'].items()}
        packet['amount_unit']='USD'
        self.assertAlmostEqual(f.run(packet)['per_share'],baseline['per_share'])


if __name__=='__main__':unittest.main()
