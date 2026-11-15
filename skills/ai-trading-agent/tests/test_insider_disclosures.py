from decimal import Decimal,localcontext
import json
from pathlib import Path
import sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import insider_disclosures as insider
import source_coverage as coverage
from source_claims import Corpus
import supplied_research as store

class InsiderDisclosureTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='insider-rows-');self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name);self.sources=self.root/'sources';self.sources.mkdir()
  self.raw=b'Fictional structured disclosures only. Actual identity, holdings and motives are not established.\n'
  (self.sources/'original.txt').write_bytes(self.raw)
  def row(key,code,quantity,price,footnote):return {'id':key,'code':code,'quantity':quantity,'price':price,'transaction_date':'2034-02-03','filed_at':'2034-02-06','footnote':footnote}
  self.rows=[row('rA','P',12,7.5,'open-market discretionary purchase'),row('rB','A',40,0,'restricted-share award'),
   row('rC','F',9,8,'shares withheld for tax on vesting'),row('rD','M',18,3,'option exercise; linked sale under prearranged plan'),
   row('rE','S',18,8,'linked to rD; plan adopted 2033-09-12')]
  self.rows[0]['ownership']='direct'
  self.doc={'issuer':'SYN','insider_rows':self.rows,'official_disclosure':{'value_range_usd':[2000,9000]},
   'institutions':[{'manager':'SYN-M','report_period':'2033-12-31','filed':'2034-02-02','amendment':False,'shares':600},
    {'manager':'SYN-M','report_period':'2034-03-31','filed':'2034-05-03','amendment':False,'shares':850},
    {'manager':'SYN-M','report_period':'2034-03-31','filed':'2034-05-12','amendment':True,'amends':'2034-05-03','shares':720}],
   'source':{'path':'original.txt','sha256':store.digest(self.raw),'published_at':'2034-02-07T10:00:00Z','observed_at':'2034-02-07T11:00:00Z'}}
  self.manifest=self.root/'ingress.json';self.write()
 def write(self):
  raw=store.encode(self.doc);(self.sources/'records.json').write_bytes(raw)
  self.manifest.write_bytes(store.encode({'schema_version':1,'sources':[{'id':'records','path':'records.json','sha256':store.digest(raw),'format':'json'},
   {'id':'raw','path':'original.txt','sha256':store.digest(self.raw),'format':'text'}]}));self.pin=store.digest(self.manifest.read_bytes())
 def result(self):return insider.analyze(Corpus(self.manifest,self.pin,self.sources))
 def dataset(self):return self.result()['datasets'][0]
 def test_unknown_row_currency_does_not_inherit_adjacent_disclosure_usd(self):
  result=self.result();self.assertFalse(result['currency_inherited_from_other_contexts'])
  for row in result['datasets'][0]['rows']:
   self.assertIsNone(row['price_currency']['value']);self.assertEqual(row['price_currency']['status'],'UNSPECIFIED_IN_INSIDER_ROW')
   self.assertIsNone(row['quantity_times_price']['currency']);self.assertIsNone(row['cash_proxy']['currency'])
 def test_row_local_currency_never_propagates_to_other_rows(self):
  self.rows[0]['currency']='EUR';self.write();rows=self.dataset()['rows']
  self.assertEqual(rows[0]['price_currency']['value'],'EUR');self.assertTrue(all(r['price_currency']['value'] is None for r in rows[1:]))
 def test_root_currency_is_not_silently_inherited(self):
  self.doc['currency']='USD';self.write();self.assertTrue(all(r['price_currency']['value'] is None for r in self.dataset()['rows']))
 def test_mixed_known_and_unknown_currencies_have_separate_conditional_groups(self):
  self.rows[0]['currency']='EUR';self.rows[3]['currency']='JPY';self.write();groups=self.dataset()['cash_proxy_groups']
  self.assertEqual({g['currency'] for g in groups},{'EUR','JPY',None});self.assertTrue(all(not g['unit_compatibility_verified'] for g in groups))
 def test_conflicting_row_currencies_are_not_resolved_by_order(self):
  self.rows[0].update(currency='EUR',price_currency='JPY');self.write();row=self.dataset()['rows'][0]
  self.assertEqual(row['price_currency']['status'],'CONFLICTING_ROW_LOCAL_CURRENCY');self.assertIsNone(row['price_currency']['value'])
 def test_supported_codes_and_nontrade_mechanisms_remain_separate(self):
  rows=self.dataset()['rows'];self.assertEqual([r['code_mechanism'] for r in rows],['PURCHASE','AWARD','TAX_WITHHOLDING','OPTION_EXERCISE','SALE'])
  for index in (1,2,3):self.assertEqual(rows[index]['discretion_status'],'NOT_CLASSIFIED_AS_DISCRETIONARY_PURCHASE_OR_SALE')
  self.assertEqual(rows[0]['discretion_status'],'SUPPLIED_FOOTNOTE_DECLARES_DISCRETIONARY')
  self.assertEqual(rows[4]['discretion_status'],'REPORTED_PLAN_OR_LINKED_TRANSACTION_NOT_NEW_DISCRETION_PROOF')
 def test_exact_notional_and_signed_quantities_without_current_holdings_claim(self):
  data=self.dataset();self.assertEqual([r['quantity_times_price']['value'] for r in data['rows']],['90.0','0','72','54','144'])
  self.assertEqual(data['listed_row_quantity_arithmetic']['value'],'43')
  self.assertFalse(data['listed_row_quantity_arithmetic']['current_holdings_established'])
  self.assertEqual(data['cash_proxy_groups'][0]['raw_signed_numeric_sum'],'0.0')
  self.assertEqual(data['cash_proxy_groups'][0]['row_ids'],['rA','rD','rE'])
 def test_non_cash_rows_not_counted_as_purchase_or_sale_cash(self):
  rows=self.dataset()['rows'];self.assertFalse(rows[1]['cash_proxy']['included']);self.assertFalse(rows[2]['cash_proxy']['included'])
  self.assertEqual(rows[2]['quantity_times_price']['value'],'72');self.assertIsNone(rows[2]['cash_proxy']['value'])
 def test_unknown_identities_and_ownership_remain_local(self):
  rows=self.dataset()['rows'];self.assertTrue(all(r['identity_status']=='IDENTITY_UNSPECIFIED_IN_ROW' for r in rows))
  self.assertEqual(rows[0]['ownership_as_supplied'],'direct');self.assertTrue(all(r['ownership_as_supplied'] is None for r in rows[1:]))
  self.assertTrue(all(r['holdings_status']=='NOT_SUPPLIED_IN_ROW' for r in rows))
 def test_transaction_filing_and_source_observation_dates_remain_distinct(self):
  data=self.dataset();row=data['rows'][0];self.assertEqual(row['filing_lag_calendar_days'],3)
  self.assertEqual(row['transaction_date'],'2034-02-03');self.assertEqual(row['filed_at'],'2034-02-06')
  self.assertEqual(data['original_source_metadata']['observed_at'],'2034-02-07T11:00:00Z')
 def test_plan_link_and_adoption_date_are_literal_not_motive_proof(self):
  row=self.dataset()['rows'][4];self.assertEqual(row['footnote']['plan_adoption_dates_as_reported'],['2033-09-12'])
  self.assertEqual(row['footnote']['linked_ids_as_reported'],[{'id':'rD','present_in_same_original_insider_list':True}])
  self.assertFalse(row['motive_or_advance_knowledge_established'])
 def test_other_population_amendments_never_amend_insider_rows(self):
  data=self.dataset();self.assertFalse(data['other_population_amendments_applied_to_insiders'])
  self.assertTrue(all(r['insider_amendment_status']=='NOT_SUPPLIED_IN_ROW' for r in data['rows']))
  self.rows[0]['amendment']=True;self.rows[0]['amends']='earlier-row';self.write()
  self.assertEqual(self.dataset()['rows'][0]['insider_amendment_fields'],{'amendment':True,'amends':'earlier-row'})
 def test_no_discretionary_phrase_is_inferred_from_not_or_non_discretionary(self):
  for text in ('not a discretionary purchase','non-discretionary purchase','open-market purchase'):
   self.rows[0]['footnote']=text;self.write();self.assertEqual(self.dataset()['rows'][0]['discretion_status'],'DISCRETION_UNRESOLVED')
 def test_unknown_code_and_missing_link_remain_unresolved(self):
  self.rows[1]['code']='Z';self.rows[4]['footnote']='linked to absent; plan adopted 2033-09-12';self.write();data=self.dataset()
  self.assertEqual(data['rows'][1]['code_mechanism'],'UNSUPPORTED_TRANSACTION_CODE');self.assertFalse(data['listed_row_quantity_arithmetic']['all_codes_supported'])
  self.assertFalse(data['rows'][4]['footnote']['linked_ids_as_reported'][0]['present_in_same_original_insider_list'])
 def test_code_and_literal_footnote_conflict_remains_unresolved(self):
  self.rows[0]['footnote']='open-market discretionary sale';self.write();row=self.dataset()['rows'][0]
  self.assertEqual(row['discretion_status'],'UNRESOLVED_CODE_FOOTNOTE_CONFLICT');self.assertEqual(row['code_mechanism'],'PURCHASE')
 def test_negated_plan_is_not_positive_plan_declaration(self):
  self.rows[0]['footnote']='not under a prearranged plan';self.write();row=self.dataset()['rows'][0]
  self.assertFalse(row['footnote']['explicit_plan_phrase']);self.assertEqual(row['discretion_status'],'DISCRETION_UNRESOLVED')
 def test_duplicate_row_ids_rejected(self):
  self.rows[1]['id']='rA';self.write()
  with self.assertRaisesRegex(ValueError,'DUPLICATE_INSIDER_ROW_ID'):self.result()
 def test_original_raw_hash_and_source_corpus_are_bound(self):
  self.doc['source']['sha256']='0'*64;self.write()
  with self.assertRaisesRegex(ValueError,'REVISION_RAW_REFERENCE_HASH_MISMATCH'):self.result()
 def test_invalid_quantity_or_date_does_not_silently_coerce(self):
  self.rows[0]['quantity']=True;self.write()
  with self.assertRaises(ValueError):self.result()
  self.rows[0]['quantity']=12;self.rows[0]['filed_at']='2034-02-01';self.write()
  with self.assertRaisesRegex(ValueError,'INSIDER_FILING_PRECEDES_TRANSACTION'):self.result()
 def test_exact_arithmetic_independent_of_ambient_decimal_precision(self):
  with localcontext() as context:
   context.prec=2
   self.assertEqual(str(insider.exact_product(Decimal('12345678901234567890123456789'),Decimal('3'))),'37037036703703703670370370367')
   self.assertEqual(str(insider.exact_sum([Decimal('12345678901234567890123456789'),Decimal('-1')])),'12345678901234567890123456788')
 def test_native_whole_pair_replay_rejects_invented_currency(self):
  request=b'Review insider mechanisms, dates and source limits.\n';(self.sources/'request.txt').write_bytes(request)
  scope={'schema_version':1,'original_request':{'path':'request.txt','sha256':store.digest(request)},'manifest_sha256':self.pin,'analysis_profile':'INSIDER_DISCLOSURES','units':[{'id':'whole','start_byte':0,'end_byte':len(request),'sha256':store.digest(request)}]}
  sp=self.root/'scope.json';sp.write_bytes(store.encode(scope));spin=store.digest(sp.read_bytes())
  plan={'schema_version':1,'units':[{'unit_id':'whole','source_ids':['records','raw'],'discovery_routes':[]}], 'sources':[{'source_id':sid,'access':'SUPPLIED_BODY','lineage':[]} for sid in ['records','raw']]}
  pp=self.root/'plan.json';pp.write_bytes(store.encode(plan));out=self.root/'delivery'
  coverage.compose(pp,sp,spin,self.manifest,self.pin,self.sources,out);coverage.verify(out,spin,self.pin,out/'first-response.md',out/'response.json')
  result=json.loads((out/'response.json').read_bytes());self.assertIsNone(result['native_analysis']['datasets'][0]['rows'][0]['price_currency']['value'])
  self.assertIn(b'UNSPECIFIED_IN_INSIDER_ROW',(out/'first-response.md').read_bytes())
  result['native_analysis']['datasets'][0]['rows'][0]['price_currency']['value']='USD';(out/'response.json').write_bytes(store.encode(result))
  receipt=json.loads((out/'receipt.json').read_bytes());receipt['artifacts']=store.file_inventory(out);(out/'receipt.json').write_bytes(store.encode(receipt))
  with self.assertRaisesRegex(ValueError,'COVERAGE_REPLAY_MISMATCH'):coverage.verify(out,spin,self.pin)

if __name__=='__main__':unittest.main()
