"""Synthetic cutoff-local annotations and native-to-canonical replay controls."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import market_sources
import market_flow
import market_flow_report
import final_report
from test_market_flow import pressure_document

CUTOFFS=['2026-11-11T17:30:00Z','2026-11-11T18:30:00Z',
         '2026-11-11T21:00:00Z','2026-11-11T23:00:00Z']


def at(document, cutoff):
    result=deepcopy(document);result['as_of']=cutoff;return result


def example(shape='fork', unknown_basis=False):
    document=pressure_document()
    for row in document['records']:
        row['available_at']='2026-11-11T17:00:00Z'
        row['source'].update(observed_at=row['available_at'],retrieved_at=row['available_at'])
    original=document['records'][-1]
    original['caller_provenance']={'note':'Retain declared history independently of engine annotations.'}
    original['payload']['amendment_ambiguity']={'source_note':'Caller payload field remains untouched.'}
    first=deepcopy(original)
    first.update(id='r1',action='cancel' if shape=='cancel' else 'replace',supersedes='si',
                 available_at='2026-11-11T17:00:00Z' if shape=='equal_clock' else '2026-11-11T18:00:00Z')
    first['source'].update(observed_at=first['available_at'],retrieved_at=first['available_at'])
    document['records'].append(first)
    if shape not in ('cancel','equal_clock'):
        second=deepcopy(first)
        second.update(id='r2',action='cancel' if shape in ('fork_cancel','linear_cancel') else 'replace',
                      supersedes='r1' if shape in ('linear','linear_cancel') else 'si',
                      available_at='2026-11-11T22:00:00Z' if shape=='future_fork' else '2026-11-11T19:00:00Z')
        second['source'].update(observed_at=second['available_at'],retrieved_at=second['available_at'])
        document['records'].append(second)
    if unknown_basis:
        for row in document['records']:
            for field in ('adjustment_basis','price_basis','volume_basis'):
                if field in row['payload']:row['payload'][field]='UNKNOWN'
    return document


def normalized_request(document):
    # The same enclosing settings are mandatory; normalize returns evidence only.
    result=deepcopy(document);result['records']=market_sources.normalize(document)['records'];return result


class CutoffRenormalizationTests(unittest.TestCase):
    def test_later_annotations_are_recomputed_without_mutating_originals(self):
        document=example();later=normalized_request(document);before=deepcopy(later)
        self.assertTrue(any(row.get('amendment_ambiguity') for row in later['records']))
        earlier=at(later,CUTOFFS[1]);result=market_sources.normalize(earlier)
        self.assertEqual(result,market_sources.normalize(at(document,CUTOFFS[1])))
        self.assertFalse(any(row.get('amendment_ambiguity') for row in result['records']))
        si=market_flow.positioning(earlier)['short_interest'][0]
        self.assertTrue(si['active_positioning_eligible'])
        self.assertEqual(market_flow.squeeze(earlier)['assessments'][0]['state'],'DEVELOPING_PRESSURE_HEURISTIC')
        self.assertEqual(later,before)
        original=next(row for row in result['records'] if row['id']=='si')
        self.assertEqual(original['caller_provenance'],document['records'][-3]['caller_provenance'])
        self.assertEqual(original['payload']['amendment_ambiguity'],{'source_note':'Caller payload field remains untouched.'})

    def test_raw_normalized_earlier_same_later_and_roundtrips_agree(self):
        for shape in ('fork','linear','cancel','fork_cancel','linear_cancel','equal_clock','future_fork'):
            raw=example(shape)
            for origin in CUTOFFS:
                normalized=normalized_request(at(raw,origin));before=deepcopy(normalized)
                for cutoff in CUTOFFS:
                    expected=at(raw,cutoff);reused=at(normalized,cutoff)
                    with self.subTest(shape=shape,origin=origin,cutoff=cutoff):
                        self.assertEqual(reused['settings'],expected['settings'])
                        self.assertEqual(market_sources.normalize(reused),market_sources.normalize(expected))
                        self.assertEqual(market_flow.positioning(reused),market_flow.positioning(expected))
                        self.assertEqual(market_flow.squeeze(reused),market_flow.squeeze(expected))
                self.assertEqual(normalized,before)
            reused=at(raw,CUTOFFS[-1])
            for cutoff in CUTOFFS[::-1]+CUTOFFS:
                reused=normalized_request(at(reused,cutoff))
                self.assertEqual(market_sources.normalize(reused),market_sources.normalize(at(raw,cutoff)))

    def test_future_branch_retained_or_removed_gives_same_earlier_assessment(self):
        raw=example();later=normalized_request(raw)
        assessments=[]
        for document in (raw,later):
            for remove in (False,True):
                earlier=at(document,CUTOFFS[1])
                if remove:earlier['records']=[row for row in earlier['records'] if row['id']!='r2']
                result=market_flow.squeeze(earlier)
                assessments.append(result['assessments'])
                self.assertEqual(len(result['evidence']['records']),len(raw['records'])-int(remove))
                if not remove:
                    future=next(row for row in result['evidence']['records'] if row['id']=='r2')
                    self.assertIn('NOT_YET_AVAILABLE',future['exclusion_reasons'])
        self.assertTrue(all(row==assessments[0] for row in assessments))
        self.assertEqual(assessments[0][0]['state'],'DEVELOPING_PRESSURE_HEURISTIC')

    def test_real_current_ambiguity_cancellation_and_unknown_bases_stay_conservative(self):
        for shape in ('fork','fork_cancel','equal_clock'):
            document=normalized_request(example(shape))
            for _ in range(3):document=normalized_request(document)
            result=market_flow.squeeze(document)
            with self.subTest(shape=shape):
                self.assertTrue(result['assessments'])
                self.assertTrue(all(row['state']=='INSUFFICIENT_EVIDENCE' and not row['active_positioning_eligible'] for row in result['assessments']))
        for shape in ('cancel','linear_cancel'):
            self.assertEqual(market_flow.squeeze(normalized_request(example(shape)))['assessments'],[])
        linear=market_flow.squeeze(normalized_request(example('linear')))['assessments']
        self.assertEqual(len(linear),1);self.assertEqual(linear[0]['short_interest_record_id'],'r2')
        self.assertEqual(linear[0]['state'],'DEVELOPING_PRESSURE_HEURISTIC')
        unknown=at(normalized_request(example(unknown_basis=True)),CUTOFFS[1])
        si=market_flow.positioning(unknown)['short_interest'][0]
        self.assertTrue(si['active_positioning_eligible'])
        self.assertIsNone(si['short_interest_percent_float']);self.assertIsNone(si['adv']['days_to_cover'])
        self.assertEqual(market_flow.squeeze(unknown)['assessments'][0]['state'],'INSUFFICIENT_EVIDENCE')

    def test_source_bound_and_exported_canonical_results_use_requested_cutoff(self):
        with tempfile.TemporaryDirectory(prefix='mf-cut-') as temporary:
            root=Path(temporary);raw=example();later=normalized_request(raw)
            documents={'raw':at(raw,CUTOFFS[1]),'reused':at(later,CUTOFFS[1])}
            inventory=[];bindings=[]
            for name,document in documents.items():
                data=json.dumps(document).encode();(root/(name+'.json')).write_bytes(data)
                inventory.append({'id':name,'path':name+'.json','format':'json','sha256':hashlib.sha256(data).hexdigest()})
                bindings.append({'id':name,'source_ref':{'source_id':name,'pointer':''}})
            manifest=root/'i.json';manifest.write_text(json.dumps({'schema_version':1,'sources':inventory}))
            pin=hashlib.sha256(manifest.read_bytes()).hexdigest()
            request={'documents':bindings,'operations':['flow','positioning','squeeze']}
            result=market_flow_report.analyze(request,manifest,pin,root)
            self.assertEqual(result['rows'][0]['operations'],result['rows'][1]['operations'])
            self.assertEqual(result['rows'][1]['operations']['squeeze']['result']['assessments'][0]['state'],'DEVELOPING_PRESSURE_HEURISTIC')
            plan=root/'p.json';plan.write_text(json.dumps({'output_contract':final_report.STRICT,'sections':[
                {'kind':'source_report','producer':'market_flow_report','request':request}]}))
            report=root/'r';final_report.compose(plan,report,manifest,pin,root)
            metadata=root/'m.json';metadata.write_text(json.dumps({'case_id':'synthetic-cutoff-reuse',
                'runtime_model_metadata':{'model':'unknown','effort':'unknown'}}))
            output=root/'e';final_report.export_response(report,metadata,output);final_report.verify_response(output)
            response=json.loads((output/'response.json').read_bytes())
            rows=response['rows'][0]['result']['rows']
            self.assertEqual(rows[0]['operations'],rows[1]['operations'])
            self.assertTrue(rows[1]['operations']['positioning']['result']['short_interest'][0]['active_positioning_eligible'])
            text=(report/'first-response.md').read_text(encoding='utf8')
            self.assertEqual(text.count('"state": "DEVELOPING_PRESSURE_HEURISTIC"'),2)
            self.assertNotIn('"state": "INSUFFICIENT_EVIDENCE"',text)
            # The original later-normalized source still retains its old annotation.
            retained=json.loads((root/'reused.json').read_bytes())
            self.assertTrue(any(row.get('amendment_ambiguity') for row in retained['records']))
            self.assertEqual(retained,documents['reused'])


if __name__=='__main__':unittest.main()
