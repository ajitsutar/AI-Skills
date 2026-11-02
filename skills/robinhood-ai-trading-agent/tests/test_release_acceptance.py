import copy,hashlib,json,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import release_acceptance as r
import dependency_inventory as d

def rights():
 return {'schema_version':1,'as_of':'2026-11-01T00:00:00Z','intended_use':'redistribution','sources':[{'id':'fictional','provider':'fixture','artifact_kind':'market_data','source_url':'fictional://data','terms_url':'fictional://terms','terms_sha256':'a'*64,'terms_observed_at':'2026-10-01T00:00:00Z','valid_until':'2026-12-01T00:00:00Z','permitted_uses':['personal_research'],'review_status':'permitted','reviewer':'fictional-reviewer','attribution':'fictional','retention_days':30,'evidence_ref':'fixture-only'}]}

class AcceptanceTests(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
 def tearDown(self):self.temp.cleanup()
 def test_personal_permission_is_not_redistribution(self):
  out=r.rights_inventory(rights());self.assertFalse(out['inventory_complete']);self.assertIn('INTENDED_USE_NOT_LISTED',out['sources'][0]['reasons']);self.assertFalse(out['rights_granted'])
 def test_expired_future_and_unknown_terms(self):
  x=rights();x['intended_use']='personal_research';x['sources'][0]['valid_until']='2026-10-31T00:00:00Z';self.assertIn('REVIEW_EXPIRED',r.rights_inventory(x)['sources'][0]['reasons'])
  x['sources'][0]['terms_observed_at']='2026-12-01T00:00:00Z';self.assertIn('FUTURE_TERMS_OBSERVATION',r.rights_inventory(x)['sources'][0]['reasons'])
 def test_declared_current_terms_do_not_authenticate(self):
  x=rights();x['intended_use']='personal_research';out=r.rights_inventory(x);self.assertTrue(out['inventory_complete']);self.assertFalse(out['source_evidence_authenticated'])
 def test_offline_fixture_runs_actual_helper(self):
  x={'schema_version':1,'fixtures':[{'id':'empty-overlap','operation':'experiment.overlap_review','inputs':{'attempts':[]},'expect':{'/registered_attempt_count':0,'/search_completeness_established':False},'absolute_tolerance':0,'relative_tolerance':0}]}
  result=r.run_fixtures(x,self.root/'run');self.assertEqual(result['status'],'OFFLINE_FIXTURES_PASSED');self.assertTrue((self.root/'run/result.json').exists());self.assertFalse(result['predictive_skill_established'])
  x['fixtures'][0]['expect']['/registered_attempt_count']=1;self.assertEqual(r.run_fixtures(x,self.root/'bad')['status'],'OFFLINE_FIXTURES_FAILED')
 def test_no_arbitrary_operation(self):
  x={'schema_version':1,'fixtures':[{'id':'bad','operation':'os.system','inputs':{},'expect':{'':0},'absolute_tolerance':0,'relative_tolerance':0}]}
  self.assertRaisesRegex(ValueError,'NOT_ALLOWLISTED',r.run_fixtures,x,self.root/'bad')
 def test_comparison_requires_actual_files_and_preserves_unrun(self):
  response=self.root/'answer.txt';response.write_bytes(b'fictional response');sha=hashlib.sha256(response.read_bytes()).hexdigest()
  x={'schema_version':1,'expected_hosts':['codex','muse','claude'],'prompt_sha256':'a'*64,'input_bundle_sha256':'b'*64,'captures':[{'host':'codex','model':'fictional','model_version':'fixture','observed_at':'2026-11-01T00:00:00Z','prompt_sha256':'a'*64,'input_bundle_sha256':'b'*64,'response_path':'answer.txt','response_sha256':sha,'checks':[{'id':i,'outcome':'pass','reviewer':'fixture','evidence_ref':'fictional'} for i in sorted(r.HOST_CHECKS)],'independence_limits':['fictional fixture only']}]}
  out=r.compare_host_responses(x,self.root);self.assertEqual([h['status'] for h in out['hosts']],['RETAINED_RESPONSE_REVIEW_PASSED','NOT_RUN','NOT_RUN']);self.assertFalse(out['all_hosts_reviewed']);response.write_bytes(b'changed');self.assertEqual(r.compare_host_responses(x,self.root)['hosts'][0]['status'],'INCOMPLETE_OR_FAILED')
 def test_response_path_cannot_escape_root(self):
  x={'schema_version':1,'expected_hosts':['x'],'prompt_sha256':'a'*64,'input_bundle_sha256':'b'*64,'captures':[{'host':'x','model':'fixture','model_version':'fixture','observed_at':'2026-11-01T00:00:00Z','prompt_sha256':'a'*64,'input_bundle_sha256':'b'*64,'response_path':'../outside.txt','response_sha256':'c'*64,'checks':[],'independence_limits':[]}]}
  self.assertRaisesRegex(ValueError,'OUTSIDE_EVIDENCE',r.compare_host_responses,x,self.root)
 def test_boolean_not_equal_to_numeric(self):self.assertFalse(r.equal(False,0,0,0))
 def test_host_response_grade_rejects_duplicate_and_nonfinite(self):
  x={'response_text':'{"amount":1,"amount":2}','expected':{'amount':2},'absolute_tolerance':0,'relative_tolerance':0}
  self.assertEqual(r.grade_response(x)['status'],'UNGRADABLE_RESPONSE');x['response_text']='{"amount": NaN}';self.assertEqual(r.grade_response(x)['status'],'UNGRADABLE_RESPONSE')
 def test_host_response_grade_preserves_mismatch(self):
  x={'response_text':'{"amount":104,"traded":false}','expected':{'amount':104,'traded':False},'absolute_tolerance':0,'relative_tolerance':0}
  self.assertEqual(r.grade_response(x)['status'],'FIXTURE_MATCH');x['response_text']='{"amount":104,"traded":true}';self.assertEqual(r.grade_response(x)['status'],'FIXTURE_MISMATCH')
 def test_wheel_hash_requires_actual_bytes(self):
  file=self.root/'fixture.whl';file.write_bytes(b'fictional-not-a-wheel');a={'filename':file.name,'bytes':file.stat().st_size,'sha256':hashlib.sha256(file.read_bytes()).hexdigest()};inv={'packages':[{'name':'fixture','artifacts':[a]}],'resolution_errors':[]}
  self.assertFalse(d.verify_artifacts(inv,self.root)['install_test_performed']);file.write_bytes(b'tampered');self.assertRaisesRegex(ValueError,'HASH_MISMATCH',d.verify_artifacts,inv,self.root)
 def test_missing_artifact_not_an_installed_tree_hash(self):self.assertRaisesRegex(ValueError,'MISSING_DISTRIBUTION',d.verify_artifacts,{'packages':[{'name':'x','artifacts':[]}],'resolution_errors':[]},self.root)
 def test_dependency_closure_and_actual_artifact_lock(self):
  req=self.root/'requirements.txt';req.write_text('fixture-root==1.0\n');art=self.root/'artifacts';art.mkdir()
  fake={'fixture-root':SimpleNamespace(version='1.0',requires=['fixture-child>=2; python_version >= "3.0"'],metadata={}), 'fixture-child':SimpleNamespace(version='2.0',requires=[],metadata={})}
  with patch.object(d.metadata,'distribution',side_effect=lambda name:fake[name]):
   first=d.capture(req,self.root/'observed');self.assertEqual(len(first['packages']),2);self.assertFalse(first['artifact_hash_coverage_complete']);self.assertFalse((self.root/'observed/requirements.lock.txt').exists())
   for name in ['fixture_root-1.0-py3-none-any.whl','fixture_child-2.0-py3-none-any.whl']:(art/name).write_bytes(b'fictional artifact bytes; never installed')
   second=d.capture(req,self.root/'locked',art);self.assertTrue(second['artifact_hash_coverage_complete']);self.assertIn('--hash=sha256:',(self.root/'locked/requirements.lock.txt').read_text());self.assertEqual(len(d.verify_artifacts(second,art)['artifacts']),2)
 def test_dependency_version_conflict_cannot_emit_lock(self):
  req=self.root/'requirements.txt';req.write_text('fixture-root==9.0\n');art=self.root/'artifacts';art.mkdir();(art/'fixture_root-1.0-py3-none-any.whl').write_bytes(b'fictional')
  with patch.object(d.metadata,'distribution',return_value=SimpleNamespace(version='1.0',requires=[],metadata={})):
   result=d.capture(req,self.root/'conflict',art);self.assertFalse(result['artifact_hash_coverage_complete']);self.assertEqual(result['resolution_errors'][0]['reason'],'INSTALLED_VERSION_CONFLICT');self.assertFalse((self.root/'conflict/requirements.lock.txt').exists())

if __name__=='__main__':unittest.main()
