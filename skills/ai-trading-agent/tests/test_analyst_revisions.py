import copy
from decimal import Decimal
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import analyst_revisions as revisions
import source_coverage as coverage
from source_claims import Corpus
import supplied_research as store


class AnalystRevisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='metric-revisions-'); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.sources = self.root / 'sources'; self.sources.mkdir()
        self.target = {'issuer':'SYN','firm_id':'Oak','analyst_id':'Researcher','issued_at':'2031-01-02T10:00:00Z',
            'currency':'EUR','target':45,'price_basis':'common_share','target_horizon':'forward_12_months'}
        self.old = {'firm_id':'Oak','issued_at':'2031-01-02T10:00:00Z','rating':'hold','currency':'EUR','target':45,
            'eps':1.50,'revenue':80,'unit_revenue':'EUR','fiscal_period':'FY2032','eps_basis':'GAAP diluted'}
        self.new = {**self.old,'issued_at':'2031-02-03T10:00:00Z','rating':'buy','target':48,'eps':1.65,'revenue':84}
        self.initiation = {**self.new,'firm_id':'Birch','issued_at':'2031-03-04T10:00:00Z','event_type':'initiation',
            'target':79,'fiscal_period':'FY2033','eps_basis':'adjusted diluted','eps':2.20,'revenue':95}
        self.doc_targets = {'as_of':'2031-04-01T10:00:00Z','individual_targets':[copy.deepcopy(self.target),
            {**self.target,'issued_at':self.new['issued_at'],'target':48},
            {**self.target,'firm_id':'Birch','issued_at':'2031-01-07T10:00:00Z','target':75}]}
        self.doc_events = {'events':[self.old,self.new,self.initiation]}
        self.raw_bodies = {
            'old.txt':b'Oak: rating hold; target EUR 45; FY2032 GAAP diluted EPS EUR 1.50; revenue EUR 80.\n',
            'new.txt':b'Oak: rating buy; target EUR 48; FY2032 GAAP diluted EPS EUR 1.65; revenue EUR 84.\n',
            'init.txt':b'Birch initiated new coverage: FY2033 adjusted diluted EPS EUR 2.20; revenue EUR 95; target EUR 79.\n',
        }
        for row,name in zip(self.doc_events['events'],self.raw_bodies):
            row['source']={'path':name,'sha256':store.digest(self.raw_bodies[name]),'verbatim_excerpt':self.raw_bodies[name].decode().strip()}
        self.manifest = self.root/'ingress.json';self.write()

    def write(self):
        rows=[]
        for name,doc in [('targets.json',self.doc_targets),('events.json',self.doc_events)]:
            raw=store.encode(doc);(self.sources/name).write_bytes(raw)
            rows.append({'id':name,'path':name,'format':'json','sha256':store.digest(raw)})
        for name,raw in self.raw_bodies.items():
            (self.sources/name).write_bytes(raw);rows.append({'id':name,'path':name,'format':'text','sha256':store.digest(raw)})
        self.manifest.write_bytes(store.encode({'schema_version':1,'sources':rows}));self.pin=store.digest(self.manifest.read_bytes())

    def result(self):return revisions.analyze(Corpus(self.manifest,self.pin,self.sources))

    def compared(self,metric,after=1,before=0):
        return next(r for r in self.result()['metric_comparisons'] if r['metric']==metric
            and r.get('after_record')=='events.json:/events/'+str(after)
            and r.get('before_record')=='events.json:/events/'+str(before))

    def test_metric_specific_native_deltas_and_original_pointers(self):
        for metric,delta,pct in [('target','3','6.6666666666666666666666666666666666666666666666667'),('eps','0.15','10.0'),('revenue','4','5.00')]:
            row=self.compared(metric);self.assertEqual(Decimal(row['reported_numeric_difference']['delta']),Decimal(delta))
            self.assertEqual(Decimal(row['reported_numeric_difference']['percent_change']),Decimal(pct))
        self.assertEqual(self.compared('rating')['rating_transition']['before'],'hold')
        self.assertEqual(self.compared('rating')['rating_transition']['after'],'buy')
        self.assertFalse(self.compared('target')['verified_genuine_revision'])

    def test_target_dimensions_link_only_from_exact_contemporaneous_target(self):
        row=self.result()['records'][4]
        # Events follow original target rows in the manifest's original order.
        self.assertEqual(row['fields']['target_horizon'],'forward_12_months')
        self.assertNotIn('target_horizon',row['original_fields'])
        self.assertTrue(all(x['match_basis']==['firm_id','issued_at','currency','target'] for x in row['dimension_links']))
        self.assertEqual(self.compared('target')['missing_dimensions'],[])

    def test_eps_basis_and_fiscal_period_do_not_control_target_comparability(self):
        self.new['eps_basis']='adjusted basic';self.new['fiscal_period']='FY2033';self.write()
        self.assertEqual(self.compared('target')['status'],'MATCHED_REPORTED_REVISION')
        self.assertEqual(set(self.compared('eps')['mismatched_dimensions']),{'eps_basis','fiscal_period'})
        self.assertIsNone(self.compared('eps')['reported_numeric_difference'])

    def test_revenue_unknown_accounting_basis_does_not_inherit_eps_basis(self):
        row=self.compared('revenue')
        self.assertEqual(row['revenue_accounting_basis']['status'],'UNKNOWN')
        self.assertEqual(row['status'],'REPORTED_NUMERIC_CHANGE_ACCOUNTING_BASIS_UNVERIFIED')
        self.assertEqual(row['reported_numeric_difference']['delta'],'4')
        self.assertNotIn('eps_basis',row['dimension_requirements'])

    def test_conflicting_known_revenue_basis_blocks_comparison(self):
        self.old['revenue_basis']='reported';self.new['revenue_basis']='constant_currency';self.write()
        row=self.compared('revenue');self.assertEqual(row['status'],'NOT_COMPARABLE_REVENUE_ACCOUNTING_BASIS')
        self.assertIsNone(row['reported_numeric_difference'])

    def test_initiation_and_earlier_same_firm_evidence_remain_conflict(self):
        result=self.result();event=result['event_assessments'][2]
        self.assertEqual(event['coverage_status'],'UNRESOLVED_COVERAGE_CONFLICT')
        row=next(r for r in result['metric_comparisons'] if r['metric']=='target' and r['after_record']=='events.json:/events/2')
        self.assertEqual(row['status'],'CONDITIONAL_RAW_DIFFERENCE_UNRESOLVED_COVERAGE_CONFLICT')
        self.assertIn('target_horizon',row['missing_dimensions']);self.assertNotIn('eps_basis',row['missing_dimensions'])
        self.assertEqual(row['reported_numeric_difference']['delta'],'4')
        self.assertFalse(row['verified_genuine_revision'])

    def test_raw_initiation_not_silently_lost_when_structured_event_type_missing(self):
        del self.initiation['event_type'];self.write()
        self.assertEqual(self.result()['event_assessments'][2]['coverage_status'],'UNRESOLVED_COVERAGE_CONFLICT')

    def test_no_prior_recognized_eps_is_not_no_prior_firm_coverage(self):
        result=self.result();rows=[r for r in result['metric_comparisons'] if r['after_record']=='events.json:/events/2' and r['metric']=='eps']
        self.assertEqual(rows[0]['status'],'NO_EARLIER_RECOGNIZED_METRIC_RECORD');self.assertFalse(rows[0]['source_absence_established'])
        self.assertEqual(result['event_assessments'][2]['coverage_status'],'UNRESOLVED_COVERAGE_CONFLICT')

    def test_structured_rating_without_raw_rating_keeps_origin_gap(self):
        row=next(r for r in self.result()['records'] if r['id']=='events.json:/events/2')
        self.assertEqual(row['fields']['rating'],'buy')
        self.assertEqual(row['field_origins']['rating']['status'],'STRUCTURED_ONLY_RAW_FIELD_UNRESOLVED')

    def test_raw_value_and_currency_conflicts_visible(self):
        self.new['eps']=9.9;self.write()
        self.assertTrue(self.compared('eps')['raw_value_conflict'])
        self.assertEqual(self.compared('eps')['status'],'CONDITIONAL_REPORTED_DIFFERENCE_UNRESOLVED_EVIDENCE')
        self.new['currency']='USD';self.write()
        row=next(r for r in self.result()['records'] if r['id']=='events.json:/events/1')
        self.assertEqual(row['field_origins']['target']['status'],'STRUCTURED_RAW_CURRENCY_CONFLICT')

    def test_target_horizon_share_basis_currency_each_independent(self):
        for field,value in [('target_horizon','forward_52_weeks'),('price_basis','different_share'),('currency','USD')]:
            with self.subTest(field=field):
                target=self.doc_targets['individual_targets'][1];old=target[field];target[field]=value;self.write()
                row=self.compared('target')
                if field=='currency':self.assertIn('target_horizon',row['missing_dimensions'])
                else:self.assertIn(field,row['mismatched_dimensions']);self.assertIsNone(row['reported_numeric_difference'])
                target[field]=old

    def test_ambiguous_target_link_not_selected_by_order(self):
        self.doc_targets['individual_targets'].append({**self.doc_targets['individual_targets'][1],'issuer':'OTHER'});self.write()
        row=self.compared('target');self.assertTrue(row['dimension_link_conflict']);self.assertIn('issuer',row['missing_dimensions'])

    def test_raw_reference_hash_and_complete_corpus_pin_enforced(self):
        self.new['source']['sha256']='0'*64;self.write()
        with self.assertRaisesRegex(ValueError,'REVISION_RAW_REFERENCE_HASH_MISMATCH'):self.result()

    def test_raw_reference_must_be_unique_within_complete_corpus(self):
        self.new['source']['path']='missing.txt';self.write()
        with self.assertRaisesRegex(ValueError,'REVISION_RAW_REFERENCE_MISSING_OR_AMBIGUOUS'):self.result()

    def test_unknown_raw_reference_does_not_get_invented(self):
        del self.new['source'];self.write()
        row=next(r for r in self.result()['records'] if r['id']=='events.json:/events/1')
        self.assertEqual(row['field_origins']['eps']['status'],'STRUCTURED_ONLY_RAW_UNAVAILABLE')

    def test_future_events_retained_but_not_compared(self):
        self.new['issued_at']='2032-02-03T10:00:00Z';self.write();result=self.result()
        self.assertFalse(any(r['after_record']=='events.json:/events/1' for r in result['metric_comparisons']))
        self.assertEqual(next(r for r in result['records'] if r['id']=='events.json:/events/1')['clock_status'],'AFTER_ORIGINAL_CUTOFF')

    def test_boolean_nonfinite_and_unbounded_numeric_values_rejected(self):
        for value in (True,float('inf'),Decimal('NaN'),Decimal('1e101')):
            with self.subTest(value=value),self.assertRaises(ValueError):revisions.number(value)

    def test_zero_base_undefined_and_negative_base_formula_explicit(self):
        self.assertIsNone(revisions.difference(0,2)['percent_change'])
        self.assertEqual(revisions.difference(-2,-1)['percent_change'],'-50.0')

    def test_large_exact_delta_is_not_rounded_to_fifty_digits(self):
        before=Decimal(1);after=Decimal('1e100')
        self.assertEqual(revisions.difference(before,after)['delta'],'9'*100)

    def test_raw_numeric_tokens_do_not_match_shorter_prefixes(self):
        for raw in ('Target EUR 19,250.','Target EUR 1.25e3.','Target EUR 19.25million.','Target EUR 19.25.5.'):
            with self.subTest(raw=raw):
                result=revisions.raw_metric_origin('target',19,{'text':raw,'source_id':'raw'},'EUR')
                self.assertEqual(result['status'],'STRUCTURED_ONLY_RAW_FIELD_UNRESOLVED');self.assertIsNone(result['raw_value'])
        result=revisions.raw_metric_origin('target',Decimal('19.25'),{'text':'Target EUR 19.25.','source_id':'raw'},'EUR')
        self.assertEqual(result['status'],'LITERAL_RAW_VALUE_MATCH')
        for raw in ('Target now 19.25','Target NOW 19.25','Target was 19.25'):
            result=revisions.raw_metric_origin('target',Decimal('19.25'),{'text':raw,'source_id':'raw'},'EUR')
            self.assertEqual(result['status'],'STRUCTURED_ONLY_RAW_FIELD_UNRESOLVED')

    def test_target_horizon_ambiguity_does_not_contaminate_other_metrics(self):
        self.doc_targets['individual_targets'].append({**self.doc_targets['individual_targets'][1],'target_horizon':'forward_52_weeks'});self.write()
        self.assertTrue(self.compared('target')['dimension_link_conflict'])
        self.assertEqual(self.compared('eps')['status'],'MATCHED_REPORTED_REVISION')
        self.assertEqual(self.compared('rating')['status'],'MATCHED_REPORTED_REVISION')
        self.assertEqual(self.compared('revenue')['status'],'REPORTED_NUMERIC_CHANGE_ACCOUNTING_BASIS_UNVERIFIED')

    def test_no_cross_firm_or_same_time_revision_pair(self):
        self.new['firm_id']='Other';self.new['issued_at']=self.old['issued_at'];self.write()
        self.assertTrue(all(r.get('before_record')!='events.json:/events/0' for r in self.result()['metric_comparisons'] if r['after_record']=='events.json:/events/1'))

    def test_complete_pair_native_analysis_is_replayed_not_authored_annex(self):
        request=b'Review rating changes, target changes and estimate revisions.\n';(self.sources/'request.txt').write_bytes(request)
        scope={'schema_version':1,'original_request':{'path':'request.txt','sha256':store.digest(request)},'manifest_sha256':self.pin,
               'analysis_profile':'ANALYST_REVISIONS','units':[{'id':'whole','start_byte':0,'end_byte':len(request),'sha256':store.digest(request)}]}
        scope_path=self.root/'scope.json';scope_path.write_bytes(store.encode(scope));scope_pin=store.digest(scope_path.read_bytes())
        ids=[r['id'] for r in json.loads(self.manifest.read_bytes())['sources']]
        plan={'schema_version':1,'units':[{'unit_id':'whole','source_ids':ids,'discovery_routes':[]}],
              'sources':[{'source_id':sid,'access':'UNCLASSIFIED','lineage':[]} for sid in ids]}
        plan_path=self.root/'plan.json';plan_path.write_bytes(store.encode(plan));output=self.root/'coverage'
        coverage.compose(plan_path,scope_path,scope_pin,self.manifest,self.pin,self.sources,output)
        result=json.loads((output/'response.json').read_bytes())
        self.assertEqual(result['native_analysis']['method'],revisions.METHOD)
        self.assertIn(b'UNRESOLVED_COVERAGE_CONFLICT',(output/'first-response.md').read_bytes())
        coverage.verify(output,scope_pin,self.pin,output/'first-response.md',output/'response.json')
        result['native_analysis']['event_assessments'][2]['coverage_status']='CLEAN_INITIATION';(output/'response.json').write_bytes(store.encode(result))
        receipt=json.loads((output/'receipt.json').read_bytes());receipt['artifacts']=store.file_inventory(output);(output/'receipt.json').write_bytes(store.encode(receipt))
        with self.assertRaisesRegex(ValueError,'COVERAGE_REPLAY_MISMATCH'):coverage.verify(output,scope_pin,self.pin)


if __name__=='__main__':unittest.main()
