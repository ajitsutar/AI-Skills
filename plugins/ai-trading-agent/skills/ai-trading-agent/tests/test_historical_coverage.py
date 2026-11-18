"""Fictional coverage regressions: identity, intervals, source overlap and missing data."""
import copy,gzip,json,subprocess,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import historical_coverage as coverage

W={'ref':'evidence/fictional.json','sha256':'a'*64}
D=['2020-01-02','2020-01-03','2020-01-06']
def case():
    bounds=[{'start_inclusive':D[0],'end_exclusive':'2020-01-07'}]
    return {'schema_version':1,'sessions':D,'calendar_reviewed':True,'calendar_evidence':[W],'securities':[{'id':'security:A','issuer_id':'issuer:A','share_class_id':'common:A','kind':'equity','membership_intervals':bounds,'listing_intervals':copy.deepcopy(bounds),'membership_reviewed':True,'membership_evidence':[W],'listing_reviewed':True,'listing_evidence':[W]}],
            'series':[{'id':'source:A','issuer_id':'issuer:A','share_class_id':'common:A','kind':'equity','source':W,'observations':[{'date':d,'adjusted_close':100+i} for i,d in enumerate(D)]}],
            'mappings':[{'security_id':'security:A','series_id':'source:A','relationship':'same_security_rename','reviewed':True,'evidence':[W],**bounds[0]}]}
def row(c):return coverage.audit(c)['rows'][0]

class HistoricalCoverageTests(unittest.TestCase):
    def test_reviewed_rename_covers_dates_but_never_certifies_returns(self):
        r=coverage.audit(case());self.assertEqual(r['rows'][0]['missing_sessions'],[])
        self.assertEqual(r['rows'][0]['status'],'DECLARED_REVIEWED_DATE_COVERAGE')
        self.assertFalse(r['point_in_time_complete_certified']);self.assertFalse(r['return_series_constructed'])
    def test_ticker_reuse_cannot_masquerade_as_rename(self):
        c=case();c['mappings'][0]['relationship']='ticker_reuse';self.assertEqual(row(c)['missing_sessions'],D)
    def test_merger_requires_accounting_even_when_caller_says_reviewed(self):
        c=case();c['mappings'][0]['relationship']='merger_exchange';self.assertEqual(row(c)['missing_sessions'],D)
    def test_same_cik_different_class_rejected(self):
        c=case();c['series'][0]['share_class_id']='preferred:A';self.assertEqual(row(c)['missing_sessions'],D)
    def test_unknown_class_not_inferred_from_issuer(self):
        c=case();c['securities'][0].pop('share_class_id');self.assertEqual(row(c)['missing_sessions'],D)
    def test_reused_etf_ticker_quarantined(self):
        c=case();c['series'][0]['kind']='etf';self.assertEqual(row(c)['missing_sessions'],D)
    def test_unreviewed_evidence_does_not_count(self):
        c=case();c['mappings'][0]['reviewed']=False;self.assertEqual(row(c)['missing_sessions'],D)
        c=case();c['mappings'][0]['evidence']=[];self.assertEqual(row(c)['missing_sessions'],D)
    def test_missing_native_source_witness_rejected(self):
        c=case();c['series'][0]['source']={'ref':'guess'};self.assertEqual(row(c)['missing_sessions'],D)
    def test_listing_boundary_avoids_pre_ipo_gaps(self):
        c=case();c['securities'][0]['listing_intervals'][0]['start_inclusive']=D[1]
        c['series'][0]['observations']=c['series'][0]['observations'][1:]
        self.assertEqual(row(c)['expected_session_count'],2);self.assertEqual(row(c)['missing_sessions'],[])
    def test_exclusive_membership_exit(self):
        c=case();c['securities'][0]['membership_intervals'][0]['end_exclusive']=D[-1]
        c['series'][0]['observations']=c['series'][0]['observations'][:2]
        self.assertEqual(row(c)['expected_session_count'],2);self.assertEqual(row(c)['missing_sessions'],[])
    def test_unknown_and_empty_bounds_are_not_complete(self):
        c=case();c['securities'][0].pop('membership_intervals');self.assertIsNone(row(c)['missing_sessions'])
        self.assertEqual(row(c)['status'],'EXPECTED_SESSIONS_UNKNOWN')
        c=case();c['securities'][0]['membership_intervals']=[];self.assertEqual(row(c)['status'],'NO_EXPECTED_SESSIONS')
    def test_unknown_listing_leaves_conditional_coverage(self):
        c=case();c['securities'][0].pop('listing_intervals');self.assertEqual(row(c)['status'],'CONDITIONAL_DATE_COVERAGE')
    def test_unreviewed_calendar_is_explicitly_conditional(self):
        c=case();c.pop('calendar_evidence');self.assertEqual(row(c)['status'],'CONDITIONAL_DATE_COVERAGE')
    def test_filing_date_never_substitutes_for_accession(self):
        f={'issuer_id':'issuer:A','accession':'original','filed':'2020-01-02'}
        m={'issuer_id':'issuer:A','accession':'replacement','filing_date':'2020-01-02','acceptance_at':'2021-01-02T12:00:00Z','source':W}
        r=coverage.join_filing_metadata([f],[m]);self.assertEqual(r['rows'][0]['status'],'NO_EXACT_ACCESSION_MATCH')
        self.assertIsNone(r['rows'][0]['acceptance_at'])
    def test_accession_also_requires_exact_issuer(self):
        f={'issuer_id':'issuer:A','accession':'same'}
        m={'issuer_id':'issuer:B','accession':'same','acceptance_at':'2020-01-02T12:00:00Z','source':W}
        self.assertEqual(coverage.join_filing_metadata([f],[m])['exact_acceptance_count'],0)
    def test_exact_acceptance_is_not_public_availability_certification(self):
        f={'issuer_id':'issuer:A','accession':'same'}
        m={**f,'acceptance_at':'2020-01-02T07:00:00-05:00','source':W}
        r=coverage.join_filing_metadata([f],[m])['rows'][0]
        self.assertEqual(r['acceptance_at'],'2020-01-02T12:00:00+00:00');self.assertFalse(r['public_availability_verified'])
    def test_conflicting_acceptance_times_and_filing_dates_remain_unknown(self):
        f={'issuer_id':'issuer:A','accession':'same','filed':'2020-01-02'}
        m={**f,'acceptance_at':'2020-01-02T12:00:00Z','source':W}
        r=coverage.join_filing_metadata([f],[m,{**m,'acceptance_at':'2020-01-03T12:00:00Z'}])['rows'][0]
        self.assertEqual(r['status'],'CONFLICTING_METADATA');self.assertIsNone(r['acceptance_at'])
        r=coverage.join_filing_metadata([f],[{**m,'filing_date':'2020-01-03'}])['rows'][0]
        self.assertEqual(r['status'],'CONFLICTING_METADATA')
    def test_naive_acceptance_and_missing_source_are_not_invented(self):
        f={'issuer_id':'issuer:A','accession':'same'}
        for m in [{**f,'acceptance_at':'2020-01-02T12:00:00','source':W},{**f,'acceptance_at':'2020-01-02T12:00:00Z'}]:
            self.assertEqual(coverage.join_filing_metadata([f],[m])['exact_acceptance_count'],0)
    def test_union_is_not_approved_stitched_series(self):
        c=case();second=copy.deepcopy(c['series'][0]);second['id']='source:B';second['observations']=second['observations'][1:]
        c['series'][0]['observations']=c['series'][0]['observations'][:1];c['series'].append(second)
        m=copy.deepcopy(c['mappings'][0]);m['series_id']='source:B';c['mappings'].append(m)
        r=row(c);self.assertEqual(r['missing_sessions'],[]);self.assertTrue(r['multiple_sources_needed_for_date_union'])
        self.assertEqual(r['single_source_complete_ids'],[]);self.assertFalse(r['return_series_constructed'])
    def test_invalid_duplicate_and_excluded_values_are_not_usable(self):
        c=case();c['series'][0]['observations'][0]['adjusted_close']=0
        c['series'][0]['observations'].append({'date':D[1],'adjusted_close':101})
        c['series'][0]['quality_excluded_dates']=[D[2]];self.assertEqual(row(c)['missing_sessions'],D)
    def test_off_calendar_and_mapping_boundary(self):
        c=case();c['series'][0]['observations'].append({'date':'2020-01-04','adjusted_close':100})
        c['mappings'][0]['end_exclusive']=D[-1];r=coverage.audit(c)
        self.assertEqual(r['rows'][0]['missing_sessions'],[D[-1]])
        self.assertEqual(r['source_quality']['source:A']['off_calendar'],['2020-01-04'])
    def test_synthetic_carried_and_unknown_rows_cannot_close_observed_gaps(self):
        for role in ('carried_forward','synthetic','modeled_terminal','patched_exit','unknown',None):
            c=case();c['series'][0]['observations'][1]['observation_role']=role
            r=coverage.audit(c)
            self.assertEqual(r['rows'][0]['missing_sessions'],[D[1]])
            self.assertEqual(r['source_quality']['source:A']['non_observed'],[D[1]])
    def test_bad_grid_duplicate_ids_and_unknown_endpoint_fail(self):
        for change in ('grid','ids','endpoint','date'):
            c=case()
            if change=='grid':c['sessions']=D+D[:1]
            if change=='ids':c['securities']*=2
            if change=='endpoint':c['mappings'][0]['series_id']='missing'
            if change=='date':c['mappings'][0]['end_exclusive']='2020-01-01'
            with self.assertRaises(ValueError):coverage.audit(c)
    def test_cli_compressed_input_output_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);inp=root/'input.json.gz';out=root/'result.json.gz';inp.write_bytes(gzip.compress(json.dumps(case()).encode()))
            cmd=[sys.executable,str(Path(coverage.__file__)),'--input',str(inp),'--output',str(out)]
            p=subprocess.run(cmd,capture_output=True);self.assertEqual(p.returncode,0,p.stderr)
            r=json.loads(gzip.decompress(out.read_bytes()));self.assertEqual(r['missing_identity_qualified_sessions'],0)
            old=out.read_bytes();p=subprocess.run(cmd,capture_output=True);self.assertNotEqual(p.returncode,0);self.assertEqual(out.read_bytes(),old)
    def test_cli_decompressed_size_bound(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);inp=root/'input.json.gz';out=root/'result.json.gz';inp.write_bytes(gzip.compress(json.dumps(case()).encode()))
            p=subprocess.run([sys.executable,str(Path(coverage.__file__)),'--input',str(inp),'--output',str(out),'--max-input-bytes','10'],capture_output=True)
            self.assertNotEqual(p.returncode,0);self.assertFalse(out.exists())

if __name__=='__main__':unittest.main()
