import copy,importlib.util,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import quant_workbench as w
import report_facts


class PortableIntegrationTests(unittest.TestCase):
    def require_optional(self):
        missing=[name for name in ('statsmodels','QuantLib','vaderSentiment') if importlib.util.find_spec(name) is None]
        if missing:self.skipTest('Optional calculation libraries unavailable: '+','.join(missing))
    def document(self):
        return json.loads((ROOT/'examples/portable-workbench.json').read_text())

    def test_all_six_operations_compute_and_replay(self):
        self.require_optional()
        packet=self.document()
        self.assertEqual({j['operation'] for j in packet['jobs']},set(w.PORTABLE_OPERATIONS))
        prepared=w.prepare(packet)
        original=copy.deepcopy(prepared)
        bundle=w.freeze(prepared)
        self.assertEqual([r for r in bundle['result']['results'] if r['status']!='COMPUTED'],[])
        self.assertEqual(prepared,original)
        self.assertEqual(w.verify(bundle)['status'],'REPLAY_MATCH')

    def test_past_cutoff_rejects_every_future_job(self):
        packet=self.document();packet['contract']['as_of']='2000-01-01T00:00:00Z'
        result=w.run(packet)
        self.assertTrue(all(r['status']=='REJECTED_INPUT' for r in result['results']))

    def test_currency_mismatch_rejects_pricing_and_paper(self):
        packet=self.document();packet['contract']['base_currency']='EUR'
        result=w.run(packet)
        for row in result['results']:
            if row['operation']!='data.asof_snapshot':self.assertEqual(row['status'],'REJECTED_INPUT')

    def test_report_identity_matches_updated_workbench(self):
        self.assertEqual(set(w.MODULES),set(report_facts.QUANT_FILES))
        self.assertEqual(w.implementation_hash(),report_facts.quant_hash())
        self.require_optional()
        bundle=w.freeze(w.prepare(self.document()))
        result=report_facts.project(json.dumps(bundle).encode(),'quant')
        self.assertTrue(result['checks'][0]['code_mapping_matches'])

    def test_freeze_records_optional_runtime_versions(self):
        self.require_optional()
        result=w.freeze(w.prepare(self.document()))
        for name in ('statsmodels','QuantLib','vaderSentiment'):
            self.assertNotEqual(result['environment'][name],'UNAVAILABLE')


if __name__=='__main__':unittest.main()
