import copy
import json
import math
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from time_series_toolkit import run


def at(day): return '2026-01-%02dT00:00:00Z'%day
def packet(operation,inputs): return {'schema_version':1,'operation':operation,'inputs':inputs}
def row(day,**values): return {'timestamp':at(day),'available_at':at(day),**values}
def gbm_packet():
    return packet('gbm',{'symbol':'FICTIONAL','price_unit':'USD/share','price_basis':'unadjusted_scenario',
        'initial_price':100,'parameters_available_at':at(1),'start_at':at(1),'mu':0.0,'sigma':0.0,
        'horizon_years':1,'steps':2,'paths':3,'seed':17,'year_basis':'ACT_365_FIXED_SECONDS',
        'distribution':'independent_standard_normal_log_increments','measure':'real_world_scenario',
        'risk_free_rate':None,'dividend_yield':None,'as_of':at(1)})
def trend_packet():
    return packet('trend',{'symbol':'FICT','value_unit':'USD/share','price_basis':'split_adjusted',
        'time_unit':'day','method':'backward_secant_midpoint_acceleration','as_of':at(5),
        'rows':[row(1,value=0),row(2,value=1),row(4,value=9)]})
def pair_packet():
    return packet('pair_ols',{'x_symbol':'X','y_symbol':'Y','x_unit':'USD/share','y_unit':'USD/share',
        'price_basis':'split_adjusted','train_cutoff':at(3),'as_of':at(6),
        'standard_deviation':'population_training_residual','minimum_x_variance':1e-12,
        'minimum_spread_std':1e-12,'train_rows':[row(1,x=1,y=3),row(2,x=2,y=3),row(3,x=3,y=6)],
        'test_rows':[row(4,x=4,y=8)]})


class TimeSeriesTests(unittest.TestCase):
    def test_gbm_zero_parameters_golden(self):
        r=run(gbm_packet())
        self.assertEqual(r['paths'],[[100,100,100]]*3)
        self.assertEqual(r['expected_terminal_price'],100)
        self.assertEqual(r['terminal_price_variance'],0)
        self.assertEqual(r['end_at'],'2027-01-01T00:00:00Z')

    def test_gbm_deterministic_compounding(self):
        p=gbm_packet();p['inputs']['mu']=math.log(2)
        r=run(p)
        for path in r['paths']:
            self.assertAlmostEqual(path[1],100*math.sqrt(2))
            self.assertAlmostEqual(path[-1],200)

    def test_gbm_seed_isolation_path_prefix_and_no_input_mutation(self):
        p=gbm_packet();p['inputs']['sigma']=0.25;old=copy.deepcopy(p)
        first=run(p);random.seed(999);random.random();self.assertEqual(first,run(p));self.assertEqual(p,old)
        p['inputs']['paths']=5
        self.assertEqual(first['paths'],run(p)['paths'][:3])
        p['inputs']['seed']=18
        self.assertNotEqual(first['paths'],run(p)['paths'][:3])

    def test_gbm_distribution_moments_independent_analytic_check(self):
        p=gbm_packet();p['inputs'].update(mu=.07,sigma=.2,steps=1,paths=50000,seed=481)
        r=run(p);terminal=[v[-1] for v in r['paths']]
        expected=100*math.exp(.07);variance=10000*math.exp(.14)*(math.exp(.04)-1)
        empirical_var=sum((v-r['sample_terminal_mean'])**2 for v in terminal)/len(terminal)
        self.assertLess(abs(r['sample_terminal_mean']-expected),5*math.sqrt(variance/len(terminal)))
        self.assertLess(abs(empirical_var-variance)/variance,.04)

    def test_gbm_risk_neutral_mu_contract(self):
        p=gbm_packet();p['inputs'].update(measure='risk_neutral',mu=.03,risk_free_rate=.05,dividend_yield=.02)
        self.assertAlmostEqual(run(p)['expected_terminal_price'],100*math.exp(.03))
        p['inputs']['mu']=.04
        with self.assertRaisesRegex(ValueError,'RATE_MINUS_YIELD'):run(p)

    def test_gbm_negative_price_limits_and_overflow(self):
        for field,value,error in [('initial_price',-1,'POSITIVE'),('sigma',-1,'BELOW'),('steps',False,'INTEGER'),('mu',1000,'OVERFLOW'),('mu',-10000,'UNDERFLOW')]:
            p=gbm_packet();p['inputs'][field]=value
            with self.assertRaisesRegex(ValueError,error):run(p)
        p=gbm_packet();p['inputs'].update(paths=100000,steps=100000)
        with self.assertRaisesRegex(ValueError,'CELL_LIMIT'):run(p)

    def test_gbm_nonzero_variance_underflow_rejected(self):
        p=gbm_packet();p['inputs'].update(initial_price=1e-200,sigma=.2)
        with self.assertRaisesRegex(ValueError,'VARIANCE_OVERFLOW_OR_UNDERFLOW'):run(p)
        # Deterministic zero variance remains valid at the same price magnitude.
        p['inputs']['sigma']=0
        self.assertEqual(run(p)['terminal_price_variance'],0)
        p=gbm_packet();p['inputs']['sigma']=1e-200
        with self.assertRaisesRegex(ValueError,'VARIANCE_OVERFLOW_OR_UNDERFLOW'):run(p)

    def test_gbm_expected_price_underflow_rejected_even_if_sample_positive(self):
        # The seeded path rounds to a positive subnormal, while E[S_T] rounds to zero.
        p=gbm_packet();p['inputs'].update(initial_price=5e-324,mu=-1,sigma=1,steps=1,paths=1,seed=2)
        with self.assertRaisesRegex(ValueError,'EXPECTED_PRICE_OVERFLOW_OR_UNDERFLOW'):run(p)

    def test_trend_irregular_quadratic_golden(self):
        r=run(trend_packet())['rows']
        self.assertIsNone(r[0]['velocity']);self.assertIsNone(r[0]['acceleration'])
        self.assertEqual(r[1]['velocity'],1);self.assertIsNone(r[1]['acceleration'])
        self.assertEqual(r[2]['velocity'],4);self.assertEqual(r[2]['acceleration'],2)

    def test_trend_time_scaling_translation_and_prefix(self):
        p=trend_packet();base=run(p)['rows'];p['inputs']['rows'].append(row(5,value=-99))
        self.assertEqual(run(p)['rows'][:3],base)
        p=trend_packet();p['inputs']['time_unit']='hour';r=run(p)['rows']
        self.assertAlmostEqual(r[2]['velocity'],4/24);self.assertAlmostEqual(r[2]['acceleration'],2/24**2)
        p=trend_packet()
        for r in p['inputs']['rows']:r['value']+=10000
        self.assertEqual(run(p)['rows'],base)

    def test_trend_delayed_availability_propagates(self):
        p=trend_packet();p['inputs']['rows'][1]['available_at']=at(5)
        r=run(p)['rows'];self.assertEqual(r[2]['available_at'],at(5))
        p['inputs']['as_of']=at(4)
        with self.assertRaisesRegex(ValueError,'AVAILABILITY'):run(p)

    def test_pair_ols_hand_calculated(self):
        r=run(pair_packet())
        self.assertEqual(r['alpha'],1);self.assertEqual(r['beta'],1.5)
        self.assertEqual(r['train_residuals'],[.5,-1,.5])
        self.assertAlmostEqual(r['train_residual_population_std'],math.sqrt(.5))
        self.assertEqual(r['test_rows'][0]['spread'],1)
        self.assertAlmostEqual(r['test_rows'][0]['z_score'],math.sqrt(2))

    def test_pair_future_test_does_not_refit(self):
        p=pair_packet();r=run(p);p['inputs']['test_rows'].append(row(5,x=2000,y=-10000));s=run(p)
        for key in ('alpha','beta','train_residual_population_std','train_residuals'):
            self.assertEqual(r[key],s[key])
        self.assertEqual(r['test_rows'][0],s['test_rows'][0])

    def test_pair_y_translation_preserves_spread(self):
        p=pair_packet();r=run(p)
        for rows in ('train_rows','test_rows'):
            for v in p['inputs'][rows]:v['y']+=100
        s=run(p);self.assertEqual(s['alpha'],r['alpha']+100);self.assertEqual(s['test_rows'],r['test_rows'])

    def test_pair_degenerate_and_leakage_rejected(self):
        p=pair_packet()
        for r in p['inputs']['train_rows']:r['x']=1
        with self.assertRaisesRegex(ValueError,'X_VARIANCE'):run(p)
        p=pair_packet()
        for r in p['inputs']['train_rows']:r['y']=r['x']*2+1
        with self.assertRaisesRegex(ValueError,'RESIDUAL_STD'):run(p)
        p=pair_packet();p['inputs']['train_rows'][0]['available_at']=at(4)
        with self.assertRaisesRegex(ValueError,'AVAILABILITY'):run(p)
        p=pair_packet();p['inputs']['test_rows'][0]['timestamp']=at(3)
        with self.assertRaisesRegex(ValueError,'FOLLOW_TRAIN'):run(p)

    def test_strict_schema_and_timestamps(self):
        for bad in ('2026-01-01T00:00:00+00:99','2026-W01-1','2026-02-30T00:00:00Z','2026-01-01T24:00:00Z','2026-01-01'):
            p=trend_packet();p['inputs']['as_of']=bad
            with self.assertRaises(ValueError):run(p)
        p=trend_packet();p['inputs']['unknown']='ignored'
        with self.assertRaisesRegex(ValueError,'EXACT_FIELDS'):run(p)
        p=trend_packet();p['inputs']['rows'][0]['value']=float('nan')
        with self.assertRaisesRegex(ValueError,'FINITE'):run(p)
        p=trend_packet();p['inputs']['rows'][0]=None
        with self.assertRaisesRegex(ValueError,'OBJECT'):run(p)
        p=trend_packet();p['inputs']['rows'][1]['timestamp']=at(1)
        with self.assertRaisesRegex(ValueError,'TIME_ORDER'):run(p)
        p=trend_packet();p['inputs']['rows'][0]['value']=True
        with self.assertRaisesRegex(ValueError,'JSON_NUMBER'):run(p)

    def test_example_json_and_cli_preserve_files(self):
        root=Path(__file__).resolve().parents[1]
        examples=list((root/'examples').glob('time-series-*-input.json'))
        self.assertEqual(len(examples),3)
        for path in examples:
            self.assertEqual(run(json.loads(path.read_text()))['status'],'OFFLINE_RESEARCH_CALCULATED')
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'input.json';path.write_text(json.dumps(gbm_packet()));original=path.read_bytes()
            proc=subprocess.run([sys.executable,str(root/'scripts/time_series_toolkit.py'),str(path),'--output',str(path)],capture_output=True)
            self.assertNotEqual(proc.returncode,0);self.assertEqual(path.read_bytes(),original)
            output=Path(directory)/'out.json';output.write_text('retained')
            proc=subprocess.run([sys.executable,str(root/'scripts/time_series_toolkit.py'),str(path),'--output',str(output)],capture_output=True)
            self.assertNotEqual(proc.returncode,0);self.assertEqual(output.read_text(),'retained')

    def test_cli_duplicate_keys_rejected_at_envelope_and_nested_levels(self):
        root=Path(__file__).resolve().parents[1]
        raw=json.dumps(gbm_packet())
        ambiguous=[raw.replace('"schema_version": 1','"schema_version": 999, "schema_version": 1'),
                   raw.replace('"mu": 0.0','"mu": 0.9, "mu": 0.0')]
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'input.json';output=Path(directory)/'output.json'
            for text in ambiguous:
                path.write_text(text,encoding='utf-8')
                proc=subprocess.run([sys.executable,str(root/'scripts/time_series_toolkit.py'),str(path),
                                     '--output',str(output)],capture_output=True,text=True)
                self.assertNotEqual(proc.returncode,0)
                self.assertIn('DUPLICATE_JSON_KEY',proc.stderr)
                self.assertFalse(output.exists())
                self.assertEqual(path.read_text(encoding='utf-8'),text)


if __name__=='__main__':unittest.main()
