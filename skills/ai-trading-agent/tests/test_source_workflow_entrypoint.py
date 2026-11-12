import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class SourceWorkflowEntrypointTests(unittest.TestCase):
    def test_main_workflow_runs_and_replays_original_source_report(self):
        script = Path(__file__).resolve().parents[1] / 'scripts/research_workflow.py'
        with tempfile.TemporaryDirectory(prefix='source-workflow-entry-') as temp:
            root = Path(temp)
            originals = root / 'originals'
            originals.mkdir()
            from test_reit_sources import fixture
            source_request, original = fixture()
            raw = json.dumps(original).encode()
            (originals / 'record.json').write_bytes(raw)
            manifest = root / 'manifest.json'
            manifest.write_text(json.dumps({'schema_version':1,'sources':[{
                'id':'original','path':'record.json','format':'json',
                'sha256':hashlib.sha256(raw).hexdigest()}]}), encoding='utf-8')
            pin = hashlib.sha256(manifest.read_bytes()).hexdigest()
            request = root / 'request.json'
            request.write_text(json.dumps({'producer':'reit_sources','producer_request':source_request}), encoding='utf-8')
            output = root / 'result'
            command = [sys.executable,'-B',str(script)]
            run = subprocess.run(command + ['source-run',str(request),'--manifest',str(manifest),
                '--manifest-sha256',pin,'--source-root',str(originals),'--private-output-dir',str(output)],
                capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)
            result = json.loads((output/'result.json').read_bytes())
            self.assertTrue(result['metric_ledger']['affo']['source_bound_comparability'])
            self.assertEqual((output/'originals/record.json').read_bytes(),raw)
            verified = subprocess.run(command + ['source-verify',str(output)],capture_output=True,text=True)
            self.assertEqual(verified.returncode,0,verified.stderr)
            plan=root/'final-plan.json';final=root/'final-output'
            plan.write_text(json.dumps({'sections':[{'kind':'source_report','producer':'reit_sources','request':source_request}]}),encoding='utf-8')
            composed=subprocess.run(command+['final-compose',str(plan),'--manifest',str(manifest),
                '--manifest-sha256',pin,'--source-root',str(originals),'--private-output-dir',str(final)],capture_output=True,text=True)
            self.assertEqual(composed.returncode,0,composed.stdout+composed.stderr)
            final_check=subprocess.run(command+['final-verify',str(final),'--final-response',str(final/'first-response.md')],capture_output=True,text=True)
            self.assertEqual(final_check.returncode,0,final_check.stdout+final_check.stderr)
            for args in (['source-verify',str(output),'--manifest',str(manifest)],
                         ['final-verify',str(final),'--source-root',str(originals)],
                         ['source-run',str(request),'--final-response',str(final/'first-response.md')]):
                rejected=subprocess.run(command+args,capture_output=True,text=True)
                self.assertNotEqual(rejected.returncode,0)
            (output/'report.md').write_text('Contradictory replacement report.',encoding='utf-8')
            rejected = subprocess.run(command + ['source-verify',str(output)],capture_output=True,text=True)
            self.assertNotEqual(rejected.returncode,0)


if __name__ == '__main__':
    unittest.main()
