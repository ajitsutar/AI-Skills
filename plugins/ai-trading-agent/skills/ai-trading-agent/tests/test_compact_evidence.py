"""Behavioral compact-storage and exact replay regressions with fictional data."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import evidence_storage as es
import quant_report as qr
import research_workflow as wf
import report_facts as rf
import answer_facts

def fixture(count=250):
    source = qr.encoded({'returns':[.01 if i%3 else -.012 for i in range(count)],
                         'unused':{'publication_time':'2025-01-01T12:00:00Z','units':'fraction'}})
    jobs=[{'id':'j'+str(i),'operation':'validation.hac','arguments':{
        'returns':{'$source':{'id':'s','pointer':'/returns'}},
        'lags':{'$assumption':1,'reason':'fictional sensitivity'}}} for i in range(3)]
    plan={'schema_version':1,'network_mode':'offline','contract':{'prompt':'Fictional repeated series','purpose':'offline synthetic test','base_currency':'USD','horizon_id':'P1Y','as_of':'2025-01-01T00:00:00Z'},
          'sources':[{'id':'s','path':'source.json','sha256':wf.sha(source),'format':'json','role':'fictional returns'}],
          'jobs':jobs,'requirements':[{'id':'r','question':'Compare hypothetical jobs','job_ids':[j['id'] for j in jobs]}],
          'claims':[{'id':'c','job_id':'j0','pointer':'/result/mean'}]}
    return plan,source

class CompactEvidenceTests(unittest.TestCase):
    def test_redirected_object_directory_prevents_write(self):
        with tempfile.TemporaryDirectory() as temp:
            store=es.ArtifactStore(Path(temp)/'store',create=True)
            original=Path.lstat
            def redirected(path):
                info=original(path)
                if path == store.root/'objects':
                    return SimpleNamespace(st_mode=info.st_mode,st_file_attributes=0x400)
                return info
            # Windows junction attribute is checked on the lexical ancestor,
            # before a resolver could hide its redirect. No object is opened.
            with mock.patch.object(Path,'lstat',redirected),mock.patch.object(Path,'open',side_effect=AssertionError('must not open')):
                with self.assertRaisesRegex(ValueError,'REDIRECT'):
                    store.write('new.json',b'private')
            self.assertEqual(list((store.root/'objects').iterdir()),[])

    def test_oversized_stored_blob_rejected_before_allocation(self):
        with tempfile.TemporaryDirectory() as temp:
            store=es.ArtifactStore(Path(temp)/'store',create=True)
            store.write('data.json',b'private')
            with mock.patch.object(es,'MAX_STORED_BYTES',1),mock.patch.object(Path,'open',side_effect=AssertionError('must not open')):
                with self.assertRaisesRegex(ValueError,'SIZE_LIMIT'):
                    store.read('data.json')

    def test_compressed_memory_budget_is_explicit(self):
        artifacts=es.CompressedArtifacts()
        with mock.patch.object(es,'MAX_RESIDENT_COMPRESSED_BYTES',1):
            with self.assertRaisesRegex(ValueError,'MEMORY_LIMIT'):
                artifacts['data.json']=b'private'
        self.assertEqual(len(artifacts),0)

    def test_content_addressed_roundtrip_deduplicates_and_bounds(self):
        with tempfile.TemporaryDirectory() as temp:
            store=es.ArtifactStore(Path(temp)/'store',create=True)
            raw=b'fictional-data\n'*10000
            store.write('first/data.txt',raw)
            store.write('second/data.txt',raw)
            self.assertEqual(len(list((store.root/'objects').glob('*'))),1)
            self.assertEqual(store.read('first/data.txt'),raw)
            self.assertLess(sum(p.stat().st_size for p in store.root.rglob('*') if p.is_file()),len(raw)//10)
            with self.assertRaises(ValueError):store.write('../escape',b'x')
            with self.assertRaises(ValueError):store.write('first/data.txt',b'x')
            row=store.index['artifacts']['first/data.txt']
            row['bytes']=3
            with self.assertRaises(ValueError):store.read('first/data.txt')

    def test_changed_compressed_object_and_alias_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            store=es.ArtifactStore(Path(temp)/'store',create=True)
            store.write('data.json',b'{"units":"USD","value":42}')
            row=store.index['artifacts']['data.json']
            target=store.root/row['object']
            raw=target.read_bytes();target.write_bytes(raw[:-1]+bytes([raw[-1]^1]))
            with self.assertRaises(ValueError):store.read('data.json')
            target.write_bytes(raw)
            row['object']='../outside.gz'
            with self.assertRaises(ValueError):store.read('data.json')

    def test_workflow_numerics_claims_and_complete_fields_match_legacy(self):
        plan,source=fixture()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'source.json').write_bytes(source);(root/'plan.json').write_bytes(wf.encode(plan))
            legacy=wf.run(root/'plan.json',root/'legacy')
            compact=wf.run(root/'plan.json',root/'compact',compact_evidence=True)
            self.assertEqual(legacy,compact)
            self.assertEqual(wf.verify(root/'compact')['status'],'WORKFLOW_REPLAY_AND_REPORT_MATCH')
            self.assertEqual(answer_facts.project_verified(root/'compact')['result_sha256'],wf.sha(wf.encode(compact)))
            reader=es.Reader(root/'compact')
            self.assertEqual(reader.read('sources/source.json'),source)
            self.assertEqual(compact['unused_source_pointers'],legacy['unused_source_pointers'])
            self.assertEqual(compact['claims'][0]['status'],'PROJECTED')
            bundle=reader.read('jobs/0000/quant/bundle.json')
            descriptor=rf.strict_json(reader.read('jobs/0000/quant/facts.json'))
            full=rf.materialize_compact(bundle,descriptor)
            self.assertEqual(full,rf.project(bundle,'quant'))
            legacy_size=sum(p.stat().st_size for p in (root/'legacy').rglob('*') if p.is_file())
            compact_size=sum(p.stat().st_size for p in (root/'compact').rglob('*') if p.is_file())
            self.assertLess(compact_size,legacy_size/5)
            self.assertLess(len(reader.read('report.md')),40000)

    def test_unchanged_index_does_not_hide_source_corruption(self):
        plan,source=fixture(12)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'source.json').write_bytes(source);(root/'plan.json').write_bytes(wf.encode(plan))
            wf.run(root/'plan.json',root/'compact',compact_evidence=True)
            store=es.ArtifactStore(root/'compact');row=store.index['artifacts']['sources/source.json']
            (store.root/row['object']).write_bytes(es.compress(source+b' '))
            with self.assertRaises(ValueError):wf.verify(root/'compact')

    def test_descriptor_requires_exact_source_and_options(self):
        raw=qr.encoded({'schema_version':1,'input':{'units':'USD'},'result':{}})
        descriptor=rf.compact_descriptor(raw,'quant')
        with self.assertRaises(ValueError):rf.materialize_compact(raw+b' ',descriptor)
        changed=copy.deepcopy(descriptor);changed['source_bytes']+=1
        with self.assertRaises(ValueError):rf.materialize_compact(raw,changed)

    def test_compact_execute_and_standalone_quant_replay(self):
        request={'schema_version':1,'contract':{'prompt':'Fictional returns','purpose':'offline synthetic test','base_currency':'USD','horizon_id':'P1Y','as_of':'2025-01-01T00:00:00Z'},
          'jobs':[{'id':'a','operation':'validation.hac','inputs':{'returns':[.01,-.02,.03,.01,.04],'lags':1}}],
          'requirements':[{'id':'r','question':'Compute','job_ids':['a']}],
          'claims':[{'id':'c','job_id':'a','pointer':'/result/mean'}]}
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'request.json').write_bytes(qr.encoded(request))
            completion=wf.execute(root/'request.json',root/'execute','fictional request',compact_evidence=True)
            self.assertEqual(completion['status'],'COMPLETED_LOCAL_WORKFLOW',completion.get('failure'))
            self.assertEqual(answer_facts.project_verified(root/'execute')['verification']['status'],'WORKFLOW_REPLAY_AND_REPORT_MATCH')
            qr.run(root/'request.json',root/'quant',compact_evidence=True)
            self.assertEqual(qr.verify(root/'quant')['status'],'REPLAY_AND_REPORT_MATCH')

    def test_standalone_quant_binds_storage_implementation(self):
        request={'schema_version':1,
          'contract':{'prompt':'Fictional returns','purpose':'offline synthetic test','base_currency':'USD','horizon_id':'P1Y','as_of':'2025-01-01T00:00:00Z'},
          'jobs':[{'id':'a','operation':'validation.hac','inputs':{'returns':[.01,-.02,.03,.01,.04],'lags':1}}]}
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'request.json').write_bytes(qr.encoded(request))
            qr.run(root/'request.json',root/'quant',compact_evidence=True)
            original_hash=rf.code_hash
            with mock.patch.object(rf,'code_hash',side_effect=lambda name:'0'*64 if name=='evidence_storage.py' else original_hash(name)):
                with self.assertRaisesRegex(ValueError,'COMPACT_STORAGE_CODE_MISMATCH'):
                    qr.verify(root/'quant')

if __name__=='__main__':unittest.main()
