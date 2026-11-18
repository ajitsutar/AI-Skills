"""Generic benchmark identities and a genuinely standard-library-only CLI."""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0, str(SCRIPTS))
import volatility_baselines as baselines


def fixture():
    times = [(datetime(2024, 1, 1, tzinfo=timezone.utc)+timedelta(days=i)).isoformat() for i in range(55)]
    raw = ('timestamp,close\n'+'\n'.join(f'{t},{100+0.2*i+math.sin(i)*.3:.9f}' for i,t in enumerate(times))+'\n').encode()
    audit = {'schema_version':1, 'csv_sha256':hashlib.sha256(raw).hexdigest(),
        'close_column':'close', 'timestamp_column':'timestamp', 'periods_per_year':252.,
        'symbol':'SYNTHETIC_BENCHMARK', 'provider':'generic test', 'provider_field':'close',
        'bar_interval':'1d', 'adjustment_notes':'generic synthetic test', 'retrieved_at':times[-1],
        'data_kind':'fictional', 'price_basis':'split_adjusted',
        'corporate_actions':{'status':'reviewed','evidence':['synthetic'],'window_start':times[0],
            'window_end':times[-1],'events':[]},
        'session_review':{'status':'reviewed','evidence':['synthetic'],'window_start':times[0],
            'window_end':times[-1],'calendar':'fictional calendar'},'large_move_reviews':[]}
    return raw, audit


class PortableBaselines(unittest.TestCase):
    def test_hand_calculated_training_warmup(self):
        # sample variance([1,2,3])=1; training states1,2.5,5.75.
        self.assertEqual(baselines.ewma_predictions([1,2,3,4,5],3,2,.5,1),[5.75,10.875])
        output=baselines.baseline_comparison([1,2,3,4,5],3,2,.5)
        self.assertEqual(output['ewma_predicted_variance_percent_squared'],[5.75,10.875])
        self.assertNotEqual(output['ewma_predicted_variance_percent_squared'][0],1)
        self.assertEqual(output['ewma_training_warmup_returns'],3)

    def test_target_changes_only_later_forecast(self):
        before=baselines.ewma_predictions([1,2,3,4,5],3,2,.5,1)
        after=baselines.ewma_predictions([1,2,3,8,5],3,2,.5,1)
        self.assertEqual(before[0],after[0]);self.assertNotEqual(before[1],after[1])
        self.assertEqual(before,baselines.ewma_predictions([1,2,3,4,5,float('nan')],3,2,.5,1))

    def test_zero_realized_return_floor(self):
        self.assertAlmostEqual(baselines.variance_loss([0],[2]),5e-13-1-math.log(5e-13))
        self.assertEqual(baselines.variance_loss([2],[2]),0)

    def test_invalid_loss_inputs_rejected(self):
        for x,p in [([],[]),([1],[]),([-1],[1]),([1],[0]),([float('nan')],[1]),([1],[float('inf')])]:
            with self.subTest(x=x,p=p),self.assertRaises(ValueError):baselines.variance_loss(x,p)

    def test_invalid_recursion_inputs_rejected(self):
        for kwargs in [{'train':True},{'train':2},{'train':3.5},{'test':0},
                       {'decay':0},{'decay':1},{'decay':float('nan')},{'initial_variance':0},
                       {'initial_variance':float('inf')},{'observations':[1,2,float('nan'),4,5]},
                       {'observations':[1,2,3,4]},{'observations':[1e308]*5}]:
            args=dict(observations=[1,2,3,4,5],train=3,test=2,decay=.5,initial_variance=1);args.update(kwargs)
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):baselines.ewma_predictions(**args)

    def test_zero_variance_floors_remain_explicit(self):
        result=baselines.baseline_comparison([0]*6,3,3)
        self.assertEqual(result['initial_variance_percent_squared'],1e-8)
        self.assertTrue(all(x>0 for x in result['ewma_predicted_variance_percent_squared']))

    def test_audited_csv_metadata_and_ineligibility(self):
        raw,audit=fixture();result=baselines.from_csv(raw,audit,min_observations=30,validation_test=10)
        self.assertEqual((result['price_count'],result['return_count'],result['training_returns']),(55,54,44))
        self.assertEqual(result['csv_sha256'],audit['csv_sha256'])
        self.assertEqual(result['data_quality']['status'],'FICTIONAL')
        self.assertFalse(result['data_quality']['eligible_for_sizing'])
        self.assertFalse(result['garch_fit_performed']);self.assertIsNone(result['garch_qlike'])
        self.assertIsNone(result['garch_forecast_variance']);self.assertIsNone(result['native_adapter_sizing_eligibility'])
        self.assertEqual(result['forecast_horizon_observations'],1)
        self.assertEqual(result['variance_units'],'percent_log_return_squared_per_observation')
        self.assertEqual(len(result['ewma_predicted_variance_percent_squared']),10)

    def test_unverified_audit_cannot_become_sizing_permission(self):
        raw,_=fixture();out=baselines.from_csv(raw,min_observations=30,validation_test=10)
        self.assertEqual(out['data_quality']['status'],'UNVERIFIED')
        self.assertFalse(out['data_quality']['eligible_for_sizing']);self.assertFalse(out['execution_authorized'])

    def test_changed_audit_hash_and_scale_rejected(self):
        raw,audit=fixture()
        for key,value in [('csv_sha256','0'*64),('periods_per_year',12),('close_column','adjusted_close')]:
            changed=copy.deepcopy(audit);changed[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):baselines.from_csv(raw,changed,min_observations=30,validation_test=10)

    def test_bad_csv_and_counts_rejected(self):
        raw,_=fixture();lines=raw.decode().splitlines()
        for price in ['0','-1','NaN','inf']:
            altered=lines.copy();altered[1]=altered[1].split(',')[0]+','+price
            with self.subTest(price=price),self.assertRaises(ValueError):baselines.from_csv(('\n'.join(altered)+'\n').encode(),min_observations=30,validation_test=10)
        altered=lines.copy();altered[2]=altered[1]
        with self.assertRaises(ValueError):baselines.from_csv(('\n'.join(altered)+'\n').encode(),min_observations=30,validation_test=10)
        with self.assertRaises(ValueError):baselines.from_csv(raw,min_observations=50,validation_test=10)
        with self.assertRaises(ValueError):baselines.from_csv(raw,min_observations=30,validation_test=10,periods_per_year=0)

    def test_cli_with_site_packages_disabled_and_optional_imports_blocked(self):
        raw,audit=fixture()
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve()
            (root/'prices.csv').write_bytes(raw);(root/'audit.json').write_text(json.dumps(audit),encoding='utf-8')
            program = '''import sys,runpy,importlib.abc
class DenyOptional(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname.split('.')[0] in {'arch','numpy','pandas','scipy','statsmodels'}: raise ImportError('Optional imports forbidden')
sys.meta_path.insert(0,DenyOptional())
sys.path.insert(0,sys.argv.pop(1))
sys.argv=sys.argv[1:]
runpy.run_path(sys.argv[0],run_name='__main__')
'''
            process=subprocess.run([sys.executable,'-I','-S','-B','-c',program,str(SCRIPTS),str(SCRIPTS/'volatility_baselines.py'),str(root/'prices.csv'),
                '--data-audit',str(root/'audit.json'),'--min-observations','30','--validation-test','10'],capture_output=True,text=True,cwd=root)
            self.assertEqual(process.returncode,0,process.stderr)
            out=json.loads(process.stdout)
            self.assertEqual(out['status'],'BASELINES_ONLY_NO_GARCH_FIT')
            self.assertEqual(out['audit_sha256'],hashlib.sha256((root/'audit.json').read_bytes()).hexdigest())
            self.assertEqual((root/'prices.csv').read_bytes(),raw)


if __name__=='__main__':unittest.main()
