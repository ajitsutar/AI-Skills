"""Generic final artifact counterexamples; no private evaluation values."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import final_report as module


class FinalReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='final-report-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.originals = self.root / 'originals'; self.originals.mkdir()
        self.manifest = self.root / 'manifest.json'; self.request = self.root / 'plan.json'; self.output = self.root / 'output'
        from test_reit_sources import fixture
        request, original = fixture()
        self.sources([('original', 'json', original)])
        self.plan = {'sections': [{'kind':'source_report','producer':'reit_sources','request':request}]}

    def sources(self, rows):
        entries = []
        for sid, fmt, value in rows:
            raw = json.dumps(value).encode() if fmt == 'json' else value.encode() if isinstance(value, str) else value
            name = sid + '.source'; (self.originals / name).write_bytes(raw)
            entries.append({'id': sid, 'path': name, 'format': fmt, 'sha256': hashlib.sha256(raw).hexdigest()})
        self.manifest.write_text(json.dumps({'schema_version': 1, 'sources': entries}), encoding='utf-8')
        self.pin = hashlib.sha256(self.manifest.read_bytes()).hexdigest()

    def compose(self):
        self.request.write_text(json.dumps(self.plan), encoding='utf-8')
        return module.compose(self.request, self.output, self.manifest, self.pin, self.originals)

    def report(self): return (self.output / 'first-response.md').read_text(encoding='utf-8')

    def resign_inventory(self):
        path = self.output / 'receipt.json'; receipt = json.loads(path.read_bytes())
        receipt['artifacts'] = module.source.file_inventory(self.output)
        path.write_bytes(module.source.encode(receipt))



    def test_reit_real_execution_final_bytes_and_receipt(self):
        receipt = self.compose()
        self.assertEqual(receipt['status'], 'FINAL_REPORT_REPLAY_AND_BYTES_MATCH')
        self.assertFalse(receipt['whole_report_semantic_pass'])
        self.assertEqual(receipt['response_file'], 'first-response.md')
        self.assertIn('source-record compatible arithmetic', self.report())
        self.assertIn('Source replay', self.report())
        self.assertEqual(module.verify(self.output)['final_response_sha256'], receipt['final_response_sha256'])








    def test_unaudited_contradictory_prose_remains_partial_with_byte_spans(self):
        self.plan['unverified_prose'] = 'Ω: These numbers prove every company has guaranteed EPS.'
        receipt = self.compose(); self.assertEqual(receipt['status'], 'PARTIAL_UNAUDITED_PROSE')
        raw = (self.output/'first-response.md').read_bytes(); span = receipt['unverified_spans'][0]
        self.assertEqual(raw[span['start_byte']:span['end_byte']], self.plan['unverified_prose'].encode())
        self.assertIn('not verified by the source', self.report()); self.assertFalse(receipt['whole_report_semantic_pass'])

    def test_edited_final_report_rejected_even_after_inventory_resign(self):
        self.compose(); (self.output/'first-response.md').write_text('Fabricated conclusion.')
        self.resign_inventory()
        with self.assertRaisesRegex(ValueError, 'FINAL_RESPONSE_BYTES_MISMATCH'): module.verify(self.output)

    def test_unrelated_published_response_rejected(self):
        self.compose(); path = self.root/'published.md'; path.write_bytes((self.output/'first-response.md').read_bytes())
        module.verify(self.output, path)
        path.write_text('Different saved final response.')
        with self.assertRaisesRegex(ValueError, 'PUBLISHED_RESPONSE_DIFFERS'): module.verify(self.output, path)

    def test_authored_cached_result_request_rejected(self):
        self.plan['sections'][0]['result'] = {'status': 'PASS'}
        with self.assertRaisesRegex(ValueError, 'EXACT_PLAN_OR_SECTION'): self.compose()

    def test_changed_producer_output_rejected_after_outer_inventory_resign(self):
        self.compose(); path = self.output/'sections/000/producer/result.json'
        result = json.loads(path.read_bytes()); result['predicate'] = 'SOURCE_ABSENT'; path.write_text(json.dumps(result))
        self.resign_inventory()
        with self.assertRaisesRegex(ValueError, 'RETAINED_ARTIFACT'): module.verify(self.output)

    def test_rehashed_authored_success_cannot_replace_original_producer_replay(self):
        self.compose(); producer=self.output/'sections/000/producer'
        path=producer/'result.json'; result=json.loads(path.read_bytes())
        result['predicate']='SOURCE_ABSENT'; path.write_bytes(module.source.encode(result))
        receipt_path=producer/'receipt.json'; receipt=json.loads(receipt_path.read_bytes())
        receipt['artifacts']=module.source.file_inventory(producer)
        receipt_path.write_bytes(module.source.encode(receipt)); self.resign_inventory()
        with self.assertRaisesRegex(ValueError,'ORIGINAL_SOURCE_REPLAY_MISMATCH'): module.verify(self.output)

    def test_section_deletion_rejected(self):
        self.compose(); shutil.rmtree(self.output/'sections/000'); self.resign_inventory()
        with self.assertRaisesRegex(ValueError, 'SECTION_SET_CHANGED'): module.verify(self.output)

    def test_relocated_whole_report_replays_with_original_location_removed(self):
        self.compose()
        relocated = self.root/'relocated'; shutil.copytree(self.output, relocated)
        self.output.rename(self.root/'old-run'); self.originals.rename(self.root/'old-sources')
        self.assertEqual(module.verify(relocated)['status'], 'FINAL_REPORT_REPLAY_AND_BYTES_MATCH')


    def test_existing_output_is_never_overwritten(self):
        self.output.mkdir(); marker=self.output/'keep'; marker.write_text('original')
        with self.assertRaisesRegex(ValueError, 'NEW_PRIVATE_OUTPUT_REQUIRED'): self.compose()
        self.assertEqual(marker.read_text(), 'original')

    def test_original_manifest_pin_and_nonselected_source_tamper_rejected(self):
        from test_reit_sources import fixture
        _, original = fixture()
        self.sources([('original','json',original),('unselected','text','Other source')])
        (self.originals/'unselected.source').write_text('Changed source')
        with self.assertRaises(ValueError): self.compose()
        self.assertFalse((self.output/'receipt.json').exists())

    def test_unsupported_section_and_producer_kinds_are_rejected(self):
        for section in ({'kind':'source_claim','request':{'operation':'presence'}},
                        {'kind':'terminal_objectives','document':{},'contract':{}},
                        {'kind':'source_report','producer':'analyst_sources','request':{}},
                        {'kind':'source_report','producer':'source_claims','request':{}}):
            with self.subTest(section=section), self.assertRaises(ValueError):
                module.plan(json.dumps({'sections':[section]}).encode())

    def test_original_property_fact_survives_omitted_requested_rows(self):
        from test_reit_sources import fixture
        request, original = fixture()
        request['document'].pop('property_fractions',None)
        original['portfolio']={'largest_tenant_revenue_fraction':0.37}
        self.sources([('original','json',original)])
        self.plan['sections'][0]['request']=request
        self.compose();text=self.report()
        self.assertIn('0.37',text);self.assertIn('revenue',text)
        self.assertIn('unknown',text.lower());module.verify(self.output)

    def test_multiple_reit_sections_preserve_order(self):
        self.plan['sections'].append(copy.deepcopy(self.plan['sections'][0]))
        self.plan['sections'][1]['request']['bindings']=[]
        self.compose();audit=module.verify(self.output)
        self.assertEqual([s['kind'] for s in audit['sections']],['source_report','source_report'])
        self.assertIn('conditional',self.report().lower())

    def test_real_cli_compose_and_verify(self):
        self.request.write_text(json.dumps(self.plan), encoding='utf8')
        command=[sys.executable,'-B',module.__file__]
        done=subprocess.run(command+['compose',str(self.request),'--manifest',str(self.manifest),
            '--manifest-sha256',self.pin,'--source-root',str(self.originals),'--output',str(self.output)],capture_output=True,text=True)
        self.assertEqual(done.returncode,0,done.stdout+done.stderr)
        checked=subprocess.run(command+['verify',str(self.output),'--final-response',str(self.output/'first-response.md')],capture_output=True,text=True)
        self.assertEqual(checked.returncode,0,checked.stdout+checked.stderr)


if __name__ == '__main__': unittest.main(verbosity=2)
