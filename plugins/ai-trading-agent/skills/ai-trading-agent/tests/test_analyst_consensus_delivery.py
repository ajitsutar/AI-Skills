"""Synthetic dispersion and same-record provider delivery regressions."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import analyst_sources as module
import final_report
from source_claims import Corpus


class AnalystConsensusDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='consensus-delivery-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sources = self.root / 'originals'
        self.sources.mkdir()
        self.manifest = self.root / 'manifest.json'
        self.request = {'as_of': '2034-08-19T18:00:00Z',
            'cohort': {'issuer': 'SYNTH', 'currency': 'EUR', 'price_basis': 'common_share_unadjusted',
                       'target_horizon': 'forward_12_months'},
            'extraction_profile': {'formats': ['json_records']}}

    def metadata(self):
        return {'published_at': '2034-08-18T13:00:00Z', 'observed_at': '2034-08-18T14:00:00Z',
                'url': 'https://example.test/research/synthetic'}

    def target(self, firm='Cedar', value=71, **changes):
        return {**self.request['cohort'], 'firm_id': firm, 'analyst_id': 'Author' + firm,
                'target': value, 'issued_at': '2034-08-17T12:00:00Z',
                'access': 'FULL_REPORT', 'source': self.metadata(), **changes}

    def pool(self, **changes):
        return {**self.request['cohort'], 'provider': 'Atlas', 'upstream': 'ResearchFeed',
                'firm_population': ['Cedar', 'Elm', 'Pine'], 'mean': 95,
                'target_count': 7, 'as_of': '2034-08-18', 'source': self.metadata(), **changes}

    def prepare(self, document):
        raw = json.dumps(document).encode()
        (self.sources / 'evidence.json').write_bytes(raw)
        self.manifest.write_text(json.dumps({'schema_version': 1, 'sources': [
            {'id': 'evidence', 'path': 'evidence.json', 'format': 'json',
             'sha256': hashlib.sha256(raw).hexdigest()}]}), encoding='utf8')
        self.pin = hashlib.sha256(self.manifest.read_bytes()).hexdigest()
        return raw

    def analyze(self, document):
        self.prepare(document)
        return module.analyze(self.request, self.manifest, self.pin, self.sources)

    def pools(self, output):
        return output['eligible_cohort']['result']['provider_consensus']

    def assert_unresolved(self, document):
        out = self.analyze(document)
        self.assertEqual(self.pools(out), [])
        self.assertTrue(out['coverage']['unresolved_candidates'])
        self.assertEqual(out['coverage']['status'], 'INCOMPLETE')
        return out

    def test_nonuniform_dispersion_and_deduplication(self):
        rows = [self.target(n, v) for n, v in zip(['Cedar','Elm','Pine','Oak'], [71,83,102,138])]
        rows += [self.target(value=500, issued_at='2034-07-01T12:00:00Z'), copy.deepcopy(rows[0]),
                 self.target('Excluded', 900, access='SNIPPET')]
        out = self.analyze({'individual_targets': rows})['eligible_cohort']['result']['consensus']
        for k, v in {'mean':98.5, 'median':92.5, 'minimum':71, 'maximum':138,
                     'range_width':67, 'q1':80, 'q3':111, 'iqr':31, 'independent_firms':4}.items():
            self.assertEqual(out[k], v, k)
        self.assertEqual(out['iqr_over_median'],31/92.5)
        self.assertEqual(out['quartile_method'],'LINEAR_INTERPOLATION_INDEX_(n-1)*p')

    def test_singleton_zero_is_not_unknown(self):
        out = self.analyze(self.target())['eligible_cohort']['result']['consensus']
        self.assertEqual((out['range_width'],out['iqr']), (0,0))
        self.assertEqual(out['q1'],71)

    def test_empty_does_not_manufacture_zero(self):
        out = self.analyze(self.target(access='SNIPPET'))['eligible_cohort']['result']['consensus']
        self.assertEqual(out['status'],'UNAVAILABLE')
        self.assertNotIn('iqr',out)
        self.assertNotIn('range_width',out)

    def test_provider_pools_stay_separate_bound_and_population_scoped(self):
        second = self.pool(provider='Beacon',mean=108,target_count=9,as_of='2034-08-16',
                           firm_population=['Cedar','Oak','Birch'])
        out = self.analyze({'bucket/~': {'provider_consensus':[self.pool(),second]},
                            'individual_targets':[self.target()]})
        self.assertEqual(out['eligible_cohort']['result']['consensus']['mean'],71)
        pools = self.pools(out)
        self.assertEqual([p['mean'] for p in pools],[95,108])
        corpus=Corpus(self.manifest,self.pin,self.sources)
        for row in pools:
            self.assertEqual(row['status'],'PROVIDER_REPORTED_NOT_COMBINED')
            self.assertTrue(row['comparable_dimensions'])
            self.assertFalse(row['source_authenticity_verified'])
            for key,binding in row['bindings'].items():
                resolved = ([corpus.resolve(ref) for ref in binding['members']] if 'members' in binding
                            else corpus.resolve(binding['source_ref']))
                self.assertEqual(resolved,row[key])
            self.assertTrue(row['bindings']['mean']['source_ref']['pointer'].startswith('/bucket~1~0/'))
        lineage=out['eligible_cohort']['result']['source_population_provenance']
        self.assertEqual(lineage[0]['declared_shared_upstream_groups'],[])
        self.assertEqual(lineage[1]['declared_shared_upstream_groups'][0]['entity_ids'],['Atlas','Beacon'])
        self.assertIn('never averaged',out['report']['text'])

    def test_direct_metadata_identical_duplicates_and_no_reference_following(self):
        row=self.pool();row.update(self.metadata())
        row['source'].update(path='../missing.json',sha256='0'*64,verbatim_excerpt='not followed')
        out=self.pools(self.analyze(row))[0]
        self.assertEqual(out['bindings']['published_at']['source_ref']['pointer'],'/published_at')
        self.assertEqual(out['source']['path'],'evidence.json')

    def test_provider_missing_roles_never_filled_from_request_or_ancestor(self):
        for key in ('provider','as_of','issuer','currency','price_basis','target_horizon','mean','target_count'):
            with self.subTest(key=key):
                row=self.pool();value=row.pop(key)
                self.assert_unresolved({key:value,'provider_consensus':[row]})
        for key in module.SOURCE_METADATA:
            with self.subTest(key=key):
                row=self.pool();value=row['source'].pop(key)
                self.assert_unresolved({key:value,'source':{key:value},'provider_consensus':[row]})

    def test_conflict_null_or_unknown_qualifier_not_ignored(self):
        for key in module.SOURCE_METADATA:
            row=self.pool();row[key]=None
            self.assert_unresolved(row)
        for changes in ({'mean':None},{'mean':True},{'target_count':True},{'target_count':0},
                        {'target_count':2.5},{'mean':-2},{'minimum':110,'maximum':90},
                        {'minimum':100,'maximum':120},{'forecast_only':True},
                        {'firm_population':['Cedar','Cedar']},{'upstream':[]}):
            with self.subTest(changes=changes): self.assert_unresolved(self.pool(**changes))

    def test_invalid_future_chronology_and_date_precision(self):
        for key, value in [('published_at','2034-08-20T12:00:00Z'),
                           ('observed_at','2034-08-20T12:00:00Z'),
                           ('observed_at','2034-08-17T12:00:00Z'),
                           ('published_at','2034-08-18'),('url','http://example.test')]:
            row=self.pool();row['source'][key]=value
            self.assert_unresolved(row)
        for value in ['2034-08-20','2034-08-19','2034-08-18T14:00:00Z','unknown','2034-08-18T12:00:00']:
            self.assert_unresolved(self.pool(as_of=value))
        self.assertEqual(self.pools(self.analyze(self.pool()))[0]['snapshot_precision'],
                         'DATE_ONLY_NO_INTRADAY_TIME_INFERRED')

    def test_mismatched_dimensions_remain_separate_explicitly_noncomparable(self):
        for key,value in [('issuer','OTHER'),('currency','GBP'),('price_basis','adr'),
                          ('target_horizon','forward_52_weeks')]:
            out=self.pools(self.analyze(self.pool(**{key:value})))[0]
            self.assertFalse(out['comparable_dimensions'])
            self.assertEqual(out[key],value)

    def test_unknown_provider_containers_and_url_only_are_unresolved(self):
        for value in ['https://example.test/provider', {'mean':95}, [None], [95], [{'provider':'Atlas'}]]:
            self.assert_unresolved({'provider_consensus':value})
        self.assert_unresolved({'provider':'Atlas','mean':95,'url':'https://example.test/provider'})

    def test_bad_pool_does_not_erase_valid_pool_or_targets(self):
        out=self.analyze({'provider_consensus':[self.pool(),self.pool(provider='Bad',target_count=-1)],
                          'individual_targets':[self.target()]})
        self.assertEqual(len(self.pools(out)),1)
        self.assertEqual(out['eligible_cohort']['result']['consensus']['mean'],71)
        self.assertEqual(out['coverage']['status'],'INCOMPLETE')

    def test_native_md_json_delivery_replay_and_tamper(self):
        rows=[self.target(n,v) for n,v in zip(['Cedar','Elm','Pine','Oak'],[71,83,102,138])]
        raw=self.prepare({'individual_targets':rows,'provider_consensus':[self.pool()]})
        plan=self.root/'plan.json'
        plan.write_text(json.dumps({'output_contract':final_report.STRICT,
                                    'sections':[{'kind':'source_report','producer':'analyst_sources',
                                               'request':self.request}]}),encoding='utf8')
        output=self.root/'report'
        final_report.compose(plan,output,self.manifest,self.pin,self.sources)
        text=(output/'first-response.md').read_text(encoding='utf8')
        for fragment in ['"range_width": 67','"iqr": 31','LINEAR_INTERPOLATION_INDEX_(n-1)*p',
                         '"provider": "Atlas"','"mean": 95','PROVIDER_REPORTED_NOT_COMBINED']:
            self.assertIn(fragment,text)
        self.assertEqual((output/'originals/evidence.json').read_bytes(),raw)
        final_report.verify(output)
        structured=json.loads((output/'analysis.json').read_bytes())
        self.assertIn('"range_width": 67',json.dumps(structured))
        self.assertIn('"provider": "Atlas"',json.dumps(structured))
        metadata=self.root/'metadata.json'
        metadata.write_text(json.dumps({'case_id':'synthetic-consensus',
            'runtime_model_metadata':{'model':'unknown','effort':'unknown'}}),encoding='utf8')
        exported=self.root/'exported'
        final_report.export_response(output,metadata,exported)
        final_report.verify_response(exported)
        response=json.loads((exported/'response.json').read_bytes())
        consensus=response['rows'][0]['result']['eligible_cohort']['result']['consensus']
        self.assertEqual((consensus['range_width'],consensus['iqr']),(67,31))
        self.assertEqual(response['rows'][0]['result']['eligible_cohort']['result']['provider_consensus'][0]['provider'],'Atlas')
        (output/'first-response.md').write_text(text.replace('"iqr": 31','"iqr": 32'),encoding='utf8')
        with self.assertRaises(ValueError): final_report.verify(output)


if __name__=='__main__':unittest.main()
