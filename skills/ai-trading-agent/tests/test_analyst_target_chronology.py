import copy,json,unittest
from decimal import Decimal
import test_analyst_revisions as fixture
from source_claims import Corpus
import analyst_revisions as revisions
import source_coverage as coverage
import supplied_research as store


class TargetChronologyTests(unittest.TestCase):
 write=fixture.AnalystRevisionTests.write
 def setUp(self):
  fixture.AnalystRevisionTests.setUp(self)
  self.first={**self.target,'target':61,'target_horizon':'forward_6_months'}
  self.second={**self.first,'issued_at':'2031-03-03T10:00:00Z','target':67}
  self.doc_targets['individual_targets']=[self.first,self.second];self.doc_events['events']=[];self.write()
 def result(self):return revisions.analyze(Corpus(self.manifest,self.pin,self.sources))
 def coverage(self):return self.result()['target_record_coverage']
 def comparison(self):return self.coverage()['comparisons'][0]
 def test_target_only_records_receive_chronological_dispositions(self):
  result=self.result();self.assertEqual(result['event_assessments'],[]);self.assertEqual(result['metric_comparisons'],[])
  review=result['target_record_coverage'];self.assertEqual(len(review['record_assessments']),2);self.assertEqual(len(review['comparisons']),1)
  self.assertEqual(review['comparisons'][0]['before_source_ref']['pointer'],'/individual_targets/0')
  self.assertEqual(review['comparisons'][0]['after_source_ref']['pointer'],'/individual_targets/1')
 def test_matching_literal_horizons_allow_reported_change(self):
  row=self.comparison();self.assertEqual(row['status'],'MATCHED_REPORTED_TARGET_CHANGE')
  self.assertEqual(row['reported_numeric_difference']['delta'],'6');self.assertFalse(row['verified_genuine_revision'])
 def test_changed_horizon_not_assumed_equivalent(self):
  self.second['target_horizon']='forward_26_weeks';self.write();row=self.comparison()
  self.assertEqual(row['status'],'NOT_COMPARABLE_METRIC_DIMENSIONS');self.assertIsNone(row['reported_numeric_difference'])
  self.assertEqual(row['target_horizon_disposition'],'LITERAL_HORIZONS_DIFFER_NO_EQUIVALENCE_ASSUMED')
 def test_unknown_horizon_keeps_conditional_difference_and_unknown_status(self):
  self.first.pop('target_horizon');self.write();row=self.comparison()
  self.assertEqual(row['status'],'CONDITIONAL_REPORTED_DIFFERENCE_UNRESOLVED_EVIDENCE')
  self.assertEqual(row['target_horizon_disposition'],'HORIZON_UNKNOWN_NO_EQUIVALENCE_ESTABLISHED');self.assertFalse(row['horizon_equivalence_inferred'])
 def test_case_or_alias_horizon_strings_not_normalized(self):
  self.second['target_horizon']='FORWARD_6_MONTHS';self.write();self.assertIn('target_horizon',self.comparison()['mismatched_dimensions'])
 def test_currency_basis_issuer_and_analyst_conflicts_each_block_clean_comparison(self):
  original=copy.deepcopy(self.second)
  for key in ('currency','price_basis','issuer','analyst_id'):
   with self.subTest(dimension=key):
    self.second.clear();self.second.update(original);self.second[key]='DIFFERENT';self.write();row=self.comparison()
    self.assertIn(key,row['mismatched_dimensions']);self.assertIsNone(row['reported_numeric_difference'])
 def test_missing_analyst_remains_unknown(self):
  self.second.pop('analyst_id');self.write();row=self.comparison()
  self.assertIn('analyst_id',row['missing_dimensions']);self.assertEqual(row['status'],'CONDITIONAL_REPORTED_DIFFERENCE_UNRESOLVED_EVIDENCE')
 def test_different_firms_are_not_joined(self):
  self.second['firm_id']='Other';self.write();self.assertEqual(self.coverage()['comparisons'],[])
 def test_same_time_conflicting_targets_are_not_ordered_or_selected(self):
  self.second['issued_at']=self.first['issued_at'];self.write();review=self.coverage()
  self.assertEqual(review['comparisons'],[])
  self.assertEqual(review['record_assessments'][0]['same_time_observations'][0]['status'],'CONFLICTING_SAME_TIME_REPORTED_TARGET')
 def test_conflicting_prior_same_time_targets_suppress_arithmetic(self):
  self.doc_targets['individual_targets'].insert(1,{**self.first,'target':63});self.write();rows=self.coverage()['comparisons']
  self.assertEqual(len(rows),2);self.assertTrue(all(r['status']=='UNRESOLVED_SAME_TIME_TARGET_CONFLICT' for r in rows))
  self.assertTrue(all(r['reported_numeric_difference'] is None for r in rows))
 def test_exact_duplicate_records_retained_without_independence_claim(self):
  self.doc_targets['individual_targets'].insert(1,copy.deepcopy(self.first));self.write();review=self.coverage()
  self.assertEqual(len(review['comparisons']),2);peer=review['record_assessments'][0]['same_time_observations'][0]
  self.assertEqual(peer['status'],'SAME_LITERAL_TARGET_OBSERVATION');self.assertFalse(peer['independent_observation_verified'])
  self.assertTrue(review['comparison_count_is_not_revision_count'])
 def test_same_time_different_issuer_is_not_duplicate_conflict(self):
  self.doc_targets['individual_targets'].append({**self.first,'issuer':'OTHER','target':900});self.write()
  self.assertEqual(self.coverage()['record_assessments'][0]['same_time_observations'],[])
 def test_target_after_original_cutoff_retained_but_not_compared(self):
  self.second['issued_at']='2032-03-03T10:00:00Z';self.write();review=self.coverage()
  self.assertEqual(review['comparisons'],[]);self.assertEqual(review['record_assessments'][1]['status'],'AFTER_ORIGINAL_CUTOFF_NOT_COMPARED')
 def test_target_record_without_value_receives_explicit_disposition(self):
  self.second.pop('target');self.write();review=self.coverage()
  self.assertEqual(review['comparisons'],[]);self.assertEqual(review['record_assessments'][1]['status'],'NO_TARGET_VALUE_IN_RECORD')
 def test_event_mirror_is_retained_without_revision_count_claim(self):
  self.doc_events['events']=[copy.deepcopy(self.first)];self.write();review=self.coverage()
  self.assertEqual(len(review['comparisons']),2);self.assertTrue(review['comparison_count_is_not_revision_count'])
  self.assertEqual(review['record_assessments'][0]['same_time_observations'][0]['status'],'SAME_LITERAL_TARGET_OBSERVATION')
 def test_same_time_initiation_event_remains_coverage_conflict(self):
  self.doc_events['events']=[{**self.second,'event_type':'initiation'}];self.write()
  self.assertEqual(self.comparison()['status'],'CONDITIONAL_RAW_DIFFERENCE_UNRESOLVED_COVERAGE_CONFLICT')
 def test_every_earlier_candidate_retained_in_chronological_order(self):
  middle={**self.first,'issued_at':'2031-02-01T10:00:00Z','target':64};self.doc_targets['individual_targets']=[self.second,self.first,middle];self.write()
  rows=[r for r in self.coverage()['comparisons'] if r['after_record'].endswith('/0')]
  self.assertEqual([r['before_issued_at'] for r in rows],[self.first['issued_at'],middle['issued_at']])
 def test_actual_pair_contains_known_horizon_disposition_and_rejects_substitution(self):
  self.second['target_horizon']='forward_26_weeks';self.write()
  request=b'Review all dated target changes and source dimensions.\n';(self.sources/'request.txt').write_bytes(request)
  scope={'schema_version':1,'original_request':{'path':'request.txt','sha256':store.digest(request)},'manifest_sha256':self.pin,'analysis_profile':'ANALYST_REVISIONS',
   'units':[{'id':'whole','start_byte':0,'end_byte':len(request),'sha256':store.digest(request)}]}
  sp=self.root/'scope.json';sp.write_bytes(store.encode(scope));spin=store.digest(sp.read_bytes())
  ids=[r['id'] for r in json.loads(self.manifest.read_bytes())['sources']]
  plan={'schema_version':1,'units':[{'unit_id':'whole','source_ids':ids,'discovery_routes':[]}],'sources':[{'source_id':sid,'access':'SUPPLIED_BODY','lineage':[]} for sid in ids]}
  pp=self.root/'plan.json';pp.write_bytes(store.encode(plan));out=self.root/'delivery'
  coverage.compose(pp,sp,spin,self.manifest,self.pin,self.sources,out);coverage.verify(out,spin,self.pin,out/'first-response.md',out/'response.json')
  self.assertIn(b'LITERAL_HORIZONS_DIFFER_NO_EQUIVALENCE_ASSUMED',(out/'first-response.md').read_bytes())
  response=json.loads((out/'response.json').read_bytes());row=response['native_analysis']['target_record_coverage']['comparisons'][0]
  self.assertIsNone(row['reported_numeric_difference']);row['target_horizon_disposition']='LITERAL_REPORTED_HORIZONS_MATCH'
  (out/'response.json').write_bytes(store.encode(response));receipt=json.loads((out/'receipt.json').read_bytes());receipt['artifacts']=store.file_inventory(out);(out/'receipt.json').write_bytes(store.encode(receipt))
  with self.assertRaisesRegex(ValueError,'COVERAGE_REPLAY_MISMATCH'):coverage.verify(out,spin,self.pin)


if __name__=='__main__':unittest.main()
