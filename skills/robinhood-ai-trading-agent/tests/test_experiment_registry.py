import copy,hashlib,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import experiment_registry as e

def contract(prompt=b'Frozen fictional question'):
 return {'schema_version':2,'attempt_id':'trial-1','campaign_id':'fictional','parent_attempt_id':None,'revision_reason':None,'model':{'host':'fixture','name':'none','version':'none','settings':{}},'prompt_sha256':hashlib.sha256(prompt).hexdigest(),'package_sha256':'a'*64,'runtime_sha256':'b'*64,'data_vintages':[{'id':'fixture-data','sha256':'c'*64,'available_at':'2025-01-01T00:00:00Z'}],'universe_sha256':'d'*64,'constraints':{'max_weight':.2},'selection':{'rule':'fictional'},'conventions':{'accounting':'Marked to market USD','benchmark':'Fictional total-return benchmark','cash':'Zero interest','dividends':'Reinvested','costs':'Zero fictional costs'},'train_start':'2024-01-01T00:00:00Z','train_end':'2024-12-31T00:00:00Z','evaluation_start':'2025-01-02T00:00:00Z','evaluation_end':'2025-12-31T00:00:00Z','label_end':'2026-01-02T00:00:00Z','embargo_seconds':86400,'purpose':'development'}

class RegistryTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.r=e.Registry(self.root);self.prompt=self.root/'prompt.txt';self.prompt.write_bytes(b'Frozen fictional question');self.out=self.root/'result.txt';self.out.write_bytes(b'actual failed invocation bytes')
 def tearDown(self):self.temp.cleanup()
 def test_failed_and_abandoned_attempts_count(self):
  a=contract();self.r.register(a,self.prompt);self.r.record_result(a['attempt_id'],'failed',self.out)
  b=copy.deepcopy(a);b.update(attempt_id='trial-2',parent_attempt_id='trial-1',revision_reason='Constraint changed');b['constraints']={'max_weight':.1}
  self.r.register(b,self.prompt);self.r.record_result('trial-2','abandoned',self.out)
  result=self.r.audit();self.assertEqual(result['registered_attempts'],2);self.assertEqual(result['outcomes'],{'trial-1':'failed','trial-2':'abandoned'});self.assertTrue(result['overlap']['warnings']);self.assertFalse(result['overlap']['search_completeness_established'])
 def test_prompt_byte_mismatch(self):
  self.prompt.write_bytes(b'different');self.assertRaisesRegex(ValueError,'PROMPT_BYTES',self.r.register,contract(),self.prompt);self.assertEqual(self.r.read(),[])
 def test_original_result_preserved_after_source_change(self):
  self.r.register(contract(),self.prompt);row=self.r.record_result('trial-1','complete',self.out,self.out,self.out);self.out.write_bytes(b'changed external file');self.assertEqual(self.r.audit()['events'],2);blob=self.root/'blobs'/row['payload']['artifacts'][0]['sha256'];self.assertEqual(blob.read_bytes(),b'actual failed invocation bytes')
 def test_blob_tampering_detected(self):
  row=self.r.register(contract(),self.prompt);(self.root/'blobs'/row['payload']['artifacts'][0]['sha256']).write_bytes(b'x');self.assertRaisesRegex(ValueError,'ARTIFACT_HASH',self.r.audit)
 def test_chain_tampering_detected(self):
  self.r.register(contract(),self.prompt);rows=json.loads(self.r.events.read_text());rows[0]['payload']['contract']['constraints']={};self.r.events.write_text(json.dumps(rows));self.assertRaisesRegex(ValueError,'CHAIN_HASH',self.r.audit)
 def test_no_overwrite_terminal_result(self):
  self.r.register(contract(),self.prompt);self.r.record_result('trial-1','failed',self.out);self.assertRaisesRegex(ValueError,'RESULT_ALREADY',self.r.record_result,'trial-1','complete',self.out)
 def test_existing_writer_lock_is_not_stolen(self):
  (self.root/'.writer-lock').mkdir();self.assertRaisesRegex(ValueError,'WRITER_LOCKED',self.r.register,contract(),self.prompt)
 def test_unknown_parent_and_embargo(self):
  x=contract();x.update(parent_attempt_id='missing',revision_reason='revision');self.assertRaisesRegex(ValueError,'PARENT_NOT',self.r.register,x,self.prompt)
  x=contract();x['embargo_seconds']=999999;self.assertRaisesRegex(ValueError,'EMBARGO',e.validate_attempt,x)
 def test_cross_trial_training_contamination(self):
  x=contract();y=copy.deepcopy(x);y['attempt_id']='second';y['train_end']='2025-06-01T00:00:00Z';y['evaluation_start']='2025-06-03T00:00:00Z'
  result=e.overlap_review({'attempts':[x,y]});self.assertIn('TRAINING_OVERLAPS_OTHER_EVALUATION_LABELS',{r['kind'] for r in result['warnings']})
 def test_forward_capture_is_timestamped_before_target(self):
  x=contract();x.update(purpose='forward_paper',evaluation_start='2030-01-02T00:00:00Z',evaluation_end='2030-02-01T00:00:00Z',label_end='2030-02-01T00:00:00Z')
  with patch.object(e,'utcnow',return_value='2030-01-01T00:00:00+00:00'):self.r.register(x,self.prompt)
  with patch.object(e,'utcnow',return_value='2030-01-03T00:00:00+00:00'):
   self.r.capture_forward('trial-1','2030-01-02T00:00:00Z','2030-01-04T00:00:00Z',self.out)
   self.assertRaisesRegex(ValueError,'DUPLICATE',self.r.capture_forward,'trial-1','2030-01-02T00:00:00Z','2030-01-04T00:00:00Z',self.out)
   self.assertRaisesRegex(ValueError,'NOT_BEFORE_TARGET',self.r.capture_forward,'trial-1','2030-01-02T12:00:00Z','2030-01-03T00:00:00Z',self.out)
 def test_forward_registration_after_start_rejected(self):
  x=contract();x['purpose']='forward_paper'
  with patch.object(e,'utcnow',return_value='2026-01-01T00:00:00+00:00'):self.assertRaisesRegex(ValueError,'REGISTRATION_TOO_LATE',self.r.register,x,self.prompt)
 def test_late_holdout_registration_never_untouched(self):
  x=contract();x['purpose']='holdout'
  with patch.object(e,'utcnow',return_value='2026-01-01T00:00:00+00:00'):self.r.register(x,self.prompt)
  out=self.r.audit()['holdout_assessments'][0];self.assertEqual(out['status'],'LATE_REGISTERED_NOT_UNTOUCHED_HOLDOUT');self.assertFalse(out['globally_untouched_holdout_established'])
 def test_timely_holdout_remains_only_local_and_overlap_is_reported(self):
  x=contract();x['purpose']='holdout'
  with patch.object(e,'utcnow',return_value='2025-01-01T00:00:00+00:00'):self.r.register(x,self.prompt)
  self.assertEqual(self.r.audit()['holdout_assessments'][0]['status'],'LOCALLY_PROSPECTIVE_CONTRACT_ONLY')
  y=copy.deepcopy(x);y['attempt_id']='trial-2'
  with patch.object(e,'utcnow',return_value='2025-01-01T01:00:00+00:00'):self.r.register(y,self.prompt)
  self.assertTrue(all(a['status']=='REGISTERED_OVERLAP_NOT_UNTOUCHED_HOLDOUT' for a in self.r.audit()['holdout_assessments']))
 def test_future_vintage_flagged_without_hiding_original_contract(self):
  x=contract();x['purpose']='holdout';x['data_vintages'][0]['available_at']='2025-06-01T00:00:00Z'
  self.assertEqual(e.validate_attempt(x)['preselection_vintages_available_after_evaluation_start'],['fixture-data'])
  with patch.object(e,'utcnow',return_value='2025-01-01T00:00:00+00:00'):self.r.register(x,self.prompt)
  self.assertEqual(self.r.audit()['holdout_assessments'][0]['status'],'FUTURE_PRESELECTION_INPUTS_NOT_UNTOUCHED_HOLDOUT')

 def test_complete_requires_actual_accounting_and_benchmark_bytes(self):
  self.r.register(contract(),self.prompt)
  self.assertRaisesRegex(ValueError,'COMPLETED_ACCOUNTING',self.r.record_result,'trial-1','complete',self.out)
  missing=self.root/'missing.csv'
  self.assertRaisesRegex(ValueError,'ARTIFACT_FILE',self.r.record_result,'trial-1','complete',self.out,missing,self.out)
  accounting=self.root/'accounting.csv';accounting.write_bytes(b'nav,100')
  benchmark=self.root/'benchmark.csv';benchmark.write_bytes(b'index,101')
  event=self.r.record_result('trial-1','complete',self.out,accounting,benchmark)
  self.assertEqual([a['role'] for a in event['payload']['artifacts']],['result_or_error','accounting','benchmark'])
  accounting.write_bytes(b'revised');benchmark.unlink();self.r.audit()
  artifact=event['payload']['artifacts'][1]
  self.assertEqual((self.root/'blobs'/artifact['sha256']).read_bytes(),b'nav,100')
  (self.root/'blobs'/artifact['sha256']).write_bytes(b'tampered');self.assertRaisesRegex(ValueError,'ARTIFACT_HASH',self.r.audit)
 def test_conventions_are_explicit_and_revision_requires_new_attempt(self):
  x=contract();del x['conventions']['costs'];self.assertRaisesRegex(ValueError,'CONVENTIONS_REQUIRED',e.validate_attempt,x)
  x=contract();x['conventions']['cash']='';self.assertRaisesRegex(ValueError,'EXPLICIT_CONVENTION',e.validate_attempt,x)
  x=contract();self.r.register(x,self.prompt);x['conventions']['costs']='10 bps'
  self.assertRaisesRegex(ValueError,'ALREADY_REGISTERED',self.r.register,x,self.prompt)

if __name__=='__main__':unittest.main()
