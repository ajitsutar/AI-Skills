import json,shutil,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import supplied_research as bridge

class SuppliedResearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='supplied-research-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.sources=self.root/'sources';self.sources.mkdir()
        self.raw=b'{"holding":{"basis":"common","amount":7.5}}\n'
        (self.sources/'record.json').write_bytes(self.raw)
        self.manifest=self.root/'ingress.json';self.make_manifest()
        self.req=self.root/'request.json';self.document={'producer':'source_claims','producer_request':{'operation':'presence','terms':['common']}}
        self.save_request();self.output=self.root/'output'
    def make_manifest(self,filename='record.json'):
        self.manifest.write_bytes(bridge.encode({'schema_version':1,'sources':[{'id':'original','path':filename,
            'sha256':bridge.digest(self.raw),'format':'json'}]}));self.pin=bridge.digest(self.manifest.read_bytes())
    def save_request(self):self.req.write_bytes(bridge.encode(self.document))
    def run_bridge(self):return bridge.run(self.req,self.output,self.manifest,self.pin,self.sources)
    def rewrite_inventory(self):
        p=self.output/'receipt.json';r=json.loads(p.read_bytes());r['artifacts']=bridge.file_inventory(self.output);p.write_bytes(bridge.encode(r))
    def test_real_producer_originals_report_and_replay(self):
        receipt=self.run_bridge();result=json.loads((self.output/'result.json').read_bytes())
        self.assertEqual(result['predicate'],'SOURCE_CANDIDATE_PRESENT')
        self.assertEqual((self.output/'originals/record.json').read_bytes(),self.raw)
        self.assertIn('Complete structured evidence',(self.output/'report.md').read_text())
        self.assertFalse(receipt['whole_report_semantic_pass']);self.assertEqual(bridge.verify(self.output)['status'],'SOURCE_REPLAY_AND_SAVED_REPORT_MATCH')
    def test_no_cached_success_field_accepted(self):
        self.document['result']={'status':'PASS'};self.save_request()
        with patch.object(bridge,'produce') as producer,self.assertRaisesRegex(ValueError,'EXACT_REQUEST_FIELDS_REQUIRED'):self.run_bridge()
        producer.assert_not_called();self.assertTrue((self.output/'failure.json').exists());self.assertFalse((self.output/'receipt.json').exists())
    def test_original_pin_not_replaceable(self):
        self.pin='0'*64
        with self.assertRaisesRegex(ValueError,'EXTERNAL_MANIFEST_PIN_MISMATCH'):self.run_bridge()
        self.assertEqual((self.sources/'record.json').read_bytes(),self.raw)
    def test_whole_corpus_member_hash_checked(self):
        (self.sources/'record.json').write_bytes(b'{"other":1}')
        with self.assertRaisesRegex(ValueError,'ORIGINAL_SOURCE_HASH_MISMATCH'):self.run_bridge()
    def test_saved_report_edit_rejected_after_rehash(self):
        self.run_bridge();p=self.output/'report.md';p.write_bytes(p.read_bytes()+b'Unjustified conclusion.\n');self.rewrite_inventory()
        with self.assertRaisesRegex(ValueError,'SAVED_REPORT_MISMATCH'):bridge.verify(self.output)
    def test_cached_output_edit_rejected_by_source_replay(self):
        self.run_bridge();p=self.output/'result.json';r=json.loads(p.read_bytes());r['predicate']='SOURCE_ABSENT';p.write_bytes(bridge.encode(r));self.rewrite_inventory()
        with self.assertRaisesRegex(ValueError,'ORIGINAL_SOURCE_REPLAY_MISMATCH'):bridge.verify(self.output)
    def test_rejected_claim_never_becomes_semantic_pass(self):
        self.document['producer_request']['assert_claims']=['source_absent'];self.save_request();receipt=self.run_bridge()
        result=json.loads((self.output/'result.json').read_bytes());self.assertEqual(result['claim_verdict'],'REJECTED')
        self.assertIn('REJECTED',(self.output/'report.md').read_text());self.assertFalse(receipt['whole_report_semantic_pass'])
    def test_free_prose_is_always_unaudited(self):
        self.document['unverified_prose']='An unsupported qualitative interpretation.';self.save_request();receipt=self.run_bridge()
        report=(self.output/'report.md').read_text();self.assertIn('## Unaudited prose',report)
        self.assertEqual(receipt['free_prose_status'],'UNAUDITED_PROSE_PRESENT');self.assertFalse(bridge.verify(self.output)['whole_report_semantic_pass'])
    def test_failure_retains_partial_originals(self):
        with patch.object(bridge,'produce',side_effect=RuntimeError('producer failed')):
            with self.assertRaisesRegex(RuntimeError,'producer failed'):self.run_bridge()
        self.assertTrue((self.output/'ingress.json').exists());self.assertTrue((self.output/'originals/record.json').exists())
        self.assertFalse((self.output/'receipt.json').exists());self.assertEqual(json.loads((self.output/'failure.json').read_bytes())['stage'],'producer')
    def test_producer_drift_blocks_completion(self):
        with patch.object(bridge,'produce',side_effect=[{'status':'FIRST'},{'status':'SECOND'}]):
            with self.assertRaisesRegex(ValueError,'ORIGINAL_SOURCE_REPLAY_MISMATCH'):self.run_bridge()
        self.assertTrue((self.output/'result.json').exists());self.assertFalse((self.output/'receipt.json').exists())
    def test_producer_report_bad_digest_rejected(self):
        self.document={'producer':'analyst_sources','producer_request':{}};self.save_request()
        with patch.object(bridge,'produce',return_value={'report':{'text':'Generated source findings.','sha256':'0'*64,'whole_report_semantic_pass':False}}):
            with self.assertRaisesRegex(ValueError,'PRODUCER_REPORT_HASH_MISMATCH'):self.run_bridge()
    def test_fixed_producer_report_is_replayed(self):
        self.document={'producer':'reit_sources','producer_request':{}};self.save_request();text='Basis remains unresolved.\n'
        result={'report':{'text':text,'sha256':bridge.digest(text.encode()),'whole_report_semantic_pass':False},'metric_ledger':{'primary':None}}
        with patch.object(bridge,'produce',return_value=result) as producer:
            receipt=self.run_bridge();self.assertEqual(producer.call_count,2);self.assertFalse(bridge.verify(self.output)['whole_report_semantic_pass'])
        self.assertIn(text,(self.output/'report.md').read_text());self.assertFalse(receipt['source_authenticity_verified'])
    def test_implementation_change_blocks_verify(self):
        self.run_bridge()
        with patch.object(bridge,'implementations',return_value={'changed.py':'0'*64}):
            with self.assertRaisesRegex(ValueError,'IMPLEMENTATION_CHANGED'):bridge.verify(self.output)
    def test_unrelated_receipt_named_source_is_inventoried(self):
        (self.sources/'receipt.json').write_bytes(self.raw);self.make_manifest('receipt.json');r=self.run_bridge()
        self.assertIn('originals/receipt.json',r['artifacts']);bridge.verify(self.output)
    def test_existing_output_unchanged(self):
        self.output.mkdir();p=self.output/'keep';p.write_bytes(b'original')
        with self.assertRaisesRegex(ValueError,'NEW_PRIVATE_OUTPUT_REQUIRED'):self.run_bridge()
        self.assertEqual(p.read_bytes(),b'original');self.assertEqual(len(list(self.output.iterdir())),1)
    def test_source_case_collision_rejected(self):
        manifest=json.loads(self.manifest.read_bytes());manifest['sources'].append({**manifest['sources'][0],'id':'other','path':'RECORD.json'})
        self.manifest.write_bytes(bridge.encode(manifest));self.pin=bridge.digest(self.manifest.read_bytes())
        # This also works on case-sensitive hosts.
        if not (self.sources/'RECORD.json').exists():(self.sources/'RECORD.json').write_bytes(self.raw)
        with self.assertRaisesRegex(ValueError,'DUPLICATE_SOURCE_PATH'):self.run_bridge()
    def test_real_analyst_producer_report_and_replay(self):
        row={'firm_id':'Cedar','analyst_id':'Researcher','issuer':'SYN','currency':'USD','target':46.5,
             'issued_at':'2028-02-02T10:00:00Z','published_at':'2028-02-02T11:00:00Z','observed_at':'2028-02-02T12:00:00Z',
             'url':'https://example.test/note','price_basis':'common_share_unadjusted','target_horizon':'forward_12_months','access':'FULL_REPORT'}
        self.raw=bridge.encode(row);(self.sources/'record.json').write_bytes(self.raw);self.make_manifest()
        self.document={'producer':'analyst_sources','producer_request':{'as_of':'2028-02-10T12:00:00Z',
            'cohort':{'issuer':'SYN','currency':'USD','price_basis':'common_share_unadjusted','target_horizon':'forward_12_months'},
            'extraction_profile':{'formats':['json_records','labelled_sentences']}}};self.save_request()
        self.run_bridge();result=json.loads((self.output/'result.json').read_bytes())
        self.assertEqual(result['eligible_cohort']['result']['consensus']['mean'],46.5)
        self.assertIn('Cedar',(self.output/'report.md').read_text());self.assertFalse(bridge.verify(self.output)['whole_report_semantic_pass'])
    def test_real_reit_producer_report_and_replay(self):
        from test_reit_sources import fixture
        req,original=fixture();self.raw=bridge.encode(original);(self.sources/'record.json').write_bytes(self.raw);self.make_manifest()
        self.document={'producer':'reit_sources','producer_request':req};self.save_request();self.run_bridge()
        result=json.loads((self.output/'result.json').read_bytes())
        self.assertTrue(result['metric_ledger']['affo']['source_bound_comparability'])
        self.assertIn('source-record compatible arithmetic',(self.output/'report.md').read_text())
        self.assertFalse(bridge.verify(self.output)['whole_report_semantic_pass'])

    def test_real_reit_fractional_json_request_retains_exact_bytes_and_replays(self):
        from test_reit_sources import fixture
        req, original = fixture()
        req['document']['cfo']['amount'] = 17.125
        for binding in req['bindings']:
            if binding['target_pointer'] == '/cfo/amount':
                original['records'][int(binding['record_pointer'].split('/')[-1])]['value'] = 17.125
        self.raw = json.dumps(original).encode()
        (self.sources/'record.json').write_bytes(self.raw); self.make_manifest()
        self.document = {'producer':'reit_sources', 'producer_request':req}
        raw_request = json.dumps(self.document).encode()
        self.req.write_bytes(raw_request)
        receipt = self.run_bridge()
        result = json.loads((self.output/'result.json').read_bytes())
        self.assertEqual(result['metric_ledger']['cfo']['value'], '17.125')
        self.assertEqual((self.output/'original-request.json').read_bytes(), raw_request)
        self.assertEqual((self.output/'originals/record.json').read_bytes(), self.raw)
        self.assertFalse(receipt['whole_report_semantic_pass'])
        self.assertEqual(bridge.verify(self.output)['status'], 'SOURCE_REPLAY_AND_SAVED_REPORT_MATCH')

    def test_unbound_reit_basis_stays_conditional_after_replay(self):
        # Preserve the accepted public-subset regression with an explicit REIT
        # fixture, since the full experimental suite defaults to source claims.
        from test_reit_sources import fixture
        req, original = fixture()
        req['bindings'] = []
        self.raw = bridge.encode(original)
        (self.sources/'record.json').write_bytes(self.raw); self.make_manifest()
        self.document = {'producer':'reit_sources', 'producer_request':req}
        self.save_request(); receipt = self.run_bridge()
        result = json.loads((self.output/'result.json').read_bytes())
        self.assertIsNone(result['metric_ledger']['affo']['value'])
        self.assertIsNotNone(result['metric_ledger']['affo']['conditional_same_basis_value'])
        self.assertFalse(receipt['whole_report_semantic_pass'])
        self.assertEqual(bridge.verify(self.output)['status'], 'SOURCE_REPLAY_AND_SAVED_REPORT_MATCH')

    def test_real_reit_exported_copy_replays_without_original_location(self):
        from test_reit_sources import fixture
        req,original=fixture();self.raw=bridge.encode(original);(self.sources/'record.json').write_bytes(self.raw);self.make_manifest()
        self.document={'producer':'reit_sources','producer_request':req};self.save_request();self.run_bridge()
        exported=self.root/'exported-copy';shutil.copytree(self.output,exported)
        retained_result=(exported/'result.json').read_bytes()
        self.output.rename(self.root/'original-run-moved')
        self.sources.rename(self.root/'input-sources-moved')
        self.assertEqual(bridge.verify(exported)['status'],'SOURCE_REPLAY_AND_SAVED_REPORT_MATCH')
        self.assertEqual((exported/'result.json').read_bytes(),retained_result)

if __name__=='__main__':unittest.main(verbosity=2)
