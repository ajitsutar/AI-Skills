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
            raw = b'{"distribution":{"holder_scope":"common","amount":13}}\n'
            (originals / 'record.json').write_bytes(raw)
            manifest = root / 'manifest.json'
            manifest.write_text(json.dumps({'schema_version':1,'sources':[{
                'id':'record','path':'record.json','format':'json',
                'sha256':hashlib.sha256(raw).hexdigest()}]}), encoding='utf-8')
            pin = hashlib.sha256(manifest.read_bytes()).hexdigest()
            request = root / 'request.json'
            request.write_text(json.dumps({'producer':'source_claims',
                                          'producer_request':{'operation':'presence','terms':['common']}}), encoding='utf-8')
            output = root / 'result'
            command = [sys.executable,'-B',str(script)]
            run = subprocess.run(command + ['source-run',str(request),'--manifest',str(manifest),
                '--manifest-sha256',pin,'--source-root',str(originals),'--private-output-dir',str(output)],
                capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)
            result = json.loads((output/'result.json').read_bytes())
            self.assertEqual(result['predicate'],'SOURCE_CANDIDATE_PRESENT')
            self.assertEqual((output/'originals/record.json').read_bytes(),raw)
            verified = subprocess.run(command + ['source-verify',str(output)],capture_output=True,text=True)
            self.assertEqual(verified.returncode,0,verified.stderr)
            (output/'report.md').write_text('Contradictory replacement report.',encoding='utf-8')
            rejected = subprocess.run(command + ['source-verify',str(output)],capture_output=True,text=True)
            self.assertNotEqual(rejected.returncode,0)


if __name__ == '__main__':
    unittest.main()
